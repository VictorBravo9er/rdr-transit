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

