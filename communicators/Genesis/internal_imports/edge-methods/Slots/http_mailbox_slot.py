#!/usr/bin/env python3
"""HTTP mailbox slot prototype (WAN fallback when TCP / WebSocket are blocked).

Asymmetric on purpose. The server is the only reachable HTTP endpoint and
owns the queues. The client is not allowed to host a server; it POSTs
outbound messages and short-polls its inbox.

The server mints a UUID at startup and never forgets it for the life of
the process. That UUID names the server-side /dev/shm JSON bin. No
communicator tokens on the CLI.

Queued messages stay until the client fetches them, or until they sit
longer than one client poll cycle — then the server drops them.

Terminal 1 (reachable mailbox server):
  python http_mailbox_slot.py --role server --name FOX --listen 127.0.0.1:9101

Terminal 2 (polling client, outbound HTTP only):
  python http_mailbox_slot.py --role client --name OTTER --peer 127.0.0.1:9101 --poll 3

Type a line and press enter to send. :q or Ctrl-C to quit.

Non-interactive proof:
  python http_mailbox_slot.py --role server --name FOX   --listen 127.0.0.1:9101 --auto --hold 8 --poll 3
  python http_mailbox_slot.py --role client --name OTTER --peer   127.0.0.1:9101 --auto --hold 8 --poll 3

Client→server is immediate POST. Server→client waits up to --poll seconds.

Capability row (harvest later for L1):
  server: listen yes | accept yes | send(queue) yes | recv(POST) yes | request_response no
  client: listen no  | connect(HTTP) yes | send(POST) yes | recv(poll) yes | request_response no
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import uuid
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


BIN_DIR = "/dev/shm"


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


def fmt_addr(addr: tuple[str, int]) -> str:
    return f"{addr[0]}:{addr[1]}"


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
# Server-side mailbox (SHM bin keyed by the startup UUID)
# ---------------------------------------------------------------------------

class Mailbox:
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
        self.bin_path = os.path.join(BIN_DIR, f"http_mailbox_{self.mailbox_id}.json")
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
            os.makedirs(BIN_DIR, exist_ok=True)
            tmp = self.bin_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._snapshot(), fh, ensure_ascii=False, indent=2)
            os.replace(tmp, self.bin_path)
        except OSError:
            pass

    def unlink(self) -> None:
        for path in (self.bin_path, self.bin_path + ".tmp"):
            try:
                os.unlink(path)
            except OSError:
                pass

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

    def client_names(self) -> list[str]:
        with self.lock:
            return list(self.clients)

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

    def enqueue(self, dest: str, msg: dict) -> None:
        item = {"enqueued_at": time.time(), "msg": msg}
        with self.lock:
            if dest not in self.lanes:
                self.lanes[dest] = []
            self.lanes[dest].append(item)
            self._persist()

    def enqueue_all(self, msg: dict) -> list[str]:
        with self.lock:
            names = list(self.clients)
            now = time.time()
            for name in names:
                self.lanes.setdefault(name, []).append({"enqueued_at": now, "msg": msg})
            self._persist()
            return names

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


# ---------------------------------------------------------------------------
# Server role
# ---------------------------------------------------------------------------

class MailboxServer:
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

    def next_seq(self) -> int:
        with self.seq_lock:
            self.seq += 1
            return self.seq

    def listen_url(self) -> str:
        return f"http://{fmt_addr(self.listen)}"

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

            def _read_json(self) -> dict:
                n = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(n) if n else b""
                return decode_msg(raw)

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

    def serve(self):
        Handler = self._handler_class()
        self.httpd = ThreadingHTTPServer(self.listen, Handler)
        self.httpd.daemon_threads = True
        print(
            f"[{self.name} LISTEN] {self.listen_url()} mailbox={self.box.mailbox_id} bin={self.box.bin_path}",
            flush=True,
        )
        self.httpd.serve_forever()

    def start(self):
        self.server_thread = threading.Thread(target=self.serve, name=f"{self.name}-http", daemon=True)
        self.server_thread.start()
        threading.Thread(target=self._sweep_loop, name=f"{self.name}-ttl", daemon=True).start()

    def _sweep_loop(self):
        while not self.sweep_stop.wait(0.25):
            self.box.sweep()

    def wait_for_client(self, timeout: float) -> None:
        print(f"[{self.name} WAIT] for a tuner-style client to POST /tune", flush=True)
        if not self.client_present.wait(timeout=timeout):
            raise TimeoutError(f"{self.name} never saw a client join")
        print(f"[{self.name} PEER UP] clients={self.box.client_names()}", flush=True)

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

    def burst(self) -> None:
        for line in silly_for(self.name):
            self.send_text(line)
            time.sleep(0.15)

    def close(self):
        self.sweep_stop.set()
        if self.httpd is not None:
            self.httpd.shutdown()
            self.httpd.server_close()
        self.box.unlink()


# ---------------------------------------------------------------------------
# Client role — outbound HTTP only
# ---------------------------------------------------------------------------

class MailboxClient:
    def __init__(self, name: str, peer: tuple[str, int], poll: float):
        self.name = name
        self.peer = peer
        self.poll = poll
        self.seq = 0
        self.seq_lock = threading.Lock()
        self.mailbox_id = None
        self.stop = threading.Event()

    def next_seq(self) -> int:
        with self.seq_lock:
            self.seq += 1
            return self.seq

    def peer_url(self, path: str) -> str:
        return f"http://{fmt_addr(self.peer)}{path}"

    def _request(self, method: str, path: str, payload: dict | None = None, timeout: float = 5.0) -> dict:
        data = None if payload is None else encode_msg(payload)
        headers = {}
        if data is not None:
            headers["Content-Type"] = "application/json; charset=utf-8"
        req = urllib.request.Request(self.peer_url(path), data=data, method=method, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return decode_msg(resp.read())

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

    def tune(self) -> dict:
        info = self._request("POST", "/tune", {"from": self.name, "kind": "tune", "poll": self.poll, "ts": time.time()})
        self.mailbox_id = info.get("mailbox", self.mailbox_id)
        print(f"[{self.name} TUNE] {info}", flush=True)
        return info

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

    def poll_loop(self) -> None:
        while not self.stop.wait(self.poll):
            try:
                self.poll_once()
            except Exception as e:
                if self.stop.is_set():
                    return
                print(f"[{self.name} POLL FAIL] {type(e).__name__}: {e}", flush=True)

    def burst(self) -> None:
        for line in silly_for(self.name):
            try:
                self.send_text(line)
            except Exception as e:
                print(f"[{self.name} SEND FAIL] {type(e).__name__}: {e}", flush=True)
            time.sleep(0.15)

    def close(self):
        self.stop.set()


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="HTTP mailbox slot — server holds queues, client polls")
    p.add_argument("--role", required=True, choices=("server", "client"))
    p.add_argument("--name", required=True, help="endpoint identity printed on every message")
    p.add_argument("--listen", help="server bind host:port (server role)")
    p.add_argument("--peer", help="server host:port (client role)")
    p.add_argument("--poll", type=float, default=3.0, help="client poll cycle seconds; also the server TTL")
    p.add_argument("--auto", action="store_true", help="send canned burst, skip stdin")
    p.add_argument("--hold", type=float, default=8.0, help="seconds to stay alive after --auto burst")
    p.add_argument("--wait", type=float, default=20.0, help="seconds to wait for the other role")
    return p.parse_args(argv)


def stdin_loop(send_text) -> None:
    try:
        for line in sys.stdin:
            text = line.rstrip("\n")
            if not text:
                continue
            if text in {":q", "/quit", "/exit"}:
                return
            try:
                send_text(text)
            except Exception as e:
                print(f"[SEND FAIL] {type(e).__name__}: {e}", flush=True)
    except KeyboardInterrupt:
        print(flush=True)


def run_server(args) -> int:
    if not args.listen:
        print("server role requires --listen host:port", file=sys.stderr)
        return 2
    slot = MailboxServer(args.name, parse_hostport(args.listen), args.poll)
    slot.start()
    time.sleep(0.15)
    try:
        slot.wait_for_client(timeout=args.wait)
        slot.burst()
        if args.auto:
            time.sleep(args.hold)
        else:
            print(f"[{slot.name} READY] type a line to queue for clients, Ctrl-C to quit", flush=True)
            stdin_loop(slot.send_text)
    except KeyboardInterrupt:
        print(flush=True)
    finally:
        slot.close()
        print(f"[{slot.name} CLOSE] listen {slot.listen_url()} mailbox={slot.box.mailbox_id}", flush=True)
    return 0


def run_client(args) -> int:
    if not args.peer:
        print("client role requires --peer host:port", file=sys.stderr)
        return 2
    slot = MailboxClient(args.name, parse_hostport(args.peer), args.poll)
    try:
        slot.wait_for_server(timeout=args.wait)
        slot.tune()
        poller = threading.Thread(target=slot.poll_loop, name=f"{slot.name}-poll", daemon=True)
        poller.start()
        slot.poll_once()
        slot.burst()
        if args.auto:
            time.sleep(args.hold)
        else:
            print(f"[{slot.name} READY] type a line to POST, Ctrl-C to quit", flush=True)
            stdin_loop(slot.send_text)
    except KeyboardInterrupt:
        print(flush=True)
    finally:
        slot.close()
        print(f"[{slot.name} CLOSE] peer {fmt_addr(slot.peer)} mailbox={slot.mailbox_id}", flush=True)
    return 0


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.poll <= 0:
        print("--poll must be > 0", file=sys.stderr)
        return 2
    if args.role == "server":
        return run_server(args)
    return run_client(args)


if __name__ == "__main__":
    raise SystemExit(main())
