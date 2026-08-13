# File Identity Principle

## Core claim

A real filesystem artifact that the system must locate reliably is identified by
a stable triple of identity fields, not by a bare path string alone.

The triple is the authority for “this is the same file” across moves, renames
of parent directories, and machine-specific absolute locations.

## Rules

1. **Identity before path.**  
   Call sites that mean a tracked file carry the identity triple (or an object
   that holds it). Resolution to a concrete path happens late, at the point of use.

2. **Strict match.**  
   Lookup succeeds only when all identity fields match the registry of record.
   Partial matches are failures, not guesses.

3. **Registry as map, not as mutator of meaning.**  
   The registry maps identity → location metadata. Changing where a file lives
   updates the map; it does not silently change which identity a call site meant.

4. **Broken reference is a hard error.**  
   Missing or mismatched identity is raised explicitly so repair can be deliberate.

5. **Virtual destinations are a different namespace.**  
   Paths inside an ephemeral runtime store are not required to use the same
   triple until they are promoted to tracked real-filesystem artifacts.

## What this is not

- Not a requirement that every string path in the system use the registry.
- Not automatic rewriting of call sites on every rename (unless a separate tool
  is explicitly run).
- Not a substitute for the Runtime-Context Principle: identity still only makes
  sense inside the sequence that loads the registry and the code that uses it.

## Fictitious illustration

A program needs a helper module. Instead of hard-coding
`/home/someone/project/lib/helper.py`, it carries identity
`(id=…, area=core/lib, name=helper.py)`. At runtime the registry resolves that
triple to the current absolute location. If the file was moved and the registry
updated, the program still finds it. If the triple is wrong, resolution fails
loudly rather than opening the wrong file.
