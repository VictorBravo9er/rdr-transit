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
