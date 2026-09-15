
# === Tier 0 (imports) ===

# === standard.py (from VirtualFS) ===
from __future__ import annotations
import argparse, ast, asyncio, ctypes, fcntl, hashlib, httpx, inspect, json, math, numpy, os, random, re, requests, secrets, select, shutil, signal, sqlite3, socket, stat, struct, subprocess, sys, tempfile, threading, time, traceback, tracemalloc, urllib, uuid, websockets, yaml
from aiohttp import web
from collections import deque, Counter
from ctypes import util as ctypes_util
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, HTTPServer
import importlib.util
from importlib.abc import SourceLoader
from pathlib import Path
from scipy.stats import norm
from types import SimpleNamespace, ModuleType
from typing import Any, Dict, Iterable, Optional, Sequence, Union
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from weakref import WeakValueDictionary
from websockets.sync.client import connect
from websockets.sync.server import serve

# === COMMUNICATORS_ROOT (resolved at prefix-build time) ===
from pathlib import Path
COMMUNICATORS_ROOT = Path('/home/prometheusd/Analysis Labs/Dev Tools/com-branches/staged/staged-2-grok/communicators')


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


# === Transponder_Codec (class) ===
class Transponder_Codec_internal:
    pass
_Transponder_Codec_internal = Transponder_Codec_internal()

class Transponder_Codec:
    """Canonical JSON-object codec. Methods are static so T1 slots and a
    later T2 Wire can both call Codec.encode_msg without holding state.
    """
    Raw = Union[None, str, bytes, bytearray, dict]

    @staticmethod
    def encode_msg(payload: dict) -> str:
        """Dict -> JSON object text. No trailing newline, no UTF-8 wrap."""
        if not isinstance(payload, dict):
            raise TypeError(f"payload must be dict, got {type(payload)!r}")
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def encode_bytes(payload: dict, newline: bool = False) -> bytes:
        """Dict -> UTF-8 JSON bytes. newline=True is NDJSON framing for
        stream slots; the extra byte is *frame*, not codec.
        """
        data = Transponder_Codec.encode_msg(payload).encode("utf-8")
        if newline:
            data += b"\n"
        return data

    @staticmethod
    def decode_msg(raw: Raw) -> dict:
        """JSON object text/bytes/dict -> dict. Empty input -> {}."""
        if raw is None or raw == b"" or raw == "":
            return {}
        if isinstance(raw, dict):
            obj: Any = raw
        else:
            if isinstance(raw, (bytes, bytearray)):
                text = raw.decode("utf-8")
            else:
                text = str(raw)
            text = text.strip()
            if not text:
                return {}
            obj = json.loads(text)
        if not isinstance(obj, dict):
            raise ValueError(f"JSON root must be an object, got {type(obj).__name__}")
        return obj

    @staticmethod
    def canonicalize(payload: dict) -> dict:
        """Round-trip through JSON so shm-style bins store the same shape
        the wire would have sent.
        """
        return Transponder_Codec.decode_msg(Transponder_Codec.encode_msg(payload))


# === Transponder_Locators (class) ===
class Transponder_Locators_internal:
    pass
_Transponder_Locators_internal = Transponder_Locators_internal()

class Transponder_Locators:
    TOKEN_RE = re.compile(r"^[0-9A-Fa-f]+$")
    BIN_DIR = "/dev/shm"

    @staticmethod
    def parse_hostport(spec: str) -> tuple[str, int]:
        spec = spec.strip()
        if "://" in spec:
            spec = spec.split("://", 1)[1]
        if spec.count(":") != 1:
            raise ValueError(f"expected host:port, got {spec!r}")
        host, port_s = spec.rsplit(":", 1)
        host = "127.0.0.1" if host in ("", "localhost") else host
        return host, int(port_s)

    @staticmethod
    def fmt_addr(addr: tuple[str, int]) -> str:
        return f"{addr[0]}:{addr[1]}"

    @staticmethod
    def parse_sockpath(spec: str) -> str:
        """Filesystem path, unix://path, or host:port mapped into /tmp."""
        spec = spec.strip()
        if spec.startswith("unix://"):
            spec = spec[len("unix://"):]
        if spec.startswith("unix:"):
            spec = spec[len("unix:"):]
        looks_like_path = (
            spec.startswith("/")
            or spec.startswith("./")
            or spec.startswith("../")
            or spec.endswith(".sock")
            or "/" in spec
        )
        if looks_like_path:
            return spec
        if spec.count(":") == 1:
            host, port_s = spec.rsplit(":", 1)
            if port_s.isdigit():
                host = "127.0.0.1" if host in ("", "localhost") else host
                return f"/tmp/unix_slot_{host}_{port_s}.sock"
        return spec

    @staticmethod
    def parse_token(spec: str) -> str:
        spec = spec.strip()
        for prefix in ("shm://", "shm:", "token:"):
            if spec.startswith(prefix):
                spec = spec[len(prefix):]
                break
        if not Transponder_Locators.TOKEN_RE.match(spec):
            raise ValueError(f"token must be hex, got {spec!r}")
        if len(spec) < 8:
            raise ValueError(f"token too short ({len(spec)}); pass a hex communicator token")
        return spec.lower()

    @staticmethod
    def shm_bin_paths(token_a: str, token_b: str) -> tuple[str, str]:
        a, b = sorted((token_a, token_b))
        stem = f"comm_slot_{a}_{b}"
        return (
            os.path.join(Transponder_Locators.BIN_DIR, f"{stem}.json"),
            os.path.join(Transponder_Locators.BIN_DIR, f"{stem}.lock"),
        )


# === SlotRefused (class) ===
class SlotRefused_internal:
    pass
_SlotRefused_internal = SlotRefused_internal()

class SlotRefused:
    @staticmethod
    def __init__(self, slot: str, verb: str, flag: str, detail: str = ""):
        self.slot = slot
        self.verb = verb
        self.flag = flag
        extra = f" ({detail})" if detail else ""
        super().__init__(f"{slot} refuses {verb}: {flag}{extra}")


