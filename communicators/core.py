import json, secrets, os, tracemalloc, signal, shutil, subprocess, time, threading
import websockets.sync.client as ws_client
from collections import deque
from .state import manifest, truncate, freight

tracemalloc.start(7)

"""
negative == initiates websocket
positive == recieves and remembers websocket(s)
down == from middleware to communicator
up == from communicator to middleware
"""

def singleton(cls):
    instances = {}
    original_new = cls.__new__
    def __new__(cls, *args, **kwargs):
        if cls not in instances:
            instances[cls] = original_new(cls, *args, **kwargs)
        return instances[cls]
    cls.__new__ = staticmethod(__new__)
    return cls

def inject_echo_payload(func):
    def wrapper(self, *args, **kwargs):
        if 'payload' not in kwargs and hasattr(self, 'echo_payload'):
            kwargs['payload'] = self.echo_payload
        return func(self, *args, **kwargs)
    return wrapper

def get_ws_closed_status(ws):
    manifest.info("Checking ws status...")
    if ws is None:
        return 'Default'
    try:
        manifest.info(f"ws as string: {str(ws)} This is after the ws object.")
        return 'True' if ws.state.name == 'CLOSED' else 'False'
    except Exception as e:
        manifest.error(f'Exception checking ws.state so we can see what is going on: {e}')
        return 'Default'

@singleton
class NegativeCom:
    # Clarification: Only NegativeCom has permission to initiate websocket connections.
    _instance = None

    def __init__(self, config=None):
        self.config = config or {}
        self.echo_payload = None
        self.negative = self
        self.lock = threading.Lock()

    def __new__(cls, config):
        if cls._instance is None:
            cls._instance = object.__new__(cls)
            cls._instance.ws = None
            cls._instance.up_queue = deque()  # incoming messages from another server to middleware
            cls._instance.down_queue = deque()  # outgoing messages from middleware to another server
            cls._instance._busy_down = False
            cls._instance._busy_up = False
            cls._instance._connected_once = False
            cls._instance._listener_thread = None
            cls._instance._listener_started = False
        return cls._instance

    def _connect(self):
        if self.ws and not (get_ws_closed_status(self.ws) == 'True'): return
        if self._connected_once and (self.ws is None or (get_ws_closed_status(self.ws) == 'True')):
            manifest.error('WS connection dropped unexpectedly')
            return
        elif not self._connected_once:
            addr = self.config.get('negative_address', {})
            ws_path = f"ws://{addr.get('host')}:{addr.get('port')}/ws"
            try:
                self.ws = ws_client.connect(
                    ws_path,
                    ping_interval=None,
                    ping_timeout=None,
                    close_timeout+None,
                    max_size=None)
                manifest.info(f'WS connected to {ws_path}')
                manifest.info(f'1st Send ok; WS close? {get_ws_closed_status(self.ws)}, exc={getattr(self.ws, "close_exc", "None")}')
                self.listen_for_responses(self.ws)
                manifest.info(f'2nd Send ok; WS close? {get_ws_closed_status(self.ws)}, exc={getattr(self.ws, "close_exc", "None")}')
                self._connected_once = True
            except Exception as e:
                manifest.error(f'Connection error: {e}')

    def get_ws(self):
        self._connect()
        return self.ws

    def wait_for_echo(self, token):
        while True:
            time.sleep(0.1)
            for msg in list(self.up_queue):
                if msg.get('received') == token:
                    self.up_queue.remove(msg)
                    return

    def process_down_queue(self):
        with self.lock:
            manifest.info("This was triggered.")
            if self._busy_down: return
            for item in list(self.down_queue):
                self._busy_down = True
                if self.down_queue[0]:
                    if 'communicator_token' not in self.down_queue[0]:
                        self.down_queue[0]['communicator_token'] = f'{secrets.randbelow(10**29):029d}'
                    self.send(self.down_queue[0])
                    token = self.down_queue[0].get('communicator_token')
                    self.wait_for_echo(token)
                    self.down_queue.popleft()
                    self._busy_down = False

    def send(self, payload):
        ws = self.get_ws()
        if ws:
            manifest.info(f'Sending payload: {truncate(500, payload)}, WS close: {get_ws_closed_status(self.ws)}')
            if (get_ws_closed_status(self.ws) == 'True'):
                manifest.error('Attempting to send on close WS')
                return
            ws.send(json.dumps(payload))

    # Break is necessary to prevent rapid useless error loops. This is v1 Failure should be loud, but not repatative.
    def listen_for_responses(self, websocket):
        def _listener():
            ws = self.get_ws()
            while ws and not (get_ws_closed_status(self.ws) == 'True'):
                manifest.info('WS recv loop iteration')
                try:
                    message = ws.recv()
                    if message:
                        manifest.info(f'Message received: {truncate(500, message)}')
                        data = json.loads(message)
                        self.up_queue.append(data)
                        manifest.info('Message appended to up_queue')
                        self.process_up_queue()
                    else:
                        break
                except Exception as e:
                    manifest.error(f'Listen error: {e}')
                    if (get_ws_closed_status(self.ws) == 'True'):
                        manifest.error('WS close unexpectedly in NegativeCom listener')
                    break
        if self._listener_thread and self._listener_started:
            return
        manifest.info('Listener thread started')
        self._listener_started = True
        self._listener_thread = threading.Thread(target=_listener, daemon=True)
        self._listener_thread.start()

    def process_up_queue(self):
        if self._busy_up: return
        manifest.info('Processing up_queue')
        for item in list(self.up_queue):
            self._busy_up = True
            if self.up_queue[0]:
                self.negative.from_N(self.up_queue[0])
                token = self.up_queue[0].get('communicator_token')
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
        token = payload.get('communicator_token') if payload else None
        if token and self.ws:
            echo_payload = {'received': token}
            self.ws.send(json.dumps(echo_payload))

    def from_N(self, payload):
        manifest.info(truncate(500, payload))
        token = payload.get('communicator_token')
        if token and self.ws:
            echo_payload = {'received': token}
            if payload.get('echo') == 'delay':
                time.sleep(0.1)
                pass
            else:
                self.ws.send(json.dumps(echo_payload))

    def to_N(self, payload):
        manifest.info(truncate(500, payload))
        payload = freight(payload)
        self.down_queue.append(payload)
        self.process_down_queue()

    def close(self):
        if self.ws:
            self.ws.close()
            self.ws = None

