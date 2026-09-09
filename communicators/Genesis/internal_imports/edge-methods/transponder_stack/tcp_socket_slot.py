#!/usr/bin/env python3
"""TCP connection-slot prototype.

Unlike HTTP, one TCP connection is already duplex. Both processes therefore
share a single host:port. The first process to bind becomes the listener; the
other dials. After the socket exists, both sides send and receive — there is
no extra listen port.

Terminal A:
  python tcp_socket_slot.py --name FOX   --listen 127.0.0.1:9101 --peer 127.0.0.1:9101

Terminal B:
  python tcp_socket_slot.py --name OTTER --listen 127.0.0.1:9101 --peer 127.0.0.1:9101

`--listen` and `--peer` are kept so the CLI matches slot_http.py. For this
slot they must name the same address.

Type a line and press enter to send. Ctrl-C to quit.

Non-interactive proof:
  python tcp_socket_slot.py --name FOX   --listen 127.0.0.1:9101 --peer 127.0.0.1:9101 --auto --hold 4
  python tcp_socket_slot.py --name OTTER --listen 127.0.0.1:9101 --peer 127.0.0.1:9101 --auto --hold 4

Wire framing: one JSON object per line (NDJSON). encode at send, decode at recv.

Capability row (harvest later for L1):
  listen yes | accept yes | connect yes | send yes | recv yes | close yes
  serve yes | request_response yes | send_and_close yes | persistent_client yes
"""

from codec import Codec
from demo import Demo
from locators import Locators


# ---------------------------------------------------------------------------
# Slot
# ---------------------------------------------------------------------------

class TcpSlot:
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

    def addr_s(self) -> str:
        return f"tcp://{self.host}:{self.port}"

    def next_seq(self) -> int:
        with self.seq_lock:
            self.seq += 1
            return self.seq

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

    def wait_for_peer(self, timeout: float = 20.0) -> None:
        # attach() already blocks until the duplex socket exists
        if self.conn is None:
            self.attach(timeout)
        print(f"[{self.name} PEER UP] role={self.role} addr={self.addr_s()}", flush=True)

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
                        incoming = Codec.decode_msg(raw)
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
        data = Codec.encode_bytes(payload, newline=True)
        with self.send_lock:
            self.conn.sendall(data)

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
        for line in Demo.silly_for(self.name):
            try:
                self.send_text(line)
            except Exception as e:
                print(f"[{self.name} SEND FAIL] {type(e).__name__}: {e}", flush=True)
            time.sleep(0.15)

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
