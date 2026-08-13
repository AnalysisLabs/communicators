#!/usr/bin/env python3
"""
DB_bootloader.py – sequential initializer for the Runtime VirtualFS.

Runs the four stages in strict order:

  1. VirtualFS.py          create (or recreate) the empty tables
  2. DB_layout.py          seed the boot-order directory skeleton
  3. prefix_builder.py     assemble the runtime prefix and store it

Each module is self-contained; this file only orchestrates.
Intended to be invoked inside the Communicators Nix flake shell
(``nix develop`` from the project root that contains env-bootloader/flake.nix).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def find_communicators_root(start=None) -> Path:
    """Walk up until we find a directory named 'communicators'."""
    d = Path(start or Path.cwd()).absolute()
    while d != Path("/"):
        if d.name == "communicators":
            return d
        d = d.parent
    return Path.cwd()  # fallback

root = find_communicators_root()

# Guaranteed location relative to communicators root
_path_reffs = (
    find_communicators_root()
    / "path_reffs.py"
)
sys.path.insert(0, str(_path_reffs.parent))
from path_reffs import*


_virtualfs_ref = FileRef(
    uuid="dc57ce78-e092-4caf-9016-df666f07cdd5",
    file_path="Genesis/Genesis_DB",
    file_name="VirtualFS.py",
)

_prefix_builder_ref = FileRef(
    uuid="d97229e0-f3f3-46ac-9db4-a94e84b3a43c",
    file_path="Genesis/Genesis_DB",
    file_name="prefix_builder.py",
)


def run(ref: FileRef, *extra_args: str) -> None:
    script_path = resolve_path(ref.uuid, ref.file_path, ref.file_name)
    cmd = [sys.executable, str(script_path), *extra_args]
    print(f"→ {' '.join(cmd)}")
    subprocess.run(cmd, cwd=str(script_path.parent), check=True)


def main() -> None:
    run(_virtualfs_ref)
    run(_prefix_builder_ref, "--write")
    print("\nDB boot sequence complete.")


if __name__ == "__main__":
    main()
