# Namespace Modules — API to the Metamorphosis store

This document replaces the earlier singleton / `AppNamespace` sketch.
That model described an in-process blackboard. It is not what
`Metamorphosis/servers/namespace.py` is for.

`namespace.py` is the **API access point to `metamorphosis.db`**.
Everything that needs an artifact for a serious direction goes through
it. The writer stays the persistence engine. The namespace stays slim.

---

## Place in the stage

Genesis already did its groundwork: identity, prefix, ephemeral boot
store, execution harness.

Metamorphosis has now done *its* groundwork: `Metamorphosis_DB` exists,
with structures and `metamorphosis_writer`. That is the threshold.
From here, programs do not pass code to the next program. They pass
**references**. The next program asks the namespace for what those
references name, and the namespace pulls the blob or value out of the
store.

```
egg_transpiler  ──put ref + blob──►  namespace  ──writer──►  metamorphosis.db
caterpillar     ──get ref────────►  namespace  ──writer──►  blob / value
later servers   ──get / put ref──►  namespace  ──writer──►  table + path
```

The same namespace module serves both shapes:

- **Imported** — in-process function calls. This is the current
  proving ground. No port, no transponder.
- **Served** — the same functions, reached over a transponder
  connection, once the import path is proven.

Transport changes. The request language does not.

---

## What namespace is

A thin dispatch layer over `metamorphosis_writer`.

Its job is to accept a request, decide **which structure and which
address inside that structure** the request means, and call the matching
writer operation.

| Direction | Incoming | Namespace decides | Writer call (examples) |
|-----------|----------|-------------------|-------------------------|
| Put | blob or value + address | table + virtual path, or table + key | `write_file`, `put_document`, `append_log`, `register_object` |
| Get | address | table + virtual path, or table + key | `read_file`, `get_document`, `read_log`, `get_object`, `list_objects`, `list_dir` |

It is allowed to know the five structure types. It is not allowed to
open SQLite itself, invent schema, or recreate the database.

---

## What namespace is not

- Not the bootloader. `metamorphosis_db.init_metamorphosis_db` already
  created the file and core tables. Namespace assumes the store is
  there. Missing DB is a hard error, not an init path.
- Not the writer. SQL, hashing, catalog upserts, VFS graph walks live
  in `metamorphosis_writer.py`.
- Not the prefix. `PathReffs`, `AtomicImporter`, `COMMUNICATORS_ROOT`,
  `manifest`, `transponder` arrive from Genesis when the program is
  assembled.
- Not an in-memory singleton (`BaseNamespace`, `AppNamespace`, process
  globals of dicts). Durable state is in the DB. Process memory is a
  cache at most, and is optional.
- Not the owner of port 8765 as a product feature. Binding a port is
  one access mode, deferred until import mode works.
- Not a second VirtualFS implementation. The VFS tables already live
  in the Metamorphosis store.

---

## Why this is the linchpin

Once the store holds the artifacts, the rest of Metamorphosis becomes
reference-passing:

1. A producer (egg, a control method, a later server) **puts** a blob
   or a keyed value at an address.
2. The producer hands the next stage a **reference** to that address
   (and only that).
3. The consumer **gets** through namespace and receives the blob or
   value.

Egg and caterpillar were designed around that idea even when the only
pipe they had was the transponder. `load` meant “here is a program;
put it in this namespace address.” `build` meant “get whatever lives
at this address, run a method against it, put the result at that
address.” The socket was a stand-in for the API. The API is the
namespace. The store is the DB.

That is also why namespace must parse addresses rather than accept
raw writer calls from every caller. Callers speak in namespace terms
(named places, virtual paths, keys). Namespace maps those terms onto
writer terms (structure type, table, path or key).

---

## Addressing

An address is enough information to find one thing in the store
without sending the thing itself.

Minimum fields:

- **structure** — one of the five types in
  `metamorphosis_structures.py`:
  `object_catalog`, `vfs`, `document`, `log`, `flat` / mapping.
- **table** — the concrete table, when the structure has more than
  one (`namespace_state`, a named log, a mapping table). VFS has a
  single well-known pair of tables.
- **locator** — virtual path inside VFS, document key, log stream
  name, catalog `(type, name, owner)`, or mapping row identity.

A reference is that address, optionally plus catalog metadata
(`register_object` pointer back to `table:locator`).

Callers may send a compact form. Namespace parses it.

