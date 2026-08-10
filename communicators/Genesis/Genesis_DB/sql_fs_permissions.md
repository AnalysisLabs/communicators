# Fine-Grained Permissions Specification

**SQL Filesystem Mirror – Permissions Design**

**Convention:** Every permission is identified by a unique **32-bit unsigned integer** (`INTEGER` / `UINT32` in SQLite).  
This integer is the sole canonical identifier used in all storage, APIs, and bitmasks.

---

## 1. Core Design Principles

1. **Lookup table is the source of truth**  
   All permission names, descriptions, and categories live in a single table.  
   Application code and the filesystem never hard-code permission numbers except through this table.

2. **4-byte integer IDs**  
   - Range: `1` … `4_294_967_295` (full 32-bit unsigned).  
   - In practice we reserve the low numbers (1–1023) for the well-known core set.  
   - IDs ≥ 1024 are available for application-specific or future permissions.

3. **Storage options for a file/directory**
   - **Preferred for flexibility**: Junction table (`entry_permissions`) or a JSON array of integer IDs.
   - **Alternative for speed / ≤ 32 permissions**: A single 32-bit or 64-bit integer used as a bitmask (bit position = ID – 1).  
     With the curated list below we stay well under 64, so a `BIGINT` bitmask is viable if desired.

4. **Four logical roles (still supported)**  
   Even with fine-grained permissions we retain the four high-level roles that were discussed:
   - **Owner (Master)**
   - **Agent**
   - **Group**
   - **Others**

   These roles are *not* permissions themselves. They are used when *evaluating* which set of fine-grained permissions applies to a particular actor.

5. **Absence = deny**  
   If a permission ID is not present for an actor, the action is denied (default-deny model).

---

## 2. Recommended Schema

```sql
-- Canonical permission definitions
CREATE TABLE permission_definitions (
    id          INTEGER PRIMARY KEY,          -- unique 32-bit ID
    name        TEXT    NOT NULL UNIQUE,      -- machine name, e.g. 'read_content'
    category    TEXT    NOT NULL,             -- grouping for UI / docs
    description TEXT,
    is_directory_only INTEGER NOT NULL DEFAULT 0,  -- 1 = only meaningful on directories
    is_file_only      INTEGER NOT NULL DEFAULT 0   -- 1 = only meaningful on files
);

-- Optional: junction table (most flexible)
CREATE TABLE entry_permissions (
    entry_id    INTEGER NOT NULL,             -- FK to files or directories
    entry_type  TEXT    NOT NULL,             -- 'file' | 'directory'
    role        TEXT    NOT NULL,             -- 'owner' | 'agent' | 'group' | 'other'
    permission_id INTEGER NOT NULL,           -- FK to permission_definitions.id
    PRIMARY KEY (entry_id, entry_type, role, permission_id)
);

-- Indexes for fast checks
CREATE INDEX idx_entry_permissions_lookup
    ON entry_permissions (entry_id, entry_type, role);
```

Alternative compact storage (when the permission set stays small):

```sql
-- Store a bitmask per role
ALTER TABLE files ADD COLUMN perms_owner  INTEGER DEFAULT 0;  -- 32/64-bit bitmask
ALTER TABLE files ADD COLUMN perms_agent  INTEGER DEFAULT 0;
ALTER TABLE files ADD COLUMN perms_group  INTEGER DEFAULT 0;
ALTER TABLE files ADD COLUMN perms_other  INTEGER DEFAULT 0;
-- same columns on directories table
```

---

## 3. Curated Permission Catalog

IDs are deliberately sequential and stable.  
**Do not renumber existing IDs** once the system is in production.

### 3.1 Content Operations (IDs 1–20)

| ID | Name                  | Category          | Description |
|----|-----------------------|-------------------|-------------|
| 1  | `read_content`        | content           | Read the byte content of a file or list directory entries |
| 2  | `write_content`       | content           | Overwrite or modify the content of a file |
| 3  | `append`              | content           | Append data to the end of a file (no truncate/overwrite) |
| 4  | `truncate`            | content           | Truncate a file to zero length or a specified size |
| 5  | `delete`              | content           | Delete the file or empty directory |
| 6  | `rename`              | content           | Rename or move the entry within the same filesystem |
| 7  | `hard_link`           | content           | Create a hard link to this file |
| 8  | `symlink`             | content           | Create a symbolic link that points to this entry |

### 3.2 Directory Operations (IDs 21–40)

| ID | Name                  | Category          | Description |
|----|-----------------------|-------------------|-------------|
| 21 | `list`                | directory         | List the names of children (distinct from reading content) |
| 22 | `create_file`         | directory         | Create a new regular file inside this directory |
| 23 | `create_subdirectory` | directory         | Create a new subdirectory |
| 24 | `delete_child`        | directory         | Delete any child file or subdirectory |
| 25 | `traverse`            | directory         | Enter / traverse through this directory (execute bit analogue) |
| 26 | `search`              | directory         | Search / match patterns inside this directory |

### 3.3 Metadata & Ownership (IDs 41–60)

