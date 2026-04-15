import socket, asyncio, struct, os, uuid
from .state import manifest

def generate_unique_socket_path():
    path = f'/tmp/ws_{uuid.uuid4()}.sock'
    while os.path.exists(path):
        path = f'/tmp/ws_{uuid.uuid4()}.sock'
    return path

class UnixSocketFramer:
    @staticmethod
    def frame_message(message: str) -> bytes:
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

class UnixSocketClientSync:
    def __init__(self, socket_path: str):
        self.socket_path = socket_path
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.connect(self.socket_path)

    def connect(socket_path):
        self.sock.connect(socket_path)

    def send_message(self, message: str):
        framed = UnixSocketFramer.frame_message(message)
        self.sock.sendall(framed)

    def receive_message(self) -> str:
        data = b''
        while len(data) < 4:
            chunk = self.sock.recv(4 - len(data))
            if not chunk:
                raise ConnectionError('Socket closed')
            data += chunk
        length = struct.unpack('!I', data)[0]
        data = b''
        while len(data) < length:
            chunk = self.sock.recv(length - len(data))
            if not chunk:
                raise ConnectionError('Socket closed')
            data += chunk
        return data.decode('utf-8')

    def close(self):
        self.sock.close()

class UnixSocketClientAsync:
    def __init__(self, socket_path: str):
        self.socket_path = socket_path
        self.reader = None
        self.writer = None

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
        self.writer.close()
        await self.writer.wait_closed()

class UnixSocketServerAsync:
    def __init__(self, socket_path: str, handler):
        self.socket_path = socket_path
        self.handler = handler

    async def start_server(self):
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)
        server = await asyncio.start_unix_server(self._handle_client, self.socket_path)
        await server.serve_forever()

    async def _handle_client(self, reader, writer):
        buffer = b''
        try:
            while True:
                data = await reader.read(1024)
                if not data:
                    break
                buffer += data
                message, buffer = UnixSocketFramer.unframe_message(buffer)
                while message:
                    response = await self.handler(message)
                    if response:
                        framed = UnixSocketFramer.frame_message(response)
                        writer.write(framed)
                        await writer.drain()
                    message, buffer = UnixSocketFramer.unframe_message(buffer)
        except asyncio.IncompleteReadError:
            pass
        finally:
            writer.close()
            await writer.wait_closed()
