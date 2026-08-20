#!/usr/bin/env python3
"""
Execution harness for Communicators OS (Metamorphosis stage).

Receives a fully-assembled prefix (handed over by Genesis), concatenates it
with the user program, injects process_path annotations, stores the combined
source under the given VirtualFS destination, then hands the text + destination
to execution_launcher.py which runs inside an independent child process.

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
from atomic_importer import from_path_import

_path_reffs = (
    find_communicators_root()
    / "Genesis"
    / "internal_imports"
    / "path_reffs.py"
)
sys.path.insert(0, str(_path_reffs.parent))
from path_reffs import *

# Local Metamorphosis/execution FileRefs
_vfs_process_path_ref = FileRef(
    uuid="8c0a8471-559e-4bce-9789-b25f45c5b5b2",
    file_path="Metamorphosis/execution",
    file_name="vfs_process_path.py",
)

_launcher_ref = FileRef(
    uuid="20c4cbf1-46c4-4d6a-88a9-e8c119fde42d",
    file_path="Metamorphosis/execution",
    file_name="execution_launcher.py",
)

_writer_ref = FileRef(
    uuid="93752a7b-6da4-49ff-b704-e2bc2c32926a",
    file_path="Metamorphosis/Metamorphosis_DB",
    file_name="metamorphosis_writer.py",
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_inject_process_paths():
    inject_process_paths, = from_path_import(
        resolve_path(
            _vfs_process_path_ref.uuid,
            _vfs_process_path_ref.file_path,
            _vfs_process_path_ref.file_name,
        ),
        "inject_process_paths",
    )
    return inject_process_paths


def _launcher_path() -> Path:
    return resolve_path(
        _launcher_ref.uuid,
        _launcher_ref.file_path,
        _launcher_ref.file_name,
    )

def metamorphosis_db_available() -> bool:
    """
    Fail-safe probe: return True only if the Metamorphosis DB exists
    and object_catalog can be read as a properly structured table.
    Any error (missing file, missing table, connection failure,
    unexpected shape, import problems, etc.) returns False.
    """
    try:
        import sqlite3
        from pathlib import Path

        # Same default location the Metamorphosis_DB modules use
        db_path = (
            find_communicators_root()
            / "Metamorphosis"
            / "Metamorphosis_DB"
            / "metamorphosis.db"
        )

        if not db_path.exists():
            return False

        conn = sqlite3.connect(str(db_path))
        try:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                "SELECT id, type, owner, name, pointer, metadata, "
                "created_at, updated_at FROM object_catalog LIMIT 5"
            )
            rows = cur.fetchall()

            # Accept empty table; just require that the query succeeded
            # and each row has the expected columns.
            expected = {
                "id", "type", "owner", "name",
                "pointer", "metadata", "created_at", "updated_at"
            }
            for row in rows:
                if set(row.keys()) != expected:
                    return False
            return True
        finally:
            conn.close()

    except Exception:
        # Absorb every possible failure mode while the DB is still being born
        return False

# ---------------------------------------------------------------------------
# Two-pronged persistence
# ---------------------------------------------------------------------------

_pending_artifacts: dict[str, str] = {}   # dst → combined source


def save_combined(dst: str, combined: str) -> None:
    """
    Two-pronged save:

      1. If Metamorphosis DB is alive, try to write into its VFS.
      2. On any failure (or DB not ready) fall back to real-FS
         next to the harness and also stash in _pending_artifacts.
    """
    if metamorphosis_db_available():
        try:
            write_file, = from_path_import(
                resolve_path(
                    _writer_ref.uuid,
                    _writer_ref.file_path,
                    _writer_ref.file_name,
                ),
                "write_file",
            )
            write_file(
                dst,
                combined,
                access_tier="agent_user",
                create_parents=True,
            )
            print(f"→ Combined script stored in Metamorphosis DB → {dst}")
            # Successful DB write – no need to keep a pending copy
            _pending_artifacts.pop(dst, None)
            return
        except Exception as e:
            print(f"→ Metamorphosis DB write failed ({type(e).__name__}: {e}); falling back")

    # Fallback: real filesystem + pending registry
    out_name = Path(dst).name
    out_path = find_communicators_root() / "Metamorphosis" / "execution" / out_name
    out_path.write_text(combined, encoding="utf-8")
    _pending_artifacts[dst] = combined
    print(f"→ Combined script saved (pending) → {out_path}")

def flush_pending_artifacts() -> None:
    """
    Move every artifact currently sitting in _pending_artifacts into the
    Metamorphosis DB.

    Precondition: the caller guarantees that the Metamorphosis DB is fully
    operational (metamorphosis_db_available() would return True and the
    writer is usable).  No fallback logic is performed here.
    """
    if not _pending_artifacts:
        print("→ flush_pending_artifacts: nothing pending")
        return

    write_file, = from_path_import(
        resolve_path(
            _writer_ref.uuid,
            _writer_ref.file_path,
            _writer_ref.file_name,
        ),
        "write_file",
    )

    # Iterate over a copy so we can mutate the dict safely
    for dst, combined in list(_pending_artifacts.items()):
        write_file(
            dst,
            combined,
            access_tier="agent_user",
            create_parents=True,
        )
        print(f"→ flushed pending artifact → {dst}")
        del _pending_artifacts[dst]

    print("→ flush_pending_artifacts complete")

# ---------------------------------------------------------------------------
# Source assembly
# ---------------------------------------------------------------------------

def load_module(src: FileRef, dst: str, prefix: str) -> tuple[str, str]:
    """
    Assemble the final combined source and store it in the VirtualFS.

    Parameters
    ----------
    src : FileRef
        Identity of the real-filesystem user program.
    dst : str
        VirtualFS destination path.
    prefix : str
        Fully assembled prefix code (provided by Genesis).
    """
    program_path = resolve_path(src.uuid, src.file_path, src.file_name)

    if not program_path.exists():
        print(f"Error: program not found at {program_path}")
        sys.exit(1)

    user_code = program_path.read_text(encoding="utf-8")

    combined = (
        prefix.rstrip()
        + "\n\n\n# ==================== (USER PROGRAM) ====================\n"
        + user_code
    )

    # Inject hierarchical process paths, prefixed by the destination path
    inject_process_paths = _get_inject_process_paths()
    combined = inject_process_paths(combined, program_path=dst)

    save_combined(dst, combined)

    return combined, dst


# ---------------------------------------------------------------------------
# Launch
# ---------------------------------------------------------------------------

def execution_harness(src: FileRef, dst: str, prefix: str, wait: bool = False, launch: bool = False,) -> None:
    """
    Assemble the program using the supplied prefix and hand it to the child-side launcher.

    The child process:
      - receives the source on stdin
      - receives the VirtualFS destination as argv[1]
      - compiles under that name, populates linecache, installs the
        process_path intermediary, then execs.
    """
    comm_root = find_communicators_root()
    combined, dst = load_module(src, dst, prefix)

    if not launch:
        print(f"→ launch=False – skipping execution_launcher for {dst}")
        return

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
