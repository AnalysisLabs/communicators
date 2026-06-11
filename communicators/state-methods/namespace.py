class BaseNamespace:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._data = SimpleNamespace()
                    cls._instance._lock = threading.RLock()
                    cls._instance.initialize_states()
        return cls._instance

    def initialize_states(self):
        # Hook for subclasses to define states like ideal, real, temporary
        pass

    def __getattr__(self, name: str) -> Any:
        with self._lock:
            return getattr(self._data, name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name in ('_data', '_lock', '_instance'):
            super().__setattr__(name, value)
            return
        with self._lock:
            setattr(self._data, name, value)

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
                if not hasattr(ns, p): setattr(ns, p, SimpleNamespace())
            _namespaces[name] = getattr(ns, name.split('/')[-1])

def populate_namespace(name: str, data: dict[str, Any]) -> None:
    with _ns_lock:
        ns = _namespaces[name]
        if ns is None:
            initialize_namespace(name)
        def _rec_set(d: dict[str, Any]) -> SimpleNamespace:
            return SimpleNamespace(**{k: _rec_set(v) if isinstance(v, dict) else v for k, v in d.items()})
        for k, v in data.items():
            setattr(ns, k, _rec_set(v) if isinstance(v, dict) else v)

def _start_ns_server():
    class NSHandler(BaseHTTPRequestHandler):
        def do_POST(self):
            data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            if data.get('action') == 'populate_namespace':
                populate_namespace(data['substance'], data.get('namespace'))
                self.wfile.write('populated ✓'.encode('utf-8'))
            elif data.get('action') == 'snapshot_namespace':
                snapshot_namespace(data['substance'])
                self.wfile.write(f"namespace saved to {data['substance']}".encode())
    server = HTTPServer(('localhost', 8765), NSHandler)
    server.serve_forever()

def port_in_use(host, port):
    return True
    try:
        httpx.head(f'http://{host}:{port}', timeout=0.2)
        return True
    except httpx.RequestError:
        return False

if port_in_use('localhost', 8765):
    os.system('kill -9 $(lsof -t -i:8765) 2>/dev/null || true')

_start_ns_server()


