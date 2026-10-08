"""
Configuration defaults and constants for RDR-Transit.
"""

import os
import platform
import socket
from pathlib import Path

# Networking Ports
DEFAULT_BROADCAST_PORT: int = 56780
DEFAULT_TRANSFER_PORT: int = 17116

# Transfer Framing & Buffers
DEFAULT_CHUNK_SIZE: int = 98304  # 96 KB
MAX_PACKET_SIZE: int = 1048576   # 1 MB

# Timeouts (seconds)
DEFAULT_DISCOVERY_TIMEOUT: float = 2.0
DEFAULT_SOCKET_TIMEOUT: float = 20.0
DEFAULT_CONNECT_TIMEOUT: float = 6.0

# System info
SYSTEM_OS: str = platform.system()  # 'Linux', 'Windows', 'Darwin'
HOSTNAME: str = socket.gethostname()

# Default Download Directory (OS-safe)
DEFAULT_DOWNLOAD_DIR: Path = Path.home() / "Downloads" / "RDR-Transit"

# Default directory exclusion set for recursive transfers
DEFAULT_EXCLUDED_DIRS: set[str] = {
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".git",
    "node_modules",
    ".idea",
    ".vscode",
}
