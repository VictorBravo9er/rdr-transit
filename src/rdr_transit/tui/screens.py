"""
Modal dialog screens for RDR-Transit TUI (Add files, Transfer progress, Manual peer).
"""

from pathlib import Path
from typing import Optional

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, ProgressBar, Static

from rdr_transit.utils.filesystem import format_size


class AddPathDialog(ModalScreen[Optional[str]]):
    """Dialog to enter a file or folder path to stage for sending."""

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog-window"):
            yield Label("📁 Add File or Directory to Send", classes="dialog-title")
            yield Label("Enter the path of the file or folder:")
            yield Input(id="path-input", placeholder="e.g. ~/Documents/notes.pdf or ./my_project")
            with Horizontal(classes="dialog-buttons"):
                yield Button("Cancel", id="btn-cancel", classes="-danger")
                yield Button("Add Path", id="btn-add", classes="-primary")

    def on_mount(self) -> None:
        self.query_one("#path-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._submit()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-add":
            self._submit()
        else:
            self.dismiss(None)

    def _submit(self) -> None:
        val = self.query_one("#path-input", Input).value.strip()
        if val:
            path = Path(val).expanduser().resolve()
            if path.exists():
                self.dismiss(str(path))
            else:
                self.notify(f"Path does not exist: {val}", severity="error")
        else:
            self.dismiss(None)


class ManualPeerDialog(ModalScreen[Optional[str]]):
    """Dialog to manually specify a target IP address."""

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog-window"):
            yield Label("🌐 Direct IP Target", classes="dialog-title")
            yield Label("Enter the target IP address:")
            yield Input(id="ip-input", placeholder="e.g. 192.168.137.1")
            with Horizontal(classes="dialog-buttons"):
                yield Button("Cancel", id="btn-cancel", classes="-danger")
                yield Button("Select IP", id="btn-select", classes="-primary")

    def on_mount(self) -> None:
        self.query_one("#ip-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._submit()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-select":
            self._submit()
        else:
            self.dismiss(None)

    def _submit(self) -> None:
        val = self.query_one("#ip-input", Input).value.strip()
        if val:
            self.dismiss(val)
        else:
            self.dismiss(None)


class SendSnippetDialog(ModalScreen[Optional[str]]):
    """Dialog to enter text or clipboard snippet to send."""

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog-window"):
            yield Label("📋 Send Text / Clipboard Snippet", classes="dialog-title")
            yield Label("Enter text or paste from clipboard:")
            yield Input(id="snippet-input", placeholder="Type message or paste URL/text...")
            with Horizontal(classes="dialog-buttons"):
                yield Button("Cancel", id="btn-cancel", classes="-danger")
                yield Button("Send Snippet", id="btn-send-snip", classes="-primary")

    def on_mount(self) -> None:
        self.query_one("#snippet-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._submit()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-send-snip":
            self._submit()
        else:
            self.dismiss(None)

    def _submit(self) -> None:
        val = self.query_one("#snippet-input", Input).value.strip()
        self.dismiss(val if val else None)


class TransferProgressModal(ModalScreen[None]):
    """Live transfer dialog displaying real-time progress bars and speed."""

    def __init__(self, target_label: str, total_bytes: int, total_files: int, parallel_workers: int = 1, on_cancel=None):
        super().__init__()
        self.target_label = target_label
        self.total_bytes = total_bytes
        self.total_files = total_files
        self.parallel_workers = parallel_workers
        self.on_cancel_callback = on_cancel
        self.is_finished = False

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog-window"):
            yield Label(f"⚡ Streaming to: {self.target_label}", classes="dialog-title", id="transfer-title")
            stream_label = f" ({self.parallel_workers} parallel streams)" if self.parallel_workers > 1 else ""
            yield Label(f"Total: {self.total_files} files ({format_size(self.total_bytes)}){stream_label}", classes="stat-row", id="stat-total")
            yield Label("Current File: Preparing...", classes="stat-row", id="stat-current-file")

            yield ProgressBar(total=100, show_eta=True, id="overall-bar")

            with Horizontal(classes="stat-row"):
                yield Label("Speed: 0.00 MB/s", id="stat-speed")
                yield Label(" | Transferred: 0 B", id="stat-transferred")

            with Horizontal(classes="dialog-buttons"):
                yield Button("Cancel", id="btn-transfer-cancel", classes="-danger")

    def update_progress(
        self,
        percent: float,
        current_file: str,
        transferred_bytes: int,
        speed_mb: float,
        completed_files: int,
    ) -> None:
        """Update UI elements with live transmission statistics."""
        try:
            bar = self.query_one("#overall-bar", ProgressBar)
            bar.progress = percent

            self.query_one("#stat-current-file", Label).update(f"Current File: {current_file}")
            self.query_one("#stat-speed", Label).update(f"Speed: {speed_mb:.2f} MB/s")
            self.query_one("#stat-transferred", Label).update(
                f" | Transferred: {format_size(transferred_bytes)} ({completed_files}/{self.total_files})"
            )
        except Exception:
            pass

    def mark_completed(self, success: bool, message: str) -> None:
        """Called when transfer finishes."""
        self.is_finished = True
        try:
            bar = self.query_one("#overall-bar", ProgressBar)
            bar.progress = 100.0 if success else bar.progress

            title = self.query_one("#transfer-title", Label)
            title.update("✓ Transfer Completed!" if success else "✗ Transfer Finished with Errors")

            btn = self.query_one("#btn-transfer-cancel", Button)
            btn.label = "Close"
            btn.variant = "primary"
            btn.focus()
        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if self.is_finished:
            self.dismiss(None)
        else:
            if self.on_cancel_callback:
                self.on_cancel_callback()
            self.dismiss(None)


class HelpDialog(ModalScreen[None]):
    """Keyboard shortcuts and help dialog."""

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog-window"):
            yield Label("ℹ RDR-Transit Quick Help", classes="dialog-title")
            yield Static(
                "[bold cyan]Navigation & Controls:[/bold cyan]\n"
                " • [bold yellow]Tab / Shift+Tab[/bold yellow]: Cycle through panels and buttons\n"
                " • [bold yellow]↑ / ↓ Arrow Keys[/bold yellow]: Navigate peer list and staging queue\n"
                " • [bold yellow]Enter / Space[/bold yellow]: Activate selected button or row\n\n"
                "[bold cyan]Quick Keys:[/bold cyan]\n"
                " • [bold green]d[/bold green]: Refresh peer discovery scan\n"
                " • [bold green]a[/bold green]: Add file or folder to send queue\n"
                " • [bold green]c[/bold green]: Clear send queue\n"
                " • [bold green]s[/bold green]: Send staged items to selected peer\n"
                " • [bold green]r[/bold green]: Toggle receiver server on/off\n"
                " • [bold green]?[/bold green]: Show this help modal\n"
                " • [bold red]q[/bold red]: Quit application\n"
            )
            with Horizontal(classes="dialog-buttons"):
                yield Button("Close", id="btn-close-help", classes="-primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(None)
