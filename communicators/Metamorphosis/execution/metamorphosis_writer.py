
# === Tier 0 (imports) ===

# === standard.py (from VirtualFS) ===
from __future__ import annotations
import argparse, ast, asyncio, hashlib, httpx, inspect, json, math, numpy, os, random, re, requests, secrets, shutil, signal, sqlite3, socket, struct, subprocess, sys, tempfile, threading, time, traceback, tracemalloc, uuid, websockets, yaml
from aiohttp import web
from collections import deque, Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, HTTPServer
import importlib.util
from importlib.abc import SourceLoader
from pathlib import Path
from scipy.stats import norm
from types import SimpleNamespace, ModuleType
from typing import Any, Dict, Iterable, Optional, Sequence
from weakref import WeakValueDictionary
from websockets.sync.server import serve

# === COMMUNICATORS_ROOT (resolved at prefix-build time) ===
from pathlib import Path
COMMUNICATORS_ROOT = Path('/home/prometheusd/Analysis Labs/Dev Tools/com-branches/staged/staged-1/communicators')

# === Tier 1 (imports) ===

# === PathReffs (class) ===
class PathReffs_internal:

    # ---------------------------------------------------------------------------
    # Reff Usage
    # ---------------------------------------------------------------------------

    def find_communicators_root(self, start=None) -> Path:
        # Prefer explicitly defined COMMUNICATORS_ROOT when present
        root = globals().get("COMMUNICATORS_ROOT")
        if root is not None:
            return Path(root).absolute()

        d = Path(start or Path.cwd()).absolute()
        while d != Path("/"):
            if d.name == "communicators":
                return d
            d = d.parent
        return Path.cwd()

    @lru_cache(maxsize=1)
    def _load_registry(self) -> list[dict]:
        root = self.find_communicators_root()
        registry_file = root / "file_registry.json"
        if not registry_file.exists():
            raise FileNotFoundError(f"file_registry.json not found at {registry_file}")
        return json.loads(registry_file.read_text(encoding="utf-8"))

    def resolve_path(
        self,
        uuid: str,
        file_path: str,
        file_name: str,
    ) -> Path:
        """
        Strict lookup by the full identity triple.
        Returns the absolute Path computed from the current communicators root
        + the relative file_path + file_name stored in the registry.

        Raises FileNotFoundError on any mismatch (broken reference).
        """
        registry = self._load_registry()
        root = self.find_communicators_root()

        for entry in registry:
            if (entry["uuid"] == uuid
                and entry["file_path"] == file_path
                and entry["file_name"] == file_name):

                if file_path:
                    return root / file_path / file_name
                else:
                    return Path(root / file_name)

        raise FileNotFoundError(
            f"Broken reference: uuid={uuid!r}, file_path={file_path!r}, file_name={file_name!r}"
        )


_PathReffs_internal = PathReffs_internal()

class PathReffs:

    # ---------------------------------------------------------------------------
    # Reff Making
    # ---------------------------------------------------------------------------

    @dataclass(frozen=True)
    class FileRef:
        """
        Immutable reference to a file tracked in file_registry.json.

        The three fields form the stable identity.
        """
        uuid: str
        file_path: str
        file_name: str

        def __str__(self) -> str:
            return f"{self.file_path}/{self.file_name}" if self.file_path else self.file_name

        @classmethod
        def from_entry(cls, entry: dict) -> FileRef:
            """Convenience constructor from a raw registry dict."""
            return cls(
                uuid=entry["uuid"],
                file_path=entry["file_path"],
                file_name=entry["file_name"],
            )

    @staticmethod
    def resolve_path(
        uuid: str,
        file_path: str,
        file_name: str,
    ) -> Path:
        """
        Strict lookup by the full identity triple.
        Returns the absolute Path computed from the current communicators root
        + the relative file_path + file_name stored in the registry.

        Raises FileNotFoundError on any mismatch (broken reference).
        """
        registry = _PathReffs_internal._load_registry()
        root = _PathReffs_internal.find_communicators_root()

        for entry in registry:
            if (entry["uuid"] == uuid
                and entry["file_path"] == file_path
                and entry["file_name"] == file_name):

                if file_path:
                    return root / file_path / file_name
                else:
                    return Path(root / file_name)

        raise FileNotFoundError(
            f"Broken reference: uuid={uuid!r}, file_path={file_path!r}, file_name={file_name!r}"
        )


