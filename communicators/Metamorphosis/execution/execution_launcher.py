#!/usr/bin/env python3
"""
execution_launcher.py – lightweight child-side launcher for Communicators.

Receives:
  - the final combined source on stdin
  - the VirtualFS destination path as sys.argv[1]  (e.g. "Runtime/generated/namespace.py")

Responsibilities:
  1. Read the source text.
  2. Populate linecache so inspect / traceback context lines work.
  3. Stamp co_filename = dst so every frame reports the VirtualFS path.
  4. Install the process_path-aware exception intermediary (hook point).
  5. exec the code under a controlled globals dict that also sets __file__.

This module is deliberately tiny.  All heavy lifting (prefix assembly,
process-path injection, VirtualFS writes) stays in the parent harness.
"""

from __future__ import annotations

import argparse
import linecache
import sys
import traceback


def _install_intermediary(dst: str) -> None:
    """
    Hook point for the process_path-aware error reformatter.

    For now this is a minimal placeholder that keeps the classic
    traceback but guarantees the frames already carry the correct
    dst filename (thanks to the compile below).  The real reformatter
    that turns "File … line N" into Manifest-style process_paths
    will be installed here later.
    """
    # Future: sys.excepthook = process_path_excepthook
    # Future: also override traceback.print_exception if desired
    pass


def main() -> None:
    # Launcher only claims --dst. Everything else belongs to the target.
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--dst", required=True)
    parser.add_argument("--prefix", default=None)
    args, remaining = parser.parse_known_args()

    dst = args.dst

    # Target CLI sees only the flags that were meant for it
    sys.argv = [sys.argv[0], *remaining]
    if args.prefix is not None:
        sys.argv.extend(["--prefix", args.prefix])

    src = sys.stdin.read()
    if not src:
        print("execution_launcher: empty source on stdin", file=sys.stderr)
        sys.exit(1)

    linecache.cache[dst] = (
        len(src),
        None,
        src.splitlines(True),
        dst,
    )

    _install_intermediary(dst)

    code = compile(src, dst, "exec")

    glb = {
        "__name__": "__main__",
        "__file__": dst,
        "__builtins__": __builtins__,
    }
    if args.prefix is not None:
        glb["prefix"] = args.prefix

    exec(code, glb)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except BaseException:
        # Last-resort reporting so a failure inside the launcher itself
        # still lands in ns_server.log (stderr is already redirected).
        traceback.print_exc()
        sys.exit(1)
