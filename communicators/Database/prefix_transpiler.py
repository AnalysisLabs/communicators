#!/usr/bin/env python3
"""
prefix_transpiler.py – A → B → C metamorphosis for Communicators prefixes.

Stage B (structural split)
  - Every class that uses the markers is split:
      OriginalName          – only @externalmethod methods (decorator → @staticmethod)
      OriginalName_internal – only @internalmethod methods (decorator stripped)
  - Undecorated methods raise:
      UndecoratedFunctionError: undecorated function: {name} in class: {cls}
  - Result is written to Database/prefix_tierB.py

Stage C (call-site rewrite)
  - For each split class a private instance is emitted:
      _OriginalName_internal = OriginalName_internal()
  - Bare calls to names that now live on the internal class are rewritten
    to go through that private instance (Option C1).
  - Cross-class public calls (Manifest.info, etc.) are left untouched.
  - Result is written to Database/prefix_tierC.py

The markers @externalmethod / @internalmethod are recognised only by this
transpiler; they never appear in the emitted source.

Side effect: transpile_to_tier_c always persists both B and C via vfs_writer
so the intermediate and final forms are inspectable in the VirtualFS.
"""

from __future__ import annotations

import ast
import sys
from typing import Dict, List, Optional, Set, Tuple

from vfs_writer import write_file


class UndecoratedFunctionError(Exception):
    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _marker(decorator_list: list) -> Optional[str]:
    """Return 'externalmethod' or 'internalmethod' if present, else None."""
    for dec in decorator_list:
        if isinstance(dec, ast.Name) and dec.id in ("externalmethod", "internalmethod"):
            return dec.id
        # tolerate @something.externalmethod style if it ever appears
        if isinstance(dec, ast.Attribute) and dec.attr in ("externalmethod", "internalmethod"):
            return dec.attr
    return None


def _has_self(args: ast.arguments) -> bool:
    return bool(args.args) and args.args[0].arg == "self"


def _strip_internalmethod_only(decorator_list: list) -> list:
    """Remove only @internalmethod markers; keep every other decorator."""
    kept = []
    for dec in decorator_list:
        if isinstance(dec, ast.Name) and dec.id == "internalmethod":
            continue
        if isinstance(dec, ast.Attribute) and dec.attr == "internalmethod":
            continue
        kept.append(dec)
    return kept


def _prepare_internal_method(func: ast.FunctionDef) -> ast.FunctionDef:
    """
    Prepare a method for the *_internal class:
      - strip only @internalmethod (leave any other decorators intact)
      - guarantee a leading 'self' parameter
    """
    new_decorators = _strip_internalmethod_only(func.decorator_list)

    if _has_self(func.args):
        new_args = func.args
    else:
        new_args = ast.arguments(
            posonlyargs=list(func.args.posonlyargs),
            args=[ast.arg(arg="self")] + list(func.args.args),
            vararg=func.args.vararg,
            kwonlyargs=list(func.args.kwonlyargs),
            kw_defaults=list(func.args.kw_defaults),
            kwarg=func.args.kwarg,
            defaults=list(func.args.defaults),
        )

    return ast.FunctionDef(
        name=func.name,
        args=new_args,
        body=func.body,
        decorator_list=new_decorators,
        returns=func.returns,
        type_comment=func.type_comment,
    )


def _make_staticmethod(func: ast.FunctionDef) -> ast.FunctionDef:
    """Return func with @staticmethod as its only decorator."""
    return ast.FunctionDef(
        name=func.name,
        args=func.args,
        body=func.body,
        decorator_list=[ast.Name(id="staticmethod", ctx=ast.Load())],
        returns=func.returns,
        type_comment=func.type_comment,
    )


# ---------------------------------------------------------------------------
# Stage B – structural split
# ---------------------------------------------------------------------------

