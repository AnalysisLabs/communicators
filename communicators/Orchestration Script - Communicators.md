

# [[Communicators]] Library — Orchestration Script Decisions

**Goal**: Build a clean, reliable, declarative orchestrator for managing graphs of processes/nodes (servers, workers, lab equipment, etc.) with excellent observability and self-healing.

## Core Architectural Decisions

### 1. Declarative Desired State (YAML-First)
- The single source of truth is a YAML file describing the **desired graph** of nodes, dependencies, timing, and configuration.
- The orchestrator’s only job is **reconciliation**: continuously drive actual state toward the declared desired state.
- Imperative “do this then that” logic is avoided in favor of declarative definitions + reconciliation loops.

### 2. Separation of methods from instances
- Some modules will merely define methods at various levels of abstraction.
	- Of these method modules some will serve nodes, while others server the control plane.
- Instantiation will be covered by the control layer with the guidance of the YAML.

### 3. Clear Graph vs. Node Separation
- **Graph layer** (orchestrator): owns dependencies, parallelism, scheduling, retries, global coordination, and state reconciliation.
- **Node layer** (workers): intentionally “ignorant” — they know only how to perform their single task and how to report status/logs/metrics back to the control plane.
- This separation keeps node code simple and testable while concentrating complexity in the orchestrator.

### 4. Centralized Control Plane + Ignorant Nodes
- One Python orchestrator process acts as the brain.
- Nodes are lightweight, stateless (or minimally stateful) processes that receive instructions and stream back telemetry.
- All intelligence (scheduling, failure handling, resource decisions) lives in the central plane.

### 5. Manifest-Style Logging as First-Class Feature
- Every event, state change, log line, and metric from every node is **timestamped and collated** into a single chronological “manifest” file/stream.
- This provides perfect, queryable observability and is the primary tool for debugging and auditing.
- Structured + human-readable output.

### 6. Self-Healing by Default
- Built-in retry policies, exponential backoff, circuit breakers, and failure categorization.
- Transient failures are automatically recovered without human intervention.
- Clear failure modes and escalation paths for persistent problems.

### 7. Sparse / Lazy Activation
- Nodes/processes are only spawned when needed (demand-driven).
- Idle capacity consumes minimal resources.
- Supports both always-on services and on-demand/ephemeral tasks.

### 8. Thin Bootstrap / Launcher Layer
- Minimal Bash (or small Python) script responsible for:
  - Environment setup
  - Signal handling (SIGTERM, SIGHUP, etc.)
  - Starting the main orchestrator process
  - Clean shutdown and log rotation
- Keeps the core orchestrator focused on logic, not bootstrapping.

### 9. Reconciliation Loop (homeostasis) as the Heart
Core loop:
1. Load desired state from YAML
2. Discover actual state (running processes, health, resource usage)
3. Compute diff
4. Execute actions (start/stop/restart/scale/rebalance)
5. Write everything to the manifest
6. Sleep / wait for events

### 10. Standardized Node Interface
- Simple, versioned protocol (Unix domain sockets or lightweight HTTP/gRPC) for:
  - Heartbeats / health checks
  - Status and progress reporting
  - Log streaming
  - Metric emission
- Nodes are encouraged to be as small and focused as possible.

### 11. Process Lifecycle Management
- Proper start → run → graceful shutdown → forced kill path
- Zombie process reaping
- Resource limits and cgroups where appropriate
- Clear ownership (orchestrator owns the process tree)

## Key Non-Goals (Current Phase)
- Full distributed consensus / multi-orchestrator HA (single orchestrator is acceptable initially)
- Complex workflow DSL or visual editor
- Built-in GUI or web dashboard (CLI + manifest queries first)
- Automatic schema migration for YAML (versioning via comments or separate schema file)

## Benefits of These Choices
- **Reliability**: Self-healing + manifest logging dramatically reduces “unknown state” problems
- **Debuggability**: One chronological manifest makes root-cause analysis straightforward
- **Scalability**: Graph abstraction + ignorant nodes make it natural to add parallelism or new node types
- **Maintainability**: Clear separation of concerns keeps the codebase understandable as complexity grows
- **Portability**: Same orchestration patterns can eventually apply to servers, lab hardware, robots, etc.

