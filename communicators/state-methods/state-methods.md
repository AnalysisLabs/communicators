
# State Methods — Real State (Health), Ideal State (YAML), IR, Transient State

**Specialized Design Document for `communicators/state-methods/`**

## Purpose
`state-methods` is the **single source of truth layer** for everything the orchestrator knows about "what should be" versus "what actually is". It implements the reconciliation heart of the system and feeds the self-healing machinery.

It directly realizes:
- **Declarative Desired State (YAML-First)**
- **Reconciliation Loop (homeostasis)**
- **Manifest-Style Logging as First-Class Feature**
- **Exhaustive Error Handling Without Combinatorial Explosion**

## Three-State Model

### 1. Ideal State (Desired)
Loaded from YAML. Immutable after load. Contains the complete graph declaration plus per-node configuration.

```python
# state-methods/ideal.py
@dataclass(frozen=True)
class IdealState:
    graph: Graph
    policies: ErrorPolicyTable
    manifest_path: Path
    health_interval: float

    @classmethod
    def from_yaml(cls, path: Path) -> "IdealState":
        raw = yaml.safe_load(path.read_text())
        # auto host/port/socket_path defaults + static overrides supported
        return cls(
            graph=build_graph(raw["graph"]),
            policies=ErrorPolicyTable.from_dict(raw.get("error_policies", {})),
            ...
        )
```

**YAML loading features**:
- Automatic defaults: if a node omits `host` / `port` / `socket_path`, sensible values are generated from `NodeID`.
- Explicit static values always win.
- Schema validation with friendly error messages (using the quasi-natural language described below).

### 2. Real State (Actual / Health)
Discovered continuously via:
- `kill -0` process liveness (encapsulated in `ServerRuntime.is_alive()`)
- Optional application-level heartbeats (Unix socket or manifest messages)
- Resource metrics (psutil)
- Exit code analysis on termination

```python
# state-methods/real.py
class RealState:
    def __init__(self, registry: ProcessRegistry):
        self.registry = registry

    def snapshot(self) -> dict[NodeID, NodeRuntime]:
        return {
            nid: runtime
            for nid, runtime in self.registry.all_runtimes().items()
            if runtime.is_alive()
        }
```

### 3. Transient State
Ephemeral data that lives only inside one reconciliation iteration:
- Current diff between Ideal and Real
- Pending actions (start/stop/restart queue)
- Backoff timers and circuit-breaker state per node

## Quasi-Natural Language Error Reporting
A major goal of this module is that **no unexpected error type can ever exist**. Every failure is instantly turned into a human-readable, categorized sentence that appears in the manifest.

```python
def explain_error(error: Exception, node: NodeInstance, context: dict) -> str:
    axes = classify_error(error)  # returns Duration, Recoverability, Scope, RootCause, Severity
    return (
        f"Node {node.id} experienced a {axes.duration} {axes.root_cause} failure "
        f"of {axes.severity} severity affecting {axes.scope}. "
        f"Recommended action: {policy_table.lookup(axes)}"
    )
```

Example manifest line:
```
2026-04-27T13:22:41.003Z [primary-01] ERROR: Node primary-01 experienced a transient network failure of warning severity affecting single node. Recommended action: retry with exponential backoff (attempt 2/5)
```

This eliminates "unknown error" bugs and makes root-cause analysis trivial.

## Intermediate Representation (IR)
The `ffiir` module (see its article) consumes the Ideal State and produces a compact, validated IR that the reconciliation loop operates on. This decouples YAML syntax from execution semantics.

## Reconciliation Loop (Core Algorithm)

```python
def reconcile(ideal: IdealState, real: RealState) -> None:
    diff = compute_diff(ideal.graph, real.snapshot())
    actions = plan_actions(diff, ideal.policies)
    for action in actions:
        execute_action(action)          # via control-layer-methods
        manifest.log(action, explain=explain_error(...))
    write_manifest_checkpoint()
```

## Design Decisions

- **Frozen IdealState** — Once loaded, the desired world never mutates inside a run. All dynamism lives in Real + Transient.
- **Error axes as first-class data** — The five-axis classification (Duration, Recoverability, Scope, Root Cause, Severity) is the only way errors are represented. No ad-hoc `if isinstance` trees.
- **Manifest is the database** — We do not maintain a separate SQLite/etcd store for state; the chronological manifest + periodic checkpoints are sufficient and far more debuggable.
- **Auto-defaulting in YAML** — Reduces boilerplate while still allowing full static control when needed (lab equipment with fixed IPs, for example).

## Policy Table Example (excerpt)
```yaml
error_policies:
  transient:
    max_retries: 5
    backoff: exponential
    jitter: true
    action: retry
  permanent_node:
    action: restart
    notify: false
  permanent_subtree:
    action: restart_tree
    notify: true
  fatal:
    action: halt
    notify: ops_team
```

## Benefits
- Perfect observability: every state transition is explained in plain English in the manifest.
- Self-healing is exhaustive by construction — any new error is forced onto the existing axes and immediately gets a policy.
- YAML remains the single source of truth; the orchestrator is purely a reconciler.

## Open Questions
- Should we add a "predicted future state" simulation mode that can warn the operator before applying a change that would cause a cascade failure?
- Integration with external stores (etcd, Consul) for multi-orchestrator scenarios (explicitly a non-goal for v1).