# === AtomicImporter (class) ===
class AtomicImporter_internal:

    # ---------------------------------------------------------------------------
    # Shared core
    # ---------------------------------------------------------------------------

    def _load(self, name: str, loader, origin: str) -> ModuleType:
        if name in sys.modules:
            return sys.modules[name]

        spec = importlib.util.spec_from_loader(name, loader, origin=origin)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module          # must happen before exec
        try:
            spec.loader.exec_module(module)
        except Exception:
            del sys.modules[name]           # clean up on failure
            raise
        return module

    def _extract(self, module: ModuleType, items: tuple) -> tuple[Any, ...]:
        """
        items may contain:
          - "name"              → returns module.name
          - ("name", "alias")   → returns module.name  (caller binds it to alias)
        """
        result = []
        for item in items:
            if isinstance(item, tuple):
                name, _alias = item          # alias is only used by the caller
                result.append(getattr(module, name))
            else:
                result.append(getattr(module, item))
        return tuple(result)

    # ---------------------------------------------------------------------------
    # Code-blob version
    # ---------------------------------------------------------------------------

    class StringLoader(SourceLoader):
        def __init__(self, source: str, filename: str):
            self.source = source
            self.filename = filename

        def get_data(self, path: str) -> bytes:
            return self.source.encode("utf-8")

        def get_filename(self, fullname: str) -> str:
            return self.filename

    # ---------------------------------------------------------------------------
    # Path version
    # ---------------------------------------------------------------------------

    def from_path(self, path: str | Path, name: str | None = None) -> ModuleType:
        """Equivalent to: import <module>  (from a real filesystem path)"""
        path = Path(path).resolve()
        if name is None:
            name = path.stem
        source = path.read_text(encoding="utf-8")
        return self.from_code(source, name, filename=str(path))

    def from_path_import(self, path: str | Path, *items: str | tuple[str, str]) -> tuple[Any, ...]:
        """
        Equivalent to: from <module> import a, b as c, ...

        Examples
        --------
        a, b = self.from_path_import("math_helpers.py", "a", "b")
        x, y = self.from_path_import("math_helpers.py", ("a", "x"), ("b", "y"))
        """
        mod = self.from_path(path)
        return self._extract(mod, items)

    def from_code(self, source: str, name: str, filename: str | None = None) -> ModuleType:
        """Equivalent to: import <module>  (from a string)"""
        if filename is None:
            filename = f"<string:{name}>"
        loader = self.StringLoader(source, filename)
        return self._load(name, loader, filename)

    def from_code_import(
        self,
        source: str,
        name: str,
        *items: str | tuple[str, str],
        filename: str | None = None,
    ) -> tuple[Any, ...]:
        """
        Equivalent to: from <module> import a, b as c, ...  (from a string)

        Examples
        --------
        a, b = self.from_code_import(src, "mymod", "a", "b")
        x, y = self.from_code_import(src, "mymod", ("a", "x"), ("b", "y"))
        """
        mod = self.from_code(source, name, filename=filename)
        return self._extract(mod, items)


_AtomicImporter_internal = AtomicImporter_internal()

