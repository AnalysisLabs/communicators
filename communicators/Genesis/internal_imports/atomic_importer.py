from types import ModuleType
import importlib.util
import sys
from pathlib import Path
from importlib.abc import SourceLoader
from typing import Any

# === Start Here ===

# ---------------------------------------------------------------------------
# Shared core
# ---------------------------------------------------------------------------

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


def _extract(module: ModuleType, items: tuple) -> tuple[Any, ...]:
    """
    items may contain:
      - "name"              → returns module.name
      - ("name", "alias")   → returns module.name  (caller binds it to alias)
    """
    result = []
    for item in items:
        if isinstance(item, tuple):
            name, _alias = item          # alias is only used by the caller
            result.append(getattr(module, name))
        else:
            result.append(getattr(module, item))
    return tuple(result)


# ---------------------------------------------------------------------------
# Path version
# ---------------------------------------------------------------------------

def from_path(path: str | Path, name: str | None = None) -> ModuleType:
    """Equivalent to: import <module>  (from a real filesystem path)"""
    path = Path(path).resolve()
    if name is None:
        name = path.stem
    source = path.read_text(encoding="utf-8")
    return from_code(source, name, filename=str(path))


def from_path_import(path: str | Path, *items: str | tuple[str, str]) -> tuple[Any, ...]:
    """
    Equivalent to: from <module> import a, b as c, ...

    Examples
    --------
    a, b = from_path_import("math_helpers.py", "a", "b")
    x, y = from_path_import("math_helpers.py", ("a", "x"), ("b", "y"))
    """
    mod = from_path(path)
    return _extract(mod, items)


# ---------------------------------------------------------------------------
# Code-blob version
# ---------------------------------------------------------------------------

class StringLoader(SourceLoader):
    def __init__(self, source: str, filename: str):
        self.source = source
        self.filename = filename

    def get_data(self, path: str) -> bytes:
        return self.source.encode("utf-8")

    def get_filename(self, fullname: str) -> str:
        return self.filename


def from_code(source: str, name: str, filename: str | None = None) -> ModuleType:
    """Equivalent to: import <module>  (from a string)"""
    if filename is None:
        filename = f"<string:{name}>"
    loader = StringLoader(source, filename)
    return _load(name, loader, filename)


def from_code_import(
    source: str,
    name: str,
    *items: str | tuple[str, str],
    filename: str | None = None,
) -> tuple[Any, ...]:
    """
    Equivalent to: from <module> import a, b as c, ...  (from a string)

    Examples
    --------
    a, b = from_code_import(src, "mymod", "a", "b")
    x, y = from_code_import(src, "mymod", ("a", "x"), ("b", "y"))
    """
    mod = from_code(source, name, filename=filename)
    return _extract(mod, items)
