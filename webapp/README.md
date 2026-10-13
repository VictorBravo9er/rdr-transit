# RDR-Transit Web P2P (⚡)

> **100% Client-Side Local Network & P2P File Transfer Web App**  
> Built with **Vite + Tailwind CSS + WebRTC DataChannels + PWA Service Worker**. Zero backend server required.

---

## Highlights

- **100% Client-Side**: No backend, no server-side storage, no tracking. Can be hosted statically on GitHub Pages, Vercel, Netlify, or run locally.
- **Service Worker Precaching (Instant F5 / Offline Reload)**: All built assets (`index.html`, JS bundles, CSS, icons) are precached in the browser's Cache Storage via Workbox. Pressing refresh (F5) or reopening the app instantly serves from local cache without re-downloading identical files over the network. When a new version is pushed to hosting, the Service Worker automatically detects the revision in the background and updates the cache.
- **Local Wi-Fi Speed**: Connects directly via WebRTC DataChannels. When both devices are on the same local network, traffic is routed locally across the Wi-Fi router at maximum speed without passing through the internet.
- **Backpressure-Managed Streaming**: Streams gigabyte-sized files in 64 KB binary chunks with backpressure monitoring (`bufferedAmount`) so memory never overflows.
- **Serverless QR & Token Handshake**:
  - **Host** generates an encrypted connection invitation embedded into a QR code or copyable token.
  - **Joiner** points their phone/laptop camera to scan the QR code (or pastes the token) and generates an answer code.
  - Handshake completes in seconds.
- **File & Snippet Support**: Send multiple files, folders, or instant clipboard text snippets.

---

## Quick Start (Development)

```bash
cd webapp
pnpm install
pnpm dev
```

Vite will serve the app locally (typically at `http://localhost:5173` or your local IP address `http://192.168.x.x:5173`).

---

## Building for Production

```bash
cd webapp
pnpm build
```

The production output will be generated in `webapp/dist/`, which includes the pre-configured Service Worker (`dist/sw.js`) and precache manifest. It is completely static and ready to be deployed to any static host.
