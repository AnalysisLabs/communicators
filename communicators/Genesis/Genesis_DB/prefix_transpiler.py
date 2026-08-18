#!/usr/bin/env python3
"""
prefix_transpiler.py – Stage B + Stage C for Communicators prefixes.

Pipeline
--------
prefix_tierA / prefix_tier2
        │
        ▼  stage_b_split   (structural split by markers)
prefix_tierB   ← written to VirtualFS
        │
        ▼  stage_c_rewrite (call-site repair)
prefix_tierC   ← written to VirtualFS and returned

Emission order for each original class (Stage B):
    class Name_internal: ...
    _Name_internal = Name_internal()
    class Name: ...               # public façade

Rules enforced
--------------
- Only @externalmethod and @internalmethod are legal on methods of
  "imported" classes.  Any undecorated def raises TranspileError.
- @externalmethod  →  stays on the public class, decorator becomes @staticmethod
- @internalmethod  →  moves to {Name}_internal, decorator is stripped
- Call sites that refer to internal methods are rewritten to the private
  instance (Option C1):  _Name_internal.method(...)
- AST is used solely to discover line ranges.  All mutation is performed
  on the original source lines so that comments and formatting outside
  the transformed classes are preserved exactly.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List, Tuple


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

# Guaranteed location relative to communicators root
_atomic_importer = (
    find_communicators_root()
    / "Genesis"
    / "internal_imports"
    / "atomic_importer.py"
)
sys.path.insert(0, str(_atomic_importer.parent))
from atomic_importer import from_path, from_path_import, from_code, from_code_import
_path_reffs = (
    find_communicators_root()
    / "Genesis"
    / "internal_imports"
    / "path_reffs.py"
)
sys.path.insert(0, str(_path_reffs.parent))
from path_reffs import*


_vfs_writer_ref = FileRef(
    uuid="f9284397-10ec-4856-8f1e-1bc62b9c8436",
    file_path="Genesis/Genesis_DB",
    file_name="vfs_writer.py",
)

read_file, write_file = from_path_import(
    resolve_path(
        _vfs_writer_ref.uuid,
        _vfs_writer_ref.file_path,
        _vfs_writer_ref.file_name,
    ),
    "read_file",
    "write_file",
)


class TranspileError(Exception):
    pass


# ---------------------------------------------------------------------------
# Line-range helpers (the only place AST is used)
# ---------------------------------------------------------------------------

@dataclass
class MemberRange:
    """A direct member of a top-level class (method or nested class)."""
    kind: str          # "func" | "class"
    name: str
    start: int         # 1-based inclusive
    end: int           # 1-based inclusive
    raw_lines: List[str]


def _parse_class_ranges(source: str) -> List[Tuple[str, int, int]]:
    """Return [(class_name, start_lineno, end_lineno), ...] (1-based, inclusive)."""
    tree = ast.parse(source)
    result = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            end = getattr(node, "end_lineno", node.lineno)
            result.append((node.name, node.lineno, end))
    return result


def _parse_raw_member_ranges(
    source: str, class_start: int, class_end: int
) -> List[Tuple[str, str, int, int]]:
    """
    Return [(kind, name, core_start, core_end), ...] for every direct
    FunctionDef / AsyncFunctionDef / ClassDef inside the given top-level class.
    AST is used only for line numbers.
    """
    tree = ast.parse(source)
    raw = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        if node.lineno != class_start:
            continue
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                deco_start = item.lineno
                if item.decorator_list:
                    deco_start = min(d.lineno for d in item.decorator_list)
                end = getattr(item, "end_lineno", item.lineno)
                raw.append(("func", item.name, deco_start, end))
            elif isinstance(item, ast.ClassDef):
                deco_start = item.lineno
                if item.decorator_list:
                    deco_start = min(d.lineno for d in item.decorator_list)
                end = getattr(item, "end_lineno", item.lineno)
                raw.append(("class", item.name, deco_start, end))
    return raw


def _expand_member_ranges(
    source_lines: List[str],
    class_start: int,
    class_end: int,
    raw_members: List[Tuple[str, str, int, int]],
) -> List[MemberRange]:
    if not raw_members:
        return []

    raw_members = sorted(raw_members, key=lambda t: t[2])
    expanded: List[MemberRange] = []
    prev_end = class_start

    for kind, name, core_start, core_end in raw_members:
        block_start = class_start + 1 if not expanded else prev_end + 1
        block_end = core_end
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
# Misc. Helpers
# ---------------------------------------------------------------------------


def _ensure_self_parameter(lines: List[str]) -> List[str]:
    """
    Guarantee that the first parameter of a method is `self`.
    Idempotent: if `self` is already present, the line is left unchanged.
    """
    out = []
    for line in lines:
        m = re.match(r'^([ \t]*)def\s+(\w+)\s*\((.*)\)\s*:', line)
        if not m:
            out.append(line)
            continue

        indent, name, params = m.groups()
        params = params.strip()

        if not params:
            new_params = "self"
        else:
            first = params.split(",")[0].strip()
            # already has self (with or without annotation)
            if first == "self" or first.startswith("self:") or first.startswith("self "):
                new_params = params
            else:
                new_params = f"self, {params}"

        out.append(f"{indent}def {name}({new_params}):")
    return out

# ---------------------------------------------------------------------------
# Stage B – structural split + marker classification
# ---------------------------------------------------------------------------

def _strip_marker_and_make_static(lines: List[str]) -> List[str]:
    """Turn an @externalmethod function into a clean @staticmethod function."""
    out = []
    for line in lines:
        if re.search(r"@externalmethod\b", line):
            indent = re.match(r"[ \t]*", line).group(0)
            out.append(f"{indent}@staticmethod")
        else:
            out.append(line)
    return out


def _strip_marker_only(lines: List[str]) -> List[str]:
    """Remove @internalmethod lines; keep everything else."""
    out = []
    for line in lines:
        if re.search(r"@(?:external|internal)method\b", line):
            continue
        out.append(line)
    return out


def stage_b_split(prefix_a: str) -> str:
    """
    Split every class that contains the markers into

        class Name_internal: ...
        _Name_internal = Name_internal()
        class Name: ...               # public façade

    Nested classes that carry @externalmethod / @internalmethod are treated
    as first-class members:
      - the marker decides which façade they land in
      - the marker is stripped
      - nothing inside the nested class is modified
      - @staticmethod is never applied to a nested class
    """
    source_lines = prefix_a.splitlines(keepends=True)
    plain_lines = [ln.rstrip("\n\r") for ln in source_lines]

    class_ranges = _parse_class_ranges(prefix_a)
    if not class_ranges:
        return prefix_a

    pieces: List[str] = []
    last_end = 0

    for class_name, cls_start, cls_end in class_ranges:
        pieces.extend(source_lines[last_end : cls_start - 1])

        raw = _parse_raw_member_ranges(prefix_a, cls_start, cls_end)
        members = _expand_member_ranges(plain_lines, cls_start, cls_end, raw)

        external_members: List[MemberRange] = []
        internal_members: List[MemberRange] = []

        for mem in members:
            text = "\n".join(mem.raw_lines)
            is_external = bool(re.search(r"@externalmethod\b", text))
            is_internal = bool(re.search(r"@internalmethod\b", text))

            if not is_external and not is_internal:
                raise TranspileError(
                    f"undecorated {mem.kind}: {mem.name} in class {class_name} "
                    f"(see lines {mem.start}-{mem.end})"
                )
            if is_external and is_internal:
                raise TranspileError(
                    f"{mem.kind} {mem.name} in class {class_name} has both "
                    f"@externalmethod and @internalmethod"
                )

            if is_external:
                external_members.append(mem)
            else:
                internal_members.append(mem)

        # ---- internal class (emitted first) ----
        internal_lines = [f"class {class_name}_internal:\n"]
        if not internal_members:
            internal_lines.append("    pass\n")
        else:
            for mem in internal_members:
                if mem.kind == "func":
                    transformed = _strip_marker_only(mem.raw_lines)
                else:  # nested class – strip marker only, leave interior alone
                    transformed = _strip_marker_only(mem.raw_lines)
                for ln in transformed:
                    internal_lines.append(ln + "\n")
                internal_lines.append("\n")

        pieces.extend(internal_lines)

        # ---- private instance ----
        pieces.append(f"_{class_name}_internal = {class_name}_internal()\n")
        pieces.append("\n")

        # ---- public class ----
        public_lines = [f"class {class_name}:\n"]
        if not external_members:
            public_lines.append("    pass\n")
        else:
            for mem in external_members:
                if mem.kind == "func":
                    # ordinary method → become @staticmethod
                    transformed = _strip_marker_and_make_static(mem.raw_lines)
                else:
                    # nested class → strip marker only, never make static
                    transformed = _strip_marker_only(mem.raw_lines)
                for ln in transformed:
                    public_lines.append(ln + "\n")
                public_lines.append("\n")

        pieces.extend(public_lines)
        last_end = cls_end

    pieces.extend(source_lines[last_end:])
    return "".join(pieces)


# ---------------------------------------------------------------------------
# Stage C – call-site rewrite
# ---------------------------------------------------------------------------

def _rewrite_calls_in_body(
    body_lines: List[str],
    internal_names: set[str],
    class_name: str,
    *,
    as_instance: bool,
) -> List[str]:
    """
    Conservative text rewrite of calls to internal methods.

    Only bare names are rewritten (never attribute accesses, never def lines).
    as_instance=True  →  rewrite to  self.name(
    as_instance=False →  rewrite to  _Class_internal.name(
    """
    if not internal_names:
        return body_lines

    prefix = "self." if as_instance else f"_{class_name}_internal."
    out = []
    for line in body_lines:
        # Never rewrite the function definition itself
        if re.match(r'^[ \t]*def\s+', line):
            out.append(line)
            continue

        new = line
        for name in internal_names:
            new = re.sub(
                rf"(?<!\.)\b{re.escape(name)}\s*\(",
                f"{prefix}{name}(",
                new,
            )
        out.append(new)
    return out

def stage_c_rewrite(prefix_b: str) -> str:
    """
    1. Discover every public / _internal pair.
    2. Rewrite call sites:
         - inside external methods  →  _Name_internal.method(...)
         - inside internal methods  →  self.method(...)
    3. Ensure every internal method signature begins with `self`.
    """
    source_lines = prefix_b.splitlines(keepends=True)
    plain_lines = [ln.rstrip("\n\r") for ln in source_lines]

    class_ranges = _parse_class_ranges(prefix_b)

    # public_name → set of internal method names
    internal_map: Dict[str, set[str]] = {}
    for class_name, cls_start, cls_end in class_ranges:
        if class_name.endswith("_internal"):
            continue
        internal_name = f"{class_name}_internal"
        internal_cls = next(
            ((n, s, e) for n, s, e in class_ranges if n == internal_name), None
        )
        if internal_cls is None:
            internal_map[class_name] = set()
            continue
        _, i_start, i_end = internal_cls
        i_raw = _parse_raw_member_ranges(prefix_b, i_start, i_end)
        names = {name for kind, name, _, _ in i_raw if kind == "func"}
        internal_map[class_name] = names

    pieces: List[str] = []
    last_end = 0

    for class_name, cls_start, cls_end in class_ranges:
        pieces.extend(source_lines[last_end : cls_start - 1])

        # ----------------------------------------------------------
        # Internal class – rewrite bodies + insure `self`
        # ----------------------------------------------------------
        if class_name.endswith("_internal"):
            public_name = class_name[: -len("_internal")]
            internal_names = internal_map.get(public_name, set())

            raw = _parse_raw_member_ranges(prefix_b, cls_start, cls_end)
            func_ranges = _expand_member_ranges(
                plain_lines, cls_start, cls_end, raw
            )

            new_class_lines = [f"class {class_name}:\n"]
            if not func_ranges:
                new_class_lines.append("    pass\n")
            else:
                for fn in func_ranges:
                    # 1. make sure the signature has self
                    body = _ensure_self_parameter(fn.raw_lines)
                    # 2. turn bare sibling calls into self.xxx(
                    body = _rewrite_calls_in_body(
                        body,
                        internal_names,
                        public_name,
                        as_instance=True,
                    )
                    for ln in body:
                        new_class_lines.append(ln + "\n")
                    new_class_lines.append("\n")

            pieces.extend(new_class_lines)
            last_end = cls_end
            continue

        # ----------------------------------------------------------
        # Public class – existing behaviour (as_instance=False)
        # ----------------------------------------------------------
        internal_names = internal_map.get(class_name, set())
        raw = _parse_raw_member_ranges(prefix_b, cls_start, cls_end)
        func_ranges = _expand_member_ranges(
            plain_lines, cls_start, cls_end, raw
        )

        new_class_lines = [f"class {class_name}:\n"]
        if not func_ranges:
            new_class_lines.append("    pass\n")
        else:
            for fn in func_ranges:
                body = _rewrite_calls_in_body(
                    fn.raw_lines,
                    internal_names,
                    class_name,
                    as_instance=False,
                )
                for ln in body:
                    new_class_lines.append(ln + "\n")
                new_class_lines.append("\n")

        pieces.extend(new_class_lines)
        last_end = cls_end

    pieces.extend(source_lines[last_end:])
    return "".join(pieces)


# ---------------------------------------------------------------------------
# Public entry point (writes B and C to the VirtualFS)
# ---------------------------------------------------------------------------

def transpile_to_tier_c(prefix_a: str) -> str:
    """
    Full A → B → C pipeline.

    - Writes prefix_tierB.py into the VirtualFS after Stage B.
    - Writes prefix_tierC.py into the VirtualFS after Stage C.
    - Returns the Stage-C text (so prefix_builder.build_prefixA still works).
    """
    tier_b = stage_b_split(prefix_a)
    write_file(
        "Database/prefix_tierB.py",
        tier_b,
        access_tier="agent_user",
    )

    tier_c = stage_c_rewrite(tier_b)
    write_file(
        "Database/prefix_tierC.py",
        tier_c,
        access_tier="agent_user",
    )

    return tier_c


def transpile_and_return(prefix_a: str) -> str:
    """Alias used by prefix_builder.build_prefixA()."""
    return transpile_to_tier_c(prefix_a)


if __name__ == "__main__":
    import sys
    from pathlib import Path

    if len(sys.argv) < 2:
        print("Usage: prefix_transpiler.py <prefix_tierA.py>", file=sys.stderr)
        sys.exit(1)

    src = Path(sys.argv[1]).read_text(encoding="utf-8")
    try:
        result = transpile_to_tier_c(src)
        print(result)
    except TranspileError as e:
        print(f"TranspileError: {e}", file=sys.stderr)
        sys.exit(1)
