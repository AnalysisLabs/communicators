#!/usr/bin/env python3
"""
Reversible mass-editor: prefix-legal class call names + drop disk imports / Demo.

Run from the parent of transponder_stack (edge-methods). --root is optional.

Usage
-----
  python fix_transponder_names.py list
  python fix_transponder_names.py plan
  python fix_transponder_names.py apply
  python fix_transponder_names.py revert --from-backup

What it does
------------
1. Rewrite Load-context names:
      Codec      -> Transponder_Codec
      Locators   -> Transponder_Locators
      FEATURES   -> Wire.FEATURES     (only inside class Wire)
      FALLBACK   -> Wire.FALLBACK     (only inside class Wire)
2. Delete peer imports that will not exist after concat
      from codec import Codec
      from locators import Locators
      from demo import Demo
      from shm_slot / tcp_socket_slot / unix_socket_slot / websocket_slot import ...
3. Delete codec.py module-level aliases (encode_msg = Codec.encode_msg, …)
4. Empty burst() bodies that only loop Demo.silly_for
5. Replace Demo.pulse_text(seq) with a local f-string

AST is used only for locations. Mutation is on source lines.
"""
from __future__ import annotations

import argparse
import ast
import shutil
import sys
from pathlib import Path
from typing import List, Optional, Tuple


TARGET_FILES = [
    "codec.py",
    "transponder_locators.py",
    "shm_slot.py",
    "station_tuner_slot.py",
    "http_mailbox_slot.py",
    "http_slot.py",
    "tcp_socket_slot.py",
    "unix_socket_slot.py",
    "websocket_slot.py",
    "wire.py",
    "transponder_module.py",
]

BACKUP_SUFFIX = ".pre_names"

# Load-name rewrites. FEATURES/FALLBACK are further gated to class Wire.
RENAME = {
    "Codec": "Transponder_Codec",
    "Locators": "Transponder_Locators",
}

WIRE_ATTR = {
    "FEATURES": "Wire.FEATURES",
    "FALLBACK": "Wire.FALLBACK",
}

DROP_IMPORT_MODULES = {
    "codec",
    "locators",
    "demo",
    "shm_slot",
    "tcp_socket_slot",
    "unix_socket_slot",
    "websocket_slot",
}

CODEC_ALIASES = {"encode_msg", "decode_msg", "encode_bytes", "canonicalize"}


def default_root() -> Path:
    cwd = Path.cwd()
    candidates = [
        cwd / "transponder_stack",
        cwd,
        Path(__file__).resolve().parent / "transponder_stack",
    ]
    for c in candidates:
        if c.is_dir() and (c / "wire.py").exists():
            return c
    return cwd / "transponder_stack"


def iter_targets(root: Path) -> List[Path]:
    files = []
    for name in TARGET_FILES:
        p = root / name
        if p.exists():
            files.append(p)
        else:
            print(f"warning: missing {p}", file=sys.stderr)
    return files


# ---------------------------------------------------------------------------
# AST discovery
# ---------------------------------------------------------------------------

class _ClassStack(ast.NodeVisitor):
    def __init__(self):
        self.stack: List[str] = []
        self.name_loads: List[Tuple[int, int, str, Optional[str]]] = []
        # (lineno, col, name, enclosing_class)
        self.imports: List[Tuple[int, int, str]] = []
        # (lineno, end_lineno, repr)
        self.aliases: List[Tuple[int, int, str]] = []
        self.bursts: List[Tuple[int, int, int]] = []
        # (def_lineno, body_start, end_lineno)
        self.pulse_calls: List[Tuple[int, int, int, int]] = []
        # (lineno, col, end_lineno, end_col)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load):
            cls = self.stack[-1] if self.stack else None
            self.name_loads.append((node.lineno, node.col_offset, node.id, cls))
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        mod = node.module or ""
        names = ", ".join(a.name for a in node.names)
        self.imports.append((node.lineno, getattr(node, "end_lineno", node.lineno), f"from {mod} import {names}"))
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        # module-level codec aliases only (visitor is not inside a class)
        if not self.stack and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            if node.targets[0].id in CODEC_ALIASES:
                self.aliases.append(
                    (node.lineno, getattr(node, "end_lineno", node.lineno), node.targets[0].id)
                )
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if node.name == "burst":
            self.bursts.append(
                (node.lineno, node.body[0].lineno if node.body else node.lineno,
                 getattr(node, "end_lineno", node.lineno))
            )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        f = node.func
        if (
            isinstance(f, ast.Attribute)
            and isinstance(f.value, ast.Name)
            and f.value.id == "Demo"
            and f.attr == "pulse_text"
        ):
            self.pulse_calls.append(
                (
                    node.lineno,
                    node.col_offset,
                    getattr(node, "end_lineno", node.lineno),
                    getattr(node, "end_col_offset", node.col_offset),
                )
            )
        self.generic_visit(node)