# === DirWatch (class) ===
class DirWatch_internal:

    def __init__(self):
        self.IN_MODIFY = 0x00000002
        self.IN_CLOSE_WRITE = 0x00000008
        self.IN_MOVED_TO = 0x00000080
        self.IN_CREATE = 0x00000100
        self.IN_ATTRIB = 0x00000004
        self.WATCH_MASK = (
            self.IN_MODIFY
            | self.IN_CLOSE_WRITE
            | self.IN_MOVED_TO
            | self.IN_CREATE
            | self.IN_ATTRIB
        )
        self.EVENT_HDR = struct.Struct("iIII")
        self.libc = ctypes.CDLL(ctypes_util.find_library("c"), use_errno=True)
        self.libc.inotify_init.restype = ctypes.c_int
        self.libc.inotify_add_watch.restype = ctypes.c_int
        self.libc.inotify_add_watch.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint32,
        ]
        self.directory = None
        self.filename = None
        self.fd = None

    def _open(self, directory: str, filename: str):
        if self.fd is not None:
            self._close()
        self.directory = directory
        self.filename = filename
        self.fd = self.libc.inotify_init()
        if self.fd < 0:
            raise OSError("inotify_init failed")
        wd = self.libc.inotify_add_watch(
            self.fd, directory.encode("utf-8"), self.WATCH_MASK
        )
        if wd < 0:
            os.close(self.fd)
            self.fd = None
            raise OSError("inotify_add_watch failed")

    def _wait(self, timeout: float) -> bool:
        if self.fd is None:
            return False
        ready, _, _ = select.select([self.fd], [], [], timeout)
        if not ready:
            return False
        data = os.read(self.fd, 4096)
        hit = False
        off = 0
        hdr = self.EVENT_HDR
        while off + hdr.size <= len(data):
            _wd, _mask, _cookie, namelen = hdr.unpack_from(data, off)
            off += hdr.size
            name = data[off:off + namelen].split(b"\x00", 1)[0].decode("utf-8", "replace")
            off += namelen
            if name == self.filename or name == "":
                hit = True
        return hit

    def _close(self):
        if self.fd is None:
            return
        try:
            os.close(self.fd)
        except OSError:
            pass
        self.fd = None


_DirWatch_internal = DirWatch_internal()

class DirWatch:

    @staticmethod
    def open(directory: str, filename: str):
        return _DirWatch_internal._open(directory, filename)

    @staticmethod
    def wait(timeout: float) -> bool:
        return _DirWatch_internal._wait(timeout)

    @staticmethod
    def close():
        return _DirWatch_internal._close()


# === Tier 2 (imports) ===

# === TcpSlot (class) ===
class TcpSlot_internal:
    def __init__(self):
        self.name = None
        self.host = None
        self.port = None
        self.seq = 0
        self.seq_lock = threading.Lock()
        self.send_lock = threading.Lock()
        self.inbox = []
        self.inbox_lock = threading.Lock()
        self.replies = {}
        self.reply_events = {}
        self.conn = None
        self.listener = None
        self.role = None
        self.alive = threading.Event()
        self.recv_thread = None
        self.on_payload = None

    def _open(self, name: str, addr: tuple[str, int]):
        self._close()
        self.name = name
        self.host, self.port = addr
        self.seq = 0
        self.inbox = []
        self.replies = {}
        self.reply_events = {}
        self.role = None
        self.recv_thread = None
        self.on_payload = None

    def _set_on_payload(self, cb):
        self.on_payload = cb

    def _addr_s(self) -> str:
        return f"tcp://{self.host}:{self.port}"

    def _next_seq(self) -> int:
        with self.seq_lock:
            self.seq += 1
            return self.seq

    def _bind_listen(self) -> socket.socket:
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((self.host, self.port))
        listener.listen(1)
        listener.settimeout(0.3)
        return listener

    def _connect(self, timeout: float) -> socket.socket:
        conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        conn.settimeout(timeout)
        conn.connect((self.host, self.port))
        conn.settimeout(None)
        return conn

    def _attach(self, wait: float) -> None:
        deadline = time.time() + wait
        last_err = None
        while time.time() < deadline:
            try:
                self.listener = self._bind_listen()
                self.role = "listen"
                print(f"[{self.name} LISTEN] {self._addr_s()}  (waiting for peer)", flush=True)
                while time.time() < deadline:
                    try:
                        conn, peer = self.listener.accept()
                        self.conn = conn
                        print(f"[{self.name} ACCEPT] peer={peer[0]}:{peer[1]}", flush=True)
                        self._start_recv()
                        return
                    except socket.timeout:
                        continue
                raise TimeoutError(f"{self.name} bound {self._addr_s()} but nobody connected")
            except OSError as e:
                last_err = e
                if self.listener is not None:
                    try:
                        self.listener.close()
                    except Exception:
                        pass
                    self.listener = None
                try:
                    self.conn = self._connect(timeout=0.4)
                    self.role = "connect"
                    print(f"[{self.name} CONNECT] {self._addr_s()}", flush=True)
                    self._start_recv()
                    return
                except OSError as e2:
                    last_err = e2
                    time.sleep(0.15)
        raise TimeoutError(f"{self.name} never attached to {self._addr_s()}: {last_err}")

    def _wait_for_peer(self, timeout: float = 20.0) -> None:
        if self.conn is None:
            self._attach(timeout)
        print(f"[{self.name} PEER UP] role={self.role} addr={self._addr_s()}", flush=True)

    def _start_recv(self) -> None:
        self.alive.set()
        self.recv_thread = threading.Thread(target=_recv_loop, name=f"{self.name}-recv", daemon=True)
        self.recv_thread.start()

    def _recv_loop(self) -> None:
        buf = b""
        conn = self.conn
        try:
            while self.alive.is_set():
                try:
                    chunk = conn.recv(4096)
                except OSError:
                    break
                if not chunk:
                    print(f"[{self.name} PEER CLOSED]", flush=True)
                    break
                buf += chunk
                while b"\n" in buf:
                    raw, buf = buf.split(b"\n", 1)
                    if not raw.strip():
                        continue
                    try:
                        incoming = Transponder_Codec.decode_msg(raw)
                    except Exception as e:
                        print(f"[{self.name} BAD JSON] {e}: {raw!r}", flush=True)
                        continue
                    self._handle_incoming(incoming)
        finally:
            self.alive.clear()

    def _handle_incoming(self, incoming: dict) -> None:
        cb = getattr(self, "on_payload", None)
        if cb is not None and incoming.get("kind") not in ("reply", "hello"):
            try:
                cb(incoming)
            except Exception as e:
                print(f"[{self.name} HOOK FAIL] {e}", flush=True)
            if incoming.get("kind") != "chat":
                return
        kind = incoming.get("kind", "chat")
        origin = incoming.get("from", "?")
        text = incoming.get("text", "")
        seq = incoming.get("seq", "?")

        if kind == "reply":
            with self.inbox_lock:
                ev = self.reply_events.get(seq)
                self.replies[seq] = incoming
            if ev is not None:
                ev.set()
            return

        with self.inbox_lock:
            self.inbox.append(incoming)
        print(f"[{self.name} RECV] from={origin} seq={seq} text={text!r}", flush=True)

        if kind == "chat":
            try:
                self._write({
                    "ok": True,
                    "kind": "reply",
                    "heard_by": self.name,
                    "from": origin,
                    "seq": seq,
                    "text": text,
                })
            except OSError as e:
                print(f"[{self.name} REPLY FAIL] {e}", flush=True)

    def _write(self, payload: dict) -> None:
        data = Transponder_Codec.encode_bytes(payload, newline=True)
        with self.send_lock:
            self.conn.sendall(data)

    def _request_response(self, payload: dict, timeout: float = 5.0) -> dict:
        seq = payload.get("seq")
        ev = threading.Event()
        with self.inbox_lock:
            self.reply_events[seq] = ev
        try:
            self._write(payload)
            if not ev.wait(timeout):
                raise TimeoutError(f"no reply for seq={seq}")
            with self.inbox_lock:
                return self.replies.get(seq, {})
        finally:
            with self.inbox_lock:
                self.reply_events.pop(seq, None)

    def _send_text(self, text: str) -> dict:
        payload = {
            "from": self.name,
            "seq": self._next_seq(),
            "kind": "chat",
            "text": text,
            "ts": time.time(),
        }
        print(f"[{self.name} SEND] seq={payload['seq']} text={text!r}", flush=True)
        reply = self._request_response(payload)
        print(f"[{self.name} REPLY] {reply}", flush=True)
        return reply

    def _close(self) -> None:
        self.alive.clear()
        for sock in (self.conn, self.listener):
            if sock is None:
                continue
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass
        self.conn = None
        self.listener = None


