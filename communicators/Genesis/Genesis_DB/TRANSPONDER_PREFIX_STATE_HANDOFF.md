# Transponder prefix — stateful Stage B handoff

Date: 2026-09-10  
Branch: `variant/staged/staged-2`  
Repo: https://github.com/AnalysisLabs/communicators/tree/variant/staged/staged-2/communicators

This note is for a **fresh session**. It is the decision record, not a transcript. The builder merge worked. Genesis writes a prefix. Metamorphosis dies inside that prefix because hatch types were written as many instances and Stage B compiles them as PathReffs-shaped singletons. Tomorrow’s work is to make the hatch modules match Stage B, not to fork Stage B.

---

## 1. Where the tree is

### What already shipped

- `prefix_builder.py` owns `_load_source`, FileRefs, `MEMBERS`, the AST cutter, `fill_queue`, `emit_prefix`.
- `_load_source(ref)`: `str` → `read_file` (VirtualFS); `FileRef` → `resolve_path` + disk.
- No `build_prefix0/1/2` as the law. Those names are thin wrappers around `emit_prefix(through_tier=N)`.
- `build_prefixA()` = `transpile_to_tier_d(emit_prefix())`. Tier A is still Stage B+C+D on the **full** concat, including the stack.
- `--write` produces tiers 0–4 plus A. Last successful Genesis run: prefix ~125k chars, node ids 8–14.
- After Stage B, **PathReffs / AtomicImporter / Manifest** match `Metamorphosis/execution/prefix.py` byte-for-byte (old gold).
- T0 is live `standard.py`, not the old baked snapshot. That is why `ctypes` / `fcntl` / `select` appeared.

### Boot landmines already fixed (do not re-diagnose)

1. `file_registry.json` line ~277: missing comma after `wire_prototype(preserve_but_ignore).py`. Boot died in `path_reffs._load_registry` **before** Genesis built the DB. Not a builder bug.
2. `standard.py` imported `sellect`. First Metamorphosis `exec` died on prefix line 6. Changed to `select`. Rebuild prefix after any T0 edit.

### Current failure (end of day)

```text
_DirWatch_internal = DirWatch_internal()
TypeError: missing 2 required positional arguments: 'directory' and 'filename'
```

Filename in the traceback is `metamorphosis_bootloader.py` only because the prefix is prepended. Line ~598 is Stage B’s unconditional construct. Metamorphosis body has not run. `DirWatch` is the first hatch class in emit order whose internal `__init__` is not zero-arg. The same landmine is waiting on `TcpSlot`, `UnixSlot`, `WsSlot`, `ShmSlot`, `HttpSlot`, mailbox pair, `Station`, `Tuner`, `Wire`, `NegativeCom`, `PositiveCom`.

Standalone stack (two terminals, `shm_slot.py`) never ran Stage B. `DirWatch(dir, file)` as a normal instance is the spelling that **worked there** and **does not survive here**.

---

## 2. Architecture that is not up for debate

### Stage B stays

Emission for every marked class:

```text
class Name_internal: ...
_Name_internal = Name_internal()
class Name: ...          # public façade, external/dual methods as @staticmethod
```

Do not skip Stage B on the stack. Do not add a “stateful track” that leaves hatch types unsplit. Do not remove construct, C.a, C.b, or C.c. **Adds** to the transpiler are allowed. Removals are not.

### What the split is for

Filter user-reachable names (`DirWatch.wait`, `Wire.attach`, `NegativeCom.to_N`) from names the user program is not supposed to type (`_lock`, `_drain`, `_watch_loop`). Classic modules already look like this: Manifest public methods are thin passthroughs onto `_manifest_internal._log`. PathReffs public `resolve_path` does not hold the registry.

The split is **not** “instances versus functions.” It is **façade versus engine**.

### Cardinality Stage B already chose

One `_Name_internal` per class **per exec**. Each user program / combined script gets its own prefix globals. FOX and OTTER were already two processes. The zoo being prevented is two `DirWatch` objects **inside one script**, not two programs sharing a watch.

If one script later needs two watches, that is a **dict on the singleton**, not a second class pair.

### Modules conform to Genesis_DB

