
"""
negative == initiates websocket
positive == recieves and remembers websocket(s)
down == from middleware to communicator
up == from communicator to middleware
"""

class NegativeCom:
    # Clarification: Only NegativeCom has permission to initiate websocket connections.
    _instance = None

    @internalmethod
    def __init__(self, config=None):
        self.config = config or {}
        self.echo_payload = None
        self.negative = self
        self.lock = threading.Lock()
        self.socket_path = generate_unique_socket_path()
        self.ws = None
        self.wire = self.config.get("wire")

    @internalmethod
    def __new__(cls, config):
        if cls._instance is None:
            cls._instance = object.__new__(cls)
            cls._instance.ws = None
            cls._instance.up_queue = deque()  # incoming messages from another server to middleware
            cls._instance.down_queue = deque()  # outgoing messages from middleware to another server
            cls._instance._busy_down = False
            cls._instance._busy_up = False
            cls._instance.wire = None
            cls._instance.echo_seen = set()
        return cls._instance

    @dualmethod
    def inject_echo_payload(func):
        def wrapper(self, *args, **kwargs):
            if 'payload' not in kwargs and hasattr(self, 'echo_payload'):
                kwargs['payload'] = self.echo_payload
            return func(self, *args, **kwargs)
        return wrapper

    @externalmethod
    def attach_wire(self, wire):
        self.wire = wire
        self.ws = wire
        if not hasattr(self, "echo_seen"):
            self.echo_seen = set()
        self._start_up_pump()
        return wire

    @internalmethod
    def _start_up_pump(self):
        if getattr(self, "_pump_started", False):
            return
        self._pump_started = True
        self._pump_alive = True

        def pump():
            while getattr(self, "_pump_alive", False):
                if self.up_queue and not self._busy_up:
                    self.process_up_queue()
                time.sleep(0.05)

        threading.Thread(target=pump, name="neg-up-pump", daemon=True).start()

    @dualmethod
    def process_down_queue(self):
        with self.lock:
            manifest.info("This was triggered.")
            if self._busy_down: return
            for item in list(self.down_queue):
                self._busy_down = True
                if self.down_queue[0]:
                    self.sender(self.ws, self.down_queue[0])
                    token = self.down_queue[0]['communicator_token']
                    self.wait_for_echo(token)
                    self.down_queue.popleft()
                    self._busy_down = False

    @dualmethod
    def sender(self, ws, payload):
        body = payload if isinstance(payload, dict) else freight.upgrades(payload)
        if self.wire is None:
            raise RuntimeError("NegativeCom.sender has no Wire attached")
        self.wire.send(body)
        if isinstance(body, dict) and "received" in body:
            self.echo_seen.add(body["received"])

    # Break is necessary to prevent rapid useless error loops. This is v1 Failure should be loud, but not repatative.
    @externalmethod
    def receiver(self, ws, message=None):
        if message:
            manifest.info(f'Message received: {truncate(500, message)}')
            data = freight.upgrades(message=message)
            if "received" in data:
                self.echo_seen.add(data["received"])
                return
            self.up_queue.append(data)
            manifest.info('Message appended to up_queue')

    @dualmethod
    def process_up_queue(self):
        if self._busy_up: return
        manifest.info('Processing up_queue')
        for item in list(self.up_queue):
            self._busy_up = True
            if self.up_queue[0]:
                self.negative.from_N(self.up_queue[0])
                token = freight.get(freight_obj=self.up_queue[0], key='communicator_token')
                self.wait_for_echo(token)
                self.up_queue.popleft()
        manifest.info('up_queue processed')
        self._busy_up = False

    @dualmethod
    def wait_for_echo(self, token):
        while True:
            time.sleep(0.1)
            if token in getattr(self, "echo_seen", ()):
                return
            for msg in list(self.up_queue):
                if msg.get('received') == token:
                    self.up_queue.remove(msg)
                    return

    @externalmethod
    @inject_echo_payload
    def echo(self, payload=None):
        token = freight.get(freight_obj=payload, key='communicator_token') if payload else None
        if token and self.ws:
            echo_payload = {'received': token}
            self.sender(self.ws, freight.upgrades(echo_payload))

    @dualmethod
    def from_N(self, payload):
        manifest.info(truncate(500, payload))
        token = freight.get(freight_obj=payload, key='communicator_token')
        if token and self.ws:
            echo_payload = {'received': token}
            if payload.get('echo') == 'delay':
                time.sleep(0.1)
                pass
            else:
                self.sender(self.ws, echo_payload)

    @externalmethod
    def to_N(self, payload):
        manifest.info(truncate(500, payload))
        payload = freight.upgrades(payload)
        self.down_queue.append(payload)
        self.process_down_queue()

