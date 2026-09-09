#!/usr/bin/env python3
"""Shared JSON object codec for every connection slot.

This is the first Tier-1 piece of the wire spine: a dict in, a dict out.
Framing that is unique to a medium (NDJSON newline, HTTP body, WebSocket
text frame, shm lane object, UDP datagram) stays in that slot class.

Prefix shape (markers later):

    class Codec:
        @externalmethod
        def encode_msg(...)
        @externalmethod
        def decode_msg(...)
"""


class Transponder_Codec:
    """Canonical JSON-object codec. Methods are static so T1 slots and a
    later T2 Wire can both call Codec.encode_msg without holding state.
    """
    Raw = Union[None, str, bytes, bytearray, dict]

    @staticmethod
    def encode_msg(payload: dict) -> str:
        """Dict -> JSON object text. No trailing newline, no UTF-8 wrap."""
        if not isinstance(payload, dict):
            raise TypeError(f"payload must be dict, got {type(payload)!r}")
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def encode_bytes(payload: dict, newline: bool = False) -> bytes:
        """Dict -> UTF-8 JSON bytes. newline=True is NDJSON framing for
        stream slots; the extra byte is *frame*, not codec.
        """
        data = Codec.encode_msg(payload).encode("utf-8")
        if newline:
            data += b"\n"
        return data

    @staticmethod
    def decode_msg(raw: Raw) -> dict:
        """JSON object text/bytes/dict -> dict. Empty input -> {}."""
        if raw is None or raw == b"" or raw == "":
            return {}
        if isinstance(raw, dict):
            obj: Any = raw
        else:
            if isinstance(raw, (bytes, bytearray)):
                text = raw.decode("utf-8")
            else:
                text = str(raw)
            text = text.strip()
            if not text:
                return {}
            obj = json.loads(text)
        if not isinstance(obj, dict):
            raise ValueError(f"JSON root must be an object, got {type(obj).__name__}")
        return obj

    @staticmethod
    def canonicalize(payload: dict) -> dict:
        """Round-trip through JSON so shm-style bins store the same shape
        the wire would have sent.
        """
        return Codec.decode_msg(Codec.encode_msg(payload))


# Qualified use (Codec.encode_msg) is the prefix convention.
# These aliases keep current slot call sites short during the increment.
encode_msg = Codec.encode_msg
decode_msg = Codec.decode_msg
encode_bytes = Codec.encode_bytes
canonicalize = Codec.canonicalize
