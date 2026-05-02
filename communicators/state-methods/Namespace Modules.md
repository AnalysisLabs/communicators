

# Namespace Modules — The Shared State Layer

**General Pattern for Python-Dominated Libraries**

## Purpose

A **namespace module** provides a single, independent, long-lived object that holds all shared configuration and runtime state for an entire application or library.  

It is the global  place where state lives. All other modules remain mostly stateless and simply import the namespace when they need data. This creates clean separation between *logic* and *state*, making the system easier to test, reason about, scale, and evolve.

This pattern is especially valuable when:
- You want a tiny orchestrator that stays under ~30–50 lines
- You are building for future scale (hyperscale mindset)
- You want modules to be reusable and testable without hidden global state
- You are moving from “everything mixed together” to proper architectural layers

## Core Concept

Instead of each module carrying its own state or using scattered globals, you create **one central namespace** that acts as the application’s shared memory / blackboard.

- The namespace is **initialized once** early in the program (usually by a dedicated `initialize` step).
- After initialization, every module can safely read (and selectively write) to it.
- The namespace is **independent** — no module owns it, and it outlives any individual module.

## Three-Layer Mental Model

1. **Namespace Layer** — The single source of truth (config + runtime state)
2. **Module Layer** — Stateless (or mostly stateless) logic that imports the namespace
3. **Orchestrator Layer** — Tiny top-level script that runs the pipeline in order: `initialize → modules → ...`

## Basic Implementation

### 1. The Namespace Itself

```python
# core/namespace.py
from types import SimpleNamespace
import threading
from typing import Any

class AppNamespace:
    """Single shared application state object."""
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._data = SimpleNamespace()
                    cls._instance._lock = threading.RLock()
        return cls._instance

    def __getattr__(self, name: str) -> Any:
        with self._lock:
            return getattr(self._data, name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name in ("_data", "_lock", "_instance"):
            super().__setattr__(name, value)
            return
        with self._lock:
            setattr(self._data, name, value)

    def __contains__(self, name: str) -> bool:
        with self._lock:
            return hasattr(self._data, name)

    def debug(self) -> None:
        keys = [k for k in dir(self._data) if not k.startswith("_")]
        print("🧠 Namespace contains:", sorted(keys))


# Public singleton — import this everywhere
ns = AppNamespace()
```

### 2. The Initialize Step (only place that loads config)

```python
# modules/initialize.py
import yaml
from pathlib import Path
from core.namespace import ns

def initialize(config_dir: str = "config") -> None:
    """Run once at startup. Populates the shared namespace."""
    for yaml_file in Path(config_dir).glob("**/*.yaml"):
        data = yaml.safe_load(yaml_file.read_text()) or {}
        for key, value in data.items():
            if isinstance(value, dict):
                value = SimpleNamespace(**value)
            setattr(ns, key, value)
    
    print("✅ Namespace initialized")
    ns.debug()
```

### 3. Example Stateless Module

```python
# modules/auth.py
from core.namespace import ns

def create_session(username: str):
    if "sessions" not in ns:
        ns.sessions = {}
    ns.sessions[username] = {"active": True}
    return ns.sessions[username]
```

### 4. Tiny Orchestrator

```python
# main.py
from modules.initialize import initialize
from modules.auth import create_session
# ... other modules

def run():
    initialize()
    session = create_session("user123")
    # continue pipeline...

if __name__ == "__main__":
    run()
```

## Design Decisions

- **Singleton with thread-safety** — One object for the entire process lifetime. Safe for multi-threaded or future async use.
- **SimpleNamespace under the hood** — Easy attribute access (`ns.site.name`) while still allowing dynamic keys.
- **Initialize once, read everywhere** — The only place that does file I/O or heavy setup.
- **Modules stay stateless** — Logic becomes pure functions that read from the namespace when needed.
- **Explicit over implicit** — State is visible and debuggable instead of hidden inside modules.

## Evolution Paths (Start Simple, Grow When Needed)

- Add **pydantic** models for validation and typed access
- Support **environment overrides** (YAML + env vars)
- Add **contextvars** for per-request / per-task state
- Replace the singleton with a proper **dependency-injection container** later
- Make parts of the namespace **hot-reloadable** during development
- Add **manifest / audit logging** of every state change (useful for self-healing systems)

## Benefits

- **Dramatically cleaner modules** — No more hidden globals or passing state through 8 functions.
- **Easy to test** — Inject a test namespace or mock it.
- **Scales with the project** — Works for 6k lines or 60k+ lines.
- **Future-proof for hyperscale** — Adding workers, caching, or distributed state becomes localized changes instead of widespread rewrites.
- **Observability** — One place to inspect everything with `ns.debug()` or logging.

## When to Use This Pattern

Use a namespace module when you want:
- A small, clear orchestrator
- Modules that are easy to reason about in isolation
- Shared configuration that multiple parts of the system need
- The ability to evolve toward more advanced state management without rewriting everything

Avoid it for:
- Very small scripts (overkill)
- Pure functional pipelines with no shared state at all
- Situations where you need strict per-request isolation (use context vars instead)

## Open Questions / Future Extensions

- Should the namespace support **predicted future state** simulation before applying changes?
- How to handle **multi-process** or **distributed** scenarios cleanly?
- Should we add **versioning** or **migration** support for the namespace schema over time?
