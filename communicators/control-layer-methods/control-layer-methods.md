# Control Layer Methods — High-Level Python Script, Exhaustive Healing Tree, Bash & Python-Wrapped Methods

**Specialized Design Document for `communicators/control-layer-methods/`**

## Purpose
This is the **operational brain** of the orchestrator. It contains the high-level Python entry point and the exhaustive library of methods that actually start, stop, restart, and monitor every constituent program (Bash scripts, Python entry points, binaries, future lab hardware).

It implements:
- **Centralized Control Plane + Ignorant Nodes**
- **Launcher Executor**
- **Lifecycle Controller**
- **Process Registry / Inventory**
- **Manifest Integrator**

All complexity of process management, signal handling, zombie reaping, and self-healing lives here so that node code and graph code stay simple.

## High-Level Architecture

```
control-script (entry point)
        │
        ▼
control-layer-methods/
├── launcher.py          # Server Specification + Launcher Executor
├── lifecycle.py         # Lifecycle Controller + Health Checker
├── registry.py          # Process Registry
├── bash_wrappers.py     # Thin Bash launchers + Python wrappers
├── manifest_integrator.py
└── healing_tree.py      # Exhaustive fallback tree (no bare `raise`)
```

## Key Abstractions (implemented here)

### Server Specification
```python
@dataclass
class ServerSpec:
    id: NodeID
    executable: str
    args: list[str]
    env: dict[str, str]
    cwd: Path
    role: Role
    health: HealthCheckSpec
    restart_policy: RestartPolicy
```

### Launcher Executor
The single function that actually spawns anything:

```python
def launch(spec: ServerSpec, manifest_fd: int) -> ServerRuntime:
    """Returns lightweight handle; all Popen, fd inheritance, unbuffering, process-group
    management is hidden inside."""
    if spec.executable.endswith(".sh"):
        return _launch_bash(spec, manifest_fd)
    elif spec.executable.endswith(".py"):
        return _launch_python(spec, manifest_fd)
    ...
```

Features:
- Automatic line-buffering for both Bash and Python children
- Shared manifest FD inheritance
- Proper `setsid` / process-group creation for clean signal delivery
- Returns `ServerRuntime` (PID + `is_alive()` via `kill -0` + restart handle)

### Lifecycle Controller
Wires everything together:

```python
class LifecycleController:
    def launch_tree(self, root_id: NodeID) -> None:
        ...

    def graceful_shutdown(self, node_id: NodeID, timeout: float = 30.0) -> bool:
        ...

    def forced_kill(self, node_id: NodeID) -> None:
        ...

    def restart(self, node_id: NodeID, reason: str) -> None:
        self.graceful_shutdown(...)
        self.launch(...)  # with backoff from policy
```

### Exhaustive Healing Tree (`healing_tree.py`)
Instead of raising exceptions, every method has a complete fallback chain:

```python
def run_with_full_healing(node: NodeInstance, ideal: IdealState):
    try:
        return _run_node(node)
    except TransientError as e:
        return retry_with_backoff(node, e)
    except PermanentNodeError:
        return restart_node(node)
    except PermanentSubtreeError:
        return restart_subtree(node)
    except FatalError:
        manifest.log("FATAL", explain=explain_error(e))
        sys.exit(1)
    except Exception as e:  # last resort — still never leaks
        manifest.log("UNEXPECTED but handled", explain=explain_error(e))
        return restart_node(node)  # safe default
```

This guarantees the "exhaustive tree of methods for running every constituent program so that errors are exhaustively healed with fall backs rather than raising errors."

## Bash Methods vs Python-Wrapped Bash
- `bash_wrappers/primary.sh` — minimal launcher used by thin bootstrap
- `python_wrapped_bash.py` — same logic but with full manifest integration and Python error classification

Both produce identical manifest output and obey the same `kill -0` contract.

## Integration with `kill -0` Liveness
The `ServerRuntime.is_alive()` method (implemented here) is the only place `os.kill(pid, 0)` or the Bash equivalent is ever called. Higher layers only ever ask "are you still alive?" via the registry.

## Design Decisions

- **One orchestrator process owns the entire tree** — No forking of the control plane itself.
- **All actions are manifest-first** — Every `launch`, `stop`, `restart`, health check result is written to the manifest *before* the action is taken and again after completion.
- **No bare `raise`** — The healing tree ensures every code path ends in a deliberate, logged, categorized outcome.
- **Thin Bash bootstrap** — The actual `control-script` entry point is a 30-line Bash script that only sets up the environment and `exec`s the Python control layer.

## Example High-Level Call (from control-script)
```python
from communicators.control_layer_methods import LifecycleController
from communicators.state_methods import IdealState

ideal = IdealState.from_yaml("desired.yaml")
ctrl = LifecycleController(ideal)
ctrl.reconcile_forever()   # the main loop
```

## Benefits
- Nodes stay tiny and ignorant.
- Every possible failure mode has a defined, logged, healing response.
- The control layer can be unit-tested in isolation by injecting fake `ServerRuntime` objects.

## Open Questions
- Add support for cgroups v2 resource limits per subtree?
- Should the healing tree expose a "dry-run" mode that only logs what it *would* do?
- Future: allow the control layer to delegate certain node types to external orchestrators (Kubernetes, systemd) while still owning the manifest.