_TcpSlot_internal = TcpSlot_internal()

class TcpSlot:

    @staticmethod
    def open(name: str, addr: tuple[str, int]):
        return _TcpSlot_internal._open(name, addr)

    @staticmethod
    def set_on_payload(cb):
        return _TcpSlot_internal._set_on_payload(cb)

    @staticmethod
    def addr_s() -> str:
        return _TcpSlot_internal._addr_s()

    @staticmethod
    def next_seq() -> int:
        return _TcpSlot_internal._next_seq()

    @staticmethod
    def attach(wait: float) -> None:
        return _TcpSlot_internal._attach(wait)

    @staticmethod
    def wait_for_peer(timeout: float = 20.0) -> None:
        return _TcpSlot_internal._wait_for_peer(timeout)

    @staticmethod
    def write(payload: dict) -> None:
        return _TcpSlot_internal._write(payload)

    @staticmethod
    def request_response(payload: dict, timeout: float = 5.0) -> dict:
        return _TcpSlot_internal._request_response(payload, timeout)

    @staticmethod
    def send_text(text: str) -> dict:
        return _TcpSlot_internal._send_text(text)

    @staticmethod
    def burst() -> None:
        pass

    @staticmethod
    def close() -> None:
        return _TcpSlot_internal._close()


# === UnixSlot (class) ===
class UnixSlot_internal:
    def __init__(self):
        self.name = None
        self.path = None
        self.seq = 0
        self.seq_lock = threading.Lock()
        self.send_lock = threading.Lock()
        self.inbox = []
        self.inbox_lock = threading.Lock()
        self.replies = {}
        self.reply_events = {}
        self.conn = None
        self.listener = None
        self.role = None
        self.owns_path = False
        self.alive = threading.Event()
        self.recv_thread = None
        self.on_payload = None

    def _open(self, name: str, path: str):
        self._close()
        self.name = name
        self.path = path
        self.seq = 0
        self.inbox = []
        self.replies = {}
        self.reply_events = {}
        self.role = None
        self.owns_path = False
        self.recv_thread = None
        self.on_payload = None

    def _set_on_payload(self, cb):
        self.on_payload = cb

    def _is_sock_file(self, path: str) -> bool:
        try:
            return stat.S_ISSOCK(os.stat(path).st_mode)
        except FileNotFoundError:
            return False
        except OSError:
            return False

    def _unlink_if_stale(self, path: str) -> bool:
        """Remove a leftover socket file that nothing is accepting on."""
        if not self._is_sock_file(path):
            return False
        probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            probe.connect(path)
            return False
        except ConnectionRefusedError:
            try:
                os.unlink(path)
                return True
            except FileNotFoundError:
                return False
        except OSError:
            return False
        finally:
            try:
                probe.close()
            except OSError:
                pass

    def _addr_s(self) -> str:
        return f"unix://{self.path}"

    def _next_seq(self) -> int:
        with self.seq_lock:
            self.seq += 1
            return self.seq

    def _bind_listen(self) -> socket.socket:
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(self.path)
        listener.listen(1)
        listener.settimeout(0.3)
        self.owns_path = True
        return listener

    def _connect(self, timeout: float) -> socket.socket:
        conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        conn.settimeout(timeout)
        conn.connect(self.path)
        conn.settimeout(None)
        return conn

    def _attach(self, wait: float) -> None:
        deadline = time.time() + wait
        last_err = None
        parent = os.path.dirname(self.path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        while time.time() < deadline:
            try:
                self.listener = self._bind_listen()
                self.role = "listen"
                print(f"[{self.name} LISTEN] {self._addr_s()}  (waiting for peer)", flush=True)
                while time.time() < deadline:
                    try:
                        conn, _peer = self.listener.accept()
                        self.conn = conn
                        print(f"[{self.name} ACCEPT] path={self.path}", flush=True)
                        self._start_recv()
                        return
                    except socket.timeout:
                        continue
                raise TimeoutError(f"{self.name} bound {self._addr_s()} but nobody connected")
            except OSError as e:
                last_err = e
                if self.listener is not None:
                    try:
                        self.listener.close()
                    except Exception:
                        pass
                    self.listener = None
                    self.owns_path = False
                try:
                    self.conn = self._connect(timeout=0.4)
                    self.role = "connect"
                    print(f"[{self.name} CONNECT] {self._addr_s()}", flush=True)
                    self._start_recv()
                    return
                except ConnectionRefusedError as e2:
                    last_err = e2
                    if self._unlink_if_stale(self.path):
                        print(f"[{self.name} STALE] removed leftover {self.path}", flush=True)
                    time.sleep(0.15)
                except OSError as e2:
                    last_err = e2
                    time.sleep(0.15)
        raise TimeoutError(f"{self.name} never attached to {self._addr_s()}: {last_err}")

    def _wait_for_peer(self, timeout: float = 20.0) -> None:
        if self.conn is None:
            self._attach(timeout)
        print(f"[{self.name} PEER UP] role={self.role} addr={self._addr_s()}", flush=True)

    def _start_recv(self) -> None:
        self.alive.set()
        self.recv_thread = threading.Thread(target=_recv_loop, name=f"{self.name}-recv", daemon=True)
        self.recv_thread.start()

    def _recv_loop(self) -> None:
        buf = b""
        conn = self.conn
        try:
            while self.alive.is_set():
                try:
                    chunk = conn.recv(4096)
                except OSError:
                    break
                if not chunk:
                    print(f"[{self.name} PEER CLOSED]", flush=True)
                    break
                buf += chunk
                while b"\n" in buf:
                    raw, buf = buf.split(b"\n", 1)
                    if not raw.strip():
                        continue
                    try:
                        incoming = Transponder_Codec.decode_msg(raw)
                    except Exception as e:
                        print(f"[{self.name} BAD JSON] {e}: {raw!r}", flush=True)
                        continue
                    self._handle_incoming(incoming)
        finally:
            self.alive.clear()

    def _handle_incoming(self, incoming: dict) -> None:
        cb = getattr(self, "on_payload", None)
        if cb is not None and incoming.get("kind") not in ("reply", "hello"):
            try:
                cb(incoming)
            except Exception as e:
                print(f"[{self.name} HOOK FAIL] {e}", flush=True)
            if incoming.get("kind") != "chat":
                return
        kind = incoming.get("kind", "chat")
        origin = incoming.get("from", "?")
        text = incoming.get("text", "")
        seq = incoming.get("seq", "?")

        if kind == "reply":
            with self.inbox_lock:
                ev = self.reply_events.get(seq)
                self.replies[seq] = incoming
            if ev is not None:
                ev.set()
            return

        with self.inbox_lock:
            self.inbox.append(incoming)
        print(f"[{self.name} RECV] from={origin} seq={seq} text={text!r}", flush=True)

        if kind == "chat":
            try:
                self._write({
                    "ok": True,
                    "kind": "reply",
                    "heard_by": self.name,
                    "from": origin,
                    "seq": seq,
                    "text": text,
                })
            except OSError as e:
                print(f"[{self.name} REPLY FAIL] {e}", flush=True)

    def _write(self, payload: dict) -> None:
        data = Transponder_Codec.encode_bytes(payload, newline=True)
        with self.send_lock:
            self.conn.sendall(data)

    def _request_response(self, payload: dict, timeout: float = 5.0) -> dict:
        seq = payload.get("seq")
        ev = threading.Event()
        with self.inbox_lock:
            self.reply_events[seq] = ev
        try:
            self._write(payload)
            if not ev.wait(timeout):
                raise TimeoutError(f"no reply for seq={seq}")
            with self.inbox_lock:
                return self.replies.get(seq, {})
        finally:
            with self.inbox_lock:
                self.reply_events.pop(seq, None)

    def _send_text(self, text: str) -> dict:
        payload = {
            "from": self.name,
            "seq": self._next_seq(),
            "kind": "chat",
            "text": text,
            "ts": time.time(),
        }
        print(f"[{self.name} SEND] seq={payload['seq']} text={text!r}", flush=True)
        reply = self._request_response(payload)
        print(f"[{self.name} REPLY] {reply}", flush=True)
        return reply

    def _close(self) -> None:
        self.alive.clear()
        for sock in (self.conn, self.listener):
            if sock is None:
                continue
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass
        self.conn = None
        self.listener = None
        if self.owns_path:
            try:
                os.unlink(self.path)
            except FileNotFoundError:
                pass
            self.owns_path = False


_UnixSlot_internal = UnixSlot_internal()

class UnixSlot:

    @staticmethod
    def open(name: str, path: str):
        return _UnixSlot_internal._open(name, path)

    @staticmethod
    def set_on_payload(cb):
        return _UnixSlot_internal._set_on_payload(cb)

    @staticmethod
    def addr_s() -> str:
        return _UnixSlot_internal._addr_s()

    @staticmethod
    def next_seq() -> int:
        return _UnixSlot_internal._next_seq()

    @staticmethod
    def attach(wait: float) -> None:
        return _UnixSlot_internal._attach(wait)

    @staticmethod
    def wait_for_peer(timeout: float = 20.0) -> None:
        return _UnixSlot_internal._wait_for_peer(timeout)

    @staticmethod
    def write(payload: dict) -> None:
        return _UnixSlot_internal._write(payload)

    @staticmethod
    def request_response(payload: dict, timeout: float = 5.0) -> dict:
        return _UnixSlot_internal._request_response(payload, timeout)

    @staticmethod
    def send_text(text: str) -> dict:
        return _UnixSlot_internal._send_text(text)

    @staticmethod
    def burst() -> None:
        pass

    @staticmethod
    def close() -> None:
        return _UnixSlot_internal._close()


# === WsSlot (class) ===
class WsSlot_internal:
    def __init__(self):
        self.name = None
        self.host = None
        self.port = None
        self.seq = 0
        self.seq_lock = threading.Lock()
        self.send_lock = threading.Lock()
        self.inbox = []
        self.inbox_lock = threading.Lock()
        self.replies = {}
        self.reply_events = {}
        self.ws = None
        self.server = None
        self.role = None
        self.alive = threading.Event()
        self.attached = threading.Event()
        self.recv_thread = None
        self.server_thread = None
        self.on_payload = None

    def _open(self, name: str, addr: tuple[str, int]):
        self._close()
        self.name = name
        self.host, self.port = addr
        self.seq = 0
        self.inbox = []
        self.replies = {}
        self.reply_events = {}
        self.role = None
        self.alive.clear()
        self.attached.clear()
        self.recv_thread = None
        self.server_thread = None
        self.on_payload = None

    def _set_on_payload(self, cb):
        self.on_payload = cb

    def _addr_s(self) -> str:
        return f"ws://{self.host}:{self.port}"

    def _next_seq(self) -> int:
        with self.seq_lock:
            self.seq += 1
            return self.seq

    def _server_handler(self, websocket):
        self.ws = websocket
        self.role = self.role or "listen"
        self.alive.set()
        self.attached.set()
        print(f"[{self.name} ACCEPT] {self._addr_s()}", flush=True)
        try:
            for raw in websocket:
                try:
                    incoming = Transponder_Codec.decode_msg(raw)
                except Exception as e:
                    print(f"[{self.name} BAD JSON] {e}: {raw!r}", flush=True)
                    continue
                self._handle_incoming(incoming)
        finally:
            print(f"[{self.name} PEER CLOSED]", flush=True)
            self.alive.clear()

    def _recv_loop(self) -> None:
        try:
            for raw in self.ws:
                if not self.alive.is_set():
                    break
                try:
                    incoming = Transponder_Codec.decode_msg(raw)
                except Exception as e:
                    print(f"[{self.name} BAD JSON] {e}: {raw!r}", flush=True)
                    continue
                self._handle_incoming(incoming)
        except Exception as e:
            if self.alive.is_set():
                print(f"[{self.name} RECV END] {type(e).__name__}: {e}", flush=True)
        finally:
            print(f"[{self.name} PEER CLOSED]", flush=True)
            self.alive.clear()

    def _attach(self, wait: float) -> None:
        deadline = time.time() + wait
        last_err = None
        while time.time() < deadline:
            try:
                self.server = serve(_server_handler, self.host, self.port)
                self.role = "listen"
                self.server_thread = threading.Thread(
                    target=self.server.serve_forever,
                    name=f"{self.name}-wsserve",
                    daemon=True,
                )
                self.server_thread.start()
                print(f"[{self.name} LISTEN] {self._addr_s()}  (waiting for peer)", flush=True)
                if not self.attached.wait(timeout=max(0.05, deadline - time.time())):
                    raise TimeoutError(f"{self.name} bound {self._addr_s()} but nobody connected")
                return
            except OSError as e:
                last_err = e
                self._stop_server()
                try:
                    self.ws = connect(self._addr_s(), open_timeout=0.4)
                    self.role = "connect"
                    self.alive.set()
                    self.attached.set()
                    self.recv_thread = threading.Thread(
                        target=_recv_loop,
                        name=f"{self.name}-wsrecv",
                        daemon=True,
                    )
                    self.recv_thread.start()
                    print(f"[{self.name} CONNECT] {self._addr_s()}", flush=True)
                    return
                except Exception as e2:
                    last_err = e2
                    time.sleep(0.15)
        raise TimeoutError(f"{self.name} never attached to {self._addr_s()}: {last_err}")

    def _wait_for_peer(self, timeout: float = 20.0) -> None:
        if not self.attached.is_set():
            self._attach(timeout)
        print(f"[{self.name} PEER UP] role={self.role} addr={self._addr_s()}", flush=True)

    def _handle_incoming(self, incoming: dict) -> None:
        cb = getattr(self, "on_payload", None)
        if cb is not None and incoming.get("kind") not in ("reply", "hello"):
            try:
                cb(incoming)
            except Exception as e:
                print(f"[{self.name} HOOK FAIL] {e}", flush=True)
            if incoming.get("kind") != "chat":
                return
        kind = incoming.get("kind", "chat")
        origin = incoming.get("from", "?")
        text = incoming.get("text", "")
        seq = incoming.get("seq", "?")

        if kind == "reply":
            with self.inbox_lock:
                ev = self.reply_events.get(seq)
                self.replies[seq] = incoming
            if ev is not None:
                ev.set()
            return

        with self.inbox_lock:
            self.inbox.append(incoming)
        print(f"[{self.name} RECV] from={origin} seq={seq} text={text!r}", flush=True)

        if kind == "chat":
            try:
                self._write({
                    "ok": True,
                    "kind": "reply",
                    "heard_by": self.name,
                    "from": origin,
                    "seq": seq,
                    "text": text,
                })
            except Exception as e:
                print(f"[{self.name} REPLY FAIL] {e}", flush=True)

    def _write(self, payload: dict) -> None:
        data = Transponder_Codec.encode_msg(payload)
        with self.send_lock:
            self.ws.send(data)

    def _request_response(self, payload: dict, timeout: float = 5.0) -> dict:
        seq = payload.get("seq")
        ev = threading.Event()
        with self.inbox_lock:
            self.reply_events[seq] = ev
        try:
            self._write(payload)
            if not ev.wait(timeout):
                raise TimeoutError(f"no reply for seq={seq}")
            with self.inbox_lock:
                return self.replies.get(seq, {})
        finally:
            with self.inbox_lock:
                self.reply_events.pop(seq, None)

    def _send_text(self, text: str) -> dict:
        payload = {
            "from": self.name,
            "seq": self._next_seq(),
            "kind": "chat",
            "text": text,
            "ts": time.time(),
        }
        print(f"[{self.name} SEND] seq={payload['seq']} text={text!r}", flush=True)
        reply = self._request_response(payload)
        print(f"[{self.name} REPLY] {reply}", flush=True)
        return reply

    def _stop_server(self) -> None:
        if self.server is None:
            return
        try:
            self.server.shutdown()
        except Exception:
            pass
        try:
            self.server.close()
        except Exception:
            pass
        self.server = None

    def _close(self) -> None:
        self.alive.clear()
        if self.ws is not None:
            try:
                self.ws.close()
            except Exception:
                pass
            self.ws = None
        self._stop_server()


_WsSlot_internal = WsSlot_internal()

class WsSlot:

    @staticmethod
    def open(name: str, addr: tuple[str, int]):
        return _WsSlot_internal._open(name, addr)

    @staticmethod
    def set_on_payload(cb):
        return _WsSlot_internal._set_on_payload(cb)

    @staticmethod
    def addr_s() -> str:
        return _WsSlot_internal._addr_s()

    @staticmethod
    def next_seq() -> int:
        return _WsSlot_internal._next_seq()

    @staticmethod
    def attach(wait: float) -> None:
        return _WsSlot_internal._attach(wait)

    @staticmethod
    def wait_for_peer(timeout: float = 20.0) -> None:
        return _WsSlot_internal._wait_for_peer(timeout)

    @staticmethod
    def write(payload: dict) -> None:
        return _WsSlot_internal._write(payload)

    @staticmethod
    def request_response(payload: dict, timeout: float = 5.0) -> dict:
        return _WsSlot_internal._request_response(payload, timeout)

    @staticmethod
    def send_text(text: str) -> dict:
        return _WsSlot_internal._send_text(text)

    @staticmethod
    def burst() -> None:
        pass

    @staticmethod
    def close() -> None:
        return _WsSlot_internal._close()


# === ShmSlot (class) ===
class ShmSlot_internal:
    def __init__(self):
        self.name = None
        self.mine = None
        self.peer = None
        self.bin_path = None
        self.lock_path = None
        self.seq = 0
        self.seq_lock = threading.Lock()
        self.inbox = []
        self.inbox_lock = threading.Lock()
        self.replies = {}
        self.reply_events = {}
        self.alive = threading.Event()
        self.peer_up = threading.Event()
        self.watch_thread = None
        self.on_payload = None

    def _open(self, name: str, mine: str, peer: str):
        self.name = name
        self.mine = mine
        self.peer = peer
        self.bin_path, self.lock_path = Transponder_Locators.shm_bin_paths(mine, peer)
        self.seq = 0
        self.inbox = []
        self.replies = {}
        self.reply_events = {}
        self.alive.clear()
        self.peer_up.clear()
        self.watch_thread = None
        self.on_payload = None

    def _set_on_payload(self, cb):
        self.on_payload = cb

    def _addr_s(self) -> str:
        return f"shm://{os.path.basename(self.bin_path)}"

    def _next_seq(self) -> int:
        with self.seq_lock:
            self.seq += 1
            return self.seq

    def _lock(self):
        os.makedirs(Transponder_Locators.BIN_DIR, exist_ok=True)
        lockf = open(self.lock_path, "a+")
        fcntl.flock(lockf.fileno(), fcntl.LOCK_EX)
        return lockf

    def _read_bin(self) -> dict:
        try:
            with open(self.bin_path, "r", encoding="utf-8") as f:
                raw = f.read()
        except FileNotFoundError:
            raw = ""
        if not raw.strip():
            return {"lanes": {self.mine: [], self.peer: []}, "present": {}}
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            obj = {"lanes": {self.mine: [], self.peer: []}, "present": {}}
        obj.setdefault("lanes", {})
        obj["lanes"].setdefault(self.mine, [])
        obj["lanes"].setdefault(self.peer, [])
        obj.setdefault("present", {})
        return obj

    def _write_bin(self, obj: dict) -> None:
        tmp = self.bin_path + ".tmp"
        data = json.dumps(obj, ensure_ascii=False, indent=2) + "\n"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.bin_path)

    def _mutate(self, fn):
        lockf = self._lock()
        try:
            obj = self._read_bin()
            result = fn(obj)
            self._write_bin(obj)
            return result
        finally:
            fcntl.flock(lockf.fileno(), fcntl.LOCK_UN)
            lockf.close()

    def _ensure_bin(self) -> None:
        def mark(obj):
            obj["present"][self.mine] = {"name": self.name, "ts": time.time()}
            return obj["present"]

        present = self._mutate(mark)
        print(f"[{self.name} BIN] {self.bin_path} present={list(present)}", flush=True)
        if self.peer in present:
            self.peer_up.set()

    def _attach(self, wait: float) -> None:
        self._ensure_bin()
        DirWatch.open(Transponder_Locators.BIN_DIR, os.path.basename(self.bin_path))
        self.alive.set()
        self.watch_thread = threading.Thread(
            target=_watch_loop, name=f"{self.name}-inotify", daemon=True
        )
        self.watch_thread.start()
        print(f"[{self.name} LISTEN] token={self.mine} peer={self.peer}", flush=True)

        deadline = time.time() + wait
        while time.time() < deadline and not self.peer_up.is_set():
            self._drain()
            if self.peer_up.is_set():
                break
            remaining = max(0.05, deadline - time.time())
            DirWatch.wait(timeout=min(0.5, remaining))
        if not self.peer_up.is_set():
            raise TimeoutError(f"{self.name} never saw peer token {self.peer} in {self.bin_path}")

    def _wait_for_peer(self, timeout: float = 20.0) -> None:
        if not self.peer_up.is_set():
            self._attach(timeout)
        print(f"[{self.name} PEER UP] addr={self._addr_s()}", flush=True)

    def _watch_loop(self) -> None:
        while self.alive.is_set():
            try:
                hit = DirWatch.wait(timeout=0.5)
            except Exception:
                if not self.alive.is_set():
                    break
                raise
            if self.alive.is_set() and (hit or not self.peer_up.is_set()):
                self._drain()

    def _drain(self) -> None:
        lockf = None
        items = []
        try:
            lockf = self._lock()
            obj = self._read_bin()
            if self.peer in obj.get("present", {}):
                self.peer_up.set()
            items = list(obj["lanes"].get(self.mine) or [])
            if items:
                obj["lanes"][self.mine] = []
                self._write_bin(obj)
        except Exception as e:
            print(f"[{self.name} DRAIN FAIL] {type(e).__name__}: {e}", flush=True)
            items = []
        finally:
            if lockf is not None:
                try:
                    fcntl.flock(lockf.fileno(), fcntl.LOCK_UN)
                    lockf.close()
                except Exception:
                    pass
        for raw in items:
            try:
                incoming = Transponder_Codec.decode_msg(raw)
            except Exception as e:
                print(f"[{self.name} BAD JSON] {e}: {raw!r}", flush=True)
                continue
            self._handle_incoming(incoming)

    def _handle_incoming(self, incoming: dict) -> None:
        cb = getattr(self, "on_payload", None)
        if cb is not None and incoming.get("kind") not in ("reply", "hello"):
            try:
                cb(incoming)
            except Exception as e:
                print(f"[{self.name} HOOK FAIL] {e}", flush=True)
            if incoming.get("kind") != "chat":
                return
        kind = incoming.get("kind", "chat")
        origin = incoming.get("from", "?")
        text = incoming.get("text", "")
        seq = incoming.get("seq", "?")

        if kind == "hello":
            self.peer_up.set()
            return

        if kind == "reply":
            with self.inbox_lock:
                ev = self.reply_events.get(seq)
                self.replies[seq] = incoming
            if ev is not None:
                ev.set()
            return

        with self.inbox_lock:
            self.inbox.append(incoming)
        print(f"[{self.name} RECV] from={origin} seq={seq} text={text!r}", flush=True)

        if kind == "chat":
            try:
                self._enqueue(self.peer, {
                    "ok": True,
                    "kind": "reply",
                    "heard_by": self.name,
                    "from": origin,
                    "seq": seq,
                    "text": text,
                })
            except Exception as e:
                print(f"[{self.name} REPLY FAIL] {e}", flush=True)

    def _write(self, payload: dict) -> None:
        self._enqueue(self.peer, payload)

    def _enqueue(self, dest_token: str, payload: dict) -> None:
        boxed = Transponder_Codec.canonicalize(payload)

        def append(obj):
            obj["lanes"].setdefault(dest_token, []).append(boxed)
            obj["present"][self.mine] = {"name": self.name, "ts": time.time()}

        self._mutate(append)

    def _request_response(self, payload: dict, timeout: float = 5.0) -> dict:
        seq = payload.get("seq")
        ev = threading.Event()
        with self.inbox_lock:
            self.reply_events[seq] = ev
        try:
            self._enqueue(self.peer, payload)
            if not ev.wait(timeout):
                raise TimeoutError(f"no reply for seq={seq}")
            with self.inbox_lock:
                return self.replies.get(seq, {})
        finally:
            with self.inbox_lock:
                self.reply_events.pop(seq, None)

    def _send_text(self, text: str) -> dict:
        payload = {
            "from": self.name,
            "from_token": self.mine,
            "seq": self._next_seq(),
            "kind": "chat",
            "text": text,
            "ts": time.time(),
        }
        print(f"[{self.name} SEND] seq={payload['seq']} text={text!r}", flush=True)
        reply = self._request_response(payload)
        print(f"[{self.name} REPLY] {reply}", flush=True)
        return reply

    def _close(self) -> None:
        self.alive.clear()
        DirWatch.close()

        def leave(obj):
            obj.get("present", {}).pop(self.mine, None)
            empty = not obj.get("present")
            return empty

        try:
            empty = self._mutate(leave)
        except Exception:
            empty = False
        if empty:
            for path in (self.bin_path, self.lock_path, self.bin_path + ".tmp"):
                try:
                    os.unlink(path)
                except FileNotFoundError:
                    pass


