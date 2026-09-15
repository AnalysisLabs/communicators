# Transponder — MOC

Edge I/O spine of Communicators OS. Two processes exchange JSON dicts
(**freight**) without the rest of the OS caring which medium carried them.

Not the graph, not the namespace store, not the prefix assembler. Those
consume it. Namespace is **imported** first, later **served** over a
transponder; the request language stays the same.

## Layers

Only Wire and the faces are the advertised prefix API. Slots are a legal hatch.

```text
Imago / user programs     NegativeCom / PositiveCom     Tier 4 faces
Metamorphosis glue        attach + inject (not a module)
Metamorphosis raw         Wire                          Tier 3 session
hatch                     TcpSlot UnixSlot WsSlot ShmSlot   Tier 2
shared                    Codec Locators DirWatch …     Tier 1
stdlib                    standard.py                   Tier 0
```

- **Slots** — one medium. Bind-or-connect, frame, `_write`, inbound `on_payload`.
  No fallbacks if you skip Wire.
- **Wire** — attach one slot; fallback **at attach time only** (loopback default
  `tcp → unix → shm`). Then `send(dict)` and an inbound callback. Illegal verbs
  raise via `SlotRefused` (not settled whether that type is an Exception).
- **Faces** — queues, `communicator_token`, protocol echo,
  `to_N` / `from_N` / `to_P` / `from_P`. Join is **injection**, not import:

```text
wire.attach(..., on_message=lambda msg: face.receiver(wire, msg))
face.attach_wire(wire)
face.sender → wire.send
slot inbound → on_payload → face.receiver
```

`boot_wire` / `pair_boot` are demo join recipes, not prefix modules.

Same-tier modules must not call each other (`Prefix_Tier_Principle`).
`DirWatch` sits in T1 so `ShmSlot` can stay T2. Wire cannot be T2 because
it sees more than one slot.

User-visible after Tier A trim: `NegativeCom`, `PositiveCom`, `Wire`.
`transponder_*` is the hatch module spelling.

## Polarity and freight

| Face | Role | Verbs |
|------|------|--------|
| **NegativeCom** | Initiates | `to_N` send, `from_N` receive |
| **PositiveCom** | Accepts and remembers | `from_P` receive, `to_P` reply |

Down = middleware → communicator. Up = communicator → middleware.

`communicator_token` lives in freight, **above** Wire. Positive replies reuse
the prompt’s token. Echo `{received: token}` is protocol, not application
freight; `wait_for_echo` must see it without discarding. A daemon pump off
`attach_wire` runs `process_up_queue` so the recv thread does not block
inside `wait_for_echo`.

Obsolete for payload I/O: `WSTamer`, `UnixSocketClientSync`.

## Proven vs in flight (as of 2026-09-15)

**Proven** (standalone two OS processes, not `test_faces.py`): client `to_N`
one prompt; bot `from_P`; bot `to_P` three freight replies; client `from_N`
on a persistent Wire. Default row tcp, fallback unix, last resort shm.
Client exit after three replies is demo-only.

**In flight:** the same stack concatenated into the Genesis prefix and
split by Stage B into `Name_internal` / public façade. Hatch types were
written as instances; Stage B constructs them as PathReffs-shaped
singletons. First crash: `_DirWatch_internal = DirWatch_internal()`
missing `directory` and `filename`. Fix is hatch shape (zero-arg internal
`__init__`, thin `@externalmethod`), not a second transpiler.

HTTP / mailbox / station-tuner exist on disk under `transponder_stack/`
and may stay off `MEMBERS` until a fallback row needs them.

Acceptance bar for prefix integration: two-process chat against a
**prefix-built** program, not `chat_*.py` as ordinary scripts. Boot
success is weaker: `./run.sh` execs the prefix without hatch construct
errors.

## Links

- [[transponder graph]] — import map of the standalone stack
- [[TRANSPONDER_PREFIX_HANDOFF]] — slots → Wire → faces → prefix tiers
- [[TRANSPONDER_PREFIX_HANDOFF_2]] — membership table, current file state
- [[TRANSPONDER_PREFIX_STATE_HANDOFF]] — Stage B singleton vs instance ctors
- [[Prefix_Tier_Principle]]
- [[Internal_Import_Principle]]
- [[Runtime_Context_Principle]]
- Session job: `2026-09-15.md` at the worktree root

On disk: `Genesis/internal_imports/edge-methods/transponder_stack/`.
Builder law: `MEMBERS` in `Genesis/Genesis_DB/prefix_builder.py`.
Do not load `Slots/`, the old `transponder_module.py` blob, or
`wire_prototype`.

## Changelog

- 2026-09-15: Initial MOC from a grok session reading the tree and the
  three prefix handoffs. Not a spec freeze. Hatch-to-prefix construct
  was still failing at DirWatch.
