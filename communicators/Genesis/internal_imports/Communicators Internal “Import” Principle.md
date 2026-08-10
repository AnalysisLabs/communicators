# Communicators Internal “Import” Principle

## Goal
Provide a small set of carefully controlled names (`Manifest`, `transponder`, …) 
to every user program so that their methods can be called exactly like:

    Manifest.info(...)
    transponder.connect_to(...)

while guaranteeing that **no other names** from those modules leak into the 
global namespace of the user program.

## What I care about
- Methods are only reachable through the public objects (`Manifest.xxx`, `transponder.xxx`).
- Only the functions I deliberately expose are visible.
- Zero accidental name collisions with the user program that receives the prefix.
- The mechanism is reliable and easy to reason about at boot time.

## What I do not care about
- Whether the implementation uses `types.ModuleType`, a class, a `SimpleNamespace`, 
  a plain dict, or any other technique.
- Whether the underlying source is executed with `exec`, imported normally, 
  or constructed by hand.
- Any particular Python import machinery.

The only requirement is the observable effect: a clean, collision-free, 
attribute-style interface.