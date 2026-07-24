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

import marshal
import subprocess
import sys
import traceback
import uuid
from pathlib import Path


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


def _get_prefix() -> str:
    _ensure_vfs_on_path()
    from vfs_writer import read_file
    return read_file("Database/prefix.py")


# ---------------------------------------------------------------------------
# Execution harness
# ---------------------------------------------------------------------------

def load_module(scope: str, path: str):
    """
    Build a self-contained code object:
      - prefix pulled from VirtualFS (Database/prefix.py)
      - user program from disk
      - combined source also stored under Runtime/generated/ for inspection
    """
    program_path = Path(resolve_path(scope, path))
    if not program_path.exists():
        print(f"Error: program not found at {program_path}")
        sys.exit(1)

    prefix_code = _get_prefix()
    user_code = program_path.read_text(encoding="utf-8")

    combined = (
        prefix_code.rstrip()
        + "\n\n\n# ==================== USER PROGRAM ====================\n"
        + user_code
    )

    # Persist the exact source that will be executed
    _ensure_vfs_on_path()
    from vfs_writer import write_file
    virt = f"Runtime/generated/{uuid.uuid4().hex}.py"
    write_file(
        virt,
        combined,
        access_tier="agent_user",
        create_parents=True,          # Runtime/ may already exist; generated/ is created on demand
    )
    print(f"→ Combined script stored in VirtualFS → {virt}")

    # Compile with the original user path so tracebacks stay meaningful
    code_obj = compile(combined, str(program_path), "exec")
    return code_obj, virt


def execution_harness(target_path: str, wait: bool = False) -> None:
    comm_root = find_communicators_root()
    code_obj, _ = load_module("internal", target_path)

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
        print(f"execution_harness failure on: {target_path}")
        print(e)
        traceback.print_exception(type(e), e, e.__traceback__)


def main() -> None:
    _ensure_vfs_initialized()

    execution_harness("state-methods/namespace.py", wait=False)
    execution_harness("transpiler/egg_transpiler.py", wait=True)

    print("bootloader sequence complete")


if __name__ == "__main__":
    main()
