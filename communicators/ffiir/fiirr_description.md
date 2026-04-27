# Foreign Function Interface Intermediate Representation (FFIIR / ffiir)

**Specialized Design Document for `communicators/ffiir/`**

## Purpose
`ffiir` (Foreign Function Interface Intermediate Representation) is the **decoupling and validation layer** between the human friendly API and human-written YAML desired state from the executable runtime structures used by the control plane and graph methods.

It solves the classic problem: "How do we let users write clean, nested, high-level YAML while giving the orchestrator fast, typed, validated objects that contain no YAML-specific logic?"

It directly supports:
- **YAML loading methods** (auto vs static host/port/socket_path)
- **Intermediate representation (IR) methods**
- **Separation of methods from instances**
- Future FFI to other languages or external systems (lab hardware APIs, ROS, etc.)

## Core Concept

**IR = Normalized, Validated, Executable Form of the Desired State**

The YAML is allowed to be user-friendly and sparse. The IR is strict, complete, and ready for topological sorting, dependency resolution, and code generation (if ever needed).

## Directory Structure & Modules

```
ffiir/
├── __init__.py
├── schema.py          # Pydantic or dataclasses + validation
├── normalizer.py      # defaults, auto host/port/socket_path, nesting flattening
├── validator.py       # cycle detection, type resolution, policy completeness
├── ir_builder.py      # main entry: yaml → IR
└── ir_types.py        # the actual IR dataclasses (NodeIR, GraphIR, ConnectionIR, ...)
```

## The IR Data Model (key classes)

```python
@dataclass(frozen=True)
class NodeIR:
    id: NodeID
    type: NodeType
    executable: str
    args: tuple[str, ...]
    env: Mapping[str, str]
    cwd: Path
    role: Role
    health_check: HealthCheckIR
    restart_policy: RestartPolicyIR
    parent_id: NodeID | None
    children: tuple[NodeID, ...]
    connection: ConnectionIR | None   # unix_socket or ws_tamer
    protocol_version: int = 1

@dataclass(frozen=True)
class GraphIR:
    id: GraphID
    nodes: Mapping[NodeID, NodeIR]
    root_nodes: tuple[NodeID, ...]
    error_policies: ErrorPolicyTable
    manifest_path: Path
```

## Key Transformations Performed by ffiir

1. **Auto-defaulting**
   ```yaml
   # user writes
   - id: sensor-01
     executable: ./read-sensor.sh
   ```
   becomes in IR:
   ```python
   NodeIR(
       id="sensor-01",
       health_check=HealthCheckIR(unix_socket=Path("/run/communicators/sensor-01.sock")),
       connection=ConnectionIR(unix_socket=...),
       ...
   )
   ```

2. **Static override support**
   If user specifies `host: 192.168.1.42` or `port: 5555` or `socket_path: /custom/path.sock`, those values are preserved exactly.

3. **Nesting flattening**
   YAML can use nested `children:` blocks for readability. The IR builder produces a flat `nodes` dict with explicit `parent_id` / `children` references.

4. **Policy completion**
   Any missing `error_policies` section is filled with safe defaults that guarantee self-healing.

## Validation Guarantees

- No cycles (topological sort succeeds)
- All referenced executables exist and are executable (or marked as external)
- Every node has a resolvable `NodeType`
- Every primary has at least one connection method defined
- Error policy table covers all five axes for every severity level
- No duplicate NodeIDs

Any violation produces a **quasi all-natural language error** (via `state-methods.explain_error`) that is written to stdout and the manifest before the process exits.

## Usage Example (inside control-script)

```python
from communicators.ffiir import build_ir
from communicators.state_methods import IdealState

ideal = IdealState.from_yaml("lab.yaml")
ir = build_ir(ideal)          # <-- the only place YAML touches the runtime

# From here on, only IR is used
registry = ProcessRegistry.from_ir(ir)
graph = Graph.from_ir(ir)
...
```

## Design Decisions

- **IR is immutable and hashable** — Safe to cache, pass between threads, or even serialize to disk for crash recovery.
- **One IR per graph** — Multiple graphs = multiple IR objects. Keeps memory usage predictable.
- **No business logic in ffiir** — It only transforms and validates. All scheduling, healing, and execution decisions live in `graph-methods`, `state-methods`, and `control-layer-methods`.
- **Extensible for FFI** — The `NodeIR` already contains a `foreign_interface` field (optional) for future integration with C libraries, ROS topics, or proprietary lab equipment protocols.

## Benefits
- YAML can evolve independently of the runtime (new keys are ignored until explicitly added to the normalizer).
- The orchestrator never parses YAML at runtime after startup — huge reliability win.
- Clear separation: user sees friendly YAML; machine sees strict IR.

## Open Questions
- Should ffiir support JSON Schema export so external tools (VS Code, web UIs) can provide autocomplete for the YAML?
- Versioning strategy for IR itself (when we add new required fields in v2)?
- Ability to "diff" two IRs and produce a minimal reconciliation plan (useful for hot-reload)?
