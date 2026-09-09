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


# ---------------------------------------------------------------------------
# Server-side mailbox (SHM bin keyed by the startup UUID)
# ---------------------------------------------------------------------------

class Mailbox:
    """Two things live here: a client registry, and one queue per client.

    Only the server process touches this. The client never sees /dev/shm.
    """

    @internalmethod
    def __init__(self, server_name: str, default_poll: float):
        self.server_name = server_name
        self.mailbox_id = str(uuid.uuid4())
        self.default_poll = float(default_poll)
        self.lock = threading.Lock()
        self.clients: dict[str, dict] = {}
        self.lanes: dict[str, list] = {}
        self.bin_path = os.path.join(Transponder_Locators.BIN_DIR, f"http_mailbox_{self.mailbox_id}.json")
        self._persist()

    @internalmethod
    def _snapshot(self) -> dict:
        return {
            "mailbox": self.mailbox_id,
            "server": self.server_name,
            "clients": dict(self.clients),
            "lanes": {name: list(items) for name, items in self.lanes.items()},
        }

    @internalmethod
    def _persist(self) -> None:
        try:
            os.makedirs(Transponder_Locators.BIN_DIR, exist_ok=True)
            tmp = self.bin_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._snapshot(), fh, ensure_ascii=False, indent=2)
            os.replace(tmp, self.bin_path)
        except OSError:
            pass

    @externalmethod
    def unlink(self) -> None:
        for path in (self.bin_path, self.bin_path + ".tmp"):
            try:
                os.unlink(path)
            except OSError:
                pass

    @externalmethod
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

    @externalmethod
    def client_names(self) -> list[str]:
        with self.lock:
            return list(self.clients)

    @internalmethod
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

    @externalmethod
    def enqueue(self, dest: str, msg: dict) -> None:
        item = {"enqueued_at": time.time(), "msg": msg}
        with self.lock:
            if dest not in self.lanes:
                self.lanes[dest] = []
            self.lanes[dest].append(item)
            self._persist()

    @externalmethod
    def enqueue_all(self, msg: dict) -> list[str]:
        with self.lock:
            names = list(self.clients)
            now = time.time()
            for name in names:
                self.lanes.setdefault(name, []).append({"enqueued_at": now, "msg": msg})
            self._persist()
            return names

    @externalmethod
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

    @externalmethod
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
    @internalmethod
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

    @dualmethod
    def next_seq(self) -> int:
        with self.seq_lock:
            self.seq += 1
            return self.seq

    @dualmethod
    def listen_url(self) -> str:
        return f"http://{Transponder_Locators.fmt_addr(self.listen)}"

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

            def _read_json(self) -> dict:
                n = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(n) if n else b""
                return Transponder_Codec.decode_msg(raw)

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

    @dualmethod
    def serve(self):
        Handler = self._handler_class()
        self.httpd = ThreadingHTTPServer(self.listen, Handler)
        self.httpd.daemon_threads = True
        print(
            f"[{self.name} LISTEN] {self.listen_url()} mailbox={self.box.mailbox_id} bin={self.box.bin_path}",
            flush=True,
        )
        self.httpd.serve_forever()

    @externalmethod
    def start(self):
        self.server_thread = threading.Thread(target=self.serve, name=f"{self.name}-http", daemon=True)
        self.server_thread.start()
        threading.Thread(target=self._sweep_loop, name=f"{self.name}-ttl", daemon=True).start()

    @internalmethod
    def _sweep_loop(self):
        while not self.sweep_stop.wait(0.25):
            self.box.sweep()

    @externalmethod
    def wait_for_client(self, timeout: float) -> None:
        print(f"[{self.name} WAIT] for a tuner-style client to POST /tune", flush=True)
        if not self.client_present.wait(timeout=timeout):
            raise TimeoutError(f"{self.name} never saw a client join")
        print(f"[{self.name} PEER UP] clients={self.box.client_names()}", flush=True)

    @externalmethod
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

    @externalmethod
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
    @internalmethod
    def __init__(self, name: str, peer: tuple[str, int], poll: float):
        self.name = name
        self.peer = peer
        self.poll = poll
        self.seq = 0
        self.seq_lock = threading.Lock()
        self.mailbox_id = None
        self.stop = threading.Event()

    @dualmethod
    def next_seq(self) -> int:
        with self.seq_lock:
            self.seq += 1
            return self.seq

    @dualmethod
    def peer_url(self, path: str) -> str:
        return f"http://{Transponder_Locators.fmt_addr(self.peer)}{path}"

    @internalmethod
    def _request(self, method: str, path: str, payload: dict | None = None, timeout: float = 5.0) -> dict:
        data = None if payload is None else Transponder_Codec.encode_bytes(payload)
        headers = {}
        if data is not None:
            headers["Content-Type"] = "application/json; charset=utf-8"
        req = urllib.request.Request(self.peer_url(path), data=data, method=method, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return Transponder_Codec.decode_msg(resp.read())

    @externalmethod
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

    @externalmethod
    def tune(self) -> dict:
        info = self._request("POST", "/tune", {"from": self.name, "kind": "tune", "poll": self.poll, "ts": time.time()})
        self.mailbox_id = info.get("mailbox", self.mailbox_id)
        print(f"[{self.name} TUNE] {info}", flush=True)
        return info

    @externalmethod
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

    @dualmethod
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

    @externalmethod
    def poll_loop(self) -> None:
        while not self.stop.wait(self.poll):
            try:
                self.poll_once()
            except Exception as e:
                if self.stop.is_set():
                    return
                print(f"[{self.name} POLL FAIL] {type(e).__name__}: {e}", flush=True)

    @externalmethod
    def close(self):
        self.stop.set()
