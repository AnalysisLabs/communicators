
# Meta-OS Dev Environment Setup (Outer Layer)

**Status:** In progress  
**Type:** Tooling / Workflow  
**Related:** [[communicators]], [[Levels of Abstraction]], [[Outer Layer]]

## Purpose

Create a clean, ergonomic, and self-consistent way to enter the development environment for the **communicators** meta-OS project.

This lives in the **outer layer** — the personal ergonomic scaffolding that gets me into the right state so the inner meta-OS code can stay pure and focused on its actual work (declarative runtime construction, distributed coordination, memory management at the meta level, valet-style behavior, etc.).

## Core Idea

Instead of manually managing a venv and running `pip install -e .` every time (or forgetting to do it), I want a single, thoughtful **interactive shell script** that acts as a **"meta-terminal"** for the project.

The script should feel like a small concierge for my own development workflow — consistent with the character of the thing I'm building.

## What the Script Should Do

- Create the virtual environment (`.venv`) if it doesn't exist
- Activate the venv
- **Only** run `pip install -e .` (and optionally `requirements.txt`) **if and only if** the package is not already installed in editable mode
- Drop me into a fresh interactive shell with everything ready
- Be idempotent and safe to run repeatedly
- Be easy to extend later (menu options, different modes, extra dev tools, etc.)

## Why This Approach

- Keeps the **inner layer** (the actual meta-OS code) clean — no more `Path(__file__)` + `sys.path.insert` bootstrap in every file.
- Once `pip install -e .` has succeeded, `from prelude import *` (and all other internal imports) just work normally.
- The setup logic stays where it belongs: in the outer layer.
- The script can evolve with the project without polluting the core codebase.
- It turns the daily "get into the project" ritual into something intentional and slightly fun (meta-terminal for the meta-OS).

## Current Design (as of 2026-05-29)

The script (`setup-dev.sh` or similar) lives in the repository root and follows this flow:

1. Check/create `.venv`
2. Activate it
3. Check if the package is already importable (`python -c "import communicators"`)
4. If not installed → run `pip install -e .` (+ `requirements.txt` if present)
5. Print a ready message
6. Drop into an interactive shell (`exec $SHELL -i`)
7. It should have a small interactive menu 

This gives me a clean, activated environment with minimal friction.

## Open Questions / Future Improvements

- How should it handle multiple modes (e.g. "dev", "test", "production simulation")?
- How much "magic" is acceptable before it becomes hard to understand or debug?

## Philosophy

This is the **outer layer** doing its job well so the **inner layer** can stay focused on being a lightweight, metamorphic, distributed meta-OS.

The script should be:
- Reliable
- If an install fails that install name should be printed in terminal.
- self-healing where possible.
- Minimal maybe
- Extensible
- Pleasant to use every day

It is scaffolding, not the organism itself.


## TODO
# objectives:
- builds venv
- abstracts boilerplate
- abstracts internal lib
- interactive shell does not exit automatically.

---

**Tags:** #meta-os #tooling #outer-layer #python #bash #workflow