class AtomicImporter:

    # ---------------------------------------------------------------------------
    # Path version
    # ---------------------------------------------------------------------------

    @staticmethod
    def from_path(path: str | Path, name: str | None = None) -> ModuleType:
        """Equivalent to: import <module>  (from a real filesystem path)"""
        path = Path(path).resolve()
        if name is None:
            name = path.stem
        source = path.read_text(encoding="utf-8")
        return _AtomicImporter_internal.from_code(source, name, filename=str(path))

    @staticmethod
    def from_path_import(path: str | Path, *items: str | tuple[str, str]) -> tuple[Any, ...]:
        """
        Equivalent to: from <module> import a, b as c, ...

        Examples
        --------
        a, b = _AtomicImporter_internal.from_path_import("math_helpers.py", "a", "b")
        x, y = _AtomicImporter_internal.from_path_import("math_helpers.py", ("a", "x"), ("b", "y"))
        """
        mod = _AtomicImporter_internal.from_path(path)
        return _AtomicImporter_internal._extract(mod, items)

    @staticmethod
    def from_code(source: str, name: str, filename: str | None = None) -> ModuleType:
        """Equivalent to: import <module>  (from a string)"""
        if filename is None:
            filename = f"<string:{name}>"
        loader = _AtomicImporter_internal.StringLoader(source, filename)
        return _AtomicImporter_internal._load(name, loader, filename)

    @staticmethod
    def from_code_import(
        source: str,
        name: str,
        *items: str | tuple[str, str],
        filename: str | None = None,
    ) -> tuple[Any, ...]:
        """
        Equivalent to: from <module> import a, b as c, ...  (from a string)

        Examples
        --------
        a, b = _AtomicImporter_internal.from_code_import(src, "mymod", "a", "b")
        x, y = _AtomicImporter_internal.from_code_import(src, "mymod", ("a", "x"), ("b", "y"))
        """
        mod = _AtomicImporter_internal.from_code(source, name, filename=filename)
        return _AtomicImporter_internal._extract(mod, items)


# === Manifest (class) ===
class manifest_internal:

    def _get_internal_files(self):
        parent_dir = Path(__file__).parent
        files = set()
        if parent_dir.exists():
            for f in parent_dir.iterdir():
                files.add(f.name)
        return files

    def _find_external_caller(self, internal_files):
        frame = inspect.currentframe()
        while frame:
            caller_file = frame.f_code.co_filename.split('/')[-1]
            if caller_file not in internal_files and "/usr/lib/python" not in frame.f_code.co_filename:
                return f'{frame.f_code.co_filename}.{frame.f_code.co_qualname}'
            frame = frame.f_back
        return None

    def _log(self, level, message, process_path=None):
        if process_path is None:
            frame = inspect.currentframe().f_back.f_back
            filename = frame.f_code.co_filename.rsplit('/', 1)[-1]
            # func_name = frame.f_code.co_name
            class_name = frame.f_locals.get('self').__class__.__name__ if 'self' in frame.f_locals else ''
            func_name = frame.f_code.co_qualname
            if class_name and func_name.startswith(class_name + '.'):
                func_name = func_name[len(class_name) + 1:]
            func_name = func_name.replace('.<locals>', '.')
            class_name = frame.f_locals.get('self').__class__.__name__ if 'self' in frame.f_locals else ''
            process_path = f'[{filename}.{class_name}.{func_name}]' if class_name else f'[{filename}.{func_name}]'
            internal_files = self._get_internal_files()
            if filename in internal_files:
                external_caller = self._find_external_caller(internal_files)
                if external_caller:
                    process_path = f'[{process_path[1:-1]} from {external_caller}]'
            process_path = process_path.replace('..', '.')
        utc_ts = datetime.now(timezone.utc).isoformat()
        if level:
            print(f'{utc_ts} {level} {process_path} {message}')
        else:
            print(f'{utc_ts} {process_path} {message}')


_manifest_internal = manifest_internal()

