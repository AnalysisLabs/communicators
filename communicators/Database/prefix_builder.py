#!/usr/bin/env python3
"""
prefix_builder.py – assemble tiered runtime prefixes for Communicators programs.

Tier structure (see Communicators_Prefix_Tiers.md):

  Tier 0  – standard.py + COMMUNICATORS_ROOT (resolved at build time)
  Tier 1  – Tier 0 + Manifest   (temporary ModuleType)
  Tier 2  – Tier 1 + transponder (temporary ModuleType, Manifest injected)
  Tier Z  – final prefix that is actually prepended to user programs
            (currently identical to Tier 2)

Each tier is built as a self-contained string.  Higher tiers are constructed
by taking the text of the previous tier and appending the next ModuleType
block.  Only public names (Manifest, transponder, …) remain after each tier.
"""

from __future__ import annotations

import types
from pathlib import Path
from textwrap import dedent

from vfs_writer import read_file, write_file


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
    """Tier 1: Tier 0 + Manifest (temporary ModuleType)."""
    manifest_src = _load_source_from_disk(
        "state-methods/manifest.py",
        "manifest.py",
    )

    parts: list[str] = []
    parts.append(build_prefix0().rstrip())
    parts.append("")

    # --- Manifest via temporary ModuleType ---
    parts.append("# === Manifest (temporary ModuleType) ===")
    parts.append("import types")
    parts.append("_manifest_src = " + repr(manifest_src))
    parts.append(dedent("""\
        _manifest_mod = types.ModuleType("_temp_manifest")
        exec(_manifest_src, _manifest_mod.__dict__)
        Manifest = _manifest_mod.manifest          # public name expected by the rest of the system
        del _manifest_mod
    """).rstrip())
    parts.append("")

    return "\n".join(parts)


def build_prefix2() -> str:
    """Tier 2: Tier 1 + transponder (temporary ModuleType, Manifest injected)."""
    transponder_src = _load_source_from_disk(
        "edge-methods/connections/transponder_module.py",
        "transponder_module.py",
    )

    parts: list[str] = []
    parts.append(build_prefix1().rstrip())
    parts.append("")

    # --- transponder via temporary ModuleType ---
    parts.append("# === transponder (temporary ModuleType) ===")
    parts.append("_transponder_src = " + repr(transponder_src))
    parts.append(dedent("""\
        _transponder_mod = types.ModuleType("_temp_transponder")
        _transponder_mod.Manifest = Manifest       # inject so the module can use it
        exec(_transponder_src, _transponder_mod.__dict__)
        transponder = _transponder_mod
        del _transponder_mod
    """).rstrip())
    parts.append("")

    return "\n".join(parts)


def build_prefixZ() -> str:
    """
    Tier Z: the final prefix that is prepended to user programs
    (namespace.py, egg_transpiler.py, …).

    Currently identical to Tier 2.  Future tiers will be inserted here.
    """
    return build_prefix2()

def write_prefix_to_vfs(
    tier: str = "Z",
    virtual_path: str | None = None,
) -> int:
    """
    Build the requested tier and store it in the VirtualFS.

    tier: "0" | "1" | "2" | "Z"
    virtual_path: override the default path for that tier.
                  If None, sensible defaults are used.
    """
    builders = {
        "0": build_prefix0,
        "1": build_prefix1,
        "2": build_prefix2,
        "Z": build_prefixZ,
    }
    if tier not in builders:
        raise ValueError(f"Unknown tier {tier!r}")

    default_paths = {
        "0": "Database/prefix_tier0.py",
        "1": "Database/prefix_tier1.py",
        "2": "Database/prefix_tier2.py",
        "Z": "Database/prefix.py",          # classic name kept for compatibility
    }

    path = virtual_path or default_paths[tier]
    prefix = builders[tier]()
    return write_file(path, prefix, access_tier="agent_user")


def write_all_prefixes() -> dict[str, int]:
    """
    Write every tier (including the redundant prefix.py == prefixZ).
    Returns a mapping {tier: node_id}.
    """
    ids = {}
    for tier in ("0", "1", "2", "Z"):
        ids[tier] = write_prefix_to_vfs(tier=tier)
    # explicit redundancy the user requested
    ids["prefixZ"] = write_prefix_to_vfs(
        tier="Z",
        virtual_path="Database/prefix_tierZ.py",
    )
    return ids
# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    prefix = build_prefixZ()

    if "--write" in sys.argv:
        ids = write_all_prefixes()
        print(f"Wrote prefix → Database/prefix.py  (node id {ids})")
        print(f"Length: {len(prefix)} characters")
    else:
        # Just print it so you can inspect
        print(prefix)
        print("\n# (re-run with --write to store it in the VirtualFS)", file=sys.stderr)
