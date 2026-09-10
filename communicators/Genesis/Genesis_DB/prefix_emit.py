"""Emit a prefix from the tier table.

No build_prefix0 / build_prefix1 / build_prefix2. Structure comes from
MEMBERS. Load goes through _load_source.

Does not emit the obsolete Stage-B `transponder` blob.
Does not rectify. Does not run Stage B. Does not write VirtualFS.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from prefix_queue import (
    QUEUE,
    ClassBlob,
    PrefixQueue,
    cut_class,
    whole_file_blob,
    _origin_of,
)


# ---------------------------------------------------------------------------
# Same bindings as prefix_builder. Delete this block when pasting in.
# ---------------------------------------------------------------------------

try:
    FileRef
except NameError:
    @dataclass(frozen=True)
    class FileRef:
        uuid: str
        file_path: str
        file_name: str


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

# Every source the prefix still needs. Not the old T2 transponder blob.
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


@dataclass(frozen=True)
class Member:
    tier: int
    order: int
    class_name: str
    prefix_name: str
    ref: object | None
    prepare: str = "cut_class"  # whole_file | cut_class | communicators_root
    banner: str | None = None


# The law. Emit expands from this tuple. No named build_prefixN.
#
# Member(tier, order, class_name, prefix_name, ref, prepare=..., banner=...)
#
#   tier         Prefix tier. A row may use names introduced in tiers 0..tier-1
#                only. Same-tier rows must not call each other. Emit prints
#                "# === Tier N (imports) ===" when this number changes.
#                  0  language/std + COMMUNICATORS_ROOT
#                  1  core objects that need only T0
#                     (PathReffs, AtomicImporter, Manifest, then T1 helpers)
#                  2  one-medium slots (need T1 codec/locators/helpers)
#                  3  Wire (first type that sees more than one slot)
#                  4  faces (NegativeCom / PositiveCom)
#
#   order        Concat order *inside* that tier. Not a dependency edge.
#                Gaps are deliberate so a later row can be inserted without
#                renumbering:
#                  T0  0, 1
#                  T1  0-2   existing scaffold (keep first)
#                      10-15 stack helpers (room 3-9 if scaffold grows)
#                  T2  0-8   slots
#                  T3  0
#                  T4  0-1
#
#   class_name   Identifier on the blob and in "# === Name (class) ===".
#                For whole_file rows this is the banner name (PathReffs,
#                Manifest), not necessarily the only class in the source.
#                COMMUNICATORS_ROOT is synthetic and has no class.
#
#   prefix_name  Hatch spelling of the prefix *module* row
#                (transponder_tcp, …). Not a second class identifier.
#                User-visible names after a later Tier A trim are still
#                the class_name values (NegativeCom, Wire, …).
#
#   ref          What _load_source fetches.
#                  FileRef  — registry disk (uuid is a real UUID)
#                  str      — VirtualFS path ("Database/path_reffs.py")
#                  None     — nothing to load (COMMUNICATORS_ROOT)
#                Several rows may share one ref; fill_queue loads it once
#                and cuts out the requested class_name.
#
#   prepare      How that text becomes a blob.
#                  whole_file          paste loaded source as one block
#                                      (standard, VFS PathReffs / AtomicImporter,
#                                      disk Manifest). Do not cut: the VFS
#                                      copies already contain _internal + public.
#                  cut_class           one top-level class from the source
#                  communicators_root  generated Path assignment, no load
#
#   banner       Optional override for the "# === … ===" line. Used when
#                the historical label is not "{class_name} (class)"
#                (standard.py (from VirtualFS), COMMUNICATORS_ROOT, …).
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
    if member.prepare == "whole_file":
        return f"# === {member.class_name} (class) ==="
    return f"# === {member.class_name} (class) ==="


def _root_block(root=None) -> str:
    r = root if root is not None else globals().get("root")
    if r is None:
        r = Path.cwd()
    return (
        "from pathlib import Path\n"
        f"COMMUNICATORS_ROOT = Path({str(r)!r})\n"
    )


def fill_queue(
    *,
    loader: Callable[[object], str] | None = None,
    queue: PrefixQueue | None = None,
    root=None,
) -> PrefixQueue:
    load = loader if loader is not None else globals().get("_load_source")
    if load is None:
        raise RuntimeError("_load_source is not defined")

    q = queue if queue is not None else QUEUE
    q.reset()
    cache: dict[object, str] = {}

    for member in MEMBERS:
        if member.prepare == "communicators_root":
            q.extend([ClassBlob(member.class_name, _root_block(root), origin="generated", whole_file=True)])
            continue
        ref = member.ref
        key = ref if isinstance(ref, str) else id(ref)
        if key not in cache:
            cache[key] = load(ref)
        source = cache[key]
        origin = _origin_of(ref)
        if member.prepare == "whole_file":
            q.extend([whole_file_blob(source, member.class_name, origin=origin)])
        elif member.prepare == "cut_class":
            q.extend([ClassBlob(member.class_name, cut_class(source, member.class_name), origin=origin)])
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
    loader: Callable[[object], str] | None = None,
    root=None,
) -> str:
    q = queue if queue is not None else fill_queue(loader=loader, root=root)
    present = q.by_name()
    parts: list[str] = []
    current = None
    for member in _rows(through_tier):
        blob = present.get(member.class_name)
        if blob is None:
            raise UnmappedClass(f"queue missing {member.class_name}")
        if member.tier != current:
            current = member.tier
            if parts:
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


if __name__ == "__main__":
    print(describe_plan())
    print("\n# fill_queue() / emit_prefix() need _load_source from prefix_builder")
