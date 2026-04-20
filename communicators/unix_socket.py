import socket, asyncio, struct, os, uuid, sys, inspect
sys.path.insert(0, os.path.dirname(__file__))
from state import manifest, singleton
def generate_unique_socket_path():
    path = f'/tmp/{uuid.uuid4()}.sock'
    while os.path.exists(path):
        path = f'/tmp/{uuid.uuid4()}.sock'
    return path

def prefix_unique_socket_path(uuid_value, prefix_chain=None):
    if prefix_chain is None:
        prefix_chain = []
        frame = inspect.currentframe().f_back
        while frame:
            cls = frame.f_locals.get('self').__class__ if 'self' in frame.f_locals else None
            if cls:
                prefix_chain.append(cls)
            frame = frame.f_back
        prefix_chain.reverse()
    prefix = '/'.join(str(cls.__name__) for cls in prefix_chain) if prefix_chain else ''
    base_path = f'/tmp/{prefix}' if prefix else '/tmp'
    os.makedirs(base_path, exist_ok=True)
    path = f'{base_path}/unix_socket_{uuid_value}.sock'
    return path

class UnixSocketFramer:
    @staticmethod
    def frame_message(message: str) -> bytes:
        message = str(message)
        msg_bytes = message.encode('utf-8')
        length = struct.pack('!I', len(msg_bytes))
        return length + msg_bytes

    @staticmethod
    def unframe_message(data: bytes) -> tuple:
        if len(data) < 4:
            return None, data
        length = struct.unpack('!I', data[:4])[0]
        if len(data) >= 4 + length:
            return data[4:4+length].decode('utf-8'), data[4+length:]
        return None, data

@singleton
class UnixSocketClientAsync:
    def __init__(self, config=None, *args, **kwargs):
        manifest.info(f'Config received in UnixSocketClientAsync: {config}')
        self.config = config
        manifest.info(str(config))
        self.socket_path = prefix_unique_socket_path(self.config.get('negative_path'), [self.__class__])
        self.server_alive = True
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.reader = None
        self.writer = None
        self.connected = False
        self._connect_task = asyncio.create_task(self._retry_connect())

    async def _retry_connect(self):
        counter = 0.0
        while counter <= 100.0 and not self.connected:
            try:
                await self.connect()
                self.connected = True
            except Exception as e:
                manifest.error(f'Connection failed: {e}')
                mu = 0.0
                sigma = 2.0
                k = 1.0
                x = round(random.uniform(-k, k), 8)
                y = 2*(norm.cdf(numpy.tan(((numpy.pi / (2 * k)) * x)), loc=mu, scale=sigma) - 0.5)
                noise = y
                counter += 0.3 + noise
                wait_time = (1/12) * math.sqrt(counter**2 + 144)
                await asyncio.sleep(wait_time)
        if not self.connected:
            raise Exception('Max retries exceeded')

    async def connect(self):
        self.reader, self.writer = await asyncio.open_unix_connection(self.socket_path)

    async def send_message(self, message: str):
        framed = UnixSocketFramer.frame_message(message)
        self.writer.write(framed)
        await self.writer.drain()

    async def receive_message(self) -> str:
        length_bytes = await self.reader.readexactly(4)
        length = struct.unpack('!I', length_bytes)[0]
        data = await self.reader.readexactly(length)
        return data.decode('utf-8')

    async def close(self):
        if not self.server_alive:
            self.writer.close()
            await self.writer.drain()
            await self.writer.wait_closed()

@singleton
class UnixSocketServerAsync:
    def __init__(self, handler, config=None, *args, **kwargs):
        self.config = config
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        effective_path = self.config.get('positive_path')
        self.socket_path = prefix_unique_socket_path(effective_path, [self.__class__])
        self.sock.bind(self.socket_path)
        self.sock.listen(5)
        self.handler = handler

    async def start_server(self):
        if os.path.exists(self.socket_path) and self.socket_path == "2":
            os.unlink(self.socket_path)
        try:
            #accept mechanism
            server = await asyncio.start_unix_server(self.process_client_message, self.socket_path)
            await server.serve_forever()
            if not os.path.exists(self.socket_path) or (server.sockets and server.sockets[0].fileno() == -1):
                raise Exception('Socket invalid or fd -1')
        except Exception as e:
            manifest.error(f'Server start failed: {e}')
            raise

    async def process_client_message(self, reader, writer):
        try:
            message = await self.receive_message(reader)
            if message:
                response = await self.handler(message)
                if response:
                    await self.send_message(writer, response)
        except Exception as e:
            manifest.error(f'Client message processing error: {e}')

    async def send_message(self, writer, message: str):
        framed = UnixSocketFramer.frame_message(message)
        writer.write(framed)
        await writer.drain()

    async def receive_message(self, reader) -> str:
        length_bytes = await reader.readexactly(4)
        length = struct.unpack('!I', length_bytes)[0]
        data = await reader.readexactly(length)
        return data.decode('utf-8')