Hatch types move toward PathReffs. Genesis_DB does not grow a second public/`_internal` meaning for “stateful.”

---

## 3. What we ruled out (and why)

These were discussed at length. Do not reopen them tomorrow without a new fact.

### Skip Stage B on T1 helpers + T2–T4

Would keep standalone instance spelling. Would also ship `@externalmethod` into Metamorphosis and break the PathReffs/AtomicImporter/Manifest façade Metamorphosis already uses if applied to the whole prefix. Partial “transpile only through Manifest, append raw stack” was rejected: hatch types must conform, not get a private pipeline.

### Make modules stateless

Slots have fds, threads, bins. Impossible. The correct sentence is: **state lives on `_Name_internal`**. Public methods do not hold it. PathReffs_internal already caches the registry. That is not stateless; it is singleton state.

### `@externalmethod` on `__init__` (or “keep `__init__` on the public class”)

Looks like it fixes `_DirWatch_internal = DirWatch_internal()`.

- If `__init__` is `@externalmethod`, Stage B still makes it `@staticmethod`. `DirWatch(dir, file)` may write `fd` onto a **public husk**. Public `wait` is also static; `watch.wait(timeout)` does not bind that husk. Crash moves from construct to first `wait`.
- If Stage B special-cases `__init__` (public, not static) but leaves `wait` / `_lock` as they are: construct works; **internal methods still run on the empty singleton**. `ShmSlot.__init__` sets `bin_path` on the husk; `_lock` reads `_ShmSlot_internal.bin_path` which was never set.

`__init__` on the public class only works if **every** method that shares those fields is also a real instance method on that same object. That is “drop the split for anything with state.” Forbidden.

### Teach Stage C to rewrite `DirWatch.EVENT_HDR` → `DirWatch_internal.__init.EVENT_HDR`

Wrong target name. After construct the field is `_DirWatch_internal.EVENT_HDR`.

Stage C only rewrites **bare calls**:

```text
name(   →  _Name_internal.name(     # C.a, public methods
name(   →  self.name(               # C.b, internal methods
```

It does not rewrite `Name.attr`, `self.attr`, or `self.Name.attr`. That is by design (PathReffs public bodies call `_load_registry()`, they do not say `PathReffs._load_registry`). An attribute-rewrite pass is an optional **add**, and only after construct is zero-arg. It is not required if public methods are thin `return _wait(...)`.

`self.DirWatch.EVENT_HDR` was a source typo, not a missed C rewrite.

### Fork the transpiler into stateless-track / stateful-track

Pays for the filter twice, then invents a weaker one. User programs would reach `_drain`. Markers on the stack become decoration. Not the direction.

### Dummy defaults on `DirWatch.__init__`

Papers over line 598. Leaves `@staticmethod def wait(self, timeout)` and every other hatch ctor intact. Next crash is `TcpSlot`.

### Two methods named `wait` in the pre-split class

```python
@internalmethod
def wait(self, timeout): ...

@externalmethod
def wait(timeout):
    return wait(timeout)
```

Illegal: second def wins. `@dualmethod` is also wrong: B copies **one** body to both sides, so a thin wrapper would be thin (and recursive) on the internal side.

**Required source shape** (PathReffs helpers):

```python
@internalmethod
def _wait(self, timeout: float) -> bool:
    ...

@externalmethod
def wait(timeout: float) -> bool:
    return _wait(timeout)
```

C.a → `return _DirWatch_internal._wait(timeout)`.

---

## 4. The direction (do this)

Refactor transponder-adjacent modules so the public class is a **strong, thin façade** and `_Name_internal` is the **persistent engine**.

### Per class

1. `@internalmethod def __init__(self):` — zero required args. Optional: libc / masks / empty fields (`fd = None`).
2. Required construct args move to `@internalmethod def _open(...)` / `_attach(...)`.
3. Real work stays `@internalmethod` with a leading underscore (`_wait`, `_close`, `_lock`, `_drain`).
4. User-facing names are `@externalmethod` with **no `self`**, body only `return _foo(...)`.
5. Call sites inside the stack and in standalone CLIs: `DirWatch.open(...)`, `DirWatch.wait(...)`. No `self.watch = DirWatch(...)`.
6. `@dualmethod` only when **both** sides should contain the **same** non-recursive body. Do not use dual for “fat engine + thin façade.”

