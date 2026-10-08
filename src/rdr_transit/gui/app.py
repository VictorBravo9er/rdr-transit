"""
Responsive, cross-platform Desktop GUI for RDR-Transit built with Tkinter / ttk.
Zero external dependencies, multi-threaded transfer and discovery, thread-safe UI updates.
"""

from dataclasses import dataclass
import logging
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Dict, List, Optional

from rdr_transit import __version__
from rdr_transit.config import (
    DEFAULT_BROADCAST_PORT,
    DEFAULT_DOWNLOAD_DIR,
    DEFAULT_TRANSFER_PORT,
    HOSTNAME,
    SYSTEM_OS,
)
from rdr_transit.discovery import DiscoveredPeer, PeerDiscoveryService, send_beacon
from rdr_transit.settings import AppConfig, load_config, save_config
from rdr_transit.transfer.receiver import ReceiverServer
from rdr_transit.transfer.sender import BatchSender, TransferStats, send_text_snippet
from rdr_transit.utils.filesystem import collect_target_files, format_size
from rdr_transit.utils.network import get_primary_ip

logger = logging.getLogger(__name__)


class RDRTransitGUI:
    """Main Application GUI window."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(f"RDR Transit (⚡) v{__version__}")
        self.root.geometry("820x640")
        self.root.minsize(720, 520)

        # Config state
        self.cfg: AppConfig = load_config()
        self.local_ip: str = get_primary_ip()
        self.staged_paths: List[Path] = []
        self.discovered_peers: Dict[str, DiscoveredPeer] = {}
        self.active_sender: Optional[BatchSender] = None

        # Thread-safe event queue
        self.event_queue: queue.Queue = queue.Queue()
        self._check_queue_job = self.root.after(100, self._process_event_queue)

        # Style configuration
        self._setup_styles()

        # Build UI layout
        self._build_header()
        self._build_notebook()
        self._build_statusbar()

        # Discovery & Receiver services
        self.discovery_service: Optional[PeerDiscoveryService] = None
        self.receiver_server: Optional[ReceiverServer] = None

        self._start_discovery()
        self._start_receiver()

        # Clean exit on close
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _setup_styles(self) -> None:
        style = ttk.Style()
        # Use clam or default theme for clean look
        themes = style.theme_names()
        if "clam" in themes:
            style.theme_use("clam")

        # Custom element styles
        style.configure("Header.TFrame", background="#1e222d")
        style.configure("HeaderTitle.TLabel", font=("Helvetica", 14, "bold"), foreground="#00e5ff", background="#1e222d")
        style.configure("HeaderSub.TLabel", font=("Helvetica", 9), foreground="#b0bec5", background="#1e222d")
        style.configure("StatusPill.TLabel", font=("Helvetica", 9, "bold"), foreground="#00e676", background="#1e222d")
        style.configure("Action.TButton", font=("Helvetica", 10, "bold"))
        style.configure("Treeview.Heading", font=("Helvetica", 9, "bold"))

    def _build_header(self) -> None:
        header = ttk.Frame(self.root, style="Header.TFrame", padding=(15, 10))
        header.pack(fill=tk.X, side=tk.TOP)

        left_box = ttk.Frame(header, style="Header.TFrame")
        left_box.pack(side=tk.LEFT, fill=tk.Y)

        title = ttk.Label(left_box, text=f"⚡ RDR Transit  v{__version__}", style="HeaderTitle.TLabel")
        title.pack(anchor=tk.W)

        sub = ttk.Label(
            left_box,
            text=f"Device: {HOSTNAME} ({SYSTEM_OS})  |  Local IP: {self.local_ip}:{self.cfg.transfer_port}",
            style="HeaderSub.TLabel",
        )
        sub.pack(anchor=tk.W, pady=(2, 0))

        right_box = ttk.Frame(header, style="Header.TFrame")
        right_box.pack(side=tk.RIGHT, fill=tk.Y)

        self.recv_status_label = ttk.Label(right_box, text="● Receiver Active", style="StatusPill.TLabel")
        self.recv_status_label.pack(side=tk.LEFT, padx=(0, 10))

        self.recv_toggle_btn = ttk.Button(right_box, text="Stop Receiver", command=self._toggle_receiver)
        self.recv_toggle_btn.pack(side=tk.LEFT)

    def _build_notebook(self) -> None:
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=8)

        # Tab 1: Send Files
        self.tab_send = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.tab_send, text=" 🚀 Send Files ")
        self._build_send_tab()

        # Tab 2: Discovered Peers
        self.tab_peers = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.tab_peers, text=" 📡 Discovered Peers ")
        self._build_peers_tab()

        # Tab 3: Text & Clipboard Snippets
        self.tab_snippet = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.tab_snippet, text=" 📋 Text Snippet ")
        self._build_snippet_tab()

        # Tab 4: History & Logs
        self.tab_logs = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.tab_logs, text=" 📥 Activity & Logs ")
        self._build_logs_tab()

        # Tab 5: Settings
        self.tab_settings = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.tab_settings, text=" ⚙️ Settings ")
        self._build_settings_tab()

    def _build_send_tab(self) -> None:
        # Target Peer selection box
        target_frame = ttk.LabelFrame(self.tab_send, text="Target Peer", padding=10)
        target_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(target_frame, text="Select Peer:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        self.peer_combo_var = tk.StringVar()
        self.peer_combo = ttk.Combobox(target_frame, textvariable=self.peer_combo_var, state="readonly", width=36)
        self.peer_combo.grid(row=0, column=1, sticky=tk.W, padx=5, pady=2)
        self.peer_combo.bind("<<ComboboxSelected>>", self._on_peer_combobox_changed)

        ttk.Label(target_frame, text="Direct IP / Host:").grid(row=0, column=2, sticky=tk.W, padx=(15, 5), pady=2)
        self.direct_ip_var = tk.StringVar()
        self.direct_ip_entry = ttk.Entry(target_frame, textvariable=self.direct_ip_var, width=18)
        self.direct_ip_entry.grid(row=0, column=3, sticky=tk.W, padx=5, pady=2)

        refresh_btn = ttk.Button(target_frame, text="Scan Peers", command=self._trigger_peer_scan)
        refresh_btn.grid(row=0, column=4, padx=(10, 5), pady=2)

        # Staged Files list
        files_frame = ttk.LabelFrame(self.tab_send, text="Staged Files & Folders", padding=10)
        files_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        btn_row = ttk.Frame(files_frame)
        btn_row.pack(fill=tk.X, pady=(0, 6))

        add_files_btn = ttk.Button(btn_row, text="+ Add Files...", command=self._add_files)
        add_files_btn.pack(side=tk.LEFT, padx=(0, 6))

        add_dir_btn = ttk.Button(btn_row, text="+ Add Folder...", command=self._add_directory)
        add_dir_btn.pack(side=tk.LEFT, padx=(0, 6))

        remove_btn = ttk.Button(btn_row, text="Remove Selected", command=self._remove_staged)
        remove_btn.pack(side=tk.LEFT, padx=(0, 6))

        clear_btn = ttk.Button(btn_row, text="Clear All", command=self._clear_staged)
        clear_btn.pack(side=tk.LEFT)

        self.files_summary_label = ttk.Label(btn_row, text="0 items (0 B)")
        self.files_summary_label.pack(side=tk.RIGHT)

        # Listbox for staged items
        list_container = ttk.Frame(files_frame)
        list_container.pack(fill=tk.BOTH, expand=True)

        self.staged_tree = ttk.Treeview(list_container, columns=("path", "size"), show="headings", height=6)
        self.staged_tree.heading("path", text="Item Path")
        self.staged_tree.heading("size", text="Size")
        self.staged_tree.column("path", width=500, stretch=True)
        self.staged_tree.column("size", width=100, anchor=tk.E)

        staged_scroll = ttk.Scrollbar(list_container, orient=tk.VERTICAL, command=self.staged_tree.yview)
        self.staged_tree.configure(yscrollcommand=staged_scroll.set)

        self.staged_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        staged_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Transfer Control & Progress
        progress_frame = ttk.LabelFrame(self.tab_send, text="Transfer Progress", padding=10)
        progress_frame.pack(fill=tk.X)

        self.send_progress_bar = ttk.Progressbar(progress_frame, mode="determinate")
        self.send_progress_bar.pack(fill=tk.X, pady=(2, 6))

        prog_info_row = ttk.Frame(progress_frame)
        prog_info_row.pack(fill=tk.X)

        self.send_status_label = ttk.Label(prog_info_row, text="Idle - ready to transfer")
        self.send_status_label.pack(side=tk.LEFT)

        self.send_speed_label = ttk.Label(prog_info_row, text="")
        self.send_speed_label.pack(side=tk.RIGHT)

        action_row = ttk.Frame(progress_frame)
        action_row.pack(fill=tk.X, pady=(8, 0))

        self.send_action_btn = ttk.Button(
            action_row, text="⚡ Send All to Peer", style="Action.TButton", command=self._start_send
        )
        self.send_action_btn.pack(side=tk.RIGHT, padx=(6, 0))

        self.cancel_send_btn = ttk.Button(
            action_row, text="Cancel Transfer", command=self._cancel_send, state=tk.DISABLED
        )
        self.cancel_send_btn.pack(side=tk.RIGHT)

    def _build_peers_tab(self) -> None:
        top_row = ttk.Frame(self.tab_peers)
        top_row.pack(fill=tk.X, pady=(0, 8))

        scan_btn = ttk.Button(top_row, text="🔄 Discover Now", command=self._trigger_peer_scan)
        scan_btn.pack(side=tk.LEFT, padx=(0, 8))

        quick_send_btn = ttk.Button(top_row, text="🚀 Send Files to Selected", command=self._quick_send_selected_peer)
        quick_send_btn.pack(side=tk.LEFT, padx=(0, 8))

        quick_snip_btn = ttk.Button(top_row, text="📋 Send Snippet to Selected", command=self._quick_snip_selected_peer)
        quick_snip_btn.pack(side=tk.LEFT)

        self.peer_count_label = ttk.Label(top_row, text="Peers: 0")
        self.peer_count_label.pack(side=tk.RIGHT)

        # Peers tree
        tree_container = ttk.Frame(self.tab_peers)
        tree_container.pack(fill=tk.BOTH, expand=True)

        cols = ("name", "os", "ip", "port", "status")
        self.peers_tree = ttk.Treeview(tree_container, columns=cols, show="headings")
        self.peers_tree.heading("name", text="Device Name")
        self.peers_tree.heading("os", text="OS")
        self.peers_tree.heading("ip", text="IP Address")
        self.peers_tree.heading("port", text="Port")
        self.peers_tree.heading("status", text="Status")

        self.peers_tree.column("name", width=220)
        self.peers_tree.column("os", width=100, anchor=tk.CENTER)
        self.peers_tree.column("ip", width=160, anchor=tk.CENTER)
        self.peers_tree.column("port", width=80, anchor=tk.CENTER)
        self.peers_tree.column("status", width=100, anchor=tk.CENTER)

        peers_scroll = ttk.Scrollbar(tree_container, orient=tk.VERTICAL, command=self.peers_tree.yview)
        self.peers_tree.configure(yscrollcommand=peers_scroll.set)

        self.peers_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        peers_scroll.pack(side=tk.RIGHT, fill=tk.Y)

    def _build_snippet_tab(self) -> None:
        target_row = ttk.Frame(self.tab_snippet)
        target_row.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(target_row, text="Destination IP / Host:").pack(side=tk.LEFT, padx=(0, 8))
        self.snippet_target_var = tk.StringVar()
        snippet_target_entry = ttk.Entry(target_row, textvariable=self.snippet_target_var, width=24)
        snippet_target_entry.pack(side=tk.LEFT, padx=(0, 10))

        paste_btn = ttk.Button(target_row, text="Paste from Clipboard", command=self._paste_clipboard_to_snippet)
        paste_btn.pack(side=tk.LEFT, padx=(0, 6))

        send_snip_btn = ttk.Button(target_row, text="⚡ Send Snippet", style="Action.TButton", command=self._send_snippet)
        send_snip_btn.pack(side=tk.RIGHT)

        ttk.Label(self.tab_snippet, text="Text / Code Snippet:").pack(anchor=tk.W, pady=(0, 4))
        self.snippet_text = tk.Text(self.tab_snippet, wrap=tk.WORD, height=14, font=("Courier", 10))
        self.snippet_text.pack(fill=tk.BOTH, expand=True)

    def _build_logs_tab(self) -> None:
        bar = ttk.Frame(self.tab_logs)
        bar.pack(fill=tk.X, pady=(0, 8))

        open_folder_btn = ttk.Button(bar, text="📁 Open Downloads Folder", command=self._open_download_dir)
        open_folder_btn.pack(side=tk.LEFT, padx=(0, 8))

        clear_logs_btn = ttk.Button(bar, text="Clear Log", command=self._clear_logs)
        clear_logs_btn.pack(side=tk.LEFT)

        self.activity_log = tk.Text(self.tab_logs, wrap=tk.WORD, state=tk.DISABLED, bg="#11141a", fg="#e0e0e0", font=("Courier", 9))
        self.activity_log.pack(fill=tk.BOTH, expand=True)

    def _build_settings_tab(self) -> None:
        grid = ttk.LabelFrame(self.tab_settings, text="Configuration & Preferences", padding=15)
        grid.pack(fill=tk.BOTH, expand=True)

        row = 0
        ttk.Label(grid, text="Download Directory:").grid(row=row, column=0, sticky=tk.W, pady=6)
        self.setting_dl_dir_var = tk.StringVar(value=self.cfg.download_dir)
        dl_entry = ttk.Entry(grid, textvariable=self.setting_dl_dir_var, width=44)
        dl_entry.grid(row=row, column=1, sticky=tk.W, padx=8, pady=6)
        browse_btn = ttk.Button(grid, text="Browse...", command=self._browse_download_dir)
        browse_btn.grid(row=row, column=2, sticky=tk.W, pady=6)

        row += 1
        ttk.Label(grid, text="Transfer Port (TCP):").grid(row=row, column=0, sticky=tk.W, pady=6)
        self.setting_transfer_port_var = tk.StringVar(value=str(self.cfg.transfer_port))
        tp_entry = ttk.Entry(grid, textvariable=self.setting_transfer_port_var, width=12)
        tp_entry.grid(row=row, column=1, sticky=tk.W, padx=8, pady=6)

        row += 1
        ttk.Label(grid, text="Discovery Port (UDP):").grid(row=row, column=0, sticky=tk.W, pady=6)
        self.setting_bcast_port_var = tk.StringVar(value=str(self.cfg.broadcast_port))
        bp_entry = ttk.Entry(grid, textvariable=self.setting_bcast_port_var, width=12)
        bp_entry.grid(row=row, column=1, sticky=tk.W, padx=8, pady=6)

        row += 1
        ttk.Label(grid, text="Parallel Streams:").grid(row=row, column=0, sticky=tk.W, pady=6)
        self.setting_parallel_var = tk.StringVar(value=str(self.cfg.default_parallel))
        par_entry = ttk.Spinbox(grid, from_=1, to=16, textvariable=self.setting_parallel_var, width=6)
        par_entry.grid(row=row, column=1, sticky=tk.W, padx=8, pady=6)

        row += 1
        ttk.Label(grid, text="Beacon Interval (sec):").grid(row=row, column=0, sticky=tk.W, pady=6)
        self.setting_interval_var = tk.StringVar(value=str(self.cfg.beacon_interval))
        int_entry = ttk.Spinbox(grid, from_=1.0, to=30.0, increment=1.0, textvariable=self.setting_interval_var, width=6)
        int_entry.grid(row=row, column=1, sticky=tk.W, padx=8, pady=6)

        row += 1
        save_btn = ttk.Button(grid, text="💾 Save Preferences", style="Action.TButton", command=self._save_settings)
        save_btn.grid(row=row, column=1, sticky=tk.W, padx=8, pady=16)

    def _build_statusbar(self) -> None:
        self.statusbar = ttk.Label(self.root, text="Ready", relief=tk.SUNKEN, anchor=tk.W, padding=(6, 3))
        self.statusbar.pack(side=tk.BOTTOM, fill=tk.X)

    # --- Discovery & Receiver Integration ---

    def _start_discovery(self) -> None:
        try:
            self.discovery_service = PeerDiscoveryService(
                broadcast_port=self.cfg.broadcast_port,
                beacon_interval=self.cfg.beacon_interval,
                on_peer_updated=self._on_peer_discovered_callback,
            )
            self.discovery_service.start()
            self._log(f"Discovery service running on UDP {self.cfg.broadcast_port}")
        except Exception as e:
            self._log(f"Discovery error: {e}")

    def _start_receiver(self) -> None:
        try:
            dest_dir = Path(self.cfg.download_dir).expanduser().resolve()
            dest_dir.mkdir(parents=True, exist_ok=True)

            self.receiver_server = ReceiverServer(
                download_dir=dest_dir,
                port=self.cfg.transfer_port,
                bind_host="0.0.0.0",
                allow_skip=True,
                verify_checksum=True,
                on_file_start=self._on_recv_file_start,
                on_file_complete=self._on_recv_file_complete,
                on_snippet_received=self._on_recv_snippet,
            )
            self.receiver_server.start()
            self.recv_status_label.config(text="● Receiver Active", foreground="#00e676")
            self.recv_toggle_btn.config(text="Stop Receiver")
            self._log(f"Receiver listening on TCP {self.cfg.transfer_port} -> {dest_dir}")
        except Exception as e:
            self._log(f"Receiver start failed: {e}")
            self.recv_status_label.config(text="● Receiver Inactive", foreground="#ff5252")
            self.recv_toggle_btn.config(text="Start Receiver")

    def _toggle_receiver(self) -> None:
        if self.receiver_server and self.receiver_server.is_running:
            self.receiver_server.stop()
            self.recv_status_label.config(text="● Receiver Stopped", foreground="#ff5252")
            self.recv_toggle_btn.config(text="Start Receiver")
            self._log("Receiver daemon stopped.")
        else:
            self._start_receiver()

    def _on_peer_discovered_callback(self, peer: DiscoveredPeer) -> None:
        # Push to event queue for thread-safe UI update
        self.event_queue.put(("peer_updated", peer))

    def _on_recv_file_start(self, peer_ip: str, fname: str, folder: str, fsize: int) -> None:
        path_desc = f"{folder}/{fname}" if folder else fname
        self.event_queue.put(("log", f"📥 Receiving from {peer_ip}: {path_desc} ({format_size(fsize)})"))

    def _on_recv_file_complete(self, peer_ip: str, fname: str, dest: Path, ok: bool, err: str) -> None:
        if ok:
            self.event_queue.put(("log", f"✓ Saved: {dest}"))
        else:
            self.event_queue.put(("log", f"✗ Reception failed: {fname} ({err})"))

    def _on_recv_snippet(self, peer_ip: str, text: str, saved_path: str) -> None:
        preview = text[:60] + ("..." if len(text) > 60 else "")
        self.event_queue.put(("log", f"📋 Snippet from {peer_ip}: {preview} (saved {saved_path})"))

    def _process_event_queue(self) -> None:
        """Poll and apply thread-safe UI updates."""
        try:
            while True:
                msg_type, data = self.event_queue.get_nowait()
                if msg_type == "peer_updated":
                    peer: DiscoveredPeer = data
                    self.discovered_peers[peer.ip] = peer
                    self._refresh_peers_view()
                elif msg_type == "log":
                    self._log(str(data))
                elif msg_type == "send_progress":
                    stats: TransferStats = data
                    self._update_send_progress_ui(stats)
                elif msg_type == "send_completed":
                    stats = data
                    self._on_send_finished(stats)
        except queue.Empty:
            pass
        finally:
            self._check_queue_job = self.root.after(100, self._process_event_queue)

    def _refresh_peers_view(self) -> None:
        # Update peers table
        selected_iid = self.peers_tree.selection()
        selected_ip = None
        if selected_iid:
            selected_ip = self.peers_tree.item(selected_iid[0], "values")[2]

        self.peers_tree.delete(*self.peers_tree.get_children())
        peer_list = sorted(self.discovered_peers.values(), key=lambda p: p.name)

        combo_values = []
        for p in peer_list:
            status_text = "Online" if p.is_alive else "Away"
            item_id = self.peers_tree.insert("", tk.END, values=(p.name, p.os_badge, p.ip, p.port, status_text))
            if p.ip == selected_ip:
                self.peers_tree.selection_set(item_id)
            combo_values.append(f"{p.name} ({p.ip})")

        self.peer_count_label.config(text=f"Peers: {len(peer_list)}")
        self.peer_combo["values"] = combo_values
        if combo_values and not self.peer_combo_var.get():
            self.peer_combo_var.set(combo_values[0])
            self.direct_ip_var.set(peer_list[0].ip)

    def _on_peer_combobox_changed(self, event=None) -> None:
        val = self.peer_combo_var.get()
        if "(" in val and ")" in val:
            ip = val.split("(")[-1].rstrip(")")
            self.direct_ip_var.set(ip)
            self.snippet_target_var.set(ip)

    def _trigger_peer_scan(self) -> None:
        if self.discovery_service:
            self.discovery_service.trigger_beacon()
        send_beacon(broadcast_port=self.cfg.broadcast_port)
        self.statusbar.config(text="Broadcast beacon sent. Scanning peers...")

    def _quick_send_selected_peer(self) -> None:
        sel = self.peers_tree.selection()
        if not sel:
            messagebox.showinfo("Select Peer", "Please select a peer from the list first.")
            return
        vals = self.peers_tree.item(sel[0], "values")
        peer_ip = vals[2]
        self.direct_ip_var.set(peer_ip)
        self.notebook.select(self.tab_send)

    def _quick_snip_selected_peer(self) -> None:
        sel = self.peers_tree.selection()
        if not sel:
            messagebox.showinfo("Select Peer", "Please select a peer from the list first.")
            return
        vals = self.peers_tree.item(sel[0], "values")
        peer_ip = vals[2]
        self.snippet_target_var.set(peer_ip)
        self.notebook.select(self.tab_snippet)

    # --- File Staging & Sending ---

    def _add_files(self) -> None:
        filenames = filedialog.askopenfilenames(title="Select files to send")
        if filenames:
            for f in filenames:
                p = Path(f).resolve()
                if p not in self.staged_paths:
                    self.staged_paths.append(p)
            self._refresh_staged_view()

    def _add_directory(self) -> None:
        dirname = filedialog.askdirectory(title="Select directory to send")
        if dirname:
            p = Path(dirname).resolve()
            if p not in self.staged_paths:
                self.staged_paths.append(p)
            self._refresh_staged_view()

    def _remove_staged(self) -> None:
        selected = self.staged_tree.selection()
        if not selected:
            return
        for item_id in selected:
            idx = self.staged_tree.index(item_id)
            if 0 <= idx < len(self.staged_paths):
                del self.staged_paths[idx]
        self._refresh_staged_view()

    def _clear_staged(self) -> None:
        self.staged_paths.clear()
        self._refresh_staged_view()

    def _refresh_staged_view(self) -> None:
        self.staged_tree.delete(*self.staged_tree.get_children())
        total_bytes = 0
        file_count = 0

        for path in self.staged_paths:
            if path.is_file():
                sz = path.stat().st_size
                total_bytes += sz
                file_count += 1
                self.staged_tree.insert("", tk.END, values=(str(path), format_size(sz)))
            elif path.is_dir():
                items = collect_target_files([path])
                dir_bytes = sum(f.size for f in items)
                total_bytes += dir_bytes
                file_count += len(items)
                self.staged_tree.insert("", tk.END, values=(f"[Folder] {path}", f"{len(items)} files ({format_size(dir_bytes)})"))

        self.files_summary_label.config(text=f"{len(self.staged_paths)} items / {file_count} files ({format_size(total_bytes)})")

    def _start_send(self) -> None:
        target_ip = self.direct_ip_var.get().strip()
        if not target_ip:
            messagebox.showerror("No Target", "Please select or type a target peer IP address.")
            return

        if not self.staged_paths:
            messagebox.showerror("Empty Queue", "Please stage at least one file or folder to send.")
            return

        self.send_action_btn.config(state=tk.DISABLED)
        self.cancel_send_btn.config(state=tk.NORMAL)
        self.send_progress_bar["value"] = 0
        self.send_status_label.config(text=f"Connecting to {target_ip}...")
        self.statusbar.config(text=f"Transferring {len(self.staged_paths)} item(s) to {target_ip}...")

        def _worker():
            try:
                sender = BatchSender(
                    target_ip=target_ip,
                    target_port=self.cfg.transfer_port,
                    parallel_transfers=self.cfg.default_parallel,
                    on_progress=lambda stats: self.event_queue.put(("send_progress", stats)),
                    on_file_complete=lambda name, ok, err: self.event_queue.put(("log", f"Sent: {name} {'✓' if ok else '✗ ' + err}")),
                )
                self.active_sender = sender
                final_stats = sender.send_paths(self.staged_paths)
                self.event_queue.put(("send_completed", final_stats))
            except Exception as e:
                self.event_queue.put(("log", f"Transfer error: {e}"))
                self.event_queue.put(("send_completed", None))

        threading.Thread(target=_worker, daemon=True).start()

    def _cancel_send(self) -> None:
        if self.active_sender:
            self.active_sender.cancel()
            self._log("Cancelling transfer...")
            self.cancel_send_btn.config(state=tk.DISABLED)

    def _update_send_progress_ui(self, stats: TransferStats) -> None:
        pct = (stats.transferred_bytes / max(1, stats.total_bytes)) * 100
        self.send_progress_bar["value"] = min(100, pct)
        speed_str = f"{stats.speed_mb_per_sec:.2f} MB/s"
        file_desc = stats.current_file_name or f"{stats.completed_files}/{stats.total_files} files"
        self.send_status_label.config(text=f"{file_desc} ({pct:.1f}%)")
        self.send_speed_label.config(text=speed_str)

    def _on_send_finished(self, stats: Optional[TransferStats]) -> None:
        self.active_sender = None
        self.send_action_btn.config(state=tk.NORMAL)
        self.cancel_send_btn.config(state=tk.DISABLED)

        if stats:
            self.send_progress_bar["value"] = 100
            summary = (
                f"Transfer finished: {stats.completed_files} ok, {stats.skipped_files} skipped, "
                f"{stats.failed_files} failed in {stats.elapsed_seconds:.1f}s ({stats.speed_mb_per_sec:.2f} MB/s)"
            )
            self.send_status_label.config(text=summary)
            self.statusbar.config(text=summary)
            self._log(summary)
            if stats.failed_files == 0:
                messagebox.showinfo("Transfer Complete", f"Successfully transferred {stats.completed_files} file(s)!")
            else:
                messagebox.showwarning("Transfer Warning", f"Transfer completed with {stats.failed_files} error(s). Check logs.")
        else:
            self.send_status_label.config(text="Transfer failed.")
            self.statusbar.config(text="Transfer failed.")

    # --- Snippet / Clipboard ---

    def _paste_clipboard_to_snippet(self) -> None:
        try:
            clip = self.root.clipboard_get()
            self.snippet_text.delete("1.0", tk.END)
            self.snippet_text.insert(tk.END, clip)
        except Exception as e:
            messagebox.showwarning("Clipboard", f"Could not read clipboard: {e}")

    def _send_snippet(self) -> None:
        target = self.snippet_target_var.get().strip() or self.direct_ip_var.get().strip()
        if not target:
            messagebox.showerror("No Target", "Please specify target IP for snippet.")
            return

        text = self.snippet_text.get("1.0", tk.END).strip()
        if not text:
            messagebox.showerror("Empty Snippet", "Please enter text or code to send.")
            return

        def _worker():
            try:
                ok = send_text_snippet(
                    target_ip=target,
                    text=text,
                    target_port=self.cfg.transfer_port,
                    sender_name=HOSTNAME,
                )
                if ok:
                    self.event_queue.put(("log", f"📋 Snippet ({len(text)} chars) sent to {target}"))
                    self.event_queue.put(("snippet_sent", True))
                else:
                    self.event_queue.put(("log", f"✗ Failed to send snippet to {target}"))
            except Exception as e:
                self.event_queue.put(("log", f"Snippet send error: {e}"))

        threading.Thread(target=_worker, daemon=True).start()
        self.statusbar.config(text=f"Sending snippet to {target}...")

    # --- Logs & Settings ---

    def _log(self, text: str) -> None:
        ts = time.strftime("%H:%M:%S")
        self.activity_log.config(state=tk.NORMAL)
        self.activity_log.insert(tk.END, f"[{ts}] {text}\n")
        self.activity_log.see(tk.END)
        self.activity_log.config(state=tk.DISABLED)

    def _clear_logs(self) -> None:
        self.activity_log.config(state=tk.NORMAL)
        self.activity_log.delete("1.0", tk.END)
        self.activity_log.config(state=tk.DISABLED)

    def _open_download_dir(self) -> None:
        p = Path(self.cfg.download_dir).expanduser().resolve()
        p.mkdir(parents=True, exist_ok=True)
        try:
            if SYSTEM_OS == "Linux":
                subprocess.Popen(["xdg-open", str(p)])
            elif SYSTEM_OS == "Darwin":
                subprocess.Popen(["open", str(p)])
            elif SYSTEM_OS == "Windows":
                os.startfile(str(p))  # type: ignore
        except Exception as e:
            messagebox.showerror("Error", f"Could not open directory: {e}")

    def _browse_download_dir(self) -> None:
        selected = filedialog.askdirectory(initialdir=self.cfg.download_dir, title="Select Download Directory")
        if selected:
            self.setting_dl_dir_var.set(selected)

    def _save_settings(self) -> None:
        try:
            self.cfg.download_dir = self.setting_dl_dir_var.get().strip()
            self.cfg.transfer_port = int(self.setting_transfer_port_var.get().strip())
            self.cfg.broadcast_port = int(self.setting_bcast_port_var.get().strip())
            self.cfg.default_parallel = int(self.setting_parallel_var.get().strip())
            self.cfg.beacon_interval = float(self.setting_interval_var.get().strip())

            save_config(self.cfg)
            messagebox.showinfo("Saved", "Preferences saved successfully!")
            self._log("Settings saved to configuration.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save settings: {e}")

    def on_close(self) -> None:
        """Gracefully shut down background workers on window close."""
        if self._check_queue_job:
            self.root.after_cancel(self._check_queue_job)
        if self.discovery_service:
            self.discovery_service.stop()
        if self.receiver_server:
            self.receiver_server.stop()
        self.root.destroy()


def launch_gui() -> None:
    """Entrypoint function to run the RDR Transit GUI application."""
    root = tk.Tk()
    app = RDRTransitGUI(root)
    root.mainloop()


if __name__ == "__main__":
    launch_gui()
