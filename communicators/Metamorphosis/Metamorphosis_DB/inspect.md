**Metamorphosis DB – manual inspection cheat sheet**

Same idea as the Genesis `inspect.txt`: no inspection module, just commands you can paste. Assumes you are already inside the Nix flake shell (or any environment where `python3` + the stdlib `sqlite3` module work).

```bash
nix --extra-experimental-features "nix-command flakes" develop .
```

Default DB path (from the file registry / `DEFAULT_DB_FILE`):

```text
Metamorphosis/Metamorphosis_DB/metamorphosis.db
```

From the communicators root:

```bash
cd Metamorphosis/Metamorphosis_DB
```

(or keep using the full relative path in the snippets below).

---

### 0. What tables exist right now?

```bash
python3 -c '
import sqlite3
conn = sqlite3.connect("metamorphosis.db")
for row in conn.execute("SELECT name, type FROM sqlite_master WHERE type IN (\"table\",\"index\") ORDER BY type, name"):
    print(row)
'
```

After a fresh boot you should see at least:

- `object_catalog`
- `file_contents`
- `file_graph`

(plus internal `sqlite_*` bits). Document / log / flat tables appear only after something calls the typed helpers in `metamorphosis_writer`.

---

### 1. `object_catalog` — top-level registry

```bash
python3 -c '
import sqlite3
conn = sqlite3.connect("metamorphosis.db")
for row in conn.execute("""
    SELECT id, type, owner, name, pointer, metadata, created_at, updated_at
    FROM object_catalog
    ORDER BY id
"""):
    print(row)
'
```

Filter by type or owner:

```bash
python3 -c '
import sqlite3
conn = sqlite3.connect("metamorphosis.db")
for row in conn.execute("""
    SELECT id, type, owner, name, pointer
    FROM object_catalog
    WHERE type = ?
    ORDER BY id
""", ("vfs_node",)):
    print(row)
'
```

---

### 2. VFS – hierarchy (`file_graph`)

```bash
python3 -c '
import sqlite3
conn = sqlite3.connect("metamorphosis.db")
for row in conn.execute("""
    SELECT id, parent_id, name, type, content_id, access_tier,
           created_at, updated_at
    FROM file_graph
    ORDER BY id
"""):
    print(row)
'
```

Roots only (`parent_id IS NULL`):

```bash
python3 -c '
import sqlite3
conn = sqlite3.connect("metamorphosis.db")
for row in conn.execute("""
    SELECT id, name, type, content_id, access_tier, created_at, updated_at
    FROM file_graph
    WHERE parent_id IS NULL
    ORDER BY id
"""):
    print(row)
'
```

---

### 3. VFS – payloads (`file_contents`)

Metadata (no blob dump):

```bash
python3 -c '
import sqlite3
conn = sqlite3.connect("metamorphosis.db")
for row in conn.execute("""
    SELECT id, hash, size, length(data)
    FROM file_contents
    ORDER BY id
"""):
    print(row)
'
```

Dump one payload by content id (replace `1` as needed):

```bash
python3 -c '
import sqlite3
conn = sqlite3.connect("metamorphosis.db")
row = conn.execute("SELECT data FROM file_contents WHERE id = 1").fetchone()
print(row[0] if row else "<missing>")
'
```

Join graph → content (path-ish listing with sizes):

```bash
python3 -c '
import sqlite3
conn = sqlite3.connect("metamorphosis.db")
for row in conn.execute("""
    SELECT g.id, g.parent_id, g.name, g.type, g.content_id,
           c.size, c.hash
    FROM file_graph g
    LEFT JOIN file_contents c ON c.id = g.content_id
    ORDER BY g.id
"""):
    print(row)
'
```

---

### 4. Quick “is the DB alive?” smoke check

```bash
python3 -c '
import sqlite3
from pathlib import Path
p = Path("metamorphosis.db")
print("exists:", p.exists(), "size:", p.stat().st_size if p.exists() else None)
conn = sqlite3.connect(p)
print("tables:", [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type=\"table\" ORDER BY name")])
print("catalog rows:", conn.execute("SELECT COUNT(*) FROM object_catalog").fetchone()[0])
print("graph rows:", conn.execute("SELECT COUNT(*) FROM file_graph").fetchone()[0])
print("content rows:", conn.execute("SELECT COUNT(*) FROM file_contents").fetchone()[0])
'
```

---

### 5. When later tables appear (documents / logs / flat maps)

After something has created them via the writer helpers:

```bash
python3 -c '
import sqlite3
conn = sqlite3.connect("metamorphosis.db")
tables = [r[0] for r in conn.execute(
    "SELECT name FROM sqlite_master WHERE type=\"table\" AND name NOT LIKE \"sqlite_%\" ORDER BY name"
)]
print("all user tables:", tables)
for t in tables:
    if t in ("object_catalog", "file_graph", "file_contents"):
        continue
    n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    print(f"  {t}: {n} rows")
'
```

Then inspect a specific dynamic table the same way as above (`SELECT * FROM <name> ORDER BY id LIMIT 20`, etc.).

---

**Note:** If you run these from the communicators root instead of `Metamorphosis/Metamorphosis_DB`, use:

```python
sqlite3.connect("Metamorphosis/Metamorphosis_DB/metamorphosis.db")
```

in every snippet.
