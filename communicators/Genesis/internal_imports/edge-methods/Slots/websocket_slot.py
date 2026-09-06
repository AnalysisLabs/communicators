#!/usr/bin/env python3
"""WebSocket connection-slot prototype.

Like TCP, a WebSocket is duplex after the handshake. Both processes share
one host:port. The first process to bind becomes the listener; the other
dials. After the socket exists, both sides send and receive.

Terminal A:
  python websocket_slot.py --name FOX   --listen 127.0.0.1:9101 --peer 127.0.0.1:9101

Terminal B:
  python websocket_slot.py --name OTTER --listen 127.0.0.1:9101 --peer 127.0.0.1:9101

`--listen` and `--peer` are kept so the CLI matches slot_http.py. For this
slot they must name the same address.

Type a line and press enter to send. Ctrl-C to quit.

Non-interactive proof:
  python websocket_slot.py --name FOX   --listen 127.0.0.1:9101 --peer 127.0.0.1:9101 --auto --hold 4
  python websocket_slot.py --name OTTER --listen 127.0.0.1:9101 --peer 127.0.0.1:9101 --auto --hold 4

Wire framing: one JSON object per WebSocket text frame.
encode at send, decode at recv.

Capability row (harvest later for L1):
  listen yes | accept yes | connect yes | send yes | recv yes | close yes
  serve yes | request_response yes | send_and_close yes | persistent_client yes
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time

from websockets.sync.client import connect
from websockets.sync.server import serve


# ---------------------------------------------------------------------------
# JSON framing — the only payload format this slot speaks
# Stream boundary is the WebSocket text frame (TCP used a newline).
# ---------------------------------------------------------------------------

def encode_msg(payload: dict) -> str:
    if not isinstance(payload, dict):
        raise TypeError(f"payload must be dict, got {type(payload)!r}")
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def decode_msg(raw) -> dict:
    if raw is None or raw == b"" or raw == "":
        return {}
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


def parse_hostport(spec: str) -> tuple[str, int]:
    spec = spec.strip()
    if "://" in spec:
        spec = spec.split("://", 1)[1]
    if spec.count(":") != 1:
        raise ValueError(f"expected host:port, got {spec!r}")
    host, port_s = spec.rsplit(":", 1)
    host = "127.0.0.1" if host in ("", "localhost") else host
    return host, int(port_s)


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

class WsSlot:
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

    def addr_s(self) -> str:
        return f"ws://{self.host}:{self.port}"

    def next_seq(self) -> int:
        with self.seq_lock:
            self.seq += 1
            return self.seq

    def _server_handler(self, websocket):
        self.ws = websocket
        self.role = self.role or "listen"
        self.alive.set()
        self.attached.set()
        print(f"[{self.name} ACCEPT] {self.addr_s()}", flush=True)
        try:
            for raw in websocket:
                try:
                    incoming = decode_msg(raw)
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
                    incoming = decode_msg(raw)
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

    def wait_for_peer(self, timeout: float = 20.0) -> None:
        if not self.attached.is_set():
            self.attach(timeout)
        print(f"[{self.name} PEER UP] role={self.role} addr={self.addr_s()}", flush=True)

    def _handle_incoming(self, incoming: dict) -> None:
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
        data = encode_msg(payload)
        with self.send_lock:
            self.ws.send(data)

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

    def burst(self) -> None:
        for line in silly_for(self.name):
            try:
                self.send_text(line)
            except Exception as e:
                print(f"[{self.name} SEND FAIL] {type(e).__name__}: {e}", flush=True)
            time.sleep(0.15)

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

    def close(self) -> None:
        self.alive.clear()
        if self.ws is not None:
            try:
                self.ws.close()
            except Exception:
                pass
            self.ws = None
        self._stop_server()


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="WebSocket slot prototype — one shared host:port, duplex socket")
    p.add_argument("--name", required=True, help="endpoint identity printed on every message")
    p.add_argument("--listen", required=True, help="shared host:port (must equal --peer)")
    p.add_argument("--peer", required=True, help="shared host:port (must equal --listen)")
    p.add_argument("--auto", action="store_true", help="send canned burst, skip stdin")
    p.add_argument("--hold", type=float, default=3.0, help="seconds to stay alive after --auto burst")
    p.add_argument("--wait", type=float, default=20.0, help="seconds to wait for the duplex socket")
    return p.parse_args(argv)


def stdin_loop(slot: WsSlot) -> None:
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
    if listen != peer:
        print(
            "websocket slot uses one duplex socket; --listen and --peer must be the same host:port\n"
            f"  listen={listen!r} peer={peer!r}",
            file=sys.stderr,
        )
        return 2

    slot = WsSlot(args.name, listen)
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
        print(f"[{slot.name} CLOSE] {slot.addr_s()}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
