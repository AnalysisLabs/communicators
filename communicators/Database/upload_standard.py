#!/usr/bin/env python3
"""
upload_standard.py – first concrete use of vfs_writer.

Copies prelude/standard.py into the VirtualFS under Internal_Lib/standard.py
with access_tier="agent_user".

Assumes VirtualFS.py + DB_layout.py have already been run.
"""

from pathlib import Path
from vfs_writer import write_file, read_file, list_dir

def find_communicators_root(start=None):
    d = Path(start or Path.cwd()).absolute()
    while d != Path("/"):
        if d.name == "communicators":
            return d
        d = d.parent
    return Path.cwd()  # fallback

# Location of the real source on disk
SOURCE = find_communicators_root() / "prelude" / "standard.py"

def main() -> None:
    if not SOURCE.exists():
        raise FileNotFoundError(f"Cannot find {SOURCE}")

    content = SOURCE.read_text(encoding="utf-8")

    node_id = write_file(
        virtual_path="Internal_Lib/standard.py",
        content=content,
        access_tier="agent_user",
    )
    print(f"Uploaded → Internal_Lib/standard.py  (node id {node_id})")

    # Quick verification
    assert read_file("Internal_Lib/standard.py") == content
    print("Verification OK")

    print("\nCurrent Internal_Lib/ contents:")
    for name, typ in list_dir("Internal_Lib"):
        print(f"  {name:30s}  {typ}")


if __name__ == "__main__":
    main()
