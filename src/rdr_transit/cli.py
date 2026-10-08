"""
Command-line interface entry points for RDR-Transit.
"""

import argparse
import os
from pathlib import Path
import sys
import time

from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.prompt import Prompt
from rich.table import Table

from rdr_transit import __version__
from rdr_transit.config import (
    DEFAULT_BROADCAST_PORT,
    DEFAULT_DOWNLOAD_DIR,
    DEFAULT_EXCLUDED_DIRS,
    DEFAULT_TRANSFER_PORT,
    HOSTNAME,
)
from rdr_transit.discovery import discover_peers, send_beacon
from rdr_transit.transfer.receiver import ReceiverServer
from rdr_transit.transfer.sender import BatchSender, TransferStats
from rdr_transit.utils.filesystem import collect_target_files, format_size
from rdr_transit.utils.network import get_primary_ip

from rdr_transit.settings import CONFIG_FILE, AppConfig, load_config, save_config
from rdr_transit.transfer.sender import BatchSender, TransferStats, send_text_snippet

console = Console()


def handle_discover(args: argparse.Namespace) -> None:
    """Scan local network and display active peers."""
    cfg = load_config()
    bport = args.broadcast_port or cfg.broadcast_port
    with console.status("[bold cyan]Scanning for peers (UDP 56780)...[/bold cyan]"):
        peers = discover_peers(timeout=args.timeout, broadcast_port=bport)

    if not peers:
        console.print("[yellow]No active peers found on local subnet.[/yellow]")
        return

    table = Table(title="Discovered LAN-Share / RDR-Transit Peers", border_style="cyan")
    table.add_column("#", justify="center", style="bold cyan")
    table.add_column("Device Name", style="bold white")
    table.add_column("OS", style="green")
    table.add_column("IP Address", style="yellow")
    table.add_column("Port", style="dim")

    for idx, peer in enumerate(peers, 1):
        table.add_row(str(idx), peer.name, peer.os_badge, peer.ip, str(peer.port))

    console.print(table)


def handle_receive(args: argparse.Namespace) -> None:
    """Run receiver server to listen for incoming files."""
    cfg = load_config()
    out_dir_str = args.output_dir if args.output_dir != str(DEFAULT_DOWNLOAD_DIR) else cfg.download_dir
    dest_dir = Path(out_dir_str).expanduser().resolve()
    dest_dir.mkdir(parents=True, exist_ok=True)

    my_ip = get_primary_ip()
    port = args.port or cfg.transfer_port

    def on_start(peer_ip: str, fname: str, folder: str, fsize: int) -> None:
        path_desc = f"{folder}/{fname}" if folder else fname
        console.print(f"[cyan]Receiving from [bold]{peer_ip}[/bold]:[/cyan] {path_desc} ({format_size(fsize)})")

    def on_complete(peer_ip: str, fname: str, dest: Path, ok: bool, err: str) -> None:
        if ok:
            console.print(f"[green]✓ Saved:[/green] {dest}")
        else:
            console.print(f"[bold red]✗ Failed {fname} from {peer_ip}:[/bold red] {err}")

    def on_snippet(peer_ip: str, text: str, saved_path: str) -> None:
        preview = text[:80] + ("..." if len(text) > 80 else "")
        console.print(f"[bold magenta]📋 Snippet from {peer_ip}:[/bold magenta] {preview} (saved to {saved_path})")

    server = ReceiverServer(
        download_dir=dest_dir,
        port=port,
        bind_host=args.host,
        allow_skip=not args.no_skip,
        verify_checksum=not args.no_verify,
        on_file_start=on_start,
        on_file_complete=on_complete,
        on_snippet_received=on_snippet,
    )

    panel_content = (
        f"[bold white]Status:[/bold white] [green]Listening for connections[/green]\n"
        f"[bold white]Local IP:[/bold white] [yellow]{my_ip}[/yellow]\n"
        f"[bold white]Port:[/bold white] [cyan]{port}[/cyan] (TCP)\n"
        f"[bold white]Save Location:[/bold white] [magenta]{dest_dir}[/magenta]\n"
        f"[bold white]Incremental Skip:[/bold white] {'[green]Enabled[/green]' if not args.no_skip else '[yellow]Disabled[/yellow]'}\n"
        f"[bold white]Checksum Verification:[/bold white] {'[green]SHA-256[/green]' if not args.no_verify else '[yellow]Off[/yellow]'}\n\n"
        f"[dim]Press Ctrl+C to terminate receiver server.[/dim]"
    )
    console.print(Panel(panel_content, title="[bold green]RDR-Transit Receiver Daemon[/bold green]", border_style="green"))

    server.start()

    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        console.print("\n[yellow]Stopping receiver daemon...[/yellow]")
    finally:
        server.stop()
        console.print("[dim]Receiver stopped.[/dim]")


