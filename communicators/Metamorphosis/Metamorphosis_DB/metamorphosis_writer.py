#!/usr/bin/env python3
"""
metamorphosis_writer.py – typed data-access library for the metamorphosis / namespace store.

Analogous to vfs_writer.py from the bootstrap stage, generalized across
the five structure types defined in metamorphosis_structures.py.

Primary surface the rest of the namespace server should call:

  - create_* helpers          (new concrete tables of a given structure type)
  - catalog registration      (object_catalog)
  - VFS read / write / list
  - document put / get
  - log append / read
  - generic flat-table helpers

All operations go through the structure-type definitions.  Connection
management and basic transactions live here; boot policy and seeding
live elsewhere.
"""


# ---------------------------------------------------------------------------
# Bring in the execution harness so we can assemble a true prefixed source
# ---------------------------------------------------------------------------
_harness_ref = PathReffs.FileRef(
    uuid="1314875b-3a56-43ef-bda0-6d126042f5c1",
    file_path="Metamorphosis/execution",
    file_name="execution_harness.py",
)

load_module, = AtomicImporter.from_path_import(
    PathReffs.resolve_path(
        _harness_ref.uuid,
        _harness_ref.file_path,
        _harness_ref.file_name,
    ),
    "load_module",
)

# ---------------------------------------------------------------------------
# Assemble the real (prefix + metamorphosis_db) source, then extract the symbol
# ---------------------------------------------------------------------------
_meta_structures_ref = PathReffs.FileRef(
    uuid="09126e37-7bd4-4b2d-a455-f44125ab9048",
    file_path="Metamorphosis/Metamorphosis_DB",
    file_name="metamorphosis_structures.py",
)

combined, _ = load_module(
    src=_meta_structures_ref,
    dst="Metamorphosis/DB/metamorphosis_structures.py",
    prefix=prefix,
)

create_core_structures, = AtomicImporter.from_code_import(
    combined,
    "metamorphosis_structures",
    "create_core_structures",
)


(
    create_document_table,
    create_flat_table,
    create_log_table,
    create_object_catalog,
    create_vfs_tables,
) = AtomicImporter.from_code_import(
    combined,
    "metamorphosis_structures",
    "create_document_table",
    "create_flat_table",
    "create_log_table",
    "create_object_catalog",
    "create_vfs_tables",
)

# ---------------------------------------------------------------------------
# Path resolution (mirrors metamorphosis_db.py)
# ---------------------------------------------------------------------------

# Default location via the file registry (same convention as every other
# tracked artefact in the tree).
_meta_db_ref = PathReffs.FileRef(
    uuid="747cfa54-45a3-4102-82ea-8610907e1f1a",
    file_path="Metamorphosis/Metamorphosis_DB",
    file_name="metamorphosis.db",
)

DEFAULT_DB_FILE = PathReffs.resolve_path(
    _meta_db_ref.uuid,
    _meta_db_ref.file_path,
    _meta_db_ref.file_name,
)

_CANDIDATES = [
    DEFAULT_DB_FILE,
    Path.cwd() / "metamorphosis.db",
]


def _default_db() -> Path:
    return next((p for p in _CANDIDATES if p.exists()), DEFAULT_DB_FILE)