Examples of compact forms the egg/caterpillar era already implied:

- `in state_namespace` — put or get a document named `state_namespace`
  (or a catalog entry of type `namespace` pointing at one).
- a virtual path such as `Metamorphosis/transpiler/caterpillar_transpiler.py`
  — VFS `write_file` / `read_file`.
- a catalog name — resolve via `get_object`, then follow `pointer`.

Parsing rules belong in namespace, not in every producer. Until the
grammar is frozen, the import API can take explicit kwargs
(`structure`, `table`, `path`, `key`, `name`) and derive the compact
form later for the transponder payload.

Real-filesystem identity (`FileRef` / `uuid + file_path + file_name`)
is how *code modules* find each other on disk. Store addresses are how
*artifacts inside `metamorphosis.db`* find each other. Do not collapse
the two. A FileRef can name `namespace.py`. A store address names a
row or VFS node the namespace just wrote.

---

## Request language

Two verbs. Same verbs on import and on the wire.

### Put

```
put(address, payload, *, owner=None, meta=None)
```

- `payload` is a code blob (str), a JSON-able value, or bytes the
  writer already knows how to store.
- Namespace chooses writer:
  - VFS path → `write_file(virtual_path, content)`
  - document table + key → `put_document(table, key, data, owner=…)`
  - log → `append_log(...)`
  - new named place → `register_object(...)` then the put
- Returns the reference that later gets should use (path, key, and
  catalog id when one was created).

### Get

```
get(address, *, owner=None) -> payload
```

- Namespace chooses writer:
  - VFS path → `read_file(virtual_path)`
  - document table + key → `get_document(...)`
  - catalog name → `get_object` then follow pointer if needed
  - directory → `list_dir`
- Missing address is an error the caller can handle. Namespace does
  not create-on-read.

List and debug helpers (`list_namespaces`, catalog queries) are gets
with a broader locator, not a third verb.

`initialize_namespace` from the kernel-era file, if kept at all, is
only “register this name and seed an empty document.” It must not
create the database file.

---

## Two access modes

### Import mode (now)

Prefix-assembled callers resolve `namespace.py` with `FileRef` +
`AtomicImporter` and call `put` / `get` as ordinary functions (or as
methods on the prefixed `namespace` façade).

On import, namespace:

- does **not** bind a port
- does **not** run `init_metamorphosis_db`
- does **not** kill whatever is on 8765
- may probe that the writer can connect; if the file is absent, fail
  loudly

This is the test the egg path needs: assemble the caterpillar blob,
`put` it under a VFS path and/or a namespace key, hand the next
stage the reference.

### Server mode (after import mode works)

`transponder.persistent_server` accepts connections. Each complete
message is the same request language: verb + address + optional
payload. Namespace parses, calls the same `put` / `get`, and replies
with payload or an error.

The current transponder is a byte-ACK stub. Server mode is blocked on:

- a framed message (bytes in, bytes out; no raw Python dicts on
  `sendall`)
- a handler that actually dispatches into `put` / `get`
- the import path already being correct, so the server is not
  debugging two layers at once

Egg’s `load` / `build` should call the import API first. When the
server exists, those same calls become transponder payloads without
changing address semantics.

---

## Slimness rules

`namespace.py` stays an access point.

Allowed inside it:

- address parsing
- structure-type dispatch
- thin wrappers that pick one writer function
- the import-vs-server façade
- port helpers, **only** when server mode is being brought up

Forbidden inside it:

- `sqlite3.connect`
- schema or `CREATE TABLE`
- ephemeral wipe / “ensure the DB exists”
- prefix assembly
- FileRef resolution of *other* programs except to import the writer
- embedding `load` / `build` / markdown parsing (that is egg)
- copying writer internals “to save an import”

How it reaches the writer: the same way every current Metamorphosis_DB
consumer does — `PathReffs.FileRef` for
`Metamorphosis/Metamorphosis_DB/metamorphosis_writer.py`,
`AtomicImporter.from_path_import` (or `from_code_import` of a
prefix-assembled blob) for `write_file`, `read_file`, `put_document`,
`get_document`, `register_object`, `get_object`, `list_objects`,
`append_log`, `read_log`, `list_dir`. Bare `from metamorphosis_writer
import ...` is the old world.

How callers reach namespace: the FileRef already in
`file_registry.json`

```
uuid      253a5376-dfdc-4e07-b4d1-20446bb9211f
file_path Metamorphosis/servers
file_name namespace.py
```

