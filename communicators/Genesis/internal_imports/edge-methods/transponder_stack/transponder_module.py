
"""
negative == initiates websocket
positive == recieves and remembers websocket(s)
down == from middleware to communicator
up == from communicator to middleware
"""

class NegativeCom:
    # Clarification: Only NegativeCom has permission to initiate websocket connections.

    @internalmethod
    def __init__(self):
        self.config = {}
        self.echo_payload = None
        self.negative = self
        self.lock = threading.Lock()
        self.socket_path = None
        self.ws = None
        self.wire = None
        self.up_queue = deque()
        self.down_queue = deque()
        self._busy_down = False
        self._busy_up = False
        self.echo_seen = set()
        self._pump_started = False
        self._pump_alive = False

    @internalmethod
    def _attach_wire(self, wire):
        self.wire = wire
        self.ws = wire
        _start_up_pump()
        return wire

    @externalmethod
    def attach_wire(wire):
        return _attach_wire(wire)

    @internalmethod
    def _start_up_pump(self):
        if self._pump_started:
            return
        self._pump_started = True
        self._pump_alive = True

        def pump():
            while self._pump_alive:
                if self.up_queue and not self._busy_up:
                    _process_up_queue()
                time.sleep(0.05)

        threading.Thread(target=pump, name="neg-up-pump", daemon=True).start()

    @internalmethod
    def _process_down_queue(self):
        with self.lock:
            manifest.info("This was triggered.")
            if self._busy_down:
                return
            for item in list(self.down_queue):
                self._busy_down = True
                if self.down_queue[0]:
                    _sender(self.ws, self.down_queue[0])
                    token = self.down_queue[0]['communicator_token']
                    _wait_for_echo(token)
                    self.down_queue.popleft()
                    self._busy_down = False

    @externalmethod
    def process_down_queue():
        return _process_down_queue()

    @internalmethod
    def _sender(self, ws, payload):
        body = payload if isinstance(payload, dict) else payload
        if self.wire is None:
            raise RuntimeError("NegativeCom.sender has no Wire attached")
        self.wire.send(body)
        if isinstance(body, dict) and "received" in body:
            self.echo_seen.add(body["received"])

    @externalmethod
    def sender(ws, payload):
        return _sender(ws, payload)

    @internalmethod
    def _receiver(self, ws, message=None):
        if message:
            manifest.info(f'Message received: {message}')
            data = message if isinstance(message, dict) else {"message": message}
            if "received" in data:
                self.echo_seen.add(data["received"])
                return
            self.up_queue.append(data)
            manifest.info('Message appended to up_queue')

    @externalmethod
    def receiver(ws, message=None):
        return _receiver(ws, message)

    @internalmethod
    def _process_up_queue(self):
        if self._busy_up:
            return
        manifest.info('Processing up_queue')
        for item in list(self.up_queue):
            self._busy_up = True
            if self.up_queue[0]:
                _from_N(self.up_queue[0])
                token = self.up_queue[0].get('communicator_token') if isinstance(self.up_queue[0], dict) else None
                _wait_for_echo(token)
                self.up_queue.popleft()
        manifest.info('up_queue processed')
        self._busy_up = False

    @externalmethod
    def process_up_queue():
        return _process_up_queue()

    @internalmethod
    def _wait_for_echo(self, token):
        while True:
            time.sleep(0.1)
            if token in self.echo_seen:
                return
            for msg in list(self.up_queue):
                if isinstance(msg, dict) and msg.get('received') == token:
                    self.up_queue.remove(msg)
                    return

    @externalmethod
    def wait_for_echo(token):
        return _wait_for_echo(token)

    @internalmethod
    def _echo(self, payload=None):
        if payload is None:
            payload = self.echo_payload
        token = payload.get('communicator_token') if isinstance(payload, dict) else None
        if token and self.ws:
            echo_payload = {'received': token}
            _sender(self.ws, echo_payload)

    @externalmethod
    def echo(payload=None):
        return _echo(payload)

    @internalmethod
    def _from_N(self, payload):
        manifest.info(payload)
        token = payload.get('communicator_token') if isinstance(payload, dict) else None
        if token and self.ws:
            echo_payload = {'received': token}
            if payload.get('echo') == 'delay':
                time.sleep(0.1)
            else:
                _sender(self.ws, echo_payload)

    @externalmethod
    def from_N(payload):
        return _from_N(payload)

    @internalmethod
    def _to_N(self, payload):
        manifest.info(payload)
        self.down_queue.append(payload)
        _process_down_queue()

    @externalmethod
    def to_N(payload):
        return _to_N(payload)

