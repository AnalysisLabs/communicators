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
    class NSHandler(BaseHTTPRequestHandler):
        def do_POST(self):
            data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            if 'in_namespace' in data or 'to_namespace' in data:
                ref = data.get('in_namespace') or data.get('to_namespace')
                obj = data.get('object_program') or data.get(list(data.keys())[-1])
            if obj is not None:
                if ref:
                    populate_namespace(ref, obj)
                else:
                    replace_namespace(obj)
            else:
                populate_namespace(data.get('substance'), data.get('namespace'))
            self.wfile.write(b'ok')

        def do_GET(self):
            data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            ref = data.get('in_namespace') or data.get('from_namespace')
            if ref:
                val = pull_value(ref)
                self.wfile.write(json.dumps(val).encode())

        def do_HEAD(self):
            self.send_response(200)
            self.end_headers()
    try:
        server = HTTPServer(('localhost', 8765), NSHandler)
    except OSError as exc:
        if exc.errno == 98:
            os.system('kill -9 $(lsof -t -i:8765) 2>/dev/null || true')
            time.sleep(0.4)
            try:
                server = HTTPServer(('localhost', 8765), NSHandler)
            except Exception as e:
                print(e)
    server.serve_forever()

def port_in_use(host, port):
    try:
        httpx.head(f'http://{host}:{port}', timeout=0.2)
        return True
    except httpx.RequestError:
        return False

if port_in_use('localhost', 8765):
    os.system('kill -9 $(lsof -t -i:8765) 2>/dev/null || true')

_start_ns_server()
