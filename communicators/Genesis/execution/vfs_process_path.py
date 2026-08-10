#!/usr/bin/env python3
"""
vfs_process_path.py – short-lived ownership tree + process_path injection.

Used by the execution harness as a final pass over the combined
(prefix + user) source before it is compiled and launched.

1. Build a nested dict that mirrors class / function structure (via AST).
2. For every manifest.* / Manifest.* call that appears at or after the
   "# === Tier 2 (imports) ===" marker, inject
       process_path="<dotted.path.from.ownership.tree>"
   as a keyword argument.

The resulting process_path is only the hierarchical ownership piece
(class.function / nested scopes).  It is intentionally incomplete;
later stages can enrich it.
"""

from __future__ import annotations

import ast
import re
from typing import Any

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dotted_program_path(program_path: str, include_py_suffix: bool = False) -> str:
    """
    Convert a VirtualFS destination into a dotted process-path prefix.

    "Runtime/generated/namespace.py"  →  "Runtime.generated.namespace"
    "Metamorphosis/generated/egg_transpiler" → "Metamorphosis.generated.egg_transpiler"

    Set include_py_suffix=True if you later decide the ".py" should stay.
    """
    p = program_path.strip("/")
    if not include_py_suffix and p.endswith(".py"):
        p = p[:-3]
    return p.replace("/", ".")

# ---------------------------------------------------------------------------
# Ownership tree (nested dicts)
# ---------------------------------------------------------------------------

def build_ownership_tree(
    source: str,
    program_path: str = "",
    include_py_suffix: bool = False,
) -> dict[str, Any]:
    """
    Nested dict mirroring program path + section banners + class/function structure.

    Hierarchy (when program_path is supplied):

        root
        └── Runtime.generated.namespace          ← dotted program path
            ├── imports!tier2
            │   ├── transponder_internal
            │   │   └── handle_connection
            │   └── transponder
            │       └── persistent_server
            └── user_program
                ├── BaseNamespace
                └── _start_ns_server
    """
    lines = source.splitlines()
    total_lines = len(lines) or 1

    # ------------------------------------------------------------------
    # 1. Discover section banners and compute their line ranges
    # ------------------------------------------------------------------
    _TIER_RE = re.compile(r"#\s*===\s*Tier\s+(\d+)\s*\(imports\)\s*===", re.I)
    _USER_RE = re.compile(r"#\s*=+\s*\(USER PROGRAM\)\s*=+", re.I)

    sections: list[tuple[str, int]] = []          # (name, start_lineno)
    for i, line in enumerate(lines, 1):
        m = _TIER_RE.search(line)
        if m:
            sections.append((f"imports!tier{m.group(1)}", i))
            continue
        if _USER_RE.search(line):
            sections.append(("user_program", i))

    section_ranges: list[tuple[str, int, int]] = []
    for idx, (name, start) in enumerate(sections):
        end = sections[idx + 1][1] - 1 if idx + 1 < len(sections) else total_lines
        section_ranges.append((name, start, end))

    # ------------------------------------------------------------------
    # 2. Build the tree
    # ------------------------------------------------------------------
    root: dict[str, Any] = {"_start": 1, "_end": total_lines}

    # Optional outermost program-path node
    if program_path:
        prog = _dotted_program_path(program_path, include_py_suffix)
        root[prog] = {"_start": 1, "_end": total_lines}
        program_node = root[prog]
    else:
        program_node = root

    # Insert the section nodes under the program node
    for name, start, end in section_ranges:
        program_node[name] = {"_start": start, "_end": end}

    def _find_parent(lineno: int) -> dict[str, Any]:
        """Return the innermost section that contains lineno, else the program node."""
        for name, start, end in reversed(section_ranges):
            if start <= lineno <= end:
                return program_node[name]
        return program_node

    def visit(node: ast.AST, current: dict[str, Any]) -> None:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            child: dict[str, Any] = {
                "_start": node.lineno,
                "_end": getattr(node, "end_lineno", node.lineno),
            }
            # Attach to the section that owns this node (or to the
            # current AST parent if we are already nested)
            parent = current if current is not program_node else _find_parent(node.lineno)
            parent[node.name] = child
            for stmt in node.body:
                visit(stmt, child)
        else:
            for child_node in ast.iter_child_nodes(node):
                visit(child_node, current)

    tree = ast.parse(source)
    for node in tree.body:
        visit(node, program_node)

    return root

def path_for_line(ownership: dict[str, Any], line: int) -> str:
    """
    Return the dotted ownership path for the innermost scope that
    contains `line`.  Example results:

        "transponder_internal.handle_connection"
        "BaseNamespace.__new__"
        "_start_ns_server"
        "<module>"
    """
    path: list[str] = []
    current = ownership

    while True:
        best_name = None
        best_node = None

        for name, node in current.items():
            if name in ("_start", "_end"):
                continue
            if node["_start"] <= line <= node["_end"]:
                if best_node is None or node["_start"] > best_node["_start"]:
                    best_name = name
                    best_node = node

        if best_name is None:
            break

        path.append(best_name)
        current = best_node

    return ".".join(path) if path else "<module>"


# ---------------------------------------------------------------------------
# Call-site injection
# ---------------------------------------------------------------------------

# Matches both the original capitalised name and the lower-cased public façade
_CALL_RE = re.compile(
    r"""
    \b([Mm]anifest)\.                  # Manifest. or manifest.
    (debug|info|warning|error|critical|printer|json|freight)
    \s*\(                              # opening paren
    """,
    re.VERBOSE,
)


def _inject_into_line(line: str, path: str) -> str:
    """Add process_path=... to a single-line Manifest call if missing."""
    if "process_path=" in line:
        return line

    m = _CALL_RE.search(line)
    if not m:
        return line

    # Very common case: the call (and its closing paren) lives on this line
    if line.rstrip().endswith(")"):
        # Insert just before the final )
        stripped = line.rstrip("\n")
        nl = "\n" if line.endswith("\n") else ""
        # Avoid producing a leading comma when the call was empty
        if re.search(r"\(\s*\)$", stripped):
            return re.sub(r"\(\s*\)$", f'(process_path="{path}")', stripped) + nl
        return stripped[:-1] + f', process_path="{path}")' + nl

    # Multi-line call start – leave untouched for this first version
    return line


def inject_process_paths(
    source: str,
    program_path: str = "",
    include_py_suffix: bool = False,
) -> str:
    """
    Main entry point.

    Builds the ownership tree once, then rewrites every qualifying
    Manifest call that appears at or after the Tier-2 marker.
    """
    ownership = build_ownership_tree(
        source,
        program_path=program_path,
        include_py_suffix=include_py_suffix,
    )
    lines = source.splitlines(keepends=True)

    # Locate the starting marker (1-based line numbers are derived from index)
    start_idx = 0
    for i, line in enumerate(lines):
        if "# === Tier 2 (imports) ===" in line:
            start_idx = i
            break

    out: list[str] = lines[:start_idx]

    for i in range(start_idx, len(lines)):
        lineno = i + 1
        line = lines[i]
        path = path_for_line(ownership, lineno)
        out.append(_inject_into_line(line, path))

    return "".join(out)