def stage_b_split(source: str) -> str:
    tree = ast.parse(source)
    new_body: List[ast.stmt] = []

    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            new_body.append(node)
            continue

        external_methods: List[ast.FunctionDef] = []
        internal_methods: List[ast.FunctionDef] = []

        for item in node.body:
            if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # keep non-method statements (docstrings, assignments, …)
                # in the public class for now
                external_methods.append(item)  # type: ignore[arg-type]
                continue

            marker = _marker(item.decorator_list)
            if marker is None:
                raise UndecoratedFunctionError(
                    f"undecorated function: {item.name} in class: {node.name}"
                )
            if marker == "externalmethod":
                # strip marker, force @staticmethod, keep signature as-is
                external_methods.append(_make_staticmethod(item))
            else:  # internalmethod
                # strip only @internalmethod, guarantee real 'self'
                internal_methods.append(_prepare_internal_method(item))

        # Private instance
        if internal_methods:
            internal_class = ast.ClassDef(
                name=f"{node.name}_internal",
                bases=[],
                keywords=[],
                body=internal_methods,
                decorator_list=[],
            )
            new_body.append(internal_class)

            # Private instance (Option C1) – emitted right after the pair
            # _Name_internal = Name_internal()
            assign = ast.Assign(
                targets=[ast.Name(id=f"_{node.name}_internal", ctx=ast.Store())],
                value=ast.Call(
                    func=ast.Name(id=f"{node.name}_internal", ctx=ast.Load()),
                    args=[],
                    keywords=[],
                ),
            )
            new_body.append(assign)

        # Public façade class (original name) – emitted after its
        # internal companion so definition order is safe.
        public_class = ast.ClassDef(
            name=node.name,
            bases=node.bases,
            keywords=node.keywords,
            body=external_methods or [ast.Pass()],
            decorator_list=node.decorator_list,
        )
        new_body.append(public_class)


    new_tree = ast.Module(body=new_body, type_ignores=[])
    ast.fix_missing_locations(new_tree)
    return ast.unparse(new_tree) + "\n"


# ---------------------------------------------------------------------------
# Stage C – call-site rewrite
# ---------------------------------------------------------------------------

class CallRewriter(ast.NodeTransformer):
    """
    Rewrite bare Name calls that refer to internal methods of the current class
    so they go through the private instance _ClassName_internal.
    """

    def __init__(self, class_name: str, internal_names: Set[str]):
        self.class_name = class_name
        self.internal_names = internal_names
        self.impl_name = f"_{class_name}_internal"

    def visit_Call(self, node: ast.Call) -> ast.Call:
        self.generic_visit(node)
        # bare name call:  foo(...)
        if isinstance(node.func, ast.Name) and node.func.id in self.internal_names:
            node.func = ast.Attribute(
                value=ast.Name(id=self.impl_name, ctx=ast.Load()),
                attr=node.func.id,
                ctx=ast.Load(),
            )
        return node


def stage_c_rewrite(source: str) -> str:
    tree = ast.parse(source)

    # Collect, for every public class, the set of names that live on its _internal
    internal_map: Dict[str, Set[str]] = {}  # public_name -> {method names}
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name.endswith("_internal"):
            public = node.name[: -len("_internal")]
            names = {
                item.name
                for item in node.body
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
            internal_map[public] = names

    new_body: List[ast.stmt] = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            new_body.append(node)
            continue

        # Only rewrite bodies of the public classes that have an internal twin
        if node.name in internal_map:
            rewriter = CallRewriter(node.name, internal_map[node.name])
            new_body.append(rewriter.visit(node))
        else:
            # also rewrite inside the _internal classes themselves
            # (in case one internal method calls another)
            if node.name.endswith("_internal"):
                public = node.name[: -len("_internal")]
                if public in internal_map:
                    rewriter = CallRewriter(public, internal_map[public])
                    new_body.append(rewriter.visit(node))
                else:
                    new_body.append(node)
            else:
                new_body.append(node)

    new_tree = ast.Module(body=new_body, type_ignores=[])
    ast.fix_missing_locations(new_tree)
    return ast.unparse(new_tree) + "\n"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def transpile_to_tier_c(source: str) -> str:
    """
    Full A → B → C transformation.

    - Writes the intermediate result to Database/prefix_tierB.py
    - Writes the final result to Database/prefix_tierC.py
    - Returns the tier-C source so callers (prefix_builder) can still use it
      as the live prefix.
    """
    tier_b = stage_b_split(source)
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


# ---------------------------------------------------------------------------
# CLI helper (optional)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser(description="Transpile a prefix from tier A to tier C")
    parser.add_argument("input", type=Path, help="Path to prefix_tierA.py (or any A-source)")
    parser.add_argument("-o", "--output", type=Path, help="Write result here instead of stdout")
    parser.add_argument("--stage", choices=("b", "c", "full"), default="full",
                        help="Stop after stage B, run only C, or full A→C")
    args = parser.parse_args()

    src = args.input.read_text(encoding="utf-8")

    try:
        if args.stage == "b":
            result = stage_b_split(src)
        elif args.stage == "c":
            result = stage_c_rewrite(src)
        else:
            result = transpile_to_tier_c(src)
    except UndecoratedFunctionError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)

    if args.output:
        args.output.write_text(result, encoding="utf-8")
        print(f"Wrote {args.output} ({len(result)} bytes)")
    else:
        print(result)
