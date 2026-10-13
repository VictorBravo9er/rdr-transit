/**
 * Lightweight signaling channel using BroadcastChannel (for instant same-browser cross-tab
 * synchronization) and lightweight public MQTT over WebSockets (for cross-device persistence).
 */

export interface SignalingMessage {
  type: 'reconnect_ping' | 'reconnect_offer' | 'reconnect_answer' | 'peer_refreshing' | 'disconnect';
  sessionId: string;
  fromRole?: 'host' | 'joiner';
  offerToken?: string;
  answerToken?: string;
  senderId?: string;
}

export class SignalingChannel {
  private bc: BroadcastChannel | null = null;
  private ws: WebSocket | null = null;
  private sessionId: string;
  private senderId: string;
  private onMessage: (msg: SignalingMessage) => void;
  private isClosed = false;
  private mqttConnected = false;

  constructor(sessionId: string, onMessage: (msg: SignalingMessage) => void) {
    this.sessionId = sessionId;
    this.senderId = 'tab_' + Math.random().toString(36).substring(2, 9);
    this.onMessage = onMessage;

    // 1. BroadcastChannel for zero-latency, offline same-origin tab persistence
    try {
      if (typeof BroadcastChannel !== 'undefined') {
        this.bc = new BroadcastChannel(`rdr_transit_${sessionId}`);
        this.bc.onmessage = (event) => {
          const msg: SignalingMessage = event.data;
          if (msg && msg.sessionId === this.sessionId && msg.senderId !== this.senderId) {
            this.onMessage(msg);
          }
        };
      }
    } catch (e) {
      console.warn('BroadcastChannel initialization failed:', e);
    }

    // 2. Public MQTT over WebSocket fallback for cross-device signaling
    this.initMqtt();
  }

  private initMqtt() {
    try {
      const topic = `rdr_transit/s_${this.sessionId}`;
      const ws = new WebSocket('wss://broker.emqx.io:8084/mqtt', ['mqtt']);
      ws.binaryType = 'arraybuffer';
      this.ws = ws;

      ws.onopen = () => {
        const clientId = 'rdr_' + Math.random().toString(36).substring(2, 9);
        const varHeader = [0, 4, 77, 81, 84, 84, 4, 2, 0, 60];
        const payload = [0, clientId.length, ...new TextEncoder().encode(clientId)];
        const packet = new Uint8Array([0x10, varHeader.length + payload.length, ...varHeader, ...payload]);
        ws.send(packet);
      };

      ws.onmessage = (event) => {
        if (!(event.data instanceof ArrayBuffer)) return;
        const buf = new Uint8Array(event.data);
        if (buf[0] === 0x20) {
          // CONNACK -> Send SUBSCRIBE
          this.mqttConnected = true;
          const topicBytes = new TextEncoder().encode(topic);
          const subPayload = [0, 1, 0, topicBytes.length, ...topicBytes, 0];
          ws.send(new Uint8Array([0x82, subPayload.length, ...subPayload]));
        } else if ((buf[0] & 0xf0) === 0x30) {
          // PUBLISH received
          try {
            const topicLen = (buf[2] << 8) | buf[3];
            const contentBytes = buf.subarray(4 + topicLen);
            const jsonStr = new TextDecoder().decode(contentBytes);
            const msg: SignalingMessage = JSON.parse(jsonStr);
            if (msg && msg.sessionId === this.sessionId && msg.senderId !== this.senderId) {
              this.onMessage(msg);
            }
          } catch (e) {
            console.warn('Failed to parse signaling message:', e);
          }
        }
      };

      ws.onerror = () => {
        // Silent fallback - BroadcastChannel handles same-device
      };

      ws.onclose = () => {
        this.mqttConnected = false;
      };
    } catch {
      // Ignore network errors in offline environments
    }
  }

  send(msg: Omit<SignalingMessage, 'sessionId' | 'senderId'>) {
    if (this.isClosed) return;
    const fullMsg: SignalingMessage = {
      ...msg,
      sessionId: this.sessionId,
      senderId: this.senderId,
    };

    // Send via BroadcastChannel
    if (this.bc) {
      try {
        this.bc.postMessage(fullMsg);
      } catch {}
    }

    // Send via MQTT WebSocket
    if (this.ws && this.ws.readyState === WebSocket.OPEN && this.mqttConnected) {
      try {
        const topic = `rdr_transit/s_${this.sessionId}`;
        const topicBytes = new TextEncoder().encode(topic);
        const payloadBytes = new TextEncoder().encode(JSON.stringify(fullMsg));
        const pubPayload = [0, topicBytes.length, ...topicBytes, ...payloadBytes];
        this.ws.send(new Uint8Array([0x30, pubPayload.length, ...pubPayload]));
      } catch {}
    }
  }

