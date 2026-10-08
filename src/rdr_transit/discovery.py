"""
Zero-configuration UDP peer discovery and beacon service (LAN-Share protocol compatible).
"""

from dataclasses import dataclass, field
import json
import logging
import socket
import threading
import time
from typing import Callable, Dict, List, Optional
import uuid

from rdr_transit.config import (
    DEFAULT_BROADCAST_PORT,
    DEFAULT_TRANSFER_PORT,
    HOSTNAME,
    SYSTEM_OS,
)
from rdr_transit.utils.network import create_udp_broadcast_socket

logger = logging.getLogger(__name__)


@dataclass
class DiscoveredPeer:
    """Represents a discovered network peer."""
    ip: str
    name: str
    os: str
    port: int = DEFAULT_TRANSFER_PORT
    device_id: str = ""
    last_seen: float = field(default_factory=time.time)

    @property
    def is_alive(self) -> bool:
        """Returns True if peer was seen in the last 15 seconds."""
        return (time.time() - self.last_seen) < 15.0

    @property
    def os_badge(self) -> str:
        """Return a platform badge symbol."""
        os_lower = self.os.lower()
        if "win" in os_lower:
            return "Windows"
        elif "mac" in os_lower or "darwin" in os_lower:
            return "macOS"
        elif "linux" in os_lower:
            return "Linux"
        return self.os or "Unknown"


def send_beacon(
    target_ip: str = "255.255.255.255",
    broadcast_port: int = DEFAULT_BROADCAST_PORT,
    device_id: Optional[str] = None,
    name: Optional[str] = None,
    os_name: Optional[str] = None,
) -> None:
    """Send a single UDP broadcast beacon to announce this device to other peers."""
    if device_id is None:
        device_id = "{" + str(uuid.uuid4()) + "}"
    if name is None:
        name = HOSTNAME
    if os_name is None:
        os_name = SYSTEM_OS

    payload = json.dumps({
        "id": device_id,
        "name": name,
        "os": os_name,
        "port": broadcast_port,
    }).encode("utf-8")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    try:
        sock.sendto(payload, (target_ip, broadcast_port))
        # If target was specific IP, also broadcast to 255.255.255.255
        if target_ip != "255.255.255.255":
            try:
                sock.sendto(payload, ("255.255.255.255", broadcast_port))
            except Exception:
                pass
    except Exception as e:
        logger.debug("Error sending discovery beacon: %s", e)
    finally:
        sock.close()


def discover_peers(timeout: float = 2.0, broadcast_port: int = DEFAULT_BROADCAST_PORT) -> List[DiscoveredPeer]:
    """
    Perform a one-shot discovery scan.
    Sends an announcement beacon, listens for replies/beacons during `timeout` seconds,
    and returns a list of discovered peers.
    """
    peers: Dict[str, DiscoveredPeer] = {}

    try:
        sock = create_udp_broadcast_socket(broadcast_port, reuse=True)
    except Exception as e:
        logger.warning("Could not bind discovery socket: %s", e)
        return []

    # Send outgoing beacon to provoke responses
    send_beacon(broadcast_port=broadcast_port)

    sock.settimeout(0.3)
    start_time = time.time()

    while time.time() - start_time < timeout:
        try:
            data, addr = sock.recvfrom(4096)
            ip = addr[0]
            try:
                msg = json.loads(data.decode("utf-8", errors="ignore"))
                if isinstance(msg, dict) and "name" in msg:
                    peers[ip] = DiscoveredPeer(
                        ip=ip,
                        name=msg.get("name", "Unknown"),
                        os=msg.get("os", "Unknown"),
                        port=DEFAULT_TRANSFER_PORT,
                        device_id=msg.get("id", ""),
                        last_seen=time.time(),
                    )
            except json.JSONDecodeError:
                continue
        except socket.timeout:
            continue
        except Exception:
            break

    sock.close()
    return list(peers.values())


class PeerDiscoveryService:
    """
    Continuous background discovery listener and beacon broadcaster.
    Calls registered callbacks whenever peers are detected or updated.
    """

    def __init__(
        self,
        broadcast_port: int = DEFAULT_BROADCAST_PORT,
        beacon_interval: float = 4.0,
        on_peer_updated: Optional[Callable[[DiscoveredPeer], None]] = None,
    ):
        self.broadcast_port = broadcast_port
        self.beacon_interval = beacon_interval
        self.on_peer_updated = on_peer_updated
        self.peers: Dict[str, DiscoveredPeer] = {}
        self._running = False
        self._listener_thread: Optional[threading.Thread] = None
        self._beacon_thread: Optional[threading.Thread] = None
        self._sock: Optional[socket.socket] = None
        self.my_device_id = "{" + str(uuid.uuid4()) + "}"

    def start(self) -> None:
        """Start background discovery listener and beacon loops."""
        if self._running:
            return
        self._running = True

        try:
            self._sock = create_udp_broadcast_socket(self.broadcast_port, reuse=True)
            self._sock.settimeout(1.0)
        except Exception as e:
            logger.error("Failed to start discovery listener on port %d: %s", self.broadcast_port, e)
            self._running = False
            return

        self._listener_thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._listener_thread.start()

        self._beacon_thread = threading.Thread(target=self._beacon_loop, daemon=True)
        self._beacon_thread.start()

    def stop(self) -> None:
        """Stop background service."""
        self._running = False
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None

    def trigger_beacon(self) -> None:
        """Immediately broadcast a beacon."""
        send_beacon(broadcast_port=self.broadcast_port, device_id=self.my_device_id)

    def get_active_peers(self) -> List[DiscoveredPeer]:
        """Return list of peers seen recently."""
        now = time.time()
        # Clean up peers older than 20s
        active = [p for p in self.peers.values() if (now - p.last_seen) < 20.0]
        return sorted(active, key=lambda p: p.name)

    def _listen_loop(self) -> None:
        while self._running and self._sock:
            try:
                data, addr = self._sock.recvfrom(4096)
                ip = addr[0]
                msg = json.loads(data.decode("utf-8", errors="ignore"))
                if isinstance(msg, dict) and "name" in msg:
                    # Ignore self-beacons if matching device id
                    if msg.get("id") == self.my_device_id:
                        continue

                    peer = DiscoveredPeer(
                        ip=ip,
                        name=msg.get("name", "Unknown"),
                        os=msg.get("os", "Unknown"),
                        port=DEFAULT_TRANSFER_PORT,
                        device_id=msg.get("id", ""),
                        last_seen=time.time(),
                    )
                    self.peers[ip] = peer
                    if self.on_peer_updated:
                        self.on_peer_updated(peer)
            except (socket.timeout, OSError):
                continue
            except Exception as e:
                logger.debug("Error in discovery listen loop: %s", e)

    def _beacon_loop(self) -> None:
        while self._running:
            send_beacon(broadcast_port=self.broadcast_port, device_id=self.my_device_id)
            time.sleep(self.beacon_interval)
