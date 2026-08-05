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
        manifest.info("New connection established", process_path="Metamorphosis.generated.egg_transpiler.imports!tier2.transponder_internal.handle_connection")

        try:
            while True:
                data = self.recv(conn, 4096)
                if not data:
                    manifest.error("Connection closed by remote side", process_path="Metamorphosis.generated.egg_transpiler.imports!tier2.transponder_internal.handle_connection")
                    break

                manifest.info(f"Received: {data}", process_path="Metamorphosis.generated.egg_transpiler.imports!tier2.transponder_internal.handle_connection")

                # Simple response to prove bidirectional flow
                # You can change this to whatever you want for testing
                response = b"ACK\n"
                self.sendall(conn, response)

        except Exception as e:
            manifest.error(f"Connection error: {e}", process_path="Metamorphosis.generated.egg_transpiler.imports!tier2.transponder_internal.handle_connection")


_transponder_internal = transponder_internal()

class transponder:

    # High level:

    @staticmethod
    def persistent_server(host, port):
        if host == 'localhost': host = '127.0.0.1'
        listener = _transponder_internal.create_listener(host, port)
        manifest.info("Transponder active", process_path="Metamorphosis.generated.egg_transpiler.imports!tier2.transponder.persistent_server")

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
localhost = "localhost"

def load(object_program: str = None, with_program: str = None, in_namespace: dict = None, from_namespace: dict = None, to_namespace: dict = None):
    if os.path.exists(str(object_program)):
        contents = open(object_program).read()
    else:
        contents = object_program
    if with_program:
        contents = subprocess.run(['python3', with_program, object_program], capture_output=True, text=True).stdout
    r = transponder.request_response(localhost, 8765, {(in_namespace or to_namespace): contents})
    # wait for simple 200 response as green light (detailed pseudocode placeholder)
    return

def build(object_program: str, with_program: str, in_namespace: dict, from_namespace: dict = None, to_namespace: dict = None):
    contents = transponder.request_response(localhost, 8765, (in_namespace or from_namespace))
    result = subprocess.run(['python3', with_program, object_program], capture_output=True, text=True).stdout
    transponder.send_and_close(localhost, 8765, {(in_namespace or to_namespace): result})

def final_byte_cleanup(dirty_line: str) -> str:
    """Final byte literal pass: remove all " (only ' matter for f-strings)."""
    b = dirty_line.encode('utf-8')
    b = b.replace(b'"', b'')
    return b.decode('utf-8')

# Validity check
def parse_line(line):
    # Strip numbered prefix
    line = line.strip()
    words = line.split()
    if len(words) < 3 or not words[0].rstrip('.').isdigit() or words[1] not in ['load', 'build']:
        return None
    num_str = words[0].rstrip('.')
    verb, obj = words[1], words[2]
    path = f"f'{{base_dir}}/{obj}'".encode()
    kwargs = {'object_program': path.replace(b'"', b'').decode()}
    for i in range(3, len(words)):
        if words[i] == 'with' and i + 1 < len(words):
            kwargs['with_program'] = f"f'{{base_dir}}/{words[i + 1]}'"
        if words[i] == 'in' and i + 1 < len(words):
            kwargs['in_namespace'] = f"f'{{base_dir}}/{words[i + 1]}'"
        if words[i] == 'from' and i + 1 < len(words):
            kwargs['from_namespace'] = f"f'{{base_dir}}/{words[i + 1]}'"
        if words[i] == 'to' and i + 1 < len(words):
            kwargs['to_namespace'] = f"f'{{base_dir}}/{words[i + 1]}'"
    kw_str = ', '.join(f'{k}="{v}"' for k, v in kwargs.items())
    dirty_line = f'code_block_{num_str} = {verb}({kw_str})'
    return final_byte_cleanup(dirty_line)

def transpile(md_file):
    code = []
    ordered_objects = []
    has_invalid = False
    invalid_lines = []
    with open(md_file, 'r') as f:
        for num, line in enumerate(f, 1):
            parsed = parse_line(line)
            if parsed:
                code.append(parsed)
            else:
                has_invalid = True
                invalid_lines.append(f'Line {num}: {line.rstrip()!r}')
    if has_invalid:
        # raise ValueError('This is not valid assembly line script')
        raise ValueError(f'Invalid lines in {md_file}:\n' + '\n'.join(invalid_lines))

    # return '\n'.join(code)

    generated_code = '\n'.join(code)
    imports_str = "base_dir = f'{COMMUNICATORS_ROOT}/state-methods'\n\n"
    # Copy load/build verbatim dynamically
    load_src = inspect.getsource(load)
    build_src = inspect.getsource(build)
    generated_code = imports_str + "\n" + load_src + '\n' + build_src + '\n' + generated_code
    # Minimal addition: process code to check object_program='to' uniqueness
    tree = ast.parse(generated_code)
    objects = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and
            isinstance(node.func, ast.Name) and
            node.func.id in ('load', 'build')):
            for kw in node.keywords:
                if kw.arg == 'object_program':
                    if isinstance(kw.value, ast.Constant):
                        objects.append(ast.literal_eval(kw.value))
                    else:
                        objects.append(ast.unparse(kw.value).strip("'\""))
                    break
    counts = Counter(objects)
    shared = {k: v for k, v in counts.items() if v > 1}
    print(f"All 'to' (object_program=) values {'unique' if not shared else f'shared: {shared}'}. Ready for _to_ handling if needed (What's next.md).")
    return generated_code

if __name__ == '__main__':
    md_file = f'{COMMUNICATORS_ROOT}/state-methods/panel.md'
    cat = transpile(md_file)
    with open('caterpillar_transpiler.py', 'w') as f:
        f.write(cat)
    load(object_program=cat, in_namespace='metamorphosis')
    os.execvp('python3', ['python3', 'caterpillar_transpiler.py'])