## Open Questions / Future Work
- Persistence strategy for orchestrator state (file, SQLite, etcd?)
- Exactly-once vs. at-least-once semantics for node execution
- How to handle long-running vs. batch/ephemeral nodes uniformly
- Integration points for external monitoring (Prometheus, etc.)

---

## High-Level Python Launcher Abstractions

The Communicators Library’s Python high-level launcher script implements the orchestration logic through a compact, composable set of abstractions that completely separate declarative intent from low-level execution mechanics. These abstractions allow the launcher to treat every node—whether a primary server, an auxiliary process, a Bash script, or a Python entry point—uniformly as part of a larger graph, while guaranteeing that manifest-style logging from all processes flows chronologically into a single shared stream or file without loss or interleaving confusion.

The launcher is deliberately thin: it loads the desired graph from YAML, consults the current actual state, computes the minimal reconciliation actions, and executes them through the abstractions below. All subprocess details (stream inheritance, unbuffering, process-group management, shared file descriptors, and environment propagation) are encapsulated so that the rest of the orchestrator remains focused on scheduling, dependencies, retries, and self-healing.

The core abstractions are:

- **Server Specification** – A declarative blueprint that fully describes any single logical node (or server-client pair), capturing its executable path, arguments, environment variables, working directory, role (primary versus auxiliary), expected ports or health checks, and any metadata required for registration or dependency resolution. This eliminates repetition and lets every node be instantiated, validated, and reused identically regardless of implementation language or nesting depth.

- **Launcher Executor** – The single point of invocation responsible for starting any defined server. It handles fire-and-forget or monitored launches, automatic inheritance of the parent’s output streams (so manifest lines appear in the same terminal or log file as the orchestrator itself), forced line-buffering for both Bash and Python children, and optional shared file-descriptor passing when everything is redirected to a common log. The executor returns only a lightweight handle; all low-level `Popen` mechanics, signal handling, and zombie reaping remain hidden.

- **Hierarchy / Tree Manager** – Models parent-child and dependency relationships across the entire graph. It enables coordinated operations on subtrees (for example, “start all auxiliaries under primary 5” or “restart the full chain for node X”) while automatically propagating shared context such as log streams, environment variables, or process-group ownership. This turns what would otherwise be manual sequencing of Bash calls into a single declarative action.

- **Process Registry / Inventory** – A centralized, queryable record of every running node, keyed by logical ID, operating-system PID or process group, status, start time, and parent relationships. It supports fast lookups (“is auxiliary Y under primary Z still alive?”), bulk operations, and recovery after restarts without manual PID hunting or external tooling.

- **Lifecycle Controller** – The high-level coordinator that wires the preceding abstractions together into complete operations: launch (single node or entire tree), graceful shutdown, forced termination, restart, status polling, and optional auto-restart policies. Callers interact only with methods such as “launch_tree(primary_id)” or “reconcile_graph()”; the controller internally computes diffs, orders actions according to dependencies, and ensures every state change is written to the manifest before sleeping or waiting for events.

- **Manifest Integrator** – A thin bridge that automatically configures every launched process to participate in the existing manifest logging system. It sets the necessary environment variables and file-descriptor inheritance so that timestamped, prefixed lines from every node—Bash or Python, primary or auxiliary—appear in perfect chronological order in the shared terminal or log file, with zero dropped messages and no additional code required in the node implementations themselves.

Collectively these abstractions make the Python launcher script read like configuration rather than orchestration boilerplate. The desired state lives in YAML; the launcher merely reconciles reality to that state, records every action and observation in the manifest, and keeps the node processes themselves “ignorant” of the larger graph. The design is intentionally language- and deployment-agnostic, supporting both always-on services and on-demand ephemeral tasks while remaining portable to future environments (containers, remote machines, or lab hardware) without changes to the core abstractions.

This section expands on the “Thin Bootstrap / Launcher Layer” principle already identified in the architectural decisions, providing the concrete Python-side realization that makes the overall reconciliation loop practical and maintainable.

---
## Centralized Liveness Checking with `kill -0`

One of the most important responsibilities of the orchestrator is knowing whether any given node is still alive — without burdening the node code itself and without introducing fragile per-node ping logic. This is solved through a single, standardized, and heavily abstracted mechanism built around the classic Unix `kill -0` technique.

