/**
 * Cloudflare Worker for RDR-Transit 6-Digit Signaling & Pairing
 *
 * Ephemeral matchmaking room coordinator for exchanging initial WebRTC SDP tokens (<3 KB).
 * File transfers and message streams never touch this worker—they run 100% direct LAN P2P.
 */

export interface Env {
  ROOMS?: DurableObjectNamespace;
}

interface RoomState {
  code: string;
  offer: string;
  sessionId?: string;
  answer?: string;
  createdAt: number;
  expiresAt: number;
  waiters: Array<(answer: string | null) => void>;
}

interface ReconnectState {
  sessionId: string;
  offer?: string;
  answer?: string;
  createdAt: number;
  expiresAt: number;
  waiters: Array<(answer: string | null) => void>;
}

// In-memory ephemeral room stores (TTL: 120s for rooms, 60s for reconnects)
const rooms = new Map<string, RoomState>();
const reconnects = new Map<string, ReconnectState>();

const ROOM_TTL_MS = 120 * 1000; // 2 minutes
const RECONNECT_TTL_MS = 60 * 1000; // 1 minute

function cleanupExpired() {
  const now = Date.now();
  for (const [code, room] of rooms.entries()) {
    if (now >= room.expiresAt) {
      for (const waiter of room.waiters) {
        waiter(null);
      }
      rooms.delete(code);
    }
  }
  for (const [id, rec] of reconnects.entries()) {
    if (now >= rec.expiresAt) {
      for (const waiter of rec.waiters) {
        waiter(null);
      }
      reconnects.delete(id);
    }
  }
}

function generateNumericCode(): string {
  // 6-digit numeric PIN: 100000 - 999999
  for (let attempt = 0; attempt < 50; attempt++) {
    const code = Math.floor(100000 + Math.random() * 900000).toString();
    if (!rooms.has(code)) {
      return code;
    }
  }
  return Math.floor(100000 + Math.random() * 900000).toString();
}

const CORS_HEADERS: Record<string, string> = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type, Authorization',
  'Access-Control-Max-Age': '86400',
};

function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      'Content-Type': 'application/json',
      ...CORS_HEADERS,
    },
  });
}

function errorResponse(message: string, status = 400): Response {
  return jsonResponse({ error: message }, status);
}

