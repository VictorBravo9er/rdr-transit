"""Tests for binary framing and protocol serialization."""

import io
import socket
import pytest

from rdr_transit.protocol import (
    PacketType,
    create_cancel_packet,
    create_data_packet,
    create_finish_packet,
    create_header_packet,
    parse_header_payload,
    read_packet,
)


def test_header_packet():
    pkt = create_header_packet(name="document.pdf", folder="work/2026", size=1048576)
    # Total header size is 5 bytes struct + json payload
    assert len(pkt) > 5

    # Simulate receiving over a socket pair
    server, client = socket.socketpair()
    try:
        client.sendall(pkt)
        ptype, payload = read_packet(server)
        assert ptype == PacketType.HEADER
        info = parse_header_payload(payload)
        assert info["name"] == "document.pdf"
        assert info["folder"] == "work/2026"
        assert info["size"] == 1048576
    finally:
        server.close()
        client.close()


def test_data_packet():
    data = b"Hello, RDR-Transit streaming world!"
    pkt = create_data_packet(data)

    server, client = socket.socketpair()
    try:
        client.sendall(pkt)
        ptype, payload = read_packet(server)
        assert ptype == PacketType.DATA
        assert payload == data
    finally:
        server.close()
        client.close()


def test_finish_packet():
    pkt = create_finish_packet()
    server, client = socket.socketpair()
    try:
        client.sendall(pkt)
        ptype, payload = read_packet(server)
        assert ptype == PacketType.FINISH
        assert payload == b""
    finally:
        server.close()
        client.close()


def test_cancel_packet():
    pkt = create_cancel_packet()
    server, client = socket.socketpair()
    try:
        client.sendall(pkt)
        ptype, payload = read_packet(server)
        assert ptype == PacketType.CANCEL
        assert payload == b""
    finally:
        server.close()
        client.close()
