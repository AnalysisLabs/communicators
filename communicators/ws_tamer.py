import json, tracemalloc, threading
import websockets.sync.client as ws_client
import websockets.sync.server as ws_server
from .state import manifest

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

# Or class
def ws_bridge(self):
    pass


