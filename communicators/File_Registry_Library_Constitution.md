
# File Registry Library Constitution

**Status:** Draft v0.1  
**Purpose:** Lock the design, philosophy, and API surface before any implementation begins.  
**Scope:** A small, independent library for managing a strict, human-editable file identity registry.

---

## 1. Core Philosophy

1. The `file_registry.json` file is the **single source of truth**.
2. The registry is intentionally plain JSON so that it remains convenient to edit by hand.
3. The library never silently modifies existing entries.
4. Automation is permitted only to *discover* and *flag* problems. All decisions that change identity or references require explicit human confirmation.
5. The primary goal is high-quality breakage detection and a clean manual resolution workflow, not auto-healing.
6. The library must remain independent of any particular project (including Communicators) and must support custom path backends in the future (real filesystem, VirtualFS, etc.).

---

## 2. Data Model

Every entry in `file_registry.json` is a triple:

```json
{
  "uuid": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "file_path": "relative/parent/dir",   // empty string "" means root
  "file_name": "filename.ext"
}
```

- `uuid` is a version-4 UUID and is the stable identity.
- `file_path` + `file_name` together describe the location relative to a designated root.
- The combination of all three fields constitutes the full identity of a file or directory.

The registry may later contain entries that do not exist on the real filesystem (e.g. VirtualFS paths). The data model itself does not distinguish them.

---

## 3. Runtime API

### 3.1 `resolve(uuid, file_path, file_name) → Path`

- Performs a **strict** lookup of the exact triple.
- On success: returns the absolute path (root + file_path + file_name).
- On failure: raises `RegistryLookupError` containing the three arguments that were supplied.
- This is the only function that normal application code should call.

### 3.2 Custom Path Backends

The library shall provide a simple resolver protocol so that alternative storage systems (VirtualFS, remote stores, etc.) can be plugged in without changing the triple model or the `resolve` signature.

---

## 4. Problem Taxonomy

The library recognizes exactly three categories of problem:

| Code              | Name                     | Definition                                              |
|-------------------|--------------------------|---------------------------------------------------------|
| `orphan_file`     | Orphan file              | A file or directory exists on disk but has no matching registry entry. |
| `broken_reference`| Broken reference         | Code contains a triple that does not match any registry entry. |
| `stale_entry`     | Stale registry entry     | A registry entry exists but the corresponding file/directory is missing. |

All three must be reportable by the `check` command and must be presentable inside the `doctor` REPL.

---

## 5. Command Surface

The library exposes the following commands (CLI and equivalent Python API):

- `filereg init`  
  Creates a new `file_registry.json` if none exists (using the same discovery rules as the original generator script). Refuses to overwrite an existing registry.

- `filereg check`  
  Scans the registry and the codebase. Reports all problems in both human-readable and machine-readable form.

- `filereg doctor`  
  Interactive REPL for resolving problems one at a time (see §6).

- `filereg todo`  
  Emits a checklist of currently open problems.

- `filereg plan show | apply | abort`  
  Manages a temporary migration plan built during a `doctor` session (see §7).

No command may modify the registry or source code without an explicit user-confirmed plan.

---

## 6. Doctor REPL Behavior

When `filereg doctor` encounters a `broken_reference`, it displays:

```
[broken reference]
  uuid:      <uuid>
  file_path: <file_path>
  file_name: <file_name>
  location:  <file>:<line>
```

### 6.1 Standard Options

```
What do you want to do?
  (n)ew entry     – treat as a genuinely new file and create a fresh registry entry
  (m)ap           – map this identity to a different identity (existing or new)
  (i)gnore        – mark as known/ignored for now
  (s)kip          – leave unresolved and move to the next problem
  (q)uit          – exit the doctor session
```

### 6.2 Automatic Suggestion Rule (2-of-3)

If a broken reference matches **exactly two** of the three fields with one or more registry entries, the tool performs a recursive search of the codebase.

- If **exactly one** registry entry is consistent with that partial match across the entire codebase, the doctor **must** present it as a declinable suggestion:

```
Suggested mapping (2-of-3 match, unique in codebase):
  → uuid:      <suggested-uuid>
    file_path: <suggested-path>
    file_name: <suggested-name>

Accept this mapping? [y/N]
```

- If the user declines, the normal menu is shown.
- If zero or more than one entry satisfies the 2-of-3 + uniqueness condition, no automatic suggestion is offered.

This rule exists to reduce friction on simple renames while remaining fully under user control.

---

## 7. Migration Plan

A migration plan is a temporary, explicit set of decisions accumulated during a `doctor` session (or constructed programmatically).

Each decision is one of:

- **repoint** — old identity → new identity  
  (updates the registry entry and all matching references in the codebase)
- **add** — insert a new registry entry (only after explicit acceptance of a “new entry” decision)
- **ignore** — record that a particular problem should be suppressed for now

Commands:

- `filereg plan show` — display the pending plan
- `filereg plan apply` — execute the plan (registry rewrite + reference rewriting)
- `filereg plan abort` — discard the plan

The plan is the only mechanism that may cause bulk changes. The library never performs reference rewriting outside of an applied plan.

---

## 8. Explicit Non-Goals (v1)

- Automatic addition of new entries without user confirmation
- Automatic rewriting of UUIDs or paths
- Heuristic “best guess” repairs beyond the strict 2-of-3 uniqueness rule
- Background daemons or file-system watchers
- Any form of auto-healing

---

## 9. Extensibility

Future versions may add:

- Custom path resolver backends
- Richer query / filter commands
- Export of plans as JSON for review or scripting
- Support for directory-only entries and VirtualFS namespaces

All extensions must preserve the invariants in §1 and §2.

---

