"""
Configuration persistence, user settings, and defaults management.
"""

from dataclasses import asdict, dataclass, field
import json
import os
from pathlib import Path
from typing import Dict, List, Optional

from rdr_transit.config import (
    DEFAULT_BROADCAST_PORT,
    DEFAULT_DOWNLOAD_DIR,
    DEFAULT_TRANSFER_PORT,
    HOSTNAME,
)

CONFIG_DIR: Path = Path.home() / ".config" / "rdr-transit"
CONFIG_FILE: Path = CONFIG_DIR / "config.json"


@dataclass
class AppConfig:
    """User-configurable settings persisted to disk."""
    device_name: str = HOSTNAME
    transfer_port: int = DEFAULT_TRANSFER_PORT
    broadcast_port: int = DEFAULT_BROADCAST_PORT
    download_dir: str = str(DEFAULT_DOWNLOAD_DIR)
    default_parallel: int = 4
    beacon_interval: float = 4.0
    incremental_sync: bool = False
    verify_checksum: bool = True
    peer_aliases: Dict[str, str] = field(default_factory=dict)  # {"alias": "ip_or_hostname"}
    recent_targets: List[str] = field(default_factory=list)


def load_config() -> AppConfig:
    """Load configuration from ~/.config/rdr-transit/config.json or return defaults."""
    if not CONFIG_FILE.exists():
        return AppConfig()

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return AppConfig(
                device_name=data.get("device_name", HOSTNAME),
                transfer_port=data.get("transfer_port", DEFAULT_TRANSFER_PORT),
                broadcast_port=data.get("broadcast_port", DEFAULT_BROADCAST_PORT),
                download_dir=data.get("download_dir", str(DEFAULT_DOWNLOAD_DIR)),
                default_parallel=data.get("default_parallel", 4),
                beacon_interval=float(data.get("beacon_interval", 4.0)),
                incremental_sync=data.get("incremental_sync", False),
                verify_checksum=data.get("verify_checksum", True),
                peer_aliases=data.get("peer_aliases", {}),
                recent_targets=data.get("recent_targets", []),
            )
    except Exception:
        return AppConfig()


def save_config(cfg: AppConfig) -> None:
    """Save configuration to ~/.config/rdr-transit/config.json."""
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(asdict(cfg), f, indent=2)
    except Exception:
        pass
