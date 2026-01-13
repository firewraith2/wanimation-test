"""Common utility functions for test scripts."""

import hashlib
import shutil
from pathlib import Path

from data import read_file_to_bytes, SEPARATOR_LINE_LENGTH

STEP_SEPARATOR = "-" * SEPARATOR_LINE_LENGTH
SECTION_SEPARATOR = "=" * SEPARATOR_LINE_LENGTH


def print_step_header(step_num, title):
    """Print a formatted step header."""
    print(STEP_SEPARATOR)
    print(f"[STEP {step_num}] {title}...")
    print(STEP_SEPARATOR)
    print()


def safe_remove_folder(folder_path: Path, description=""):
    """Safely remove a folder with optional description."""
    if not folder_path.exists():
        return False
    try:
        shutil.rmtree(folder_path)
        if description:
            print(f"[OK] Removed {description}")
        return True
    except Exception as e:
        if description:
            print(f"[WARNING] Failed to remove {description}: {e}")
        return False


def get_file_checksum(file_path: Path) -> str:
    """Get SHA256 checksum of a file."""
    data = read_file_to_bytes(file_path)
    return hashlib.sha256(data).hexdigest()


def get_subfolders(base_dir: Path):
    """Get sorted list of subfolder names in a directory."""
    return sorted(entry.name for entry in base_dir.iterdir() if entry.is_dir())