def handle_snippet(args: argparse.Namespace) -> None:
    """Send text or clipboard snippet to a peer."""
    cfg = load_config()
    target_ip = args.target
    if not target_ip:
        with console.status("[cyan]Looking for network peers...[/cyan]"):
            peers = discover_peers(timeout=2.0)
        if peers:
            target_ip = peers[0].ip
            console.print(f"[green]Auto-selected peer:[/green] {peers[0].name} ({target_ip})")
        else:
            target_ip = Prompt.ask("[yellow]No peers found. Enter target IP manually[/yellow]")

    text_to_send = args.text
    if not text_to_send:
        # Prompt user or read from stdin
        if not sys.stdin.isatty():
            text_to_send = sys.stdin.read()
        else:
            text_to_send = Prompt.ask("[bold green]Enter text snippet to send[/bold green]")

    if not text_to_send.strip():
        console.print("[red]Empty snippet. Aborting.[/red]")
        sys.exit(1)

    port = args.port or cfg.transfer_port
    sender_name = args.name or cfg.device_name

    with console.status(f"[cyan]Sending snippet to {target_ip}:{port}...[/cyan]"):
        ok, err = send_text_snippet(text_to_send, target_ip, transfer_port=port, sender_name=sender_name)

    if ok:
        console.print(f"[bold green]✓ Snippet sent successfully to {target_ip}:{port}![/bold green]")
    else:
        console.print(f"[bold red]✗ Failed to send snippet: {err}[/bold red]")


def handle_config(args: argparse.Namespace) -> None:
    """Display or edit user configuration."""
    cfg = load_config()

    if args.set:
        key, val = args.set
        if hasattr(cfg, key):
            # Type cast
            orig_val = getattr(cfg, key)
            if isinstance(orig_val, int):
                setattr(cfg, key, int(val))
            elif isinstance(orig_val, bool):
                setattr(cfg, key, val.lower() in ("true", "1", "yes"))
            else:
                setattr(cfg, key, val)
            save_config(cfg)
            console.print(f"[green]✓ Config updated:[/green] {key} = {getattr(cfg, key)}")
        else:
            console.print(f"[bold red]Unknown config key:[/bold red] {key}")
        return

    table = Table(title=f"RDR-Transit Configuration ({CONFIG_FILE})", border_style="cyan")
    table.add_column("Setting", style="bold cyan")
    table.add_column("Value", style="bold white")

    table.add_row("device_name", cfg.device_name)
    table.add_row("transfer_port", str(cfg.transfer_port))
    table.add_row("broadcast_port", str(cfg.broadcast_port))
    table.add_row("download_dir", cfg.download_dir)
    table.add_row("default_parallel", str(cfg.default_parallel))
    table.add_row("incremental_sync", str(cfg.incremental_sync))
    table.add_row("verify_checksum", str(cfg.verify_checksum))

    console.print(table)


