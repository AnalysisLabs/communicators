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


# ---------------------------------------------------------------------------
# Slot
# ---------------------------------------------------------------------------

class WsSlot:
    @internalmethod
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

    @internalmethod
    def _open(self, name: str, addr: tuple[str, int]):
        _close()
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

    @externalmethod
    def open(name: str, addr: tuple[str, int]):
        return _open(name, addr)

    @internalmethod
    def _set_on_payload(self, cb):
        self.on_payload = cb

    @externalmethod
    def set_on_payload(cb):
        return _set_on_payload(cb)

    @internalmethod
    def _addr_s(self) -> str:
        return f"ws://{self.host}:{self.port}"

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
    def _server_handler(self, websocket):
        self.ws = websocket
        self.role = self.role or "listen"
        self.alive.set()
        self.attached.set()
        print(f"[{self.name} ACCEPT] {_addr_s()}", flush=True)
        try:
            for raw in websocket:
                try:
                    incoming = Transponder_Codec.decode_msg(raw)
                except Exception as e:
                    print(f"[{self.name} BAD JSON] {e}: {raw!r}", flush=True)
                    continue
                _handle_incoming(incoming)
        finally:
            print(f"[{self.name} PEER CLOSED]", flush=True)
            self.alive.clear()

    @internalmethod
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
                _handle_incoming(incoming)
        except Exception as e:
            if self.alive.is_set():
                print(f"[{self.name} RECV END] {type(e).__name__}: {e}", flush=True)
        finally:
            print(f"[{self.name} PEER CLOSED]", flush=True)
            self.alive.clear()

    @internalmethod
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
                print(f"[{self.name} LISTEN] {_addr_s()}  (waiting for peer)", flush=True)
                if not self.attached.wait(timeout=max(0.05, deadline - time.time())):
                    raise TimeoutError(f"{self.name} bound {_addr_s()} but nobody connected")
                return
            except OSError as e:
                last_err = e
                _stop_server()
                try:
                    self.ws = connect(_addr_s(), open_timeout=0.4)
                    self.role = "connect"
                    self.alive.set()
                    self.attached.set()
                    self.recv_thread = threading.Thread(
                        target=_recv_loop,
                        name=f"{self.name}-wsrecv",
                        daemon=True,
                    )
                    self.recv_thread.start()
                    print(f"[{self.name} CONNECT] {_addr_s()}", flush=True)
                    return
                except Exception as e2:
                    last_err = e2
                    time.sleep(0.15)
        raise TimeoutError(f"{self.name} never attached to {_addr_s()}: {last_err}")

    @externalmethod
    def attach(wait: float) -> None:
        return _attach(wait)

    @internalmethod
    def _wait_for_peer(self, timeout: float = 20.0) -> None:
        if not self.attached.is_set():
            _attach(timeout)
        print(f"[{self.name} PEER UP] role={self.role} addr={_addr_s()}", flush=True)

    @externalmethod
    def wait_for_peer(timeout: float = 20.0) -> None:
        return _wait_for_peer(timeout)

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
            except Exception as e:
                print(f"[{self.name} REPLY FAIL] {e}", flush=True)

    @internalmethod
    def _write(self, payload: dict) -> None:
        data = Transponder_Codec.encode_msg(payload)
        with self.send_lock:
            self.ws.send(data)

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

    @internalmethod
    def _close(self) -> None:
        self.alive.clear()
        if self.ws is not None:
            try:
                self.ws.close()
            except Exception:
                pass
            self.ws = None
        _stop_server()

    @externalmethod
    def close() -> None:
        return _close()
