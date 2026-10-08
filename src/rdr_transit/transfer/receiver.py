"""
TCP receiver server that listens for incoming LAN-Share transfer connections.
"""

import logging
from pathlib import Path
import socket
import threading
from typing import Callable, Optional, Tuple

from rdr_transit.config import (
    DEFAULT_DOWNLOAD_DIR,
    DEFAULT_TRANSFER_PORT,
)
from rdr_transit.protocol import (
    PacketType,
    parse_header_payload,
    read_packet,
)
from rdr_transit.utils.filesystem import sanitize_destination_path

logger = logging.getLogger(__name__)


class ReceiverServer:
    """
    Multi-client TCP receiver service that processes incoming files according
    to the LAN-Share packet specification, safely storing them in a destination folder.
    """

    def __init__(
        self,
        download_dir: Path = DEFAULT_DOWNLOAD_DIR,
        port: int = DEFAULT_TRANSFER_PORT,
        bind_host: str = "0.0.0.0",
        on_file_start: Optional[Callable[[str, str, str, int], None]] = None,
        on_chunk: Optional[Callable[[str, int], None]] = None,
        on_file_complete: Optional[Callable[[str, str, Path, bool, str], None]] = None,
    ):
        self.download_dir = download_dir.expanduser().resolve()
        self.port = port
        self.bind_host = bind_host

        self.on_file_start = on_file_start
        self.on_chunk = on_chunk
        self.on_file_complete = on_file_complete

        self._server_sock: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        """Start listening for incoming connections in a background thread."""
        if self._running:
            return

        self.download_dir.mkdir(parents=True, exist_ok=True)

        self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_sock.bind((self.bind_host, self.port))
        self._server_sock.listen(10)
        self._server_sock.settimeout(1.0)

        self._running = True
        self._thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._thread.start()
        logger.info("Receiver server listening on %s:%d (saving to %s)", self.bind_host, self.port, self.download_dir)

    def stop(self) -> None:
        """Stop the receiver server and close sockets."""
        self._running = False
        if self._server_sock:
            try:
                self._server_sock.close()
            except Exception:
                pass
            self._server_sock = None

    def _accept_loop(self) -> None:
        while self._running and self._server_sock:
            try:
                client_sock, client_addr = self._server_sock.accept()
                peer_ip = client_addr[0]
                # Handle each incoming client transfer in its own worker thread
                t = threading.Thread(
                    target=self._handle_client,
                    args=(client_sock, peer_ip),
                    daemon=True,
                )
                t.start()
            except socket.timeout:
                continue
            except OSError:
                break
            except Exception as e:
                logger.debug("Error in accept loop: %s", e)

    def _handle_client(self, client_sock: socket.socket, peer_ip: str) -> None:
        current_file_path: Optional[Path] = None
        fhandle = None
        file_name = ""
        rel_folder = ""
        expected_size = 0
        bytes_written = 0
        success = False
        error_msg = ""

        try:
            client_sock.settimeout(30.0)

            while True:
                packet = read_packet(client_sock)
                if packet is None:
                    break

                ptype, payload = packet

                if ptype == PacketType.HEADER:
                    info = parse_header_payload(payload)
                    file_name = info["name"]
                    rel_folder = info["folder"]
                    expected_size = info["size"]

                    current_file_path = sanitize_destination_path(self.download_dir, rel_folder, file_name)
                    current_file_path.parent.mkdir(parents=True, exist_ok=True)
                    fhandle = open(current_file_path, "wb")
                    bytes_written = 0

                    if self.on_file_start:
                        self.on_file_start(peer_ip, file_name, rel_folder, expected_size)

                elif ptype == PacketType.DATA:
                    if fhandle:
                        fhandle.write(payload)
                        bytes_written += len(payload)
                        if self.on_chunk:
                            self.on_chunk(peer_ip, len(payload))

                elif ptype == PacketType.FINISH:
                    if fhandle:
                        fhandle.flush()
                        fhandle.close()
                        fhandle = None
                    success = True
                    break

                elif ptype == PacketType.CANCEL:
                    if fhandle:
                        fhandle.close()
                        fhandle = None
                    if current_file_path and current_file_path.exists():
                        try:
                            current_file_path.unlink()
                        except OSError:
                            pass
                    error_msg = "Transfer cancelled by sender"
                    break

        except Exception as e:
            error_msg = str(e)
            logger.error("Error receiving file from %s: %s", peer_ip, e)
            if fhandle:
                try:
                    fhandle.close()
                except Exception:
                    pass
                fhandle = None
        finally:
            client_sock.close()
            if self.on_file_complete and file_name and current_file_path:
                self.on_file_complete(peer_ip, file_name, current_file_path, success, error_msg)