### Optional transpiler adds (not required to start the module edit)

- **Construct helper** in Stage B: always bind `_Name_internal`; call `__init__` only if it is zero-arg; otherwise leave the raw instance and require `_open`. This is insurance so a missed two-arg `__init__` does not kill import. It does not inject constructor args by itself.
- **Public attribute pass** in Stage C: `Name.attr` / leftover `self.attr` → `_Name_internal.attr`. Convenience while bodies are still fat. Skip it if façades are thin. Never emit `Name_internal.__init.ATTR`.

Do not add a rule that parks `__init__` on the public class.

### Multiplicity

Default: one engine per class per script. Faces already intend this (`__new__`). Wire holds one slot. Standalone = one slot per process.

If one script needs two shm pairs: `self._watches[(dir, file)] = fd` on `_DirWatch_internal`. Same class pair.

---

## 5. Stage B / C / D cheat sheet

File: `Genesis/Genesis_DB/prefix_transpiler.py`

| Stage | Job |
|---|---|
| B | Split by markers. Internal + dual → `Name_internal`. External + dual → public, marker becomes `@staticmethod`. Then `_Name_internal = Name_internal()`. |
| C.a | Public methods: bare callee that exists on internal (func ∪ nested) → `_Name_internal.name(` |
| C.b | Internal methods: sibling bare callee → `self.name(` |
| C.c | Internal signatures start with `self` |
| D | Blank-line collapse |

B only slices **methods** and **nested classes**. Assignments between `class Name:` and the first method are glued onto the first method’s range. Class-level `IN_MODIFY` / `BIN_DIR` / `FEATURES` / `TOKEN_RE` are therefore unreliable as `Class.ATTR` on the **public** class after B. Constants used from other modules (`Transponder_Locators.BIN_DIR`, `Wire.FEATURES`) must remain reachable on the public name or via a getter. Putting one-time `CDLL(...)` in zero-arg internal `__init__` is correct (runs once at construct).

C.c will inject `self` into **any** internal `def`, including `__new__`. Current prefix already shows `def __new__(self, cls, config)` on `NegativeCom_internal`. Stop marking `__new__`, or stop using `__new__` and let `_NegativeCom_internal = NegativeCom_internal()` be the singleton (it already is).

---

## 6. Evidence already in the emitted prefix

`Metamorphosis/execution/prefix.py` (~125k) is Stage D of the full stack. Useful exhibits:

- `Transponder_Codec` / `Transponder_Locators`: empty `_internal` + `pass`, public methods doubled `@staticmethod` (B added static on methods that were already static-shaped). Harmless noise.
- `SlotRefused`: public `@staticmethod def __init__(self, slot, verb, flag, detail="")` plus `super().__init__(...)`. Exception types are **not** hatch modules. Do not façade them. Unmark `__init__` or keep SlotRefused as a plain `Exception`.
- `DirWatch_internal.__init__(directory, filename)` then `_DirWatch_internal = DirWatch_internal()` — the crash.
- Public `DirWatch.wait` still uses `self.fd` and `DirWatch.EVENT_HDR`. After the user’s revert, `EVENT_HDR` is assigned on the internal instance in `__init__`, so the public class has no such attribute. C will not rewrite it.
- `Wire.FEATURES`, `Wire.FALLBACK` used in public staticmethods as `Wire.FEATURES` — may or may not exist on the public class after B depending on where those assignments sat.
- Faces: `__new__` corrupted as above; `inject_echo_payload` as decorator on public staticmethods; `freight` / `truncate` / `generate_unique_socket_path` still assumed in scope (T0 leftovers from the original handoff — not fixed).

Gold comparison (do not expect T0 identity with the **old** prefix): old T0 lacked `ctypes`, `fcntl`, `stat`, `urllib`, `select`. Live `standard.py` is the source of truth.

---

## 7. Membership table (emit order)

`MEMBERS` in `prefix_builder.py`. T1 scaffold `0–2`, helpers start at `10`.

