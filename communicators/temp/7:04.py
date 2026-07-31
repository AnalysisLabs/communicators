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
from pathlib import Path
COMMUNICATORS_ROOT = Path('/home/prometheusd/Analysis Labs/Dev Tools/com-branches/orchestrated-3/communicators')

class Manifest_internal:

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
            if caller_file not in internal_files and '/usr/lib/python' not in frame.f_code.co_filename:
                return f'{frame.f_code.co_filename}.{frame.f_code.co_qualname}'
            frame = frame.f_back
        return None

    def _log(self, level, message):
        frame = inspect.currentframe().f_back.f_back
        filename = frame.f_code.co_filename.rsplit('/', 1)[-1]
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
_Manifest_internal = Manifest_internal()

class Manifest:

    @staticmethod
    def debug(*args):
        message = ' '.join((str(arg) for arg in args))
        _Manifest_internal._log('DEBUG', message)

    @staticmethod
    def info(*args):
        message = ' '.join((str(arg) for arg in args))
        _Manifest_internal._log('INFO', message)

    @staticmethod
    def warning(*args):
        message = ' '.join((str(arg) for arg in args))
        _Manifest_internal._log('WARNING', message)

    @staticmethod
    def error(*args):
        message = ' '.join((str(arg) for arg in args))
        _Manifest_internal._log('ERROR', message)

    @staticmethod
    def critical(*args):
        message = ' '.join((str(arg) for arg in args))
        _Manifest_internal._log('CRITICAL', message)

    @staticmethod
    def printer(*args):
        message = ' '.join((str(arg) for arg in args))
        _Manifest_internal._log('PRINTER', message)

    @staticmethod
    def json(*args):
        messages = []
        for arg in args:
            try:
                if isinstance(arg, str):
                    json.loads(arg)
                messages.append(json.dumps(arg))
            except:
                messages.append('{invalid json}')
        _Manifest_internal._log('JSON', ' '.join(messages))

    @staticmethod
    def freight(*args):
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
        _Manifest_internal._log('FREIGHT', ' '.join(messages))

class transponder_internal:

    def is_complete(self, response):
        """Simple delimiter check for the current placeholder protocol."""
        if isinstance(response, dict):
            response = json.dumps(response).encode()
        return response.endswith(b'\n') or b'ACK' in response

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
        Manifest.info('New connection established')
        try:
            while True:
                data = _transponder_internal.recv(conn, 4096)
                if not data:
                    Manifest.error('Connection closed by remote side')
                    break
                Manifest.info(f'Received: {data}')
                response = b'ACK\n'
                _transponder_internal.sendall(conn, response)
        except Exception as e:
            Manifest.error(f'Connection error: {e}')
_transponder_internal = transponder_internal()

class transponder:

    @staticmethod
    def persistent_server(host, port):
        if host == 'localhost':
            host = '127.0.0.1'
        listener = _transponder_internal.create_listener(host, port)
        Manifest.info('Transponder active')
        while True:
            conn = _transponder_internal.accept_connection(listener)
            _transponder_internal.handle_connection(conn)

    @staticmethod
    def send_and_close(host, port, data):
        if host == 'localhost':
            host = '127.0.0.1'
        conn = _transponder_internal.connect_to(host, port)
        conn.sendall(data)
        conn.close()

    @staticmethod
    def request_response(host, port, data):
        if host == 'localhost':
            host = '127.0.0.1'
        conn = _transponder_internal.connect_to(host, port)
        conn.sendall(data)
        response = b''
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                break
            response += chunk
            if _transponder_internal.is_complete(response):
                break
        conn.close()
        return response
    '\n    # We do not need this yet. It is important not is not needed for getting the namespace server working.\n    @externalmethod\n    def persistent_client(host="127.0.0.1", port=12345):\n        if host == \'conn = connect_to(host, port)localhost\': host = \'127.0.0.1\'\n\n\n        while True:\n            # send when needed\n            data = get_next_message()\n            if data:\n                conn.sendall(data)\n\n            # receive when available\n            response = conn.recv(4096)\n            if response:\n                handle_connection(response)\n    '
