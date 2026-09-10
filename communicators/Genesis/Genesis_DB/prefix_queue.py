"""Prefix class-blob queue.

_load_source fetches text (str → VirtualFS, FileRef → registry disk).
AST line ranges cut one class. A source with no top-level class becomes
one whole-file blob (standard.py).

File names are not blob identity. origin is uuid or the VFS path string.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Callable, Iterable, Sequence


@dataclass(frozen=True)
class ClassBlob:
    class_name: str
    text: str
    origin: str = ""
    whole_file: bool = False


@dataclass
class PrefixQueue:
    blobs: list[ClassBlob] = field(default_factory=list)

    def reset(self) -> None:
        self.blobs.clear()

    def extend(self, blobs: Iterable[ClassBlob]) -> None:
        self.blobs.extend(blobs)

    def class_names(self) -> list[str]:
        return [b.class_name for b in self.blobs]

    def by_name(self) -> dict[str, ClassBlob]:
        return {b.class_name: b for b in self.blobs}

    def __iter__(self):
        return iter(self.blobs)

    def __len__(self) -> int:
        return len(self.blobs)

    def __repr__(self) -> str:
        parts = [f"{b.class_name}({len(b.text)})" for b in self.blobs]
        return "PrefixQueue([" + ", ".join(parts) + "])"


QUEUE = PrefixQueue()


def _origin_of(ref) -> str:
    if isinstance(ref, str):
        return ref
    return str(getattr(ref, "uuid", "") or getattr(ref, "file_name", ""))


def _whole_file_name(ref) -> str:
    if isinstance(ref, str):
        return ref.rsplit("/", 1)[-1].removesuffix(".py")
    name = getattr(ref, "file_name", "") or ""
    return name.removesuffix(".py") or "module"


def _parse_class_ranges(source: str) -> list[tuple[str, int, int]]:
    tree = ast.parse(source)
    ranges: list[tuple[str, int, int]] = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            end = getattr(node, "end_lineno", node.lineno)
            ranges.append((node.name, node.lineno, end))
    return ranges


def _first_decorator_lineno(lines: list[str], class_lineno: int) -> int:
    i = class_lineno
    while i > 1:
        raw = lines[i - 2].lstrip()
        if raw.startswith("@"):
            i -= 1
            continue
        break
    return i


def cut_class(source: str, class_name: str) -> str:
    lines = source.splitlines(keepends=True)
    for name, start, end in _parse_class_ranges(source):
        if name != class_name:
            continue
        start = _first_decorator_lineno(lines, start)
        return "".join(lines[start - 1 : end]).rstrip() + "\n"
    raise KeyError(f"{class_name!r} is not a top-level class in source")


def cut_all_classes(source: str, *, origin: str = "") -> list[ClassBlob]:
    return [
        ClassBlob(class_name=name, text=cut_class(source, name), origin=origin)
        for name, _, _ in _parse_class_ranges(source)
    ]


def whole_file_blob(source: str, class_name: str, *, origin: str = "") -> ClassBlob:
    return ClassBlob(
        class_name=class_name,
        text=source.rstrip() + "\n",
        origin=origin,
        whole_file=True,
    )


def blobs_from_source(source: str, ref) -> list[ClassBlob]:
    """Probe helper: every class, or the whole file if there is none."""
    origin = _origin_of(ref)
    blobs = cut_all_classes(source, origin=origin)
    if blobs:
        return blobs
    return [whole_file_blob(source, _whole_file_name(ref), origin=origin)]


def enqueue_classes_from_refs(
    refs: Sequence[object],
    *,
    queue: PrefixQueue | None = None,
    reset: bool = True,
    loader: Callable[[object], str] | None = None,
) -> PrefixQueue:
    load = loader if loader is not None else globals().get("_load_source")
    if load is None:
        raise RuntimeError("_load_source is not defined")
    q = queue if queue is not None else QUEUE
    if reset:
        q.reset()
    for ref in refs:
        q.extend(blobs_from_source(load(ref), ref))
    return q


def describe_queue(queue: PrefixQueue | None = None) -> str:
    q = queue if queue is not None else QUEUE
    lines = []
    for i, b in enumerate(q):
        head = next((ln for ln in b.text.splitlines() if ln.strip()), "")
        kind = "file" if b.whole_file else "class"
        lines.append(
            f"{i:02d}  {b.class_name:<24}  {kind:<5}  {len(b.text):6d} chars  {head}"
        )
    return "\n".join(lines)
