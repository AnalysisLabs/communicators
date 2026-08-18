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
    / "Genesis"
    / "internal_imports"
    / "path_reffs.py"
)
sys.path.insert(0, str(_path_reffs.parent))
from path_reffs import*


# ---------------------------------------------------------------------------
# FileRefs
# ---------------------------------------------------------------------------

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

_atomic_importer_ref = FileRef(
    uuid="6c2d43c5-1a1f-4cd5-b41e-7ba2523604ff",
    file_path="Genesis/internal_imports",
    file_name="atomic_importer.py",
)

_path_reffs_src_ref = FileRef(          # original source (not the import)
    uuid="e77217a6-2fb1-4837-925b-312a70874ae5",
    file_path="Genesis/internal_imports",
    file_name="path_reffs.py",
)

_dual_use_rectifier_ref = FileRef(
    uuid="911c5803-bac5-4484-9619-9182eb7d7b3c",
    file_path="Genesis/Genesis_DB",
    file_name="dual_use_rectifier.py",
)

_vfs_writer_ref = FileRef(
    uuid="f9284397-10ec-4856-8f1e-1bc62b9c8436",
    file_path="Genesis/Genesis_DB",
    file_name="vfs_writer.py",
)


def run(ref: FileRef, *extra_args: str) -> None:
    script_path = resolve_path(ref.uuid, ref.file_path, ref.file_name)
    cmd = [sys.executable, str(script_path), *extra_args]
    print(f"→ {' '.join(cmd)}")
    subprocess.run(cmd, cwd=str(script_path.parent), check=True)


def main() -> None:
    # 1. Create the empty VirtualFS
    run(_virtualfs_ref)

    # 2. Produce prefix-ready copies of the two dual-use modules and store them
    #    in the VFS under Database/
    #    (import the rectifier + writer the same way every other Genesis tool does)

    # Make the rectifier importable
    sys.path.insert(0, str(resolve_path(
        _dual_use_rectifier_ref.uuid,
        _dual_use_rectifier_ref.file_path,
        _dual_use_rectifier_ref.file_name,
    ).parent))
    from dual_use_rectifier import rectify_atomic_importer, rectify_path_reffs

    # Obtain write_file the same way prefix_builder does
    from atomic_importer import from_path_import
    write_file, = from_path_import(
        resolve_path(
            _vfs_writer_ref.uuid,
            _vfs_writer_ref.file_path,
            _vfs_writer_ref.file_name,
        ),
        "write_file",
    )

    # Load original sources
    atomic_src = resolve_path(
        _atomic_importer_ref.uuid,
        _atomic_importer_ref.file_path,
        _atomic_importer_ref.file_name,
    ).read_text(encoding="utf-8")

    path_reffs_src = resolve_path(
        _path_reffs_src_ref.uuid,
        _path_reffs_src_ref.file_path,
        _path_reffs_src_ref.file_name,
    ).read_text(encoding="utf-8")

    # Rectify
    atomic_rectified = rectify_atomic_importer(atomic_src)
    path_reffs_rectified = rectify_path_reffs(path_reffs_src)

    # Persist into the VirtualFS
    id1 = write_file(
        "Database/atomic_importer.py",
        atomic_rectified,
        access_tier="agent_user",
    )
    id2 = write_file(
        "Database/path_reffs.py",
        path_reffs_rectified,
        access_tier="agent_user",
    )
    print(f"→ wrote Database/atomic_importer.py  (node {id1})")
    print(f"→ wrote Database/path_reffs.py       (node {id2})")

    # 3. Build the prefixes (they can now see the rectified copies if desired)
    run(_prefix_builder_ref, "--write")

    print("\nDB boot sequence complete.")


if __name__ == "__main__":
    main()
