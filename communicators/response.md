### Shared core (almost identical to the previous helper)


from types import ModuleType
import importlib.util
import sys
from pathlib import Path
from importlib.abc import SourceLoader

def _load(name: str, loader, origin: str) -> ModuleType:
    if name in sys.modules:
        return sys.modules[name]

    spec = importlib.util.spec_from_loader(name, loader, origin=origin)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module          # must happen before exec
    try:
        spec.loader.exec_module(module)
    except Exception:
        del sys.modules[name]           # clean up on failure
        raise
    return module


### Path version (previous case, now thinner)

def from_path(path: str | Path, name: str | None = None) -> ModuleType:
    path = Path(path).resolve()
    if name is None:
        name = path.stem
    return _load(name, None, str(path))   # None → uses file-based loader via origin
    # or more explicitly:
    # loader = importlib.machinery.SourceFileLoader(name, str(path))
    # return _load(name, loader, str(path))


### Code-blob version (new case)

class StringLoader(SourceLoader):
    def __init__(self, source: str):
        self.source = source

    def get_data(self, path: str) -> bytes:
        return self.source.encode("utf-8")

    def get_filename(self, fullname: str) -> str:
        return f"<string:{fullname}>"

def from_code(source: str, name: str) -> ModuleType:
    loader = StringLoader(source)
    return _load(name, loader, f"<string:{name}>")


