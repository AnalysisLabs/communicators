
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
COMMUNICATORS_ROOT = Path('/home/prometheusd/Analysis Labs/Dev Tools/com-branches/staged/staged-2/communicators')


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
    @staticmethod
    def encode_msg(payload: dict) -> str:
        """Dict -> JSON object text. No trailing newline, no UTF-8 wrap."""
        if not isinstance(payload, dict):
            raise TypeError(f"payload must be dict, got {type(payload)!r}")
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
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
    @staticmethod
    def fmt_addr(addr: tuple[str, int]) -> str:
        return f"{addr[0]}:{addr[1]}"

    @staticmethod
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
    IN_MODIFY = 0x00000002
    IN_CLOSE_WRITE = 0x00000008
    IN_MOVED_TO = 0x00000080
    IN_CREATE = 0x00000100
    IN_ATTRIB = 0x00000004
    WATCH_MASK = IN_MODIFY | IN_CLOSE_WRITE | IN_MOVED_TO | IN_CREATE | IN_ATTRIB
    EVENT_HDR = struct.Struct("iIII")
    libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
    libc.inotify_init.restype = ctypes.c_int
    libc.inotify_add_watch.restype = ctypes.c_int
    libc.inotify_add_watch.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32]

    def __init__(self, directory: str, filename: str):
        self.directory = directory
        self.filename = filename
        self.fd = DirWatch.libc.inotify_init()
        if self.fd < 0:
            raise OSError("inotify_init failed")
        wd = DirWatch.libc.inotify_add_watch(
            self.fd, directory.encode("utf-8"), DirWatch.WATCH_MASK
        )
        if wd < 0:
            os.close(self.fd)
            raise OSError("inotify_add_watch failed")


_DirWatch_internal = DirWatch_internal()

class DirWatch:

    @staticmethod
    def wait(self, timeout: float) -> bool:
        ready, _, _ = select.select([self.fd], [], [], timeout)
        if not ready:
            return False
        data = os.read(self.fd, 4096)
        hit = False
        off = 0
        hdr = DirWatch.EVENT_HDR
        while off + hdr.size <= len(data):
            _wd, _mask, _cookie, namelen = hdr.unpack_from(data, off)
            off += hdr.size
            name = data[off:off + namelen].split(b"\x00", 1)[0].decode("utf-8", "replace")
            off += namelen
            if name == self.filename or name == "":
                hit = True
        return hit

    @staticmethod
    def close(self):
        try:
            os.close(self.fd)
        except OSError:
            pass


# === UdpMail (class) ===
class UdpMail_internal:
    pass
_UdpMail_internal = UdpMail_internal()

class UdpMail:
    """File-local helpers used by both Station and Tuner.

    This is the @modulemethod role: a class both peer classes qualify
    against. Stage C will not rewrite these calls; they stay
    UdpMail.bind_udp(...).
    """

    @staticmethod
    @staticmethod
    def bind_udp(addr: tuple[str, int]) -> socket.socket:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(addr)
        sock.settimeout(0.3)
        return sock


# === Mailbox (class) ===
class Mailbox_internal:
    """Two things live here: a client registry, and one queue per client.

    Only the server process touches this. The client never sees /dev/shm.
    """

    def __init__(self, server_name: str, default_poll: float):
        self.server_name = server_name
        self.mailbox_id = str(uuid.uuid4())
        self.default_poll = float(default_poll)
        self.lock = threading.Lock()
        self.clients: dict[str, dict] = {}
        self.lanes: dict[str, list] = {}
        self.bin_path = os.path.join(Transponder_Locators.BIN_DIR, f"http_mailbox_{self.mailbox_id}.json")
        self._persist()

    def _snapshot(self) -> dict:
        return {
            "mailbox": self.mailbox_id,
            "server": self.server_name,
            "clients": dict(self.clients),
            "lanes": {name: list(items) for name, items in self.lanes.items()},
        }

    def _persist(self) -> None:
        try:
            os.makedirs(Transponder_Locators.BIN_DIR, exist_ok=True)
            tmp = self.bin_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._snapshot(), fh, ensure_ascii=False, indent=2)
            os.replace(tmp, self.bin_path)
        except OSError:
            pass

    def expire_locked(self, now: float) -> list[tuple[str, dict]]:
        dropped = []
        for name, items in self.lanes.items():
            poll_s = self.clients.get(name, {}).get("poll", self.default_poll)
            keep = []
            for item in items:
                age = now - float(item.get("enqueued_at", now))
                if age > poll_s:
                    dropped.append((name, item.get("msg", {})))
                else:
                    keep.append(item)
            self.lanes[name] = keep
        return dropped


_Mailbox_internal = Mailbox_internal()

class Mailbox:

    @staticmethod
    def unlink(self) -> None:
        for path in (self.bin_path, self.bin_path + ".tmp"):
            try:
                os.unlink(path)
            except OSError:
                pass

    @staticmethod
    def tune(self, name: str, poll: float | None) -> dict:
        poll_s = self.default_poll if poll is None else float(poll)
        if poll_s <= 0:
            raise ValueError("poll cycle must be > 0")
        now = time.time()
        with self.lock:
            self.clients[name] = {"name": name, "poll": poll_s, "tuned_at": now, "last_poll": 0.0}
            self.lanes.setdefault(name, [])
            self._persist()
            return {"ok": True, "mailbox": self.mailbox_id, "name": name, "poll": poll_s}

    @staticmethod
    def client_names(self) -> list[str]:
        with self.lock:
            return list(self.clients)

    @staticmethod
    def enqueue(self, dest: str, msg: dict) -> None:
        item = {"enqueued_at": time.time(), "msg": msg}
        with self.lock:
            if dest not in self.lanes:
                self.lanes[dest] = []
            self.lanes[dest].append(item)
            self._persist()

    @staticmethod
    def enqueue_all(self, msg: dict) -> list[str]:
        with self.lock:
            names = list(self.clients)
            now = time.time()
            for name in names:
                self.lanes.setdefault(name, []).append({"enqueued_at": now, "msg": msg})
            self._persist()
            return names

    @staticmethod
    def fetch(self, name: str) -> list[dict]:
        now = time.time()
        with self.lock:
            dropped = self.expire_locked(now)
            items = list(self.lanes.get(name, []))
            self.lanes[name] = []
            if name in self.clients:
                self.clients[name]["last_poll"] = now
            self._persist()
        for dest, msg in dropped:
            text = msg.get("text", "")
            seq = msg.get("seq", "?")
            print(
                f"[{self.server_name} EXPIRE] dest={dest} seq={seq} text={text!r}",
                flush=True,
            )
        return [item["msg"] for item in items]

    @staticmethod
    def sweep(self) -> None:
        now = time.time()
        with self.lock:
            dropped = self.expire_locked(now)
            if dropped:
                self._persist()
        for dest, msg in dropped:
            text = msg.get("text", "")
            seq = msg.get("seq", "?")
            print(
                f"[{self.server_name} EXPIRE] dest={dest} seq={seq} text={text!r}",
                flush=True,
            )


# === Tier 2 (imports) ===

# === TcpSlot (class) ===
class TcpSlot_internal:
    def __init__(self, name: str, addr: tuple[str, int]):
        self.name = name
        self.host, self.port = addr
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

    # -- bind-or-connect on the shared address -------------------------------

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

    def _start_recv(self) -> None:
        self.alive.set()
        self.recv_thread = threading.Thread(target=self._recv_loop, name=f"{self.name}-recv", daemon=True)
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

        # Application-level reply, same shape as the HTTP slot's POST response.
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

    def addr_s(self) -> str:
        return f"tcp://{self.host}:{self.port}"

    def next_seq(self) -> int:
        with self.seq_lock:
            self.seq += 1
            return self.seq

    def attach(self, wait: float) -> None:
        """First binder becomes listener; the other dials the same host:port."""
        deadline = time.time() + wait
        last_err = None
        while time.time() < deadline:
            try:
                self.listener = self._bind_listen()
                self.role = "listen"
                print(f"[{self.name} LISTEN] {self.addr_s()}  (waiting for peer)", flush=True)
                while time.time() < deadline:
                    try:
                        conn, peer = self.listener.accept()
                        self.conn = conn
                        print(f"[{self.name} ACCEPT] peer={peer[0]}:{peer[1]}", flush=True)
                        self._start_recv()
                        return
                    except socket.timeout:
                        continue
                raise TimeoutError(f"{self.name} bound {self.addr_s()} but nobody connected")
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
                    print(f"[{self.name} CONNECT] {self.addr_s()}", flush=True)
                    self._start_recv()
                    return
                except OSError as e2:
                    last_err = e2
                    time.sleep(0.15)
        raise TimeoutError(f"{self.name} never attached to {self.addr_s()}: {last_err}")

    def request_response(self, payload: dict, timeout: float = 5.0) -> dict:
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

    def send_text(self, text: str) -> dict:
        payload = {
            "from": self.name,
            "seq": self.next_seq(),
            "kind": "chat",
            "text": text,
            "ts": time.time(),
        }
        print(f"[{self.name} SEND] seq={payload['seq']} text={text!r}", flush=True)
        reply = self.request_response(payload)
        print(f"[{self.name} REPLY] {reply}", flush=True)
        return reply


