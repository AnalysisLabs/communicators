import json, secrets, os, tracemalloc, signal, shutil, subprocess, time, threading, uuid
from collections import deque
from .state import manifest, truncate, freight, singleton
from .ws_tamer import WSTamer
from .unix_socket import UnixSocketClientSync, generate_unique_socket_path

tracemalloc.start(7)

"""
negative == initiates websocket
positive == recieves and remembers websocket(s)
down == from middleware to communicator
up == from communicator to middleware
"""

def inject_echo_payload(func):
    def wrapper(self, *args, **kwargs):
        if 'payload' not in kwargs and hasattr(self, 'echo_payload'):
            kwargs['payload'] = self.echo_payload
        return func(self, *args, **kwargs)
    return wrapper

@singleton
class NegativeCom:
    # Clarification: Only NegativeCom has permission to initiate websocket connections.
    _instance = None

    def __init__(self, config=None):
        self.config = config or {}
        self.echo_payload = None
        self.negative = self
        self.lock = threading.Lock()
        self.socket_path = generate_unique_socket_path()
        self.ws_tamer = WSTamer()
        self.ws = self.ws_tamer.negative_sequence(config)

    def __new__(cls, config):
        if cls._instance is None:
            cls._instance = object.__new__(cls)
            cls._instance.ws = None
            cls._instance.up_queue = deque()  # incoming messages from another server to middleware
            cls._instance.down_queue = deque()  # outgoing messages from middleware to another server
            cls._instance._busy_down = False
            cls._instance._busy_up = False
        return cls._instance

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

    def sender(self, ws, payload):
        client = UnixSocketClientSync(self.ws_tamer.socket_path); #This line
        client.send_message(freight.upgrades(payload));
        client.close()

    # Break is necessary to prevent rapid useless error loops. This is v1 Failure should be loud, but not repatative.
    def receiver(self, ws, message=None):
        if message:
            manifest.info(f'Message received: {truncate(500, message)}')
            data = freight.upgrades(message=message)
            self.up_queue.append(data)
            manifest.info('Message appended to up_queue')
            self.process_up_queue()

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

    def wait_for_echo(self, token):
        while True:
            time.sleep(0.1)
            for msg in list(self.up_queue):
                if msg.get('received') == token:
                    self.up_queue.remove(msg)
                    return

    @inject_echo_payload
    def echo(self, payload=None):
        token = freight.get(freight_obj=payload, key='communicator_token') if payload else None
        if token and self.ws:
            echo_payload = {'received': token}
            sender(self.ws, freight.upgrades(echo_payload))

    def from_N(self, payload):
        manifest.info(truncate(500, payload))
        token = freight.get(freight_obj=payload, key='communicator_token')
        if token and self.ws:
            echo_payload = {'received': token}
            if payload.get('echo') == 'delay':
                time.sleep(0.1)
                pass
            else:
                sender(self.ws, freight.dumps(echo_payload))

    def to_N(self, payload):
        manifest.info(truncate(500, payload))
        payload = freight.upgrades(payload)
        self.down_queue.append(payload)
        self.process_down_queue()

@singleton
class PositiveCom:
    _instance = None
    # Clarification: PositiveCom only has permission to receive and maintain websocket connections.

    def __init__(self, config=None):
        self.config = config or {}
        self.echo_payload = None
        self.positive = self
        self.socket_path = generate_unique_socket_path()
        self.ws_tamer = WSTamer()
        handler = self.receiver
        self.ws = self.ws_tamer.positive_sequence(config, handler)

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
        return cls._instance


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

    def wait_for_echo(self, token):
        while True:
            time.sleep(0.1)
            for msg in list(self.up_queue):
                if msg.get('received') == token:
                    self.up_queue.remove(msg)
                    return

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
    def receiver(self, ws, message=None):
        if message:
            data = freight.upgrades(message=message)
            token = freight.get(freight_obj=data, key='communicator_token')
            if token: self.ws_token_dict[token] = id(ws)
            self.up_queue.append(data)
            manifest.info('Message appended to up_queue')
            self.process_up_queue()

    def sender(self, ws, payload):
        client = UnixSocketClientSync(self.ws_tamer.socket_path);
        client.send_message(payload)
        client.close()

    @inject_echo_payload
    def echo(self, payload=None):
        token = freight.get(freight_obj=payload, key='communicator_token') if payload else None
        if token and self.ws:
            echo_payload = {'received': token}
            sender(self.ws, freight.upgrades(echo_payload))

    def to_P(self, payload):
        manifest.info(truncate(500, payload))
        payload = freight.upgrades(payload)
        self.down_queue.append(payload)
        self.process_down_queue()

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
                sender(ws, freight.dumps(echo_payload))
