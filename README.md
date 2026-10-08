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

### 1. Interactive Terminal UI (TUI) Mode

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

### 2. Command Line Interface (CLI) Mode

#### Send Files or Directories
```bash
# Send an entire folder (recursively preserves directory layout)
rdr-transit send /path/to/folder --target 192.168.137.1

# Send multiple files
rdr-transit send file1.iso file2.pdf --target 192.168.137.1

# Auto-discover target device and send
rdr-transit send my_project/
```

#### Receive Files (Receiver Server)
```bash
# Start listening for incoming files on TCP port 17116
rdr-transit receive

# Custom save directory and port
rdr-transit receive --output-dir ~/Transfers --port 17116
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
