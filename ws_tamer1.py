import json, tracemalloc, threading
import websockets.sync.client as ws_client
import websockets.sync.server as ws_server
from .state import manifest
#async is strictly forbidden. syncronous event-driven is the way forward

"""
Directive to AI about how to understank the following program:

Background: ws_tamer will act like a library within a library while it is getting built to act as auxilary to core.py for strictly ws management, it should also be the sort of thing an api use could use directly ifs they don't like how hard ws are to work with, but don't want the full package offered by core.py. At this point I am mentally tracing the control flow to make sure it is conceptually complete before running tests in terminal.

Note: This is version 1. In version one, reconnection and redundant connection between any two servers are strictly forbidden. While postive and negatice coms need thier own listener on its own thread, those thread must be recycled, an dif such fails, that should result in a manifest like, "Attempting to send on closed WS" and no attempt to restore the ws. To clarify, a ws is NEVER supposed to be closed, except when the entire server system is shut down.
"""

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

def init_websocket(self, config):
    addr = config.get('negative_address', {})
    ws_path = f"ws://{addr.get('host')}:{addr.get('port')}/ws"
    try:
        ws = ws_client.connect(ws_path, ping_interval=None, ping_timeout=None, close_timeout=None, max_size=None)
        manifest.info(f'WS connected to {ws_path}')
        return ws
    except Exception as e:
        manifest.error(f'Connection error: {e}')

# a.k.a connection manager
def ws_tank(self):
    """
    Directive to AI about how to understank the following code block:
    This is for holding onto, persisting and listening to the ws for messages.
    While this will have to do some of the listening because of how ws works,
    it will forward everything to receive_over_ws to promote optimal sepparation of concern.
    """
    pass

def accept_websocket_init(self, config, handler):
    addr = config.get('positive_address', {})
    host = addr.get('host')
    port = int(addr.get('port'))
    return ws_server.serve(handler, host, port)

def send_over_ws(self, ws, payload):
    if ws and get_ws_closed_status(ws) != 'True':
        ws.send(json.dumps(payload))
        manifest.info(f'Sending payload: {payload}')
    else:
        manifest.error('Attempting to send on closed WS')

def receive_over_ws(self, ws):
    try:
        return ws.recv()
    except Exception as e:
        manifest.error(f'Listen error: {e}')
        if get_ws_closed_status(ws) == 'True':
            manifest.error('WS close unexpectedly')

def close(self):
    if self.ws:
        self.ws.close()
        self.ws = None

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
def ws_bridge(self):
    pass


