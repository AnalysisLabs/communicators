
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
        loader = StringLoader(source, filename)
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
        manifest.info("New connection established", process_path="Metamorphosis.DB.metamorphosis_bootloader.imports!.tier2.transponder_internal.handle_connection")

        try:
            while True:
                data = self.recv(conn, 4096)
                if not data:
                    manifest.error("Connection closed by remote side", process_path="Metamorphosis.DB.metamorphosis_bootloader.imports!.tier2.transponder_internal.handle_connection")
                    break

                manifest.info(f"Received: {data}", process_path="Metamorphosis.DB.metamorphosis_bootloader.imports!.tier2.transponder_internal.handle_connection")

                # Simple response to prove bidirectional flow
                # You can change this to whatever you want for testing
                response = b"ACK\n"
                self.sendall(conn, response)

        except Exception as e:
            manifest.error(f"Connection error: {e}", process_path="Metamorphosis.DB.metamorphosis_bootloader.imports!.tier2.transponder_internal.handle_connection")


_transponder_internal = transponder_internal()

class transponder:

    # High level:

    @staticmethod
    def persistent_server(host, port):
        if host == 'localhost': host = '127.0.0.1'
        listener = _transponder_internal.create_listener(host, port)
        manifest.info("Transponder active", process_path="Metamorphosis.DB.metamorphosis_bootloader.imports!.tier2.transponder.persistent_server")

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
metamorphosis_bootloader.py – thin orchestrator for metamorphosis DB initialization.

Analogous to DB_bootloader.py from the bootstrap stage.

Current sequence:

  1. metamorphosis_db.init_metamorphosis_db   → create file + core structures
                                   (object_catalog + VFS tables)
  2. (future) metamorphosis_layout     → optional seed rows / catalog entries

Keeps the boot path dumb and ordered.  Domain data access lives in
metamorphosis_writer.py; structure definitions live in metamorphosis_structures.py.
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


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Initialize the metamorphosis / namespace SQLite database"
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="Override database path (default: metamorphosis.db next to the modules)",
    )
    parser.add_argument(
        "--persistent",
        action="store_true",
        help="Do not wipe an existing database (overrides EPHEMERAL=True)",
    )
    args = parser.parse_args(argv)

    print("→ Initializing metamorphosis database …")
    path = init_metamorphosis_db(
        db_path=args.db,
        ephemeral=not args.persistent,
    )
    mode = "persistent" if args.persistent else "ephemeral"
    print(f"→ metamorphosis database ready ({mode}) at {path}")

    # Future extension point:
    # from metamorphosis_layout import seed_metamorphosis_layout
    # seed_metamorphosis_layout(path)

    print("metamorphosis boot sequence complete")


if __name__ == "__main__":
    main()
