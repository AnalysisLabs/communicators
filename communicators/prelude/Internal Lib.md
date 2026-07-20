# Internal Lib — Centralized Lazy Import Management Layer

**Status:** Design decision / deep dive
**Date:** 2026-06-21  
**Tags:** #python #metaprogramming #architecture #internal-imports #communicator-os

## Problem Summary

The `internal_lib` acts as a management layer for custom modules that live inside the library and must be importable by other parts of the same library. These modules are deliberately kept in separate semantic directories (`state/`, `connections/`, `node/`, etc.) to preserve separation of concerns.

Key constraints:
- Modules have ordered interdependencies (e.g. `manifest` is independent; `transponder` references `manifest`).
- Must avoid parasitic recursive import loops.
- Cross-module access must work cleanly at import time.
- The public surface must preserve clear namespacing (`manifest.info()`, `transponder.send_all()`, `transponder.connect_to()`, etc.) so the origin of each function/class remains obvious.
- Physical directory structure on disk **cannot** change.
- Future expansion may include classes.
- Strong preference for DRY and metaprogramming leverage.

Naive merging of module contents into a single flat namespace would solve cross-references but would destroy the desired `manifest.` vs `transponder.` separation and create API confusion.

## Recommended Solution

Use Python’s built-in **module-level `__getattr__`** (PEP 562, stable since 3.7) inside `internal_lib/__init__.py` to create a **lazy-loading gateway**.

This turns `internal_lib` into a single controlled import hub. Submodules are loaded on-demand in safe dependency order. No content merging is required. Namespacing stays intact. Circular import risk is eliminated for acyclic dependency graphs.

This is the modern, idiomatic, low-ceremony pattern for exactly this class of internal library architecture.

## Why This Works

- **Lazy loading eliminates loops**: When `transponder` is loaded and executes `from internal_lib import manifest`, the `__getattr__` handler brings in `manifest` cleanly before `transponder` finishes initializing.
- **Namespacing preserved**: After `from internal_lib import manifest, transponder` (or `import internal_lib as il`), you still write `manifest.xxx` and `transponder.yyy`. Origin clarity is maintained.
- **Directory structure untouched**: Files stay in `state/manifest.py`, `connections/transponder.py`, etc. `internal_lib/` is purely an import-management shim.
- **Cross-references become safe**: All internal modules standardize on importing through the hub (`from internal_lib import manifest`). The hub enforces ordering implicitly.
- **Future-proof for classes**: Classes defined in those modules are simply attributes on the loaded module objects.
- **DRY & metaprogrammable**: One declarative registry controls everything. Easy to later add proxies, logging, validation, or runtime injection.
- **`from internal_lib import *` friendly**: Works cleanly when `__all__` is defined.

## Implementation (Copy-Paste Ready)

Create / replace `internal_lib/__init__.py` with the following:

```python
"""
Internal Lib — Lazy Import Gateway
Central management layer for cross-referenced internal modules.
All internal cross-imports should go through this module.
"""

import importlib
from typing import Any

# ============================================================
# DECLARATIVE REGISTRY
# Add new internal modules here. Key = logical name exposed
# via internal_lib. Value = full import path from library root.
# ============================================================
INTERNAL_MODULES: dict[str, str] = {
    "manifest":   "your_library.state.manifest",
    "transponder": "your_library.connections.transponder",
    # "node_foo":   "your_library.node.something",
    # Add more as the architecture grows...
}

# Cache for already-loaded modules (populated lazily)
_LOADED: dict[str, Any] = {}

def __getattr__(name: str) -> Any:
    """Lazy attribute access — the heart of the management layer."""
    if name in INTERNAL_MODULES:
        if name not in _LOADED:
            module_path = INTERNAL_MODULES[name]
            mod = importlib.import_module(module_path)
            _LOADED[name] = mod
            # === METAPROGRAMMING HOOK POINT ===
            # Example: _inject_utilities(mod) or wrap with proxy
            # Add any runtime decoration / validation here later.
        return _LOADED[name]

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

def __dir__() -> list[str]:
    """Support tab-completion, dir(), and introspection."""
    return sorted(set(globals().keys()) | set(INTERNAL_MODULES.keys()))

__all__ = list(INTERNAL_MODULES.keys())