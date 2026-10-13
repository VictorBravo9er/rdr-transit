import {
  BUFFERED_AMOUNT_HIGH_THRESHOLD,
  BUFFERED_AMOUNT_LOW_THRESHOLD,
  CHUNK_SIZE,
  type ControlMessage,
  type FileFinishMessage,
  type FileHeaderMessage,
  type SnippetMessage,
} from './protocol';
import { compressSdp, decompressSdp } from './sdp_compress';

export type ConnectionStatus = 'disconnected' | 'connecting' | 'connected' | 'reconnecting' | 'failed';

export interface ReceivedFile {
  id: string;
  name: string;
  size: number;
  blob: Blob;
  mimeType: string;
  receivedAt: Date;
}

export interface ProgressInfo {
  fileId: string;
  name: string;
  bytesTransferred: number;
  totalBytes: number;
  percentage: number;
  speed: number; // bytes per second
}

export interface WebRTCEvents {
  onStatusChange: (status: ConnectionStatus, message?: string) => void;
  onSendProgress: (progress: ProgressInfo) => void;
  onReceiveProgress: (progress: ProgressInfo) => void;
  onFileReceived: (file: ReceivedFile) => void;
  onSnippetReceived: (snippet: string) => void;
  onSessionSync?: (sessionId: string) => void;
  onError: (error: string) => void;
}

export class WebRTCManager {
  private pc: RTCPeerConnection | null = null;
  private dataChannel: RTCDataChannel | null = null;
  private events: WebRTCEvents;

  // Session & persistence state
  private sessionId: string | null = null;
  private role: 'host' | 'joiner' | null = null;
  private isReconnecting = false;
  private reconnectTimeoutId: ReturnType<typeof setTimeout> | null = null;

  // Receiving state
  private currentIncomingFile: FileHeaderMessage | null = null;
  private incomingChunks: ArrayBuffer[] = [];
  private incomingBytes = 0;
  private incomingStartTime = 0;
  private incomingLastSpeedCalcTime = 0;
  private incomingLastSpeedCalcBytes = 0;
  private incomingSpeed = 0;

  // Sending state
  private isSending = false;
  private abortSend = false;

  constructor(events: WebRTCEvents) {
    this.events = events;
  }

  private createPeerConnection(): RTCPeerConnection {
    // Quietly cleanup previous connection without triggering 'disconnected' event
    if (this.dataChannel) {
      try {
        this.dataChannel.close();
      } catch {}
      this.dataChannel = null;
    }
    if (this.pc) {
      try {
        this.pc.close();
      } catch {}
      this.pc = null;
    }

    const config: RTCConfiguration = {
      iceServers: [
        { urls: 'stun:stun.l.google.com:19302' },
        { urls: 'stun:stun1.l.google.com:19302' },
      ],
      iceCandidatePoolSize: 2,
    };

    const pc = new RTCPeerConnection(config);

    pc.oniceconnectionstatechange = () => {
      if (pc.iceConnectionState === 'connected' || pc.iceConnectionState === 'completed') {
        if (this.reconnectTimeoutId) {
          clearTimeout(this.reconnectTimeoutId);
          this.reconnectTimeoutId = null;
        }
        this.isReconnecting = false;
        this.events.onStatusChange('connected', 'Direct Peer-to-Peer Link Active');
      } else if (pc.iceConnectionState === 'failed') {
        if (this.sessionId && !this.isReconnecting) {
          this.startReconnecting('Direct link interrupted. Reconnecting to peer...');
        } else if (!this.sessionId) {
          this.events.onStatusChange('failed', 'Direct P2P connection failed');
        }
      } else if (pc.iceConnectionState === 'disconnected') {
        if (this.sessionId && !this.isReconnecting) {
          this.startReconnecting('Peer temporarily disconnected. Waiting for reconnect...');
        } else if (!this.sessionId) {
          this.events.onStatusChange('disconnected', 'Peer disconnected');
        }
      }
    };

    this.pc = pc;
    return pc;
  }

