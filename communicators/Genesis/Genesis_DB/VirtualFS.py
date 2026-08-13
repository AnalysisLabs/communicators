#!/usr/bin/env python3
"""Initialize ephemeral SQLite VirtualFS database.

Creates the two tables required by the runtime VirtualFS design:
  - file_contents  (content-addressed payload storage)
  - file_graph     (filesystem tree + metadata)

No other tables, no seed data, no permission logic.
The database is intended to be created fresh on every run.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

# This module now lives inside the Database/ directory itself.
# The SQLite file is therefore simply a sibling of this script.
DB_FILE = Path(__file__).resolve().parent / "runtime_fs.db"

def init_runtime_fs() -> Path:
    """Create (or recreate) the VirtualFS database and its two tables.

    Returns the absolute path of the database file that was created.
    """
    path = DB_FILE
    path.parent.mkdir(parents=True, exist_ok=True)

    # Ephemeral by design: wipe any previous instance.
    if path.exists():
        path.unlink()

    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA foreign_keys = ON;")

        # ------------------------------------------------------------------
        # file_contents  – content-addressed storage
        # ------------------------------------------------------------------
        conn.execute(
            """
            CREATE TABLE file_contents (
                id          INTEGER PRIMARY KEY,
                hash        TEXT    NOT NULL UNIQUE,   -- sha256 of the data
                data        TEXT    NOT NULL,
                size        INTEGER NOT NULL
            );
            """
        )

        # ------------------------------------------------------------------
        # file_graph  – filesystem tree + metadata
        # ------------------------------------------------------------------
        conn.execute(
            """
            CREATE TABLE file_graph (
                id          INTEGER PRIMARY KEY,
                parent_id   INTEGER REFERENCES file_graph(id) ON DELETE CASCADE,  -- NULL = root
                name        TEXT    NOT NULL,                                     -- basename only
                type        TEXT    NOT NULL CHECK(type IN ('file', 'dir')),
                content_id  INTEGER REFERENCES file_contents(id),                 -- NULL for directories
                access_tier TEXT    NOT NULL DEFAULT 'others'
                                    CHECK(access_tier IN (
                                        'human_owner', 'agent_user', 'group', 'others'
                                    )),
                created_at  TEXT    NOT NULL
                                    DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),

                UNIQUE(parent_id, name)
            );
            """
        )

        # ------------------------------------------------------------------
        # Root node (required by vfs_writer._get_root_id)
        # ------------------------------------------------------------------
        conn.execute(
            """
            INSERT INTO file_graph
                (parent_id, name, type, content_id, access_tier)
            VALUES (NULL, '', 'dir', NULL, 'human_owner')
            """
        )

        conn.commit()
    finally:
        conn.close()

    return path


if __name__ == "__main__":
    db = init_runtime_fs()
    print(f"Initialized VirtualFS database at: {db}")