export default {
  async fetch(request: Request, env: Env, _ctx: ExecutionContext): Promise<Response> {
    if (request.method === 'OPTIONS') {
      return new Response(null, {
        status: 204,
        headers: CORS_HEADERS,
      });
    }

    cleanupExpired();

    const url = new URL(request.url);
    const path = url.pathname.replace(/\/+$/, '') || '/';

    try {
      // 1. Health check
      if (path === '' || path === '/' || path === '/api/health') {
        return jsonResponse({
          status: 'ok',
          service: 'rdr-transit-signaling',
          activeRooms: rooms.size,
          activeReconnects: reconnects.size,
          timestamp: Date.now(),
        });
      }

      // 2. POST /api/room -> Create room with Host Offer SDP
      if (path === '/api/room' && request.method === 'POST') {
        const body = (await request.json().catch(() => null)) as {
          offer?: string;
          sessionId?: string;
        } | null;

        if (!body || !body.offer || typeof body.offer !== 'string') {
          return errorResponse('Missing or invalid "offer" token', 400);
        }

        const code = generateNumericCode();
        const now = Date.now();
        const room: RoomState = {
          code,
          offer: body.offer,
          sessionId: body.sessionId,
          createdAt: now,
          expiresAt: now + ROOM_TTL_MS,
          waiters: [],
        };

        rooms.set(code, room);

        return jsonResponse({
          code,
          roomId: code,
          expiresAt: room.expiresAt,
          ttlSeconds: ROOM_TTL_MS / 1000,
        });
      }

      // 3. GET /api/room/:code -> Joiner fetches Host Offer SDP
      const roomGetMatch = path.match(/^\/api\/room\/([0-9]{6})$/);
      if (roomGetMatch && request.method === 'GET') {
        const code = roomGetMatch[1];
        const room = rooms.get(code);

        if (!room || Date.now() >= room.expiresAt) {
          return errorResponse('Room not found or expired', 404);
        }

        return jsonResponse({
          code: room.code,
          offer: room.offer,
          sessionId: room.sessionId,
          expiresAt: room.expiresAt,
        });
      }

      // 4. POST /api/room/:code/answer -> Joiner submits Answer SDP
      const answerMatch = path.match(/^\/api\/room\/([0-9]{6})\/answer$/);
      if (answerMatch && request.method === 'POST') {
        const code = answerMatch[1];
        const room = rooms.get(code);

        if (!room || Date.now() >= room.expiresAt) {
          return errorResponse('Room not found or expired', 404);
        }

        const body = (await request.json().catch(() => null)) as {
          answer?: string;
        } | null;

        if (!body || !body.answer || typeof body.answer !== 'string') {
          return errorResponse('Missing or invalid "answer" token', 400);
        }

        room.answer = body.answer;

        // Notify any active polling waiters immediately
        for (const waiter of room.waiters) {
          waiter(room.answer);
        }
        room.waiters = [];

        return jsonResponse({ success: true, message: 'Answer delivered' });
      }

      // 5. GET /api/room/:code/poll -> Host waits for Joiner's Answer SDP
      const pollMatch = path.match(/^\/api\/room\/([0-9]{6})\/poll$/);
      if (pollMatch && request.method === 'GET') {
        const code = pollMatch[1];
        const room = rooms.get(code);

        if (!room || Date.now() >= room.expiresAt) {
          return errorResponse('Room not found or expired', 404);
        }

        // If answer is already submitted, deliver it immediately and clean up room
        if (room.answer) {
          const answer = room.answer;
          rooms.delete(code);
          return jsonResponse({ answer, ready: true });
        }

        // Long-poll: hold connection up to timeout seconds (max 25s)
        const timeoutParam = parseInt(url.searchParams.get('timeout') || '20', 10);
        const timeoutSec = Math.min(Math.max(timeoutParam, 1), 25);

        const answer = await new Promise<string | null>((resolve) => {
          let timer: ReturnType<typeof setTimeout> | null = null;

          const onAnswer = (ans: string | null) => {
            if (timer) clearTimeout(timer);
            resolve(ans);
          };

          room.waiters.push(onAnswer);

          timer = setTimeout(() => {
            const idx = room.waiters.indexOf(onAnswer);
            if (idx !== -1) room.waiters.splice(idx, 1);
            resolve(null);
          }, timeoutSec * 1000);
        });

        if (answer) {
          rooms.delete(code);
          return jsonResponse({ answer, ready: true });
        }

        return jsonResponse({ waiting: true, ready: false });
      }

      // 6. POST /api/reconnect -> Coordinate session reconnect across page refreshes
      if (path === '/api/reconnect' && request.method === 'POST') {
        const body = (await request.json().catch(() => null)) as {
          sessionId?: string;
          role?: 'host' | 'joiner';
          offer?: string;
          answer?: string;
        } | null;

        if (!body || !body.sessionId) {
          return errorResponse('Missing sessionId', 400);
        }

        const { sessionId, role, offer, answer } = body;
        const now = Date.now();
        let rec = reconnects.get(sessionId);

        if (!rec || now >= rec.expiresAt) {
          rec = {
            sessionId,
            createdAt: now,
            expiresAt: now + RECONNECT_TTL_MS,
            waiters: [],
          };
          reconnects.set(sessionId, rec);
        }

        if (role === 'host' && offer) {
          rec.offer = offer;
          return jsonResponse({ success: true, registeredOffer: true });
        }

        if (role === 'joiner' && answer) {
          rec.answer = answer;
          for (const waiter of rec.waiters) {
            waiter(answer);
          }
          rec.waiters = [];
          return jsonResponse({ success: true, registeredAnswer: true });
        }

        return jsonResponse({
          sessionId,
          hasOffer: !!rec.offer,
          offer: rec.offer,
          hasAnswer: !!rec.answer,
          answer: rec.answer,
        });
      }

      // 7. GET /api/reconnect/:sessionId -> Check reconnect state
      const recMatch = path.match(/^\/api\/reconnect\/([^/]+)$/);
      if (recMatch && request.method === 'GET') {
        const sessionId = recMatch[1];
        const rec = reconnects.get(sessionId);

        if (!rec || Date.now() >= rec.expiresAt) {
          return jsonResponse({ sessionId, active: false });
        }

        return jsonResponse({
          sessionId,
          active: true,
          hasOffer: !!rec.offer,
          offer: rec.offer,
          hasAnswer: !!rec.answer,
          answer: rec.answer,
        });
      }

      return errorResponse(`Endpoint not found: ${request.method} ${path}`, 404);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      return errorResponse(`Internal Server Error: ${msg}`, 500);
    }
  },
};
