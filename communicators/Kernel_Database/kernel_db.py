#!/usr/bin/env python3
"""
kernel_db.py – create (or recreate) the kernel / namespace SQLite database.

Analogous to VirtualFS.py from the bootstrap stage.

Responsibilities
----------------
- Resolve the database file path
- Honor the ephemeral / persistent switch
- Create the empty database file
- Install the core structures (object_catalog + VFS tables)

It does not seed domain data and does not provide the read/write API.
Those belong to later modules (kernel_layout.py, kernel_writer.py).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from kernel_structures import create_core_structures

# ---------------------------------------------------------------------------
# Path & lifetime configuration
# ---------------------------------------------------------------------------

# Default location: sibling of this script (same convention as bootstrap).
DEFAULT_DB_FILE = Path(__file__).resolve().parent / "kernel.db"

# Development default: wipe on every init so schema experiments stay cheap.
# Flip to False when real persistent data (tokens, billing, etc.) appears.
EPHEMERAL: bool = True


def _resolve_path(db_path: Path | str | None = None) -> Path:
    if db_path is not None:
        return Path(db_path)
    return DEFAULT_DB_FILE


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def init_kernel_db(
    db_path: Path | str | None = None,
    *,
    ephemeral: bool | None = None,
) -> Path:
    """
    Create (or recreate) the kernel database and its core tables.

    Parameters
    ----------
    db_path:
        Override the default location.  None → DEFAULT_DB_FILE.
    ephemeral:
        If True, delete any existing file first.
        If None, fall back to the module-level EPHEMERAL flag.

    Returns
    -------
    Path
        Absolute path of the database file that was created.
    """
    path = _resolve_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    do_wipe = EPHEMERAL if ephemeral is None else ephemeral
    if do_wipe and path.exists():
        path.unlink()

    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA foreign_keys = ON;")
        create_core_structures(conn)
        conn.commit()
    finally:
        conn.close()

    return path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Initialize the kernel SQLite database")
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="Override database path",
    )
    parser.add_argument(
        "--persistent",
        action="store_true",
        help="Do not wipe an existing database (overrides EPHEMERAL=True)",
    )
    args = parser.parse_args()

    db = init_kernel_db(
        db_path=args.db,
        ephemeral=not args.persistent,
    )
    mode = "persistent" if args.persistent else "ephemeral"
    print(f"Initialized kernel database ({mode}) at: {db}")
