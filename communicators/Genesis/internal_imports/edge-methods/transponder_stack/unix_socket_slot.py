#!/usr/bin/env python3
"""Unix-socket connection-slot prototype.

Like TCP and WebSocket, AF_UNIX SOCK_STREAM is duplex. Both processes share
one filesystem path. The first process to bind becomes the listener; the
other dials. After the socket exists, both sides send and receive.

Terminal A:
  python unix_socket_slot.py --name FOX   --listen /tmp/slot_unix.sock --peer /tmp/slot_unix.sock

Terminal B:
  python unix_socket_slot.py --name OTTER --listen /tmp/slot_unix.sock --peer /tmp/slot_unix.sock

`--listen` and `--peer` stay so the CLI matches the other slots. For this
slot they must name the same path. A host:port string is accepted and mapped
to /tmp/unix_slot_<host>_<port>.sock so you can reuse the TCP invocation.

Type a line and press enter to send. Ctrl-C to quit.

Non-interactive proof:
  python unix_socket_slot.py --name FOX   --listen /tmp/slot_unix.sock --peer /tmp/slot_unix.sock --auto --hold 4
  python unix_socket_slot.py --name OTTER --listen /tmp/slot_unix.sock --peer /tmp/slot_unix.sock --auto --hold 4

Wire framing: one JSON object per line (NDJSON), same as TCP.
encode at send, decode at recv.

Capability row (harvest later for L1):
  listen yes | accept yes | connect yes | send yes | recv yes | close yes
  serve yes | request_response yes | send_and_close yes | persistent_client yes
"""


# ---------------------------------------------------------------------------
# Slot
# ---------------------------------------------------------------------------

class UnixSlot:
    @internalmethod
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

    @internalmethod
    def _open(self, name: str, path: str):
        _close()
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

    @externalmethod
    def open(name: str, path: str):
        return _open(name, path)

    @internalmethod
    def _set_on_payload(self, cb):
        self.on_payload = cb

    @externalmethod
    def set_on_payload(cb):
        return _set_on_payload(cb)

    @internalmethod
    def _is_sock_file(self, path: str) -> bool:
        try:
            return stat.S_ISSOCK(os.stat(path).st_mode)
        except FileNotFoundError:
            return False
        except OSError:
            return False

    @internalmethod
    def _unlink_if_stale(self, path: str) -> bool:
        """Remove a leftover socket file that nothing is accepting on."""
        if not _is_sock_file(path):
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

    @internalmethod
    def _addr_s(self) -> str:
        return f"unix://{self.path}"

    @externalmethod
    def addr_s() -> str:
        return _addr_s()

    @internalmethod
    def _next_seq(self) -> int:
        with self.seq_lock:
            self.seq += 1
            return self.seq

    @externalmethod
    def next_seq() -> int:
        return _next_seq()

    @internalmethod
    def _bind_listen(self) -> socket.socket:
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(self.path)
        listener.listen(1)
        listener.settimeout(0.3)
        self.owns_path = True
        return listener

    @internalmethod
    def _connect(self, timeout: float) -> socket.socket:
        conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        conn.settimeout(timeout)
        conn.connect(self.path)
        conn.settimeout(None)
        return conn

    @internalmethod
    def _attach(self, wait: float) -> None:
        deadline = time.time() + wait
        last_err = None
        parent = os.path.dirname(self.path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        while time.time() < deadline:
            try:
                self.listener = _bind_listen()
                self.role = "listen"
                print(f"[{self.name} LISTEN] {_addr_s()}  (waiting for peer)", flush=True)
                while time.time() < deadline:
                    try:
                        conn, _peer = self.listener.accept()
                        self.conn = conn
                        print(f"[{self.name} ACCEPT] path={self.path}", flush=True)
                        _start_recv()
                        return
                    except socket.timeout:
                        continue
                raise TimeoutError(f"{self.name} bound {_addr_s()} but nobody connected")
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
                    self.conn = _connect(timeout=0.4)
                    self.role = "connect"
                    print(f"[{self.name} CONNECT] {_addr_s()}", flush=True)
                    _start_recv()
                    return
                except ConnectionRefusedError as e2:
                    last_err = e2
                    if _unlink_if_stale(self.path):
                        print(f"[{self.name} STALE] removed leftover {self.path}", flush=True)
                    time.sleep(0.15)
                except OSError as e2:
                    last_err = e2
                    time.sleep(0.15)
        raise TimeoutError(f"{self.name} never attached to {_addr_s()}: {last_err}")

    @externalmethod
    def attach(wait: float) -> None:
        return _attach(wait)

    @internalmethod
    def _wait_for_peer(self, timeout: float = 20.0) -> None:
        if self.conn is None:
            _attach(timeout)
        print(f"[{self.name} PEER UP] role={self.role} addr={_addr_s()}", flush=True)

    @externalmethod
    def wait_for_peer(timeout: float = 20.0) -> None:
        return _wait_for_peer(timeout)

    @internalmethod
    def _start_recv(self) -> None:
        self.alive.set()
        self.recv_thread = threading.Thread(target=_recv_loop, name=f"{self.name}-recv", daemon=True)
        self.recv_thread.start()

    @internalmethod
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
                    _handle_incoming(incoming)
        finally:
            self.alive.clear()

    @internalmethod
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
                _write({
                    "ok": True,
                    "kind": "reply",
                    "heard_by": self.name,
                    "from": origin,
                    "seq": seq,
                    "text": text,
                })
            except OSError as e:
                print(f"[{self.name} REPLY FAIL] {e}", flush=True)

    @internalmethod
    def _write(self, payload: dict) -> None:
        data = Transponder_Codec.encode_bytes(payload, newline=True)
        with self.send_lock:
            self.conn.sendall(data)

    @externalmethod
    def write(payload: dict) -> None:
        return _write(payload)

    @internalmethod
    def _request_response(self, payload: dict, timeout: float = 5.0) -> dict:
        seq = payload.get("seq")
        ev = threading.Event()
        with self.inbox_lock:
            self.reply_events[seq] = ev
        try:
            _write(payload)
            if not ev.wait(timeout):
                raise TimeoutError(f"no reply for seq={seq}")
            with self.inbox_lock:
                return self.replies.get(seq, {})
        finally:
            with self.inbox_lock:
                self.reply_events.pop(seq, None)

    @externalmethod
    def request_response(payload: dict, timeout: float = 5.0) -> dict:
        return _request_response(payload, timeout)

    @internalmethod
    def _send_text(self, text: str) -> dict:
        payload = {
            "from": self.name,
            "seq": _next_seq(),
            "kind": "chat",
            "text": text,
            "ts": time.time(),
        }
        print(f"[{self.name} SEND] seq={payload['seq']} text={text!r}", flush=True)
        reply = _request_response(payload)
        print(f"[{self.name} REPLY] {reply}", flush=True)
        return reply

    @externalmethod
    def send_text(text: str) -> dict:
        return _send_text(text)

    @externalmethod
    def burst() -> None:
        pass

    @internalmethod
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

    @externalmethod
    def close() -> None:
        return _close()