@singleton
class PositiveCom:
    _instance = None
    # Clarification: PositiveCom only has permission to receive and maintain websocket connections.

    def __init__(self, config=None):
        self.config = config or {}
        self.echo_payload = None
        self.positive = self

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
            cls._instance._listener_thread = None
            cls._instance._listener_started = False
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
                token = payload.get('communicator_token')
                if token and token in self.ws_token_dict:
                    ws_id = self.ws_token_dict[token]
                    if ws_id in self.connections:
                        self.connections[ws_id].send_str(json.dumps(payload))
                        token = self.down_queue[0].get('communicator_token')
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
                token = self.up_queue[0].get('communicator_token')
                self.wait_for_echo(token)
                self.up_queue.popleft()
        self._busy_up = False

    # Break is necessary to prevent rapid useless error loops. This is v1 Failure should be loud, but not repatative.
    def listen_for_responses(self, websocket):
        self.connections[id(websocket)] = websocket
        def _listener():
            while not ({get_ws_closed_status(websocket)} == 'True'):
                manifest.info('WS recv loop iteration')
                try:
                    message = websocket.recv()
                    manifest.info(f'Message received: {truncate(500, message)}')
                    if message:
                        data = json.loads(message)
                        token = data.get('communicator_token')
                        if token: self.ws_token_dict[token] = id(websocket)
                        self.up_queue.append(data)
                        manifest.info('Message appended to up_queue')
                        self.process_up_queue()
                except Exception as e:
                    manifest.error(f'Listen error: {e}')
                    if ({get_ws_closed_status(websocket)} == 'True'):
                        manifest.error('WS close in PositiveCom listener')
                    break
        if self._listener_thread and self._listener_started:
            return
        manifest.info('Listener thread started')
        self._listener_started = True
        self._listener_thread = threading.Thread(target=_listener, daemon=True)
        self._listener_thread.start()

    @inject_echo_payload
    def echo(self, payload=None):
        token = payload.get('communicator_token') if payload else None
        if token and self.ws:
            echo_payload = {'received': token}
            self.ws.send(json.dumps(echo_payload))

    def to_P(self, payload):
        manifest.info(truncate(500, payload))
        payload = freight(payload)
        self.down_queue.append(payload)
        self.process_down_queue()

    def from_P(self, payload):
        manifest.info(truncate(500, payload))
        token = payload.get('communicator_token')
        ws_id = self.ws_token_dict.get(token)
        ws = self.connections.get(ws_id)
        if token and ws:
            echo_payload = {'received': token}
            if payload.get('echo') == 'delay':
                pass
            else:
                ws.send(json.dumps(echo_payload))
