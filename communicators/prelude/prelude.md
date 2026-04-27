# Prelude — Collect Imports & Foundational Setup

**Specialized Design Document for `communicators/prelude/`**

## Purpose
The `prelude` module serves as the single point of import collection and foundational bootstrapping for the entire [[Communicators]] library. It eliminates repetitive `import` boilerplate across all other modules (node-methods, graph-methods, state-methods, etc.) while establishing the core runtime contracts, type aliases, constants, and early initialization logic required by the declarative orchestration system.

This module embodies the "Thin Bootstrap / Launcher Layer" principle: keep the entry points minimal, predictable, and focused on wiring rather than business logic.

## Core Responsibilities

### 1. Centralized Import Collection
All third-party and standard-library dependencies are declared once here and re-exported with clean aliases. This guarantees:
- Consistent dependency versions and feature flags across the graph.
- Easy auditing of the dependency surface (no hidden `import` statements deep in node code).
- Support for optional dependencies (e.g., `pyyaml`, `psutil`, `grpcio`) via lazy loading or `try/except` guards.

**Key imports managed:**
- `yaml` (PyYAML) — for desired-state loading
- `subprocess`, `os`, `signal`, `pathlib`, `dataclasses`, `typing` (extensive use of `Protocol`, `TypeVar`, `Generic`)
- `threading`, `queue`, `concurrent.futures` — for reconciliation loops and health checkers
- `logging` + custom `ManifestLogger`
- `psutil` (optional) — for resource metrics
- `socket`, `select` — for Unix-domain socket node communication

### 2. Type Aliases & Protocol Definitions
The prelude defines the fundamental vocabulary used everywhere else:
```python
from typing import Protocol, runtime_checkable, TypeAlias, Literal

NodeID: TypeAlias = str
GraphID: TypeAlias = str
PID: TypeAlias = int
ManifestLine: TypeAlias = str

@runtime_checkable
class NodeLike(Protocol):
    id: NodeID
    def is_alive(self) -> bool: ...
    def start(self) -> None: ...
    def stop(self, graceful: bool = True) -> None: ...

@runtime_checkable
class GraphLike(Protocol):
    id: GraphID
    nodes: dict[NodeID, NodeLike]
    def reconcile(self) -> None: ...
```

### 3. Constants & Environment Contracts
```python
DEFAULT_MANIFEST_PATH: Path = Path("/var/log/communicators/manifest.log")
DEFAULT_SOCKET_DIR: Path = Path("/run/communicators")
DEFAULT_HEALTH_INTERVAL_SEC: float = 2.0
SIGNAL_MAP: dict[int, str] = {signal.SIGTERM: "SIGTERM", signal.SIGHUP: "SIGHUP", ...}
```

Environment variables that the prelude guarantees are always present for child nodes:
- `COMMUNICATORS_MANIFEST_FD` — file descriptor for the shared manifest stream
- `COMMUNICATORS_NODE_ID`
- `COMMUNICATORS_GRAPH_ID`
- `COMMUNICATORS_PARENT_PID`

### 4. Early Initialization & Validation
On import (or explicit `prelude.initialize()`), the module:
- Creates required runtime directories with correct permissions
- Validates that the process is running inside a proper cgroup / resource-limited environment (when applicable)
- Installs a global `ManifestLogger` singleton that every other module will use
- Seeds the random number generator for backoff jitter (used by self-healing)

## Design Decisions Specific to Prelude

| Decision | Rationale | Trade-off |
|----------|-----------|-----------|
| Re-export everything under `from communicators.prelude import *` | Node and graph code stays tiny and readable | Slight namespace pollution (mitigated by `__all__`) |
| Lazy import of heavy deps (`grpcio`, `docker`) | Orchestrator starts fast even if optional features unused | Minor runtime cost on first use |
| Manifest FD inheritance via `os.dup2` at launch time | Guarantees every child process writes to the same chronological stream without buffering surprises | Requires careful fd management in Launcher Executor |
| No user-configurable prelude (everything via YAML or env) | Keeps the "ignorant node" contract strict | Advanced users must subclass or monkey-patch (documented escape hatch) |

## Integration Points

- **Consumed by**: every other module (`from communicators.prelude import ...`)
- **Produces**: the `ManifestLogger` singleton used by `Manifest Integrator`
- **Called by**: `control-script` during bootstrap and `control-layer-methods` during reconciliation

## Minimal Example Usage (inside any other module)
```python
from communicators.prelude import (
    NodeID, ManifestLogger, DEFAULT_MANIFEST_PATH,
    NodeLike, ensure_runtime_dirs
)

ensure_runtime_dirs()
log = ManifestLogger("node-methods")
log.info("Node definition loaded", node_id="primary-01")
```

## Open Questions / Future Work
- Should prelude expose a `configure_logging(manifest_path: Path)` hook for tests?
- Add `importlib.metadata` version reporting so the manifest always records the exact library version at startup.
- Consider a `prelude.strict_mode()` that disables all optional features for ultra-minimal deployments (e.g., embedded lab hardware).

This prelude ensures that the rest of the library can focus purely on orchestration logic while every line that ever executes is timestamped, prefixed, and collated into the single source-of-truth manifest.
