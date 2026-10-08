# RDR Transit: Systems Architecture & Technical Specification

> **Version:** 1.0.0  
> **Target Audience:** Autonomous Agents, Core Engineers, Multiplatform Contributors  
> **Status:** Canonical Living Specification

### Documentation Suite Navigation
* 📘 [**System Overview & Protocols** (`docs/SYSTEM_DOCUMENTATION.md`)](file:///home/victor/antigravity/RDR-transit/docs/SYSTEM_DOCUMENTATION.md): Network topology, wire protocol, safety invariants.
* 💻 [**Source Code Reference** (`docs/SOURCE_CODE_REFERENCE.md`)](file:///home/victor/antigravity/RDR-transit/docs/SOURCE_CODE_REFERENCE.md): Detailed module-by-module walkthrough of Python code in `src/rdr_transit/`.
* 🎨 [**UI/UX Specification & Guide** (`docs/UI_UX_REFERENCE.md`)](file:///home/victor/antigravity/RDR-transit/docs/UI_UX_REFERENCE.md): Terminal (TUI), Desktop GUI, and Mobile interface engineering guides.
* 📱 [**Mobile & Multiplatform Reference** (`docs/MOBILE_FLUTTER_REFERENCE.md`)](file:///home/victor/antigravity/RDR-transit/docs/MOBILE_FLUTTER_REFERENCE.md): Flutter architecture, Dart protocol sockets, Android and Apple iOS/macOS configs.

---

## 1. Executive Summary & Core Tenets

**RDR Transit** is a high-performance, OS-agnostic peer-to-peer file transfer system engineered for direct local area network (LAN) communication between heterogeneous devices (Linux, Windows, macOS, Android, and iOS).

### Fundamental Architectural Tenets
1. **Zero-Configuration Discovery**: Devices announce presence and discover peers autonomously on the local subnet without external relays, cloud signaling, or user-configured IP addresses.
2. **Wire Compatibility**: Strict adherence to the open LAN-Share binary wire protocol (`<ib` 5-byte header framing) allowing zero-friction interoperability with third-party LAN-Share tools.
3. **Cross-Platform Path Invariance & Safety**: Path sanitization protects against path traversal attacks, enforces forbidden character escaping for Windows (`: * ? " < > |`), skips symbolic link traps, and standardizes POSIX/NT directory representations.
4. **Multi-Frontend Coherence**: Shared protocol and transfer engines power four distinct presentation layers:
   - **TUI**: Keyboard-driven `nmtui`-inspired terminal user interface (Textual).
   - **CLI**: Headless, scriptable automation interface (Rich).
   - **GUI**: Lightweight, zero-dependency desktop interface (Tkinter/ttk).
   - **Mobile**: Unified cross-platform mobile client for Android and Apple platforms (Flutter/Dart).

---

## 2. Network Topology & Protocol Specifications

### 2.1 Layer 1: UDP Peer Discovery (Port 56780)

Peer discovery operates via UDP broadcast over port `56780`.

#### Network Socket Characteristics
- **Broadcast Target**: `255.255.255.255:56780` and subnet-directed broadcast addresses.
- **Socket Flags**: `SO_BROADCAST`, `SO_REUSEADDR`, and (where supported on POSIX) `SO_REUSEPORT`.
- **Broadcast Interval**: Default 4.0 seconds per announcement beacon.
- **Peer Expiration Timeout**: Peers not heard from within 15–20 seconds are marked stale/inactive.

#### Discovery Beacon JSON Payload
```json
{
  "id": "{550e8400-e29b-41d4-a716-446655440000}",
  "name": "workstation-alpha",
  "os": "Linux",
  "port": 56780
}
```

#### Fields:
- `id`: Unique GUID/UUID identifying the network node across IP reassignments.
- `name`: Human-readable device identifier (hostname or user-configured alias).
- `os`: Operating system string (`Linux`, `Windows`, `Darwin`/`macOS`, `Android`, `iOS`).
- `port`: Announcement port (default `56780`). Transfer listening port defaults to `17116`.

---

### 2.2 Layer 2: TCP Binary Transfer Protocol (Port 17116)

File and snippet transmission utilizes a persistent streaming TCP socket on port `17116`.

#### Binary Packet Framing
Every packet consists of a fixed **5-byte header** followed by an optional payload:

```
0                   1                   2                   3                   4
0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                 Payload Length (Int32, Little-Endian)         | Pkt Type(Int8)|
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                             Payload Data ...                                  |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

- **Struct Format**: `<ib` (4-byte signed 32-bit integer in little-endian byte order, followed by 1-byte signed char).
- **Header Length**: Exactly `5 bytes`.

#### Packet Types (`PacketType` Enum)
| Value | Identifier | Direction | Description |
| :--- | :--- | :--- | :--- |
| `1` | `HEADER` | Sender $\rightarrow$ Receiver | Metadata preamble for an impending file |
| `2` | `DATA` | Sender $\rightarrow$ Receiver | Raw binary byte chunk (nominal size: 96 KB) |
| `3` | `FINISH` | Bidirectional | Signals end of file stream / Acknowledgment |
| `4` | `CANCEL` | Bidirectional | Immediately terminates active transfer |
| `5` | `PAUSE` | Bidirectional | Requests flow pause |
| `6` | `RESUME` | Bidirectional | Resumes paused stream |
| `7` | `SKIP` | Receiver $\rightarrow$ Sender | Signals identical file already exists on target |
| `8` | `QUERY` | Sender $\rightarrow$ Receiver | Queries existence of file hash/size prior to transmission |
| `9` | `QUERY_RESP` | Receiver $\rightarrow$ Sender | Response to pre-flight file query |
| `10` | `SNIPPET` | Sender $\rightarrow$ Receiver | Direct transmission of clipboard / text snippet |

#### Payload Formats

##### 1. `HEADER` (PacketType = 1)
UTF-8 JSON string payload:
```json
{
  "name": "archive.tar.gz",
  "folder": "backup/2026",
  "size": 104857600,
  "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
}
```
- `name`: Target file name.
- `folder`: Subdirectory hierarchy relative to the destination root (`""` for root).
- `size`: Expected byte length.
- `sha256`: Optional hex-encoded digest for verification upon receipt.

##### 2. `DATA` (PacketType = 2)
Raw binary chunk, default chunk size `98,304 bytes` (96 KB).

##### 3. `FINISH` (PacketType = 3)
Zero payload length (`payload_len = 0`).

##### 4. `SKIP` (PacketType = 7)
UTF-8 string payload indicating the skip reason (`"already_exists"`).

##### 5. `SNIPPET` (PacketType = 10)
UTF-8 JSON string payload:
```json
{
  "text": "https://example.com/share",
  "sender": "MacBook-Air"
}
```

---

## 3. Subsystem Architecture & Component Breakdown

```
+-----------------------------------------------------------------------------------+
|                                  USER INTERFACES                                  |
|   +-------------------+  +-------------------+  +-------------------+  +--------+ |
|   |  TUI (Textual)    |  |    CLI (Rich)     |  |   GUI (Tkinter)   |  | Flutter| |
|   +-------------------+  +-------------------+  +-------------------+  +--------+ |
+-----------------------------------------+-----------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                                CORE TRANSIT ENGINE                                |
|                                                                                   |
|   +--------------------------+                 +------------------------------+   |
|   |    DISCOVERY ENGINE      |                 |       TRANSFER ENGINE        |   |
|   | - UDP 56780 Broadcaster  |                 | - BatchSender (TCP 17116)    |   |
|   | - Background Listener    |                 | - ReceiverServer (TCP 17116) |   |
|   | - DiscoveredPeer State   |                 | - TransferStats Tracking     |   |
|   +--------------------------+                 +------------------------------+   |
|                                                                                   |
|   +--------------------------+  +-------------------+  +----------------------+   |
|   |      FILESYSTEM & OS     |  |      CONFIG       |  |       NETWORK        |   |
|   | - Path Sanitization      |  | - AppConfig       |  | - Broadcast Sockets  |   |
|   | - Filter Exclusions      |  | - Persistence     |  | - Primary IP Lookup  |   |
|   | - SHA-256 Checksums      |  | - Default Values  |  | - Socket Read Exact  |   |
|   +--------------------------+  +-------------------+  +----------------------+   |
+-----------------------------------------------------------------------------------+
```

### 3.1 Core Subsystems (Python: `src/rdr_transit/`)

#### 1. Discovery Subsystem (`src/rdr_transit/discovery.py`)
- **`DiscoveredPeer`**: Data model maintaining IP, hostname, OS badge, port, device ID, and `last_seen` timestamp. Provides `is_alive` liveness verification (15s threshold).
- **`send_beacon()`**: Unicast/broadcast beacon transmitter.
- **`discover_peers()`**: Synchronous discovery scanner for one-off CLI operations.
- **`PeerDiscoveryService`**: Continuous threaded service running a listener loop and periodic beacon transmitter with peer change callbacks.

#### 2. Transfer Subsystem (`src/rdr_transit/transfer/`)
- **`BatchSender` (`sender.py`)**: Multi-stream transmission orchestrator.
  - Supports configurable parallel TCP worker threads (`parallel_transfers`).
  - Pre-scans staged targets, computes total sizes, emits continuous `TransferStats` updates.
  - Automatically handles `SKIP` acknowledgments from receivers with matching file size and hash.
- **`ReceiverServer` (`receiver.py`)**: Multi-threaded TCP daemon.
  - Spawns client handling threads upon connection on port `17116`.
  - Enforces atomic file writing, safe directory creation, incremental sync detection, and checksum verification.
  - Dispatches callbacks for file start, chunk arrival, file completion, and text snippet reception.

#### 3. Filesystem Safety & Sanitization Subsystem (`src/rdr_transit/utils/filesystem.py`)
- **`sanitize_destination_path()`**:
  - Resolves target against base download directory; rejects path traversal (`../`) escaping the root.
  - Removes dangerous Windows characters (`:`, `*`, `?`, `"`, `<`, `>`, `|`) when operating across platforms.
  - Normalizes backslashes and slashes to native host delimiters.
- **`collect_target_files()`**:
  - Recursively crawls directories.
  - Automatically filters out virtual environments (`.venv`, `venv`), build caches (`__pycache__`, `.pytest_cache`), and version control metadata (`.git`).
  - Ignores broken symbolic links and circular directories.

#### 4. Settings & Persistence Subsystem (`src/rdr_transit/settings.py`)
- Manages persistent configuration in `~/.config/rdr-transit/config.json`.
- Holds device names, transfer ports, download directories, parallel worker counts, and beacon intervals.

---

### 3.2 Presentation Layers

#### 1. Terminal UI (TUI) (`src/rdr_transit/tui/`)
- Built on **Textual**.
- Responsive layout featuring an nmtui-inspired palette, live glowing beacons, staging lists, transfer meters, and keyboard shortcuts (`s` for Send, `r` for Receive, `d` for Discovery).

#### 2. Graphical UI (GUI) (`src/rdr_transit/gui/`)
- Built on Python standard **Tkinter & ttk**.
- Thread-safe event queue (`event_queue.get_nowait()`) processing network events without stalling the GUI loop.
- Tabbed interface: Send Files, Discovered Peers, Text Snippets, Activity Logs, and Preferences.

#### 3. Command Line Interface (CLI) (`src/rdr_transit/cli.py`)
- Commands:
  - `rdr-transit send <paths> [-t TARGET] [-j WORKERS]`
  - `rdr-transit receive [-d OUT_DIR] [-p PORT]`
  - `rdr-transit snippet "<text>" [-t TARGET]`
  - `rdr-transit discover [--timeout SECONDS]`
  - `rdr-transit gui`
  - `rdr-transit tui`
  - `rdr-transit config [--set KEY VALUE]`

---

### 3.3 Mobile & Multiplatform Layer (`apps/flutter_transit/`)

Built with **Flutter / Dart** to target Android, iOS, and desktop operating systems from a single codebase:
- **`lib/protocol/packets.dart`**: Complete binary packet encoder and decoder matching `<ib` framing.
- **`lib/services/discovery_service.dart`**: `RawDatagramSocket` binding on UDP `56780` with background beacons.
- **`lib/services/transfer_service.dart`**: TCP client/server streaming via `Socket` and `ServerSocket`.
- **Platform Permissions**:
  - **Android**: `CHANGE_WIFI_MULTICAST_STATE`, `INTERNET`, `WAKE_LOCK`, and media permissions in `AndroidManifest.xml`.
  - **iOS**: `NSLocalNetworkUsageDescription` in `Info.plist`, local Bonjour services, and `UIFileSharingEnabled` to expose received files to the Apple **Files** app.
  - **macOS**: Client and server socket sandbox entitlements in `Release.entitlements`.

---

## 4. Architectural Invariants & Critical Safety Rules

When reviewing, maintaining, or modifying this codebase, the following invariants **must never be broken**:

1. **Protocol Framing Invariant**:
   - The packet header is ALWAYS 5 bytes (`<ib` struct: 4-byte little-endian length + 1-byte packet type).
   - Never alter byte order or header offset; doing so breaks compatibility with LAN-Share and existing mobile nodes.
2. **Path Sanitization Invariant**:
   - Every file received over the network MUST pass through `sanitize_destination_path` before opening file descriptors.
   - Incoming relative folder paths must never resolve outside `download_dir`.
3. **Thread Safety & UI Event Loop Invariant**:
   - Network operations (TCP transfers, UDP discovery) must NEVER execute synchronously on UI threads (neither Textual main loop nor Tkinter event loop nor Flutter build phase).
   - In Tkinter: Always dispatch UI updates via `event_queue` or `root.after()`.
   - In Textual: Always use workers or `call_from_thread()`.
   - In Flutter: Use asynchronous futures, streams, or `ChangeNotifier`.
4. **Git & Build System Isolation Invariant**:
   - The Flutter `apps/flutter_transit/lib/` directory contains critical source code and must never be blocked by `.gitignore`.
   - Only root build outputs (`/build/`, `/lib/`) belong in `.gitignore`.

---

## 5. Development & Testing Methodology

### Test Suite Execution
```bash
# Run complete test suite (unit, integration, protocol, filesystem, GUI)
uv run pytest

# Run with verbose output
uv run pytest -v
```

### Component Coverage
- `tests/test_protocol.py`: Verifies packet header encoding, payload decoding, and struct sizes.
- `tests/test_filesystem.py`: Tests path sanitization, Windows character stripping, and directory exclusion filters.
- `tests/test_transfer.py`: Runs loopback TCP transfers verifying chunk streaming and checksum validations.
- `tests/test_gui.py`: Tests Tkinter headless initialization, event queues, and state handlers.
- `tests/test_tui.py`: Tests Textual TUI mounting and widget interactions.
