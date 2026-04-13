import tracemalloc, threading, asyncio, websockets
from aiohttp import web
from .state import manifest, freight
from .unix_socket import UnixSocketServerAsync, generate_unique_socket_path

"""
Directive to AI about how to understank the following program:

Background: ws_tamer will act like a library within a library while it is getting built to act as auxilary to core.py for strictly ws management, it should also be the sort of thing an api use could use directly ifs they don't like how hard ws are to work with, but don't want the full package offered by core.py. At this point I am mentally tracing the control flow to make sure it is conceptually complete before running tests in terminal.

Note: This is version 1. In version one, reconnection and redundant connection between any two servers are strictly forbidden. While postive and negatice coms need thier own listener on its own thread, those thread must be recycled, an dif such fails, that should result in a manifest like, "Attempting to send on closed WS" and no attempt to restore the ws. To clarify, a ws is NEVER supposed to be closed, except when the entire server system is shut down.
"""

class WSTamer:
    def __init__(self):
        manifest.info('WSTamer __init__ start')
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever)
        self.thread.start()
        self.socket_path = generate_unique_socket_path()
        self.ws = None
        self.unix_server = UnixSocketServerAsync(self.socket_path, self.handle_unix_message)
        asyncio.run_coroutine_threadsafe(self.unix_server.start_server(), self.loop)
        manifest.info('WSTamer __init__ end')

    async def init_websocket(self, config):
        manifest.info('init_websocket start')
        addr = config.get('negative_address', {})
        ws_path = f"ws://{addr.get('host')}:{addr.get('port')}/ws"
        self.ws = await websockets.connect(ws_path)
        manifest.info('init_websocket end')
        return self.ws

    async def get_ws_closed_status(self, ws):
        manifest.info('Checking ws status...')
        if ws is None:
            return 'Default'
        try:
            manifest.info(f'ws as string: {str(ws)}')
            return 'True' if ws.state.name == 'CLOSED' else 'False'
        except Exception as e:
            manifest.error(f'Exception: {e}')
            return 'Default'

    async def handle_unix_message(self, message):
        data = freight.loads(message)
        await self.send_over_ws(self.ws, data)

    async def send_over_ws(self, ws, payload):
        manifest.info('send_over_ws start')
        if ws:
            await ws.send(freight.dumps(payload))
        manifest.info('send_over_ws end')

    async def receive_over_ws(self, ws):
        manifest.info('receive_over_ws start')
        if ws:
            message = await ws.recv()
            client = UnixSocketClientAsync(self.socket_path)
            await client.connect()
            await client.send_message(freight.dumps({'ws': str(ws), 'message': message}))
            return ws, message
        return None, None

    async def accept_websocket_init(self, config, handler):
        manifest.info('accept_websocket_init start')
        addr = config.get('positive_address', {})
        host = addr.get('host')
        port = int(addr.get('port'))
        server = await websockets.serve(handler, host, port)
        # await server.wait_closed()

    async def handle_outbound(message):
        manifest.info('handle_outbound start')
        data = freight.loads(message);
        await self.send_over_ws(self.ws, data)

    def negative_sequence(self, config):
        manifest.info('negative_sequence start')
        return asyncio.run_coroutine_threadsafe(self.init_websocket(config), self.loop).result()

    def positive_sequence(self, config, handler):
        manifest.info('positive_sequence start')
        asyncio.run_coroutine_threadsafe(self.accept_websocket_init(config, handler), self.loop)

# Or class
"""
Directive to AI about how to understank the following code block:
ws_tamer.ws_bridge exists since I do not think that we need to explicitly include the startup (init + accept)
or the ws management functions explicitly in the api use case (core.py) since we can use decorators
or whatever to make them virtually present when first needed.
this way the api use case only needs a sender and reciever function explicitly present.
Thus we need ws_bridge (which I am happy to upgrade to a class if thet fits better) will
define the @ws_bridge for core.py so we can have the benefit of the other functions of
ws_tamer without out having to directly call them. this way the raw functions could be
used directly by someone, while core.py will enjoy all the benefits of abstraction.
Obviouslt the current ws is just a rough draft produced by copy and pasting from the
previous version of the communicators library. To be clear core.py is basicly the way
it should be but ws_tamer will need a lot of work.
"""
def ws_bridge(cls):
    pass


