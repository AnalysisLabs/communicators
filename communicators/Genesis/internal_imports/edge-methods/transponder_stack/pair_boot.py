"""Tiny attach helper shared by the two demo programs."""

from __future__ import annotations

from transponder_module import NegativeCom, PositiveCom
from wire import Wire

DEFAULT_REF = {
    "inet": "127.0.0.1:19401",
    "path": "/tmp/transponder_chat.sock",
    "mine": "c1a7b07e11112222",
    "peer": "c1a7b07e33334444",
}


def boot_positive(name="BOT"):
    face = PositiveCom({"positive_address": {"port": 0}})
    wire = Wire(favored="tcp", scope="loopback")
    wire.attach(
        name=name,
        ref=DEFAULT_REF,
        on_message=lambda msg: face.receiver(wire, msg),
        timeout=20.0,
    )
    face.attach_wire(wire)
    print(f"[{name}] live on {wire.scheme} {wire.slot.addr_s()}", flush=True)
    return face, wire


def boot_negative(name="CLIENT"):
    # shm tokens are swapped so each process owns its own inbox lane
    ref = dict(DEFAULT_REF)
    ref["mine"], ref["peer"] = ref["peer"], ref["mine"]
    face = NegativeCom({})
    wire = Wire(favored="tcp", scope="loopback")
    wire.attach(
        name=name,
        ref=ref,
        on_message=lambda msg: face.receiver(wire, msg),
        timeout=20.0,
    )
    face.attach_wire(wire)
    print(f"[{name}] live on {wire.scheme} {wire.slot.addr_s()}", flush=True)
    return face, wire
