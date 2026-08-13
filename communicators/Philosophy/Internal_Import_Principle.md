# Internal Import Principle

## Goal

Provide a small set of carefully controlled public names to every user program
so that capabilities are used in an attribute style, for example:

    Ledger.record(...)
    Router.connect(...)

while guaranteeing that **no other names** from the implementing modules leak
into the user program’s global namespace.

## What matters

- Methods are reachable only through the chosen public objects.
- Only deliberately exposed functions are visible.
- Zero accidental name collisions with the user program.
- The mechanism is reliable and easy to reason about at boot time.

## What does not matter

- Whether the implementation uses a module object, a class, a namespace,
  a plain mapping, or any other technique.
- Whether the underlying source is executed, imported normally, or built by hand.
- Any particular language import machinery.

The only requirement is the observable effect: a clean, collision-free,
attribute-style interface.

## Fictitious illustration

An internal library defines dozens of helpers. Only `Ledger` and `Router` are
bound into the environment seen by user code. Helpers such as `_hash_line` or
`_retry_once` remain invisible. User code cannot accidentally call or shadow them.
