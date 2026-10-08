"""
Main Textual Application for RDR-Transit with an nmtui-inspired aesthetic.
"""

import os
from pathlib import Path
import time
from typing import Dict, List, Optional, Tuple

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Label,
    ListItem,
    ListView,
    Static,
)

from rdr_transit.config import (
    DEFAULT_DOWNLOAD_DIR,
    DEFAULT_EXCLUDED_DIRS,
    DEFAULT_TRANSFER_PORT,
    HOSTNAME,
    SYSTEM_OS,
)
from rdr_transit.discovery import DiscoveredPeer, PeerDiscoveryService
from rdr_transit.settings import AppConfig, load_config, save_config
from rdr_transit.transfer.receiver import ReceiverServer
from rdr_transit.transfer.sender import BatchSender, TransferStats, send_text_snippet
from rdr_transit.tui.screens import (
    AddPathDialog,
    HelpDialog,
    ManualPeerDialog,
    SendSnippetDialog,
    TransferProgressModal,
)
from rdr_transit.utils.filesystem import collect_target_files, format_size
from rdr_transit.utils.network import get_primary_ip


class RDRTransitApp(App[None]):
    """Full-screen interactive TUI for RDR-Transit."""

    CSS_PATH = "styles.tcss"
    TITLE = "RDR TRANSIT"
    SUB_TITLE = "Peer-to-Peer Local Network Transfer"

    BINDINGS = [
        Binding("q", "quit", "Quit", priority=True),
        Binding("d", "scan_peers", "Scan Peers"),
        Binding("a", "add_path", "Add Path"),
        Binding("p", "send_snippet", "Snippet"),
        Binding("c", "clear_queue", "Clear Queue"),
        Binding("s", "send_staged", "Send Staged"),
        Binding("r", "toggle_receiver", "Toggle Receiver"),
        Binding("question_mark", "show_help", "Help"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.config: AppConfig = load_config()
        self.primary_ip = get_primary_ip()
        self.discovery_service = PeerDiscoveryService(broadcast_port=self.config.broadcast_port)
        self.receiver_server = ReceiverServer(
            download_dir=Path(self.config.download_dir),
            port=self.config.transfer_port,
            allow_skip=True,
            verify_checksum=self.config.verify_checksum,
            on_file_start=self._on_incoming_file_start,
            on_file_complete=self._on_incoming_file_complete,
            on_snippet_received=self._on_incoming_snippet,
        )

        self.staged_paths: List[Path] = []
        self.selected_target_ip: Optional[str] = None
        self.active_peers: Dict[str, DiscoveredPeer] = {}
        self.parallel_workers: int = self.config.default_parallel
        self.current_transfer_modal: Optional[TransferProgressModal] = None
        self.current_batch_sender: Optional[BatchSender] = None

    def compose(self) -> ComposeResult:
        # Header banner
        with Horizontal(id="app-header"):
            yield Label(f"⚡ RDR TRANSIT | {self.config.device_name} ({SYSTEM_OS})", id="header-title")
            yield Label(f"IP: {self.primary_ip}", id="header-ip-badge")

        with Horizontal(id="main-container"):
            # Left Column: Discovered Network Peers
            with Vertical(id="left-pane"):
                yield Label("📡 Discovered Network Peers", classes="pane-title")
                yield DataTable(id="peer-table", cursor_type="row")
                with Horizontal(classes="button-row"):
                    yield Button("Scan Peers", id="btn-scan", classes="-primary")
                    yield Button("Direct IP", id="btn-manual-ip")

            # Right Column: Transfer Queue & Receiver Server
            with Vertical(id="right-pane"):
                yield Label("📦 Staged Items to Send", classes="pane-title")
                with Vertical(id="staging-box"):
                    yield ListView(id="staging-list")
                    yield Label("No items staged. Press 'a' or [Add Path] to stage files.", id="staging-summary")

                with Horizontal(classes="button-row"):
                    yield Button("Add Path", id="btn-add-path", classes="-primary")
                    yield Button("Send Snippet", id="btn-snippet")
                    yield Button("Clear", id="btn-clear-path")
                    yield Button("Send Staged", id="btn-send", classes="-success")

                # Receiver Status Card
                with Vertical(id="receiver-panel"):
                    yield Label("📥 Incoming Receiver Daemon", classes="pane-title")
                    yield Label("Status: Inactive (Stopped)", id="receiver-status-label")
                    with Horizontal(classes="button-row"):
                        yield Button("Start Receiver", id="btn-toggle-receiver", classes="-primary")

        yield Footer(id="app-footer")

    def on_mount(self) -> None:
        """Initialize UI widgets, table columns, and background services."""
        table = self.query_one("#peer-table", DataTable)
        table.add_columns("Status", "Device Name", "OS", "IP Address")

        # Start peer discovery listener
        self.discovery_service.start()
        # Automatically start the receiver daemon so the device is immediately ready to accept files
        self._start_receiver()

        # Set periodic refresh timer for peer list table
        self.set_interval(2.0, self._refresh_peers_ui)
        self.set_interval(5.0, self.discovery_service.trigger_beacon)

    def on_unmount(self) -> None:
        """Clean up background services on app shutdown."""
        self.discovery_service.stop()
        self.receiver_server.stop()

    def _refresh_peers_ui(self) -> None:
        """Update peer table with currently active network peers."""
        peers = self.discovery_service.get_active_peers()
        table = self.query_one("#peer-table", DataTable)

        current_cursor = table.cursor_row
        table.clear()

        self.active_peers.clear()
        for p in peers:
            self.active_peers[p.ip] = p
            status_text = "● ONLINE" if p.is_alive else "○ IDLE"
            table.add_row(status_text, p.name, p.os_badge, p.ip, key=p.ip)

        # Restore cursor selection if available
        if table.row_count > 0 and current_cursor is not None and current_cursor < table.row_count:
            table.cursor_coordinate = (current_cursor, 0)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """When a peer row is chosen from the table."""
        if event.row_key:
            ip = str(event.row_key.value)
            self.selected_target_ip = ip
            peer = self.active_peers.get(ip)
            peer_name = peer.name if peer else ip
            self.notify(f"Selected destination peer: {peer_name} ({ip})")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id
        if btn_id == "btn-scan":
            self.action_scan_peers()
        elif btn_id == "btn-manual-ip":
            self._open_manual_ip_dialog()
        elif btn_id == "btn-add-path":
            self.action_add_path()
        elif btn_id == "btn-snippet":
            self.action_send_snippet()
        elif btn_id == "btn-clear-path":
            self.action_clear_queue()
        elif btn_id == "btn-send":
            self.action_send_staged()
        elif btn_id == "btn-toggle-receiver":
            self.action_toggle_receiver()

    def action_scan_peers(self) -> None:
        """Trigger an instant broadcast beacon and peer list update."""
        self.discovery_service.trigger_beacon()
        self.notify("Broadcasting discovery beacon...")
        self._refresh_peers_ui()

    def _open_manual_ip_dialog(self) -> None:
        """Show manual IP dialog."""
        def callback(ip: Optional[str]) -> None:
            if ip:
                self.selected_target_ip = ip
                self.notify(f"Selected custom target IP: {ip}")
        self.push_screen(ManualPeerDialog(), callback)

    def action_add_path(self) -> None:
        """Open Add Path dialog."""
        def callback(path_str: Optional[str]) -> None:
            if path_str:
                p = Path(path_str)
                if p not in self.staged_paths:
                    self.staged_paths.append(p)
                    self._update_staging_ui()
                    self.notify(f"Staged: {p.name}")
        self.push_screen(AddPathDialog(), callback)

    def action_send_snippet(self) -> None:
        """Open Send Snippet dialog."""
        target_ip = self.selected_target_ip
        if not target_ip:
            table = self.query_one("#peer-table", DataTable)
            if table.row_count > 0:
                coords = table.coordinate_to_cell_key(table.cursor_coordinate)
                target_ip = str(coords.row_key.value)
                self.selected_target_ip = target_ip
            else:
                self.notify("Select a peer first to send snippet to!", severity="warning")
                self._open_manual_ip_dialog()
                return

        def callback(snippet_text: Optional[str]) -> None:
            if snippet_text:
                self._run_send_snippet_worker(snippet_text, target_ip)
        self.push_screen(SendSnippetDialog(), callback)

    @work(thread=True)
    def _run_send_snippet_worker(self, text: str, target_ip: str) -> None:
        ok, err = send_text_snippet(
            text=text,
            receiver_ip=target_ip,
            transfer_port=self.config.transfer_port,
            sender_name=self.config.device_name,
        )
        if ok:
            self.call_from_thread(self.notify, f"✓ Sent snippet to {target_ip}!")
        else:
            self.call_from_thread(self.notify, f"✗ Failed sending snippet: {err}", severity="error")

    def _on_incoming_snippet(self, peer_ip: str, text: str, path: str) -> None:
        preview = text[:40] + ("..." if len(text) > 40 else "")
        self.notify(f"📋 Received snippet from {peer_ip}: {preview}", severity="information")

    def action_clear_queue(self) -> None:
        """Clear all staged transfer paths."""
        self.staged_paths.clear()
        self._update_staging_ui()
        self.notify("Cleared staging queue.")

    def _update_staging_ui(self) -> None:
        """Re-render the staging list view and summary label."""
        list_view = self.query_one("#staging-list", ListView)
        list_view.clear()

        total_files = 0
        total_bytes = 0

        for p in self.staged_paths:
            if p.is_file():
                fsize = p.stat().st_size
                total_files += 1
                total_bytes += fsize
                item_label = f"📄 {p.name} ({format_size(fsize)})"
            elif p.is_dir():
                items = collect_target_files([p])
                dir_bytes = sum(os.path.getsize(f[0]) for f in items)
                total_files += len(items)
                total_bytes += dir_bytes
                item_label = f"📁 {p.name}/ ({len(items)} files, {format_size(dir_bytes)})"
            else:
                item_label = f"❓ {p.name}"

            list_view.append(ListItem(Label(item_label)))

        summary_label = self.query_one("#staging-summary", Label)
        if self.staged_paths:
            summary_label.update(f"Staged: {len(self.staged_paths)} items ({total_files} files, {format_size(total_bytes)})")
        else:
            summary_label.update("No items staged. Press 'a' or [Add Path] to stage files.")

    def action_toggle_receiver(self) -> None:
        """Toggle receiver server on and off."""
        if self.receiver_server.is_running:
            self._stop_receiver()
        else:
            self._start_receiver()

    def _start_receiver(self) -> None:
        try:
            self.receiver_server.start()
            panel = self.query_one("#receiver-panel", Vertical)
            panel.add_class("running")
            label = self.query_one("#receiver-status-label", Label)
            label.update(
                f"[bold green]● Active[/bold green] | Port: [cyan]{DEFAULT_TRANSFER_PORT}[/cyan] | Saving to: [dim]{DEFAULT_DOWNLOAD_DIR}[/dim]"
            )
            btn = self.query_one("#btn-toggle-receiver", Button)
            btn.label = "Stop Receiver"
            btn.classes = "-danger"
        except OSError as e:
            label = self.query_one("#receiver-status-label", Label)
            label.update(f"[bold yellow]⚠ Port {DEFAULT_TRANSFER_PORT} in use[/bold yellow]")
            self.notify(f"Receiver port {DEFAULT_TRANSFER_PORT} unavailable: {e}", severity="warning")

    def _stop_receiver(self) -> None:
        self.receiver_server.stop()
        panel = self.query_one("#receiver-panel", Vertical)
        panel.remove_class("running")
        label = self.query_one("#receiver-status-label", Label)
        label.update("[bold red]○ Inactive (Stopped)[/bold red]")
        btn = self.query_one("#btn-toggle-receiver", Button)
        btn.label = "Start Receiver"
        btn.classes = "-primary"

    def _on_incoming_file_start(self, peer_ip: str, fname: str, folder: str, fsize: int) -> None:
        desc = f"{folder}/{fname}" if folder else fname
        self.notify(f"📥 Receiving from {peer_ip}: {desc} ({format_size(fsize)})")

    def _on_incoming_file_complete(self, peer_ip: str, fname: str, dest: Path, ok: bool, err: str) -> None:
        if ok:
            self.notify(f"✓ Saved incoming file: {dest.name}", severity="information")
        else:
            self.notify(f"✗ Failed incoming file from {peer_ip}: {err}", severity="error")

    def action_send_staged(self) -> None:
        """Validate destination and staging queue, then trigger background transfer."""
        if not self.staged_paths:
            self.notify("No files staged! Add a file or folder first (key 'a').", severity="warning")
            return

        target_ip = self.selected_target_ip
        # If no target explicitly selected, check table selection or default to first peer
        if not target_ip:
            table = self.query_one("#peer-table", DataTable)
            if table.row_count > 0:
                # Use current cursor row
                row_key = table.get_row_at(table.cursor_row if table.cursor_row is not None else 0)
                # Lookup by row key
                coords = table.coordinate_to_cell_key(table.cursor_coordinate)
                target_ip = str(coords.row_key.value)
                self.selected_target_ip = target_ip
            else:
                self.notify("No target peer selected! Click a peer or use [Direct IP].", severity="warning")
                self._open_manual_ip_dialog()
                return

        # Prepare file list
        files_to_send = collect_target_files(self.staged_paths)
        if not files_to_send:
            self.notify("No valid files found inside staged paths.", severity="error")
            return

        total_bytes = sum(os.path.getsize(f[0]) for f in files_to_send)
        total_files = len(files_to_send)

        peer = self.active_peers.get(target_ip)
        target_name = f"{peer.name} ({target_ip})" if peer else target_ip

        # Create and display transfer modal
        modal = TransferProgressModal(
            target_label=target_name,
            total_bytes=total_bytes,
            total_files=total_files,
            parallel_workers=self.parallel_workers,
            on_cancel=self._cancel_active_transfer,
        )
        self.current_transfer_modal = modal
        self.push_screen(modal)

        # Launch background worker
        self._run_transfer_worker(files_to_send, target_ip)

    def _cancel_active_transfer(self) -> None:
        if self.current_batch_sender:
            self.current_batch_sender.cancel()
            self.notify("Cancelling ongoing transfer...")

    @work(thread=True)
    def _run_transfer_worker(self, files: List[Tuple[str, str, str]], target_ip: str) -> None:
        """Runs in background thread so the UI remains 100% responsive."""
        def stats_callback(stats: TransferStats) -> None:
            if self.current_transfer_modal:
                self.call_from_thread(
                    self.current_transfer_modal.update_progress,
                    stats.percent_complete,
                    stats.current_file_name,
                    stats.transferred_bytes,
                    stats.speed_mb_per_sec,
                    stats.completed_files,
                )

        sender = BatchSender(
            files_to_send=files,
            receiver_ip=target_ip,
            max_workers=self.parallel_workers,
            include_checksum=self.config.verify_checksum,
            on_stats_update=stats_callback,
        )
        self.current_batch_sender = sender
        stats = sender.run()

        success = (stats.failed_files == 0 and not stats.is_cancelled)
        skip_msg = f" ({stats.skipped_files} skipped)" if stats.skipped_files > 0 else ""
        msg = f"Transferred {stats.completed_files}/{stats.total_files} files{skip_msg} ({format_size(stats.transferred_bytes)})"

        if self.current_transfer_modal:
            self.call_from_thread(self.current_transfer_modal.mark_completed, success, msg)

        self.call_from_thread(
            self.notify,
            f"Transfer complete: {stats.completed_files}/{stats.total_files} sent{skip_msg}",
            severity="information" if success else "error",
        )

    def action_show_help(self) -> None:
        self.push_screen(HelpDialog())


def run_tui() -> None:
    """Helper to launch TUI."""
    app = RDRTransitApp()
    app.run()


if __name__ == "__main__":
    run_tui()
