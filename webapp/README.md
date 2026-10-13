# RDR-Transit Web P2P (⚡)

> **100% Client-Side Local Network & P2P File Transfer Web App**  
> Built with **Vite + Tailwind CSS + WebRTC DataChannels + PWA Service Worker**. Zero backend server required.

---

## Highlights

- **100% Direct LAN P2P**: File transfers, folders, and snippets stream directly over encrypted WebRTC DataChannels at full local Wi-Fi speeds. Zero file payload ever touches any server.
- **Instant 6-Digit PIN Matchmaking**:
  - **Host** clicks "Generate 6-Digit PIN" and shares an ephemeral 6-digit code (e.g. `482 910`).
  - **Joiner** enters the 6-digit code, which automatically completes the WebRTC SDP handshake via a serverless **Cloudflare Worker** matchmaker (`worker/`).
  - No copy-pasting long tokens or scanning screens required under normal network conditions.
- **Offline & Air-Gapped Fallback**:
  - Expandable offline drawers provide the traditional zero-network QR code generation, camera scanning, and manual SDP token exchange for air-gapped LANs.
- **Configurable Signaling Worker**:
  - Built-in status indicator and modal settings allow pointing to your own deployed Cloudflare Worker or local `wrangler dev` endpoint.
- **Service Worker Precaching (Instant F5 / Offline Reload)**: All built assets (`index.html`, JS bundles, CSS, icons) are precached in the browser's Cache Storage via Workbox. Pressing refresh (F5) or reopening the app instantly serves from local cache without re-downloading identical files over the network. When a new version is pushed to hosting, the Service Worker automatically detects the revision in the background and updates the cache.
- **Local Wi-Fi Speed**: Connects directly via WebRTC DataChannels. When both devices are on the same local network, traffic is routed locally across the Wi-Fi router at maximum speed without passing through the internet.
- **Backpressure-Managed Streaming**: Streams gigabyte-sized files in 64 KB binary chunks with backpressure monitoring (`bufferedAmount`) so memory never overflows.
- **Unified Transmissions Feed**: Live real-time ledger tracking all sent and received files with download links, along with sent and received text snippets.
- **Connection Persistence Across Page Refresh**: Active connections automatically persist across browser reloads (F5 / refreshes) via session storage, `BroadcastChannel`, and background reconnection signaling. Connections remain established unless an active peer tab or page is explicitly closed or disconnected.
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

---

## Deploying to GitHub Pages

The repository includes an automated GitHub Actions deployment workflow at [`.github/workflows/deploy-webapp.yml`](file:///.github/workflows/deploy-webapp.yml).

### 1. Enable GitHub Actions for Pages
1. Go to your repository on GitHub: `https://github.com/VictorBravo9er/rdr-transit/settings/pages`.
2. Under **Build and deployment** > **Source**, select **GitHub Actions**.

### 2. Trigger Deployment
- **Automatic**: Any push to `main` modifying files under `webapp/` will automatically build and deploy the webapp.
- **Manual**: Navigate to **Actions** > **Deploy Webapp to GitHub Pages** > **Run workflow**.

Once deployed, the web application will be live at:
`https://victorbravo9er.github.io/rdr-transit/`

