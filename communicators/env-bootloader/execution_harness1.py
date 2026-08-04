#!/usr/bin/env python3
"""
Execution harness for Communicators OS.

Builds self-contained code objects (VirtualFS prefix + user source) and
launches them. Intended to be imported by the general bootloader after
VFS initialization.
"""

from __future__ import annotations

import marshal
import subprocess
import sys
import traceback
import uuid
from pathlib import Path

from vfs_process_path import inject_process_paths


def find_communicators_root(start=None):
    d = Path(start or Path.cwd()).absolute()
    while d != Path("/"):
        if d.name == "communicators":
            return d
        d = d.parent
    return Path.cwd()  # fallback


def resolve_path(scope: str, target: str) -> str:
    comm_root = find_communicators_root()
    if scope in ("internal", "", "comm", "communicators"):
        return str(comm_root / target)
    if scope == "host":
        return target
    raise ValueError(f"Unknown scope: {scope}")


# ---------------------------------------------------------------------------
# VirtualFS helpers
# ---------------------------------------------------------------------------

def _db_dir() -> Path:
    return Path(resolve_path("internal", "Database"))


def _ensure_vfs_on_path() -> None:
    """Make Database/ importable so we can use vfs_writer."""
    d = str(_db_dir())
    if d not in sys.path:
        sys.path.insert(0, d)


def _get_prefix() -> str:
    _ensure_vfs_on_path()
    from vfs_writer import read_file
    return read_file("Database/prefix.py")


# ---------------------------------------------------------------------------
# Execution harness
# ---------------------------------------------------------------------------

def load_module(scope: str, src: str, dst: str):
    """
    Build a self-contained code object:
      - prefix pulled from VirtualFS (Database/prefix.py)
      - user program from disk (src)
      - combined source stored at the caller-supplied VirtualFS destination (dst)
    """
    program_path = Path(resolve_path(scope, src))
    if not program_path.exists():
        print(f"Error: program not found at {program_path}")
        sys.exit(1)

    prefix_code = _get_prefix()
    user_code = program_path.read_text(encoding="utf-8")

    combined = (
        prefix_code.rstrip()
        + "\n\n\n# ==================== (USER PROGRAM) ====================\n"
        + user_code
    )

    # Inject hierarchical process paths, prefixed by the destination path
    combined = inject_process_paths(combined, program_path=dst)

    # Persist the exact source that will be executed
    _ensure_vfs_on_path()
    from vfs_writer import write_file
    write_file(
        dst,
        combined,
        access_tier="agent_user",
        create_parents=True,
    )
    print(f"→ Combined script stored in VirtualFS → {dst}")

    # after inject_process_paths and write_file, before compile

    bootstrap = f'''\
import linecache
_src = {combined!r}
linecache.cache[{dst!r}] = (
    len(_src),
    None,
    _src.splitlines(True),
    {dst!r},
)
del _src
    '''

    combined = bootstrap + combined

    # Compile with the original user path so tracebacks stay meaningful
    code_obj = compile(combined, dst, "exec")
    return code_obj, dst


def execution_harness(src: str, dst: str, wait: bool = False) -> None:
    comm_root = find_communicators_root()
    code_obj, _ = load_module("internal", src, dst)

    try:
        # Launch via marshal so we never need a temporary .py on the real disk
        proc = subprocess.Popen(
            [
                sys.executable,
                "-c",
                f"import marshal;exec(marshal.loads({marshal.dumps(code_obj)!r}))",
            ],
            start_new_session=True,
            stdout=open(str(comm_root / "ns_server.log"), "a"),
            stderr=subprocess.STDOUT,
            close_fds=True,
        )
        if wait:
            proc.wait()
    except Exception as e:
        print(f"execution_harness failure on: {src}")
        print(e)
        traceback.print_exception(type(e), e, e.__traceback__)
