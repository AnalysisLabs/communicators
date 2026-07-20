import sys, os
from pathlib import Path
COMMUNICATORS_ROOT = "/home/guatamap/Analysis Labs/Dev Tools/com-branches/orchestrated-1/communicators"
sys.path.insert(0, COMMUNICATORS_ROOT)
from prelude import*


# ==================== USER PROGRAM ====================
class BaseNamespace:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._data = {}
                    cls._instance._lock = threading.RLock()
                    cls._instance.initialize_states()
        return cls._instance

    def initialize_states(self):
        # Hook for subclasses to define states like ideal, real, temporary
        pass

    def __getattr__(self, name: str) -> Any:
        with self._lock:
            return self._data.get(name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name in ('_data', '_lock', '_instance'):
            super().__setattr__(name, value)
            return
        with self._lock:
            self._data[name] = value

    def __contains__(self, name: str) -> bool:
        with self._lock:
            return hasattr(self._data, name)

    def debug(self) -> None:
        keys = [k for k in dir(self._data) if not k.startswith('_')]
        print('🧠 Namespace contains:', sorted(keys))

    def snapshot_namespace(self, path: str) -> None:
        data = json.dumps({k: getattr(self._data, k) for k in dir(self._data) if not k.startswith('_')}).encode()
        with open(path, 'ab') as f: f.write(data)

_namespaces: Dict[str, BaseNamespace] = {}
_ns_lock = threading.Lock()

# API needs these fields(action, substance, namespace)

def initialize_namespace(*names: str) -> None:
    with _ns_lock:
        if BaseNamespace._instance is None:
            BaseNamespace()
        if name not in _namespaces:
            ns = BaseNamespace()
            for p in name.split('/'):
                if not hasattr(ns, p): setattr(ns, p, {})
            _namespaces[name] = getattr(ns, name.split('/')[-1])

def populate_namespace(name: str, data: dict[str, Any]) -> None:
    with _ns_lock:
        ns = _namespaces[name]
        if ns is None:
            initialize_namespace(name)
        for k, v in data.items():
            ns[k] = v

def _start_ns_server():
    """Start the namespace server using transponder instead of HTTPServer."""
    try:
        # Import here or at top: import transponder
        transponder.persistent_server('localhost', 8765)
    except Exception as e:
        Manifest.error(f"Failed to start namespace server: {e}")

def port_in_use(host: str, port: int, timeout: float = 0.3) -> bool:
    """Check if something is listening on (host, port) using a raw TCP connect."""
    if host == 'localhost':
        host = '127.0.0.1'

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)

    try:
        result = sock.connect_ex((host, port))
        return result == 0  # 0 means connection succeeded → something is listening
    except Exception:
        return False
    finally:
        sock.close()


def kill_port(host: str = 'localhost', port: int = 8765) -> None:
    """Aggressively kill anything listening on the port (Linux/macOS)."""
    if host == 'localhost':
        host = '127.0.0.1'

    print(f"🔪 Checking/killing port {port}...")
    os.system(f'lsof -t -i:{port} | xargs kill -9 2>/dev/null || true')
    time.sleep(0.4)  # give OS time to release the socket

if port_in_use('localhost', 8765):
    kill_port('localhost', 8765)

_start_ns_server()
