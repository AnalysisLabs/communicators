
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
        manifest.info("New connection established", process_path="Metamorphosis.DB.metamorphosis_structures.imports!.tier2.transponder_internal.handle_connection")

        try:
            while True:
                data = self.recv(conn, 4096)
                if not data:
                    manifest.error("Connection closed by remote side", process_path="Metamorphosis.DB.metamorphosis_structures.imports!.tier2.transponder_internal.handle_connection")
                    break

                manifest.info(f"Received: {data}", process_path="Metamorphosis.DB.metamorphosis_structures.imports!.tier2.transponder_internal.handle_connection")

                # Simple response to prove bidirectional flow
                # You can change this to whatever you want for testing
                response = b"ACK\n"
                self.sendall(conn, response)

        except Exception as e:
            manifest.error(f"Connection error: {e}", process_path="Metamorphosis.DB.metamorphosis_structures.imports!.tier2.transponder_internal.handle_connection")


_transponder_internal = transponder_internal()

class transponder:

    # High level:

    @staticmethod
    def persistent_server(host, port):
        if host == 'localhost': host = '127.0.0.1'
        listener = _transponder_internal.create_listener(host, port)
        manifest.info("Transponder active", process_path="Metamorphosis.DB.metamorphosis_structures.imports!.tier2.transponder.persistent_server")

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
            updated_at  TEXT    NOT NULL
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
