"""Tiny helper used by both demo programs."""

from __future__ import annotations

from wire import Wire


def default_ref():
    return {
        "inet": "127.0.0.1:19401",
        "path": "/tmp/transponder_chat.sock",
        "mine": "aaaabbbbccccdddd",
        "peer": "eeeeffff00001111",
    }


def boot(face, name: str, ref=None, favored: str = "tcp"):
    ref = dict(default_ref() if ref is None else ref)
    if name == "CLIENT":
        # shm tokens are directional; client uses the swapped pair
        ref["mine"], ref["peer"] = ref["peer"], ref["mine"]
    wire = Wire(favored=favored, scope="loopback")
    wire.attach(
        name=name,
        ref=ref,
        on_message=lambda msg: face.receiver(wire, msg),
        timeout=20.0,
    )
    face.attach_wire(wire)
    return wire