_ShmSlot_internal = ShmSlot_internal()

class ShmSlot:

    @staticmethod
    def open(name: str, mine: str, peer: str):
        return _ShmSlot_internal._open(name, mine, peer)

    @staticmethod
    def set_on_payload(cb):
        return _ShmSlot_internal._set_on_payload(cb)

    @staticmethod
    def addr_s() -> str:
        return _ShmSlot_internal._addr_s()

    @staticmethod
    def next_seq() -> int:
        return _ShmSlot_internal._next_seq()

    @staticmethod
    def ensure_bin() -> None:
        return _ShmSlot_internal._ensure_bin()

    @staticmethod
    def attach(wait: float) -> None:
        return _ShmSlot_internal._attach(wait)

    @staticmethod
    def wait_for_peer(timeout: float = 20.0) -> None:
        return _ShmSlot_internal._wait_for_peer(timeout)

    @staticmethod
    def write(payload: dict) -> None:
        return _ShmSlot_internal._write(payload)

    @staticmethod
    def request_response(payload: dict, timeout: float = 5.0) -> dict:
        return _ShmSlot_internal._request_response(payload, timeout)

    @staticmethod
    def send_text(text: str) -> dict:
        return _ShmSlot_internal._send_text(text)

    @staticmethod
    def burst() -> None:
        pass

    @staticmethod
    def close() -> None:
        return _ShmSlot_internal._close()


