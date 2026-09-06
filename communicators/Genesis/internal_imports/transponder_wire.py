# L2 spine — scheme-blind connection verbs.
# Slots implement the same names. L2 never branches on medium.
# L3 / core.py-style to_N is not here. Endpoints are not spawned here.
#
# Presence (serve) is a boot duty. Connect is on-demand attachment to a name
# that is already bound. Host/port at the public surface is a wire id.

class transponder_wire:

    # ------------------------------------------------------------------
    # Terms
    # ------------------------------------------------------------------

    @internalmethod
    def _localhost(host):
        if host in (None, "", "localhost"):
            return "127.0.0.1"
        return host

    @internalmethod
    def parse_addr(addr):
        """
        Wire id → dict.
        Accepts:
          "http://localhost:8765"
          "localhost:8765"             (scheme defaults to http)
          ("http", "localhost", 8765)
          {"scheme","host","port","path"}
        """
        if isinstance(addr, dict):
            scheme = addr.get("scheme") or "http"
            host = _localhost(addr.get("host") or "127.0.0.1")
            port = int(addr.get("port") or 8765)
            path = addr.get("path") or "/"
            return {"scheme": scheme, "host": host, "port": port, "path": path}

        if isinstance(addr, (tuple, list)):
            if len(addr) == 2:
                host, port = addr
                scheme, path = "http", "/"
            elif len(addr) >= 3:
                scheme, host, port = addr[0], addr[1], addr[2]
                path = addr[3] if len(addr) > 3 else "/"
            else:
                raise ValueError(f"bad addr tuple: {addr!r}")
            return {
                "scheme": scheme,
                "host": _localhost(host),
                "port": int(port),
                "path": path or "/",
            }

        if isinstance(addr, str):
            raw = addr.strip()
            scheme = "http"
            path = "/"
            if "://" in raw:
                scheme, raw = raw.split("://", 1)
            if "/" in raw:
                raw, rest = raw.split("/", 1)
                path = "/" + rest
            if ":" in raw:
                host, port_s = raw.rsplit(":", 1)
                port = int(port_s)
            else:
                host, port = raw, 8765
            return {
                "scheme": scheme,
                "host": _localhost(host),
                "port": port,
                "path": path,
            }

        raise TypeError(f"unsupported addr: {type(addr)!r}")

    @internalmethod
    def wire_id(addr):
        a = parse_addr(addr) if not isinstance(addr, dict) or "scheme" not in addr else addr
        return f"{a['scheme']}://{a['host']}:{a['port']}{a['path']}"

    @internalmethod
    def encode_msg(payload):
        if payload is None:
            return ""
        if isinstance(payload, (bytes, bytearray)):
            return payload.decode("utf-8")
        if isinstance(payload, str):
            return payload
        return json.dumps(payload, ensure_ascii=False)

    @internalmethod
    def decode_msg(text):
        if text is None or text == "":
            return None
        if not isinstance(text, str):
            text = text.decode("utf-8") if isinstance(text, (bytes, bytearray)) else str(text)
        try:
            return json.loads(text)
        except Exception:
            return text

    # ------------------------------------------------------------------
    # Table A — capability matrix (law, not dispatch)
    # yes / no / later. Registration refuses a column that claims yes
    # without implementing the verb.
    # ------------------------------------------------------------------

    CAPABILITY = {
        "http": {
            "listen": "yes",
            "accept": "yes",
            "connect": "yes",
            "send": "yes",
            "recv": "yes",
            "close": "yes",
            "serve": "yes",
            "request_response": "yes",
            "send_and_close": "yes",
            "persistent_client": "later",
        },
        "tcp": {
            "listen": "yes",
            "accept": "yes",
            "connect": "yes",
            "send": "yes",
            "recv": "yes",
            "close": "yes",
            "serve": "yes",
            "request_response": "yes",
            "send_and_close": "yes",
            "persistent_client": "later",
        },
        "unix": {"serve": "later", "request_response": "later"},
        "ws": {"serve": "later", "request_response": "later"},
        "shm": {"serve": "later", "request_response": "later"},
        "beacon": {"serve": "no", "request_response": "no"},
    }

    # ------------------------------------------------------------------
    # Table B — chooser (the only scheme-conditional tree)
    # ------------------------------------------------------------------

    @internalmethod
    def legal_slots(addr):
        a = parse_addr(addr)
        scheme = a["scheme"]
        host = a["host"]
        if scheme in ("unix", "shm"):
            return frozenset({scheme})
        if scheme == "beacon":
            return frozenset({"beacon"})
        if host in ("127.0.0.1", "::1"):
            return frozenset({"http", "tcp", "unix", "shm", "ws"})
        # private LAN rough cut
        if host.startswith(("10.", "192.168.", "172.")):
            return frozenset({"http", "tcp", "ws"})
        return frozenset({"http", "ws"})

    @internalmethod
    def choose_scheme(addr):
        a = parse_addr(addr)
        asked = a["scheme"]
        legal = legal_slots(a)
        registered = set(SLOTS)
        if asked in legal and asked in registered:
            return asked
        # prefer http when the caller omitted a real preference
        for candidate in ("http", "tcp", "unix", "ws", "shm"):
            if candidate in legal and candidate in registered:
                return candidate
        raise RuntimeError(
            f"no registered slot for {wire_id(a)}; "
            f"legal={sorted(legal)} registered={sorted(registered)}"
        )

    @internalmethod
    def resolve(addr):
        a = parse_addr(addr)
        scheme = choose_scheme(a)
        slot = SLOTS.get(scheme)
        if slot is None:
            raise RuntimeError(f"slot {scheme!r} is not registered")
        cap = CAPABILITY.get(scheme, {})
        return a, scheme, slot, cap

    @internalmethod
    def require(cap, verb):
        flag = cap.get(verb, "no")
        if flag != "yes":
            raise RuntimeError(f"verb {verb!r} is {flag!r} on this slot")

    # ------------------------------------------------------------------
    # Session table — local attachment to a wire id. Not a peer process.
    # ------------------------------------------------------------------

    _sessions = {}

    @internalmethod
    def _session_get(addr, role="negative"):
        a = parse_addr(addr)
        key = wire_id(a)
        sess = _sessions.get(key)
        if sess is None:
            sess = {
                "id": key,
                "addr": a,
                "role": role,
                "scheme": a["scheme"],
                "handle": None,
                "alive": False,
                "mode": "oneshot",
                "last_reply": None,
            }
            _sessions[key] = sess
        return sess

    # ------------------------------------------------------------------
    # HTTP column — first real slot. Framing = HTTP body.
    # ------------------------------------------------------------------

    @internalmethod
    def _http_serve(addr, handler):
        a = parse_addr(addr)
        host, port = a["host"], a["port"]

        class _Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):
                try:
                    manifest.info("http", self.address_string(), fmt % args)
                except Exception:
                    print(fmt % args)

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(n).decode("utf-8") if n else ""
                incoming = decode_msg(raw)
                try:
                    outgoing = handler(incoming) if handler else incoming
                except Exception as e:
                    body = encode_msg({"ok": False, "error": type(e).__name__, "message": str(e)})
                    data = body.encode("utf-8")
                    self.send_response(500)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return
                body = encode_msg(outgoing)
                data = body.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                body = encode_msg({"ok": True, "wire": wire_id(a)})
                data = body.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        httpd = HTTPServer((host, port), _Handler)
        sess = _session_get(a, role="positive")
        sess["alive"] = True
        sess["handle"] = httpd
        sess["mode"] = "oneshot"
        try:
            manifest.info("Transponder HTTP listen", wire_id(a))
        except Exception:
            print(f"Transponder HTTP listen {wire_id(a)}")
        httpd.serve_forever()

    @internalmethod
    def _http_request_response(addr, payload):
        a = parse_addr(addr)
        url = f"http://{a['host']}:{a['port']}{a['path']}"
        body = encode_msg(payload)
        # requests is in prefix Tier 0
        r = requests.post(url, data=body.encode("utf-8"), headers={"Content-Type": "application/json; charset=utf-8"}, timeout=10)
        r.raise_for_status()
        reply = decode_msg(r.text)
        sess = _session_get(a, role="negative")
        sess["alive"] = False
        sess["mode"] = "oneshot"
        sess["last_reply"] = reply
        return reply

    @internalmethod
    def _http_send_and_close(addr, payload):
        _http_request_response(addr, payload)

    # ------------------------------------------------------------------
    # TCP column — parked original stub, framed by newline.
    # Not the default. Kept so old experiments have a home.
    # ------------------------------------------------------------------

    @internalmethod
    def _tcp_listen(addr):
        a = parse_addr(addr)
        l = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        l.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        l.bind((a["host"], a["port"]))
        l.listen(5)
        return l

    @internalmethod
    def _tcp_connect(addr):
        a = parse_addr(addr)
        conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        conn.connect((a["host"], a["port"]))
        return conn

    @internalmethod
    def _tcp_serve(addr, handler):
        listener = _tcp_listen(addr)
        try:
            manifest.info("Transponder TCP listen", wire_id(addr))
        except Exception:
            print(f"Transponder TCP listen {wire_id(addr)}")
        while True:
            conn, _peer = listener.accept()
            try:
                buf = b""
                while True:
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    buf += chunk
                    if buf.endswith(b"\n"):
                        break
                incoming = decode_msg(buf.decode("utf-8").rstrip("\n"))
                outgoing = handler(incoming) if handler else incoming
                conn.sendall((encode_msg(outgoing) + "\n").encode("utf-8"))
            except Exception as e:
                try:
                    manifest.error(f"TCP session error: {e}")
                except Exception:
                    print(e)
            finally:
                conn.close()

    @internalmethod
    def _tcp_request_response(addr, payload):
        conn = _tcp_connect(addr)
        try:
            conn.sendall((encode_msg(payload) + "\n").encode("utf-8"))
            buf = b""
            while True:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                buf += chunk
                if buf.endswith(b"\n"):
                    break
            return decode_msg(buf.decode("utf-8").rstrip("\n"))
        finally:
            conn.close()

    @internalmethod
    def _tcp_send_and_close(addr, payload):
        conn = _tcp_connect(addr)
        try:
            conn.sendall((encode_msg(payload) + "\n").encode("utf-8"))
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Registry — scheme → slot object with L2 verb names.
    # Pointers later; embedded callables now.
    # ------------------------------------------------------------------

    class _Slot:
        def __init__(self, scheme, serve, request_response, send_and_close):
            self.scheme = scheme
            self.serve = serve
            self.request_response = request_response
            self.send_and_close = send_and_close

    # filled after methods exist; see _boot_registry

    @internalmethod
    def _boot_registry():
        return {
            "http": _Slot("http", _http_serve, _http_request_response, _http_send_and_close),
            "tcp": _Slot("tcp", _tcp_serve, _tcp_request_response, _tcp_send_and_close),
        }

    SLOTS = None  # replaced on first resolve

    @internalmethod
    def _slots():
        global SLOTS
        if SLOTS is None:
            SLOTS = _boot_registry()
        return SLOTS

    # ------------------------------------------------------------------
    # L2 verbs — one line of dispatch each. No if-http here.
    # ------------------------------------------------------------------

    @externalmethod
    def serve(addr, handler=None):
        """Positive attach. Blocks. Does not launch another program."""
        global SLOTS
        if SLOTS is None:
            SLOTS = _boot_registry()
        a, scheme, slot, cap = resolve(addr)
        require(cap, "serve")
        if handler is None:
            def handler(msg):
                return {"echo": msg}
        return slot.serve(a, handler)

    @externalmethod
    def persistent_server(host, port, handler=None, scheme="http"):
        """Back-compat name. host/port are the wire id."""
        return serve({"scheme": scheme, "host": host, "port": port}, handler)

    @externalmethod
    def request_response(addr, payload=None):
        """Negative oneshot. Connects to an already-bound name. Does not spawn it."""
        global SLOTS
        if SLOTS is None:
            SLOTS = _boot_registry()
        a, scheme, slot, cap = resolve(addr)
        require(cap, "request_response")
        return slot.request_response(a, payload)

    @externalmethod
    def send_and_close(addr, payload=None):
        global SLOTS
        if SLOTS is None:
            SLOTS = _boot_registry()
        a, scheme, slot, cap = resolve(addr)
        require(cap, "send_and_close")
        return slot.send_and_close(a, payload)
