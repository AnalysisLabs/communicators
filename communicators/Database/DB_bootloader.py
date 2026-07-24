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

HERE = Path(__file__).resolve().parent


def run(script: str, *extra_args: str) -> None:
    cmd = [sys.executable, str(HERE / script), *extra_args]
    print(f"→ {' '.join(cmd)}")
    subprocess.run(cmd, cwd=HERE, check=True)


def main() -> None:
    run("VirtualFS.py")
    run("DB_layout.py")
    run("prefix_builder.py", "--write")
    print("\nDB boot sequence complete.")


if __name__ == "__main__":
    main()
