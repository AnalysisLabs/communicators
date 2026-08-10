# Communicators Prefix Tiers

## Purpose

The runtime prefix is built in strict dependency tiers so that interdependent modules can be loaded safely and in the correct order without circular imports or missing names.

## Tier Rules

| Tier | Contents | May depend on | Current members |
|------|----------|---------------|-----------------|
| **0** | Third-party + standard-library imports | nothing | `standard.py` (pasted raw) |
| **1** | Core system objects that need only Tier 0 | Tier 0 | `Manifest` |
| **2** | Objects that need Tier 0 + Tier 1 | Tier 0 + 1 | `transponder` |
| **3+** | Future layers | all lower tiers | (none yet) |

### Invariants

1. A module belonging to tier *N* may use any name that was introduced in tiers *0 … N-1*.
2. A module must **not** assume names from its own tier or higher tiers exist.
3. After a tier has finished loading, only its **public** name(s) remain in the prefix namespace. Temporary module objects are deleted.
4. Injection of lower-tier names into a higher-tier module is explicit and happens before `exec`.
5. The final public interface that user programs see is always the tier’s public name (`Manifest`, `transponder`, …), never a flat dump of individual functions.

## Why Tiers Exist

The Communicators ecosystem contains modules that are tightly interdependent. Loading them with ordinary `import` statements quickly produces circular dependencies and brittle import order.  

Tiers turn the dependency graph into a linear sequence that is enforced at prefix-construction time. Each new capability is added as the next tier, and the prefix builder becomes the single place that knows the correct order.

## Extension Rule

When a new module must be added:

1. Determine the highest tier it depends on.
2. Place it in the next free tier (or an existing tier if it has identical requirements).
3. Update the prefix builder so that every name it needs from lower tiers is explicitly injected before its `exec`.
4. Expose only its public name(s) to the rest of the system.

This keeps the runtime namespace clean and the dependency direction always downward.