  close() {
    this.isClosed = true;
    if (this.bc) {
      try {
        this.bc.close();
      } catch {}
      this.bc = null;
    }
    if (this.ws) {
      try {
        this.ws.close();
      } catch {}
      this.ws = null;
    }
  }
}

export const DEFAULT_SIGNALING_URL = 'https://rdr-transit-signaling.workers.dev';
export const STORAGE_SIGNALING_URL_KEY = 'rdr_signaling_server_url';

export function getSignalingServerUrl(): string {
  try {
    const saved = localStorage.getItem(STORAGE_SIGNALING_URL_KEY);
    if (saved && saved.trim()) return saved.trim();
  } catch {}
  return DEFAULT_SIGNALING_URL;
}

export function setSignalingServerUrl(url: string) {
  try {
    localStorage.setItem(STORAGE_SIGNALING_URL_KEY, url.trim());
  } catch {}
}

export interface RoomCreationResult {
  code: string;
  roomId: string;
  expiresAt: number;
  ttlSeconds: number;
}

export interface RoomDetails {
  code: string;
  offer: string;
  sessionId?: string;
  expiresAt: number;
}

export class CloudflareSignalingClient {
  private baseUrl: string;

  constructor(customUrl?: string) {
    this.baseUrl = (customUrl || getSignalingServerUrl()).replace(/\/+$/, '');
  }

  getBaseUrl(): string {
    return this.baseUrl;
  }

  setBaseUrl(url: string) {
    this.baseUrl = url.replace(/\/+$/, '');
    setSignalingServerUrl(this.baseUrl);
  }

  async checkHealth(): Promise<{ ok: boolean; activeRooms?: number; error?: string }> {
    try {
      const controller = new AbortController();
      const id = setTimeout(() => controller.abort(), 4000);
      const res = await fetch(`${this.baseUrl}/api/health`, {
        signal: controller.signal,
      });
      clearTimeout(id);
      if (!res.ok) return { ok: false, error: `HTTP ${res.status}` };
      const data = await res.json();
      return { ok: true, activeRooms: data.activeRooms };
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Connection failed';
      return { ok: false, error: msg };
    }
  }

  async createRoom(offer: string, sessionId?: string): Promise<RoomCreationResult> {
    const res = await fetch(`${this.baseUrl}/api/room`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ offer, sessionId }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || `Failed to create room: HTTP ${res.status}`);
    }
    return res.json();
  }

  async joinRoom(code: string): Promise<RoomDetails> {
    const sanitizedCode = code.replace(/\D/g, '');
    const res = await fetch(`${this.baseUrl}/api/room/${sanitizedCode}`);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || `Room ${sanitizedCode} not found or expired`);
    }
    return res.json();
  }

  async submitAnswer(code: string, answer: string): Promise<void> {
    const sanitizedCode = code.replace(/\D/g, '');
    const res = await fetch(`${this.baseUrl}/api/room/${sanitizedCode}/answer`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ answer }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || `Failed to submit answer: HTTP ${res.status}`);
    }
  }

  async waitForAnswer(code: string, abortSignal?: AbortSignal, maxWaitMs = 120000): Promise<string> {
    const sanitizedCode = code.replace(/\D/g, '');
    const startTime = Date.now();

    while (Date.now() - startTime < maxWaitMs) {
      if (abortSignal?.aborted) {
        throw new Error('Waiting aborted');
      }

      try {
        const res = await fetch(`${this.baseUrl}/api/room/${sanitizedCode}/poll?timeout=15`, {
          signal: abortSignal,
        });

        if (!res.ok) {
          if (res.status === 404) {
            throw new Error('Room expired or closed');
          }
          await new Promise((r) => setTimeout(r, 1000));
          continue;
        }

        const data = await res.json();
        if (data.answer) {
          return data.answer;
        }
        // If data.waiting is true, continue to next poll
      } catch (e: unknown) {
        if (abortSignal?.aborted || (e instanceof Error && e.name === 'AbortError')) {
          throw new Error('Waiting aborted');
        }
        await new Promise((r) => setTimeout(r, 1500));
      }
    }

    throw new Error('Timed out waiting for peer to join');
  }

  async reconnect(
    sessionId: string,
    role: 'host' | 'joiner',
    token?: string
  ): Promise<{ hasOffer?: boolean; offer?: string; hasAnswer?: boolean; answer?: string }> {
    try {
      const body: Record<string, string> = { sessionId, role };
      if (role === 'host' && token) body.offer = token;
      if (role === 'joiner' && token) body.answer = token;

      const res = await fetch(`${this.baseUrl}/api/reconnect`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (res.ok) {
        return res.json();
      }
    } catch {}
    return {};
  }
}

