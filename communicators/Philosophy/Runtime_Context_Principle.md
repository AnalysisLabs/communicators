# Runtime-Context Principle

## Core claim

Almost nothing in the system makes sense when examined in isolation.
Meaning, correctness, and even basic executability appear only when a piece
is viewed inside the full boot and load sequence that actually runs it.

## What this means in practice

- A module’s source may look incomplete, circular, or broken when read alone.
- Names that appear missing are often supplied by an earlier stage of assembly.
- Names that seem undefined are bound at load time.
- Side effects that look dangerous are ordered so they become safe only because
  of what has already run.
- Error paths and control flow frequently depend on objects that do not exist
  until a previous stage has finished.

Therefore:

> Judging any single module, class, or function outside the runtime sequence
> in which it is loaded is usually a category error.

## Consequences

1. **Reading order is not source order.**  
   Ask “when does this execute?” before “does this look correct?”

2. **The assembled runtime unit is the real program.**  
   A user fragment is only the final piece. Coherence is required of the
   combination that actually runs, not of the fragment in isolation.

3. **Isolation is intentional but incomplete.**  
   Stages create deliberate boundaries (only chosen public names remain
   visible). The full dependency graph is visible only after assembly.

4. **Bugs often live in the seams.**  
   Failures are frequently in the contract between stages, not inside one module.

5. **Documentation must describe sequences, not only artifacts.**  
   Describing a capability without *when* and *how* it is bound is incomplete.

## Short form

> Almost nothing makes sense in isolation.  
> Coherence is a property of the boot sequence, not of any individual module.

## Fictitious illustration

Suppose a program refers to `Ledger` and `Router`. Read alone, both look
undefined. In the actual sequence, an earlier stage injects `Ledger`, a later
stage binds `Router` using `Ledger`, and only then is the user fragment
executed. Critiquing the user fragment for “missing imports” without that
sequence is the category error this principle forbids.