  private setupDataChannel(channel: RTCDataChannel) {
    channel.binaryType = 'arraybuffer';
    channel.bufferedAmountLowThreshold = BUFFERED_AMOUNT_LOW_THRESHOLD;

    channel.onopen = () => {
      if (this.reconnectTimeoutId) {
        clearTimeout(this.reconnectTimeoutId);
        this.reconnectTimeoutId = null;
      }
      this.isReconnecting = false;
      this.events.onStatusChange('connected', 'DataChannel Ready for File Transmission');

      // If host has an established sessionId, sync it with joiner
      if (this.role === 'host' && this.sessionId) {
        this.sendSessionSync(this.sessionId);
      }
    };

    channel.onclose = () => {
      if (this.sessionId && !this.isReconnecting) {
        this.startReconnecting('Peer disconnected. Waiting for peer...');
      } else if (!this.sessionId) {
        this.events.onStatusChange('disconnected', 'DataChannel closed');
      }
    };

    channel.onerror = (err) => {
      console.error('DataChannel error:', err);
      this.events.onError('DataChannel encountered an error');
    };

    channel.onmessage = (event) => {
      this.handleIncomingMessage(event.data);
    };

    this.dataChannel = channel;
  }

  /**
   * Generates an Offer token to share with the peer.
   */
  async createOfferToken(): Promise<string> {
    this.role = 'host';
    const pc = this.createPeerConnection();
    this.events.onStatusChange('connecting', 'Gathering network addresses...');

    const channel = pc.createDataChannel('rdr-transit-dc', { ordered: true });
    this.setupDataChannel(channel);

    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);

    await this.waitForIceGathering(pc);

    if (!pc.localDescription) {
      throw new Error('Failed to generate local offer description');
    }

