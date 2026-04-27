# Graph Methods — Elementary Node Structure, Load Spreading, Connection Management

**Specialized Design Document for `communicators/graph-methods/`**

## Purpose
`graph-methods` is responsible for modeling, validating, and operating on the **entire declared graph** of nodes. It turns a flat YAML list of nodes into a living, queryable, dependency-aware structure that the reconciliation loop can drive toward the desired state.

It implements the **"Clear Graph vs. Node Separation"** and **"Hierarchy / Tree Manager"** abstractions.

## Core Sub-Modules

### 1. `elementary.py` — Genealogy & Node Identity
Every node instance carries its full ancestry:

```python
@dataclass
class NodeInstance:
    spec: NodeSpec
    pid: PID | None = None
    parent_id: NodeID | None = None
    children: list[NodeID] = field(default_factory=list)
    start_time: datetime | None = None
    restart_count: int = 0

    @property
    def genealogy(self) -> list[NodeID]:
        """Returns ordered list from root primary down to this node."""
        ...
```

This enables operations such as:
- "Restart the entire subtree under primary-03"
- "Only start auxiliaries after their primary reports healthy"

### 2. `load_spreading.py` — Node Instance Spawning & Parallelism
Responsible for turning declarative `NodeSpec` entries into live `NodeInstance` objects while respecting:
- Dependency ordering (topological sort)
- Parallelism limits (max concurrent spawns per subtree)
- Resource budgets (CPU, memory, file descriptors)

```python
def spread_load(graph: Graph, max_parallel: int = 8) -> list[NodeInstance]:
    """Yields nodes in safe launch order, respecting parallelism caps."""
    topo = topological_sort(graph)
    batches = chunk_by_parallelism(topo, max_parallel)
    for batch in batches:
        yield from launch_batch(batch)  # uses Launcher Executor
```

### 3. `connections.py` — Unix Socket & WS-Tamer
Two built-in connection primitives:

- **unix_socket**: Low-latency, local, file-descriptor passing capable. Used for primary ↔ auxiliary communication and for the manifest stream itself.
- **ws_tamer**: WebSocket-based "tamer" for nodes that run on remote machines or inside containers. Provides the same manifest and control surface over the network.

```python
class ConnectionManager:
    def create_unix_socket(self, node: NodeInstance) -> Path:
        ...

    def create_ws_tamer(self, node: NodeInstance, remote_host: str) -> str:
        ...
```

Both connection types automatically register with the **Process Registry** and participate in manifest logging.

## Graph Data Model (simplified)

```yaml
# Desired state example (consumed by state-methods then turned into Graph)
graph:
  id: lab-orchestration-01
  nodes:
    - id: primary-01
      role: primary
      executable: ./servers/primary.py
      children: [aux-01, aux-02]
    - id: aux-01
      role: auxiliary
      executable: ./workers/sensor-reader.sh
      depends_on: [primary-01]
```

The `Graph` object materializes this into a traversable structure with:
- `adjacency_list`
- `reverse_dependencies`
- `subtree_roots`
- `critical_path` (for scheduling decisions)

## Key Operations Exposed

| Method | Description | Used By |
|--------|-------------|---------|
| `build_graph(yaml_path)` | Parse + validate + topological sort | control-script |
| `launch_tree(root_id)` | Start primary + all descendants in order | Lifecycle Controller |
| `restart_subtree(node_id)` | Graceful stop → restart of entire branch | self-healing |
| `get_ready_nodes()` | Nodes whose dependencies are satisfied | reconciliation loop |
| `prune_dead_nodes()` | Remove terminated instances from registry | health checker |

## Design Decisions

- **Graph is immutable after construction** — Any change triggers a full re-validation and new `Graph` object. This prevents subtle state drift.
- **No cycles allowed** — The loader raises a clear, categorized error (`permanent: graph-topology`) if a cycle is detected.
- **Lazy materialization** — `NodeInstance` objects are created only when the node is actually spawned (supports sparse activation).
- **Connection abstraction** — Both Unix sockets and WS-Tamer implement the same `Communicator` protocol, so higher layers never care which transport is used.

## Example: Starting a Subtree
```python
from communicators.graph_methods import build_graph, launch_tree

g = build_graph("desired-state.yaml")
launch_tree(g, root_id="primary-01")  # starts primary + aux-01, aux-02 in correct order
```

All state changes, PIDs, and connection details are written to the manifest before the function returns.

## Benefits
- Complexity of dependencies, parallelism, and hierarchy lives in one place.
- Nodes remain completely ignorant — they never see the graph object.
- Perfect audit trail: the manifest contains the exact sequence of graph operations that led to the current state.

## Open Questions
- Should we support "virtual nodes" (placeholders that only exist in the graph for dependency ordering but never spawn a process)?
- Dynamic graph mutation at runtime (add/remove nodes without full restart) — powerful but risky for lab hardware safety.