_TcpSlot_internal = TcpSlot_internal()

class TcpSlot:

    @staticmethod
    def wait_for_peer(self, timeout: float = 20.0) -> None:
        # _TcpSlot_internal.attach() already blocks until the duplex socket exists
        if self.conn is None:
            self.attach(timeout)
        print(f"[{self.name} PEER UP] role={self.role} addr={self.addr_s()}", flush=True)

    @staticmethod
    def burst(self) -> None:
        pass

    @staticmethod
    def close(self) -> None:
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

    @staticmethod
    def addr_s(self) -> str:
        return f"tcp://{self.host}:{self.port}"

    @staticmethod
    def next_seq(self) -> int:
        with self.seq_lock:
            self.seq += 1
            return self.seq

    @staticmethod
    def attach(self, wait: float) -> None:
        """First binder becomes listener; the other dials the same host:port."""
        deadline = time.time() + wait
        last_err = None
        while time.time() < deadline:
            try:
                self.listener = self._bind_listen()
                self.role = "listen"
                print(f"[{self.name} LISTEN] {self.addr_s()}  (waiting for peer)", flush=True)
                while time.time() < deadline:
                    try:
                        conn, peer = self.listener.accept()
                        self.conn = conn
                        print(f"[{self.name} ACCEPT] peer={peer[0]}:{peer[1]}", flush=True)
                        self._start_recv()
                        return
                    except socket.timeout:
                        continue
                raise TimeoutError(f"{self.name} bound {self.addr_s()} but nobody connected")
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
                    print(f"[{self.name} CONNECT] {self.addr_s()}", flush=True)
                    self._start_recv()
                    return
                except OSError as e2:
                    last_err = e2
                    time.sleep(0.15)
        raise TimeoutError(f"{self.name} never attached to {self.addr_s()}: {last_err}")

    @staticmethod
    def request_response(self, payload: dict, timeout: float = 5.0) -> dict:
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

    @staticmethod
    def send_text(self, text: str) -> dict:
        payload = {
            "from": self.name,
            "seq": self.next_seq(),
            "kind": "chat",
            "text": text,
            "ts": time.time(),
        }
        print(f"[{self.name} SEND] seq={payload['seq']} text={text!r}", flush=True)
        reply = self.request_response(payload)
        print(f"[{self.name} REPLY] {reply}", flush=True)
        return reply