---

## Contract with egg and caterpillar

Egg compiles `panel.md` into `caterpillar_transpiler.py`. That
generated program is a sequence of `load` / `build` steps. Each step
names an object and one or two namespace places (`in` / `from` /
`to`).

Intended meaning, now that the store exists:

- `load object in N` — read the object (from disk only if it is not
  already in the store), `put` it at address `N` (and at a VFS path
  when the object is a file-shaped blob). Return a reference.
- `build object with method from A to B` — `get` address `A`, run
  `method`, `put` the result at address `B` and/or the VFS path for
  `object`.
- After egg finishes assembling caterpillar, egg itself `put`s the
  caterpillar source into the store and passes a **reference**, not
  the source text, to whatever runs next.
- Caterpillar, when launched through the harness, `get`s what it
  needs. It does not inherit a pile of strings through
  `subprocess` stdout as the long-term path.

Until server mode exists, `load` / `build` are in-process calls into
this module. They must not send dicts at port 8765.

`base_dir = …/state-methods` is dead. Addresses are store addresses.
On-disk inputs that still need to be ingested once (panel, ideal.yaml,
methods under `Metamorphosis/transpiler-methods/`) are FileRefs at
the edge and VFS paths once ingested.

---

## Relationship to the rest of the tree

| Piece | Relation to namespace |
|-------|------------------------|
| `metamorphosis_db.py` | Creates the file and core structures. Already run. Namespace never calls it in the happy path. |
| `metamorphosis_structures.py` | Defines the five types namespace must dispatch across. |
| `metamorphosis_writer.py` | Only persistence API namespace should use. |
| `Metamorphosis/execution/` | Harness + generated prefix dumps. Launch namespace and egg through it. Do not treat `execution/namespace.py` as source. |
| `Genesis/internal_imports/path_reffs.py` | File identity for modules on disk. |
| `Genesis/internal_imports/atomic_importer.py` | How namespace imports writer, how others import namespace. |
| `Genesis/internal_imports/transponder_module.py` | Future wire for the same `put` / `get`. Not the store. |
| `file_registry.json` | Identity of the namespace *source file*. Not the catalog of store objects. |
| `object_catalog` (inside the DB) | Identity of named store objects the namespace registered. |

---

## Durable names that already matter

The kernel-era file used a document table `namespace_state` and
catalog type `"namespace"`. Keep those as the default document
surface for named blackboards (`state_namespace`,
`ideal_state_namespace`, `Metamorphosis`, …).

File-shaped artifacts (caterpillar source, mermaid, topology JSON,
assembled prefixes that must survive a handoff) go through VFS.
The catalog pointer for those rows should be a virtual path, not a
second copy of the blob inside `namespace_state`.

Do not store a 200-line program in a document *and* in VFS without a
reason. VFS is the blob home. Documents hold maps, handles, and
small state. The catalog says which is which.

---

## Error policy

- Unknown structure or unparseable address → fail, do not guess a
  table.
- Writer cannot connect because `metamorphosis.db` is missing → fail
  with “boot the store first,” not a hidden `init_metamorphosis_db`.
- Get of a missing key/path → `None` or a typed miss the caller can
  branch on; do not insert empties on the way.
- Server-mode framed errors come back as data, not as an ACK that
  pretends the put happened.

---

## What “done enough to test import mode” looks like

1. Namespace source uses FileRef + AtomicImporter to reach the writer.
2. No `init_kernel_db` / `init_metamorphosis_db` / port bind on import.
3. `put` and `get` cover at least VFS blobs and document keys.
4. Egg (or a small test article) puts a caterpillar-sized blob and
   reads it back by reference only.
5. A second program, given only that reference, retrieves the same
   blob through namespace.

Server mode, framed transponder messages, and rewriting every
`transpiler-methods/*` absolute path are later. They are not required
to prove the linchpin.

---

## Deliberately omitted from this document

- In-memory singleton tutorials.
- Pydantic / DI / contextvar evolution paths.
- Exact on-the-wire bytes for the transponder (blocked on import
  mode).
- Per-alternative DB geometry essays. Those stay next to the
  structure module that owns the geometry.
- Philosophy restated at length. File identity, internal import,
  prefix tiers, and the ephemeral-vs-durable store split already
  live under `Philosophy/`. This file is the Metamorphosis-local
  contract that sits on top of them.
