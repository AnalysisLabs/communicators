#!/usr/bin/env python3
"""
vfs_writer.py – general-purpose middleman for writing programs into the Runtime VirtualFS.

Works with the schema created by VirtualFS.py.
Uses content-addressed storage (sha256). The DB is ephemeral by design.

Typical use (from any later stage or generator):

    from vfs_writer import write_file

    source = Path("whatever.py").read_text(encoding="utf-8")
    # or source = some_generated_string

    write_file(
        "Internal_Lib/standard.py",
        source,
        access_tier="agent_user",
    )

You can also override the database location:

    write_file(..., db_path="/path/to/genesis_fs.db")
"""

from __future__ import annotations

import hashlib
import sys
import sqlite3
from pathlib import Path
from typing import Optional


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

# Guaranteed location relative to communicators root
_path_reffs = (
    find_communicators_root()
    / "Genesis"
    / "internal_imports"
    / "path_reffs.py"
)
sys.path.insert(0, str(_path_reffs.parent))
from path_reffs import*

_db_ref = FileRef(
    uuid="f297d474-1d81-4f4d-b111-5c4369ad153d",
    file_path="Genesis/Genesis_DB",
    file_name="runtime_fs.db",
)

db_path = resolve_path(
        _db_ref.uuid,
        _db_ref.file_path,
        _db_ref.file_name,
    )

def _connect() -> sqlite3.Connection:
    if not db_path.exists():
        raise FileNotFoundError(
            f"{db_path} does not exist.\n"
            "Run VirtualFS.py first."
        )
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def _sha256(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _ensure_content(conn: sqlite3.Connection, data: str) -> int:
    """Insert or reuse a content row. Returns content_id."""
    h = _sha256(data)
    size = len(data.encode("utf-8"))

    cur = conn.execute("SELECT id FROM file_contents WHERE hash = ?", (h,))
    row = cur.fetchone()
    if row:
        return row[0]

    cur = conn.execute(
        "INSERT INTO file_contents (hash, data, size) VALUES (?, ?, ?)",
        (h, data, size),
    )
    return cur.lastrowid


def _get_root_id(conn: sqlite3.Connection) -> int:
    cur = conn.execute(
        "SELECT id FROM file_graph WHERE parent_id IS NULL AND name = ''"
    )
    row = cur.fetchone()
    if not row:
        raise RuntimeError("Root node missing")
    return row[0]


def _find_child(
    conn: sqlite3.Connection, parent_id: Optional[int], name: str
) -> Optional[int]:
    cur = conn.execute(
        "SELECT id FROM file_graph WHERE parent_id IS ? AND name = ?",
        (parent_id, name),
    )
    row = cur.fetchone()
    return row[0] if row else None


def write_file(
    virtual_path: str,
    content: str,
    *,
    access_tier: str = "agent_user",
    create_parents: bool = True,
) -> int:
    """
    Write (or replace) a file in the VirtualFS.

    Parameters
    ----------
    virtual_path : str
        Virtual path, e.g. "Internal_Lib/standard.py"
    content : str
        Full source text of the program (already generated or read from disk).
    access_tier : str
        One of: human_owner | agent_user | group | others
    create_parents : bool
        If True, missing intermediate directories are created automatically.
        Default False – the layout seeder is expected to have made the dirs.

    Returns
    -------
    int
        The file_graph.id of the written (or updated) node.
    """
    parts = [p for p in virtual_path.strip("/").split("/") if p]
    if not parts:
        raise ValueError("Cannot write to the root itself")

    filename = parts[-1]
    dir_parts = parts[:-1]

    conn = _connect()
    try:
        parent_id = _get_root_id(conn)

        # Walk / create the directory path
        for dirname in dir_parts:
            existing = _find_child(conn, parent_id, dirname)
            if existing is not None:
                parent_id = existing
            else:
                if not create_parents:
                    raise FileNotFoundError(
                        f"Directory '{dirname}' does not exist under the current parent. "
                        f"Run the layout seeder or pass create_parents=True."
                    )
                cur = conn.execute(
                    """
                    INSERT INTO file_graph
                        (parent_id, name, type, content_id, access_tier)
                    VALUES (?, ?, 'dir', NULL, ?)
                    """,
                    (parent_id, dirname, access_tier),
                )
                parent_id = cur.lastrowid

        # Content-addressed payload
        content_id = _ensure_content(conn, content)

        # Insert or replace the file node
        existing_file = _find_child(conn, parent_id, filename)
        if existing_file is not None:
            conn.execute(
                """
                UPDATE file_graph
                SET content_id = ?, access_tier = ?
                WHERE id = ?
                """,
                (content_id, access_tier, existing_file),
            )
            node_id = existing_file
        else:
            cur = conn.execute(
                """
                INSERT INTO file_graph
                    (parent_id, name, type, content_id, access_tier)
                VALUES (?, ?, 'file', ?, ?)
                """,
                (parent_id, filename, content_id, access_tier),
            )
            node_id = cur.lastrowid

        conn.commit()
        return node_id
    finally:
        conn.close()


def read_file(
    virtual_path: str,
    *,
) -> str:
    """Return the text content of a virtual file (for verification / loading)."""
    parts = [p for p in virtual_path.strip("/").split("/") if p]
    if not parts:
        raise ValueError("Cannot read the root")

    conn = _connect()
    try:
        parent_id = _get_root_id(conn)
        for name in parts:
            node_id = _find_child(conn, parent_id, name)
            if node_id is None:
                raise FileNotFoundError(f"No such virtual path: {virtual_path}")
            parent_id = node_id

        cur = conn.execute(
            """
            SELECT c.data
            FROM file_graph g
            JOIN file_contents c ON c.id = g.content_id
            WHERE g.id = ? AND g.type = 'file'
            """,
            (parent_id,),
        )
        row = cur.fetchone()
        if not row:
            raise FileNotFoundError(f"Not a file or empty content: {virtual_path}")
        return row[0]
    finally:
        conn.close()
