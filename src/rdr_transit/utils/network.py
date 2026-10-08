"""
Cross-platform network interface queries and socket utilities.
"""

import os
import platform
import socket
from typing import List, Set


def get_primary_ip() -> str:
    """
    Detect the machine's primary outward-facing IPv4 address without sending actual traffic.
    Works reliably across Windows, Linux, and macOS.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Does not actually establish a connection or send packets on UDP
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        return ip
    except Exception:
        # Fallback to hostname resolution
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"
    finally:
        s.close()


def get_all_local_ips() -> List[str]:
    """Retrieve all local non-loopback IPv4 addresses assigned to this host."""
    ips: Set[str] = set()
    primary = get_primary_ip()
    if primary and not primary.startswith("127."):
        ips.add(primary)

    try:
        host = socket.gethostname()
        for ip in socket.gethostbyname_ex(host)[2]:
            if not ip.startswith("127."):
                ips.add(ip)
    except Exception:
        pass

    return sorted(list(ips))


def create_udp_broadcast_socket(bind_port: int, reuse: bool = True) -> socket.socket:
    """
    Create a UDP socket configured for broadcasting and listening,
    handling differences between Linux, Windows, and macOS.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    if reuse:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # SO_REUSEPORT is available on Linux and macOS, but not on Windows
        if hasattr(socket, "SO_REUSEPORT"):
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except OSError:
                pass

    # On Windows, binding to '' or '0.0.0.0' works smoothly
    sock.bind(("", bind_port))
    return sock
