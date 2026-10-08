"""
Tests for RDR-Transit Desktop GUI components.
"""

from pathlib import Path
import tkinter as tk
from unittest.mock import MagicMock, patch

import pytest

from rdr_transit.discovery import DiscoveredPeer
from rdr_transit.gui.app import RDRTransitGUI
from rdr_transit.transfer.sender import TransferStats


@pytest.fixture
def gui_instance(tmp_path):
    root = tk.Tk()
    root.withdraw()  # Don't show window during testing
    with patch("rdr_transit.gui.app.PeerDiscoveryService"), \
         patch("rdr_transit.gui.app.ReceiverServer"):
        app = RDRTransitGUI(root)
        app.cfg.download_dir = str(tmp_path / "Downloads")
        yield app
    try:
        app.on_close()
    except Exception:
        pass


def test_gui_initialization(gui_instance):
    assert gui_instance is not None
    assert gui_instance.root is not None
    assert gui_instance.notebook is not None
    assert len(gui_instance.staged_paths) == 0


def test_gui_peer_discovery_event(gui_instance):
    peer = DiscoveredPeer(
        ip="192.168.1.150",
        name="AndroidPhone",
        os="Android",
        port=17116,
    )
    # Put peer into queue and process
    gui_instance.event_queue.put(("peer_updated", peer))
    gui_instance._process_event_queue()

    assert "192.168.1.150" in gui_instance.discovered_peers
    children = gui_instance.peers_tree.get_children()
    assert len(children) == 1
    vals = gui_instance.peers_tree.item(children[0], "values")
    assert vals[0] == "AndroidPhone"
    assert vals[2] == "192.168.1.150"


def test_gui_stage_and_clear_files(gui_instance, tmp_path):
    test_file = tmp_path / "sample.txt"
    test_file.write_text("hello world")

    gui_instance.staged_paths.append(test_file)
    gui_instance._refresh_staged_view()

    items = gui_instance.staged_tree.get_children()
    assert len(items) == 1
    assert "sample.txt" in gui_instance.staged_tree.item(items[0], "values")[0]

    # Test clear
    gui_instance._clear_staged()
    assert len(gui_instance.staged_tree.get_children()) == 0


def test_gui_progress_update(gui_instance):
    stats = TransferStats(
        total_files=2,
        completed_files=1,
        total_bytes=1000,
        transferred_bytes=500,
        current_file_name="file2.bin",
    )
    gui_instance.event_queue.put(("send_progress", stats))
    gui_instance._process_event_queue()

    assert gui_instance.send_progress_bar["value"] == 50.0
    assert "file2.bin" in gui_instance.send_status_label.cget("text")