### Why `kill -0`?

`kill -0 $PID` (or its Python equivalent `os.kill(pid, 0)`) is the idiomatic, safe, and battle-tested way to ask the operating system: “Does this process still exist?” It sends signal 0, which is a no-op. The kernel simply checks whether the PID is valid and whether the caller has permission to signal it. No termination signal is ever delivered, no signal handler is invoked in the target process, and the check is extremely fast and lightweight.

This approach is deliberately chosen because:
- It requires **zero cooperation** from the node (the node can be a black box written in Python, C++, Bash, or anything else).
- It works uniformly for both Python and C++ nodes.
- It has near-zero overhead and works even when the node is busy or unresponsive.
- It is completely safe and has been the standard pattern on Unix systems for decades.

### How It Is Abstracted in the Architecture

The `kill -0` check is never exposed directly to the high-level orchestrator script or to individual node implementations. Instead, it is fully encapsulated inside the existing abstraction stack:

- **ServerRuntime** — The `is_alive()` method on every `ServerRuntime` instance performs the actual liveness check (either via the pure-Python `os.kill(pid, 0)` or by delegating to a thin Bash helper if process-group semantics require it). The method also tracks consecutive failures, last-check timestamp, and any backoff state for restart decisions.

- **Process Registry** — Maintains the authoritative list of all `ServerRuntime` objects. When the health checker needs to scan the system, it simply iterates over the registry. No manual PID management or scattered `kill` calls exist anywhere else in the codebase.

- **Lifecycle Controller / Health Checker** — A small, dedicated component (either a background thread or a method called from the main reconciliation loop) periodically asks every runtime in the registry “are you still alive?” If a runtime reports false, the controller immediately triggers `restart()` using the original `ServerDefinition` stored in that runtime. All decisions and state changes are written to the manifest before any action is taken.

- **Launcher Executor** — When a node is first started (or restarted), the Launcher captures the PID (and optionally the full process group) and hands it to the newly created `ServerRuntime`. The Bash wrapper used by the Launcher is responsible only for the initial `exec` and environment setup; it does not perform ongoing pings.

This design keeps the node implementations completely ignorant of liveness concerns. A node never needs to implement a ping endpoint, heartbeat thread, or health-check HTTP route unless it wants to provide richer application-level status later. The orchestrator owns the question “is this node alive?” at the process level.

### Minimal Implementation Sketch

```python
# Inside ServerRuntime
def is_alive(self) -> bool:
    if self._process is None:
        return False
    try:
        os.kill(self._process.pid, 0)   # or call thin Bash helper
        return True
    except ProcessLookupError:
        return False

# In the Health Checker (called periodically by Lifecycle Controller)
for runtime in registry.all_runtimes():
    if not runtime.is_alive():
        manifest.log(f"Node {runtime.id} died — initiating restart")
        runtime.restart()
```

The Bash equivalent (used only inside the thin launcher wrapper when needed) is simply:

```bash
if kill -0 "$PID" 2>/dev/null; then
    exit 0   # alive
else
    exit 1   # dead
fi
```

### Benefits in the Broader Architecture

- **Nodes stay ignorant** — Exactly as required by the “Graph vs. Node Separation” principle.
- **Self-healing becomes trivial** — The same `is_alive()` + `restart()` path powers both manual restarts and automatic recovery.
- **Sparse / lazy activation is natural** — The orchestrator can keep a node in the registry as “dormant” and only call `start()` when demand appears; liveness checks simply return false until then.
- **Future-proof** — When application-level heartbeats (via manifest messages or a lightweight Unix socket) are added later, they can be layered on top of the process-level `kill -0` check without changing any node code.

This small, well-abstracted mechanism is one of the quiet foundations that makes the entire declarative, self-healing, sparsely-activated system possible while keeping every node as simple and focused as possible.

---
## Exhaustive Error Handling Without Combinatorial Explosion

A recurring risk in orchestration systems is **error-handling explosion**: as the number of possible failure modes grows (network blips, resource exhaustion, bad input, hardware faults, dependency failures, timeouts, permission errors, etc.), the healing logic can become an unmaintainable tree of special cases.

