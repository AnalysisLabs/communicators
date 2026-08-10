#!/usr/bin/env python3
"""
kernel_bootloader.py – thin orchestrator for kernel DB initialization.

Analogous to DB_bootloader.py from the bootstrap stage.

Current sequence:

  1. kernel_db.init_kernel_db   → create file + core structures
                                   (object_catalog + VFS tables)
  2. (future) kernel_layout     → optional seed rows / catalog entries

Keeps the boot path dumb and ordered.  Domain data access lives in
kernel_writer.py; structure definitions live in kernel_structures.py.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from kernel_db import init_kernel_db


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Initialize the kernel / namespace SQLite database"
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="Override database path (default: kernel.db next to the modules)",
    )
    parser.add_argument(
        "--persistent",
        action="store_true",
        help="Do not wipe an existing database (overrides EPHEMERAL=True)",
    )
    args = parser.parse_args(argv)

    print("→ Initializing kernel database …")
    path = init_kernel_db(
        db_path=args.db,
        ephemeral=not args.persistent,
    )
    mode = "persistent" if args.persistent else "ephemeral"
    print(f"→ kernel database ready ({mode}) at {path}")

    # Future extension point:
    # from kernel_layout import seed_kernel_layout
    # seed_kernel_layout(path)

    print("kernel boot sequence complete")


if __name__ == "__main__":
    main()
