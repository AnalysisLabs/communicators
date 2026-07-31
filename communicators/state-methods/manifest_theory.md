# Communicators Manifest Process-Path Principle

## Purpose

Manifest exists to answer one question at the moment a log line is emitted:

> Where, in the running system, did this message originate?

The answer is delivered as a compact process path of the form

```text
[program.Class.function]
```

(or a close variant that may also record an external caller). This path is the reason Manifest is used instead of raw `print` or a conventional logger.

## The Old Assumption (retired)

The original implementation presupposed that every relevant frame corresponded to a real file on disk. It therefore:

- used `__file__` to discover “internal” files,
- treated filesystem paths as the primary identity of a program, and
- walked frames under the expectation that `co_filename` and line numbers would map cleanly to source that could be opened.

That assumption held when Communicators was a library of ordinary modules. It no longer holds.

## The New Reality

A running Communicators system is a hybrid:

- some code still lives as ordinary files on disk,
- most of the boot and library surface is now assembled from the VirtualFS (SQL-backed, content-addressed, often exec’d from strings or generated artefacts),
- future execution substrates are not ruled out.

Consequently, origin tracking must not encode a preference for any single storage or loading mechanism. A process path that only works for on-disk modules, or only works for VirtualFS modules, is incomplete.

## Invariants That Remain

1. **The process path is still the product.**  
   Callers continue to receive a human-readable origin of the form `[program.Class.function]` (with optional external-caller annotation). The format may evolve slightly; the intent does not.

2. **Internal frames are filtered.**  
   Frames that belong to the Manifest implementation itself, to the injected prefix, to the tier/boot machinery, or to the language runtime are skipped in the same spirit that `/usr/lib/python` frames were skipped in the original design. The path that reaches the log should name the *user or subsystem* origin, not the logging plumbing.

3. **No single substrate is privileged.**  
   The curation logic must tolerate, and produce useful paths for:
   - real filesystem modules,
   - code loaded or exec’d from the VirtualFS,
   - synthetic or generated modules whose `co_filename` is `<string>` or another non-path token,
   - any future loader that still produces Python frames.

4. **Failure must degrade, not crash.**  
   If a particular frame lacks a usable filename, qualname, or `self`, the process path may become less specific, but logging itself must continue. Origin tracking is a quality-of-life feature layered on top of the message; it must not become a new source of fatal errors.

## Design Consequences

- Discovery of “what counts as internal” can no longer rely on `Path(__file__).parent` or on enumerating a directory. It must be expressed in terms of names, code objects, synthetic filename patterns, or explicit registries that are populated when the prefix and subsystems are built.
- Frame walking remains a viable core technique, provided the termination condition is “this frame is still inside the logging/prefix/runtime machinery” rather than “this filename lives under a particular directory.”
- Additional metaprogramming (tagging code objects at prefix-construction time, recording a boot boundary, etc.) is legitimate when it makes the internal/external distinction more reliable across substrates.
- The public surface of Manifest (`Manifest.info`, `Manifest.error`, \ldots) and the Internal “Import” Principle are unchanged; only the curation engine behind the process path is being generalized.

## Relationship to Other Principles

- **Runtime-Context Principle** — Manifest’s value appears only inside the running boot sequence. Judging the process-path logic against a single on-disk file is the same category error the Runtime-Context Principle warns against.
- **Internal “Import” Principle** — Only the deliberate public names are visible to user programs. The internal helpers that compute process paths stay behind that boundary.
- **Prefix Tiers** — The tiers are one of the substrates the process-path logic must understand and filter; they are not the only substrate.

# Pseudocode for _log
```text
function _log(level, message):

    # 1. Obtain a usable origin frame
    #    Walk upward, skipping frames that belong to:
    #      - Manifest / *_internal implementation
    #      - the injected prefix / tier machinery
    #      - the language runtime / stdlib
    #    Stop at the first frame that is “user or subsystem” code.
    #    Works whether that code came from disk, VirtualFS, <string>, or future loaders.
    origin = first_non_internal_frame()

    # 2. Build the process path from whatever the origin frame can give us
    #    (filename token, qualname, enclosing class via self if present, \ldots)
    #    Degrade gracefully when some pieces are missing.
    process_path = format_process_path(origin)
    #    → ultimately a string of the form [program.Class.function]
    #      or a close, still-useful variant

    # 3. Timestamp
    utc_ts = current_utc_isoformat()

    # 4. Emit (preserved exactly)
    if level:
        print(f'{utc_ts} {level} {process_path} {message}')
    else:
        print(f'{utc_ts} {process_path} {message}')
```

## Short Form

> Manifest still answers “where did this log come from?” with a process path.  
> It no longer assumes the answer lives on disk.  
> It must work for filesystem modules, VirtualFS modules, synthetic modules, and whatever loaders come next, while continuing to hide its own and the prefix’s frames.

The heart of Manifest is the process path.  
The body that computes it must now live comfortably in a hybrid execution world.