The design solves this by treating errors as **orthogonal, composable categories** rather than unique snowflakes. Every error is classified along a small number of independent axes. Each axis maps to a narrow, reusable healing strategy. The combination of axes produces the specific response without requiring a new code path for every possible error.

### Error Categorization Axes (Current Working Set)

| Axis                  | Possible Values                          | Typical Healing Strategy |
|-----------------------|------------------------------------------|--------------------------|
| **Duration**          | Transient / Intermittent / Permanent     | Backoff + retry / Circuit breaker / Escalate |
| **Recoverability**    | Self-healable / Node-restartable / Subtree-restartable / Fatal | Automatic retry / `restart()` / `restart_tree()` / Human alert |
| **Scope**             | Single node / Dependency chain / Resource pool / Global | Targeted restart / Cascade restart / Resource rebalance / Full graph reconciliation |
| **Root Cause Class**  | Resource (CPU/mem/disk) / Network / Logic / Configuration / External dependency | Scale resource / Reconnect / Reconcile config / Fail fast + alert |
| **Severity**          | Informational / Warning / Error / Critical | Log only / Retry with backoff / Immediate restart / Halt + notify |

### How Healing Logic Stays Small

- A **Policy Table** (simple YAML or Python dict) maps each combination of axes to a healing action.
- New error types are added by extending one or more existing axes — no new `if` branches are required in the core healing code.
- The **Lifecycle Controller** and **ServerRuntime** implement the strategies; the orchestrator only decides *which* strategy to invoke based on the categorized error.
- Every healing decision, action taken, and outcome is written to the manifest with the categorized error attached. This gives perfect auditability without extra logging code.

### Example Policy Snippet (illustrative)

```yaml
error_policies:
  transient:
    max_retries: 5
    backoff: exponential
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

### Benefits

- **Exhaustive coverage** — Any new error can be placed on the existing axes and immediately gets appropriate handling.
- **No combinatorial explosion** — The number of strategies grows linearly with the number of axes, not exponentially with the number of error types.
- **Predictable and debuggable** — The manifest always shows *why* a particular healing action was chosen.
- **Evolvable** — Adding a new axis (e.g., “Security” or “Cost”) only requires updating the policy table and the corresponding strategy implementations.

This approach keeps the healing logic small, testable, and aligned with the “ignorant nodes + smart control plane” principle: nodes simply fail in whatever way they fail; the orchestrator classifies the failure and applies the appropriate policy.

---
## Hierarchy of the Library

- Prelude
	- collect imports
- Node methods
	- pre-defined to_/from_, N/P
	- type of node resolution
	- load/core
- Graph methods
	- elementary node structure (genealogy of instance)
	- load spreading
		- node instance spawning
		- parallel connection management
	- connection methods
		- unix_socket
		- ws_tamer
- State methods
	- real state (health)
		- Build quasi-natural language for more poignantly explaining the errors that are raised.
		- The goal is such that no unexpected error type can exist, and I insistently work on make sure all errors are caught and healed in real time.
	- ideal state (yaml config)
		- YAML loading methods
			- auto as default for host/port/socket_path
			- but allowance for static host/port/socket_path
		- Intermediate representation (IR) methods
		- transient state methods
- Control layer methods
	- high level python script
	- exhaustive tree of methods for running every constituent program so that errors are exhaustively healed with fall backs rather than raising errors.
		- bash methods
		- python wrapped bash methods
- Extra nodes
- Intra graphs
- Foreign function interface intermediate representation (fiirr)
	- to_from
	- yaml_extraction
- Control script
	- Load yaml config
	- IR
	- use IR to put nodes/graph into their own homeostasis loops
	- use exhaustive self-healing or raise errors when a server or graph goes down.

---
## Critique of this Hierarchy

### Question 1: Is this hierarchy itself too bloated?

Answer: No because it is properly nested.

### Question 2: Is the YAML config going to become unwieldy?

Answer: If flat yes. but the yaml config must support nesting of communicators. Also the yaml config can be split so the implicit config of auxiliary servers is buried in the communicators library. 

### Challenge 1: I must do diligence to ensure the yaml config does not become unwieldy

### Question 3: What is the right time to stop planning and start coding?

Answer: Once I have anticipated the limits of the planned iteration and whether such limitations are satisfying.