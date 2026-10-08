"""
Cross-platform file system scanning, path normalization, and security sanitization.
"""

import os
from pathlib import Path
import re
from typing import List, Optional, Set, Tuple

from rdr_transit.config import DEFAULT_EXCLUDED_DIRS


# Regex pattern for characters forbidden in Windows filenames: \ / : * ? " < > |
WINDOWS_INVALID_CHARS = re.compile(r'[\\/:*?"<>|]')


def format_size(num_bytes: int) -> str:
    """Format bytes into a human-readable string (KB, MB, GB)."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(num_bytes) < 1024.0:
            return f"{num_bytes:.2f} {unit}" if unit != "B" else f"{num_bytes} B"
        num_bytes /= 1024.0
    return f"{num_bytes:.2f} PB"


def collect_target_files(
    input_paths: List[str | Path],
    excluded_dirs: Optional[Set[str]] = None,
    include_hidden: bool = False,
) -> List[Tuple[str, str, str]]:
    """
    Scan files and directories to build a flat list of transfer tuples.
    Returns: List of (abs_file_path, rel_target_folder, file_name)
    Using forward slashes '/' for rel_target_folder for wire compatibility.
    """
    if excluded_dirs is None:
        excluded_dirs = set(DEFAULT_EXCLUDED_DIRS)

    items: List[Tuple[str, str, str]] = []

    for item in input_paths:
        path = Path(item).expanduser().resolve()

        if not path.exists():
            continue

        if path.is_file():
            # Never transfer raw symlinks across different OSes
            if not path.is_symlink():
                items.append((str(path), "", path.name))

        elif path.is_dir():
            root_name = path.name
            for current_root, dirs, files in os.walk(path):
                # Filter out excluded directories in-place
                dirs[:] = [
                    d for d in dirs
                    if d not in excluded_dirs and (include_hidden or not d.startswith("."))
                ]

                rel_from_root = Path(current_root).relative_to(path)
                if rel_from_root == Path("."):
                    folder_wire_path = root_name
                else:
                    # Always use posix forward slashes for cross-platform network protocol
                    folder_wire_path = f"{root_name}/{rel_from_root.as_posix()}"

                for filename in files:
                    if not include_hidden and filename.startswith("."):
                        continue
                    full_file = Path(current_root) / filename
                    if not full_file.is_symlink():
                        items.append((str(full_file), folder_wire_path, filename))

    return items


def sanitize_filename(filename: str) -> str:
    """Sanitize a filename by removing path separators and Windows illegal characters."""
    clean = WINDOWS_INVALID_CHARS.sub("_", filename).strip()
    return clean or "unnamed_file"


def sanitize_destination_path(base_dir: Path, rel_folder: str, file_name: str) -> Path:
    """
    Safely resolve destination file path, preventing directory traversal attacks.
    Guarantees the target path is strictly inside base_dir.
    """
    base_dir = base_dir.expanduser().resolve()

    # Clean rel_folder parts
    safe_parts: List[str] = []
    if rel_folder:
        parts = rel_folder.replace("\\", "/").split("/")
        for p in parts:
            p_clean = p.strip()
            # Prevent directory traversal
            if p_clean in ("", ".", ".."):
                continue
            safe_parts.append(sanitize_filename(p_clean))

    safe_filename = sanitize_filename(file_name)
    target = base_dir.joinpath(*safe_parts, safe_filename).resolve()

    # Strict sandbox check: must be inside base_dir
    try:
        target.relative_to(base_dir)
    except ValueError:
        raise ValueError(f"Path traversal detected: {rel_folder}/{file_name}")

    return target
