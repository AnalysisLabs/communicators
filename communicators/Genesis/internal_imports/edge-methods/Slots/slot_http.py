#!/usr/bin/env python3
"""HTTP connection-slot prototype.

Each process is BOTH a server (positive / listen) and a client (negative / peer).
Messages are JSON objects on the wire. Encode at send, decode at recv.

Terminal A:
  python slot_http.py --name FOX --listen 127.0.0.1:9101 --peer 127.0.0.1:9102

Terminal B:
  python slot_http.py --name OTTER --listen 127.0.0.1:9102 --peer 127.0.0.1:9101

Type a line and press enter to send. Ctrl-C to quit.

Non-interactive proof (used by the sandbox test):
  python slot_http.py --name FOX --listen 127.0.0.1:9101 --peer 127.0.0.1:9102 --auto --hold 4

Capability row (harvest later for L1):
  listen yes | accept yes | connect yes | send yes | recv yes | close yes
  serve yes | request_response yes | send_and_close yes | persistent_client later
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


# ---------------------------------------------------------------------------
# JSON framing — the only payload format this slot speaks
# ---------------------------------------------------------------------------

def encode_msg(payload: dict) -> bytes:
    if not isinstance(payload, dict):
        raise TypeError(f"payload must be dict, got {type(payload)!r}")
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def decode_msg(raw) -> dict:
    if raw is None or raw == b"" or raw == "":
        return {}
    if isinstance(raw, (bytes, bytearray)):
        text = raw.decode("utf-8")
    else:
        text = str(raw)
    obj = json.loads(text)
    if not isinstance(obj, dict):
        raise ValueError(f"JSON root must be an object, got {type(obj).__name__}")
    return obj


def parse_hostport(spec: str) -> tuple[str, int]:
    spec = spec.strip()
    if "://" in spec:
        spec = spec.split("://", 1)[1]
    if spec.count(":") != 1:
        raise ValueError(f"expected host:port, got {spec!r}")
    host, port_s = spec.rsplit(":", 1)
    host = "127.0.0.1" if host in ("", "localhost") else host
    return host, int(port_s)


# Distinctive canned lines so each origin is obvious in the other terminal.
SILLY = {
    "FOX": [
        "quartz-fox juggles 17 pinecones under a magenta lighthouse",
        "FOX-only proverb: never trust a teapot that quotes Hegel",
        "FOX payload zebra-plaid #3 — this line must not appear on FOX as inbound from itself",
    ],
    "OTTER": [
        "otter-kelp accordion solo in B-flat minor, volume 11",
        "OTTER-only proverb: a polite cyclone still rearranges the furniture",
        "OTTER payload marmalade-submarine #9 — origin stamp is the point",
    ],
}


def silly_for(name: str) -> list[str]:
    if name in SILLY:
        return list(SILLY[name])
    return [
        f"{name} recites the serial number of a leftover moon: 7Q-NEBULA",
        f"{name} claims the spoon is a diplomat from the cutlery republic",
        f"{name} unique-stamp {int(time.time())} — look for this exact token",
    ]


# ---------------------------------------------------------------------------
# Slot
# ---------------------------------------------------------------------------

class HttpSlot:
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

    def next_seq(self) -> int:
        with self.seq_lock:
            self.seq += 1
            return self.seq

    def peer_url(self, path: str = "/msg") -> str:
        return f"http://{self.peer_host}:{self.peer_port}{path}"

    def listen_url(self) -> str:
        return f"http://{self.listen_host}:{self.listen_port}"

    # -- server (positive) ---------------------------------------------------

    def _handler_class(self):
        slot = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):
                return

            def _write(self, code: int, payload: dict):
                body = encode_msg(payload)
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
                    incoming = decode_msg(raw)
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

    def serve(self):
        Handler = self._handler_class()
        self.httpd = ThreadingHTTPServer((self.listen_host, self.listen_port), Handler)
        self.httpd.daemon_threads = True
        print(
            f"[{self.name} LISTEN] {self.listen_url()}  -> peer {self.peer_host}:{self.peer_port}",
            flush=True,
        )
        self.httpd.serve_forever()

    def start_server_thread(self):
        self.server_thread = threading.Thread(target=self.serve, name=f"{self.name}-http", daemon=True)
        self.server_thread.start()

    def close(self):
        if self.httpd is not None:
            self.httpd.shutdown()
            self.httpd.server_close()

    # -- client (negative) ---------------------------------------------------

    def request_response(self, payload: dict, timeout: float = 5.0) -> dict:
        body = encode_msg(payload)
        req = urllib.request.Request(
            self.peer_url("/msg"),
            data=body,
            method="POST",
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
        return decode_msg(raw)

    def wait_for_peer(self, timeout: float = 20.0) -> None:
        deadline = time.time() + timeout
        url = self.peer_url("/health")
        last_err = None
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(url, timeout=1.0) as resp:
                    info = decode_msg(resp.read())
                print(f"[{self.name} PEER UP] {info}", flush=True)
                return
            except Exception as e:
                last_err = e
                time.sleep(0.2)
        raise TimeoutError(f"{self.name} never saw peer at {url}: {last_err}")

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

    def burst(self) -> None:
        for line in silly_for(self.name):
            try:
                self.send_text(line)
            except Exception as e:
                print(f"[{self.name} SEND FAIL] {type(e).__name__}: {e}", flush=True)
            time.sleep(0.15)


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="HTTP slot prototype — each process listens and dials")
    p.add_argument("--name", required=True, help="endpoint identity printed on every message")
    p.add_argument("--listen", required=True, help="local host:port that serves POST /msg")
    p.add_argument("--peer", required=True, help="remote host:port this process POSTs to")
    p.add_argument("--auto", action="store_true", help="send canned burst, skip stdin")
    p.add_argument("--hold", type=float, default=3.0, help="seconds to stay alive after --auto burst")
    p.add_argument("--wait", type=float, default=20.0, help="seconds to wait for peer /health")
    return p.parse_args(argv)


def stdin_loop(slot: HttpSlot) -> None:
    print(f"[{slot.name} READY] type a line to send, Ctrl-C to quit", flush=True)
    try:
        for line in sys.stdin:
            text = line.rstrip("\n")
            if not text:
                continue
            if text in {":q", "/quit", "/exit"}:
                return
            try:
                slot.send_text(text)
            except Exception as e:
                print(f"[{slot.name} SEND FAIL] {type(e).__name__}: {e}", flush=True)
    except KeyboardInterrupt:
        print(flush=True)


def main(argv=None) -> int:
    args = parse_args(argv)
    listen = parse_hostport(args.listen)
    peer = parse_hostport(args.peer)
    if listen == peer:
        print("listen and peer are the same address; both endpoints need their own port", file=sys.stderr)
        return 2

    slot = HttpSlot(args.name, listen, peer)
    slot.start_server_thread()
    time.sleep(0.15)

    try:
        slot.wait_for_peer(timeout=args.wait)
        slot.burst()
        if args.auto:
            time.sleep(args.hold)
        else:
            stdin_loop(slot)
    except KeyboardInterrupt:
        print(flush=True)
    finally:
        slot.close()
        print(f"[{slot.name} CLOSE] listen {slot.listen_url()}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
