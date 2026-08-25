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
from atomic_importer import from_path_import, from_code_import

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

_pending_artifacts: dict[str, str] = {}
_active_prefix: str | None = None
_write_file_cached = None
_writer_loading = False

def _get_write_file():
    """
    Build (prefix + metamorphosis_writer source) and extract write_file
    via from_code_import so PathReffs / AtomicImporter / COMMUNICATORS_ROOT exist.
    """
    global _write_file_cached, _writer_loading

    if _write_file_cached is not None:
        return _write_file_cached

    if _active_prefix is None:
        raise RuntimeError(
            "write_file requested before any load_module set _active_prefix"
        )

    if _writer_loading:
        # Writer top-level itself calls load_module → save_combined.
        # Do not recurse into another writer load.
        raise RuntimeError("write_file requested while metamorphosis_writer is loading")

    writer_path = resolve_path(
        _writer_ref.uuid,
        _writer_ref.file_path,
        _writer_ref.file_name,
    )
    if not writer_path.exists():
        raise FileNotFoundError(f"metamorphosis_writer not found at {writer_path}")

    user_code = writer_path.read_text(encoding="utf-8")
    combined = (
        _active_prefix.rstrip()
        + "\n\n\n# ==================== (USER PROGRAM) ====================\n"
        + user_code
    )
    # Intentionally no inject_process_paths / no save_combined — this is a
    # library load for the harness, not a staged artifact publish.

    _writer_loading = True
    try:
        write_file, = from_code_import(
            combined,
            "metamorphosis_writer",
            "write_file",
            filename=str(writer_path),  # better paths in tracebacks
        )
        _write_file_cached = write_file
        return write_file
    finally:
        _writer_loading = False

def flush_pending_artifacts() -> None:
    if not _pending_artifacts:
        print("→ flush_pending_artifacts: nothing pending")
        return

    write_file = _get_write_file()

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


def save_combined(dst: str, combined: str) -> None:
    # While the writer module is still executing its top-level body it will
    # call load_module(structures) → save_combined.  Never attempt a DB write
    # in that window (write_file is not ready / would recurse).
    if metamorphosis_db_available() and not _writer_loading:
        try:
            flush_pending_artifacts()
            write_file = _get_write_file()
            write_file(
                dst,
                combined,
                access_tier="agent_user",
                create_parents=True,
            )
            print(f"→ Combined script stored in Metamorphosis DB → {dst}")
            _pending_artifacts.pop(dst, None)
            return
        except Exception as e:
            print(
                f"→ Metamorphosis DB write failed ({type(e).__name__}: {e}); "
                f"falling back"
            )

    out_name = Path(dst).name
    out_path = find_communicators_root() / "Metamorphosis" / "execution" / out_name
    out_path.write_text(combined, encoding="utf-8")
    _pending_artifacts[dst] = combined
    print(f"→ Combined script saved (pending) → {out_path}")


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
    global _active_prefix
    _active_prefix = prefix

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


def _target_kwargs_to_cli(kwargs: dict) -> list[str]:
    """
    Turn arbitrary target kwargs into CLI flags.
    None  → omit
    True  → --flag
    False → omit          (store_true style)
    other → --flag value
    """
    args: list[str] = []
    for key, value in kwargs.items():
        flag = f"--{key.replace('_', '-')}"
        if value is None:
            continue
        if isinstance(value, bool):
            if value:
                args.append(flag)
            continue
        args.extend([flag, str(value)])
    return args

# ---------------------------------------------------------------------------
# Launch
# ---------------------------------------------------------------------------

def execution_harness(
    src: FileRef,
    dst: str,
    prefix: str,
    wait: bool = False,
    launch: bool = False,
    **target_kwargs,                    # ← any kwargs the target demands
) -> None:
    """
    Assemble the program and optionally hand it to the child-side launcher.

    Harness-owned parameters: src, dst, prefix, wait, launch.
    Every other keyword argument is assumed to belong to the target program
    and is forwarded unchanged (as CLI flags) to execution_launcher.
    """
    comm_root = find_communicators_root()
    combined, dst = load_module(src, dst, prefix)

    if not launch:
        print(f"→ launch=False – skipping execution_launcher for {dst}")
        return

    launcher = _launcher_path()
    if not launcher.exists():
        raise FileNotFoundError(f"execution_launcher.py not found at {launcher}")

    cli_args = _target_kwargs_to_cli(target_kwargs)

    try:
        proc = subprocess.Popen(
            [sys.executable, str(launcher), "--dst", dst, *cli_args],
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
