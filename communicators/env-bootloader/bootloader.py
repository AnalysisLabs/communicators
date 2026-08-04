#!/usr/bin/env python3
"""
Communicators OS general bootloader.

1. Runs Database/DB_bootloader.py (creates the ephemeral SQLite VirtualFS,
   seeds the layout, and writes the assembled prefix into Database/prefix.py).
2. For every program, pulls that prefix from the VirtualFS, concatenates it
   with the user source, stores the combined text under Runtime/generated/,
   then launches the result.

Must be executed inside the Nix flake shell:

    nix develop ./env-bootloader
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from execution_harness import execution_harness, _db_dir


def _ensure_vfs_initialized() -> None:
    """Run the specialised DB bootloader once (fresh DB + layout + prefix)."""
    boot = _db_dir() / "DB_bootloader.py"
    if not boot.exists():
        raise FileNotFoundError(f"DB bootloader not found: {boot}")
    print("→ Initializing Runtime VirtualFS via DB_bootloader.py …")
    subprocess.run(
        [sys.executable, str(boot)],
        cwd=str(_db_dir()),
        check=True,
    )


def main() -> None:
    _ensure_vfs_initialized()

    execution_harness(
        src="state-methods/namespace.py",
        dst="Runtime/generated/namespace.py",
        wait=False,
    )
    execution_harness(
        src="transpiler/egg_transpiler.py",
        dst="Metamorphosis/generated/egg_transpiler",
        wait=True,
    )

    print("bootloader sequence complete")


if __name__ == "__main__":
    main()