class manifest:

    @staticmethod
    def debug(*args, process_path=None):
        message = ' '.join(str(arg) for arg in args)
        _manifest_internal._log('DEBUG', message, process_path=process_path)

    @staticmethod
    def info(*args, process_path=None):
        message = ' '.join(str(arg) for arg in args)
        _manifest_internal._log('INFO', message, process_path=process_path)

    @staticmethod
    def warning(*args, process_path=None):
        message = ' '.join(str(arg) for arg in args)
        _manifest_internal._log('WARNING', message, process_path=process_path)

    @staticmethod
    def error(*args, process_path=None):
        message = ' '.join(str(arg) for arg in args)
        _manifest_internal._log('ERROR', message, process_path=process_path)

    @staticmethod
    def critical(*args, process_path=None):
        message = ' '.join(str(arg) for arg in args)
        _manifest_internal._log('CRITICAL', message, process_path=process_path)

    @staticmethod
    def printer(*args, process_path=None):
        message = ' '.join(str(arg) for arg in args)
        _manifest_internal._log('PRINTER', message, process_path=process_path)

    @staticmethod
    def json(*args, process_path=None):
        messages = []
        for arg in args:
            try:
                if isinstance(arg, str):
                    json.loads(arg)
                messages.append(json.dumps(arg))
            except:
                messages.append('{invalid json}')
        _manifest_internal._log('JSON', ' '.join(messages), process_path=process_path)

    @staticmethod
    def freight(*args, process_path=None):
        messages = []
        for arg in args:
            if isinstance(arg, freight) and hasattr(arg):
                messages.append(arg)
            else:
                try:
                    f = freight.upgrades(arg)
                    messages.append(f)
                except:
                    messages.append('{invalid freight}')
        _manifest_internal._log('FREIGHT', ' '.join(messages), process_path=process_path)


# === Tier 2 (imports) ===

# === Transponder (class) ===
class transponder_internal:
    # Terms:

    def is_complete(self, response):
        """Simple delimiter check for the current placeholder protocol."""
        if isinstance(response, dict): response = json.dumps(response).encode()
        return response.endswith(b'\n') or b'ACK' in response

    # Utils:

    def create_listener(self, ip, port):
        l = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        l.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        l.bind((ip, port))
        l.listen(5)
        return l

    def accept_connection(self, listener):
        """
        Accepts an incoming connection on the listening endpoint.
        Returns the new connected endpoint (socket object) that can be used
        for send/recv with the remote side.
        """
        conn, addr = listener.accept()
        return conn

    def connect_to(self, host, port):
        """
        Actively connects to a remote listening endpoint (host, port).
        Returns the connected endpoint that can be used for send/recv.
        """
        conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        conn.connect((host, port))
        return conn

    def sendall(self, conn, data):
        """
        Send all bytes on the given connected endpoint.
        Blocks until all data is sent or an error occurs.
        """
        conn.sendall(data)

    def recv(self, conn, size):
        """
        Receive up to `size` bytes from the given connected endpoint.
        Returns the bytes received (may be fewer than `size`).
        """
        return conn.recv(size)

    def handle_connection(self, conn):
        """
        Minimal proof-of-concept handler.
        Receives data, prints it, and optionally echoes back a simple ACK.
        Good enough to validate that connections are working and bidirectional.
        """
        manifest.info("New connection established")

        try:
            while True:
                data = self.recv(conn, 4096)
                if not data:
                    manifest.error("Connection closed by remote side")
                    break

                manifest.info(f"Received: {data}")

                # Simple response to prove bidirectional flow
                # You can change this to whatever you want for testing
                response = b"ACK\n"
                self.sendall(conn, response)

        except Exception as e:
            manifest.error(f"Connection error: {e}")


_transponder_internal = transponder_internal()

class transponder:

    # High level:

    @staticmethod
    def persistent_server(host, port):
        if host == 'localhost': host = '127.0.0.1'
        listener = _transponder_internal.create_listener(host, port)
        manifest.info("Transponder active")

        while True:
            conn = _transponder_internal.accept_connection(listener)
            # Hand off or handle directly
            _transponder_internal.handle_connection(conn)

    @staticmethod
    def send_and_close(host, port, data):
        if host == 'localhost': host = '127.0.0.1'
        conn = _transponder_internal.connect_to(host, port)
        conn.sendall(data)           # fire-and-forget style
        conn.close()

    @staticmethod
    def request_response(host, port, data):
        if host == 'localhost': host = '127.0.0.1'
        conn = _transponder_internal.connect_to(host, port)
        conn.sendall(data)

        response = b""
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                break
            response += chunk
            if _transponder_internal.is_complete(response):   # your simple check
                break

        conn.close()
        return response


# ==================== (USER PROGRAM) ====================
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
