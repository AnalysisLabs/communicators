# Node Methods — Pre-defined `to_/from_`, N/P Resolution, Load/Core

**Specialized Design Document for `communicators/node-methods/`**

## Purpose
The `node-methods` package defines the **standardized, versioned interface** that every concrete node implementation (Python, Bash, C++, external binary) must satisfy. It is the contract layer that keeps nodes "ignorant" of the larger graph while giving the orchestrator uniform control, liveness checking, and manifest participation.

This directly implements the **"Standardized Node Interface"** and **"Separation of methods from instances"** architectural decisions.

## Core Sub-Modules

### 1. `to_from.py` — Serialization & State Transfer
Provides canonical `to_dict()` / `from_dict()` and `to_yaml()` / `from_yaml()` methods for every node type.

```python
from communicators.prelude import NodeID
from dataclasses import dataclass, asdict
import yaml

@dataclass
class NodeSpec:
    id: NodeID
    executable: str
    args: list[str]
    env: dict[str, str]
    cwd: str
    role: Literal["primary", "auxiliary"]
    health_check: dict  # port, path, or unix_socket

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "NodeSpec":
        return cls(**d)

    def to_yaml(self) -> str:
        return yaml.safe_dump(self.to_dict())

    @classmethod
    def from_yaml(cls, s: str) -> "NodeSpec":
        return cls.from_dict(yaml.safe_load(s))
```

These methods are used by:
- YAML loader in `state-methods`
- IR (intermediate representation) in `ffiir`
- Process Registry when persisting state across orchestrator restarts

### 2. `resolution.py` — Type of Node Resolution
Determines at runtime what kind of node we are dealing with and which concrete implementation to load.

```python
from enum import Enum

class NodeType(Enum):
    PYTHON_ENTRYPOINT = "python"
    BASH_SCRIPT = "bash"
    BINARY = "binary"
    DOCKER_CONTAINER = "docker"   # future
    LAB_HARDWARE = "hardware"     # future

def resolve_node_type(spec: NodeSpec) -> NodeType:
    if spec.executable.endswith(".py"):
        return NodeType.PYTHON_ENTRYPOINT
    if spec.executable.endswith(".sh"):
        return NodeType.BASH_SCRIPT
    ...
```

Resolution also handles **N/P (Node/Primary)** classification:
- `N` = regular worker/auxiliary node
- `P` = primary / root-of-subtree node that may own child auxiliaries

This classification drives hierarchy decisions in `graph-methods`.

### 3. `load_core.py` — The Ignorant Node Contract
The heart of the module. Every node, regardless of language, is wrapped so that it only needs to:
1. Read its configuration from environment variables / stdin (JSON or YAML)
2. Perform its single task
3. Stream structured lines to the inherited manifest FD
4. Exit with a conventional code (0 = success, 1-99 = transient, 100+ = permanent)

```python
# node-methods/load_core.py
from communicators.prelude import ManifestLogger, NodeID, ensure_manifest_fd

def load_node(spec: NodeSpec) -> None:
    log = ManifestLogger(f"node-{spec.id}")
    ensure_manifest_fd()  # inherits or opens the shared stream

    # Node is now "ignorant" — it does not know about parents, siblings, or the graph
    try:
        if spec.role == "primary":
            run_primary_logic(spec, log)
        else:
            run_auxiliary_logic(spec, log)
    except Exception as e:
        # All errors are caught here and turned into manifest lines + conventional exit code
        log.error("node-failed", error=str(e), category=classify_error(e))
        sys.exit(1 if is_transient(e) else 100)
```

## Pre-defined Methods Summary

| Method Family | Purpose | Used By |
|---------------|---------|---------|
| `to_/from_dict` | State transfer & IR | state-methods, ffiir, control-script |
| `to_/from_yaml` | Human & git-friendly persistence | YAML desired-state files |
| `resolve_node_type` | Dispatch to correct launcher | control-layer-methods |
| `load_node` | The universal entry point executed by every child | Launcher Executor |
| `classify_error` | Maps raw exception → error axes (see error handling doc) | self-healing in Lifecycle Controller |

## Design Decisions

- **No inheritance for node logic** — Nodes are plain functions or small scripts. The "class" is only the `NodeSpec` dataclass. This keeps node code trivial to test in isolation.
- **Versioned protocol** — Every `NodeSpec` carries a `protocol_version: int`. Future changes (e.g., adding structured health JSON) are gated behind version bumps without breaking existing nodes.
- **Zero node-side dependencies** — A Bash node only needs `cat`, `date`, and the inherited manifest FD. Python nodes get the prelude but are encouraged to stay under 200 LOC.

## Example Node Implementation (Python)
```python
#!/usr/bin/env python3
from communicators.node_methods.load_core import load_node
from communicators.prelude import NodeSpec

spec = NodeSpec.from_env()  # or from YAML
load_node(spec)  # never returns — exits with conventional code
```

The actual work lives in `run_primary_logic` / `run_auxiliary_logic` which the node author overrides by providing a different entry point (still loaded via the same `load_core`).

## Benefits
- Complete separation: node authors never import graph or state logic.
- Uniform observability: every node, no matter how written, produces identical manifest format.
- Self-healing ready: `classify_error` + conventional exit codes feed directly into the policy table in `state-methods`.

## Open Questions
- Should we add a `node-methods.health` sub-module that optionally exposes a Unix socket for richer application-level heartbeats (layered on top of `kill -0`)?
- Support for "node bundles" (a single Python file that registers multiple logical nodes) — useful for lab equipment drivers.
