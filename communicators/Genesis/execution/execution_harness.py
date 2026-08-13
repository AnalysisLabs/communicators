#!/usr/bin/env python3
"""
Execution harness for Communicators OS.

Builds the final combined source (VirtualFS prefix + user program),
stores it under the caller-supplied VirtualFS destination, then hands
the text + the destination name to execution_launcher.py which runs
inside an independent child process.

The launcher is responsible for:
  - compile(src, dst, "exec")          → correct co_filename
  - linecache population               → inspect / source recovery
  - installing the process_path intermediary
  - exec under controlled globals
"""

from __future__ import annotations

import subprocess
import sys
import traceback
from pathlib import Path

from vfs_process_path import inject_process_paths

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
    / "path_reffs.py"
)
sys.path.insert(0, str(_path_reffs.parent))
from path_reffs import*

_vfs_writer_ref = FileRef(
    uuid="f9284397-10ec-4856-8f1e-1bc62b9c8436",
    file_path="Genesis/Genesis_DB",
    file_name="vfs_writer.py",
)

# ---------------------------------------------------------------------------
# VirtualFS helpers
# ---------------------------------------------------------------------------


def _get_prefix() -> str:
    read_file, = from_path_import(
        resolve_path(
            _vfs_writer_ref.uuid,
            _vfs_writer_ref.file_path,
            _vfs_writer_ref.file_name,
        ),
        "read_file",
    )
    return read_file("Database/prefix.py")

def _launcher_path() -> Path:
    """execution_launcher.py lives next to this file."""
    return Path(__file__).resolve().parent / "execution_launcher.py"


# ---------------------------------------------------------------------------
# Source assembly
# ---------------------------------------------------------------------------

def load_module(src: FileRef, dst: str) -> tuple[str, str]:
    """
    Assemble the final combined source and store it in the VirtualFS.

    Parameters
    ----------
    src : FileRef
        Identity of the real-filesystem user program.
    dst : str
        VirtualFS destination path (still a plain string for now).

    Returns
    -------
    (combined_source, dst)
    """
    # Strict triple lookup via path_reffs
    program_path = resolve_path(src.uuid, src.file_path, src.file_name)

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
    write_file, = from_path_import(
        resolve_path(
            _vfs_writer_ref.uuid,
            _vfs_writer_ref.file_path,
            _vfs_writer_ref.file_name,
        ),
        "write_file",
    )
    write_file(
        dst,
        combined,
        access_tier="agent_user",
        create_parents=True,
    )
    print(f"→ Combined script stored in VirtualFS → {dst}")

    return combined, dst


# ---------------------------------------------------------------------------
# Launch
# ---------------------------------------------------------------------------

def execution_harness(src: FileRef, dst: str, wait: bool = False) -> None:
    """
    Assemble the program and hand it to the child-side launcher.

    The child process:
      - receives the source on stdin
      - receives the VirtualFS destination as argv[1]
      - compiles under that name, populates linecache, installs the
        process_path intermediary, then execs.
    """
    comm_root = find_communicators_root()
    combined, dst = load_module(src, dst)

    launcher = _launcher_path()
    if not launcher.exists():
        raise FileNotFoundError(f"execution_launcher.py not found at {launcher}")

    try:
        proc = subprocess.Popen(
            [sys.executable, str(launcher), dst],
            stdin=subprocess.PIPE,
            start_new_session=True,
            stdout=open(str(comm_root / "ns_server.log"), "a"),
            stderr=subprocess.STDOUT,
            close_fds=True,
        )
        assert proc.stdin is not None
        proc.stdin.write(combined.encode("utf-8"))
        proc.stdin.close()

        if wait:
            proc.wait()
    except Exception as e:
        print(f"execution_harness failure on: {src}")
        print(e)
        traceback.print_exception(type(e), e, e.__traceback__)
