#!/usr/bin/env python3
"""HTTP connection-slot prototype.

Each process is BOTH a server (positive / listen) and a client (negative / peer).
Messages are JSON objects on the wire. Encode at send, decode at recv.

Terminal A:
  python http_slot.py.py --name FOX --listen 127.0.0.1:9101 --peer 127.0.0.1:9102

Terminal B:
  python http_slot.py.py --name OTTER --listen 127.0.0.1:9102 --peer 127.0.0.1:9101

Type a line and press enter to send. Ctrl-C to quit.

Non-interactive proof (used by the sandbox test):
  python http_slot.py.py --name FOX --listen 127.0.0.1:9101 --peer 127.0.0.1:9102 --auto --hold 4

Capability row (harvest later for L1):
  listen yes | accept yes | connect yes | send yes | recv yes | close yes
  serve yes | request_response yes | send_and_close yes | persistent_client later
"""


# ---------------------------------------------------------------------------
# Slot
# ---------------------------------------------------------------------------

class HttpSlot:
    @internalmethod
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

    @dualmethod
    def next_seq(self) -> int:
        with self.seq_lock:
            self.seq += 1
            return self.seq

    @dualmethod
    def peer_url(self, path: str = "/msg") -> str:
        return f"http://{self.peer_host}:{self.peer_port}{path}"

    @dualmethod
    def listen_url(self) -> str:
        return f"http://{self.listen_host}:{self.listen_port}"

    # -- server (positive) ---------------------------------------------------

    @internalmethod
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

    @dualmethod
    def serve(self):
        Handler = self._handler_class()
        self.httpd = ThreadingHTTPServer((self.listen_host, self.listen_port), Handler)
        self.httpd.daemon_threads = True
        print(
            f"[{self.name} LISTEN] {self.listen_url()}  -> peer {self.peer_host}:{self.peer_port}",
            flush=True,
        )
        self.httpd.serve_forever()

    @externalmethod
    def start_server_thread(self):
        self.server_thread = threading.Thread(target=self.serve, name=f"{self.name}-http", daemon=True)
        self.server_thread.start()

    @externalmethod
    def close(self):
        if self.httpd is not None:
            self.httpd.shutdown()
            self.httpd.server_close()

    # -- client (negative) ---------------------------------------------------

    @dualmethod
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

    @externalmethod
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

    @dualmethod
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

    @externalmethod
    def burst(self) -> None:
        pass