# === Tier 3 (imports) ===

# === Wire (class) ===
class Wire_internal:
    encode_msg = staticmethod(Transponder_Codec.encode_msg)
    decode_msg = staticmethod(Transponder_Codec.decode_msg)

    FEATURES = {
        "tcp": {"verbs": {"attach": "yes", "send": "yes", "recv": "yes"}},
        "unix": {"verbs": {"attach": "yes", "send": "yes", "recv": "yes"}},
        "ws": {"verbs": {"attach": "yes", "send": "yes", "recv": "yes"}},
        "shm": {"verbs": {"attach": "yes", "send": "yes", "recv": "yes"}},
    }

    FALLBACK = {
        "loopback": {"tcp": "unix", "unix": "shm"},
    }

    def __init__(self, favored: str = "tcp", scope: str = "loopback"):
        self.favored = favored
        self.scope = scope
        self.slot = None
        self.scheme = None
        self.on_message = None
        self.name = None

    def _make_slot(self, scheme: str, name: str, ref: dict):
        if scheme == "tcp":
            host, port = Transponder_Locators.parse_hostport(ref["inet"])
            return TcpSlot(name, (host, port))
        if scheme == "ws":
            host, port = Transponder_Locators.parse_hostport(ref["inet"])
            return WsSlot(name, (host, port))
        if scheme == "unix":
            path = Transponder_Locators.parse_sockpath(ref.get("path") or ref["inet"])
            return UnixSlot(name, path)
        if scheme == "shm":
            mine = Transponder_Locators.parse_token(ref["mine"])
            peer = Transponder_Locators.parse_token(ref["peer"])
            return ShmSlot(name, mine, peer)
        raise SlotRefused(scheme, "attach", "no", "no constructor")

    def _hook(self, incoming: dict) -> None:
        cb = self.on_message
        if cb is None:
            return
        cb(incoming)

    def require(self, slot: str, verb: str) -> None:
        row = Wire.FEATURES.get(slot)
        if row is None:
            raise SlotRefused(slot, verb, "no", "unknown slot")
        flag = row["verbs"].get(verb, "no")
        if flag != "yes":
            raise SlotRefused(slot, verb, flag)

    def candidates(self) -> list[str]:
        start = self.favored or "tcp"
        out = [start]
        seen = {start}
        cur = start
        while True:
            nxt = Wire.FALLBACK.get(self.scope, {}).get(cur)
            if nxt is None or nxt in seen:
                break
            out.append(nxt)
            seen.add(nxt)
            cur = nxt
        return out


