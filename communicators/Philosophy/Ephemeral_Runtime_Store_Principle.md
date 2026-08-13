# Ephemeral Runtime Store Principle

## Core claim

Runtime-generated program text and related artifacts that exist only for a
single boot live in an ephemeral, queryable store, not as long-lived loose files
on the host disk.

## Rules

1. **Fresh each run.**  
   The store is created empty (aside from required structural roots) at the
   start of a boot sequence and is not relied on across process lifetimes.

2. **Content addressing where payloads matter.**  
   Stored program text is keyed by content digest so identical payloads share
   storage and replacement is well-defined.

3. **Tree shape is metadata.**  
   Directory-like structure is a graph of names under a root, separate from
   payload bytes.

4. **Parents may be created on write** when the store is used as a pure runtime
   scratch space; a fixed seeded layout is optional, not mandatory.

5. **Not a substitute for real-filesystem identity.**  
   Tracked source modules still obey the File Identity Principle. The ephemeral
   store holds *generated* combinations and intermediate products.

## Fictitious illustration

A boot stage combines a shared prologue with a user fragment and stores the
result under a runtime path such as `Generated/job_42`. That path exists only
inside the ephemeral store for this run. The original user fragment on disk
remains tracked by file identity; the combined text does not need a durable
disk path.
