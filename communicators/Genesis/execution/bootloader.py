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

    # Real filesystem sources → FileRef
    namespace_ref = FileRef(
        uuid="253a5376-dfdc-4e07-b4d1-20446bb9211f",
        file_path="Metamorphosis/servers",
        file_name="namespace.py",
    )

    egg_transpiler_ref = FileRef(
        uuid="2d057654-b1d8-4c38-b9b1-214eb60b4acd",
        file_path="Metamorphosis/transpiler",
        file_name="egg_transpiler.py",
    )

    # Note: dst values are still VirtualFS paths (not in file_registry.json yet)
    execution_harness(
        src=namespace_ref,
        dst="Runtime/generated/namespace.py",
        wait=False,
    )
    execution_harness(
        src=egg_transpiler_ref,
        dst="Metamorphosis/generated/egg_transpiler",
        wait=True,
    )

    print("bootloader sequence complete")


if __name__ == "__main__":
    main()