    return compressSdp(pc.localDescription.sdp);
  }

  /**
   * Accepts an Offer token and creates an Answer token.
   */
  async acceptOfferAndCreateAnswerToken(offerToken: string): Promise<string> {
    this.role = 'joiner';
    const pc = this.createPeerConnection();
    this.events.onStatusChange('connecting', 'Connecting to host offer...');

    pc.ondatachannel = (event) => {
      this.setupDataChannel(event.channel);
    };

    const sdp = decompressSdp(offerToken);
    await pc.setRemoteDescription({
      type: 'offer',
      sdp,
    });

    const answer = await pc.createAnswer();
    await pc.setLocalDescription(answer);

    await this.waitForIceGathering(pc);

    if (!pc.localDescription) {
      throw new Error('Failed to generate local answer description');
    }

    return compressSdp(pc.localDescription.sdp);
  }

  /**
   * Finalizes handshake by accepting Answer token.
   */
  async acceptAnswerToken(answerToken: string): Promise<void> {
    if (!this.pc) {
      throw new Error('No active peer connection to accept answer');
    }

    const sdp = decompressSdp(answerToken);
    await this.pc.setRemoteDescription({
      type: 'answer',
      sdp,
    });
    this.events.onStatusChange('connecting', 'Establishing direct connection...');
  }

  private waitForIceGathering(pc: RTCPeerConnection): Promise<void> {
    return new Promise((resolve) => {
      if (pc.iceGatheringState === 'complete') {
        resolve();
        return;
      }

      const checkState = () => {
        if (pc.iceGatheringState === 'complete') {
          pc.removeEventListener('icegatheringstatechange', checkState);
          resolve();
        }
      };

      pc.addEventListener('icegatheringstatechange', checkState);

      // Fallback timeout in case some candidates delay
      setTimeout(() => {
        pc.removeEventListener('icegatheringstatechange', checkState);
        resolve();
      }, 1500);
    });
  }

  /**
   * Enters the reconnecting state with a grace timer.
   */
  startReconnecting(message = 'Connection lost. Reconnecting to peer...'): void {
    if (this.isReconnecting) return;
    this.isReconnecting = true;
    this.events.onStatusChange('reconnecting', message);

    if (this.reconnectTimeoutId) {
      clearTimeout(this.reconnectTimeoutId);
    }

    // Grace period before completely marking as disconnected (25 seconds)
    this.reconnectTimeoutId = setTimeout(() => {
      if (this.isReconnecting) {
        this.isReconnecting = false;
        this.sessionId = null;
        this.close();
      }
    }, 25000);
  }

  /**
   * Send session synchronization message over DataChannel.
   */
  sendSessionSync(sessionId: string): void {
    if (this.dataChannel && this.dataChannel.readyState === 'open') {
      try {
        this.dataChannel.send(JSON.stringify({ type: 'session_sync', sessionId }));
      } catch {}
    }
  }

  /**
   * Send explicit disconnect message to peer.
   */
  sendDisconnect(): void {
    if (this.dataChannel && this.dataChannel.readyState === 'open') {
      try {
        this.dataChannel.send(JSON.stringify({ type: 'disconnect' }));
      } catch {}
    }
  }

  /**
   * Send a text / clipboard snippet to connected peer.
   */
  sendSnippet(text: string): boolean {
    if (!this.dataChannel || this.dataChannel.readyState !== 'open') {
      this.events.onError('Cannot send snippet: peer not connected');
      return false;
    }

    const msg: SnippetMessage = {
      type: 'snippet',
      text,
      timestamp: Date.now(),
    };

    this.dataChannel.send(JSON.stringify(msg));
    return true;
  }

  /**
   * Streams a file to the connected peer with backpressure control.
   */
  async sendFile(file: File): Promise<boolean> {
    if (!this.dataChannel || this.dataChannel.readyState !== 'open') {
      this.events.onError('Cannot send file: peer not connected');
      return false;
    }

    if (this.isSending) {
      this.events.onError('A file is already being transferred');
      return false;
    }

    this.isSending = true;
    this.abortSend = false;

    const fileId = `${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
    const totalChunks = Math.ceil(file.size / CHUNK_SIZE);

    // 1. Send Header
    const header: FileHeaderMessage = {
      type: 'header',
      fileId,
      name: file.name,
      size: file.size,
      mimeType: file.type || 'application/octet-stream',
      totalChunks,
    };

    this.dataChannel.send(JSON.stringify(header));

    // 2. Stream Binary Chunks with backpressure handling
    let offset = 0;
    const startTime = performance.now();
    let lastCalcTime = startTime;
    let lastCalcBytes = 0;
    let currentSpeed = 0;

    try {
      while (offset < file.size && !this.abortSend) {
        // Backpressure wait
        if (this.dataChannel.bufferedAmount > BUFFERED_AMOUNT_HIGH_THRESHOLD) {
          await this.waitForBufferLow();
        }

        const chunkSlice = file.slice(offset, offset + CHUNK_SIZE);
        const chunkBuffer = await chunkSlice.arrayBuffer();

        this.dataChannel.send(chunkBuffer);
        offset += chunkBuffer.byteLength;

        // Speed calculation
        const now = performance.now();
        if (now - lastCalcTime > 250) {
          const deltaSec = (now - lastCalcTime) / 1000;
          const deltaBytes = offset - lastCalcBytes;
          currentSpeed = deltaBytes / deltaSec;
          lastCalcTime = now;
          lastCalcBytes = offset;
        }

        this.events.onSendProgress({
          fileId,
          name: file.name,
          bytesTransferred: offset,
          totalBytes: file.size,
          percentage: file.size > 0 ? (offset / file.size) * 100 : 100,
          speed: currentSpeed,
        });
      }

      if (this.abortSend) {
        this.dataChannel.send(JSON.stringify({ type: 'cancel', fileId }));
        this.events.onError('Transfer was canceled');
        return false;
      }

      // 3. Send Finish
      const finishMsg: FileFinishMessage = {
        type: 'finish',
        fileId,
      };
      this.dataChannel.send(JSON.stringify(finishMsg));

      return true;
    } catch (err) {
      console.error('File send error:', err);
      this.events.onError(`Error sending file: ${err}`);
      return false;
    } finally {
      this.isSending = false;
    }
  }

  cancelSend(): void {
    if (this.isSending) {
      this.abortSend = true;
    }
  }

  private waitForBufferLow(): Promise<void> {
    return new Promise((resolve) => {
      if (!this.dataChannel || this.dataChannel.bufferedAmount <= BUFFERED_AMOUNT_LOW_THRESHOLD) {
        resolve();
        return;
      }

      const onLow = () => {
        if (this.dataChannel) {
          this.dataChannel.removeEventListener('bufferedamountlow', onLow);
        }
        resolve();
      };

      this.dataChannel.addEventListener('bufferedamountlow', onLow);
    });
  }

  private handleIncomingMessage(data: string | ArrayBuffer) {
    if (typeof data === 'string') {
      try {
        const msg: ControlMessage = JSON.parse(data);
        if (msg.type === 'header') {
          this.currentIncomingFile = msg;
          this.incomingChunks = [];
          this.incomingBytes = 0;
          this.incomingStartTime = performance.now();
          this.incomingLastSpeedCalcTime = this.incomingStartTime;
          this.incomingLastSpeedCalcBytes = 0;
          this.incomingSpeed = 0;

          this.events.onReceiveProgress({
            fileId: msg.fileId,
            name: msg.name,
            bytesTransferred: 0,
            totalBytes: msg.size,
            percentage: 0,
            speed: 0,
          });
        } else if (msg.type === 'finish') {
          if (this.currentIncomingFile && this.currentIncomingFile.fileId === msg.fileId) {
            const blob = new Blob(this.incomingChunks, {
              type: this.currentIncomingFile.mimeType,
            });

            const receivedFile: ReceivedFile = {
              id: this.currentIncomingFile.fileId,
              name: this.currentIncomingFile.name,
              size: this.currentIncomingFile.size,
              blob,
              mimeType: this.currentIncomingFile.mimeType,
              receivedAt: new Date(),
            };

            this.events.onFileReceived(receivedFile);

            // Reset
            this.currentIncomingFile = null;
            this.incomingChunks = [];
            this.incomingBytes = 0;
          }
        } else if (msg.type === 'snippet') {
          this.events.onSnippetReceived(msg.text);
        } else if (msg.type === 'session_sync') {
          this.sessionId = msg.sessionId;
          if (this.events.onSessionSync) {
            this.events.onSessionSync(msg.sessionId);
          }
        } else if (msg.type === 'disconnect') {
          if (this.reconnectTimeoutId) {
            clearTimeout(this.reconnectTimeoutId);
            this.reconnectTimeoutId = null;
          }
          this.isReconnecting = false;
          this.sessionId = null;
          this.role = null;
          this.close(true);
        } else if (msg.type === 'cancel') {
          this.currentIncomingFile = null;
          this.incomingChunks = [];
          this.incomingBytes = 0;
          this.events.onError('Sender canceled the file transfer');
        }
      } catch (e) {
        console.error('Failed to parse incoming control message:', e);
      }
    } else if (data instanceof ArrayBuffer) {
      if (!this.currentIncomingFile) return;

      this.incomingChunks.push(data);
      this.incomingBytes += data.byteLength;

      const now = performance.now();
      if (now - this.incomingLastSpeedCalcTime > 250) {
        const deltaSec = (now - this.incomingLastSpeedCalcTime) / 1000;
        const deltaBytes = this.incomingBytes - this.incomingLastSpeedCalcBytes;
        this.incomingSpeed = deltaBytes / deltaSec;
        this.incomingLastSpeedCalcTime = now;
        this.incomingLastSpeedCalcBytes = this.incomingBytes;
      }

      this.events.onReceiveProgress({
        fileId: this.currentIncomingFile.fileId,
        name: this.currentIncomingFile.name,
        bytesTransferred: this.incomingBytes,
        totalBytes: this.currentIncomingFile.size,
        percentage:
          this.currentIncomingFile.size > 0
            ? (this.incomingBytes / this.currentIncomingFile.size) * 100
            : 100,
        speed: this.incomingSpeed,
      });
    }
  }

  close(clearSession = true): void {
    if (this.reconnectTimeoutId) {
      clearTimeout(this.reconnectTimeoutId);
      this.reconnectTimeoutId = null;
    }
    this.isReconnecting = false;
    if (clearSession) {
      this.sessionId = null;
      this.role = null;
    }
    if (this.dataChannel) {
      try {
        this.dataChannel.close();
      } catch {}
      this.dataChannel = null;
    }
    if (this.pc) {
      try {
        this.pc.close();
      } catch {}
      this.pc = null;
    }
    this.events.onStatusChange('disconnected');
  }

  isConnected(): boolean {
    return this.dataChannel !== null && this.dataChannel.readyState === 'open';
  }

  isTransferring(): boolean {
    return this.isSending || this.currentIncomingFile !== null;
  }

  getSessionId(): string | null {
    return this.sessionId;
  }

  setSessionId(id: string | null): void {
    this.sessionId = id;
  }

  getRole(): 'host' | 'joiner' | null {
    return this.role;
  }

  setRole(role: 'host' | 'joiner' | null): void {
    this.role = role;
  }

  isCurrentlyReconnecting(): boolean {
    return this.isReconnecting;
  }
}
