"""Prefix class-blob queue. Paste into prefix_builder.py.

File names do not appear on blobs. A blob is a class identifier plus its
source text, cut by AST line ranges. Multi-class files yield one blob per
top-level class.

Does not rectify, does not run Stage B, does not emit a prefix.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Iterable, Sequence


@dataclass(frozen=True)
class ClassBlob:
    """One top-level class, ready to concat later."""

    class_name: str
    text: str
    origin_uuid: str = ""  # FileRef.uuid only, for debug; not a path


@dataclass
class PrefixQueue:
    """Ordered bag of class blobs. Append-only until reset()."""

    blobs: list[ClassBlob] = field(default_factory=list)

    def reset(self) -> None:
        self.blobs.clear()

    def extend(self, blobs: Iterable[ClassBlob]) -> None:
        self.blobs.extend(blobs)

    def class_names(self) -> list[str]:
        return [b.class_name for b in self.blobs]

    def __iter__(self):
        return iter(self.blobs)

    def __len__(self) -> int:
        return len(self.blobs)

    def __repr__(self) -> str:
        parts = [f"{b.class_name}({len(b.text)})" for b in self.blobs]
        return "PrefixQueue([" + ", ".join(parts) + "])"


QUEUE = PrefixQueue()


def _parse_class_ranges(source: str) -> list[tuple[str, int, int]]:
    """[(class_name, start_lineno, end_lineno), ...] 1-based inclusive.

    AST is used only for numbers. Decorators sit on or above ClassDef.lineno;
    the walk-up in cut_class captures them.
    """
    tree = ast.parse(source)
    ranges: list[tuple[str, int, int]] = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            end = getattr(node, "end_lineno", node.lineno)
            ranges.append((node.name, node.lineno, end))
    return ranges


def _first_decorator_lineno(lines: list[str], class_lineno: int) -> int:
    """Walk up from `class` through contiguous @decorator lines only."""
    i = class_lineno  # 1-based
    while i > 1:
        raw = lines[i - 2].lstrip()
        if raw.startswith("@"):
            i -= 1
            continue
        break
    return i


def cut_class(source: str, class_name: str) -> str:
    """Return one top-level class body, including its decorator stack."""
    lines = source.splitlines(keepends=True)
    for name, start, end in _parse_class_ranges(source):
        if name != class_name:
            continue
        start = _first_decorator_lineno(lines, start)
        return "".join(lines[start - 1 : end]).rstrip() + "\n"
    raise KeyError(f"{class_name!r} is not a top-level class in source")


def cut_all_classes(source: str, *, origin_uuid: str = "") -> list[ClassBlob]:
    """Every top-level class in *source*, in file order."""
    blobs: list[ClassBlob] = []
    for name, _, _ in _parse_class_ranges(source):
        blobs.append(
            ClassBlob(
                class_name=name,
                text=cut_class(source, name),
                origin_uuid=origin_uuid,
            )
        )
    return blobs


def enqueue_classes_from_refs(
    refs: Sequence["FileRef"],
    *,
    queue: PrefixQueue | None = None,
    reset: bool = True,
) -> PrefixQueue:
    """Load each FileRef, cut every top-level class, push onto the queue.

    `refs` order is the only order that matters here. Tier/order mapping
    is a later table; do not infer it from file names.
    """
    q = queue if queue is not None else QUEUE
    if reset:
        q.reset()
    for ref in refs:
        source = _load_source(ref)
        q.extend(cut_all_classes(source, origin_uuid=ref.uuid))
    return q


def describe_queue(queue: PrefixQueue | None = None) -> str:
    q = queue if queue is not None else QUEUE
    lines = []
    for i, b in enumerate(q):
        head = next((ln for ln in b.text.splitlines() if ln.strip()), "")
        lines.append(
            f"{i:02d}  {b.class_name:<24}  {len(b.text):6d} chars  {head}"
        )
    return "\n".join(lines)