| ID | Name                  | Category          | Description |
|----|-----------------------|-------------------|-------------|
| 41 | `read_metadata`       | metadata          | Read size, timestamps, ownership, and other attributes |
| 42 | `write_metadata`      | metadata          | Change timestamps, size (via truncate), or custom attributes |
| 43 | `change_permissions`  | metadata          | Modify the permission set of this entry |
| 44 | `change_owner`        | metadata          | Change the owner (Master) of this entry |
| 45 | `change_group`        | metadata          | Change the group associated with this entry |
| 46 | `read_xattr`          | metadata          | Read extended attributes / custom key-value metadata |
| 47 | `write_xattr`         | metadata          | Write or delete extended attributes |

### 3.4 Advanced / Security (IDs 61–90)

| ID | Name                  | Category          | Description |
|----|-----------------------|-------------------|-------------|
| 61 | `lock`                | security          | Acquire an exclusive or shared lock on the entry |
| 62 | `snapshot`            | security          | Create a point-in-time snapshot / version of the entry |
| 63 | `restore`             | security          | Restore the entry from a previous snapshot |
| 64 | `encrypt`             | security          | Encrypt the content (or mark for encryption) |
| 65 | `decrypt`             | security          | Decrypt the content |
| 66 | `sign`                | security          | Cryptographically sign the entry |
| 67 | `verify_signature`    | security          | Verify a cryptographic signature |
| 68 | `immutable`           | security          | Make the entry immutable (cannot be modified or deleted) |
| 69 | `append_only`         | security          | Force the entry into append-only mode |
| 70 | `no_atime`            | security          | Suppress access-time updates |

### 3.5 Application / Custom Layer (IDs 91–120)

These are the permissions that map most closely to the original four-tier discussion and your “Agent” role.

| ID | Name                  | Category          | Description |
|----|-----------------------|-------------------|-------------|
| 91 | `agent_execute`       | application       | Special permission granted only to the “Agent” role |
| 92 | `master_full_control` | application       | Convenience permission that implies every other permission (Owner only) |
| 93 | `version_read`        | application       | Read historical versions of the entry |
| 94 | `version_write`       | application       | Create or prune historical versions |
| 95 | `comment`             | application       | Add or edit comments / annotations attached to the entry |
| 96 | `tag`                 | application       | Add, remove, or modify tags |
| 97 | `archive`             | application       | Mark the entry for long-term archival / cold storage |
| 98 | `offline`             | application       | Mark the entry as residing on slow / offline media |

---

## 4. Role Evaluation Model

When an actor attempts an action the system evaluates in this order:

1. **Owner (Master)** – if the actor is the owner, use the Owner permission set.
2. **Agent** – if the actor is acting as the designated Agent for this entry (or globally).
3. **Group** – if the actor belongs to the entry’s group.
4. **Others** – fallback for everyone else.

Each role has its own independent set of the fine-grained permission IDs above.

---

## 5. Suggested Starter Set for v1

For the first working version of the SQL filesystem mirror it is recommended to implement only a **minimal subset** that still gives real value:

**Must-have (IDs to implement first):**

```
1  read_content
2  write_content
5  delete
21 list
22 create_file
23 create_subdirectory
24 delete_child
25 traverse
41 read_metadata
42 write_metadata
43 change_permissions
```

Everything else can be added later without breaking existing IDs.

---

## 6. Example Usage Patterns

### Checking a permission (junction-table style)
```sql
SELECT 1
FROM entry_permissions
WHERE entry_id = ?
  AND entry_type = 'file'
  AND role = 'owner'
  AND permission_id = 2;          -- write_content
```

### Granting a set of permissions to Owner
```sql
INSERT INTO entry_permissions (entry_id, entry_type, role, permission_id)
VALUES
  (42, 'file', 'owner', 1),   -- read_content
  (42, 'file', 'owner', 2),   -- write_content
  (42, 'file', 'owner', 5);   -- delete
```

### Convenience: full control for Owner
```sql
-- Using the special master_full_control permission
INSERT INTO entry_permissions (entry_id, entry_type, role, permission_id)
VALUES (42, 'file', 'owner', 92);
```

---

## 7. Migration & Stability Notes

- IDs in the ranges 1–120 are considered **stable**.  
  Never reassign or delete them once released.
- Application-specific permissions should start at ID 1024 or higher.
- When adding a new permission, always insert a row into `permission_definitions` first; never invent IDs on the fly in application code.

---

## 8. Relationship to Classic Unix Permissions

The classic Unix `rwx` bits can be expressed as a mapping onto the fine-grained set:

| Unix bit | Rough equivalent permissions |
|----------|------------------------------|
| `r` (file)   | `read_content` + `read_metadata` |
| `w` (file)   | `write_content` + `append` + `truncate` + `delete` |
| `x` (file)   | (execution – not modelled here unless you add an `execute` permission) |
| `r` (dir)    | `list` + `read_metadata` |
| `w` (dir)    | `create_file` + `create_subdirectory` + `delete_child` |
| `x` (dir)    | `traverse` |

You can keep a helper that converts a classic mode (e.g. 0755) into the corresponding set of fine-grained IDs if you ever need to import or export Unix-style permissions.

---

*Document version: 1.0*  
*Designed for the limited-scope SQL filesystem mirror project.*  
*Last updated: 2026-07-21*
