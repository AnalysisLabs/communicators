#!/usr/bin/env python3
"""
prefix_builder.py – assemble the runtime prefix for Communicators programs.

Order of operations inside the generated prefix:

1. find_communicators_root() + COMMUNICATORS_ROOT = ...
2. Temporary ModuleType load of manifest.py
3. Temporary ModuleType load of transponder_module.py
   (with Manifest injected so it can use Manifest.info / Manifest.error)
4. Only public names are left in the namespace

The resulting prefix is a single self-contained string that can be
prepended to any program.
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
# Core builder
# ---------------------------------------------------------------------------

def build_prefix() -> str:
    """
    Assemble and return the complete prefix as a single string.
    """
    standard_src = _load_source_from_disk(
        "prelude/standard.py",
        "standard.py",
    )
    manifest_src = _load_source_from_disk(
        "state-methods/manifest.py",
        "manifest.py",
    )
    transponder_src = _load_source_from_disk(
        "edge-methods/connections/transponder_module.py",
        "transponder_module.py",
    )

    # ------------------------------------------------------------------
    # Assemble the prefix text
    # ------------------------------------------------------------------
    parts: list[str] = []

    # --- standard library collection ---
    parts.append("# === standard.py (from VirtualFS) ===")
    parts.append(standard_src.rstrip())
    parts.append("")

    # --- COMMUNICATORS_ROOT ---
    parts.append("# === COMMUNICATORS_ROOT ===")
    parts.append(dedent("""\
        def find_communicators_root(start=None):
            d = Path(start or Path.cwd()).absolute()
            while d != Path("/"):
                if d.name == "communicators":
                    return d
                d = d.parent
            return Path.cwd()  # fallback

        COMMUNICATORS_ROOT = find_communicators_root()
    """).rstrip())
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

    # --- transponder via temporary ModuleType (Manifest already available) ---
    parts.append("# === transponder (temporary ModuleType) ===")
    parts.append("_transponder_src = " + repr(transponder_src))
    parts.append(dedent("""\
        _transponder_mod = types.ModuleType("_temp_transponder")
        _transponder_mod.Manifest = Manifest       # inject so the module can use it
        exec(_transponder_src, _transponder_mod.__dict__)

        # Export every public (non-private) name.  No hard-coded assumptions
        # about which names exist inside the module.
        for _name in list(_transponder_mod.__dict__):
            if not _name.startswith("_"):
                globals()[_name] = getattr(_transponder_mod, _name)

        del _transponder_mod
    """).rstrip())
    parts.append("")

    parts.append("# === end of auto-generated prefix ===")
    parts.append("")

    return "\n".join(parts)


def write_prefix_to_vfs(virtual_path: str = "Database/prefix.py") -> int:
    """
    Build the prefix and store it in the VirtualFS.
    Returns the node id.
    """
    prefix = build_prefix()
    return write_file(virtual_path, prefix, access_tier="agent_user")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    prefix = build_prefix()

    if "--write" in sys.argv:
        node_id = write_prefix_to_vfs()
        print(f"Wrote prefix → Database/prefix.py  (node id {node_id})")
        print(f"Length: {len(prefix)} characters")
    else:
        # Just print it so you can inspect
        print(prefix)
        print("\n# (re-run with --write to store it in the VirtualFS)", file=sys.stderr)
