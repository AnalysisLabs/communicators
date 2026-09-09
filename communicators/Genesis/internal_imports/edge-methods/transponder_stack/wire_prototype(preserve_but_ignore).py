#!/usr/bin/env python3
"""Prototype Wire: tables + dispatch + fallback. Not prefix-ready.

This is the first object that is allowed to know more than one slot.
It uses Codec for payloads. It constructs a slot class and calls a verb.
OS-level attach/send failure walks FALLBACK[scope]. SlotRefused does not.

Slots remain importable for raw development tests.
"""

from __future__ import annotations

from codec import Codec


class SlotRefused(RuntimeError):
    def __init__(self, slot: str, verb: str, flag: str, detail: str = ""):
        self.slot = slot
        self.verb = verb
        self.flag = flag  # "no" | "later"
        extra = f" ({detail})" if detail else ""
        super().__init__(f"{slot} refuses {verb}: {flag}{extra}")


# Static capability / feature rows harvested from the prototypes.
FEATURES = {
    "http": {
        "persistence": "oneshot",
        "scope": ("loopback", "lan", "wan"),
        "locators": ("inet",),
        "verbs": {
            "attach": "yes", "send": "yes", "recv": "yes",
            "request_response": "yes", "close": "yes",
            "fanout": "no",
        },
    },
    "tcp": {
        "persistence": "session",
        "scope": ("loopback", "lan", "wan"),
        "locators": ("inet",),
        "verbs": {
            "attach": "yes", "send": "yes", "recv": "yes",
            "request_response": "yes", "close": "yes",
            "fanout": "no",
        },
    },
    "unix": {
        "persistence": "session",
        "scope": ("loopback",),
        "locators": ("path",),
        "verbs": {
            "attach": "yes", "send": "yes", "recv": "yes",
            "request_response": "yes", "close": "yes",
            "fanout": "no",
        },
    },
    "ws": {
        "persistence": "session",
        "scope": ("loopback", "lan", "wan"),
        "locators": ("inet",),
        "verbs": {
            "attach": "yes", "send": "yes", "recv": "yes",
            "request_response": "yes", "close": "yes",
            "fanout": "no",
        },
    },
    "shm": {
        "persistence": "session",
        "scope": ("loopback",),
        "locators": ("token",),
        "verbs": {
            "attach": "yes", "send": "yes", "recv": "yes",
            "request_response": "yes", "close": "yes",
            "fanout": "no",
        },
    },
    "station": {
        "persistence": "fanout",
        "scope": ("loopback", "lan", "wan"),
        "locators": ("inet",),
        "verbs": {
            "attach": "yes", "send": "yes", "recv": "no",
            "request_response": "no", "close": "yes",
            "fanout": "yes",
        },
    },
    "tuner": {
        "persistence": "fanout",
        "scope": ("loopback", "lan", "wan"),
        "locators": ("inet",),
        "verbs": {
            "attach": "yes", "send": "no", "recv": "yes",
            "request_response": "no", "close": "yes",
            "fanout": "no",
        },
    },
    "http_mailbox": {
        "persistence": "mailbox",
        "scope": ("loopback", "lan", "wan"),
        "locators": ("inet",),
        "verbs": {
            "attach": "yes", "send": "yes", "recv": "yes",
            "request_response": "no", "close": "yes",
            "fanout": "later",
        },
    },
}


# Directed, scoped. OS failure only — not SlotRefused.
FALLBACK = {
    "loopback": {
        "tcp": "unix",
        "unix": "shm",
        "ws": "tcp",
        "http": "tcp",
        "http_mailbox": "http",
    },
    "lan": {
        "tcp": "ws",
        "ws": "http",
        "http": "http_mailbox",
    },
    "wan": {
        "tcp": "ws",
        "ws": "http",
        "http": "http_mailbox",
    },
}


class Wire:
    """T2 prototype. Faces (T3) are not here yet."""

    encode_msg = staticmethod(Codec.encode_msg)
    decode_msg = staticmethod(Codec.decode_msg)

    def __init__(self, favored: str | None = None, scope: str = "loopback"):
        self.favored = favored
        self.scope = scope

    def require(self, slot: str, verb: str) -> None:
        row = FEATURES.get(slot)
        if row is None:
            raise SlotRefused(slot, verb, "no", "unknown slot")
        flag = row["verbs"].get(verb, "no")
        if flag != "yes":
            raise SlotRefused(slot, verb, flag)

    def next_fallback(self, slot: str) -> str | None:
        return FALLBACK.get(self.scope, {}).get(slot)

    def candidates(self) -> list[str]:
        start = self.favored
        if start is None:
            start = {"loopback": "tcp", "lan": "tcp", "wan": "ws"}[self.scope]
        out = [start]
        seen = {start}
        cur = start
        while True:
            nxt = self.next_fallback(cur)
            if nxt is None or nxt in seen:
                break
            out.append(nxt)
            seen.add(nxt)
            cur = nxt
        return out


if __name__ == "__main__":
    w = Wire(favored="tcp", scope="loopback")
    print("candidates", w.candidates())
    print("encoded", Wire.encode_msg({"from": "WIRE", "kind": "probe", "seq": 1}))
    try:
        w.require("tuner", "send")
    except SlotRefused as e:
        print("refused as designed:", e)