def analyze(source: str) -> _ClassStack:
    v = _ClassStack()
    v.visit(ast.parse(source))
    return v


def _line_has_demo_silly(source_lines: List[str], start: int, end: int) -> bool:
    chunk = "".join(source_lines[start - 1 : end])
    return "Demo.silly_for" in chunk


# ---------------------------------------------------------------------------
# Mutations (right-to-left so columns stay valid)
# ---------------------------------------------------------------------------

def apply_to_source(source: str, filename: str, *, do_write: bool) -> Tuple[str, List[str]]:
    info = analyze(source)
    lines = source.splitlines(keepends=True)
    log: List[str] = []

    # Planned name replacements: (lineno, col, old, new)
    renames: List[Tuple[int, int, str, str]] = []
    for lineno, col, name, cls in info.name_loads:
        if name in RENAME:
            new = RENAME[name]
            renames.append((lineno, col, name, new))
        elif name in WIRE_ATTR and cls == "Wire":
            new = WIRE_ATTR[name]
            renames.append((lineno, col, name, new))

    # Dedup exact positions
    seen = set()
    uniq = []
    for item in renames:
        key = item[:3]
        if key in seen:
            continue
        seen.add(key)
        uniq.append(item)
    renames = uniq

    drop_lines: set[int] = set()

    for start, end, text in info.imports:
        mod = text.split()[1] if text.startswith("from ") else ""
        # text is "from codec import Codec"
        parts = text.split()
        mod = parts[1] if len(parts) >= 2 else ""
        if mod in DROP_IMPORT_MODULES:
            for ln in range(start, end + 1):
                drop_lines.add(ln)
            log.append(f"DROP-IMPORT   {filename}:{start}  {text}")

    if filename == "codec.py":
        for start, end, name in info.aliases:
            for ln in range(start, end + 1):
                drop_lines.add(ln)
            log.append(f"DROP-ALIAS    {filename}:{start}  {name} = ...")

    empty_bursts: List[Tuple[int, int, int]] = []
    for def_ln, body_ln, end_ln in info.bursts:
        if _line_has_demo_silly(lines, def_ln, end_ln):
            empty_bursts.append((def_ln, body_ln, end_ln))
            log.append(f"EMPTY-BURST   {filename}:{def_ln}  drop Demo.silly_for loop")

    for lineno, col, end_ln, end_col in info.pulse_calls:
        log.append(f"REWRITE-PULSE {filename}:{lineno}  Demo.pulse_text(...) -> f'pulse {{seq}}'")

    for lineno, col, old, new in sorted(renames, key=lambda t: (t[0], t[1])):
        log.append(f"RENAME        {filename}:{lineno}:{col}  {old} -> {new}")

    if not do_write:
        return source, log

    # 1. Name replacements, bottom-right first
    for lineno, col, old, new in sorted(renames, key=lambda t: (t[0], t[1]), reverse=True):
        idx = lineno - 1
        line = lines[idx]
        # col is 0-based in the logical line without considering keepends
        raw = line.rstrip("\n")
        nl = line[len(raw):]
        if raw[col: col + len(old)] != old:
            log.append(f"MISS-RENAME   {filename}:{lineno}:{col}  expected {old!r} got {raw[col:col+len(old)]!r}")
            continue
        raw = raw[:col] + new + raw[col + len(old):]
        lines[idx] = raw + nl

    # 2. Demo.pulse_text(...) -> f"pulse {seq}"  (re-parse after renames? pulse is Demo, unchanged)
    # Do on original coords; pulse lines do not contain Codec/Locators.
    for lineno, col, end_ln, end_col in sorted(info.pulse_calls, key=lambda t: (t[0], t[1]), reverse=True):
        if lineno != end_ln:
            log.append(f"MISS-PULSE    {filename}:{lineno}  multi-line call, skipped")
            continue
        idx = lineno - 1
        raw = lines[idx].rstrip("\n")
        nl = lines[idx][len(raw):]
        raw = raw[:col] + 'f"pulse {seq}"' + raw[end_col:]
        lines[idx] = raw + nl

    # 3. Empty burst bodies (after token edits so line numbers still match original AST)
    for def_ln, body_ln, end_ln in sorted(empty_bursts, key=lambda t: t[0], reverse=True):
        # Keep the def line; replace everything from body_ln through end_ln with a single pass
        def_raw = lines[def_ln - 1]
        indent = def_raw[: len(def_raw) - len(def_raw.lstrip(" \t"))]
        body_indent = indent + "    "
        new_body = f"{body_indent}pass\n"
        # drop body lines
        del lines[body_ln - 1 : end_ln]
        lines.insert(body_ln - 1, new_body)

    # 4. Drop import / alias lines (1-based set). After burst deletion, line
    #    numbers above bursts shifted. Imports sit at the top, bursts lower,
    #    so import line numbers are still valid.
    for ln in sorted(drop_lines, reverse=True):
        if 1 <= ln <= len(lines):
            del lines[ln - 1]

    text = "".join(lines)
    text = _collapse_blank_runs(text)
    return text, log


