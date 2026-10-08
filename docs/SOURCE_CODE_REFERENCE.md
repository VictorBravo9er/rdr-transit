# RDR-Transit: Source Code Architecture & Technical Reference

> **Companion Document to [`docs/SYSTEM_DOCUMENTATION.md`](file:///home/victor/antigravity/RDR-transit/docs/SYSTEM_DOCUMENTATION.md)**  
> **Target Audience:** Autonomous Agents, Core Developers, System Engineers  
> **Coverage:** Full walkthrough of `src/rdr_transit/` modules, algorithms, concurrency models, and design patterns.

---

## 1. Directory & Module Map

```
src/rdr_transit/
├── __init__.py           # Package version (__version__) and root exports
├── __main__.py           # CLI invocation via `python -m rdr_transit`
├── config.py             # Global constants, networking defaults, buffer sizes
├── protocol.py           # LAN-Share wire framing (<ib struct) and packet serialization
├── discovery.py          # UDP 56780 peer beaconing, socket reuse, and discovery service
├── settings.py           # User configuration persistence (~/.config/rdr-transit/config.json)
├── cli.py                # Command-line interface with Rich formatting and command dispatch
├── utils/
│   ├── __init__.py
│   ├── filesystem.py     # Path traversal protection, Windows char escaping, crawler
│   └── network.py        # Primary IP resolution and cross-platform UDP broadcast sockets
├── transfer/
│   ├── __init__.py
│   ├── sender.py         # Multi-threaded TCP sender (BatchSender) & snippet sender
│   └── receiver.py       # Multi-client TCP receiver daemon (ReceiverServer)
├── tui/
│   ├── __init__.py
│   ├── app.py            # Textual nmtui-inspired terminal application
│   ├── screens.py        # Modal dialogs, help screens, file selector widgets
│   └── styles.tcss       # Textual CSS design specifications
└── gui/
    ├── __init__.py       # GUI package export
    └── app.py            # Tkinter/ttk desktop application with thread-safe queue
```

---

## 2. Core Protocol & Serialization (`src/rdr_transit/protocol.py`)

### 2.1 Struct Framing
The wire framing adheres to `<ib`:
```python
PACKET_HEADER_STRUCT = struct.Struct("<ib")
PACKET_HEADER_SIZE = PACKET_HEADER_STRUCT.size  # 5 bytes
```
- `<`: Little-endian byte order.
- `i`: 32-bit signed integer representing the payload byte length.
- `b`: 8-bit signed integer representing the `PacketType`.

### 2.2 Packet Type Enumeration
```python
class PacketType(IntEnum):
    HEADER = 1       # JSON file metadata preamble
    DATA = 2         # Binary file chunk
    FINISH = 3       # End of file / receiver acknowledgment
    CANCEL = 4       # Abort transfer
    PAUSE = 5        # Suspend transmission
    RESUME = 6       # Resume transmission
    SKIP = 7         # File already exists on receiver (incremental sync)
    QUERY = 8        # Pre-flight query
    QUERY_RESP = 9   # Pre-flight query response
    SNIPPET = 10     # Clipboard / text transfer
```

### 2.3 Key Functions
- `create_header_packet(name, folder, size, sha256="") -> bytes`:
  Packs JSON `{"name": str, "folder": str, "size": int, "sha256": str}` with header `<ib`.
- `create_data_packet(chunk: bytes) -> bytes`:
  Packs raw binary chunk up to `DEFAULT_CHUNK_SIZE` (96 KB).
- `create_finish_packet() -> bytes`: Zero-length payload packet with type `3`.
- `create_skip_packet(reason="already_exists") -> bytes`: Packed skip signal with reason payload.
- `create_snippet_packet(text: str, sender_name="") -> bytes`: Packs JSON `{"text": text, "sender": sender_name}` with type `10`.
- `read_exact(sock, length: int) -> bytes`:
  Loops `sock.recv()` until exactly `length` bytes are accumulated or raises `ConnectionError`. Ensures packet headers are never partially parsed.
- `read_packet(sock) -> Tuple[PacketType, bytes]`:
  Reads 5-byte header via `read_exact`, unpacks `length` and `type`, then reads `length` payload bytes via `read_exact`.

---

## 3. Network Discovery Subsystem (`src/rdr_transit/discovery.py`)

### 3.1 Data Structures
```python
@dataclass
class DiscoveredPeer:
    ip: str
    name: str
    os: str
    port: int = DEFAULT_TRANSFER_PORT
    device_id: str = ""
    last_seen: float = field(default_factory=time.time)
```
- `is_alive`: Returns `True` if seen within the last 15.0 seconds.
- `os_badge`: Maps OS string to unified badges (`Windows`, `macOS`, `Linux`, `Android`).

### 3.2 Services & Concurrency
- `send_beacon(target_ip, broadcast_port, device_id, name, os_name)`:
  Constructs a JSON announcement payload and broadcasts via UDP `56780`. If a specific IP is targeted, it sends both unicast and broadcast to `255.255.255.255`.
- `discover_peers(timeout=2.0) -> List[DiscoveredPeer]`:
  One-shot synchronous scanner: sends a beacon, listens with `0.3s` socket timeouts, and returns deduplicated peers.
- `PeerDiscoveryService`:
  Persistent background discovery engine:
  - Spawns `_listener_thread`: Non-blocking UDP recv loop updating internal peer table.
  - Spawns `_beacon_thread`: Periodic heartbeat broadcaster (every 4.0s).
  - Fires `on_peer_updated` callbacks to notify UI layers asynchronously.

---

## 4. Transfer Engine Subsystem (`src/rdr_transit/transfer/`)

### 4.1 Sender Engine (`src/rdr_transit/transfer/sender.py`)
- **`TransferStats`**: Tracks total files, completed, skipped, failed, total bytes, transferred bytes, and computes `speed_mb_per_sec` dynamically.
- **`BatchSender`**:
  - Pre-computation: Resolves file lists via `collect_target_files`, tallying byte totals.
  - Concurrency: Employs `concurrent.futures.ThreadPoolExecutor(max_workers=parallel_transfers)` to stream multiple files in parallel over independent TCP connections.
  - Per-File Flow:
    1. Connects to `(target_ip, target_port)` with timeout.
    2. Sends `HEADER` packet containing filename, relative folder, byte size, and optional SHA-256.
    3. Listens for initial receiver response with non-blocking peek:
       - If `SKIP` received: Marks file skipped without transmitting payload.
    4. Streams binary data in 96 KB chunks (`create_data_packet`).
    5. Sends `FINISH` packet.
    6. Awaits receiver `FINISH` ACK packet.
    7. Closes socket and records completion in `TransferStats`.
  - Cancellation: `cancel()` sets `is_cancelled = True`, terminating worker loops gracefully.

### 4.2 Receiver Engine (`src/rdr_transit/transfer/receiver.py`)
- **`ReceiverServer`**:
  - Binds server socket on `0.0.0.0:17116` with `SO_REUSEADDR`.
  - Spawns worker thread per incoming client connection (`_handle_client`).
  - Handling Logic:
    1. Reads 5-byte header.
    2. If `PacketType.SNIPPET`:
       - Decodes JSON, appends to `received_snippets.txt`, triggers `on_snippet_received`.
    3. If `PacketType.HEADER`:
       - Sanitizes path via `sanitize_destination_path(download_dir, folder, name)`.
       - Incremental Sync Check: If file exists with identical size and hash, responds with `SKIP` packet and aborts payload reception.
       - Streams incoming `DATA` chunks directly to disk (`.part` temporary file).
       - Validates SHA-256 digest on the fly if enabled.
       - Upon receiving `FINISH`, renames `.part` file to final destination and sends back `FINISH` ACK.

---

## 5. Filesystem Safety & Path Sanitization (`src/rdr_transit/utils/filesystem.py`)

### 5.1 Security Guardrails
```python
def sanitize_destination_path(base_dir: Path, relative_folder: str, filename: str) -> Path:
```
1. **Directory Traversal Defense**:
   - Resolves canonical destination path using `Path.resolve()`.
   - Asserts `dest_path.is_relative_to(base_dir.resolve())`. Any traversal attempt (`../`) raises `ValueError`.
2. **Forbidden Character Sanitization**:
   - Windows reserved characters (`:`, `*`, `?`, `"`, `<`, `>`, `|`) are replaced with underscores (`_`).
   - Null bytes (`\0`) are stripped.
3. **Leading / Trailing Punctuation**:
   - Strips leading dots, slashes, and whitespace from filename and folder segments.

### 5.2 Directory Crawling & Exclusions
- `collect_target_files(paths, exclude_patterns=DEFAULT_EXCLUDED_DIRS)`:
  - Traverses directory trees while skipping symlinks (to avoid recursion loops and symlink attacks).
  - Skips default exclusion folders: `.venv`, `venv`, `__pycache__`, `.pytest_cache`, `.git`, `node_modules`, `.idea`, `.vscode`.
  - Computes relative paths so sender folder hierarchy is preserved on the receiver.

---

## 6. Network Utilities (`src/rdr_transit/utils/network.py`)

- `get_primary_ip() -> str`:
  Connects a dummy UDP socket to `8.8.8.8:80` (no packets sent) to interrogate kernel routing tables for the outbound network interface IP.
- `create_udp_broadcast_socket(port, reuse=True) -> socket.socket`:
  Creates UDP socket with `SO_BROADCAST`, `SO_REUSEADDR`, and platform-guarded `SO_REUSEPORT` (Linux/macOS) for multi-process discovery listeners.

---

## 7. Presentation Subsystems

### 7.1 Textual Terminal UI (`src/rdr_transit/tui/app.py`)
- Employs Textual's reactive framework with custom components:
  - `HeaderBar`: Shows local IP, receiver status, and device name.
  - `PeerTableView`: Interactive datatable listing active network peers.
  - `StagingListView`: Real-time queue of files staged for transmission.
  - `DualMeter`: Dual progress meters for current file and total batch progress.
- Asynchronous Workers:
  - Non-blocking peer scanning worker (`@work(exclusive=True)`).
  - Continuous discovery service runner.
  - Background batch sender worker emitting progress events back to main thread.

### 7.2 Desktop GUI (`src/rdr_transit/gui/app.py`)
- Standard library `tkinter` + `ttk` implementation:
  - **Thread-Safe Architecture**: Background threads (`PeerDiscoveryService`, `BatchSender`, `ReceiverServer`) post events to `self.event_queue`. The main GUI thread processes the queue via `root.after(100, self._process_event_queue)`.
  - **Tab Views**:
    1. *Send Files*: Peer combobox, direct IP entry, file/folder picker, live progress bar, speed meter.
    2. *Discovered Peers*: Treeview with OS icons, IP, port, last seen status, quick action buttons.
    3. *Text Snippets*: Multiline text entry, clipboard paste, direct transmission.
    4. *Activity & Logs*: Scrollable terminal log with "Open Downloads Folder" action.
    5. *Settings*: Download directory picker, port inputs, parallel stream spinbox.

### 7.3 CLI Entrypoint (`src/rdr_transit/cli.py`)
- Configured using standard library `argparse` with subcommands:
  - `send`, `receive`, `snippet` (alias: `clip`), `discover`, `config`, `gui`, `tui`.
- Leverages `rich.progress` with multi-column progress tracking:
  - `SpinnerColumn`, `TextColumn`, `BarColumn`, `TaskProgressColumn`, `DownloadColumn`, `TransferSpeedColumn`, `TimeRemainingColumn`.
- Outputs clean ASCII/Unicode status tables on conclusion of batch transfers.