_Wire_internal = Wire_internal()

class Wire:

    @staticmethod
    def attach(self, *, name: str, ref: dict, on_message, timeout: float = 12.0, schemes=None):
        self.name = name
        self.on_message = on_message
        errors = []
        wanted = list(schemes) if schemes is not None else self.candidates()
        for scheme in wanted:
            self.require(scheme, "attach")
            slot = None
            try:
                slot = self._make_slot(scheme, name, ref)
                slot.on_payload = self._hook
                slot.attach(timeout)
                self.slot = slot
                self.scheme = scheme
                print(f"[Wire {name}] attached scheme={scheme} {slot.addr_s()}", flush=True)
                return scheme
            except Exception as e:
                errors.append(f"{scheme}: {type(e).__name__}: {e}")
                print(f"[Wire {name}] attach fail {scheme}: {e}", flush=True)
                if slot is not None:
                    try:
                        slot.close()
                    except Exception:
                        pass
        raise RuntimeError(f"Wire.attach exhausted {wanted}: {errors}")

    @staticmethod
    def send(self, payload: dict) -> None:
        if self.slot is None:
            raise RuntimeError("Wire.send before attach")
        self.require(self.scheme, "send")
        if not hasattr(self.slot, "_write"):
            raise SlotRefused(self.scheme, "send", "no", "slot has no _write")
        self.slot._write(payload)

    @staticmethod
    def close(self) -> None:
        if self.slot is not None:
            try:
                self.slot.close()
            except Exception:
                pass
            self.slot = None

    @staticmethod
    def require(self, slot: str, verb: str) -> None:
        row = Wire.FEATURES.get(slot)
        if row is None:
            raise SlotRefused(slot, verb, "no", "unknown slot")
        flag = row["verbs"].get(verb, "no")
        if flag != "yes":
            raise SlotRefused(slot, verb, flag)

    @staticmethod
    def candidates(self) -> list[str]:
        start = self.favored or "tcp"
        out = [start]
        seen = {start}
        cur = start
        while True:
            nxt = Wire.FALLBACK.get(self.scope, {}).get(cur)
            if nxt is None or nxt in seen:
                break
            out.append(nxt)
            seen.add(nxt)
            cur = nxt
        return out


