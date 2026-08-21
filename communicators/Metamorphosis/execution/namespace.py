
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

    def find_communicators_root(start=None) -> Path:
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
    def _load_registry() -> list[dict]:
        root = self.find_communicators_root()
        registry_file = root / "file_registry.json"
        if not registry_file.exists():
            raise FileNotFoundError(f"file_registry.json not found at {registry_file}")
        return json.loads(registry_file.read_text(encoding="utf-8"))





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

    def _load(name: str, loader, origin: str) -> ModuleType:
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





    def _extract(module: ModuleType, items: tuple) -> tuple[Any, ...]:
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

    def from_path(path: str | Path, name: str | None = None) -> ModuleType:
        """Equivalent to: import <module>  (from a real filesystem path)"""
        path = Path(path).resolve()
        if name is None:
            name = path.stem
        source = path.read_text(encoding="utf-8")
        return self.from_code(source, name, filename=str(path))





    def from_path_import(path: str | Path, *items: str | tuple[str, str]) -> tuple[Any, ...]:
        """
        Equivalent to: from <module> import a, b as c, ...

        Examples
        --------
        a, b = self.from_path_import("math_helpers.py", "a", "b")
        x, y = self.from_path_import("math_helpers.py", ("a", "x"), ("b", "y"))
        """
        mod = self.from_path(path)
        return self._extract(mod, items)





    def from_code(source: str, name: str, filename: str | None = None) -> ModuleType:
        """Equivalent to: import <module>  (from a string)"""
        if filename is None:
            filename = f"<string:{name}>"
        loader = StringLoader(source, filename)
        return self._load(name, loader, filename)





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
        loader = StringLoader(source, filename)
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
        manifest.info("New connection established", process_path="Metamorphosis.generated.namespace.imports!.tier2.transponder_internal.handle_connection")

        try:
            while True:
                data = self.recv(conn, 4096)
                if not data:
                    manifest.error("Connection closed by remote side", process_path="Metamorphosis.generated.namespace.imports!.tier2.transponder_internal.handle_connection")
                    break

                manifest.info(f"Received: {data}", process_path="Metamorphosis.generated.namespace.imports!.tier2.transponder_internal.handle_connection")

                # Simple response to prove bidirectional flow
                # You can change this to whatever you want for testing
                response = b"ACK\n"
                self.sendall(conn, response)

        except Exception as e:
            manifest.error(f"Connection error: {e}", process_path="Metamorphosis.generated.namespace.imports!.tier2.transponder_internal.handle_connection")


_transponder_internal = transponder_internal()

class transponder:

    # High level:

    @staticmethod
    def persistent_server(host, port):
        if host == 'localhost': host = '127.0.0.1'
        listener = _transponder_internal.create_listener(host, port)
        manifest.info("Transponder active", process_path="Metamorphosis.generated.namespace.imports!.tier2.transponder.persistent_server")

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
namespace.py – kernel-stage namespace server entry point.

Refactored to use the kernel SQLite store (kernel_db / kernel_writer)
instead of the old in-memory BaseNamespace singleton.

Responsibilities
----------------
1. Ensure the kernel database exists (ephemeral in development).
2. Provide a small durable namespace API (initialize / populate / get)
   backed by document tables + the object catalog.
3. Manage the listening port and start the transponder-based
   namespace server.

