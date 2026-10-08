"""End-to-end local socket tests for transfer engine."""

from pathlib import Path
import time
import pytest

from rdr_transit.transfer.receiver import ReceiverServer
from rdr_transit.transfer.sender import BatchSender, send_single_file


def test_end_to_end_transfer(tmp_path):
    # 1. Prepare sender source file
    src_dir = tmp_path / "sender_source"
    src_dir.mkdir()
    sample_file = src_dir / "sample.bin"
    test_content = b"0123456789ABCDEF" * 1024  # 16 KB
    sample_file.write_bytes(test_content)

    # 2. Prepare receiver target directory
    rec_dir = tmp_path / "receiver_dest"
    rec_dir.mkdir()

    # Pick an ephemeral test port
    test_port = 27116

    received_files = []

    def on_complete(peer_ip, fname, dest_path, ok, err):
        received_files.append((fname, dest_path, ok))

    server = ReceiverServer(
        download_dir=rec_dir,
        port=test_port,
        bind_host="127.0.0.1",
        on_file_complete=on_complete,
    )
    server.start()

    try:
        time.sleep(0.1)  # Allow socket to bind

        # 3. Transmit using BatchSender
        files_to_send = [(str(sample_file), "documents", "sample.bin")]
        sender = BatchSender(
            files_to_send=files_to_send,
            receiver_ip="127.0.0.1",
            transfer_port=test_port,
        )
        stats = sender.run()

        assert stats.completed_files == 1
        assert stats.failed_files == 0
        assert stats.transferred_bytes == len(test_content)

        # 4. Verify received content on disk
        dest_file = rec_dir / "documents" / "sample.bin"
        assert dest_file.exists()
        assert dest_file.read_bytes() == test_content

    finally:
        server.stop()


def test_parallel_transfers(tmp_path):
    # Prepare multiple source files
    src_dir = tmp_path / "parallel_source"
    src_dir.mkdir()
    files_to_send = []
    
    for i in range(5):
        f = src_dir / f"file_{i}.dat"
        content = f"Content for file {i} - {'X' * 5000}".encode()
        f.write_bytes(content)
        files_to_send.append((str(f), "batch", f"file_{i}.dat"))

    rec_dir = tmp_path / "parallel_dest"
    rec_dir.mkdir()
    test_port = 27117

    server = ReceiverServer(
        download_dir=rec_dir,
        port=test_port,
        bind_host="127.0.0.1",
    )
    server.start()

    try:
        time.sleep(0.1)

        # Transmit with 3 concurrent workers
        sender = BatchSender(
            files_to_send=files_to_send,
            receiver_ip="127.0.0.1",
            transfer_port=test_port,
            max_workers=3,
        )
        stats = sender.run()

        assert stats.completed_files == 5
        assert stats.failed_files == 0

        # Verify all 5 files were saved properly
        for i in range(5):
            dest_file = rec_dir / "batch" / f"file_{i}.dat"
            assert dest_file.exists()
            assert dest_file.read_bytes() == f"Content for file {i} - {'X' * 5000}".encode()

    finally:
        server.stop()


def test_incremental_skip_and_checksum(tmp_path):
    src_dir = tmp_path / "sync_source"
    src_dir.mkdir()
    f1 = src_dir / "doc.txt"
    content = b"Important project notes for RDR-Transit"
    f1.write_bytes(content)

    rec_dir = tmp_path / "sync_dest"
    rec_dir.mkdir()
    test_port = 27118

    server = ReceiverServer(
        download_dir=rec_dir,
        port=test_port,
        bind_host="127.0.0.1",
        allow_skip=True,
        verify_checksum=True,
    )
    server.start()

    try:
        time.sleep(0.1)

        # 1. First transfer: should transfer 1 file
        sender1 = BatchSender(
            files_to_send=[(str(f1), "docs", "doc.txt")],
            receiver_ip="127.0.0.1",
            transfer_port=test_port,
            include_checksum=True,
        )
        stats1 = sender1.run()
        assert stats1.completed_files == 1
        assert stats1.skipped_files == 0
        assert (rec_dir / "docs" / "doc.txt").read_bytes() == content

        # 2. Second transfer: identical file already exists -> should be SKIPPED!
        sender2 = BatchSender(
            files_to_send=[(str(f1), "docs", "doc.txt")],
            receiver_ip="127.0.0.1",
            transfer_port=test_port,
            include_checksum=True,
        )
        stats2 = sender2.run()
        assert stats2.skipped_files == 1
        assert stats2.completed_files == 0
        assert stats2.failed_files == 0

    finally:
        server.stop()


def test_snippet_transfer(tmp_path):
    from rdr_transit.transfer.sender import send_text_snippet

    rec_dir = tmp_path / "snippet_dest"
    rec_dir.mkdir()
    test_port = 27119

    received_snippets = []

    def on_snippet(peer_ip, text, file_path):
        received_snippets.append((peer_ip, text, file_path))

    server = ReceiverServer(
        download_dir=rec_dir,
        port=test_port,
        bind_host="127.0.0.1",
        on_snippet_received=on_snippet,
    )
    server.start()

    try:
        time.sleep(0.1)

        ok, err = send_text_snippet(
            text="https://github.com/victor/RDR-transit",
            receiver_ip="127.0.0.1",
            transfer_port=test_port,
            sender_name="TestSender",
        )
        assert ok
        assert not err

        time.sleep(0.1)
        assert len(received_snippets) == 1
        assert received_snippets[0][1] == "https://github.com/victor/RDR-transit"
        saved_file = Path(received_snippets[0][2])
        assert saved_file.exists()
        assert saved_file.read_text(encoding="utf-8") == "https://github.com/victor/RDR-transit"

    finally:
        server.stop()


