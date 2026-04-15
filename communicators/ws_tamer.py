import tracemalloc, threading, asyncio, websockets, math, random, numpy
from scipy.stats import norm
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
        counter = 0.0
        while counter <= 100.0:
            try:
                self.ws = await websockets.connect(ws_path)
                manifest.info('init_websocket end: ', addr)
                return self.ws
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
        raise Exception('Max retries exceeded')

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
        data = freight.upgrades(message)
        await self.send_over_ws(self.ws, data)

    async def send_over_ws(self, ws, payload):
        manifest.info('send_over_ws start')
        if ws:
            await ws.send(payload)
        manifest.info('send_over_ws end')

    async def receive_over_ws(self, ws):
        manifest.info('receive_over_ws start')
        if ws:
            message = await ws.recv()
            client = UnixSocketClientAsync(self.socket_path)
            await client.connect()
            await client.send_message({'ws': str(ws), 'message': message})
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


