import json, tracemalloc, threading, asyncio, websockets
from aiohttp import web
from .state import manifest
#async is strictly forbidden. syncronous event-driven is the way forward

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
        self.ws = None
        manifest.info('WSTamer __init__ end')

    def init_websocket(self, config):
        manifest.info('init_websocket start')
        addr = config.get('negative_address', {})
        ws_path = f"ws://{addr.get('host')}:{addr.get('port')}/ws"
        try:
            future = asyncio.run_coroutine_threadsafe(websockets.connect(ws_path), self.loop)
            self.ws = future.result()
            manifest.info('init_websocket success')
            return self.ws
            manifest.info('init_websocket end')
        except Exception as e:
            manifest.error(f'init_websocket failed: {e}')
        manifest.info('init_websocket end')

    def get_ws_closed_status(self, ws):
        manifest.info('Checking ws status...')
        if ws is None:
            return 'Default'
        try:
            manifest.info(f'ws as string: {str(ws)}')
            return 'True' if ws.state.name == 'CLOSED' else 'False'
        except Exception as e:
            manifest.error(f'Exception: {e}')
            return 'Default'

    def send_over_ws(self, ws, payload):
        manifest.info('send_over_ws start')
        if ws:
            asyncio.run_coroutine_threadsafe(ws.send(json.dumps(payload)), self.loop)
        manifest.info('send_over_ws end')

    def receive_over_ws(self, ws):
        manifest.info('receive_over_ws start')
        try:
            future = asyncio.run_coroutine_threadsafe(ws.recv(), self.loop)
            return ws, future.result()
        except:
            return None, None

    def accept_websocket_init(self, config, handler):
        addr = config.get('positive_address', {})
        host = addr.get('host')
        port = int(addr.get('port'))
        asyncio.run_coroutine_threadsafe(websockets.serve(handler, host, port).serve(handler, host, port), self.loop)

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
    original_init = cls.__init__
    def new_init(self, config=None, *args, **kwargs):
        original_init(self, config, *args, **kwargs)
        self.ws_tamer = WSTamer()
        self.ws = self.ws_tamer.init_websocket(config)
    cls.__init__ = new_init
    cls.sender = lambda self, ws, payload: self.ws_tamer.send_over_ws(ws, payload)
    cls.receiver = lambda self, websocket, message: self.ws_tamer.receive_over_ws(websocket)
    return cls


