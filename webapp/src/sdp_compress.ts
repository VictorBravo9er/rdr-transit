import { deflate, inflate } from 'pako';

/**
 * Compresses an SDP string into a URL-safe compact string.
 */
export function compressSdp(sdp: string): string {
  try {
    const jsonStr = JSON.stringify({ s: sdp });
    const deflated = deflate(jsonStr);
    let binary = '';
    const bytes = new Uint8Array(deflated);
    for (let i = 0; i < bytes.byteLength; i++) {
      binary += String.fromCharCode(bytes[i]);
    }
    const base64 = btoa(binary);
    // URL-safe replacement
    return base64.replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  } catch (err) {
    console.warn('Compression failed, falling back to base64:', err);
    return btoa(sdp);
  }
}

/**
 * Decompresses an SDP token string back to the original SDP string.
 */
export function decompressSdp(token: string): string {
  const trimmed = token.trim();
  try {
    // Restore base64 padding and URL characters
    let base64 = trimmed.replace(/-/g, '+').replace(/_/g, '/');
    while (base64.length % 4 !== 0) {
      base64 += '=';
    }
    const binary = atob(base64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) {
      bytes[i] = binary.charCodeAt(i);
    }
    const decompressedBytes = inflate(bytes);
    const inflated = new TextDecoder().decode(decompressedBytes);
    const parsed = JSON.parse(inflated);
    return parsed.s || inflated;
  } catch {
    // Fallback: try raw atob
    try {
      return atob(trimmed);
    } catch {
      return trimmed;
    }
  }
}
