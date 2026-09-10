#!/usr/bin/env python3
"""
prefix_builder.py – assemble tiered runtime prefixes for Communicators programs.

Structure comes from MEMBERS. There is no directory walk.
_load_source fetches each row (FileRef → registry disk, str → VirtualFS).
cut_class / whole_file / communicators_root turn that text into blobs.
emit_prefix concatenates blobs in (tier, order).

Old named builders remain as thin wrappers around emit_prefix so
write_prefix_to_vfs keeps working. They are not the law.

Tier A still runs transpile_to_tier_d on the full emitted string.
Do not point this graph at the obsolete T2 transponder blob
(0f589da7-…). Faces come from the stack copy (b03e35ee-…).
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Sequence


# ---------------------------------------------------------------------------
# Boot — disk imports that preexist the finished prefix
# ---------------------------------------------------------------------------

def find_communicators_root(start=None) -> Path:
    """Walk up until we find a directory named 'communicators'."""
    d = Path(start or Path.cwd()).absolute()
    while d != Path("/"):
        if d.name == "communicators":
            return d
        d = d.parent
    return Path.cwd()


root = find_communicators_root()

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
from path_reffs import *  # FileRef, resolve_path


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

_prefix_transpiler_ref = FileRef(
    uuid="c3c395ae-368a-4844-91d8-0d3d69b3eae5",
    file_path="Genesis/Genesis_DB",
    file_name="prefix_transpiler.py",
)

transpile_to_tier_d, = from_path_import(
    resolve_path(
        _prefix_transpiler_ref.uuid,
        _prefix_transpiler_ref.file_path,
        _prefix_transpiler_ref.file_name,
    ),
    "transpile_to_tier_d",
)


def _load_source(ref) -> str:
    if isinstance(ref, str):
        return read_file(ref)
    if isinstance(ref, FileRef):
        path = resolve_path(ref.uuid, ref.file_path, ref.file_name)
        if not path.exists():
            raise FileNotFoundError(f"Source not found for {ref}: {path}")
        return path.read_text(encoding="utf-8")
    raise TypeError(f"_load_source expected str or FileRef, got {type(ref)!r}")


# ---------------------------------------------------------------------------
# Module sources
# ---------------------------------------------------------------------------

_PATH_REFFS = "Database/path_reffs.py"
_ATOMIC_IMPORTER = "Database/atomic_importer.py"

_CODEC_REF = FileRef(
    uuid="37dd39db-1e88-462b-99d0-46c1c32f6043",
    file_path="Genesis/internal_imports/edge-methods/transponder_stack",
    file_name="codec.py",
)
_LOCATORS_REF = FileRef(
    uuid="9f3c5396-193c-4951-a47a-929cbc60d82c",
    file_path="Genesis/internal_imports/edge-methods/transponder_stack",
    file_name="transponder_locators.py",
)
_WIRE_REF = FileRef(
    uuid="af110108-d8d7-4c51-bffd-0723879bbf09",
    file_path="Genesis/internal_imports/edge-methods/transponder_stack",
    file_name="wire.py",
)
_TCP_SLOT_REF = FileRef(
    uuid="e622891d-6396-4f0c-a038-2cbc5d119fad",
    file_path="Genesis/internal_imports/edge-methods/transponder_stack",
    file_name="tcp_socket_slot.py",
)
_UNIX_SLOT_REF = FileRef(
    uuid="3d2e0925-4f99-4440-b55c-ca4b116c5d64",
    file_path="Genesis/internal_imports/edge-methods/transponder_stack",
    file_name="unix_socket_slot.py",
)
_WS_SLOT_REF = FileRef(
    uuid="c5ab9ec7-19c6-4786-b997-90d0a050b96e",
    file_path="Genesis/internal_imports/edge-methods/transponder_stack",
    file_name="websocket_slot.py",
)
_SHM_SLOT_REF = FileRef(
    uuid="8df05483-984e-4e81-bf90-6b4f994f1987",
    file_path="Genesis/internal_imports/edge-methods/transponder_stack",
    file_name="shm_slot.py",
)
_HTTP_SLOT_REF = FileRef(
    uuid="503640a9-f085-406d-8837-ac5b0208a1f3",
    file_path="Genesis/internal_imports/edge-methods/transponder_stack",
    file_name="http_slot.py",
)
_HTTP_MAILBOX_SLOT_REF = FileRef(
    uuid="7235367f-2b5d-4999-ba7b-859f913c5492",
    file_path="Genesis/internal_imports/edge-methods/transponder_stack",
    file_name="http_mailbox_slot.py",
)
_STATION_TUNER_SLOT_REF = FileRef(
    uuid="d198072a-2724-4986-a7f9-11de64b26623",
    file_path="Genesis/internal_imports/edge-methods/transponder_stack",
    file_name="station_tuner_slot.py",
)
_TRANSPONDER_REF = FileRef(
    uuid="b03e35ee-e03c-4eef-beec-a965790a1708",
    file_path="Genesis/internal_imports/edge-methods/transponder_stack",
    file_name="transponder_module.py",
)
_STANDARD_REF = FileRef(
    uuid="8090dc7b-4a91-448d-8ab0-0b5acfbb5dee",
    file_path="Genesis/internal_imports",
    file_name="standard.py",
)
_MANIFEST_REF = FileRef(
    uuid="64bf54d1-e607-4bfc-b6ba-73ccc2748dd4",
    file_path="Genesis/internal_imports",
    file_name="manifest.py",
)

SOURCE_REFS = (
    _STANDARD_REF,
    _PATH_REFFS,
    _ATOMIC_IMPORTER,
    _MANIFEST_REF,
    _CODEC_REF,
    _LOCATORS_REF,
    _WIRE_REF,
    _TCP_SLOT_REF,
    _UNIX_SLOT_REF,
    _WS_SLOT_REF,
    _SHM_SLOT_REF,
    _HTTP_SLOT_REF,
    _HTTP_MAILBOX_SLOT_REF,
    _STATION_TUNER_SLOT_REF,
    _TRANSPONDER_REF,
)


# ---------------------------------------------------------------------------
# Queue + cutter
# ---------------------------------------------------------------------------

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


def whole_file_blob(source: str, class_name: str, *, origin: str = "") -> ClassBlob:
    return ClassBlob(
        class_name=class_name,
        text=source.rstrip() + "\n",
        origin=origin,
        whole_file=True,
    )


# ---------------------------------------------------------------------------
# Membership table — the law
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Member:
    tier: int
    order: int
    class_name: str
    prefix_name: str
    ref: object | None
    prepare: str = "cut_class"  # whole_file | cut_class | communicators_root
    banner: str | None = None


# Member(tier, order, class_name, prefix_name, ref, prepare=..., banner=...)
#
#   tier         0 std+root · 1 scaffold then T1 helpers · 2 slots · 3 Wire · 4 faces
#   order        concat order inside the tier. T1 scaffold is 0-2; helpers start at 10
#   class_name   blob / banner identifier
#   prefix_name  hatch module spelling (transponder_tcp, …)
#   ref          FileRef | "Database/…" | None
#   prepare      whole_file | cut_class | communicators_root
#   banner       optional "# === … ===" override
#
MEMBERS: tuple[Member, ...] = (
    Member(0, 0, "standard", "standard", _STANDARD_REF, "whole_file",
           "standard.py (from VirtualFS)"),
    Member(0, 1, "COMMUNICATORS_ROOT", "COMMUNICATORS_ROOT", None, "communicators_root",
           "COMMUNICATORS_ROOT (resolved at prefix-build time)"),
    Member(1, 0, "PathReffs", "path_reffs", _PATH_REFFS, "whole_file"),
    Member(1, 1, "AtomicImporter", "atomic_importer", _ATOMIC_IMPORTER, "whole_file"),
    Member(1, 2, "Manifest", "manifest", _MANIFEST_REF, "whole_file"),
    Member(1, 10, "Transponder_Codec", "transponder_codec", _CODEC_REF),
    Member(1, 11, "Transponder_Locators", "transponder_locators", _LOCATORS_REF),
    Member(1, 12, "SlotRefused", "transponder_slot_refused", _WIRE_REF),
    Member(1, 13, "DirWatch", "transponder_dir_watch", _SHM_SLOT_REF),
    Member(1, 14, "UdpMail", "transponder_udp_mail", _STATION_TUNER_SLOT_REF),
    Member(1, 15, "Mailbox", "transponder_mailbox_bin", _HTTP_MAILBOX_SLOT_REF),
    Member(2, 0, "TcpSlot", "transponder_tcp", _TCP_SLOT_REF),
    Member(2, 1, "UnixSlot", "transponder_unix", _UNIX_SLOT_REF),
    Member(2, 2, "WsSlot", "transponder_ws", _WS_SLOT_REF),
    Member(2, 3, "ShmSlot", "transponder_shm", _SHM_SLOT_REF),
    Member(2, 4, "HttpSlot", "transponder_http", _HTTP_SLOT_REF),
    Member(2, 5, "MailboxServer", "transponder_mailbox_server", _HTTP_MAILBOX_SLOT_REF),
    Member(2, 6, "MailboxClient", "transponder_mailbox_client", _HTTP_MAILBOX_SLOT_REF),
    Member(2, 7, "Station", "transponder_station", _STATION_TUNER_SLOT_REF),
    Member(2, 8, "Tuner", "transponder_tuner", _STATION_TUNER_SLOT_REF),
    Member(3, 0, "Wire", "transponder_wire", _WIRE_REF),
    Member(4, 0, "NegativeCom", "transponder_negative", _TRANSPONDER_REF),
    Member(4, 1, "PositiveCom", "transponder_positive", _TRANSPONDER_REF),
)


class UnmappedClass(KeyError):
    pass


def _banner(member: Member) -> str:
    if member.banner:
        return f"# === {member.banner} ==="
    return f"# === {member.class_name} (class) ==="


def _root_block() -> str:
    return (
        "from pathlib import Path\n"
        f"COMMUNICATORS_ROOT = Path({str(root)!r})\n"
    )


def fill_queue(*, queue: PrefixQueue | None = None) -> PrefixQueue:
    q = queue if queue is not None else QUEUE
    q.reset()
    cache: dict[object, str] = {}

    for member in MEMBERS:
        if member.prepare == "communicators_root":
            q.extend([
                ClassBlob(
                    member.class_name,
                    _root_block(),
                    origin="generated",
                    whole_file=True,
                )
            ])
            continue
        ref = member.ref
        key = ref if isinstance(ref, str) else id(ref)
        if key not in cache:
            cache[key] = _load_source(ref)
        source = cache[key]
        origin = _origin_of(ref)
        if member.prepare == "whole_file":
            q.extend([whole_file_blob(source, member.class_name, origin=origin)])
        elif member.prepare == "cut_class":
            q.extend([
                ClassBlob(
                    member.class_name,
                    cut_class(source, member.class_name),
                    origin=origin,
                )
            ])
        else:
            raise ValueError(f"unknown prepare {member.prepare!r} on {member.class_name}")
    return q


def _rows(through_tier: int | None) -> list[Member]:
    rows = [m for m in MEMBERS if through_tier is None or m.tier <= through_tier]
    rows.sort(key=lambda m: (m.tier, m.order))
    return rows


def emit_prefix(
    *,
    through_tier: int | None = None,
    queue: PrefixQueue | None = None,
) -> str:
    q = queue if queue is not None else fill_queue()
    present = q.by_name()
    parts: list[str] = [""]
    current = None
    for member in _rows(through_tier):
        blob = present.get(member.class_name)
        if blob is None:
            raise UnmappedClass(f"queue missing {member.class_name}")
        if member.tier != current:
            current = member.tier
            if current != 0:
                parts.append("")
            parts.append(f"# === Tier {current} (imports) ===")
            parts.append("")
        parts.append(_banner(member))
        parts.append(blob.text.rstrip())
        parts.append("")
    return "\n".join(parts)


def describe_plan(queue: PrefixQueue | None = None) -> str:
    present = queue.by_name() if queue is not None else {}
    lines = []
    for member in _rows(None):
        blob = present.get(member.class_name)
        size = f"{len(blob.text):6d}" if blob else "     —"
        lines.append(
            f"T{member.tier}.{member.order:02d}  {member.prefix_name:<28}  "
            f"{member.class_name:<22}  {size}  {member.prepare}"
        )
    return "\n".join(lines)


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


# ---------------------------------------------------------------------------
# Named builders — wrappers only
# ---------------------------------------------------------------------------

def build_prefix0() -> str:
    return emit_prefix(through_tier=0)


def build_prefix1() -> str:
    return emit_prefix(through_tier=1)


def build_prefix2() -> str:
    return emit_prefix(through_tier=2)


def build_prefix3() -> str:
    return emit_prefix(through_tier=3)


def build_prefix4() -> str:
    return emit_prefix(through_tier=4)


def build_prefixA() -> str:
    return transpile_to_tier_d(emit_prefix())


def write_prefix_to_vfs(
    tier: str = "A",
    virtual_path: str | None = None,
) -> int:
    builders = {
        "0": build_prefix0,
        "1": build_prefix1,
        "2": build_prefix2,
        "3": build_prefix3,
        "4": build_prefix4,
        "A": build_prefixA,
    }
    if tier not in builders:
        raise ValueError(f"Unknown tier {tier!r}")

    default_paths = {
        "0": "Database/prefix_tier0.py",
        "1": "Database/prefix_tier1.py",
        "2": "Database/prefix_tier2.py",
        "3": "Database/prefix_tier3.py",
        "4": "Database/prefix_tier4.py",
        "A": "Database/prefix.py",
    }
    path = virtual_path or default_paths[tier]
    return write_file(path, builders[tier](), access_tier="agent_user")


def write_all_prefixes() -> dict[str, int]:
    ids = {}
    for tier in ("0", "1", "2", "3", "4", "A"):
        ids[tier] = write_prefix_to_vfs(tier=tier)
    ids["prefixA"] = write_prefix_to_vfs(
        tier="A",
        virtual_path="Database/prefix_tierA.py",
    )
    return ids


if __name__ == "__main__":
    if "--plan" in sys.argv:
        q = fill_queue()
        print(describe_plan(q))
    elif "--queue" in sys.argv:
        q = fill_queue()
        print(describe_queue(q))
    elif "--raw" in sys.argv:
        print(emit_prefix())
    elif "--write" in sys.argv:
        prefix = build_prefixA()
        ids = write_all_prefixes()
        print(f"Wrote prefix → Database/prefix.py  (node id {ids})")
        print(f"Length: {len(prefix)} characters")
    else:
        prefix = build_prefixA()
        print(prefix)
        print("\n# (re-run with --write to store it in the VirtualFS)", file=sys.stderr)
