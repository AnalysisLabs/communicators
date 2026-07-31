#!/usr/bin/env python3
"""
prefix_builder.py – assemble tiered runtime prefixes for Communicators programs.

Tier structure (see Communicators_Prefix_Tiers.md):

  Tier 0  – standard.py + COMMUNICATORS_ROOT (resolved at build time)
  Tier 1  – Tier 0 + Manifest   (temporary ModuleType)
  Tier 2  – Tier 1 + transponder (temporary ModuleType, Manifest injected)
  Tier A  – final prefix that is actually prepended to user programs
            (currently identical to Tier 2)

Each tier is built as a self-contained string.  Higher tiers are constructed
by taking the text of the previous tier and appending the next ModuleType
block.  Only public names (Manifest, transponder, …) remain after each tier.
"""

from __future__ import annotations

import types
from pathlib import Path
from textwrap import dedent

#local imports
from vfs_writer import read_file, write_file
from prefix_transpiler import transpile_to_tier_c


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def find_communicators_root(start=None) -> Path:
    """Walk up until we find a directory named 'communicators'."""
    d = Path(start or Path.cwd()).absolute()
    while d != Path("/"):
        if d.name == "communicators":
            return d
        d = d.parent
    return Path.cwd()  # fallback

root = find_communicators_root()

def _load_source_from_disk(relative: str, fallback_name: str) -> str:
    """
    Try the real communicators tree first, then fall back to the
    attachments/ copies that exist in this development environment.
    """
    root = find_communicators_root()
    candidate = root / relative
    if candidate.exists():
        return candidate.read_text(encoding="utf-8")

    # Sandbox fallback
    fallback = Path(__file__).resolve().parent.parent / "attachments" / fallback_name
    if fallback.exists():
        return fallback.read_text(encoding="utf-8")

    raise FileNotFoundError(
        f"Could not find source for {relative}\n"
        f"  tried: {candidate}\n"
        f"  tried: {fallback}"
    )


# ---------------------------------------------------------------------------
# Tier builders
# ---------------------------------------------------------------------------

def build_prefix0() -> str:
    """Tier 0: standard library collection + concrete COMMUNICATORS_ROOT."""
    standard_src = _load_source_from_disk(
        "prelude/standard.py",
        "standard.py",
    )

    parts: list[str] = []

    # --- standard library collection ---
    parts.append("# === standard.py (from VirtualFS) ===")
    parts.append(standard_src.rstrip())
    parts.append("")

    # --- COMMUNICATORS_ROOT (resolved once at prefix-build time) ---
    parts.append("# === COMMUNICATORS_ROOT (resolved at prefix-build time) ===")
    parts.append("from pathlib import Path")
    parts.append(f"COMMUNICATORS_ROOT = Path({str(root)!r})")
    parts.append("")

    return "\n".join(parts)


def build_prefix1() -> str:
    """Tier 1: Tier 0 + Manifest class."""
    manifest_src = _load_source_from_disk(
        "state-methods/manifest.py",
        "manifest.py",
    )

    parts: list[str] = []
    parts.append(build_prefix0().rstrip())
    parts.append("")

    # --- Manifest (class) ---
    parts.append("# === Manifest (class) ===")
    parts.append(manifest_src.rstrip())
    parts.append("")
    # The source itself is expected to end with the class definition.
    # We only need to make sure the public name is bound.
    # (If the class is already named Manifest inside the file, this line is a no-op.)
    parts.append("")

    return "\n".join(parts)


def build_prefix2() -> str:
    """Tier 2: Tier 1 + Transponder class."""
    transponder_src = _load_source_from_disk(
        "edge-methods/connections/transponder_module.py",
        "transponder_module.py",
    )

    parts: list[str] = []
    parts.append(build_prefix1().rstrip())
    parts.append("")

    # --- Transponder (class) ---
    parts.append("# === Transponder (class) ===")
    parts.append(transponder_src.rstrip())
    parts.append("")
    # Same assumption: the source defines class Transponder.
    # We bind the conventional lowercase instance/name that the rest of the
    # system already expects.
    parts.append("")

    return "\n".join(parts)


def build_prefixA() -> str:
    raw = build_prefix2()          # today’s tier A
    return transpile_to_tier_c(raw)

def write_prefix_to_vfs(
    tier: str = "A",
    virtual_path: str | None = None,
) -> int:
    """
    Build the requested tier and store it in the VirtualFS.

    tier: "0" | "1" | "2" | "A"
    virtual_path: override the default path for that tier.
                  If None, sensible defaults are used.
    """
    builders = {
        "0": build_prefix0,
        "1": build_prefix1,
        "2": build_prefix2,
        "A": build_prefixA,
    }
    if tier not in builders:
        raise ValueError(f"Unknown tier {tier!r}")

    default_paths = {
        "0": "Database/prefix_tier0.py",
        "1": "Database/prefix_tier1.py",
        "2": "Database/prefix_tier2.py",
        "A": "Database/prefix.py",          # classic name kept for compatibility
    }

    path = virtual_path or default_paths[tier]
    prefix = builders[tier]()
    return write_file(path, prefix, access_tier="agent_user")


def write_all_prefixes() -> dict[str, int]:
    """
    Write every tier (including the redundant prefix.py == prefixA).
    Returns a mapping {tier: node_id}.
    """
    ids = {}
    for tier in ("0", "1", "2", "A"):
        ids[tier] = write_prefix_to_vfs(tier=tier)
    # explicit redundancy the user requested
    ids["prefixA"] = write_prefix_to_vfs(
        tier="A",
        virtual_path="Database/prefix_tierA.py",
    )
    return ids
# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    prefix = build_prefixA()

    if "--write" in sys.argv:
        ids = write_all_prefixes()
        print(f"Wrote prefix → Database/prefix.py  (node id {ids})")
        print(f"Length: {len(prefix)} characters")
    else:
        # Just print it so you can inspect
        print(prefix)
        print("\n# (re-run with --write to store it in the VirtualFS)", file=sys.stderr)