def _collapse_blank_runs(text: str) -> str:
    """At most two consecutive blank lines."""
    out: List[str] = []
    blank = 0
    for line in text.splitlines(keepends=True):
        if line.strip() == "":
            blank += 1
            if blank <= 2:
                out.append(line if line.endswith("\n") else line + "\n")
        else:
            blank = 0
            out.append(line)
    return "".join(out)


def cmd_list(root: Path) -> int:
    print(f"# planned edits under {root}\n")
    for path in iter_targets(root):
        src = path.read_text(encoding="utf-8")
        _, log = apply_to_source(src, path.name, do_write=False)
        print(f"## {path.name}")
        if not log:
            print("  (no edits)")
        else:
            for line in log:
                print("  " + line)
        print()
    return 0


def cmd_plan_or_apply(root: Path, *, apply: bool, backup: bool) -> int:
    for path in iter_targets(root):
        src = path.read_text(encoding="utf-8")
        new_src, log = apply_to_source(src, path.name, do_write=apply)
        print(f"## {path.name}")
        if not log:
            print("  (no edits)")
        else:
            for line in log:
                print("  " + line)
        if apply:
            if new_src != src:
                if backup:
                    bak = path.with_name(path.name + BACKUP_SUFFIX)
                    if not bak.exists():
                        shutil.copy2(path, bak)
                        print(f"  backup -> {bak.name}")
                    else:
                        print(f"  backup exists, left {bak.name} alone")
                path.write_text(new_src, encoding="utf-8")
                print(f"  wrote {path.name}")
            else:
                print("  no changes")
        print()
    return 0


def cmd_revert(root: Path, *, from_backup: bool) -> int:
    if not from_backup:
        print("this editor has no token-level strip; use --from-backup", file=sys.stderr)
        return 2
    for path in iter_targets(root):
        bak = path.with_name(path.name + BACKUP_SUFFIX)
        if not bak.exists():
            print(f"## {path.name}  no {bak.name}, skipped")
            continue
        shutil.copy2(bak, path)
        print(f"## {path.name}  restored from {bak.name}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["list", "plan", "apply", "revert"])
    p.add_argument("--root", type=Path, default=None)
    p.add_argument("--no-backup", action="store_true")
    p.add_argument("--from-backup", action="store_true")
    args = p.parse_args(argv)
    root = (args.root or default_root()).resolve()
    if not root.is_dir():
        print(f"root does not exist: {root}", file=sys.stderr)
        return 2
    print(f"# root = {root}")
    if args.command == "list":
        return cmd_list(root)
    if args.command == "plan":
        return cmd_plan_or_apply(root, apply=False, backup=False)
    if args.command == "apply":
        return cmd_plan_or_apply(root, apply=True, backup=not args.no_backup)
    if args.command == "revert":
        return cmd_revert(root, from_backup=args.from_backup)
    return 2


if __name__ == "__main__":
    sys.exit(main())