def _connect(db_path: Optional[Path | str] = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path is not None else _default_db()
    if not path.exists():
        raise FileNotFoundError(
            f"{path} does not exist.\n"
            "Run metamorphosis_db.py (or metamorphosis_bootloader.py) first."
        )
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn


def _sha256(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Catalog helpers
# ---------------------------------------------------------------------------

def register_object(
    type: str,
    name: str,
    *,
    owner: str | None = None,
    pointer: str | None = None,
    metadata: dict | None = None,
    db_path: Optional[Path | str] = None,
) -> int:
    """Insert or replace a row in object_catalog. Returns the row id."""
    meta_json = json.dumps(metadata) if metadata is not None else None
    conn = _connect(db_path)
    try:
        cur = conn.execute(
            """
            INSERT INTO object_catalog (type, owner, name, pointer, metadata)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(owner, type, name) DO UPDATE SET
                pointer    = excluded.pointer,
                metadata   = excluded.metadata,
                updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            """,
            (type, owner, name, pointer, meta_json),
        )
        conn.commit()
        # lastrowid is not updated on ON CONFLICT DO UPDATE in all cases;
        # fetch the id explicitly for safety.
        row = conn.execute(
            """
            SELECT id FROM object_catalog
            WHERE type = ? AND name = ? AND owner IS ?
            """,
            (type, name, owner),
        ).fetchone()
        return int(row["id"])
    finally:
        conn.close()


def get_object(
    type: str,
    name: str,
    *,
    owner: str | None = None,
    db_path: Optional[Path | str] = None,
) -> dict | None:
    """Return a catalog row as a dict, or None if missing."""
    conn = _connect(db_path)
    try:
        row = conn.execute(
            """
            SELECT id, type, owner, name, pointer, metadata, created_at, updated_at
            FROM object_catalog
            WHERE type = ? AND name = ? AND owner IS ?
            """,
            (type, name, owner),
        ).fetchone()
        if row is None:
            return None
        d = dict(row)
        if d.get("metadata"):
            try:
                d["metadata"] = json.loads(d["metadata"])
            except (TypeError, json.JSONDecodeError):
                pass
        return d
    finally:
        conn.close()


def list_objects(
    *,
    type: str | None = None,
    owner: str | None = None,
    db_path: Optional[Path | str] = None,
) -> list[dict]:
    """List catalog entries, optionally filtered by type and/or owner."""
    conn = _connect(db_path)
    try:
        clauses: list[str] = []
        params: list[Any] = []
        if type is not None:
            clauses.append("type = ?")
            params.append(type)
        if owner is not None:
            clauses.append("owner IS ?")
            params.append(owner)

        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = conn.execute(
            f"""
            SELECT id, type, owner, name, pointer, metadata, created_at, updated_at
            FROM object_catalog
            {where}
            ORDER BY type, name
            """,
            params,
        ).fetchall()

        result = []
        for row in rows:
            d = dict(row)
            if d.get("metadata"):
                try:
                    d["metadata"] = json.loads(d["metadata"])
                except (TypeError, json.JSONDecodeError):
                    pass
            result.append(d)
        return result
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Table creation (typed)
# ---------------------------------------------------------------------------

def create_document(
    table_name: str,
    *,
    with_owner: bool = True,
    register: bool = True,
    owner: str | None = None,
    db_path: Optional[Path | str] = None,
) -> None:
    """Create a document table and optionally register it in the catalog."""
    conn = _connect(db_path)
    try:
        create_document_table(conn, table_name, with_owner=with_owner)
        conn.commit()
    finally:
        conn.close()

    if register:
        register_object(
            type="document",
            name=table_name,
            owner=owner,
            pointer=table_name,
            db_path=db_path,
        )


def create_log(
    table_name: str,
    *,
    with_owner: bool = True,
    with_stream: bool = True,
    register: bool = True,
    owner: str | None = None,
    db_path: Optional[Path | str] = None,
) -> None:
    """Create a log table and optionally register it in the catalog."""
    conn = _connect(db_path)
    try:
        create_log_table(
            conn, table_name, with_owner=with_owner, with_stream=with_stream
        )
        conn.commit()
    finally:
        conn.close()

    if register:
        register_object(
            type="log_stream",
            name=table_name,
            owner=owner,
            pointer=table_name,
            db_path=db_path,
        )


def create_mapping_table(
    table_name: str,
    columns: Sequence[tuple[str, str]],
    *,
    primary_key: str | None = "id",
    extra_constraints: Iterable[str] = (),
    register: bool = True,
    owner: str | None = None,
    db_path: Optional[Path | str] = None,
) -> None:
    """Create a flat relational table and optionally register it."""
    conn = _connect(db_path)
    try:
        create_flat_table(
            conn,
            table_name,
            columns,
            primary_key=primary_key,
            extra_constraints=extra_constraints,
        )
        conn.commit()
    finally:
        conn.close()

    if register:
        register_object(
            type="mapping",
            name=table_name,
            owner=owner,
            pointer=table_name,
            db_path=db_path,
        )


# ---------------------------------------------------------------------------
# Document operations
# ---------------------------------------------------------------------------

def put_document(
    table_name: str,
    key: str,
    data: Any,
    *,
    owner: str | None = None,
    db_path: Optional[Path | str] = None,
) -> int:
    """Insert or replace a document. data is serialized as JSON."""
    payload = json.dumps(data)
    conn = _connect(db_path)
    try:
        if owner is None:
            cur = conn.execute(
                f"""
                INSERT INTO {table_name} (key, data)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    data       = excluded.data,
                    updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                """,
                (key, payload),
            )
        else:
            cur = conn.execute(
                f"""
                INSERT INTO {table_name} (owner, key, data)
                VALUES (?, ?, ?)
                ON CONFLICT(owner, key) DO UPDATE SET
                    data       = excluded.data,
                    updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                """,
                (owner, key, payload),
            )
        conn.commit()
        return cur.lastrowid or 0
    finally:
        conn.close()


def get_document(
    table_name: str,
    key: str,
    *,
    owner: str | None = None,
    db_path: Optional[Path | str] = None,
) -> Any | None:
    """Return the deserialized document or None."""
    conn = _connect(db_path)
    try:
        if owner is None:
            row = conn.execute(
                f"SELECT data FROM {table_name} WHERE key = ?",
                (key,),
            ).fetchone()
        else:
            row = conn.execute(
                f"SELECT data FROM {table_name} WHERE owner IS ? AND key = ?",
                (owner, key),
            ).fetchone()
        if row is None:
            return None
        return json.loads(row["data"])
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Log operations
# ---------------------------------------------------------------------------

def append_log(
    table_name: str,
    payload: Any,
    *,
    owner: str | None = None,
    stream: str | None = None,
    db_path: Optional[Path | str] = None,
) -> int:
    """Append one entry. payload is stored as JSON."""
    data = json.dumps(payload)
    conn = _connect(db_path)
    try:
        # Build the insert dynamically according to which optional columns exist.
        # For simplicity we assume the table was created with the standard helpers.
        cols = ["payload"]
        vals: list[Any] = [data]
        if owner is not None:
            cols.insert(0, "owner")
            vals.insert(0, owner)
        if stream is not None:
            # stream sits after owner if both present
            idx = 1 if owner is not None else 0
            cols.insert(idx, "stream")
            vals.insert(idx, stream)

        placeholders = ", ".join("?" for _ in cols)
        col_list = ", ".join(cols)
        cur = conn.execute(
            f"INSERT INTO {table_name} ({col_list}) VALUES ({placeholders})",
            vals,
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def read_log(
    table_name: str,
    *,
    owner: str | None = None,
    stream: str | None = None,
    limit: int | None = None,
    db_path: Optional[Path | str] = None,
) -> list[dict]:
    """Return log rows (oldest first), optionally filtered."""
    conn = _connect(db_path)
    try:
        clauses: list[str] = []
        params: list[Any] = []
        if owner is not None:
            clauses.append("owner IS ?")
            params.append(owner)
        if stream is not None:
            clauses.append("stream IS ?")
            params.append(stream)

        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        lim = f"LIMIT {int(limit)}" if limit is not None else ""

        rows = conn.execute(
            f"""
            SELECT * FROM {table_name}
            {where}
            ORDER BY id ASC
            {lim}
            """,
            params,
        ).fetchall()

        result = []
        for row in rows:
            d = dict(row)
            try:
                d["payload"] = json.loads(d["payload"])
            except (TypeError, json.JSONDecodeError):
                pass
            result.append(d)
        return result
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# VFS operations (content-addressed + hierarchy)
# ---------------------------------------------------------------------------

def _ensure_content(conn: sqlite3.Connection, data: str) -> int:
    h = _sha256(data)
    size = len(data.encode("utf-8"))
    cur = conn.execute("SELECT id FROM file_contents WHERE hash = ?", (h,))
    row = cur.fetchone()
    if row:
        return int(row["id"])
    cur = conn.execute(
        "INSERT INTO file_contents (hash, data, size) VALUES (?, ?, ?)",
        (h, data, size),
    )
    return int(cur.lastrowid)


def _get_root_id(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT id FROM file_graph WHERE parent_id IS NULL AND name = ''"
    ).fetchone()
    if not row:
        # Lazy root creation so a pure metamorphosis_db init still works
        cur = conn.execute(
            """
            INSERT INTO file_graph (parent_id, name, type, content_id, access_tier)
            VALUES (NULL, '', 'dir', NULL, 'human_owner')
            """
        )
        conn.commit()
        return int(cur.lastrowid)
    return int(row["id"])


def _find_child(
    conn: sqlite3.Connection, parent_id: int | None, name: str
) -> int | None:
    row = conn.execute(
        "SELECT id FROM file_graph WHERE parent_id IS ? AND name = ?",
        (parent_id, name),
    ).fetchone()
    return int(row["id"]) if row else None


def write_file(
    virtual_path: str,
    content: str,
    *,
    access_tier: str = "agent_user",
    create_parents: bool = True,
    db_path: Optional[Path | str] = None,
) -> int:
    """Write (or replace) a file in the metamorphosis VFS. Returns file_graph id."""
    parts = [p for p in virtual_path.strip("/").split("/") if p]
    if not parts:
        raise ValueError("Cannot write to the root itself")

    filename = parts[-1]
    dir_parts = parts[:-1]

    conn = _connect(db_path)
    try:
        parent_id = _get_root_id(conn)

        for dirname in dir_parts:
            existing = _find_child(conn, parent_id, dirname)
            if existing is not None:
                parent_id = existing
            else:
                if not create_parents:
                    raise FileNotFoundError(
                        f"Directory '{dirname}' does not exist under the current parent."
                    )
                cur = conn.execute(
                    """
                    INSERT INTO file_graph
                        (parent_id, name, type, content_id, access_tier)
                    VALUES (?, ?, 'dir', NULL, ?)
                    """,
                    (parent_id, dirname, access_tier),
                )
                parent_id = int(cur.lastrowid)

        content_id = _ensure_content(conn, content)

        existing_file = _find_child(conn, parent_id, filename)
        if existing_file is not None:
            conn.execute(
                """
                UPDATE file_graph
                SET content_id = ?,
                    access_tier = ?,
                    updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
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
            node_id = int(cur.lastrowid)

        conn.commit()
        return node_id
    finally:
        conn.close()


def read_file(
    virtual_path: str,
    *,
    db_path: Optional[Path | str] = None,
) -> str:
    """Return the text content of a virtual file."""
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

        row = conn.execute(
            """
            SELECT c.data
            FROM file_graph g
            JOIN file_contents c ON c.id = g.content_id
            WHERE g.id = ? AND g.type = 'file'
            """,
            (parent_id,),
        ).fetchone()
        if not row:
            raise FileNotFoundError(f"Not a file or empty content: {virtual_path}")
        return row["data"]
    finally:
        conn.close()


def list_dir(
    virtual_path: str = "",
    *,
    db_path: Optional[Path | str] = None,
) -> list[tuple[str, str]]:
    """List immediate children of a virtual directory as (name, type) pairs."""
    parts = [p for p in virtual_path.strip("/").split("/") if p]

    conn = _connect(db_path)
    try:
        parent_id = _get_root_id(conn)
        for name in parts:
            node_id = _find_child(conn, parent_id, name)
            if node_id is None:
                raise FileNotFoundError(f"No such virtual path: {virtual_path or '/'}")
            parent_id = node_id

        rows = conn.execute(
            "SELECT name, type FROM file_graph WHERE parent_id = ? ORDER BY name",
            (parent_id,),
        ).fetchall()
        return [(r["name"], r["type"]) for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Minimal self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # ---------------------------------------------------------------------------
    # Bring in the execution harness so we can assemble a true prefixed source
    # ---------------------------------------------------------------------------
    _harness_ref = PathReffs.FileRef(
        uuid="1314875b-3a56-43ef-bda0-6d126042f5c1",
        file_path="Metamorphosis/execution",
        file_name="execution_harness.py",
    )

    load_module, = AtomicImporter.from_path_import(
        PathReffs.resolve_path(
            _harness_ref.uuid,
            _harness_ref.file_path,
            _harness_ref.file_name,
        ),
        "load_module",
    )

    # The Meta execution bootloader already wrote the prefix here
    prefix = (
        COMMUNICATORS_ROOT
        / "Metamorphosis"
        / "execution"
        / "prefix.py"
    ).read_text(encoding="utf-8")

    # ---------------------------------------------------------------------------
    # Assemble the real (prefix + metamorphosis_db) source, then extract the symbol
    # ---------------------------------------------------------------------------
    _meta_db_ref = PathReffs.FileRef(
        uuid="f306ba10-b72d-4cc9-9281-c75818f5b376",
        file_path="Metamorphosis/Metamorphosis_DB",
        file_name="metamorphosis_db.py",
    )

    combined, _ = load_module(
        src=_meta_db_ref,
        dst="Metamorphosis/DB/metamorphosis_db.py",
        prefix=prefix,
    )

    init_metamorphosis_db, = AtomicImporter.from_code_import(
        combined,
        "metamorphosis_db",
        "init_metamorphosis_db",
    )

    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "test_metamorphosis.db"
        init_metamorphosis_db(db, ephemeral=True)

        # catalog
        oid = register_object("entity", "demo", owner="system", pointer="demo", db_path=db)
        print(f"registered object id={oid}")
        print("get:", get_object("entity", "demo", owner="system", db_path=db))

        # document
        create_document("state_docs", db_path=db)
        put_document("state_docs", "config", {"theme": "dark"}, owner="u1", db_path=db)
        print("doc:", get_document("state_docs", "config", owner="u1", db_path=db))

        # log
        create_log("chat_log", db_path=db)
        append_log("chat_log", {"role": "user", "text": "hi"}, owner="u1", stream="s1", db_path=db)
        print("log:", read_log("chat_log", owner="u1", db_path=db))

        # vfs
        write_file("Runtime/hello.py", "print('hi')\n", db_path=db)
        print("vfs read:", read_file("Runtime/hello.py", db_path=db))
        print("vfs list:", list_dir("Runtime", db_path=db))

        print("self-test OK")
