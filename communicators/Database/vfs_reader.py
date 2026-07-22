#!/usr/bin/env python3
"""
vfs_reader.py – thin, focused module for reading file contents from the Runtime VirtualFS.

This is the retrieval counterpart to vfs_writer.py.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

# Re-use the battle-tested implementation from the writer.
# (Keeps a single source of truth for path walking + content lookup.)
from vfs_writer import read_file as _read_file, list_dir


def read_virtual(virtual_path: str, *, db_path: Optional[Path | str] = None) -> str:
    """
    Retrieve the full text content of a file stored in the VirtualFS.

    Example:
        src = read_virtual("Internal_Lib/standard.py")
    """
    return _read_file(virtual_path, db_path=db_path)


# Convenience re-exports
list_virtual = list_dir


if __name__ == "__main__":
    # Quick smoke test
    try:
        content = read_virtual("Internal_Lib/standard.py")
        print(f"Read {len(content)} characters from Internal_Lib/standard.py")
        print("First 120 chars:")
        print(content[:120])
    except Exception as e:
        print(f"Error: {e}")