class PositiveCom:
    # Clarification: PositiveCom only has permission to receive and maintain websocket connections.

    @internalmethod
    def __init__(self):
        self.config = {}
        self.echo_payload = None
        self.positive = self
        self.socket_path = None
        self.ws = None
        self.wire = None
        self.positive_addr = {}
        self.port = 0
        self.connections = {}
        self.ws_token_dict = {}
        self.ws_id = None
        self.up_queue = deque()
        self.down_queue = deque()
        self._busy_down = False
        self._busy_up = False
        self.echo_seen = set()
        self._pump_started = False
        self._pump_alive = False

    @internalmethod
    def _attach_wire(self, wire):
        self.wire = wire
        self.ws = wire
        self.connections[id(wire)] = wire
        if not self._pump_started:
            self._pump_started = True
            self._pump_alive = True

            def pump():
                while self._pump_alive:
                    if self.up_queue and not self._busy_up:
                        _process_up_queue()
                    time.sleep(0.05)

            threading.Thread(target=pump, name="pos-up-pump", daemon=True).start()
        return wire

    @externalmethod
    def attach_wire(wire):
        return _attach_wire(wire)

    @internalmethod
    def _find_pids_on_port(self, port: int) -> set:
        if shutil.which("lsof"):
            try:
                result = subprocess.run(
                    ["lsof", "-ti", f"tcp:{port}"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
            except FileNotFoundError:
                pass
            else:
                return {int(pid) for pid in result.stdout.split() if pid.strip()}
        return set()

    @internalmethod
    def _preemptive_port_cleanup(self, port: int) -> None:
        if port <= 0:
            return
        pids = _find_pids_on_port(port)
        for pid in sorted(pids):
            if pid == os.getpid():
                continue
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                continue
            time.sleep(0.1)

    @internalmethod
    def _process_down_queue(self):
        if self._busy_down:
            return
        for item in list(self.down_queue):
            self._busy_down = True
            if self.down_queue[0]:
                payload = self.down_queue[0]
                token = payload.get('communicator_token') if isinstance(payload, dict) else None
                if token and token in self.ws_token_dict:
                    ws_id = self.ws_token_dict[token]
                    if ws_id in self.connections:
                        _sender(self.connections[ws_id], self.down_queue[0])
                        _wait_for_echo(token)
                        self.down_queue.popleft()
        self._busy_down = False

    @externalmethod
    def process_down_queue():
        return _process_down_queue()

    @internalmethod
    def _wait_for_echo(self, token):
        while True:
            time.sleep(0.1)
            if token in self.echo_seen:
                return
            for msg in list(self.up_queue):
                if isinstance(msg, dict) and msg.get('received') == token:
                    self.up_queue.remove(msg)
                    return

    @externalmethod
    def wait_for_echo(token):
        return _wait_for_echo(token)

    @internalmethod
    def _process_up_queue(self):
        if self._busy_up:
            return
        for item in list(self.up_queue):
            self._busy_up = True
            if self.up_queue[0]:
                _from_P(self.up_queue[0])
                token = self.up_queue[0].get('communicator_token') if isinstance(self.up_queue[0], dict) else None
                _wait_for_echo(token)
                self.up_queue.popleft()
        self._busy_up = False

    @externalmethod
    def process_up_queue():
        return _process_up_queue()

    @internalmethod
    def _receiver(self, ws, message=None):
        if message:
            data = message if isinstance(message, dict) else {"message": message}
            token = data.get('communicator_token') if isinstance(data, dict) else None
            handle = ws if ws is not None else self.wire
            if token and handle is not None:
                self.ws_token_dict[token] = id(handle)
                self.connections[id(handle)] = handle
            if "received" in data:
                self.echo_seen.add(data["received"])
                return
            self.up_queue.append(data)
            manifest.info('Message appended to up_queue')

    @externalmethod
    def receiver(ws, message=None):
        return _receiver(ws, message)

    @internalmethod
    def _sender(self, ws, payload):
        body = payload if isinstance(payload, dict) else payload
        if self.wire is None:
            raise RuntimeError("PositiveCom.sender has no Wire attached")
        self.wire.send(body)
        if isinstance(body, dict) and "received" in body:
            self.echo_seen.add(body["received"])

    @externalmethod
    def sender(ws, payload):
        return _sender(ws, payload)

    @internalmethod
    def _echo(self, payload=None):
        if payload is None:
            payload = self.echo_payload
        token = payload.get('communicator_token') if isinstance(payload, dict) else None
        if token and self.ws:
            echo_payload = {'received': token}
            _sender(self.ws, echo_payload)

    @externalmethod
    def echo(payload=None):
        return _echo(payload)

    @internalmethod
    def _to_P(self, payload):
        manifest.info(payload)
        self.down_queue.append(payload)
        _process_down_queue()

    @externalmethod
    def to_P(payload):
        return _to_P(payload)

    @internalmethod
    def _from_P(self, payload):
        manifest.info(payload)
        token = payload.get('communicator_token') if isinstance(payload, dict) else None
        ws_id = self.ws_token_dict.get(token)
        ws = self.connections.get(ws_id)
        if token and ws:
            echo_payload = {'received': token}
            if payload.get('echo') == 'delay':
                pass
            else:
                _sender(ws, echo_payload)

    @externalmethod
    def from_P(payload):
        return _from_P(payload)