# === Tier 4 (imports) ===

# === NegativeCom (class) ===
class NegativeCom_internal:
    # Clarification: Only NegativeCom has permission to initiate websocket connections.

    def __init__(self):
        self.config = {}
        self.echo_payload = None
        self.negative = self
        self.lock = threading.Lock()
        self.socket_path = None
        self.ws = None
        self.wire = None
        self.up_queue = deque()
        self.down_queue = deque()
        self._busy_down = False
        self._busy_up = False
        self.echo_seen = set()
        self._pump_started = False
        self._pump_alive = False

    def _attach_wire(self, wire):
        self.wire = wire
        self.ws = wire
        self._start_up_pump()
        return wire

    def _start_up_pump(self):
        if self._pump_started:
            return
        self._pump_started = True
        self._pump_alive = True

        def pump():
            while self._pump_alive:
                if self.up_queue and not self._busy_up:
                    self._process_up_queue()
                time.sleep(0.05)

        threading.Thread(target=pump, name="neg-up-pump", daemon=True).start()

    def _process_down_queue(self):
        with self.lock:
            manifest.info("This was triggered.")
            if self._busy_down:
                return
            for item in list(self.down_queue):
                self._busy_down = True
                if self.down_queue[0]:
                    self._sender(self.ws, self.down_queue[0])
                    token = self.down_queue[0]['communicator_token']
                    self._wait_for_echo(token)
                    self.down_queue.popleft()
                    self._busy_down = False

    def _sender(self, ws, payload):
        body = payload if isinstance(payload, dict) else payload
        if self.wire is None:
            raise RuntimeError("NegativeCom.sender has no Wire attached")
        self.wire.send(body)
        if isinstance(body, dict) and "received" in body:
            self.echo_seen.add(body["received"])

    def _receiver(self, ws, message=None):
        if message:
            manifest.info(f'Message received: {message}')
            data = message if isinstance(message, dict) else {"message": message}
            if "received" in data:
                self.echo_seen.add(data["received"])
                return
            self.up_queue.append(data)
            manifest.info('Message appended to up_queue')

    def _process_up_queue(self):
        if self._busy_up:
            return
        manifest.info('Processing up_queue')
        for item in list(self.up_queue):
            self._busy_up = True
            if self.up_queue[0]:
                self._from_N(self.up_queue[0])
                token = self.up_queue[0].get('communicator_token') if isinstance(self.up_queue[0], dict) else None
                self._wait_for_echo(token)
                self.up_queue.popleft()
        manifest.info('up_queue processed')
        self._busy_up = False

    def _wait_for_echo(self, token):
        while True:
            time.sleep(0.1)
            if token in self.echo_seen:
                return
            for msg in list(self.up_queue):
                if isinstance(msg, dict) and msg.get('received') == token:
                    self.up_queue.remove(msg)
                    return

    def _echo(self, payload=None):
        if payload is None:
            payload = self.echo_payload
        token = payload.get('communicator_token') if isinstance(payload, dict) else None
        if token and self.ws:
            echo_payload = {'received': token}
            self._sender(self.ws, echo_payload)

    def _from_N(self, payload):
        manifest.info(payload)
        token = payload.get('communicator_token') if isinstance(payload, dict) else None
        if token and self.ws:
            echo_payload = {'received': token}
            if payload.get('echo') == 'delay':
                time.sleep(0.1)
            else:
                self._sender(self.ws, echo_payload)

    def _to_N(self, payload):
        manifest.info(payload)
        self.down_queue.append(payload)
        self._process_down_queue()


