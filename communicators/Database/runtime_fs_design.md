# Runtime Generated Files → SQLite VirtualFS

Design capture for replacing `temp/` writes with an ephemeral SQLite-backed virtual filesystem.

---

## Goal

All programs written by the author require an execution harness (dozens to hundreds of lines).  
The current bootloader combines a prefix + user program and writes the result to:

```
internal/temp/{uuid}.py
```

This is being replaced by an in-process SQLite virtual filesystem so that runtime-generated files live in a queryable, permission-gated store instead of loose files on disk.

Micro-goal: get the combined sources into the database and be able to retrieve them.  
Process launching / execution is out of scope for the first cut.

---

## Core Rules

- The database is **created fresh on every run**.  
  No persistence across restarts is required or desired at this stage.
- Initialization of the tree is done with **nested conditionals and loops in pure Python**.  
  No JSON / YAML / declarative seed file.
- The system is intentionally no more complex than a normal filesystem permission model.  
  It is **not** encryption; it is lightweight shared-secret gating to prevent careless overwrites.

---

## Schema

Two tables only.

### `contents` (payload storage, content-addressed)

```sql
CREATE TABLE contents (
    id          INTEGER PRIMARY KEY,
    hash        TEXT    NOT NULL UNIQUE,   -- sha256 of the data
    data        TEXT    NOT NULL,
    size        INTEGER NOT NULL
);
```

### `nodes` (filesystem tree + metadata)

```sql
CREATE TABLE nodes (
    id          INTEGER PRIMARY KEY,
    parent_id   INTEGER REFERENCES nodes(id) ON DELETE CASCADE,  -- NULL = root
    name        TEXT    NOT NULL,                                -- basename only
    type        TEXT    NOT NULL CHECK(type IN ('file', 'dir')),
    content_id  INTEGER REFERENCES contents(id),                 -- NULL for directories
    access_tier TEXT    NOT NULL DEFAULT 'others'
                        CHECK(access_tier IN (
                            'human_owner', 'agent_user', 'group', 'others'
                        )),
    created_at  TEXT    NOT NULL
                        DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),

    UNIQUE(parent_id, name)
);
```

Root node has `parent_id = NULL` and `name = ''`.

---

## Permission Model

Four tiers with a strict total order:

```
human_owner  >  agent_user  >  group  >  others
```

| Tier          | Password (temporary) | Typical use                          |
|---------------|----------------------|--------------------------------------|
| `human_owner` | `"123"`              | Critical / dangerous files           |
| `agent_user`  | `"444"`              | Agent-controlled runtime artifacts   |
| `group`       | `"321"`              | Normal read/write, non-critical      |
| `others`      | (none)               | Public / no protection               |

Rules:

- Presenting a higher tier’s password grants access to every lower tier.
- Anything other than `others` requires the matching password.
- A single `access_tier` column currently controls both read and write.
- When a new node is created it receives the caller’s tier (or an explicit override).
- The purpose is only to stop careless or buggy code inside the same system from overwriting important material. It is deliberately weak and can be hardened later.

Comparison to traditional filesystems: normal permission checks (owner/group/other or ACLs) are identity-based and involve **no encryption**. Encryption is a separate at-rest protection layer. The model above is closer to classic FS permissions than to encryption.

---

## Initial Tree Construction

Done entirely in Python with nested conditionals / loops. Example shape:

```python
def _initialize_tree(self):
    root_id = self._insert_node(parent_id=None, name="", node_type="dir",
                                tier="human_owner")
    runtime_id = self._insert_node(parent_id=root_id, name="runtime",
                                   node_type="dir", tier="agent_user")
    self._insert_node(parent_id=runtime_id, name="generated",
                      node_type="dir", tier="group")
    # further nested creation as needed
```

---

## Public API Shape

```python
vfs = VirtualFS(db_path)          # creates DB + tables + initial tree

vfs.write(path, data, *, tier="group", password="321", access_tier=None)
data = vfs.read(path, *, tier="group", password="321")
entries = vfs.listdir(path, *, tier="group", password="321")
```

- Paths are virtual (e.g. `"runtime/generated/{uuid}.py"`).
- Every mutating or reading call must supply a tier + password except when the target is `others`.
- The rest of the system never touches SQL directly.

---

## Integration Point in Bootloader

Replace the block that currently does:

```python
temp_dir = Path(resolve_path("internal", "temp"))
temp_dir.mkdir(exist_ok=True, parents=True)
temp_file = temp_dir / f"{uuid.uuid4().hex}.py"
temp_file.write_text(combined)
```

with a call of the form:

```python
virtual_path = f"runtime/generated/{uuid.uuid4().hex}.py"
vfs.write(virtual_path, combined,
          tier="agent_user", password="444",
          access_tier="agent_user")
```

The compiled code object is still produced the same way; only the storage of the combined source changes.

Database location (when running inside a real communicators tree):

```
<communicators-root>/internal/runtime_fs.db
```

Because the DB is ephemeral, it is safe to delete-and-recreate on every bootloader start.

---

## Open / Deferred Items

- Separate `read_tier` / `write_tier` columns (currently one tier controls both).
- Auto-creation of intermediate directories on write.
- Stronger passwords / secret storage later.
- Moving additional runtime artifacts (transpiler output, namespace dumps, etc.) into the same virtual FS.
- Restoring the actual subprocess launch path once storage is proven.

---

## Status at Time of Capture

- Schema, tier model, and ephemeral-lifecycle rules are settled.
- A working VirtualFS implementation and a bootloader that stores + retrieves combined sources have been demonstrated in a sandbox.
- Process execution is deliberately still disabled so the micro-goal stays focused on storage + retrieval only.
