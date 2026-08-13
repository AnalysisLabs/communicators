# Prefix Tier Principle

## Purpose

The runtime environment for user programs is assembled in strict dependency
tiers so that interdependent capabilities load in a safe order without circular
dependencies or missing names.

## Tier rules

| Tier | Role | May depend on |
|------|------|----------------|
| **0** | Base vocabulary (language and standard facilities) | nothing |
| **1** | Core objects that need only Tier 0 | Tier 0 |
| **2** | Objects that need Tier 0 and Tier 1 | Tier 0 + 1 |
| **3+** | Further layers | all lower tiers |

### Invariants

1. A component in tier *N* may use any name introduced in tiers *0 … N−1*.
2. It must **not** assume names from its own tier or higher tiers exist.
3. After a tier finishes, only its **public** name(s) remain visible.
   Temporary scaffolding is discarded.
4. Injection of lower-tier names into a higher-tier component is explicit and
   happens before that component is activated.
5. User programs see only the public names of tiers, never a flat dump of
   every internal function.

## Why tiers exist

Ordinary import graphs among tightly coupled pieces become circular and brittle.
Tiers turn that graph into a linear sequence enforced at assembly time. Each new
capability is added as the next tier; one assembler owns the order.

## Extension rule

When a new capability must be added:

1. Determine the highest tier it depends on.
2. Place it in the next free tier (or an existing tier with the same requirements).
3. Ensure every name it needs from lower tiers is explicitly available before it runs.
4. Expose only its public name(s) afterward.

Dependency direction always points downward.

## Fictitious illustration

Tier 0 provides basic utilities. Tier 1 introduces `Ledger`. Tier 2 introduces
`Router`, which may call `Ledger`, but `Ledger` must not call `Router`. After
assembly, user code may use `Ledger` and `Router` only; tier scaffolding is gone.
