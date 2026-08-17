#!/usr/bin/env python3
"""
Communicators OS – Metamorphosis-stage bootloader.

Receives the fully-assembled prefix produced by Genesis, prints its byte size,
and persists it as prefix.py in the same directory as this file.

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
from path_reffs import *


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
    with open(out, "w", encoding="utf-8") as f: f.write(prefix)
    print(f"prefix written → {out}")


if __name__ == "__main__":
    main()
