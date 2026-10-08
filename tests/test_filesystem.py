"""Tests for cross-platform filesystem handling, scanning, and sanitization."""

from pathlib import Path
import pytest

from rdr_transit.utils.filesystem import (
    collect_target_files,
    format_size,
    sanitize_destination_path,
    sanitize_filename,
)


def test_format_size():
    assert format_size(500) == "500 B"
    assert format_size(1024) == "1.00 KB"
    assert format_size(1048576) == "1.00 MB"
    assert format_size(1073741824) == "1.00 GB"


def test_sanitize_filename():
    assert sanitize_filename("test.txt") == "test.txt"
    # Windows forbidden characters should be sanitized to underscores
    assert sanitize_filename('bad:name*file?"<test>|.txt') == "bad_name_file___test__.txt"


def test_sanitize_destination_path_normal(tmp_path):
    dest = sanitize_destination_path(tmp_path, "subfolder/nested", "file.txt")
    expected = tmp_path / "subfolder" / "nested" / "file.txt"
    assert dest == expected.resolve()
    assert dest.is_relative_to(tmp_path)


def test_sanitize_destination_path_traversal(tmp_path):
    # Traversal attempts should be sanitized or constrained safely
    dest = sanitize_destination_path(tmp_path, "../../etc", "passwd")
    # Must never escape base_dir
    assert dest.is_relative_to(tmp_path)
    assert not str(dest).startswith("/etc/passwd")


def test_collect_target_files(tmp_path):
    # Setup test directory tree
    f1 = tmp_path / "file1.txt"
    f1.write_text("file 1 content")

    sub = tmp_path / "subdir"
    sub.mkdir()
    f2 = sub / "file2.py"
    f2.write_text("print('hello')")

    # Excluded folder
    venv = tmp_path / ".venv"
    venv.mkdir()
    f_venv = venv / "pyvenv.cfg"
    f_venv.write_text("home = /usr/bin")

    items = collect_target_files([tmp_path], excluded_dirs={".venv"})
    filenames = [item[2] for item in items]

    assert "file1.txt" in filenames
    assert "file2.py" in filenames
    assert "pyvenv.cfg" not in filenames
