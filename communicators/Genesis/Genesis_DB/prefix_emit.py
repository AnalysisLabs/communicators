"""Emit queued class blobs into prefix text by class-name tier map.

Companion to prefix_queue.py. File names do not matter. The law is
CLASS_TIER: class identifier -> (tier, order, prefix_name).

Banner convention copied from build_prefix1's Manifest block:

    # === Tier N (imports) ===

    # === Manifest (class) ===
    <class body rstrip>
    <blank line>

This script does not touch T0 (standard.py + COMMUNICATORS_ROOT) and
does not load the VFS-rectified PathReffs / AtomicImporter copies.
Those stay in the existing builders until integration.

Does not rectify. Does not run Stage B. Does not write VirtualFS.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from prefix_queue import ClassBlob, PrefixQueue


@dataclass(frozen=True)
class ClassTier:
    """One row of the handoff membership table, keyed by class identifier."""

    tier: int
    order: int
    prefix_name: str
    class_name: str


# Handoff §4, stack rows only. Order inside a tier is concat order.
# Same-tier rows must not call each other; order is not a dependency edge.
CLASS_TIER: dict[str, ClassTier] = {
    # T1 helpers
    "Transponder_Codec":    ClassTier(1, 10, "transponder_codec",         "Transponder_Codec"),
    "Transponder_Locators": ClassTier(1, 11, "transponder_locators",      "Transponder_Locators"),
    "SlotRefused":          ClassTier(1, 12, "transponder_slot_refused",  "SlotRefused"),
    "DirWatch":             ClassTier(1, 13, "transponder_dir_watch",     "DirWatch"),
    "UdpMail":              ClassTier(1, 14, "transponder_udp_mail",      "UdpMail"),
    "Mailbox":              ClassTier(1, 15, "transponder_mailbox_bin",   "Mailbox"),
    # T2 slots
    "TcpSlot":              ClassTier(2,  0, "transponder_tcp",             "TcpSlot"),
    "UnixSlot":             ClassTier(2,  1, "transponder_unix",            "UnixSlot"),
    "WsSlot":               ClassTier(2,  2, "transponder_ws",              "WsSlot"),
    "ShmSlot":              ClassTier(2,  3, "transponder_shm",             "ShmSlot"),
    "HttpSlot":             ClassTier(2,  4, "transponder_http",            "HttpSlot"),
    "MailboxServer":        ClassTier(2,  5, "transponder_mailbox_server",  "MailboxServer"),
    "MailboxClient":        ClassTier(2,  6, "transponder_mailbox_client",  "MailboxClient"),
    "Station":              ClassTier(2,  7, "transponder_station",         "Station"),
    "Tuner":                ClassTier(2,  8, "transponder_tuner",           "Tuner"),
    # T3 wire
    "Wire":                 ClassTier(3,  0, "transponder_wire",     "Wire"),
    # T4 faces
    "NegativeCom":          ClassTier(4,  0, "transponder_negative", "NegativeCom"),
    "PositiveCom":          ClassTier(4,  1, "transponder_positive", "PositiveCom"),
}


class UnmappedClass(KeyError):
    """Queue contained a class that is not in CLASS_TIER."""


class MissingClass(KeyError):
    """CLASS_TIER required a class that was not in the queue."""


def tier_of(class_name: str) -> ClassTier:
    try:
        return CLASS_TIER[class_name]
    except KeyError as exc:
        raise UnmappedClass(
            f"{class_name!r} is not in CLASS_TIER; "
            f"do not emit an unmapped class"
        ) from exc


def format_class_block(blob: ClassBlob) -> str:
    """One Manifest-shaped block. prefix_name is recorded in CLASS_TIER,
    not in the banner — tomorrow's emit can switch the label if wanted.
    """
    return "\n".join(
        [
            f"# === {blob.class_name} (class) ===",
            blob.text.rstrip(),
            "",
        ]
    )


def format_tier_banner(tier: int) -> str:
    return f"# === Tier {tier} (imports) ==="


def sort_blobs(blobs: Iterable[ClassBlob]) -> list[ClassBlob]:
    """Re-order queue contents by (tier, order). File order is discarded."""
    return sorted(
        blobs,
        key=lambda b: (tier_of(b.class_name).tier, tier_of(b.class_name).order),
    )


def group_by_tier(
    blobs: Iterable[ClassBlob],
    *,
    through_tier: int | None = None,
) -> dict[int, list[ClassBlob]]:
    grouped: dict[int, list[ClassBlob]] = {}
    for blob in sort_blobs(blobs):
        spec = tier_of(blob.class_name)
        if through_tier is not None and spec.tier > through_tier:
            continue
        grouped.setdefault(spec.tier, []).append(blob)
    return grouped


def require_mapped(blobs: Iterable[ClassBlob], *, through_tier: int | None = None) -> None:
    """Fail if the queue is missing a CLASS_TIER row at or below through_tier."""
    present = {b.class_name for b in blobs}
    missing = []
    for spec in CLASS_TIER.values():
        if through_tier is not None and spec.tier > through_tier:
            continue
        if spec.class_name not in present:
            missing.append(spec.class_name)
    if missing:
        raise MissingClass(f"queue missing mapped classes: {missing}")


def emit_tier_blocks(
    blobs: Iterable[ClassBlob],
    *,
    through_tier: int | None = None,
    require_all: bool = True,
) -> str:
    """Stack classes only, Manifest banners, tiers in order.

    Returns the T1..N fragment. Caller prepends build_prefix0() /
    PathReffs / AtomicImporter / Manifest at integration time.
    """
    blobs = list(blobs)
    if require_all:
        require_mapped(blobs, through_tier=through_tier)
    grouped = group_by_tier(blobs, through_tier=through_tier)

    parts: list[str] = []
    for tier in sorted(grouped):
        if parts:
            parts.append("")
        parts.append(format_tier_banner(tier))
        parts.append("")
        for blob in grouped[tier]:
            parts.append(format_class_block(blob))
    return "\n".join(parts).rstrip() + "\n"


def emit_from_queue(
    queue: PrefixQueue | Mapping[str, ClassBlob] | Iterable[ClassBlob],
    *,
    through_tier: int | None = None,
    require_all: bool = True,
) -> str:
    if isinstance(queue, PrefixQueue):
        blobs = list(queue.blobs)
    elif isinstance(queue, Mapping):
        blobs = list(queue.values())
    else:
        blobs = list(queue)
    return emit_tier_blocks(blobs, through_tier=through_tier, require_all=require_all)


def describe_plan(queue: Iterable[ClassBlob] | PrefixQueue) -> str:
    """Human check: class -> T{tier}.{order} prefix_name. No source paths."""
    blobs = list(queue.blobs) if isinstance(queue, PrefixQueue) else list(queue)
    lines = []
    for blob in sort_blobs(blobs):
        spec = tier_of(blob.class_name)
        lines.append(
            f"T{spec.tier}.{spec.order:02d}  {spec.prefix_name:<28}  "
            f"{spec.class_name:<22}  {len(blob.text):6d} chars"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    from pathlib import Path

    from prefix_queue import cut_all_classes, PrefixQueue

    # Offline demo: cut from a directory of stack files if given,
    # otherwise print the map alone.
    q = PrefixQueue()
    if len(sys.argv) > 1 and Path(sys.argv[1]).is_dir():
        for path in sorted(Path(sys.argv[1]).glob("*.py")):
            if path.name.startswith("wire_prototype"):
                continue
            q.extend(cut_all_classes(path.read_text(encoding="utf-8")))
        print(describe_plan(q), file=sys.stderr)
        print(emit_from_queue(q), end="")
    else:
        for spec in sorted(CLASS_TIER.values(), key=lambda s: (s.tier, s.order)):
            print(f"T{spec.tier}.{spec.order:02d}  {spec.prefix_name:<28}  {spec.class_name}")
        print(
            "\n# usage: python prefix_emit.py /path/to/transponder_stack > stack_fragment.py",
            file=sys.stderr,
        )
