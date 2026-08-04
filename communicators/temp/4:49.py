
# === Tier 0 (imports) ===

# === standard.py (from VirtualFS) ===
from __future__ import annotations
import argparse, ast, asyncio, httpx, inspect, json, math, numpy, os, random, re, requests, secrets, shutil, signal, socket, struct, subprocess, sys, threading, time, traceback, tracemalloc, uuid, websockets, yaml
from aiohttp import web
from collections import deque, Counter
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from scipy.stats import norm
from types import SimpleNamespace
from typing import Any, Dict
from weakref import WeakValueDictionary
from websockets.sync.server import serve

# === COMMUNICATORS_ROOT (resolved at prefix-build time) ===
from pathlib import Path
COMMUNICATORS_ROOT = Path('/home/prometheusd/Analysis Labs/Dev Tools/com-branches/orchestrated-3/communicators')

# === Tier 1 (imports) ===

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
        _manifest_internal._log('DEBUG', message)



    @staticmethod
    def info(*args, process_path=None):
        message = ' '.join(str(arg) for arg in args)
        _manifest_internal._log('INFO', message)



    @staticmethod
    def warning(*args, process_path=None):
        message = ' '.join(str(arg) for arg in args)
        _manifest_internal._log('WARNING', message)



    @staticmethod
    def error(*args, process_path=None):
        message = ' '.join(str(arg) for arg in args)
        _manifest_internal._log('ERROR', message)



    @staticmethod
    def critical(*args, process_path=None):
        message = ' '.join(str(arg) for arg in args)
        _manifest_internal._log('CRITICAL', message)



    @staticmethod
    def printer(*args, process_path=None):
        message = ' '.join(str(arg) for arg in args)
        _manifest_internal._log('PRINTER', message)



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
        _manifest_internal._log('JSON', ' '.join(messages))



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
        _manifest_internal._log('FREIGHT', ' '.join(messages))



# === Tier 2 (imports) ===

# === Transponder (class) ===
class transponder_internal:
    # Terms:

    def is_complete(response):
        """Simple delimiter check for the current placeholder protocol."""
        if isinstance(response, dict): response = json.dumps(response).encode()
        return response.endswith(b'\n') or b'ACK' in response



    # Utils:

    def create_listener(ip, port):
        l = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        l.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        l.bind((ip, port))
        l.listen(5)
        return l


    def accept_connection(listener):
        """
        Accepts an incoming connection on the listening endpoint.
        Returns the new connected endpoint (socket object) that can be used
        for send/recv with the remote side.
        """
        conn, addr = listener.accept()
        return conn


    def connect_to(host, port):
        """
        Actively connects to a remote listening endpoint (host, port).
        Returns the connected endpoint that can be used for send/recv.
        """
        conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        conn.connect((host, port))
        return conn


    def sendall(conn, data):
        """
        Send all bytes on the given connected endpoint.
        Blocks until all data is sent or an error occurs.
        """
        conn.sendall(data)


    def recv(conn, size):
        """
        Receive up to `size` bytes from the given connected endpoint.
        Returns the bytes received (may be fewer than `size`).
        """
        return conn.recv(size)


    def handle_connection(conn):
        """
        Minimal proof-of-concept handler.
        Receives data, prints it, and optionally echoes back a simple ACK.
        Good enough to validate that connections are working and bidirectional.
        """
        Manifest.info("New connection established")

        try:
            while True:
                data = recv(conn, 4096)
                if not data:
                    Manifest.error("Connection closed by remote side")
                    break

                Manifest.info(f"Received: {data}")

                # Simple response to prove bidirectional flow
                # You can change this to whatever you want for testing
                response = b"ACK\n"
                sendall(conn, response)

        except Exception as e:
            Manifest.error(f"Connection error: {e}")

_transponder_internal = transponder_internal()

