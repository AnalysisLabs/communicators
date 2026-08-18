#!/usr/bin/env python3
"""
dual_use_rectifier.py – prepare atomic_importer / path_reffs for Tier-1 insertion.

Takes a raw module source (already containing the # === Start Here === marker),
strips the import block, wraps the remaining body in an outer class, and
decorates every top-level function and top-level class with either
@externalmethod or @internalmethod according to a supplied public-name set.

Nested classes that already exist inside the body receive a marker but their
*contents* are left completely untouched (the later Stage-B rule).

The output is a single class definition ready to be concatenated into
prefix Tier 1.  Stage B of prefix_transpiler is expected to understand the
markers on both methods and nested classes.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from typing import List, Set, Tuple


# ---------------------------------------------------------------------------
# Public-name tables (callers may override)
# ---------------------------------------------------------------------------

ATOMIC_IMPORTER_PUBLIC = {
    "from_path",
    "from_path_import",
    "from_code",
    "from_code_import",
}

PATH_REFFS_PUBLIC = {
    "FileRef",
    "resolve_path",
}


# ---------------------------------------------------------------------------
# Line-range helpers (same philosophy as prefix_transpiler)
# ---------------------------------------------------------------------------

@dataclass
class MemberRange:
    """A top-level function or class that lives in the body after Start Here."""
    kind: str          # "func" | "class"
    name: str
    start: int         # 1-based inclusive (includes any existing decorators)
    end: int           # 1-based inclusive
    raw_lines: List[str]


def _find_start_here(lines: List[str]) -> int:
    """Return 0-based index of the line that contains the marker, or 0."""
    for i, line in enumerate(lines):
        if "# === Start Here ===" in line:
            return i
    return 0


def _collect_top_level_members(source: str) -> List[Tuple[str, str, int, int]]:
    """
    Return list of (kind, name, start_lineno, end_lineno) for every top-level
    FunctionDef / AsyncFunctionDef / ClassDef that appears *after* the
    Start-Here marker.  AST is used only for line numbers.
    """
    tree = ast.parse(source)
    members = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            deco_start = node.lineno
            if node.decorator_list:
                deco_start = min(d.lineno for d in node.decorator_list)
            end = getattr(node, "end_lineno", node.lineno)
            members.append(("func", node.name, deco_start, end))
        elif isinstance(node, ast.ClassDef):
            deco_start = node.lineno
            if node.decorator_list:
                deco_start = min(d.lineno for d in node.decorator_list)
            end = getattr(node, "end_lineno", node.lineno)
            members.append(("class", node.name, deco_start, end))
    return members


def _expand_member_ranges(
    source_lines: List[str],
    raw_members: List[Tuple[str, str, int, int]],
    body_start: int,          # 1-based first line of the body we care about
) -> List[MemberRange]:
    """
    Expand each member so that intervening comments / blank lines are
    attached to the following member (same rule the main transpiler uses).
    """
    if not raw_members:
        return []

    raw_members = sorted(raw_members, key=lambda t: t[2])
    expanded: List[MemberRange] = []
    prev_end = body_start - 1

    for kind, name, core_start, core_end in raw_members:
        block_start = prev_end + 1
        block_end = core_end
        # Guard against pathological overlap
        if block_start > block_end:
            block_start = core_start
        lines = source_lines[block_start - 1 : block_end]
        expanded.append(
            MemberRange(
                kind=kind,
                name=name,
                start=block_start,
                end=block_end,
                raw_lines=lines,
            )
        )
        prev_end = core_end

    return expanded


# ---------------------------------------------------------------------------
# Marker insertion (text-level, comment-preserving)
# ---------------------------------------------------------------------------

_DECORATOR_RE = re.compile(r"^[ \t]*@\w+")

def _already_has_marker(lines: List[str]) -> bool:
    for line in lines:
        if "@externalmethod" in line or "@internalmethod" in line:
            return True
        # stop at the first non-decorator, non-blank line
        if line.strip() and not _DECORATOR_RE.match(line):
            break
    return False


def _insert_marker(raw_lines: List[str], marker: str) -> List[str]:
    """
    Insert the chosen marker as the outermost decorator.

    - Leading blank lines and pure comment lines stay above the marker.
    - The marker is placed before any existing decorators (so it sits at
      the top of the decorator stack).
    - If a marker is already present we leave the block alone.
    """
    if _already_has_marker(raw_lines):
        return list(raw_lines)

    # Walk past leading blank lines and pure comments.
    # The first line that is either an existing decorator or the
    # def/class/async-def itself becomes the insertion point.
    insert_at = None
    for i, line in enumerate(raw_lines):
        stripped = line.lstrip()
        if not stripped:                     # blank
            continue
        if stripped.startswith("#"):         # comment
            continue
        # First real syntactic line (decorator or definition)
        if (stripped.startswith("@")
                or stripped.startswith("def ")
                or stripped.startswith("async def ")
                or stripped.startswith("class ")):
            insert_at = i
            break

    if insert_at is None:
        # Fallback: treat the whole block as opaque
        indent = re.match(r"^[ \t]*", raw_lines[0]).group(0) if raw_lines else "    "
        return [f"{indent}{marker}\n"] + list(raw_lines)

    indent = re.match(r"^[ \t]*", raw_lines[insert_at]).group(0)
    marker_line = f"{indent}{marker}\n"

    new_lines = list(raw_lines)
    new_lines.insert(insert_at, marker_line)
    return new_lines

# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def rectify(
    source: str,
    *,
    public_names: Set[str],
    outer_class_name: str,
) -> str:
    """
    Transform one module source into a single decorated outer class.

    Parameters
    ----------
    source :
        Full text of atomic_importer.py or path_reffs.py (must contain the
        # === Start Here === marker).
    public_names :
        Names that should receive @externalmethod.  Everything else receives
        @internalmethod.
    outer_class_name :
        Name of the wrapper class that will be emitted (e.g. "AtomicImporter").
    """
    lines = source.splitlines(keepends=True)

    # 1. Drop everything up to and including the Start-Here marker
    start_idx = _find_start_here(lines)          # 0-based
    body_lines = lines[start_idx + 1 :]          # keep the rest
    if not body_lines:
        raise ValueError("No content found after # === Start Here ===")

    # Re-join so we can re-parse just the body (line numbers will be relative
    # to this fragment; we will adjust later).
    body_src = "".join(body_lines)
    # We need absolute line numbers that match the original `lines` list,
    # so we work with the full source for AST and then offset.

    full_src = source
    raw_members = _collect_top_level_members(full_src)

    # Keep only members that start after the Start-Here line
    start_lineno = start_idx + 1                 # 1-based
    raw_members = [
        m for m in raw_members if m[2] > start_lineno
    ]

    members = _expand_member_ranges(
        lines,
        raw_members,
        body_start=start_lineno + 1,
    )

    # 2. Build the body of the outer class
    outer_body: List[str] = []

    for mem in members:
        is_public = mem.name in public_names
        marker = "@externalmethod" if is_public else "@internalmethod"

        decorated = _insert_marker(mem.raw_lines, marker)

        # Everything inside the outer class must be indented one level.
        # We also have to indent the marker we just inserted.
        for line in decorated:
            if line.strip() == "":
                outer_body.append("\n")
            else:
                outer_body.append("    " + line)

        outer_body.append("\n")          # blank line between members

    # 3. Assemble the final outer class
    result: List[str] = []
    result.append(f"class {outer_class_name}:\n")
    if not outer_body:
        result.append("    pass\n")
    else:
        result.extend(outer_body)

    return "".join(result)


# ---------------------------------------------------------------------------
# Convenience wrappers for the two known modules
# ---------------------------------------------------------------------------

def rectify_atomic_importer(source: str) -> str:
    return rectify(
        source,
        public_names=ATOMIC_IMPORTER_PUBLIC,
        outer_class_name="AtomicImporter",
    )


def rectify_path_reffs(source: str) -> str:
    return rectify(
        source,
        public_names=PATH_REFFS_PUBLIC,
        outer_class_name="PathReffs",
    )


# ---------------------------------------------------------------------------
# CLI (handy for quick inspection)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    from pathlib import Path

    if len(sys.argv) != 2:
        print("Usage: dual_use_rectifier.py <atomic_importer.py|path_reffs.py>",
              file=sys.stderr)
        sys.exit(1)

    path = Path(sys.argv[1])
    src = path.read_text(encoding="utf-8")

    if "atomic_importer" in path.name:
        out = rectify_atomic_importer(src)
    elif "path_reffs" in path.name:
        out = rectify_path_reffs(src)
    else:
        print("Unknown module – pass public_names manually", file=sys.stderr)
        sys.exit(1)

    print(out)
