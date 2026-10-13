/**
 * Wire protocol types and constants for WebRTC DataChannel streaming.
 */

export const CHUNK_SIZE = 64 * 1024; // 64 KB chunks
export const BUFFERED_AMOUNT_HIGH_THRESHOLD = 1024 * 1024; // 1 MB backpressure limit
export const BUFFERED_AMOUNT_LOW_THRESHOLD = 256 * 1024; // 256 KB resume threshold

export type MessageType = 'header' | 'finish' | 'snippet' | 'cancel' | 'ping' | 'pong' | 'session_sync' | 'disconnect';

export interface FileHeaderMessage {
  type: 'header';
  fileId: string;
  name: string;
  size: number;
  mimeType: string;
  totalChunks: number;
}

export interface FileFinishMessage {
  type: 'finish';
  fileId: string;
}

export interface SnippetMessage {
  type: 'snippet';
  text: string;
  timestamp: number;
}

export interface CancelMessage {
  type: 'cancel';
  fileId: string;
}

export interface SessionSyncMessage {
  type: 'session_sync';
  sessionId: string;
}

export interface DisconnectMessage {
  type: 'disconnect';
}

export type ControlMessage =
  | FileHeaderMessage
  | FileFinishMessage
  | SnippetMessage
  | CancelMessage
  | SessionSyncMessage
  | DisconnectMessage;

export function formatBytes(bytes: number, decimals = 2): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const dm = decimals < 0 ? 0 : decimals;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(dm))} ${sizes[i]}`;
}

export function formatSpeed(bytesPerSec: number): string {
  return `${formatBytes(bytesPerSec)}/s`;
}