The port-management helpers are intentionally left close to the
original implementation.  All durable state now goes through
kernel_writer; nothing is kept in a process-global dict.
"""

# ---------------------------------------------------------------------------
# Kernel store
# ---------------------------------------------------------------------------

# When this file lives inside the real communicators tree the imports will
# resolve normally.  While it sits in artifacts/ we keep the path flexible.
from metamorphosis_db import init_kernel_db
from metamorphosis_writer import (
    create_document,
    get_document,
    get_object,
    list_objects,
    put_document,
    register_object,
)

# Default document table used for general namespace key/value state.
_STATE_TABLE = "namespace_state"


def _ensure_kernel_db() -> Path:
    """Create the kernel database (honours EPHEMERAL) and the core state table."""
    path = init_kernel_db()
    # Make sure the primary document table exists and is catalogued.
    try:
        create_document(_STATE_TABLE, with_owner=True, register=True, owner=None)
    except Exception:
        # Table may already exist from a previous persistent run; that is fine.
        pass
    return path


# ---------------------------------------------------------------------------
# Durable namespace API  (replaces BaseNamespace + _namespaces)
# ---------------------------------------------------------------------------

def initialize_namespace(*names: str, owner: str | None = None) -> None:
    """
    Ensure each name exists as a top-level entry in the durable store.

    For every name we:
      - register an object_catalog entry of type 'namespace'
      - ensure an empty document exists under that key so later
        populate_namespace / get_namespace calls succeed.
    """
    for name in names:
        if not name or not isinstance(name, str):
            continue
        register_object(
            type="namespace",
            name=name,
            owner=owner,
            pointer=f"{_STATE_TABLE}:{name}",
        )
        # Seed an empty document if nothing is there yet.
        existing = get_document(_STATE_TABLE, name, owner=owner)
        if existing is None:
            put_document(_STATE_TABLE, name, {}, owner=owner)


def populate_namespace(
    name: str,
    data: dict[str, Any],
    *,
    owner: str | None = None,
    merge: bool = True,
) -> None:
    """
    Write (or merge) a dict into the durable namespace entry `name`.

    If merge=True (default) existing keys are preserved and updated;
    if merge=False the document is replaced entirely.
    """
    if not isinstance(data, dict):
        raise TypeError("populate_namespace expects a dict")

    current = get_document(_STATE_TABLE, name, owner=owner)
    if current is None:
        initialize_namespace(name, owner=owner)
        current = {}

    if merge and isinstance(current, dict):
        current.update(data)
        to_write = current
    else:
        to_write = data

    put_document(_STATE_TABLE, name, to_write, owner=owner)


def get_namespace(
    name: str,
    *,
    owner: str | None = None,
) -> dict[str, Any] | None:
    """Return the durable namespace document, or None if missing."""
    value = get_document(_STATE_TABLE, name, owner=owner)
    if value is None:
        return None
    if not isinstance(value, dict):
        return {"_value": value}
    return value


def list_namespaces(*, owner: str | None = None) -> list[str]:
    """Return the names of all registered namespace objects."""
    rows = list_objects(type="namespace", owner=owner)
    return [r["name"] for r in rows]


def debug_namespaces(*, owner: str | None = None) -> None:
    """Print a short summary of registered namespaces (development aid)."""
    names = list_namespaces(owner=owner)
    print("🧠 Namespaces:", sorted(names) if names else "(none)")


# ---------------------------------------------------------------------------
# Port management (unchanged in spirit from the original)
# ---------------------------------------------------------------------------

def port_in_use(host: str, port: int, timeout: float = 0.3) -> bool:
    """Check if something is listening on (host, port) using a raw TCP connect."""
    if host == "localhost":
        host = "127.0.0.1"

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        result = sock.connect_ex((host, port))
        return result == 0
    except Exception:
        return False
    finally:
        sock.close()


def kill_port(host: str = "localhost", port: int = 8765) -> None:
    """Aggressively kill anything listening on the port (Linux/macOS)."""
    if host == "localhost":
        host = "127.0.0.1"

    print(f"🔪 Checking/killing port {port}...")
    os.system(f"lsof -t -i:{port} | xargs kill -9 2>/dev/null || true")
    time.sleep(0.4)


# ---------------------------------------------------------------------------
# Server start
# ---------------------------------------------------------------------------

def _start_ns_server(host: str = "localhost", port: int = 8765) -> None:
    """
    Start the namespace server using the transponder abstraction.

    The transponder import is deferred so that pure data-plane use of this
    module (initialize/populate/get) does not require the full communicator
    runtime to be present.
    """
    try:
        # In the real tree this resolves through the prefix / import system.
        # While developing in isolation the import may fail; that is acceptable.
        transponder.persistent_server(host, port)
    except Exception as e:
        # Prefer Manifest when available; fall back to stderr.
        try:
            manifest.error(f"Failed to start namespace server: {e}", process_path="Metamorphosis.generated.namespace.user_program._start_ns_server")
        except Exception:
            print(f"Failed to start namespace server: {e}", file=sys.stderr)


def main() -> None:
    """Boot sequence for the namespace server process."""
    print("→ Ensuring kernel database …")
    db_path = _ensure_kernel_db()
    print(f"→ Kernel DB ready at {db_path}")

    host, port = "localhost", 8765
    if port_in_use(host, port):
        kill_port(host, port)

    print(f"→ Starting namespace server on {host}:{port}")
    _start_ns_server(host, port)


if __name__ == "__main__":
    main()
else:
    # When imported as a library (e.g. by other kernel-stage code) we still
    # make sure the DB and core state table exist, but we do not bind the port.
    try:
        _ensure_kernel_db()
    except Exception as e:
        print(f"namespace: kernel DB init deferred/failed: {e}", file=sys.stderr)