# === UnixSlot (class) ===
class UnixSlot_internal:
    @staticmethod
    def _is_sock_file(self, path: str) -> bool:
        try:
            return stat.S_ISSOCK(os.stat(path).st_mode)
        except FileNotFoundError:
            return False
        except OSError:
            return False

    @staticmethod
    def _unlink_if_stale(self, path: str) -> bool:
        """Remove a leftover socket file that nothing is accepting on."""
        if not UnixSlot._is_sock_file(path):
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

    def __init__(self, name: str, path: str):
        self.name = name
        self.path = path
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

    def _start_recv(self) -> None:
        self.alive.set()
        self.recv_thread = threading.Thread(target=self._recv_loop, name=f"{self.name}-recv", daemon=True)
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

    def addr_s(self) -> str:
        return f"unix://{self.path}"

    def next_seq(self) -> int:
        with self.seq_lock:
            self.seq += 1
            return self.seq

    def attach(self, wait: float) -> None:
        """First binder becomes listener; the other dials the same path."""
        deadline = time.time() + wait
        last_err = None
        parent = os.path.dirname(self.path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        while time.time() < deadline:
            try:
                self.listener = self._bind_listen()
                self.role = "listen"
                print(f"[{self.name} LISTEN] {self.addr_s()}  (waiting for peer)", flush=True)
                while time.time() < deadline:
                    try:
                        conn, _peer = self.listener.accept()
                        self.conn = conn
                        print(f"[{self.name} ACCEPT] path={self.path}", flush=True)
                        self._start_recv()
                        return
                    except socket.timeout:
                        continue
                raise TimeoutError(f"{self.name} bound {self.addr_s()} but nobody connected")
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
                    print(f"[{self.name} CONNECT] {self.addr_s()}", flush=True)
                    self._start_recv()
                    return
                except ConnectionRefusedError as e2:
                    last_err = e2
                    if UnixSlot._unlink_if_stale(self.path):
                        print(f"[{self.name} STALE] removed leftover {self.path}", flush=True)
                    time.sleep(0.15)
                except OSError as e2:
                    last_err = e2
                    time.sleep(0.15)
        raise TimeoutError(f"{self.name} never attached to {self.addr_s()}: {last_err}")

    def request_response(self, payload: dict, timeout: float = 5.0) -> dict:
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

    def send_text(self, text: str) -> dict:
        payload = {
            "from": self.name,
            "seq": self.next_seq(),
            "kind": "chat",
            "text": text,
            "ts": time.time(),
        }
        print(f"[{self.name} SEND] seq={payload['seq']} text={text!r}", flush=True)
        reply = self.request_response(payload)
        print(f"[{self.name} REPLY] {reply}", flush=True)
        return reply


_UnixSlot_internal = UnixSlot_internal()

class UnixSlot:

    @staticmethod
    def wait_for_peer(self, timeout: float = 20.0) -> None:
        if self.conn is None:
            self.attach(timeout)
        print(f"[{self.name} PEER UP] role={self.role} addr={self.addr_s()}", flush=True)

    @staticmethod
    def burst(self) -> None:
        pass

    @staticmethod
    def close(self) -> None:
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

    @staticmethod
    def addr_s(self) -> str:
        return f"unix://{self.path}"

    @staticmethod
    def next_seq(self) -> int:
        with self.seq_lock:
            self.seq += 1
            return self.seq

    @staticmethod
    def attach(self, wait: float) -> None:
        """First binder becomes listener; the other dials the same path."""
        deadline = time.time() + wait
        last_err = None
        parent = os.path.dirname(self.path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        while time.time() < deadline:
            try:
                self.listener = self._bind_listen()
                self.role = "listen"
                print(f"[{self.name} LISTEN] {self.addr_s()}  (waiting for peer)", flush=True)
                while time.time() < deadline:
                    try:
                        conn, _peer = self.listener.accept()
                        self.conn = conn
                        print(f"[{self.name} ACCEPT] path={self.path}", flush=True)
                        self._start_recv()
                        return
                    except socket.timeout:
                        continue
                raise TimeoutError(f"{self.name} bound {self.addr_s()} but nobody connected")
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
                    print(f"[{self.name} CONNECT] {self.addr_s()}", flush=True)
                    self._start_recv()
                    return
                except ConnectionRefusedError as e2:
                    last_err = e2
                    if UnixSlot._unlink_if_stale(self.path):
                        print(f"[{self.name} STALE] removed leftover {self.path}", flush=True)
                    time.sleep(0.15)
                except OSError as e2:
                    last_err = e2
                    time.sleep(0.15)
        raise TimeoutError(f"{self.name} never attached to {self.addr_s()}: {last_err}")

    @staticmethod
    def request_response(self, payload: dict, timeout: float = 5.0) -> dict:
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

    @staticmethod
    def send_text(self, text: str) -> dict:
        payload = {
            "from": self.name,
            "seq": self.next_seq(),
            "kind": "chat",
            "text": text,
            "ts": time.time(),
        }
        print(f"[{self.name} SEND] seq={payload['seq']} text={text!r}", flush=True)
        reply = self.request_response(payload)
        print(f"[{self.name} REPLY] {reply}", flush=True)
        return reply


# === WsSlot (class) ===
class WsSlot_internal:
    def __init__(self, name: str, addr: tuple[str, int]):
        self.name = name
        self.host, self.port = addr
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

    def _server_handler(self, websocket):
        self.ws = websocket
        self.role = self.role or "listen"
        self.alive.set()
        self.attached.set()
        print(f"[{self.name} ACCEPT] {self.addr_s()}", flush=True)
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

    def addr_s(self) -> str:
        return f"ws://{self.host}:{self.port}"

    def next_seq(self) -> int:
        with self.seq_lock:
            self.seq += 1
            return self.seq

    def attach(self, wait: float) -> None:
        deadline = time.time() + wait
        last_err = None
        while time.time() < deadline:
            try:
                self.server = serve(self._server_handler, self.host, self.port)
                self.role = "listen"
                self.server_thread = threading.Thread(
                    target=self.server.serve_forever,
                    name=f"{self.name}-wsserve",
                    daemon=True,
                )
                self.server_thread.start()
                print(f"[{self.name} LISTEN] {self.addr_s()}  (waiting for peer)", flush=True)
                if not self.attached.wait(timeout=max(0.05, deadline - time.time())):
                    raise TimeoutError(f"{self.name} bound {self.addr_s()} but nobody connected")
                return
            except OSError as e:
                last_err = e
                self._stop_server()
                try:
                    self.ws = connect(self.addr_s(), open_timeout=0.4)
                    self.role = "connect"
                    self.alive.set()
                    self.attached.set()
                    self.recv_thread = threading.Thread(
                        target=self._recv_loop,
                        name=f"{self.name}-wsrecv",
                        daemon=True,
                    )
                    self.recv_thread.start()
                    print(f"[{self.name} CONNECT] {self.addr_s()}", flush=True)
                    return
                except Exception as e2:
                    last_err = e2
                    time.sleep(0.15)
        raise TimeoutError(f"{self.name} never attached to {self.addr_s()}: {last_err}")

    def request_response(self, payload: dict, timeout: float = 5.0) -> dict:
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

    def send_text(self, text: str) -> dict:
        payload = {
            "from": self.name,
            "seq": self.next_seq(),
            "kind": "chat",
            "text": text,
            "ts": time.time(),
        }
        print(f"[{self.name} SEND] seq={payload['seq']} text={text!r}", flush=True)
        reply = self.request_response(payload)
        print(f"[{self.name} REPLY] {reply}", flush=True)
        return reply


_WsSlot_internal = WsSlot_internal()

class WsSlot:

    @staticmethod
    def wait_for_peer(self, timeout: float = 20.0) -> None:
        if not self.attached.is_set():
            self.attach(timeout)
        print(f"[{self.name} PEER UP] role={self.role} addr={self.addr_s()}", flush=True)

    @staticmethod
    def burst(self) -> None:
        pass

    @staticmethod
    def close(self) -> None:
        self.alive.clear()
        if self.ws is not None:
            try:
                self.ws.close()
            except Exception:
                pass
            self.ws = None
        self._stop_server()

    @staticmethod
    def addr_s(self) -> str:
        return f"ws://{self.host}:{self.port}"

    @staticmethod
    def next_seq(self) -> int:
        with self.seq_lock:
            self.seq += 1
            return self.seq

    @staticmethod
    def attach(self, wait: float) -> None:
        deadline = time.time() + wait
        last_err = None
        while time.time() < deadline:
            try:
                self.server = serve(self._server_handler, self.host, self.port)
                self.role = "listen"
                self.server_thread = threading.Thread(
                    target=self.server.serve_forever,
                    name=f"{self.name}-wsserve",
                    daemon=True,
                )
                self.server_thread.start()
                print(f"[{self.name} LISTEN] {self.addr_s()}  (waiting for peer)", flush=True)
                if not self.attached.wait(timeout=max(0.05, deadline - time.time())):
                    raise TimeoutError(f"{self.name} bound {self.addr_s()} but nobody connected")
                return
            except OSError as e:
                last_err = e
                self._stop_server()
                try:
                    self.ws = connect(self.addr_s(), open_timeout=0.4)
                    self.role = "connect"
                    self.alive.set()
                    self.attached.set()
                    self.recv_thread = threading.Thread(
                        target=self._recv_loop,
                        name=f"{self.name}-wsrecv",
                        daemon=True,
                    )
                    self.recv_thread.start()
                    print(f"[{self.name} CONNECT] {self.addr_s()}", flush=True)
                    return
                except Exception as e2:
                    last_err = e2
                    time.sleep(0.15)
        raise TimeoutError(f"{self.name} never attached to {self.addr_s()}: {last_err}")

    @staticmethod
    def request_response(self, payload: dict, timeout: float = 5.0) -> dict:
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

    @staticmethod
    def send_text(self, text: str) -> dict:
        payload = {
            "from": self.name,
            "seq": self.next_seq(),
            "kind": "chat",
            "text": text,
            "ts": time.time(),
        }
        print(f"[{self.name} SEND] seq={payload['seq']} text={text!r}", flush=True)
        reply = self.request_response(payload)
        print(f"[{self.name} REPLY] {reply}", flush=True)
        return reply


# === ShmSlot (class) ===
class ShmSlot_internal:
    def __init__(self, name: str, mine: str, peer: str):
        self.name = name
        self.mine = mine
        self.peer = peer
        self.bin_path, self.lock_path = Transponder_Locators.shm_bin_paths(mine, peer)
        self.seq = 0
        self.seq_lock = threading.Lock()
        self.inbox = []
        self.inbox_lock = threading.Lock()
        self.replies = {}
        self.reply_events = {}
        self.alive = threading.Event()
        self.peer_up = threading.Event()
        self.watch = None
        self.watch_thread = None
        self.on_payload = None

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

    def _watch_loop(self) -> None:
        while self.alive.is_set():
            try:
                hit = self.watch.wait(timeout=0.5)
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

    def addr_s(self) -> str:
        return f"shm://{os.path.basename(self.bin_path)}"

    def next_seq(self) -> int:
        with self.seq_lock:
            self.seq += 1
            return self.seq

    def ensure_bin(self) -> None:
        def mark(obj):
            obj["present"][self.mine] = {"name": self.name, "ts": time.time()}
            return obj["present"]

        present = self._mutate(mark)
        print(f"[{self.name} BIN] {self.bin_path} present={list(present)}", flush=True)
        if self.peer in present:
            self.peer_up.set()

    def attach(self, wait: float) -> None:
        self.ensure_bin()
        self.watch = DirWatch(Transponder_Locators.BIN_DIR, os.path.basename(self.bin_path))
        self.alive.set()
        self.watch_thread = threading.Thread(
            target=self._watch_loop, name=f"{self.name}-inotify", daemon=True
        )
        self.watch_thread.start()
        print(f"[{self.name} LISTEN] token={self.mine} peer={self.peer}", flush=True)

        deadline = time.time() + wait
        while time.time() < deadline and not self.peer_up.is_set():
            self._drain()
            if self.peer_up.is_set():
                break
            remaining = max(0.05, deadline - time.time())
            self.watch.wait(timeout=min(0.5, remaining))
        if not self.peer_up.is_set():
            raise TimeoutError(f"{self.name} never saw peer token {self.peer} in {self.bin_path}")

    def request_response(self, payload: dict, timeout: float = 5.0) -> dict:
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

    def send_text(self, text: str) -> dict:
        payload = {
            "from": self.name,
            "from_token": self.mine,
            "seq": self.next_seq(),
            "kind": "chat",
            "text": text,
            "ts": time.time(),
        }
        print(f"[{self.name} SEND] seq={payload['seq']} text={text!r}", flush=True)
        reply = self.request_response(payload)
        print(f"[{self.name} REPLY] {reply}", flush=True)
        return reply


_ShmSlot_internal = ShmSlot_internal()

class ShmSlot:

    @staticmethod
    def wait_for_peer(self, timeout: float = 20.0) -> None:
        if not self.peer_up.is_set():
            self.attach(timeout)
        print(f"[{self.name} PEER UP] addr={self.addr_s()}", flush=True)

    @staticmethod
    def burst(self) -> None:
        pass

    @staticmethod
    def close(self) -> None:
        self.alive.clear()
        if self.watch is not None:
            self.watch.close()
            self.watch = None

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

    @staticmethod
    def addr_s(self) -> str:
        return f"shm://{os.path.basename(self.bin_path)}"

    @staticmethod
    def next_seq(self) -> int:
        with self.seq_lock:
            self.seq += 1
            return self.seq

    @staticmethod
    def ensure_bin(self) -> None:
        def mark(obj):
            obj["present"][self.mine] = {"name": self.name, "ts": time.time()}
            return obj["present"]

        present = self._mutate(mark)
        print(f"[{self.name} BIN] {self.bin_path} present={list(present)}", flush=True)
        if self.peer in present:
            self.peer_up.set()

    @staticmethod
    def attach(self, wait: float) -> None:
        self.ensure_bin()
        self.watch = DirWatch(Transponder_Locators.BIN_DIR, os.path.basename(self.bin_path))
        self.alive.set()
        self.watch_thread = threading.Thread(
            target=self._watch_loop, name=f"{self.name}-inotify", daemon=True
        )
        self.watch_thread.start()
        print(f"[{self.name} LISTEN] token={self.mine} peer={self.peer}", flush=True)

        deadline = time.time() + wait
        while time.time() < deadline and not self.peer_up.is_set():
            self._drain()
            if self.peer_up.is_set():
                break
            remaining = max(0.05, deadline - time.time())
            self.watch.wait(timeout=min(0.5, remaining))
        if not self.peer_up.is_set():
            raise TimeoutError(f"{self.name} never saw peer token {self.peer} in {self.bin_path}")

    @staticmethod
    def request_response(self, payload: dict, timeout: float = 5.0) -> dict:
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

    @staticmethod
    def send_text(self, text: str) -> dict:
        payload = {
            "from": self.name,
            "from_token": self.mine,
            "seq": self.next_seq(),
            "kind": "chat",
            "text": text,
            "ts": time.time(),
        }
        print(f"[{self.name} SEND] seq={payload['seq']} text={text!r}", flush=True)
        reply = self.request_response(payload)
        print(f"[{self.name} REPLY] {reply}", flush=True)
        return reply


# === HttpSlot (class) ===
class HttpSlot_internal:
    def __init__(self, name: str, listen: tuple[str, int], peer: tuple[str, int]):
        self.name = name
        self.listen_host, self.listen_port = listen
        self.peer_host, self.peer_port = peer
        self.seq = 0
        self.seq_lock = threading.Lock()
        self.httpd = None
        self.server_thread = None
        self.inbox = []
        self.inbox_lock = threading.Lock()

    # -- server (positive) ---------------------------------------------------

    def _handler_class(self):
        slot = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):
                return

            def _write(self, code: int, payload: dict):
                body = Transponder_Codec.encode_bytes(payload)
                self.send_response(code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                if self.path.startswith("/health"):
                    self._write(200, {
                        "ok": True,
                        "name": slot.name,
                        "listen": slot.listen_url(),
                        "peer": slot.peer_url(""),
                    })
                    return
                self._write(404, {"ok": False, "error": "not found"})

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(n) if n else b""
                try:
                    incoming = Transponder_Codec.decode_msg(raw)
                except Exception as e:
                    self._write(400, {"ok": False, "error": type(e).__name__, "message": str(e)})
                    return

                with slot.inbox_lock:
                    slot.inbox.append(incoming)

                origin = incoming.get("from", "?")
                text = incoming.get("text", "")
                seq = incoming.get("seq", "?")
                print(
                    f"[{slot.name} RECV] from={origin} seq={seq} text={text!r}",
                    flush=True,
                )

                self._write(200, {
                    "ok": True,
                    "heard_by": slot.name,
                    "from": origin,
                    "seq": seq,
                    "text": text,
                })

        return Handler

    def next_seq(self) -> int:
        with self.seq_lock:
            self.seq += 1
            return self.seq

    def peer_url(self, path: str = "/msg") -> str:
        return f"http://{self.peer_host}:{self.peer_port}{path}"

    def listen_url(self) -> str:
        return f"http://{self.listen_host}:{self.listen_port}"

    def serve(self):
        Handler = self._handler_class()
        self.httpd = ThreadingHTTPServer((self.listen_host, self.listen_port), Handler)
        self.httpd.daemon_threads = True
        print(
            f"[{self.name} LISTEN] {self.listen_url()}  -> peer {self.peer_host}:{self.peer_port}",
            flush=True,
        )
        self.httpd.serve_forever()

    # -- client (negative) ---------------------------------------------------

    def request_response(self, payload: dict, timeout: float = 5.0) -> dict:
        body = Transponder_Codec.encode_bytes(payload)
        req = urllib.request.Request(
            self.peer_url("/msg"),
            data=body,
            method="POST",
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
        return Transponder_Codec.decode_msg(raw)

    def send_text(self, text: str) -> dict:
        payload = {
            "from": self.name,
            "seq": self.next_seq(),
            "kind": "chat",
            "text": text,
            "ts": time.time(),
        }
        print(f"[{self.name} SEND] seq={payload['seq']} text={text!r}", flush=True)
        reply = self.request_response(payload)
        print(f"[{self.name} REPLY] {reply}", flush=True)
        return reply


_HttpSlot_internal = HttpSlot_internal()

class HttpSlot:

    @staticmethod
    def start_server_thread(self):
        self.server_thread = threading.Thread(target=self.serve, name=f"{self.name}-http", daemon=True)
        self.server_thread.start()

    @staticmethod
    def close(self):
        if self.httpd is not None:
            self.httpd.shutdown()
            self.httpd.server_close()

    @staticmethod
    def wait_for_peer(self, timeout: float = 20.0) -> None:
        deadline = time.time() + timeout
        url = self.peer_url("/health")
        last_err = None
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(url, timeout=1.0) as resp:
                    info = Transponder_Codec.decode_msg(resp.read())
                print(f"[{self.name} PEER UP] {info}", flush=True)
                return
            except Exception as e:
                last_err = e
                time.sleep(0.2)
        raise TimeoutError(f"{self.name} never saw peer at {url}: {last_err}")

    @staticmethod
    def burst(self) -> None:
        pass

    @staticmethod
    def next_seq(self) -> int:
        with self.seq_lock:
            self.seq += 1
            return self.seq

    @staticmethod
    def peer_url(self, path: str = "/msg") -> str:
        return f"http://{self.peer_host}:{self.peer_port}{path}"

    @staticmethod
    def listen_url(self) -> str:
        return f"http://{self.listen_host}:{self.listen_port}"

    @staticmethod
    def serve(self):
        Handler = self._handler_class()
        self.httpd = ThreadingHTTPServer((self.listen_host, self.listen_port), Handler)
        self.httpd.daemon_threads = True
        print(
            f"[{self.name} LISTEN] {self.listen_url()}  -> peer {self.peer_host}:{self.peer_port}",
            flush=True,
        )
        self.httpd.serve_forever()

    # -- client (negative) ---------------------------------------------------

    @staticmethod
    def request_response(self, payload: dict, timeout: float = 5.0) -> dict:
        body = Transponder_Codec.encode_bytes(payload)
        req = urllib.request.Request(
            self.peer_url("/msg"),
            data=body,
            method="POST",
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
        return Transponder_Codec.decode_msg(raw)

    @staticmethod
    def send_text(self, text: str) -> dict:
        payload = {
            "from": self.name,
            "seq": self.next_seq(),
            "kind": "chat",
            "text": text,
            "ts": time.time(),
        }
        print(f"[{self.name} SEND] seq={payload['seq']} text={text!r}", flush=True)
        reply = self.request_response(payload)
        print(f"[{self.name} REPLY] {reply}", flush=True)
        return reply


# === MailboxServer (class) ===
class MailboxServer_internal:
    def __init__(self, name: str, listen: tuple[str, int], poll: float):
        self.name = name
        self.listen = listen
        self.poll = poll
        self.box = Mailbox(name, poll)
        self.seq = 0
        self.seq_lock = threading.Lock()
        self.httpd = None
        self.server_thread = None
        self.sweep_stop = threading.Event()
        self.client_present = threading.Event()

    def _handler_class(self):
        slot = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):
                return

            def _write(self, code: int, payload: dict):
                body = Transponder_Codec.encode_bytes(payload)
                self.send_response(code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _read_json(self) -> dict:
                n = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(n) if n else b""
                return Transponder_Codec.decode_msg(raw)

            def do_GET(self):
                parsed = urllib.parse.urlparse(self.path)
                path = parsed.path
                qs = urllib.parse.parse_qs(parsed.query)

                if path == "/health":
                    self._write(200, {
                        "ok": True,
                        "name": slot.name,
                        "mailbox": slot.box.mailbox_id,
                        "listen": slot.listen_url(),
                        "poll_default": slot.poll,
                        "clients": slot.box.client_names(),
                    })
                    return

                if path == "/poll":
                    names = qs.get("name") or qs.get("from")
                    if not names:
                        self._write(400, {"ok": False, "error": "missing name"})
                        return
                    name = names[0]
                    messages = slot.box.fetch(name)
                    for incoming in messages:
                        origin = incoming.get("from", "?")
                        text = incoming.get("text", "")
                        seq = incoming.get("seq", "?")
                        kind = incoming.get("kind", "chat")
                        tag = "REPLY" if kind == "reply" else "GIVE"
                        print(
                            f"[{slot.name} {tag}] dest={name} from={origin} seq={seq} text={text!r}",
                            flush=True,
                        )
                    self._write(200, {
                        "ok": True,
                        "mailbox": slot.box.mailbox_id,
                        "name": name,
                        "messages": messages,
                    })
                    return

                self._write(404, {"ok": False, "error": "not found"})

            def do_POST(self):
                parsed = urllib.parse.urlparse(self.path)
                path = parsed.path
                try:
                    incoming = self._read_json()
                except Exception as e:
                    self._write(400, {"ok": False, "error": type(e).__name__, "message": str(e)})
                    return

                if path == "/tune":
                    name = incoming.get("from") or incoming.get("name")
                    if not name:
                        self._write(400, {"ok": False, "error": "missing name"})
                        return
                    poll = incoming.get("poll")
                    try:
                        info = slot.box.tune(str(name), None if poll is None else float(poll))
                    except Exception as e:
                        self._write(400, {"ok": False, "error": type(e).__name__, "message": str(e)})
                        return
                    print(
                        f"[{slot.name} JOIN] client={name} poll={info['poll']} mailbox={slot.box.mailbox_id}",
                        flush=True,
                    )
                    slot.client_present.set()
                    self._write(200, info)
                    return

                if path == "/send":
                    origin = incoming.get("from", "?")
                    text = incoming.get("text", "")
                    seq = incoming.get("seq", "?")
                    print(
                        f"[{slot.name} RECV] from={origin} seq={seq} text={text!r}",
                        flush=True,
                    )
                    if incoming.get("kind", "chat") == "chat" and origin and origin != slot.name:
                        reply = {
                            "from": slot.name,
                            "seq": incoming.get("seq"),
                            "kind": "reply",
                            "heard_by": slot.name,
                            "text": text,
                            "ts": time.time(),
                        }
                        slot.box.enqueue(str(origin), reply)
                    self._write(200, {
                        "ok": True,
                        "heard_by": slot.name,
                        "mailbox": slot.box.mailbox_id,
                        "from": origin,
                        "seq": seq,
                        "text": text,
                    })
                    return

                self._write(404, {"ok": False, "error": "not found"})

        return Handler

    def _sweep_loop(self):
        while not self.sweep_stop.wait(0.25):
            self.box.sweep()

    def next_seq(self) -> int:
        with self.seq_lock:
            self.seq += 1
            return self.seq

    def listen_url(self) -> str:
        return f"http://{Transponder_Locators.fmt_addr(self.listen)}"

    def serve(self):
        Handler = self._handler_class()
        self.httpd = ThreadingHTTPServer(self.listen, Handler)
        self.httpd.daemon_threads = True
        print(
            f"[{self.name} LISTEN] {self.listen_url()} mailbox={self.box.mailbox_id} bin={self.box.bin_path}",
            flush=True,
        )
        self.httpd.serve_forever()


_MailboxServer_internal = MailboxServer_internal()

class MailboxServer:

    @staticmethod
    def start(self):
        self.server_thread = threading.Thread(target=self.serve, name=f"{self.name}-http", daemon=True)
        self.server_thread.start()
        threading.Thread(target=self._sweep_loop, name=f"{self.name}-ttl", daemon=True).start()

    @staticmethod
    def wait_for_client(self, timeout: float) -> None:
        print(f"[{self.name} WAIT] for a tuner-style client to POST /tune", flush=True)
        if not self.client_present.wait(timeout=timeout):
            raise TimeoutError(f"{self.name} never saw a client join")
        print(f"[{self.name} PEER UP] clients={self.box.client_names()}", flush=True)

    @staticmethod
    def send_text(self, text: str) -> None:
        payload = {
            "from": self.name,
            "seq": self.next_seq(),
            "kind": "chat",
            "text": text,
            "ts": time.time(),
            "mailbox": self.box.mailbox_id,
        }
        dests = self.box.enqueue_all(payload)
        print(
            f"[{self.name} SEND] seq={payload['seq']} dests={dests} text={text!r}",
            flush=True,
        )

    @staticmethod
    def close(self):
        self.sweep_stop.set()
        if self.httpd is not None:
            self.httpd.shutdown()
            self.httpd.server_close()
        self.box.unlink()

    @staticmethod
    def next_seq(self) -> int:
        with self.seq_lock:
            self.seq += 1
            return self.seq

    @staticmethod
    def listen_url(self) -> str:
        return f"http://{Transponder_Locators.fmt_addr(self.listen)}"

    @staticmethod
    def serve(self):
        Handler = self._handler_class()
        self.httpd = ThreadingHTTPServer(self.listen, Handler)
        self.httpd.daemon_threads = True
        print(
            f"[{self.name} LISTEN] {self.listen_url()} mailbox={self.box.mailbox_id} bin={self.box.bin_path}",
            flush=True,
        )
        self.httpd.serve_forever()


# === MailboxClient (class) ===
class MailboxClient_internal:
    def __init__(self, name: str, peer: tuple[str, int], poll: float):
        self.name = name
        self.peer = peer
        self.poll = poll
        self.seq = 0
        self.seq_lock = threading.Lock()
        self.mailbox_id = None
        self.stop = threading.Event()

    def _request(self, method: str, path: str, payload: dict | None = None, timeout: float = 5.0) -> dict:
        data = None if payload is None else Transponder_Codec.encode_bytes(payload)
        headers = {}
        if data is not None:
            headers["Content-Type"] = "application/json; charset=utf-8"
        req = urllib.request.Request(self.peer_url(path), data=data, method=method, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return Transponder_Codec.decode_msg(resp.read())

    def next_seq(self) -> int:
        with self.seq_lock:
            self.seq += 1
            return self.seq

    def peer_url(self, path: str) -> str:
        return f"http://{Transponder_Locators.fmt_addr(self.peer)}{path}"

    def poll_once(self) -> list[dict]:
        path = "/poll?" + urllib.parse.urlencode({"name": self.name})
        info = self._request("GET", path, timeout=max(2.0, self.poll + 1.0))
        messages = info.get("messages") or []
        for incoming in messages:
            origin = incoming.get("from", "?")
            text = incoming.get("text", "")
            seq = incoming.get("seq", "?")
            kind = incoming.get("kind", "chat")
            tag = "REPLY" if kind == "reply" else "RECV"
            print(
                f"[{self.name} {tag}] from={origin} seq={seq} text={text!r}",
                flush=True,
            )
        return messages


_MailboxClient_internal = MailboxClient_internal()

class MailboxClient:

    @staticmethod
    def wait_for_server(self, timeout: float) -> dict:
        deadline = time.time() + timeout
        last_err = None
        url = self.peer_url("/health")
        while time.time() < deadline:
            try:
                info = self._request("GET", "/health", timeout=1.0)
                self.mailbox_id = info.get("mailbox")
                print(f"[{self.name} PEER UP] {info}", flush=True)
                return info
            except Exception as e:
                last_err = e
                time.sleep(0.2)
        raise TimeoutError(f"{self.name} never saw mailbox at {url}: {last_err}")

    @staticmethod
    def tune(self) -> dict:
        info = self._request("POST", "/tune", {"from": self.name, "kind": "tune", "poll": self.poll, "ts": time.time()})
        self.mailbox_id = info.get("mailbox", self.mailbox_id)
        print(f"[{self.name} TUNE] {info}", flush=True)
        return info

    @staticmethod
    def send_text(self, text: str) -> dict:
        payload = {
            "from": self.name,
            "seq": self.next_seq(),
            "kind": "chat",
            "text": text,
            "ts": time.time(),
        }
        print(f"[{self.name} SEND] seq={payload['seq']} text={text!r}", flush=True)
        reply = self._request("POST", "/send", payload)
        print(f"[{self.name} ACCEPTED] {reply}", flush=True)
        return reply

    @staticmethod
    def poll_loop(self) -> None:
        while not self.stop.wait(self.poll):
            try:
                self.poll_once()
            except Exception as e:
                if self.stop.is_set():
                    return
                print(f"[{self.name} POLL FAIL] {type(e).__name__}: {e}", flush=True)

    @staticmethod
    def close(self):
        self.stop.set()

    @staticmethod
    def next_seq(self) -> int:
        with self.seq_lock:
            self.seq += 1
            return self.seq

    @staticmethod
    def peer_url(self, path: str) -> str:
        return f"http://{Transponder_Locators.fmt_addr(self.peer)}{path}"

    @staticmethod
    def poll_once(self) -> list[dict]:
        path = "/poll?" + urllib.parse.urlencode({"name": self.name})
        info = self._request("GET", path, timeout=max(2.0, self.poll + 1.0))
        messages = info.get("messages") or []
        for incoming in messages:
            origin = incoming.get("from", "?")
            text = incoming.get("text", "")
            seq = incoming.get("seq", "?")
            kind = incoming.get("kind", "chat")
            tag = "REPLY" if kind == "reply" else "RECV"
            print(
                f"[{self.name} {tag}] from={origin} seq={seq} text={text!r}",
                flush=True,
            )
        return messages


# === Station (class) ===
class Station_internal:
    def __init__(self, name: str, listen: tuple[str, int], interval: float, repeat: int):
        self.name = name
        self.listen = listen
        self.interval = max(0.05, interval)
        self.repeat = max(1, repeat)
        self.sock = None
        self.seq = 0
        self.seq_lock = threading.Lock()
        self.registry = {}
        self.reg_lock = threading.Lock()
        self.alive = threading.Event()
        self.join_thread = None

    def _join_loop(self) -> None:
        while self.alive.is_set():
            try:
                raw, src = self.sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                msg = Transponder_Codec.decode_msg(raw)
            except Exception as e:
                print(f"[{self.name} BAD JSON] from={src} {e}", flush=True)
                continue
            if msg.get("kind") != "tune":
                print(f"[{self.name} IGNORE] kind={msg.get('kind')!r} from={src}", flush=True)
                continue
            recv_s = msg.get("recv") or Transponder_Locators.fmt_addr(src)
            try:
                dest = Transponder_Locators.parse_hostport(str(recv_s))
            except ValueError:
                dest = (src[0], src[1])
            entry = {"name": msg.get("name") or "?", "recv": dest, "ts": time.time()}
            with self.reg_lock:
                self.registry[dest] = entry
            print(f"[{self.name} JOIN] {entry['name']} → {Transponder_Locators.fmt_addr(dest)}  n={len(self.registry)}", flush=True)

    def _destinations(self) -> list[tuple[tuple[str, int], str]]:
        with self.reg_lock:
            return [(dest, rec["name"]) for dest, rec in self.registry.items()]

    def addr_s(self) -> str:
        return f"udp://{Transponder_Locators.fmt_addr(self.listen)}"

    def start(self) -> None:
        self.sock = UdpMail.bind_udp(self.listen)
        self.alive.set()
        self.join_thread = threading.Thread(target=self._join_loop, name=f"{self.name}-join", daemon=True)
        self.join_thread.start()
        print(f"[{self.name} STATION] join-mailbox {self.addr_s()}", flush=True)

    def next_seq(self) -> int:
        with self.seq_lock:
            self.seq += 1
            return self.seq

    def emit(self) -> None:
        seq = self.next_seq()
        payload = {
            "from": self.name,
            "kind": "pulse",
            "seq": seq,
            "text": f"pulse {seq}",
            "ts": time.time(),
        }
        data = Transponder_Codec.encode_bytes(payload)
        dests = self._destinations()
        print(
            f"[{self.name} PULSE] seq={seq} text={payload['text']!r} → {len(dests)} tuner(s)",
            flush=True,
        )
        for dest, _tname in dests:
            for _k in range(self.repeat):
                try:
                    self.sock.sendto(data, dest)
                except OSError as e:
                    print(f"[{self.name} SEND FAIL] {Transponder_Locators.fmt_addr(dest)} {e}", flush=True)


_Station_internal = Station_internal()

class Station:

    @staticmethod
    def run(self, hold: float | None) -> None:
        deadline = None if hold is None else time.time() + hold
        try:
            while self.alive.is_set():
                self.emit()
                if deadline is not None and time.time() >= deadline:
                    return
                time.sleep(self.interval)
        except KeyboardInterrupt:
            print(flush=True)

    @staticmethod
    def close(self) -> None:
        self.alive.clear()
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None
        print(f"[{self.name} CLOSE] {self.addr_s()} registry={len(self.registry)}", flush=True)

    @staticmethod
    def addr_s(self) -> str:
        return f"udp://{Transponder_Locators.fmt_addr(self.listen)}"

    @staticmethod
    def start(self) -> None:
        self.sock = UdpMail.bind_udp(self.listen)
        self.alive.set()
        self.join_thread = threading.Thread(target=self._join_loop, name=f"{self.name}-join", daemon=True)
        self.join_thread.start()
        print(f"[{self.name} STATION] join-mailbox {self.addr_s()}", flush=True)

    @staticmethod
    def next_seq(self) -> int:
        with self.seq_lock:
            self.seq += 1
            return self.seq

    @staticmethod
    def emit(self) -> None:
        seq = self.next_seq()
        payload = {
            "from": self.name,
            "kind": "pulse",
            "seq": seq,
            "text": f"pulse {seq}",
            "ts": time.time(),
        }
        data = Transponder_Codec.encode_bytes(payload)
        dests = self._destinations()
        print(
            f"[{self.name} PULSE] seq={seq} text={payload['text']!r} → {len(dests)} tuner(s)",
            flush=True,
        )
        for dest, _tname in dests:
            for _k in range(self.repeat):
                try:
                    self.sock.sendto(data, dest)
                except OSError as e:
                    print(f"[{self.name} SEND FAIL] {Transponder_Locators.fmt_addr(dest)} {e}", flush=True)


# === Tuner (class) ===
class Tuner_internal:
    def __init__(self, name: str, listen: tuple[str, int], station: tuple[str, int]):
        self.name = name
        self.listen = listen
        self.station = station
        self.sock = None
        self.alive = threading.Event()
        self.inbox = []
        self.seen = set()
        self.recv_thread = None

    def _recv_loop(self) -> None:
        while self.alive.is_set():
            try:
                raw, src = self.sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                incoming = Transponder_Codec.decode_msg(raw)
            except Exception as e:
                print(f"[{self.name} BAD JSON] {e}: {raw!r}", flush=True)
                continue
            kind = incoming.get("kind", "?")
            if kind != "pulse":
                print(f"[{self.name} IGNORE] kind={kind!r} from={src}", flush=True)
                continue
            seq = incoming.get("seq")
            key = (incoming.get("from"), seq)
            if key in self.seen:
                print(f"[{self.name} DUP] seq={seq} (redundant copy ignored)", flush=True)
                continue
            self.seen.add(key)
            self.inbox.append(incoming)
            text = incoming.get("text", "")
            origin = incoming.get("from", "?")
            print(f"[{self.name} RECV] from={origin} seq={seq} text={text!r}", flush=True)

    def addr_s(self) -> str:
        return f"udp://{Transponder_Locators.fmt_addr(self.listen)}"

    def start(self) -> None:
        self.sock = UdpMail.bind_udp(self.listen)
        self.alive.set()
        self.recv_thread = threading.Thread(target=self._recv_loop, name=f"{self.name}-recv", daemon=True)
        self.recv_thread.start()
        print(
            f"[{self.name} TUNER] recv {self.addr_s()}  station udp://{Transponder_Locators.fmt_addr(self.station)}",
            flush=True,
        )


_Tuner_internal = Tuner_internal()

class Tuner:

    @staticmethod
    def tune(self) -> None:
        payload = {
            "kind": "tune",
            "name": self.name,
            "recv": Transponder_Locators.fmt_addr(self.listen),
            "ts": time.time(),
        }
        self.sock.sendto(Transponder_Codec.encode_bytes(payload), self.station)
        print(f"[{self.name} TUNE] sent to {Transponder_Locators.fmt_addr(self.station)} recv={Transponder_Locators.fmt_addr(self.listen)}", flush=True)

    @staticmethod
    def wait_for_station(self, timeout: float) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            self.tune()
            time.sleep(0.25)
            if self.inbox:
                print(f"[{self.name} STATION UP] first pulse in inbox", flush=True)
                return
        print(f"[{self.name} STATION WAIT] timed out; still listening", flush=True)

    @staticmethod
    def run(self, hold: float | None) -> None:
        if hold is not None:
            time.sleep(hold)
            return
        print(f"[{self.name} READY] listening for pulses, Ctrl-C to quit", flush=True)
        try:
            while self.alive.is_set():
                time.sleep(0.2)
        except KeyboardInterrupt:
            print(flush=True)

    @staticmethod
    def close(self) -> None:
        self.alive.clear()
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None
        print(f"[{self.name} CLOSE] {self.addr_s()} heard={len(self.inbox)}", flush=True)

    @staticmethod
    def addr_s(self) -> str:
        return f"udp://{Transponder_Locators.fmt_addr(self.listen)}"

    @staticmethod
    def start(self) -> None:
        self.sock = UdpMail.bind_udp(self.listen)
        self.alive.set()
        self.recv_thread = threading.Thread(target=self._recv_loop, name=f"{self.name}-recv", daemon=True)
        self.recv_thread.start()
        print(
            f"[{self.name} TUNER] recv {self.addr_s()}  station udp://{Transponder_Locators.fmt_addr(self.station)}",
            flush=True,
        )


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
    _instance = None

    def __init__(self, config=None):
        self.config = config or {}
        self.echo_payload = None
        self.negative = self
        self.lock = threading.Lock()
        self.socket_path = generate_unique_socket_path()
        self.ws = None
        self.wire = self.config.get("wire")

    def __new__(self, cls, config):
        if cls._instance is None:
            cls._instance = object.__new__(cls)
            cls._instance.ws = None
            cls._instance.up_queue = deque()  # incoming messages from another server to middleware
            cls._instance.down_queue = deque()  # outgoing messages from middleware to another server
            cls._instance._busy_down = False
            cls._instance._busy_up = False
            cls._instance.wire = None
            cls._instance.echo_seen = set()
        return cls._instance

    def _start_up_pump(self):
        if getattr(self, "_pump_started", False):
            return
        self._pump_started = True
        self._pump_alive = True

        def pump():
            while getattr(self, "_pump_alive", False):
                if self.up_queue and not self._busy_up:
                    self.process_up_queue()
                time.sleep(0.05)

        threading.Thread(target=pump, name="neg-up-pump", daemon=True).start()

    def inject_echo_payload(self, func):
        def wrapper(self, *args, **kwargs):
            if 'payload' not in kwargs and hasattr(self, 'echo_payload'):
                kwargs['payload'] = self.echo_payload
            return func(self, *args, **kwargs)
        return wrapper

    def process_down_queue(self):
        with self.lock:
            manifest.info("This was triggered.")
            if self._busy_down: return
            for item in list(self.down_queue):
                self._busy_down = True
                if self.down_queue[0]:
                    self.sender(self.ws, self.down_queue[0])
                    token = self.down_queue[0]['communicator_token']
                    self.wait_for_echo(token)
                    self.down_queue.popleft()
                    self._busy_down = False

    def sender(self, ws, payload):
        body = payload if isinstance(payload, dict) else freight.upgrades(payload)
        if self.wire is None:
            raise RuntimeError("NegativeCom.sender has no Wire attached")
        self.wire.send(body)
        if isinstance(body, dict) and "received" in body:
            self.echo_seen.add(body["received"])

    def process_up_queue(self):
        if self._busy_up: return
        manifest.info('Processing up_queue')
        for item in list(self.up_queue):
            self._busy_up = True
            if self.up_queue[0]:
                self.negative.from_N(self.up_queue[0])
                token = freight.get(freight_obj=self.up_queue[0], key='communicator_token')
                self.wait_for_echo(token)
                self.up_queue.popleft()
        manifest.info('up_queue processed')
        self._busy_up = False

    def wait_for_echo(self, token):
        while True:
            time.sleep(0.1)
            if token in getattr(self, "echo_seen", ()):
                return
            for msg in list(self.up_queue):
                if msg.get('received') == token:
                    self.up_queue.remove(msg)
                    return

    def from_N(self, payload):
        manifest.info(truncate(500, payload))
        token = freight.get(freight_obj=payload, key='communicator_token')
        if token and self.ws:
            echo_payload = {'received': token}
            if payload.get('echo') == 'delay':
                time.sleep(0.1)
                pass
            else:
                self.sender(self.ws, echo_payload)


_NegativeCom_internal = NegativeCom_internal()

class NegativeCom:

    @staticmethod
    def attach_wire(self, wire):
        self.wire = wire
        self.ws = wire
        if not hasattr(self, "echo_seen"):
            self.echo_seen = set()
        self._start_up_pump()
        return wire

    # Break is necessary to prevent rapid useless error loops. This is v1 Failure should be loud, but not repatative.
    @staticmethod
    def receiver(self, ws, message=None):
        if message:
            manifest.info(f'Message received: {truncate(500, message)}')
            data = freight.upgrades(message=message)
            if "received" in data:
                self.echo_seen.add(data["received"])
                return
            self.up_queue.append(data)
            manifest.info('Message appended to up_queue')

    @staticmethod
    @inject_echo_payload
    def echo(self, payload=None):
        token = freight.get(freight_obj=payload, key='communicator_token') if payload else None
        if token and self.ws:
            echo_payload = {'received': token}
            self.sender(self.ws, freight.upgrades(echo_payload))

    @staticmethod
    def to_N(self, payload):
        manifest.info(truncate(500, payload))
        payload = freight.upgrades(payload)
        self.down_queue.append(payload)
        self.process_down_queue()

    @staticmethod
    def inject_echo_payload(func):
        def wrapper(self, *args, **kwargs):
            if 'payload' not in kwargs and hasattr(self, 'echo_payload'):
                kwargs['payload'] = self.echo_payload
            return func(self, *args, **kwargs)
        return wrapper

    @staticmethod
    def process_down_queue(self):
        with self.lock:
            manifest.info("This was triggered.")
            if self._busy_down: return
            for item in list(self.down_queue):
                self._busy_down = True
                if self.down_queue[0]:
                    self.sender(self.ws, self.down_queue[0])
                    token = self.down_queue[0]['communicator_token']
                    self.wait_for_echo(token)
                    self.down_queue.popleft()
                    self._busy_down = False

    @staticmethod
    def sender(self, ws, payload):
        body = payload if isinstance(payload, dict) else freight.upgrades(payload)
        if self.wire is None:
            raise RuntimeError("NegativeCom.sender has no Wire attached")
        self.wire.send(body)
        if isinstance(body, dict) and "received" in body:
            self.echo_seen.add(body["received"])

    @staticmethod
    def process_up_queue(self):
        if self._busy_up: return
        manifest.info('Processing up_queue')
        for item in list(self.up_queue):
            self._busy_up = True
            if self.up_queue[0]:
                self.negative.from_N(self.up_queue[0])
                token = freight.get(freight_obj=self.up_queue[0], key='communicator_token')
                self.wait_for_echo(token)
                self.up_queue.popleft()
        manifest.info('up_queue processed')
        self._busy_up = False

    @staticmethod
    def wait_for_echo(self, token):
        while True:
            time.sleep(0.1)
            if token in getattr(self, "echo_seen", ()):
                return
            for msg in list(self.up_queue):
                if msg.get('received') == token:
                    self.up_queue.remove(msg)
                    return

    @staticmethod
    def from_N(self, payload):
        manifest.info(truncate(500, payload))
        token = freight.get(freight_obj=payload, key='communicator_token')
        if token and self.ws:
            echo_payload = {'received': token}
            if payload.get('echo') == 'delay':
                time.sleep(0.1)
                pass
            else:
                self.sender(self.ws, echo_payload)


# === PositiveCom (class) ===
class PositiveCom_internal:
    _instance = None
    # Clarification: PositiveCom only has permission to receive and maintain websocket connections.

    def __init__(self, config=None):
        self.config = config or {}
        self.echo_payload = None
        self.positive = self
        self.socket_path = generate_unique_socket_path()
        self.ws = None
        self.wire = self.config.get("wire")

    def __new__(self, cls, config):
        if cls._instance is None:
            cls._instance = object.__new__(cls)
            cls._instance.config = config
            cls._instance.positive_addr = cls._instance.config.get('positive_address', {})
            cls._instance.port = int(cls._instance.positive_addr.get('port', 0))
            PositiveCom._preemptive_port_cleanup(cls._instance.port)
            cls._instance.ws = None
            cls._instance.connections = {}
            cls._instance.ws_token_dict = {}
            cls._instance.ws_id = id(cls._instance)
            cls._instance.up_queue = deque()  # incoming messages from another server to middleware
            cls._instance.down_queue = deque()  # outgoing messages from middleware to another server
            cls._instance._busy_down = False
            cls._instance._busy_up = False
            cls._instance.wire = None
            cls._instance.connections = getattr(cls._instance, "connections", {})
            cls._instance.echo_seen = set()
        return cls._instance

    def inject_echo_payload(self, func):
        def wrapper(self, *args, **kwargs):
            if 'payload' not in kwargs and hasattr(self, 'echo_payload'):
                kwargs['payload'] = self.echo_payload
            return func(self, *args, **kwargs)
        return wrapper

    @staticmethod
    def _find_pids_on_port(self, port: int) -> set[int]:
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

    @staticmethod
    def _preemptive_port_cleanup(self, port: int) -> None:
        if port <= 0:
            return
        pids = PositiveCom._find_pids_on_port(port)
        for pid in sorted(pids):
            if pid == os.getpid():
                continue
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                continue
            time.sleep(0.1)

    def process_down_queue(self):
        if self._busy_down: return
        for item in list(self.down_queue):
            self._busy_down = True
            if self.down_queue[0]:
                payload = self.down_queue[0]
                token = freight.get(freight_obj=payload, key='communicator_token')
                if token and token in self.ws_token_dict:
                    ws_id = self.ws_token_dict[token]
                    if ws_id in self.connections:
                        self.sender(self.connections[ws_id], self.down_queue[0])
                        token = freight.get(freight_obj=self.down_queue[0], key='communicator_token')
                        self.wait_for_echo(token)
                        self.down_queue.popleft()
        self._busy_down = False

    def wait_for_echo(self, token):
        while True:
            time.sleep(0.1)
            if token in getattr(self, "echo_seen", ()):
                return
            for msg in list(self.up_queue):
                if msg.get('received') == token:
                    self.up_queue.remove(msg)
                    return

    def process_up_queue(self):
        if self._busy_up: return
        for item in list(self.up_queue):
            self._busy_up = True
            if self.up_queue[0]:
                self.positive.from_P(self.up_queue[0])
                token = freight.get(freight_obj=self.up_queue[0], key='communicator_token')
                self.wait_for_echo(token)
                self.up_queue.popleft()
        self._busy_up = False

    def sender(self, ws, payload):
        body = payload if isinstance(payload, dict) else freight.upgrades(payload)
        if self.wire is None:
            raise RuntimeError("PositiveCom.sender has no Wire attached")
        self.wire.send(body)
        if isinstance(body, dict) and "received" in body:
            self.echo_seen.add(body["received"])

    def from_P(self, payload):
        manifest.info(truncate(500, payload))
        token = freight.get(freight_obj=payload, key='communicator_token')
        ws_id = self.ws_token_dict.get(token)
        ws = self.connections.get(ws_id)
        if token and ws:
            echo_payload = {'received': token}
            if payload.get('echo') == 'delay':
                pass
            else:
                self.sender(ws, echo_payload)


_PositiveCom_internal = PositiveCom_internal()

class PositiveCom:

    @staticmethod
    def attach_wire(self, wire):
        self.wire = wire
        self.ws = wire
        self.connections[id(wire)] = wire
        if not hasattr(self, "echo_seen"):
            self.echo_seen = set()
        if not getattr(self, "_pump_started", False):
            self._pump_started = True
            self._pump_alive = True

            def pump():
                while getattr(self, "_pump_alive", False):
                    if self.up_queue and not self._busy_up:
                        self.process_up_queue()
                    time.sleep(0.05)

            threading.Thread(target=pump, name="pos-up-pump", daemon=True).start()
        return wire

    # Break is necessary to prevent rapid useless error loops. This is v1 Failure should be loud, but not repatative.
    @staticmethod
    def receiver(self, ws, message=None):
        if message:
            data = freight.upgrades(message=message)
            token = freight.get(freight_obj=data, key='communicator_token')
            handle = ws if ws is not None else self.wire
            if token and handle is not None:
                self.ws_token_dict[token] = id(handle)
                self.connections[id(handle)] = handle
            if "received" in data:
                self.echo_seen.add(data["received"])
                return
            self.up_queue.append(data)
            manifest.info('Message appended to up_queue')

    @staticmethod
    @inject_echo_payload
    def echo(self, payload=None):
        token = freight.get(freight_obj=payload, key='communicator_token') if payload else None
        if token and self.ws:
            echo_payload = {'received': token}
            self.sender(self.ws, freight.upgrades(echo_payload))

    @staticmethod
    def to_P(self, payload):
        manifest.info(truncate(500, payload))
        payload = freight.upgrades(payload)
        self.down_queue.append(payload)
        self.process_down_queue()

    @staticmethod
    def inject_echo_payload(func):
        def wrapper(self, *args, **kwargs):
            if 'payload' not in kwargs and hasattr(self, 'echo_payload'):
                kwargs['payload'] = self.echo_payload
            return func(self, *args, **kwargs)
        return wrapper

    @staticmethod
    @staticmethod
    def _find_pids_on_port(port: int) -> set[int]:
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

    @staticmethod
    @staticmethod
    def _preemptive_port_cleanup(port: int) -> None:
        if port <= 0:
            return
        pids = PositiveCom._find_pids_on_port(port)
        for pid in sorted(pids):
            if pid == os.getpid():
                continue
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                continue
            time.sleep(0.1)

    @staticmethod
    def process_down_queue(self):
        if self._busy_down: return
        for item in list(self.down_queue):
            self._busy_down = True
            if self.down_queue[0]:
                payload = self.down_queue[0]
                token = freight.get(freight_obj=payload, key='communicator_token')
                if token and token in self.ws_token_dict:
                    ws_id = self.ws_token_dict[token]
                    if ws_id in self.connections:
                        self.sender(self.connections[ws_id], self.down_queue[0])
                        token = freight.get(freight_obj=self.down_queue[0], key='communicator_token')
                        self.wait_for_echo(token)
                        self.down_queue.popleft()
        self._busy_down = False

    @staticmethod
    def wait_for_echo(self, token):
        while True:
            time.sleep(0.1)
            if token in getattr(self, "echo_seen", ()):
                return
            for msg in list(self.up_queue):
                if msg.get('received') == token:
                    self.up_queue.remove(msg)
                    return

    @staticmethod
    def process_up_queue(self):
        if self._busy_up: return
        for item in list(self.up_queue):
            self._busy_up = True
            if self.up_queue[0]:
                self.positive.from_P(self.up_queue[0])
                token = freight.get(freight_obj=self.up_queue[0], key='communicator_token')
                self.wait_for_echo(token)
                self.up_queue.popleft()
        self._busy_up = False

    @staticmethod
    def sender(self, ws, payload):
        body = payload if isinstance(payload, dict) else freight.upgrades(payload)
        if self.wire is None:
            raise RuntimeError("PositiveCom.sender has no Wire attached")
        self.wire.send(body)
        if isinstance(body, dict) and "received" in body:
            self.echo_seen.add(body["received"])

    @staticmethod
    def from_P(self, payload):
        manifest.info(truncate(500, payload))
        token = freight.get(freight_obj=payload, key='communicator_token')
        ws_id = self.ws_token_dict.get(token)
        ws = self.connections.get(ws_id)
        if token and ws:
            echo_payload = {'received': token}
            if payload.get('echo') == 'delay':
                pass
            else:
                self.sender(ws, echo_payload)