def handle_send(args: argparse.Namespace) -> None:
    """Send files or directories via CLI."""
    cfg = load_config()
    excluded = set(DEFAULT_EXCLUDED_DIRS)
    if args.include_venv:
        excluded.discard(".venv")
        excluded.discard("venv")

    with console.status("[cyan]Collecting files to transfer...[/cyan]"):
        files = collect_target_files(args.paths, excluded_dirs=excluded)

    if not files:
        console.print("[bold red]No valid files found in given paths.[/bold red]")
        sys.exit(1)

    target_ip = args.target
    # Check if target is an alias
    if target_ip and target_ip in cfg.peer_aliases:
        target_ip = cfg.peer_aliases[target_ip]

    bport = args.broadcast_port or cfg.broadcast_port
    port = args.port or cfg.transfer_port
    parallel_workers = args.parallel if args.parallel is not None else cfg.default_parallel
    include_checksum = args.checksum if args.checksum is not None else cfg.verify_checksum

    if not target_ip:
        with console.status("[cyan]Looking for network peers...[/cyan]"):
            peers = discover_peers(timeout=args.timeout, broadcast_port=bport)
        if peers:
            if len(peers) == 1:
                target_ip = peers[0].ip
                console.print(f"[green]Auto-selected sole peer:[/green] {peers[0].name} ({target_ip})")
            else:
                table = Table(title="Select Destination Peer", border_style="cyan")
                table.add_column("#", justify="center", style="cyan")
                table.add_column("Device Name", style="bold white")
                table.add_column("OS", style="green")
                table.add_column("IP", style="yellow")
                for idx, p in enumerate(peers, 1):
                    table.add_row(str(idx), p.name, p.os_badge, p.ip)
                console.print(table)
                choice = Prompt.ask("Choose peer number or enter custom IP", default="1")
                if choice.isdigit() and 1 <= int(choice) <= len(peers):
                    target_ip = peers[int(choice) - 1].ip
                else:
                    target_ip = choice.strip()
        else:
            target_ip = Prompt.ask("[yellow]No peers found. Enter target IP manually[/yellow]")

    if not target_ip:
        console.print("[red]No target IP specified. Aborting.[/red]")
        sys.exit(1)

    # Announce device prior to sending unless disabled
    sender_name = args.name or cfg.device_name
    if not args.no_announce:
        send_beacon(target_ip=target_ip, broadcast_port=bport, name=sender_name)
        time.sleep(0.15)

    total_bytes = sum(os.path.getsize(p[0]) for p in files)
    total_files = len(files)

    if args.quiet:
        batch = BatchSender(
            files_to_send=files,
            receiver_ip=target_ip,
            transfer_port=port,
            max_workers=parallel_workers,
            include_checksum=include_checksum,
        )
        stats = batch.run()
        print(f"Transferred {stats.completed_files}/{total_files} in {stats.elapsed_seconds:.2f}s ({stats.speed_mb_per_sec:.2f} MB/s, {stats.skipped_files} skipped)")
        return

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]{task.description}"),
        BarColumn(bar_width=40),
        TaskProgressColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
        console=console,
    )

    with progress:
        overall_task = progress.add_task("[bold magenta]Overall Progress", total=total_bytes)
        file_task = progress.add_task("[bold green]Current File", total=0)

        def on_start(idx: int, fname: str, fsize: int) -> None:
            short = ("..." + fname[-35:]) if len(fname) > 38 else fname
            par_label = f" [cyan]({parallel_workers} parallel)[/cyan]" if parallel_workers > 1 else ""
            progress.update(
                file_task,
                description=f"[bold green]File {idx}/{total_files}:[/bold green] [white]{short}[/white]{par_label}",
                completed=0,
                total=fsize,
            )

        def on_chunk(chunk_len: int, file_done: int, total_done: int) -> None:
            progress.update(file_task, advance=chunk_len)
            progress.update(overall_task, advance=chunk_len)

        batch = BatchSender(
            files_to_send=files,
            receiver_ip=target_ip,
            transfer_port=port,
            max_workers=parallel_workers,
            include_checksum=include_checksum,
            on_file_start=on_start,
            on_chunk=on_chunk,
        )
        stats = batch.run()

    # Summary Panel
    summary_table = Table.grid(padding=(0, 2))
    summary_table.add_column(style="bold")
    summary_table.add_column(style="cyan")
    status_label = "[bold green]Completed[/bold green]" if stats.failed_files == 0 else "[bold red]Completed with errors[/bold red]"
    summary_table.add_row("Status:", status_label)
    summary_table.add_row("Target:", f"{target_ip}:{port}")
    summary_table.add_row("Parallel Streams:", str(parallel_workers))
    summary_table.add_row("Checksum (SHA-256):", "Enabled" if include_checksum else "Disabled")
    summary_table.add_row("Transferred:", f"{stats.completed_files} / {total_files} files")
    if stats.skipped_files > 0:
        summary_table.add_row("Skipped (Identical):", f"[yellow]{stats.skipped_files} files[/yellow]")
    summary_table.add_row("Total Data:", format_size(stats.transferred_bytes))
    summary_table.add_row("Duration:", f"{stats.elapsed_seconds:.2f} seconds")
    summary_table.add_row("Speed:", f"{stats.speed_mb_per_sec:.2f} MB/s")

    console.print(Panel(summary_table, title="[bold green]Transfer Summary[/bold green]", border_style="green" if stats.failed_files == 0 else "red"))


