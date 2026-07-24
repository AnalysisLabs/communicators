# Communicators Runtime-Context Principle

## Core Claim

Almost nothing in the Communicators ecosystem makes sense when examined in isolation.  
Meaning, correctness, and even basic executability appear only when a piece is viewed inside the full boot / load sequence that actually runs it.

## What This Means in Practice

- A module’s source may look incomplete, circular, or even broken when read by itself.
- Imports that appear missing are often supplied by an earlier tier of the prefix.
- Names that seem undefined are injected at load time.
- Side-effects that look dangerous (starting servers, killing ports, writing to the VirtualFS) are ordered so that they become safe only because of what has already run.
- Error paths, logging, and control flow frequently depend on objects that do not exist until a previous stage has finished.

Therefore:

> **Judging any single file, class, or function outside the runtime sequence in which it is loaded is usually a category error.**

## Consequences for Design & Debugging

1. **Reading order is not source order.**  
   Always ask “when does this code actually execute?” before asking “does this code look correct?”

2. **The prefix is the real program.**  
   User modules (`namespace.py`, `egg_transpiler.py`, …) are only the final fragment. The assembled prefix + user source is the unit that must be coherent.

3. **Isolation is intentional but incomplete.**  
   Temporary `ModuleType`s create deliberate boundaries, yet those boundaries are crossed by explicit injection. The resulting graph is only visible at boot time.

4. **Bugs often live in the seams.**  
   Most failures are not inside a module but in the contract between tiers or between the prefix and the program that follows it.

5. **Documentation must describe sequences, not just artifacts.**  
   A description of `Manifest` or `transponder` that does not mention *when* and *how* they are bound is incomplete.

## Short Form (for quick reference)

> In Communicators, almost nothing makes sense in isolation.  
> Coherence is a property of the boot sequence, not of any individual file.

This principle is the reason the Tiers system, the VirtualFS prefix, and the execution harness exist. They are the concrete machinery that turns an otherwise incomprehensible collection of interdependent pieces into a running system.