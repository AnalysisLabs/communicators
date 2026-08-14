#!/usr/bin/env python3
"""
metamorphosis_structures.py – single source of truth for metamorphosis DB table shapes.

Defines the five structure types used by the metamorphosis / namespace store:

  1. object_catalog   – top-level finder / registry of everything
  2. flat relational  – ordinary columns & rows (mappings, simple entities)
  3. document         – keyed JSON / nested-structure store
  4. vfs              – content-addressed blobs + hierarchical graph
  5. log              – append-only / queue-style streams

This module knows only about physical layout.  It does not open connections,
decide paths, or perform business operations.  Both initialization and the
later data-access library import from here.
"""

from __future__ import annotations

import sqlite3
from typing import Iterable, Sequence


# ---------------------------------------------------------------------------
# 1. Object catalog (the universal finder)
# ---------------------------------------------------------------------------

def create_object_catalog(conn: sqlite3.Connection) -> None:
    """Create the object_catalog table if it does not exist."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS object_catalog (
            id          INTEGER PRIMARY KEY,
            type        TEXT    NOT NULL,   -- 'vfs_node' | 'document' | 'log_stream'
                                            -- | 'mapping' | 'entity' | ...
            owner       TEXT,               -- tenant / user id; NULL = system
            name        TEXT    NOT NULL,   -- human-readable or path-like name
            pointer     TEXT,               -- how to locate the real data
                                            -- (table name, vfs path, etc.)
            metadata    TEXT,               -- optional JSON blob
            created_at  TEXT    NOT NULL
                                DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
            updated_at  TEXT    NOT NULL
                                DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),

            UNIQUE(owner, type, name)
        );
        """
    )


# ---------------------------------------------------------------------------
# 2. Flat relational / mapping tables
# ---------------------------------------------------------------------------

def create_flat_table(
    conn: sqlite3.Connection,
    table_name: str,
    columns: Sequence[tuple[str, str]],
    *,
    primary_key: str | None = "id",
    extra_constraints: Iterable[str] = (),
) -> None:
    """
    Create a simple relational table.

    Parameters
    ----------
    table_name:
        Name of the table to create.
    columns:
        Sequence of (column_name, sql_type_and_constraints) pairs,
        e.g. [("user_id", "TEXT NOT NULL"), ("server_id", "TEXT NOT NULL")].
    primary_key:
        Column to use as INTEGER PRIMARY KEY.  Pass None if you supply
        your own primary-key definition inside `columns`.
    extra_constraints:
        Additional table-level constraints (UNIQUE, CHECK, FOREIGN KEY, …).
    """
    if not table_name.isidentifier():
        raise ValueError(f"Invalid table name: {table_name!r}")

    col_defs: list[str] = []
    if primary_key is not None:
        col_defs.append(f"{primary_key} INTEGER PRIMARY KEY")

    for name, decl in columns:
        if not name.isidentifier():
            raise ValueError(f"Invalid column name: {name!r}")
        col_defs.append(f"{name} {decl}")

    col_defs.extend(extra_constraints)

    ddl = f"CREATE TABLE IF NOT EXISTS {table_name} (\n    " + ",\n    ".join(col_defs) + "\n);"
    conn.execute(ddl)


# ---------------------------------------------------------------------------
# 3. Document tables (keyed JSON / nested structures)
# ---------------------------------------------------------------------------

def create_document_table(
    conn: sqlite3.Connection,
    table_name: str,
    *,
    with_owner: bool = True,
) -> None:
    """
    Create a document-style table: owner + key → JSON value.

    Suitable for flexible state, config, process-registry entries, etc.
    """
    if not table_name.isidentifier():
        raise ValueError(f"Invalid table name: {table_name!r}")

    owner_col = "owner TEXT," if with_owner else ""
    unique = "UNIQUE(owner, key)" if with_owner else "UNIQUE(key)"

    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            id          INTEGER PRIMARY KEY,
            {owner_col}
            key         TEXT    NOT NULL,
            data        TEXT    NOT NULL,   -- JSON
            updated_at  TEXT    NOT NULL
                                DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
            {unique}
        );
        """
    )


# ---------------------------------------------------------------------------
# 4. VFS tables (content-addressed + hierarchy)
# ---------------------------------------------------------------------------

def create_vfs_tables(conn: sqlite3.Connection) -> None:
    """
    Create the classic pair:

      - file_contents  (content-addressed payloads)
      - file_graph     (hierarchical metadata)

    Layout is intentionally close to the bootstrap VirtualFS so existing
    mental models transfer cleanly.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS file_contents (
            id          INTEGER PRIMARY KEY,
            hash        TEXT    NOT NULL UNIQUE,   -- sha256 of the data
            data        TEXT    NOT NULL,
            size        INTEGER NOT NULL
        );
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS file_graph (
            id          INTEGER PRIMARY KEY,
            parent_id   INTEGER REFERENCES file_graph(id) ON DELETE CASCADE,
            name        TEXT    NOT NULL,           -- basename only
            type        TEXT    NOT NULL CHECK(type IN ('file', 'dir')),
            content_id  INTEGER REFERENCES file_contents(id),
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


# ---------------------------------------------------------------------------
# 5. Log / append-only tables
# ---------------------------------------------------------------------------

def create_log_table(
    conn: sqlite3.Connection,
    table_name: str,
    *,
    with_owner: bool = True,
    with_stream: bool = True,
) -> None:
    """
    Create an append-oriented table.

    Rows are expected to be inserted and rarely (or never) updated.
    Suitable for chat history, event streams, process histories, etc.
    """
    if not table_name.isidentifier():
        raise ValueError(f"Invalid table name: {table_name!r}")

    owner_col = "owner  TEXT," if with_owner else ""
    stream_col = "stream TEXT," if with_stream else ""

    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            id          INTEGER PRIMARY KEY,
            {owner_col}
            {stream_col}
            payload     TEXT    NOT NULL,   -- JSON or plain text
            created_at  TEXT    NOT NULL
                                DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        );
        """
    )


# ---------------------------------------------------------------------------
# Convenience: create every core structure that must exist at boot
# ---------------------------------------------------------------------------

def create_core_structures(conn: sqlite3.Connection) -> None:
    """
    Create the structures that are always present after a fresh metamorphosis DB init.

    Currently:
      - object_catalog
      - VFS tables (file_contents + file_graph)

    Concrete document, log, and flat tables are created later via the
    typed helpers when a real consumer appears.
    """
    create_object_catalog(conn)
    create_vfs_tables(conn)