class transponder:

    # High level:

    @staticmethod
    def persistent_server(host, port):
        if host == 'localhost': host = '127.0.0.1'
        listener = _transponder_internal.create_listener(host, port)
        Manifest.info("Transponder active")

        while True:
            conn = _transponder_internal.accept_connection(listener)
            # Hand off or handle directly
            _transponder_internal.handle_connection(conn)



    @staticmethod
    def send_and_close(host, port, data):
        if host == 'localhost': host = '127.0.0.1'
        conn = _transponder_internal.connect_to(host, port)
        conn._transponder_internal.sendall(data)           # fire-and-forget style
        conn.close()



    @staticmethod
    def request_response(host, port, data):
        if host == 'localhost': host = '127.0.0.1'
        conn = _transponder_internal.connect_to(host, port)
        conn._transponder_internal.sendall(data)

        response = b""
        while True:
            chunk = conn._transponder_internal.recv(4096)
            if not chunk:
                break
            response += chunk
            if _transponder_internal.is_complete(response):   # your simple check
                break

        conn.close()
        return response


# ==================== (USER PROGRAM) ====================
class BaseNamespace:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._data = {}
                    cls._instance._lock = threading.RLock()
                    cls._instance.initialize_states()
        return cls._instance

    def initialize_states(self):
        # Hook for subclasses to define states like ideal, real, temporary
        pass

    def __getattr__(self, name: str) -> Any:
        with self._lock:
            return self._data.get(name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name in ('_data', '_lock', '_instance'):
            super().__setattr__(name, value)
            return
        with self._lock:
            self._data[name] = value

    def __contains__(self, name: str) -> bool:
        with self._lock:
            return hasattr(self._data, name)

    def debug(self) -> None:
        keys = [k for k in dir(self._data) if not k.startswith('_')]
        print('🧠 Namespace contains:', sorted(keys))

    def snapshot_namespace(self, path: str) -> None:
        data = json.dumps({k: getattr(self._data, k) for k in dir(self._data) if not k.startswith('_')}).encode()
        with open(path, 'ab') as f: f.write(data)

_namespaces: Dict[str, BaseNamespace] = {}
_ns_lock = threading.Lock()

# API needs these fields(action, substance, namespace)

def initialize_namespace(*names: str) -> None:
    with _ns_lock:
        if BaseNamespace._instance is None:
            BaseNamespace()
        if name not in _namespaces:
            ns = BaseNamespace()
            for p in name.split('/'):
                if not hasattr(ns, p): setattr(ns, p, {})
            _namespaces[name] = getattr(ns, name.split('/')[-1])

def populate_namespace(name: str, data: dict[str, Any]) -> None:
    with _ns_lock:
        ns = _namespaces[name]
        if ns is None:
            initialize_namespace(name)
        for k, v in data.items():
            ns[k] = v

def _start_ns_server():
    """Start the namespace server using transponder instead of HTTPServer."""
    try:
        # Import here or at top: import transponder
        transponder.persistent_server('localhost', 8765)
    except Exception as e:
        manifest.error(f"Failed to start namespace server: {e}")

def port_in_use(host: str, port: int, timeout: float = 0.3) -> bool:
    """Check if something is listening on (host, port) using a raw TCP connect."""
    if host == 'localhost':
        host = '127.0.0.1'

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)

    try:
        result = sock.connect_ex((host, port))
        return result == 0  # 0 means connection succeeded → something is listening
    except Exception:
        return False
    finally:
        sock.close()


def kill_port(host: str = 'localhost', port: int = 8765) -> None:
    """Aggressively kill anything listening on the port (Linux/macOS)."""
    if host == 'localhost':
        host = '127.0.0.1'

    print(f"🔪 Checking/killing port {port}...")
    os.system(f'lsof -t -i:{port} | xargs kill -9 2>/dev/null || true')
    time.sleep(0.4)  # give OS time to release the socket

if port_in_use('localhost', 8765):
    kill_port('localhost', 8765)

_start_ns_server()
