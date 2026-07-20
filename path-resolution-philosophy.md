# Path Resolution Philosophy in CommunicatorsOS

**Status:** Foundational design principle  
**Date:** June 2026  
**Author:** Thomas Fox (Analysis Labs)

---

## Core Vision

CommunicatorsOS is not a traditional operating system. It is a **distributed single-system image operating system** designed from the ground up to make a network of computers function as if they were one coherent machine.

This network can be:
- A handful of machines in a warehouse
- Thousands of nodes spread across the globe
- Millions (or theoretically more) distributed across the solar system

The fundamental promise is: **distribution should feel like local execution**, with latency as the only inevitable tax. When you run something, you should not have to think about "which machine" unless you explicitly want to.

This philosophy has profound implications for how paths, namespaces, and execution targets are resolved.

---

## Why Traditional Path Handling Is Insufficient

In conventional operating systems (Unix, Linux, Windows, etc.), paths are resolved against a single local filesystem hierarchy. Even in distributed systems or clusters, path resolution is typically handled by:
- Mounting remote filesystems (NFS, etc.)
- Explicit hostnames/IPs in paths
- Container/VM isolation boundaries

These approaches do not scale cleanly to a true "one computer" abstraction at planetary or solar-system scale. They also create unnecessary friction for the common case: running code and managing resources that live inside the CommunicatorsOS engine itself.

CommunicatorsOS therefore rejects the traditional model in favor of an explicit **scope-based resolution** system.

---

## The Scope Model

Instead of a single flat namespace, every path in CommunicatorsOS is resolved within an explicit **scope**. The scope sits between the command and the target:

```
<command> <scope> <path>
```

This design is intentional over-engineering. It ensures that as the system grows from one machine to a trillion, **no fundamental rewrite of path resolution is required** — only extensions and new scope types.

### Defined Scopes (Current + Planned)

| Scope          | Meaning                                                                 | Example Command                              | Resolution Target                          | Status      |
|----------------|-------------------------------------------------------------------------|----------------------------------------------|--------------------------------------------|-------------|
| `internal`     | Resolved relative to the privileged `communicators` library/engine     | `run internal state-methods/namespace.py`   | Inside the CommunicatorsOS core            | Primary     |
| `host`         | Resolved against the local host operating system's filesystem          | `run host /home/user/attachments/data.csv`  | Local machine filesystem (outside library) | Primary     |
| `distributed`  | Resolved across the distributed network of nodes                       | `run distributed models/vision.py`          | Network-wide (future: mirroring, sharding, etc.) | Future     |
| `dist-N`       | Targeted execution on a specific node (e.g. `dist-47`)                 | `run dist-47 models/vision.py`              | Specific remote node                       | Future     |
| `dist-all`     | Broadcast / mirrored execution across all known nodes                  | `run dist-all state-methods/sync.py`        | Entire network                             | Future     |

### Design Rationale

- **`internal`** is the default mental model for most development work inside CommunicatorsOS. The privileged `communicators` directory acts as the logical root for the OS engine itself.
- **`host`** provides a clean, explicit escape hatch to the underlying physical machine without polluting the internal namespace.
- **`distributed` / `dist-*`** leaves the door open for sophisticated distributed execution semantics (workload distribution, replication, consensus, latency-aware routing, etc.) without requiring changes to the core command syntax later.

This structure makes the system inherently **namespace-aware** and **location-transparent** by design.

---

## Philosophical Implications

### 1. Paths Are Not Just Strings — They Are Scoped References

A path in CommunicatorsOS is never "just a path." It is always a **scoped reference** that carries intent about *where* the target lives in the distributed fabric.

This is one of the fundamental quirks that will distinguish CommunicatorsOS from other operating systems.

### 2. Over-Engineering for Scale from Day One

The system is being built with the assumption that it may one day orchestrate planetary-scale or solar-system-scale compute. Therefore:

- Every design decision must remain valid (or gracefully extensible) at extreme scale.
- No "we'll fix it when we get there" shortcuts that would require breaking changes.
- The path/scope model is the first and most visible manifestation of this philosophy.

### 3. Latency Is the Only Tax

Distribution is not an afterthought or an optional feature. It is the native execution model. Running something "distributed" should feel as natural as running it locally — the only difference the user should experience is latency.

---

## Future Evolution

This document captures the initial philosophy. As the system matures, new scopes may be added (e.g., `consensus`, `edge`, `space`, latency-tiered scopes, capability-based scopes, etc.).

The key invariant is:

> **The scope sits between the verb and the target.**  
> This syntactic and semantic pattern will remain stable even as the meaning of individual scopes grows more sophisticated.

---

## Summary

CommunicatorsOS treats path resolution as a **first-class distributed systems concern**, not a filesystem detail. By introducing explicit scopes (`internal`, `host`, `distributed`, and future variants), the system achieves:

- Clean separation between engine-internal resources and host resources
- A natural path toward location-transparent distributed execution
- A syntax that scales from one machine to a trillion without fundamental redesign
- A distinctive identity: *an operating system that does not treat paths the way other operating systems do*

This is not a local optimization. It is a foundational architectural decision.

---

*End of document*