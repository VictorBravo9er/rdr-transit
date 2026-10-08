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

console = Console()


def handle_discover(args: argparse.Namespace) -> None:
    """Scan local network and display active peers."""
    with console.status("[bold cyan]Scanning for peers (UDP 56780)...[/bold cyan]"):
        peers = discover_peers(timeout=args.timeout, broadcast_port=args.broadcast_port)

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
    dest_dir = Path(args.output_dir).expanduser().resolve()
    dest_dir.mkdir(parents=True, exist_ok=True)

    my_ip = get_primary_ip()

    def on_start(peer_ip: str, fname: str, folder: str, fsize: int) -> None:
        path_desc = f"{folder}/{fname}" if folder else fname
        console.print(f"[cyan]Receiving from [bold]{peer_ip}[/bold]:[/cyan] {path_desc} ({format_size(fsize)})")

    def on_complete(peer_ip: str, fname: str, dest: Path, ok: bool, err: str) -> None:
        if ok:
            console.print(f"[green]✓ Saved:[/green] {dest}")
        else:
            console.print(f"[bold red]✗ Failed {fname} from {peer_ip}:[/bold red] {err}")

    server = ReceiverServer(
        download_dir=dest_dir,
        port=args.port,
        bind_host=args.host,
        on_file_start=on_start,
        on_file_complete=on_complete,
    )

    panel_content = (
        f"[bold white]Status:[/bold white] [green]Listening for connections[/green]\n"
        f"[bold white]Local IP:[/bold white] [yellow]{my_ip}[/yellow]\n"
        f"[bold white]Port:[/bold white] [cyan]{args.port}[/cyan] (TCP)\n"
        f"[bold white]Save Location:[/bold white] [magenta]{dest_dir}[/magenta]\n\n"
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


def handle_send(args: argparse.Namespace) -> None:
    """Send files or directories via CLI."""
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
    if not target_ip:
        with console.status("[cyan]Looking for network peers...[/cyan]"):
            peers = discover_peers(timeout=args.timeout, broadcast_port=args.broadcast_port)
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
    if not args.no_announce:
        send_beacon(target_ip=target_ip, broadcast_port=args.broadcast_port, name=args.name)
        time.sleep(0.15)

    total_bytes = sum(os.path.getsize(p[0]) for p in files)
    total_files = len(files)

    if args.quiet:
        batch = BatchSender(files_to_send=files, receiver_ip=target_ip, transfer_port=args.port)
        stats = batch.run()
        print(f"Transferred {stats.completed_files}/{total_files} in {stats.elapsed_seconds:.2f}s ({stats.speed_mb_per_sec:.2f} MB/s)")
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
            progress.update(
                file_task,
                description=f"[bold green]File {idx}/{total_files}:[/bold green] [white]{short}[/white]",
                completed=0,
                total=fsize,
            )

        def on_chunk(chunk_len: int, file_done: int, total_done: int) -> None:
            progress.update(file_task, advance=chunk_len)
            progress.update(overall_task, advance=chunk_len)

        batch = BatchSender(
            files_to_send=files,
            receiver_ip=target_ip,
            transfer_port=args.port,
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
    summary_table.add_row("Target:", f"{target_ip}:{args.port}")
    summary_table.add_row("Transferred:", f"{stats.completed_files} / {total_files} files")
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
    p_send.add_argument("-p", "--port", type=int, default=DEFAULT_TRANSFER_PORT, help="Transfer TCP port")
    p_send.add_argument("-b", "--broadcast-port", type=int, default=DEFAULT_BROADCAST_PORT, help="Discovery UDP port")
    p_send.add_argument("--timeout", type=float, default=2.0, help="Peer discovery timeout in seconds")
    p_send.add_argument("--name", default=HOSTNAME, help="Device name announced to peers")
    p_send.add_argument("--include-venv", action="store_true", help="Include virtual environment folders")
    p_send.add_argument("--no-announce", action="store_true", help="Skip sending UDP announcement beacon")
    p_send.add_argument("-q", "--quiet", action="store_true", help="Minimal text output mode")

    # Receive subcommand
    p_rec = subparsers.add_parser("receive", help="Start receiver daemon to accept incoming files")
    p_rec.add_argument("-p", "--port", type=int, default=DEFAULT_TRANSFER_PORT, help="Listening TCP port")
    p_rec.add_argument("-d", "--output-dir", default=str(DEFAULT_DOWNLOAD_DIR), help="Directory to save received files")
    p_rec.add_argument("--host", default="0.0.0.0", help="Binding host address")

    # Discover subcommand
    p_disc = subparsers.add_parser("discover", help="Scan local network for active peers")
    p_disc.add_argument("--timeout", type=float, default=2.0, help="Scan duration in seconds")
    p_disc.add_argument("-b", "--broadcast-port", type=int, default=DEFAULT_BROADCAST_PORT, help="Discovery UDP port")

    return parser


def main() -> None:
    """Main CLI entry point."""
    parser = build_parser()
    args = parser.parse_args()

    if args.subcommand == "send":
        handle_send(args)
    elif args.subcommand == "receive":
        handle_receive(args)
    elif args.subcommand == "discover":
        handle_discover(args)
    elif args.subcommand == "tui" or args.subcommand is None:
        # Default with no arguments is to launch the interactive TUI
        handle_tui(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