def handle_tui(args: argparse.Namespace) -> None:
    """Launch full-screen Textual TUI interface."""
    from rdr_transit.tui.app import RDRTransitApp
    app = RDRTransitApp()
    app.run()


def build_parser() -> argparse.ArgumentParser:
    """Construct argument parser for CLI commands."""
    parser = argparse.ArgumentParser(
        prog="rdr-transit",
        description="High-speed, OS-agnostic peer-to-peer file transfer tool.",
    )
    parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {__version__}")

    subparsers = parser.add_subparsers(dest="subcommand", help="Available subcommands")

    # TUI subcommand
    p_tui = subparsers.add_parser("tui", help="Launch interactive nmtui-inspired Terminal UI")

    # Send subcommand
    p_send = subparsers.add_parser("send", help="Send files or directories to a peer")
    p_send.add_argument("paths", nargs="+", help="Files or directories to send")
    p_send.add_argument("-t", "--target", help="Target peer IP address")
    p_send.add_argument("-p", "--port", type=int, help="Transfer TCP port")
    p_send.add_argument("-j", "--parallel", type=int, help="Number of concurrent parallel file transfer streams")
    p_send.add_argument("-b", "--broadcast-port", type=int, help="Discovery UDP port")
    p_send.add_argument("--timeout", type=float, default=2.0, help="Peer discovery timeout in seconds")
    p_send.add_argument("--name", help="Device name announced to peers")
    p_send.add_argument("--checksum", action="store_true", default=None, help="Compute and verify SHA-256 checksums")
    p_send.add_argument("--no-checksum", dest="checksum", action="store_false", help="Disable SHA-256 checksums")
    p_send.add_argument("--include-venv", action="store_true", help="Include virtual environment folders")
    p_send.add_argument("--no-announce", action="store_true", help="Skip sending UDP announcement beacon")
    p_send.add_argument("-q", "--quiet", action="store_true", help="Minimal text output mode")

    # Receive subcommand
    p_rec = subparsers.add_parser("receive", help="Start receiver daemon to accept incoming files")
    p_rec.add_argument("-p", "--port", type=int, help="Listening TCP port")
    p_rec.add_argument("-d", "--output-dir", default=str(DEFAULT_DOWNLOAD_DIR), help="Directory to save received files")
    p_rec.add_argument("--host", default="0.0.0.0", help="Binding host address")
    p_rec.add_argument("--no-skip", action="store_true", help="Disable incremental skip (force overwrite existing files)")
    p_rec.add_argument("--no-verify", action="store_true", help="Disable SHA-256 checksum validation")

    # Snippet subcommand
    p_snip = subparsers.add_parser("snippet", aliases=["clip"], help="Send text or clipboard snippet to a peer")
    p_snip.add_argument("text", nargs="?", default="", help="Text snippet to send (reads stdin if omitted)")
    p_snip.add_argument("-t", "--target", help="Target peer IP address")
    p_snip.add_argument("-p", "--port", type=int, help="Transfer TCP port")
    p_snip.add_argument("--name", help="Sender name announced to receiver")

    # Config subcommand
    p_cfg = subparsers.add_parser("config", help="View or modify user configuration")
    p_cfg.add_argument("--set", nargs=2, metavar=("KEY", "VALUE"), help="Update config setting (e.g. --set default_parallel 8)")

    # Discover subcommand
    p_disc = subparsers.add_parser("discover", help="Scan local network for active peers")
    p_disc.add_argument("--timeout", type=float, default=2.0, help="Scan duration in seconds")
    p_disc.add_argument("-b", "--broadcast-port", type=int, help="Discovery UDP port")

    return parser


def main() -> None:
    """Main CLI entry point."""
    parser = build_parser()
    args = parser.parse_args()

    if args.subcommand == "send":
        handle_send(args)
    elif args.subcommand == "receive":
        handle_receive(args)
    elif args.subcommand in ("snippet", "clip"):
        handle_snippet(args)
    elif args.subcommand == "config":
        handle_config(args)
    elif args.subcommand == "discover":
        handle_discover(args)
    elif args.subcommand == "tui" or args.subcommand is None:
        # Default with no arguments is to launch the interactive TUI
        handle_tui(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
