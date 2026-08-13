# Communicators OS — Staging Overview

This directory is the runnable root of the Communicators OS tree.
Peer stage directories (Genesis, Metamorphosis, Imago) and the Philosophy
articles sit beside tooling that starts a boot.

## Stages (grand scheme)

| Stage | Role in the whole |
|-------|-------------------|
| **Philosophy** | Stable principles. No citations of particular implementation files. |
| **Genesis** | Birth of a run: identity/registry usage, ephemeral store, prefix assembly, process launch harness. |
| **Metamorphosis** | Change and orchestration once a run exists: servers, transpilers, control scripts, graph/process machinery. |
| **Imago** | Ongoing form: homeostasis, health, feedback, healing-style behavior. |

Boot proceeds **Genesis → (workloads often under Metamorphosis) → Imago concerns**,
but not every run exercises every branch. Genesis is the required ignition path.

## Ignition

A thin shell entrypoint enters the pure development environment and hands off
to the Genesis execution bootloader. That bootloader initializes the ephemeral
runtime store, assembles the prefix, then launches selected programs through
the execution harness.

## Documentation rule (local)

- **Philosophy/** — principles only; fictitious examples if needed.
- **Each code directory** — a short markdown on *place in the grand scheme*,
  not a second copy of principles.
- Volatile how-to and schema snapshots stay next to the code they describe and
  may lag; principles and this staging page should not.

## Related principles

See Philosophy: Runtime Context, Internal Import, Prefix Tiers, File Identity,
Ephemeral Runtime Store.
