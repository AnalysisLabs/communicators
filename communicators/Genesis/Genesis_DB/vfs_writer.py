#!/usr/bin/env python3
"""
vfs_writer.py – general-purpose middleman for writing programs into the Runtime VirtualFS.

Works with the schema created by VirtualFS.py + DB_layout.py.
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
import sqlite3
from pathlib import Path
from typing import Optional


# Default search order for the ephemeral DB.
# In the real communicators tree this will normally resolve to
# <communicators-root>/internal/genesis_fs.db or similar.
_CANDIDATES = [
    Path(__file__).resolve().parent.parent / "attachments" / "genesis_fs.db",
    Path(__file__).resolve().parent / "genesis_fs.db",
    Path.cwd() / "genesis_fs.db",
]


def _default_db() -> Path:
    return next((p for p in _CANDIDATES if p.exists()), _CANDIDATES[0])


def _connect(db_path: Optional[Path] = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path is not None else _default_db()
    if not path.exists():
        raise FileNotFoundError(
            f"{path} does not exist.\n"
            "Run VirtualFS.py then DB_layout.py first."
        )
    conn = sqlite3.connect(path)
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
        raise RuntimeError("Root node missing – did DB_layout.py run?")
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
    create_parents: bool = False,
    db_path: Optional[Path | str] = None,
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
    db_path : optional
        Override the location of genesis_fs.db.

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

    conn = _connect(db_path)
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
    db_path: Optional[Path | str] = None,
) -> str:
    """Return the text content of a virtual file (for verification / loading)."""
    parts = [p for p in virtual_path.strip("/").split("/") if p]
    if not parts:
        raise ValueError("Cannot read the root")

    conn = _connect(db_path)
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


def list_dir(
    virtual_path: str = "",
    *,
    db_path: Optional[Path | str] = None,
) -> list[tuple[str, str]]:
    """
    List immediate children of a virtual directory.
    Returns list of (name, type) where type is 'file' or 'dir'.
    """
    parts = [p for p in virtual_path.strip("/").split("/") if p]

    conn = _connect(db_path)
    try:
        parent_id = _get_root_id(conn)
        for name in parts:
            node_id = _find_child(conn, parent_id, name)
            if node_id is None:
                raise FileNotFoundError(f"No such virtual path: {virtual_path or '/'}")
            parent_id = node_id

        cur = conn.execute(
            "SELECT name, type FROM file_graph WHERE parent_id = ? ORDER BY name",
            (parent_id,),
        )
        return cur.fetchall()
    finally:
        conn.close()


if __name__ == "__main__":
    # Demo / self-test for the first real upload
    import sys

    std_path = (
        Path(__file__).resolve().parent.parent / "attachments" / "standard.py"
    )
    if not std_path.exists():
        print("standard.py not found for demo", file=sys.stderr)
        sys.exit(1)

    source = std_path.read_text(encoding="utf-8")
    node_id = write_file(
        "Internal_Lib/standard.py",
        source,
        access_tier="agent_user",
    )
    print(f"Wrote Internal_Lib/standard.py → node id {node_id}")

    loaded = read_file("Internal_Lib/standard.py")
    assert loaded == source, "Round-trip failed"
    print("Round-trip OK")

    print("Contents of Internal_Lib/:")
    for name, typ in list_dir("Internal_Lib"):
        print(f"  {name:30s} {typ}")
