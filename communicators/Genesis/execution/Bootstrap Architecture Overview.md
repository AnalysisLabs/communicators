# Bootstrap Architecture Overview

> **Purpose of this document**  
> Attach this file (plus a failing log + the 1–2 source fragments involved) instead of re-dumping the entire bootloader / VirtualFS / prefix stack.  
> It records the *contracts* and *seams* of the **bootstrap stage**. Source files remain the source of truth for implementation details.

Last updated: 2026-08-05  
Status: **Bootstrap stage complete**

---

## 1. Core Principle

> Almost nothing in the Communicators ecosystem makes sense when examined in isolation.  
> Coherence is a property of the **boot sequence**, not of any individual file.

Judging a single module, class, or function outside the runtime sequence that actually loads it is usually a category error.

- Imports that appear missing are often injected by an earlier tier.
- Names that appear undefined are bound at load time.
- Side-effects (starting servers, killing ports, writing the VirtualFS) are ordered so they become safe only because of what has already run.
- Most real bugs live in the *seams* between tiers or between the prefix and the user program that follows it.

---

## 2. Boot / Load Sequence

### DB / VirtualFS initialization (once per fresh run)

```
DB_bootloader.py
  ├── VirtualFS.py          → creates empty tables (ephemeral SQLite)
  ├── DB_layout.py          → seeds the directory skeleton
  └── prefix_builder.py --write
        └── builds Tier 0 → 1 → 2 → A/C and writes Database/prefix.py
```

### Program launch (bootloader.py)

```
bootloader.py
  ├── ensures VirtualFS is initialized
  ├── execution_harness(src="state-methods/namespace.py",
  │                     dst="Runtime/generated/namespace.py", wait=False)
  └── execution_harness(src="transpiler/egg_transpiler.py",
                        dst="Metamorphosis/generated/egg_transpiler", wait=True)
```

Each `execution_harness` call:

1. Reads the current prefix from the VirtualFS (`Database/prefix.py`).
2. Concatenates prefix + user source (with the `# ==================== (USER PROGRAM) ====================` marker).
3. Runs `inject_process_paths(...)` (ownership-tree based).
4. Writes the exact combined source into the VirtualFS under the destination path.
5. Spawns `execution_launcher.py` as an independent child process:
   - combined source is fed on **stdin**
   - VirtualFS destination path is passed as `argv[1]`

### Child-side launcher (`execution_launcher.py`)

- Reads source from stdin and destination name from argv.
- Populates `linecache` under the VirtualFS path so `inspect` / traceback context work.
- Compiles with `compile(src, dst, "exec")` so every frame reports the correct VirtualFS filename.
- Executes under a controlled globals dict that sets `__name__` and `__file__`.
- Provides the installation point for the process_path-aware exception intermediary.

This design keeps the program source itself free of bootstrap scaffolding while guaranteeing that frames, source recovery, and `__file__` are correct inside the child.

---

## 3. Prefix Tiers & Transpiler Contract

This is the most important contract in the system.

### Tier construction (prefix_builder.py)

| Tier | Contents                                      | Notes |
|------|-----------------------------------------------|-------|
| 0    | `standard.py` + concrete `COMMUNICATORS_ROOT` | Base |
| 1    | Tier 0 + `Manifest` class                     |       |
| 2    | Tier 1 + `transponder` class                  |       |
| A/C  | Tier 2 after Stage B + Stage C                | What actually gets prepended |

`build_prefixA()` → `transpile_to_tier_c(raw)` which performs the two-stage rewrite and also writes the intermediate `prefix_tierB.py` / `prefix_tierC.py` into the VirtualFS for inspection.

### Stage B – structural split

For every class that contains the markers:

```
class Name_internal:
    # all @internalmethod bodies (decorator stripped)
_Name_internal = Name_internal()

class Name:
    # all @externalmethod bodies, decorator turned into @staticmethod
```

**Rules enforced at transpile time**

- Only `@externalmethod` and `@internalmethod` are legal on methods of these “imported” classes.
- Undecorated `def` → `TranspileError`.
- Both markers on the same function → `TranspileError`.

### Stage C – call-site rewrite

Stage C walks every public / `_internal` pair and rewrites call sites in **both** kinds of method:

- **Inside public (external) methods**  
  Bare calls to internal method names become:
  ```python
  _Name_internal.method(...)
  ```

- **Inside internal methods**  
  1. The signature is forced to begin with `self` (idempotent).  
  2. Bare sibling calls become:
  ```python
  self.method(...)
  ```

Only bare names are rewritten; attribute accesses and the `def` lines themselves are left untouched.  
Because internal methods are now proper instance methods, the calling-convention invariant is simply:

> Every `@internalmethod` ends up with a `self` parameter (added automatically if missing) and internal-to-internal calls are rewritten to go through `self`.

---

## 4. process_path / Ownership Injection

`vfs_process_path.py` runs as a final pass over the combined (prefix + user) source.

1. Builds a nested ownership tree from AST + section banners (`# === Tier N (imports) ===` and `# ==================== (USER PROGRAM) ====================`).
2. For every `Manifest.` / `manifest.` call that appears at or after the Tier-2 marker, injects  
   `process_path="<dotted.path.from.ownership.tree>"`  
   as a keyword argument if it is missing.

The injected path is the hierarchical ownership piece (program + section + class / function). Later stages can enrich it.

Manifest itself already emits process-path-style lines for deliberate logging. Full rewriting of classic traceback frames into the same language remains an optional later enhancement; the current combination of VirtualFS paths + Manifest ERROR lines is already coherent.

---

## 5. VirtualFS

- Ephemeral SQLite (`runtime_fs.db`), content-addressed (`file_contents` + `file_graph`).
- Created fresh by `VirtualFS.py`, laid out by `DB_layout.py`.
- All program assembly and prefix storage goes through `vfs_writer.py` (`write_file` / `read_file`).
- Destination paths used in `compile(..., dst, ...)` and in tracebacks are VirtualFS paths  
  (e.g. `Runtime/generated/namespace.py`, `Metamorphosis/generated/egg_transpiler`).

---

## 6. Bootstrap Stage – Completed Contracts

The bootstrap machinery itself is now stable. Remaining errors visible in `ns_server.log` are program-level or prefix-content issues (for example arity mismatches inside transpiled internal methods), not failures of the launch or source-recovery path.

---

## 7. Quick Reference – What Future Sessions Should Attach

Minimum useful set for a new bug:

- This file (`Bootstrap_Architecture_Overview.md`)
- The log excerpt (especially any TypeError / process_path line)
- The 1–2 source fragments that define the methods appearing in the traceback

Everything else (bootloader, harness, launcher, VirtualFS schema, full prefix source, etc.) can stay on disk until a specific contract is being changed.
