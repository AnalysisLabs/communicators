#!/usr/bin/env python3
"""
seed_layout.py – push the initial directory skeleton into file_graph.

Must be run *after* VirtualFS.py has created the empty tables.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

# Same location convention as VirtualFS.py
DB_FILE = Path(__file__).resolve().parent / "runtime_fs.db"

# Boot order of the Communicators OS
LAYOUT = [
    "Bootloader",
    "Database",
    "Namespace",
    "Metamorphosis",
    "Runtime",
    "Homeostasis",
]


def _insert_node(
    conn: sqlite3.Connection,
    *,
    parent_id: int | None,
    name: str,
    node_type: str = "dir",
    tier: str = "agent_user",
    content_id: int | None = None,
) -> int:
    """Insert one node and return its new id."""
    cur = conn.execute(
        """
        INSERT INTO file_graph
            (parent_id, name, type, content_id, access_tier)
        VALUES (?, ?, ?, ?, ?)
        """,
        (parent_id, name, node_type, content_id, tier),
    )
    return cur.lastrowid


def seed_layout() -> None:
    if not DB_FILE.exists():
        raise FileNotFoundError(
            f"{DB_FILE} does not exist.\n"
            "Run VirtualFS.py first so the tables are created."
        )

    conn = sqlite3.connect(DB_FILE)
    try:
        conn.execute("PRAGMA foreign_keys = ON;")

        # 1. Root (required by the schema)
        root_id = _insert_node(
            conn,
            parent_id=None,
            name="",
            tier="human_owner",
        )

        # 2. Top-level system directories in exact boot order
        for name in LAYOUT:
            _insert_node(
                conn,
                parent_id=root_id,
                name=name,
                tier="agent_user",
            )

        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    seed_layout()
    print("Layout seeded.")