class PositiveCom:
    _instance = None
    # Clarification: PositiveCom only has permission to receive and maintain websocket connections.

    @internalmethod
    def __init__(self, config=None):
        self.config = config or {}
        self.echo_payload = None
        self.positive = self
        self.socket_path = generate_unique_socket_path()
        self.ws = None
        self.wire = self.config.get("wire")

    @internalmethod
    def __new__(cls, config):
        if cls._instance is None:
            cls._instance = object.__new__(cls)
            cls._instance.config = config
            cls._instance.positive_addr = cls._instance.config.get('positive_address', {})
            cls._instance.port = int(cls._instance.positive_addr.get('port', 0))
            PositiveCom._preemptive_port_cleanup(cls._instance.port)
            cls._instance.ws = None
            cls._instance.connections = {}
            cls._instance.ws_token_dict = {}
            cls._instance.ws_id = id(cls._instance)
            cls._instance.up_queue = deque()  # incoming messages from another server to middleware
            cls._instance.down_queue = deque()  # outgoing messages from middleware to another server
            cls._instance._busy_down = False
            cls._instance._busy_up = False
            cls._instance.wire = None
            cls._instance.connections = getattr(cls._instance, "connections", {})
            cls._instance.echo_seen = set()
        return cls._instance

    @dualmethod
    def inject_echo_payload(func):
        def wrapper(self, *args, **kwargs):
            if 'payload' not in kwargs and hasattr(self, 'echo_payload'):
                kwargs['payload'] = self.echo_payload
            return func(self, *args, **kwargs)
        return wrapper

    @externalmethod
    def attach_wire(self, wire):
        self.wire = wire
        self.ws = wire
        self.connections[id(wire)] = wire
        if not hasattr(self, "echo_seen"):
            self.echo_seen = set()
        if not getattr(self, "_pump_started", False):
            self._pump_started = True
            self._pump_alive = True

            def pump():
                while getattr(self, "_pump_alive", False):
                    if self.up_queue and not self._busy_up:
                        self.process_up_queue()
                    time.sleep(0.05)

            threading.Thread(target=pump, name="pos-up-pump", daemon=True).start()
        return wire

    @dualmethod
    @staticmethod
    def _find_pids_on_port(port: int) -> set[int]:
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

    @dualmethod
    @staticmethod
    def _preemptive_port_cleanup(port: int) -> None:
        if port <= 0:
            return
        pids = PositiveCom._find_pids_on_port(port)
        for pid in sorted(pids):
            if pid == os.getpid():
                continue
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                continue
            time.sleep(0.1)

    @dualmethod
    def process_down_queue(self):
        if self._busy_down: return
        for item in list(self.down_queue):
            self._busy_down = True
            if self.down_queue[0]:
                payload = self.down_queue[0]
                token = freight.get(freight_obj=payload, key='communicator_token')
                if token and token in self.ws_token_dict:
                    ws_id = self.ws_token_dict[token]
                    if ws_id in self.connections:
                        self.sender(self.connections[ws_id], self.down_queue[0])
                        token = freight.get(freight_obj=self.down_queue[0], key='communicator_token')
                        self.wait_for_echo(token)
                        self.down_queue.popleft()
        self._busy_down = False

    @dualmethod
    def wait_for_echo(self, token):
        while True:
            time.sleep(0.1)
            if token in getattr(self, "echo_seen", ()):
                return
            for msg in list(self.up_queue):
                if msg.get('received') == token:
                    self.up_queue.remove(msg)
                    return

    @dualmethod
    def process_up_queue(self):
        if self._busy_up: return
        for item in list(self.up_queue):
            self._busy_up = True
            if self.up_queue[0]:
                self.positive.from_P(self.up_queue[0])
                token = freight.get(freight_obj=self.up_queue[0], key='communicator_token')
                self.wait_for_echo(token)
                self.up_queue.popleft()
        self._busy_up = False

    # Break is necessary to prevent rapid useless error loops. This is v1 Failure should be loud, but not repatative.
    @externalmethod
    def receiver(self, ws, message=None):
        if message:
            data = freight.upgrades(message=message)
            token = freight.get(freight_obj=data, key='communicator_token')
            handle = ws if ws is not None else self.wire
            if token and handle is not None:
                self.ws_token_dict[token] = id(handle)
                self.connections[id(handle)] = handle
            if "received" in data:
                self.echo_seen.add(data["received"])
                return
            self.up_queue.append(data)
            manifest.info('Message appended to up_queue')

    @dualmethod
    def sender(self, ws, payload):
        body = payload if isinstance(payload, dict) else freight.upgrades(payload)
        if self.wire is None:
            raise RuntimeError("PositiveCom.sender has no Wire attached")
        self.wire.send(body)
        if isinstance(body, dict) and "received" in body:
            self.echo_seen.add(body["received"])

    @externalmethod
    @inject_echo_payload
    def echo(self, payload=None):
        token = freight.get(freight_obj=payload, key='communicator_token') if payload else None
        if token and self.ws:
            echo_payload = {'received': token}
            self.sender(self.ws, freight.upgrades(echo_payload))

    @externalmethod
    def to_P(self, payload):
        manifest.info(truncate(500, payload))
        payload = freight.upgrades(payload)
        self.down_queue.append(payload)
        self.process_down_queue()

    @dualmethod
    def from_P(self, payload):
        manifest.info(truncate(500, payload))
        token = freight.get(freight_obj=payload, key='communicator_token')
        ws_id = self.ws_token_dict.get(token)
        ws = self.connections.get(ws_id)
        if token and ws:
            echo_payload = {'received': token}
            if payload.get('echo') == 'delay':
                pass
            else:
                self.sender(ws, echo_payload)
