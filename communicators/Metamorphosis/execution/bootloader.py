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


def find_communicators_root(start=None):
    d = Path(start or Path.cwd()).absolute()
    while d != Path("/"):
        if d.name == "communicators":
            return d
        d = d.parent
    return Path.cwd()  # fallback

# Guaranteed location relative to communicators root
_atomic_importer = (
    find_communicators_root()
    / "Genesis"
    / "internal_imports"
    / "atomic_importer.py"
)
sys.path.insert(0, str(_atomic_importer.parent))
from atomic_importer import from_path, from_path_import, from_code, from_code_import
_path_reffs = (
    find_communicators_root()
    / "Genesis"
    / "internal_imports"
    / "path_reffs.py"
)
sys.path.insert(0, str(_path_reffs.parent))
from path_reffs import*



def _ensure_vfs_initialized() -> None:
    """Run the specialised DB bootloader once (fresh DB + layout + prefix)."""
    db_bootloader_ref = FileRef(
        uuid="2d10a8e5-91e5-42c2-a4bd-395801c3e111",
        file_path="Genesis/Genesis_DB",
        file_name="DB_bootloader.py",
    )
    boot = resolve_path(
        db_bootloader_ref.uuid,
        db_bootloader_ref.file_path,
        db_bootloader_ref.file_name,
    )

    if not boot.exists():
        raise FileNotFoundError(f"DB bootloader not found: {boot}")

    print("→ Initializing Runtime VirtualFS via DB_bootloader.py …")
    subprocess.run(
        [sys.executable, str(boot)],
        cwd=str(boot.parent),
        check=True,
    )


def main() -> None:
    _ensure_vfs_initialized()

    # Load execution_harness via the new system
    _execution_harness_ref = FileRef(
        uuid="1314875b-3a56-43ef-bda0-6d126042f5c1",
        file_path="Metamorphosis/execution",
        file_name="execution_harness.py",
    )
    execution_harness, = from_path_import(
        resolve_path(
            _execution_harness_ref.uuid,
            _execution_harness_ref.file_path,
            _execution_harness_ref.file_name,
        ),
        "execution_harness",
    )

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