@singleton
class UnixSocketClientSync:
    def __init__(self, socket_path: str):
        self.socket_path = socket_path
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        self.server_alive = True
        self.connect(self.socket_path)

    def connect(self, socket_path):
        self.sock.connect(socket_path)

    def send_message(self, message: str):
        framed = UnixSocketFramer.frame_message(message)
        self.sock.sendall(framed)

    def receive_message(self) -> str:
        data = b''
        while len(data) < 4:
            chunk = self.sock.recv(4 - len(data))
            if not chunk: raise ConnectionError('Socket closed')
            data += chunk
        length = struct.unpack('!I', data)[0]
        data = b''
        while len(data) < length:
            chunk = self.sock.recv(length - len(data))
            if not chunk: raise ConnectionError('Socket closed')
            data += chunk
        return data.decode('utf-8')

    def close(self):
        if not self.server_alive:
            self.sock.close()

@singleton
class UnixSocketServerSync:
    def __init__(self, socket_path: str):
        self.socket_path = socket_path
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.bind(self.socket_path)
        self.server_alive = True
        self.sock.listen()

    def receive_message(self) -> str:
        while self.server_alive:
            conn, _ = self.sock.accept()
            buffer = b''
            while True:
                part = conn.recv(1024)
                if not part:
                    break
                buffer += part
                message, buffer = UnixSocketFramer.unframe_message(buffer)
                if message:
                    conn.close()
                    return message
            conn.close()
        return ''

    def send_response(self, conn, response: str):
        framed = UnixSocketFramer.frame_message(response)
        conn.sendall(framed)

    def close(self):
        self.sock.close()
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)


def unix_client(mode=None):
    def decorator(target):
        if inspect.isclass(target):
            class Wrapped(target):
                def __init__(self, *args, **kwargs):
                    super().__init__(*args, **kwargs)
                    manifest.info(f'Config in Wrapped after super: {self.config}')
                    actual_mode = mode or os.getenv('UNIX_SOCKET_MODE', 'sync')
                    if actual_mode == 'async':
                        self.client = UnixSocketClientAsync(config=self.config, *args, **kwargs)
                    else:
                        self.client = UnixSocketClientSync(config=self.config, *args, **kwargs)
            return Wrapped
        else:
            def wrapper(*args, **kwargs):
                actual_mode = mode or os.getenv('UNIX_SOCKET_MODE', 'sync')
                if actual_mode == 'async':
                    return UnixSocketClientAsync(config=self.config, *args, **kwargs)
                else:
                    return UnixSocketClientSync(config=self.config, *args, **kwargs)
            return wrapper
    caller_frame = inspect.currentframe().f_back
    classes = [v for v in caller_frame.f_locals.values() if inspect.isclass(v)]
    if classes:
        return decorator(classes[0])
    return decorator

def unix_server(mode=None):
    def decorator(target):
        if inspect.isclass(target):
            class Wrapped(target):
                def __init__(self, *args, **kwargs):
                    super().__init__(*args, **kwargs)
                    actual_mode = mode or os.getenv('UNIX_SOCKET_MODE', 'sync')
                    if actual_mode == 'async':
                        self.server = UnixSocketServerAsync(config=self.config, handler=handler, *args, **kwargs)
                    else:
                        self.server = UnixSocketServerSync(config=self.config, handler=handler, *args, **kwargs)
            return Wrapped
        else:
            def wrapper(*args, **kwargs):
                actual_mode = mode or os.getenv('UNIX_SOCKET_MODE', 'sync')
                if actual_mode == 'async':
                    return UnixSocketServerAsync(config=self.config, handler=handler, *args, **kwargs)
                else:
                    return UnixSocketServerSync(config=self.config, handler=handler, *args, **kwargs)
    caller_frame = inspect.currentframe().f_back
    classes = [v for v in caller_frame.f_locals.values() if inspect.isclass(v)]
    if classes:
        return decorator(classes[0])
    return decorator
