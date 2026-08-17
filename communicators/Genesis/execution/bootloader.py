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
_path_reffs = (
    find_communicators_root()
    / "Genesis"
    / "internal_imports"
    / "path_reffs.py"
)
sys.path.insert(0, str(_path_reffs.parent))
from path_reffs import*

_atomic_importer = (
    find_communicators_root()
    / "Genesis"
    / "internal_imports"
    / "atomic_importer.py"
)
sys.path.insert(0, str(_atomic_importer.parent))

_vfs_writer_ref = FileRef(
    uuid="f9284397-10ec-4856-8f1e-1bc62b9c8436",
    file_path="Genesis/Genesis_DB",
    file_name="vfs_writer.py",
)

# atomic_importer is already on sys.path in the Genesis/Metamorphosis style
from atomic_importer import from_path_import
read_file, = from_path_import(
    resolve_path(
        _vfs_writer_ref.uuid,
        _vfs_writer_ref.file_path,
        _vfs_writer_ref.file_name,
    ),
    "read_file",
)



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

    # --- conventions from prefix_builder / prefix_transpiler ---
    _vfs_writer_ref = FileRef(
        uuid="f9284397-10ec-4856-8f1e-1bc62b9c8436",
        file_path="Genesis/Genesis_DB",
        file_name="vfs_writer.py",
    )

    # fetch the just-written prefix (ensures it exists in the VirtualFS)
    prefix = read_file("Database/prefix.py")

    # resolve the Metamorphosis-stage bootloader via path_reffs
    meta_boot_ref = FileRef(
        uuid="f8dc3fbe-5167-4184-b25a-555c3753286f",
        file_path="Metamorphosis/execution",
        file_name="bootloader.py",
    )
    meta_boot = resolve_path(
        meta_boot_ref.uuid,
        meta_boot_ref.file_path,
        meta_boot_ref.file_name,
    )

    # launch it detached so it survives the death of the Genesis process;
    # pass the virtual path we just fetched

    comm_root = find_communicators_root()

    proc = subprocess.Popen(
        [sys.executable, str(meta_boot), prefix],
        stdin=subprocess.PIPE,
        start_new_session=True,
        stdout=open(str(comm_root / "ns_server.log"), "a"),
        stderr=subprocess.STDOUT,
        close_fds=True,
    )

    print("Genesis sequence complete")


if __name__ == "__main__":
    main()
