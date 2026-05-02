from prelude.standard import*
from prelude.internal_lib import*

_namespaces: Dict[str, BaseNamespace] = {}
_ns_lock = threading.Lock()

def initialize_namespace(*names: str) -> None:
    with _ns_lock:
        for name in names:
            if name not in _namespaces:
                class NS(BaseNamespace):
                    def initialize_states(self) -> None:
                        pass  # Hook preserved
                _namespaces[name] = NS()

def populate_namespace(name: str, data: dict[str, Any]) -> None:
    with _ns_lock:
        ns = _namespaces[name]
        def _rec_set(d: dict[str, Any]) -> SimpleNamespace:
            return SimpleNamespace(**{k: _rec_set(v) if isinstance(v, dict) else v for k, v in d.items()})
        for k, v in data.items():
            setattr(ns, k, _rec_set(v) if isinstance(v, dict) else v)

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

# Example subclass in another module.
class OrchestrationStates(BaseNamespace):
    def initialize_states(self):
        self.ideal_state = None  # e.g., loaded from YAML
        self.real_state = {}     # e.g., discovered runtime state
        self.temporary_state = SimpleNamespace()  # ephemeral data