_NegativeCom_internal = NegativeCom_internal()

class NegativeCom:

    @staticmethod
    def attach_wire(wire):
        return _NegativeCom_internal._attach_wire(wire)

    @staticmethod
    def process_down_queue():
        return _NegativeCom_internal._process_down_queue()

    @staticmethod
    def sender(ws, payload):
        return _NegativeCom_internal._sender(ws, payload)

    @staticmethod
    def receiver(ws, message=None):
        return _NegativeCom_internal._receiver(ws, message)

    @staticmethod
    def process_up_queue():
        return _NegativeCom_internal._process_up_queue()

    @staticmethod
    def wait_for_echo(token):
        return _NegativeCom_internal._wait_for_echo(token)

    @staticmethod
    def echo(payload=None):
        return _NegativeCom_internal._echo(payload)

    @staticmethod
    def from_N(payload):
        return _NegativeCom_internal._from_N(payload)

    @staticmethod
    def to_N(payload):
        return _NegativeCom_internal._to_N(payload)


# === PositiveCom (class) ===
class PositiveCom_internal:
    # Clarification: PositiveCom only has permission to receive and maintain websocket connections.

    def __init__(self):
        self.config = {}
        self.echo_payload = None
        self.positive = self
        self.socket_path = None
        self.ws = None
        self.wire = None
        self.positive_addr = {}
        self.port = 0
        self.connections = {}
        self.ws_token_dict = {}
        self.ws_id = None
        self.up_queue = deque()
        self.down_queue = deque()
        self._busy_down = False
        self._busy_up = False
        self.echo_seen = set()
        self._pump_started = False
        self._pump_alive = False

    def _attach_wire(self, wire):
        self.wire = wire
        self.ws = wire
        self.connections[id(wire)] = wire
        if not self._pump_started:
            self._pump_started = True
            self._pump_alive = True

            def pump():
                while self._pump_alive:
                    if self.up_queue and not self._busy_up:
                        self._process_up_queue()
                    time.sleep(0.05)

            threading.Thread(target=pump, name="pos-up-pump", daemon=True).start()
        return wire

    def _find_pids_on_port(self, port: int) -> set:
        if shutil.which("lsof"):
            try:
                result = subprocess.run(
                    ["lsof", "-ti", f"tcp:{port}"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
            except FileNotFoundError:
                pass
            else:
                return {int(pid) for pid in result.stdout.split() if pid.strip()}
        return set()

    def _preemptive_port_cleanup(self, port: int) -> None:
        if port <= 0:
            return
        pids = self._find_pids_on_port(port)
        for pid in sorted(pids):
            if pid == os.getpid():
                continue
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                continue
            time.sleep(0.1)

    def _process_down_queue(self):
        if self._busy_down:
            return
        for item in list(self.down_queue):
            self._busy_down = True
            if self.down_queue[0]:
                payload = self.down_queue[0]
                token = payload.get('communicator_token') if isinstance(payload, dict) else None
                if token and token in self.ws_token_dict:
                    ws_id = self.ws_token_dict[token]
                    if ws_id in self.connections:
                        self._sender(self.connections[ws_id], self.down_queue[0])
                        self._wait_for_echo(token)
                        self.down_queue.popleft()
        self._busy_down = False

    def _wait_for_echo(self, token):
        while True:
            time.sleep(0.1)
            if token in self.echo_seen:
                return
            for msg in list(self.up_queue):
                if isinstance(msg, dict) and msg.get('received') == token:
                    self.up_queue.remove(msg)
                    return

    def _process_up_queue(self):
        if self._busy_up:
            return
        for item in list(self.up_queue):
            self._busy_up = True
            if self.up_queue[0]:
                self._from_P(self.up_queue[0])
                token = self.up_queue[0].get('communicator_token') if isinstance(self.up_queue[0], dict) else None
                self._wait_for_echo(token)
                self.up_queue.popleft()
        self._busy_up = False

    def _receiver(self, ws, message=None):
        if message:
            data = message if isinstance(message, dict) else {"message": message}
            token = data.get('communicator_token') if isinstance(data, dict) else None
            handle = ws if ws is not None else self.wire
            if token and handle is not None:
                self.ws_token_dict[token] = id(handle)
                self.connections[id(handle)] = handle
            if "received" in data:
                self.echo_seen.add(data["received"])
                return
            self.up_queue.append(data)
            manifest.info('Message appended to up_queue')

    def _sender(self, ws, payload):
        body = payload if isinstance(payload, dict) else payload
        if self.wire is None:
            raise RuntimeError("PositiveCom.sender has no Wire attached")
        self.wire.send(body)
        if isinstance(body, dict) and "received" in body:
            self.echo_seen.add(body["received"])

    def _echo(self, payload=None):
        if payload is None:
            payload = self.echo_payload
        token = payload.get('communicator_token') if isinstance(payload, dict) else None
        if token and self.ws:
            echo_payload = {'received': token}
            self._sender(self.ws, echo_payload)

    def _to_P(self, payload):
        manifest.info(payload)
        self.down_queue.append(payload)
        self._process_down_queue()

    def _from_P(self, payload):
        manifest.info(payload)
        token = payload.get('communicator_token') if isinstance(payload, dict) else None
        ws_id = self.ws_token_dict.get(token)
        ws = self.connections.get(ws_id)
        if token and ws:
            echo_payload = {'received': token}
            if payload.get('echo') == 'delay':
                pass
            else:
                self._sender(ws, echo_payload)


_PositiveCom_internal = PositiveCom_internal()

class PositiveCom:

    @staticmethod
    def attach_wire(wire):
        return _PositiveCom_internal._attach_wire(wire)

    @staticmethod
    def process_down_queue():
        return _PositiveCom_internal._process_down_queue()

    @staticmethod
    def wait_for_echo(token):
        return _PositiveCom_internal._wait_for_echo(token)

    @staticmethod
    def process_up_queue():
        return _PositiveCom_internal._process_up_queue()

    @staticmethod
    def receiver(ws, message=None):
        return _PositiveCom_internal._receiver(ws, message)

    @staticmethod
    def sender(ws, payload):
        return _PositiveCom_internal._sender(ws, payload)

    @staticmethod
    def echo(payload=None):
        return _PositiveCom_internal._echo(payload)

    @staticmethod
    def to_P(payload):
        return _PositiveCom_internal._to_P(payload)

    @staticmethod
    def from_P(payload):
        return _PositiveCom_internal._from_P(payload)


