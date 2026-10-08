# RDR Transit (⚡)

> **OS-Agnostic, High-Speed Peer-to-Peer File & Directory Transfer with a Responsive `nmtui`-Inspired Terminal Interface.**

[![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20Windows%20%7C%20macOS-blue.svg)](https://github.com)
[![Python](https://img.shields.io/badge/python-3.9+-brightgreen.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## Overview

**RDR Transit** is a lightweight, cross-platform file and folder transfer utility engineered for direct machine-to-machine transmission across local networks, Wi-Fi hotspots, and ad-hoc connections (such as connecting a Linux laptop and a Windows PC).

It combines:
- **Zero-Configuration Network Discovery**: Automatic peer beaconing over UDP `56780`.
- **Wire Compatibility**: Seamlessly interoperable with the open LAN-Share protocol (UDP `56780` discovery + TCP `17116` chunked transfer).
- **Responsive `nmtui`-Style TUI**: A beautiful, keyboard-driven full-screen Terminal User Interface built with [Textual](https://textual.textualize.io/) featuring rounded borders, glowing status beacons, stage-and-send queues, and live dual transfer meters.
- **Scriptable CLI**: Direct commands for scripted transfers, receiver listening daemons, and quick discoveries.
- **True OS Agnosticism**: Safe cross-platform path handling, symlink protection, automated `.venv` and `__pycache__` filtering, and Windows/Linux path sanitization.

---

## Installation

### With `uv` (Recommended)

```bash
git clone <repo-url> RDR-transit
cd RDR-transit
uv sync
```

To run directly via `uv`:
```bash
uv run rdr-transit
```

### With `pip` / Standard Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate   # On Windows: .venv\Scripts\activate
pip install -e .
```

---

## Usage

### 1. Graphical User Interface (GUI) Mode

Launch the Desktop GUI:
```bash
rdr-transit gui
```
- **Discovered Peers Live Grid**: Auto-detects local devices with OS icons (Android, Apple, Linux, Windows).
- **Drag & Select File Staging**: Select multiple files or entire directories with real-time size computation.
- **Transfer Dashboard**: Live dual progress bars, transfer speeds (MB/s), and incremental skip status.
- **Background Receiver Toggle**: One-click enable/disable receiver daemon.
- **Instant Snippet Sharing**: Fast cross-device clipboard & text sharing.

---

### 2. Interactive Terminal UI (TUI) Mode

Launch the `nmtui`-inspired full-screen interface:
```bash
rdr-transit
# or
rdr-transit tui
```

#### TUI Highlights
* **Active Peer Discovery**: Automatically identifies Windows PCs, Linux machines, and macOS devices broadcasting on the subnet.
* **Stage & Send**: Add files or folders into the send queue with live preview of counts and sizes.
* **Built-in Receiver Server**: Toggle incoming file reception on/off with a single keystroke.
* **Responsive Navigation**: Full keyboard navigation (`Tab`, `Enter`, `s` for Send, `r` for Receive, `d` for Discovery refresh, `q` for Quit).

---

### 3. Mobile Apps (Android & Apple iOS)

A companion Flutter application is available in `apps/flutter_transit/`:
- **Android**: Supports APK and Play Store bundle with Wi-Fi Multicast lock and media pickers.
- **Apple iOS**: Seamless iPhone/iPad support with Apple Files app integration (`UIFileSharingEnabled`) and local network discovery permissions.

To run or build the mobile apps:
```bash
cd apps/flutter_transit
flutter pub get
flutter run -d android   # Run on Android
flutter run -d ios       # Run on iOS
```
See [apps/flutter_transit/README.md](file:///home/victor/antigravity/RDR-transit/apps/flutter_transit/README.md) for full instructions.

---

### 4. Command Line Interface (CLI) Mode

#### Send Files or Directories
```bash
# Send an entire folder (recursively preserves directory layout)
rdr-transit send /path/to/folder --target 192.168.137.1

# High-speed transfer with 4 parallel concurrent streams (-j 4)
rdr-transit send /path/to/large_directory --target 192.168.137.1 -j 4

# Send multiple files
rdr-transit send file1.iso file2.pdf --target 192.168.137.1

# Auto-discover target device and send
rdr-transit send my_project/
```

#### Receive Files (Receiver Server)
```bash
# Start listening for incoming files on TCP port 17116 (with incremental skip & SHA-256 verification)
rdr-transit receive

# Custom save directory and port
rdr-transit receive --output-dir ~/Transfers --port 17116

# Force overwrite existing files without skipping
rdr-transit receive --no-skip
```

#### Clipboard & Text Snippet Sharing
```bash
# Send text or URL directly to a peer
rdr-transit snippet "https://github.com/victor/RDR-transit" --target 192.168.137.1

# Pipe clipboard or command output to peer
cat token.txt | rdr-transit snippet --target 192.168.137.1
```

#### User Configuration & Settings
```bash
# View configuration
rdr-transit config

# Update default settings
rdr-transit config --set default_parallel 6
rdr-transit config --set download_dir ~/Transfers
```

#### Discover Devices
```bash
# Scan local network for LAN-Share / RDR-Transit peers
rdr-transit discover
```

---

## Cross-Platform Architecture

| Feature | Linux | Windows | macOS |
| :--- | :--- | :--- | :--- |
| **Discovery Broadcast** | UDP `56780` (`SO_REUSEADDR`, `SO_REUSEPORT`) | UDP `56780` (`SO_REUSEADDR`) | UDP `56780` (`SO_REUSEADDR`, `SO_REUSEPORT`) |
| **Transfer Stream** | TCP `17116` (96 KB stream chunks) | TCP `17116` | TCP `17116` |
| **File Path Safety** | Posix sanitization, symlink skip | Windows invalid char escaping (`: * ? " < > |`), path traversal block | Posix sanitization, hidden file handling |
| **Default Download Dir** | `~/Downloads/RDR-Transit` | `%USERPROFILE%\Downloads\RDR-Transit` | `~/Downloads/RDR-Transit` |

---

## Protocol Specification

RDR Transit follows a binary-framed TCP streaming protocol:
1. **Packet Framing**: `[4 bytes: Little-Endian Int32 Length] [1 byte: Int8 PacketType] [Payload]`
2. **Packet Types**:
   - `0x01` (`Header`): JSON payload `{ "name": "<filename>", "folder": "<relative_folder>", "size": <bytes> }`
   - `0x02` (`Data`): Binary chunk payload (up to 96 KB per packet)
   - `0x03` (`Finish`): Length 0 packet signaling complete reception of current file
   - `0x04` (`Cancel`): Abort active transfer
   - `0x05` / `0x06` (`Pause` / `Resume`)

---

## License

MIT License.
