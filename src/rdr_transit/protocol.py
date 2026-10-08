"""
LAN-Share binary wire protocol specification and packet serialization.
"""

from enum import IntEnum
import json
import struct
from typing import Any, Optional, Tuple


class PacketType(IntEnum):
    """LAN-Share packet types."""
    HEADER = 1
    DATA = 2
    FINISH = 3
    CANCEL = 4
    PAUSE = 5
    RESUME = 6


# Header format: 4-byte signed int (little-endian) + 1-byte signed char
# Total header length = 5 bytes
PACKET_HEADER_STRUCT = struct.Struct("<ib")
PACKET_HEADER_SIZE = PACKET_HEADER_STRUCT.size


def create_header_packet(name: str, folder: str, size: int) -> bytes:
    """
    Construct a Header packet (PacketType = 1).
    Header payload contains a JSON object: {"name": str, "folder": str, "size": int}.
    """
    header_data = {
        "name": name,
        "folder": folder,
        "size": size,
    }
    payload = json.dumps(header_data, ensure_ascii=False).encode("utf-8")
    header = PACKET_HEADER_STRUCT.pack(len(payload), PacketType.HEADER)
    return header + payload


def create_data_packet(chunk: bytes) -> bytes:
    """Construct a Data packet (PacketType = 2)."""
    header = PACKET_HEADER_STRUCT.pack(len(chunk), PacketType.DATA)
    return header + chunk


def create_finish_packet() -> bytes:
    """Construct a Finish packet (PacketType = 3) signaling complete file reception."""
    return PACKET_HEADER_STRUCT.pack(0, PacketType.FINISH)


def create_cancel_packet() -> bytes:
    """Construct a Cancel packet (PacketType = 4)."""
    return PACKET_HEADER_STRUCT.pack(0, PacketType.CANCEL)


def parse_header_payload(payload: bytes) -> dict[str, Any]:
    """Parse JSON payload of a Header packet into a dictionary."""
    text = payload.decode("utf-8", errors="replace")
    data = json.loads(text)
    return {
        "name": str(data.get("name", "")),
        "folder": str(data.get("folder", "")),
        "size": int(data.get("size", 0)),
    }


def read_exact(sock, length: int) -> bytes:
    """Read exactly `length` bytes from a socket, or raise ConnectionError on EOF."""
    buf = bytearray()
    while len(buf) < length:
        chunk = sock.recv(length - len(buf))
        if not chunk:
            raise ConnectionError(f"Connection closed prematurely, received {len(buf)}/{length} bytes")
        buf.extend(chunk)
    return bytes(buf)


def read_packet(sock) -> Optional[Tuple[PacketType, bytes]]:
    """
    Read the next framed packet from a connected socket.
    Returns (packet_type, payload), or None if socket closed cleanly before header.
    """
    header_bytes = bytearray()
    while len(header_bytes) < PACKET_HEADER_SIZE:
        chunk = sock.recv(PACKET_HEADER_SIZE - len(header_bytes))
        if not chunk:
            if len(header_bytes) == 0:
                return None  # Clean connection close
            raise ConnectionError("Connection reset while reading packet header")
        header_bytes.extend(chunk)

    data_size, ptype_raw = PACKET_HEADER_STRUCT.unpack(bytes(header_bytes))
    try:
        ptype = PacketType(ptype_raw)
    except ValueError:
        raise ValueError(f"Unknown packet type received: {ptype_raw}")

    if data_size > 0:
        payload = read_exact(sock, data_size)
    else:
        payload = b""

    return ptype, payload
