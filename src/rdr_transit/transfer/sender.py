"""
High-performance streaming file and directory sender (LAN-Share protocol compatible).
"""

from dataclasses import dataclass, field
import logging
import os
from pathlib import Path
import socket
import time
from typing import Callable, List, Optional, Tuple

from rdr_transit.config import (
    DEFAULT_CHUNK_SIZE,
    DEFAULT_CONNECT_TIMEOUT,
    DEFAULT_SOCKET_TIMEOUT,
    DEFAULT_TRANSFER_PORT,
)
from rdr_transit.protocol import (
    create_cancel_packet,
    create_data_packet,
    create_finish_packet,
    create_header_packet,
)

import concurrent.futures
import threading

logger = logging.getLogger(__name__)


@dataclass
class TransferStats:
    """Real-time and final statistics for a batch transfer operation."""
    total_files: int = 0
    completed_files: int = 0
    failed_files: int = 0
    total_bytes: int = 0
    transferred_bytes: int = 0
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    current_file_name: str = ""
    current_file_bytes: int = 0
    current_file_total: int = 0
    is_cancelled: bool = False
    active_transfers: int = 0

    @property
    def elapsed_seconds(self) -> float:
        end = self.end_time or time.time()
        return max(0.001, end - self.start_time)

    @property
    def speed_bytes_per_sec(self) -> float:
        return self.transferred_bytes / self.elapsed_seconds

    @property
    def speed_mb_per_sec(self) -> float:
        return (self.transferred_bytes / (1024 * 1024)) / self.elapsed_seconds

    @property
    def percent_complete(self) -> float:
        if self.total_bytes <= 0:
            return 100.0 if self.completed_files == self.total_files else 0.0
        return min(100.0, (self.transferred_bytes / self.total_bytes) * 100.0)


def send_single_file(
    abs_path: str,
    rel_folder: str,
    file_name: str,
    receiver_ip: str,
    transfer_port: int = DEFAULT_TRANSFER_PORT,
    timeout: float = DEFAULT_SOCKET_TIMEOUT,
    on_chunk: Optional[Callable[[int], None]] = None,
    is_cancelled_func: Optional[Callable[[], bool]] = None,
) -> Tuple[bool, str]:
    """
    Transmit a single file over TCP using the LAN-Share framing protocol.
    Returns: (success: bool, error_msg: str)
    """
    try:
        fsize = os.path.getsize(abs_path)
    except OSError as e:
        return False, f"Could not read local file size: {e}"

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)

    try:
        sock.connect((receiver_ip, transfer_port))

        # 1. Header packet
        header_pkt = create_header_packet(file_name, rel_folder, fsize)
        sock.sendall(header_pkt)

        # 2. Data chunks
        if fsize > 0:
            with open(abs_path, "rb") as f:
                while True:
                    if is_cancelled_func and is_cancelled_func():
                        try:
                            sock.sendall(create_cancel_packet())
                        except Exception:
                            pass
                        return False, "Cancelled by user"

                    chunk = f.read(DEFAULT_CHUNK_SIZE)
                    if not chunk:
                        break

                    data_pkt = create_data_packet(chunk)
                    sock.sendall(data_pkt)

                    if on_chunk:
                        on_chunk(len(chunk))

        # 3. Finish packet
        sock.sendall(create_finish_packet())

        # 4. Wait for receiver to cleanly acknowledge and close
        sock.settimeout(5.0)
        try:
            while sock.recv(1024):
                pass
        except (socket.timeout, ConnectionResetError, OSError):
            pass

        return True, ""

    except Exception as e:
        logger.debug("Failed sending %s to %s:%d: %s", file_name, receiver_ip, transfer_port, e)
        return False, str(e)
    finally:
        sock.close()


class BatchSender:
    """Orchestrates sending multiple files with optional parallel streams, live event callbacks, and cancellation."""

    def __init__(
        self,
        files_to_send: List[Tuple[str, str, str]],  # (abs_path, rel_folder, file_name)
        receiver_ip: str,
        transfer_port: int = DEFAULT_TRANSFER_PORT,
        max_workers: int = 1,
        on_file_start: Optional[Callable[[int, str, int], None]] = None,
        on_chunk: Optional[Callable[[int, int, int], None]] = None,
        on_file_done: Optional[Callable[[int, str, bool, str], None]] = None,
        on_stats_update: Optional[Callable[[TransferStats], None]] = None,
    ):
        self.files = files_to_send
        self.receiver_ip = receiver_ip
        self.transfer_port = transfer_port
        self.max_workers = max(1, max_workers)

        self.on_file_start = on_file_start
        self.on_chunk = on_chunk
        self.on_file_done = on_file_done
        self.on_stats_update = on_stats_update

        self._lock = threading.Lock()

        total_bytes = 0
        for p, _, _ in files_to_send:
            try:
                total_bytes += os.path.getsize(p)
            except OSError:
                pass

        self.stats = TransferStats(
            total_files=len(files_to_send),
            total_bytes=total_bytes,
        )
        self._cancelled = False

    def cancel(self) -> None:
        """Signal cancellation of ongoing batch transfer."""
        with self._lock:
            self._cancelled = True
            self.stats.is_cancelled = True

    def is_cancelled(self) -> bool:
        return self._cancelled

    def _transfer_worker(self, item: Tuple[int, Tuple[str, str, str]]) -> None:
        """Worker function for transferring a single file."""
        if self._cancelled:
            return

        idx, (abs_path, rel_folder, file_name) = item

        try:
            fsize = os.path.getsize(abs_path)
        except OSError:
            fsize = 0

        display_name = f"{rel_folder}/{file_name}" if rel_folder else file_name

        with self._lock:
            self.stats.active_transfers += 1
            self.stats.current_file_name = display_name
            self.stats.current_file_bytes = 0
            self.stats.current_file_total = fsize

        if self.on_file_start:
            self.on_file_start(idx, display_name, fsize)

        def chunk_callback(chunk_len: int) -> None:
            with self._lock:
                self.stats.current_file_bytes += chunk_len
                self.stats.transferred_bytes += chunk_len
            if self.on_chunk:
                self.on_chunk(chunk_len, self.stats.current_file_bytes, self.stats.transferred_bytes)
            if self.on_stats_update:
                self.on_stats_update(self.stats)

        success, err = send_single_file(
            abs_path=abs_path,
            rel_folder=rel_folder,
            file_name=file_name,
            receiver_ip=self.receiver_ip,
            transfer_port=self.transfer_port,
            on_chunk=chunk_callback,
            is_cancelled_func=self.is_cancelled,
        )

        with self._lock:
            self.stats.active_transfers -= 1
            if success:
                self.stats.completed_files += 1
            else:
                self.stats.failed_files += 1

        if self.on_file_done:
            self.on_file_done(idx, display_name, success, err)

        if self.on_stats_update:
            self.on_stats_update(self.stats)

    def run(self) -> TransferStats:
        """Execute the batch transfer either sequentially or concurrently."""
        self.stats.start_time = time.time()
        indexed_items = list(enumerate(self.files, 1))

        if self.max_workers == 1 or len(self.files) <= 1:
            for item in indexed_items:
                if self._cancelled:
                    break
                self._transfer_worker(item)
        else:
            workers = min(self.max_workers, len(self.files))
            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
                futures = [executor.submit(self._transfer_worker, item) for item in indexed_items]
                concurrent.futures.wait(futures)

        self.stats.end_time = time.time()
        return self.stats