| Tier.order | class_name | prepare | ref |
|---|---|---|---|
| 0.00 | standard | whole_file | `_STANDARD_REF` |
| 0.01 | COMMUNICATORS_ROOT | generated | — |
| 1.00 | PathReffs | whole_file | `"Database/path_reffs.py"` |
| 1.01 | AtomicImporter | whole_file | `"Database/atomic_importer.py"` |
| 1.02 | Manifest | whole_file | `_MANIFEST_REF` |
| 1.10–1.15 | Transponder_Codec, Transponder_Locators, SlotRefused, DirWatch, UdpMail, Mailbox | cut_class | stack FileRefs (shared files) |
| 2.00–2.08 | TcpSlot … Tuner | cut_class | stack FileRefs |
| 3.00 | Wire | cut_class | `_WIRE_REF` |
| 4.00–4.01 | NegativeCom, PositiveCom | cut_class | `_TRANSPONDER_REF` |

`prepare=whole_file` for VFS PathReffs / AtomicImporter: those copies are already marked (and after A, split). Do not `cut_class` them or you emit `PathReffs_internal` as its own member.

Obsolete T2 blob (`transponder` / `0f589da7-…`) is not a row. Faces come from `transponder_module.py` (`b03e35ee-…`).

---

## 8. Suggested edit order tomorrow

Do **DirWatch + ShmSlot call sites first**. That is the crash and the template.

1. `DirWatch` in `shm_slot.py`
   - zero-arg `__init__`: masks, `EVENT_HDR`, `CDLL`, `fd = None`, `filename = None`
   - `_open(directory, filename)` internal; `open(...)` external thin
   - `_wait` / `_close` internal; `wait` / `close` external thin
   - `WATCH_MASK = self.IN_MODIFY | ...` not bare `IN_MODIFY`
   - no `DirWatch.libc` from the public class
2. `ShmSlot.attach` / `_watch_loop` / `close`: `DirWatch.open(...)`, `DirWatch.wait(...)`, `DirWatch.close()`. Drop `self.watch`.
3. Rebuild prefix (`./run.sh` or `prefix_builder.py --write`). Confirm import gets past DirWatch construct.
4. Next ctor in the log (`TcpSlot` / `WsSlot` / `ShmSlot` itself / `Wire` / faces). Same recipe.
5. Only then consider B construct-insurance and/or C attribute pass.
6. Leave `SlotRefused` and face `__new__` as explicit exceptions to the cookie cutter.

Do not start a Stage C attribute rewriter on day one. Thin façades make it unnecessary for the methods you touch.

---

## 9. File map

| Path | Role |
|---|---|
| `Genesis/Genesis_DB/prefix_builder.py` | Concat law. `MEMBERS`, cutter, emit, `--write` |
| `Genesis/Genesis_DB/prefix_transpiler.py` | B/C/D. Adds only |
| `Genesis/Genesis_DB/vfs_writer.py` | `read_file` / `write_file` |
| `Genesis/internal_imports/standard.py` | T0 imports (live) |
| `Genesis/internal_imports/edge-methods/transponder_stack/*.py` | Hatch sources the cutter reads |
| `Metamorphosis/execution/prefix.py` | Last A output copied for exec |
| `Metamorphosis/execution/execution_launcher.py` | `exec` of prefix + program |
| `file_registry.json` | Must parse; no missing commas |

`prefix_queue.py` / `prefix_emit.py` were precursors. The builder no longer imports them. Treat as history unless someone still runs them standalone.

Working standalone (instance-shaped, no Stage B): the `transponder_stack` programs as ordinary scripts, two terminals. Use as behavior reference, not as prefix shape reference.

---

## 10. One-sentence brief for the next session

Keep Stage B’s public / `_internal` split; move hatch **state and work** onto `_Name_internal` with zero-arg construct plus `_open`; make `@externalmethod` a one-line call to `_foo`; fix call sites to `Class.foo(...)`; add construct insurance in B only after that shape exists; do not fork the transpiler, do not park `__init__` on the public class, do not ask C to rewrite `Class.ATTR` until façades are thin.
