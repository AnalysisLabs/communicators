import asyncio, websockets, json, secrets, os, signal, shutil, subprocess, time
from aiohttp import web
from collections import deque

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

@singleton
class NegativeCom:
    _instance = None

    def __init__(self, config=None):
        self.config = config or {}
        self.echo_payload = None
        self.negative = self

    def __new__(cls, config):
        if cls._instance is None:
            cls._instance = object.__new__(cls)
            cls._instance.ws = None
            cls._instance.up_queue = deque()  # incoming messages from another server to middleware
            cls._instance.down_queue = deque()  # outgoing messages from middleware to another server
            cls._instance._busy_down = False
            cls._instance._busy_up = False
        return cls._instance

    async def _connect(self):
        if self.ws and not getattr(self.ws, 'closed', True):
            return
        addr = self.config.get('negative_address', {})
        ws_path = f"ws://{addr.get('host')}:{addr.get('port')}/ws"
        try:
            self.ws = await websockets.connect(ws_path)
        except Exception as e:
            print(f'Connection error: {e}')

    async def get_ws(self):
        await self._connect()
        return self.ws

    async def wait_for_echo(self, token):
        while True:
            await asyncio.sleep(0.1)
            for msg in list(self.up_queue):
                if msg.get('received') == token:
                    self.up_queue.remove(msg)
                    return

    async def process_down_queue(self):
        if self._busy_down: return
        for item in list(self.down_queue):
            self._busy_down = True
            if self.down_queue[0]:
                if 'communicator_token' not in self.down_queue[0]:
                    self.down_queue[0]['communicator_token'] = f'{secrets.randbelow(10**29):029d}'
                await self.send(self.down_queue[0])

                try:
                    await asyncio.wait_for(self.wait_for_echo(token), timeout=10.0)
                    self.down_queue.popleft()
                except asyncio.TimeoutError:
                    # Log or handle failure
                    pass
                self._busy_down = False

    async def send(self, payload):
        ws = await self.get_ws()
        if ws:
            await ws.send(json.dumps(payload))

    # This conceptually recieves stuff from positiveCommunicator though in reality this is not configured yet.
    async def listen_for_responses(self):
        ws = await self.get_ws()
        if ws:
            async for message in ws:
                data = json.loads(message)
                self.up_queue.append(data)  # incoming
                await self.negative.process_up_queue()

    async def process_up_queue(self):
        if self._busy_up: return
        for item in list(self.up_queue):
            self._busy_up = True
            if self.up_queue[0]:
                self.negative.from_N(self.up_queue[0])
                # Await echo receipt with timeout
                try:
                    await asyncio.wait_for(self.wait_for_echo(token), timeout=10.0)
                    self.up_queue.popleft()
                except asyncio.TimeoutError:
                    # Log or handle failure
                    pass
        self._busy_up = False

    async def wait_for_echo(self, token):
        while True:
            await asyncio.sleep(0.1)
            for msg in list(self.up_queue):
                if msg.get('received') == token:
                    self.up_queue.remove(msg)
                    return

    @inject_echo_payload
    async def echo(self, payload=None):
        token = payload.get('communicator_token') if payload else None
        if token and self.ws:
            echo_payload = {'received': token}
            await self.ws.send(json.dumps(echo_payload))

    def from_N(self, payload):
        token = payload.get('communicator_token')
        if token and self.ws:
            echo_payload = {'received': token}
            if payload.get('echo') == 'delay':
                pass
            else:
                asyncio.create_task(self.ws.send(json.dumps(echo_payload)))

    def to_N(self, payload):
        self.down_queue.append(payload)
        asyncio.create_task(self.negative.process_down_queue())

    async def close(self):
        if self.ws:
            await self.ws.close()
            self.ws = None

@singleton
class PositiveCom:
    _instance = None

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
            cls._instance.token_to_ws_id = {}
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

    async def process_down_queue(self):
        if self._busy_down: return
        for item in list(self.down_queue):
            self._busy_down = True
            if self.down_queue[0]:
                payload = self.down_queue[0]
                token = payload.get('communicator_token')
                if token and token in self.ws_token_dict:
                    ws_id = self.ws_token_dict[token]
                    if ws_id in self.connections:
                        await self.connections[ws_id].send_str(json.dumps(payload))
                        # Await echo_payload receipt with timeout
                        try:
                            await asyncio.wait_for(self.wait_for_echo(token), timeout=10.0)
                            self.down_queue.popleft()
                        except asyncio.TimeoutError:
                            # Log or handle failure
                            pass
        self._busy_down = False

    async def wait_for_echo(self, token):
        while True:
            await asyncio.sleep(0.1)
            for msg in list(self.up_queue):
                if msg.get('received') == token:
                    self.up_queue.remove(msg)
                    return

    async def process_up_queue(self):
        if self._busy_up: return
        for item in list(self.up_queue):
            self._busy_up = True
            if self.up_queue[0]:
                self.positive.from_P(self.up_queue[0])
                # Await echo_payload receipt with timeout
                try:
                    await asyncio.wait_for(self.wait_for_echo(token), timeout=10.0)
                    self.up_queue.popleft()
                except asyncio.TimeoutError:
                    # Log or handle failure
                    pass
        self._busy_up = False

    async def listen_for_responses(self):
        ws = await self.get_ws()
        if ws:
            async for message in ws:
                await self.accept(message, ws)

    # This conceptually recieves stuff from NegativeCom though in reality this is not configured yet.
    async def accept(self, request, ws):
        await ws.prepare(request)
        ws_id = id(ws)
        self.connections[ws_id] = ws
        self.ws = ws
        msg = await ws.receive()
        if msg.type == aiohttp.WSMsgType.TEXT:
            data = json.loads(msg.data)
            token = data.get('communicator_token')
            if token:
                self.ws_token_dict[token] = ws_id
                self.up_queue.append(data)
                await self.positive.process_up_queue()

    @inject_echo_payload
    async def echo(self, payload=None):
        token = payload.get('communicator_token') if payload else None
        if token and self.ws:
            echo_payload = {'received': token}
            await self.ws.send(json.dumps(echo_payload))

    def to_P(self, payload):
        self.down_queue.append(payload)
        asyncio.create_task(self.positive.process_down_queue())

    def from_P(self, payload):
        token = payload.get('communicator_token')
        if token and self.ws:
            echo_payload = {'received': token}
            if payload.get('echo') == 'delay':
                pass
            else:
                asyncio.create_task(self.ws.send(json.dumps(echo_payload)))
