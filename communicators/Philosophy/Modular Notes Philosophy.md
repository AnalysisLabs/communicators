
# Modular Notes Philosophy

## Core Principle
Notes for evolving code/modules must stay useful for months without becoming technical debt. Prefer **atomic evergreen notes** over monolithic module docs.

## Rules

### 1. Atomic by Default
- One focused concept per note.
- Good: `async-state-updates-fail-because`
- Bad: `module-x-overview` (too broad, dies when the module changes)

### 2. Evergreen, Not Snapshot
- Write so the note can be updated in place.
- Prefer present-tense descriptions of *current* behavior and intent.
- Never try to document an entire module in one file.

### 3. Maps of Content (MOCs)
- Create a hub note per major module or subsystem.
- The MOC is just a curated list of links to atomic notes + a short description of the module’s role.
- When the module evolves, update the MOC first, then the relevant atomic notes.

### 4. Change Log at the Bottom
- Append dated entries instead of rewriting history:


## Changelog
- 2026-07-24: Switched from X to Y because Z
- 2026-06-12: Initial version
- Old reasoning stays visible; current truth stays at the top.

### 5. Dense Linking
- Link liberally both ways.
- Prefer `[[specific-concept]]` over vague references.
- Use the graph view monthly to find orphans and weak connections.

### 6. Light Structure Only
- PARA is optional and shallow (Projects / Areas / Resources / Archives).
- Do not invent elaborate folder taxonomies. Links + MOCs are the real structure.

### 7. Monthly Hygiene (15–30 min)
- Merge near-duplicates.
- Archive or delete notes that no longer reflect reality.
- Strengthen or remove weak links.
- Update MOCs so they remain accurate entry points.

## Anti-Patterns to Avoid
- Long “module description” notes that try to stay complete.
- Notes that only make sense in the context of a conversation or one-time experiment.
- Heavy reliance on tags instead of links and MOCs.
- Letting notes go stale because updating them feels expensive.

## Goal
External memory that compounds instead of decays. Notes should be cheaper to maintain than to rewrite from scratch.