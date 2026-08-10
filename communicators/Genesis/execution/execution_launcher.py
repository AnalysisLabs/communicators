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
    if len(sys.argv) < 2:
        print("usage: execution_launcher.py <dst>", file=sys.stderr)
        sys.exit(2)

    dst = sys.argv[1]
    src = sys.stdin.read()

    if not src:
        print("execution_launcher: empty source on stdin", file=sys.stderr)
        sys.exit(1)

    # Make the source recoverable under the exact name we are about to compile with.
    # This is the companion fix that prevents "could not get source code".
    linecache.cache[dst] = (
        len(src),
        None,
        src.splitlines(True),
        dst,
    )

    _install_intermediary(dst)

    # The critical step: compile under the VirtualFS destination name.
    code = compile(src, dst, "exec")

    # Controlled globals so __file__ exists (stops Manifest._get_internal_files
    # from raising NameError) and the module looks like a normal top-level script.
    glb = {
        "__name__": "__main__",
        "__file__": dst,
        "__builtins__": __builtins__,
    }

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
