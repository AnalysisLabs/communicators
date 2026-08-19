#!/usr/bin/env python3
"""
Communicators OS – Metamorphosis-stage bootloader.

Receives the fully-assembled prefix produced by Genesis, prints its byte size,
persists it as prefix.py, then drives the execution harness for the programs
owned by this stage.

Invoked by Genesis/execution/bootloader.py as:

    python3 Metamorphosis/execution/bootloader.py <prefix>

Must be executed inside the Nix flake shell that Genesis already entered.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path


def find_communicators_root(start=None):
    d = Path(start or Path.cwd()).absolute()
    while d != Path("/"):
        if d.name == "communicators":
            return d
        d = d.parent
    return Path.cwd()  # fallback


# ---------------------------------------------------------------------------
# path_reffs / atomic_importer (Genesis-style)
# ---------------------------------------------------------------------------

_atomic_importer = (
    find_communicators_root()
    / "Genesis"
    / "internal_imports"
    / "atomic_importer.py"
)
sys.path.insert(0, str(_atomic_importer.parent))
from atomic_importer import from_path_import

_path_reffs = (
    find_communicators_root()
    / "Genesis"
    / "internal_imports"
    / "path_reffs.py"
)
sys.path.insert(0, str(_path_reffs.parent))
from path_reffs import *


# FileRefs we need
_harness_ref = FileRef(
    uuid="1314875b-3a56-43ef-bda0-6d126042f5c1",
    file_path="Metamorphosis/execution",
    file_name="execution_harness.py",
)

_meta_boot_ref = FileRef(
    uuid: "131e8e12-a85c-4897-9348-10c7c8219b97",
    file_path: "Metamorphosis/Metamorphosis_DB",
    file_name: "metamorphosis_bootloader.py"
)

_namespace_ref = FileRef(
    uuid="253a5376-dfdc-4e07-b4d1-20446bb9211f",
    file_path="Metamorphosis/servers",
    file_name="namespace.py",
)


def main() -> None:
    if len(sys.argv) < 2:
        print("error: prefix argument missing", file=sys.stderr)
        sys.exit(1)

    prefix = sys.argv[1]

    # byte size of the exact string that was handed over
    data = prefix.encode("utf-8")
    byte_size = len(data)

    # simple content checksum so the receiver can verify what it got
    checksum = hashlib.sha256(data).hexdigest()[:16]

    print(f"prefix received – byte size: {byte_size}  checksum: {checksum}")

    # persist next to this bootloader
    out = Path(__file__).resolve().parent / "prefix.py"
    with open(out, "w", encoding="utf-8") as f:
        f.write(prefix)
    print(f"prefix written → {out}")

    # ------------------------------------------------------------------
    # Drive the execution harness (assembly only for now)
    # ------------------------------------------------------------------
    execution_harness, = from_path_import(
        resolve_path(
            _harness_ref.uuid,
            _harness_ref.file_path,
            _harness_ref.file_name,
        ),
        "execution_harness",
    )

    # namespace.py – assemble only (launch=False) so we can validate the
    # combined artifact without risking a real process launch yet
    execution_harness(
        src=_namespace_ref,
        dst="Metamorphosis/generated/namespace.py",
        prefix=prefix,
        wait=False,
        launch=False,          # ← flip to True when you are ready to launch
    )

    print("Metamorphosis bootloader sequence complete")


if __name__ == "__main__":
    main()
