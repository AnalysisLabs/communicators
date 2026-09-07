#!/usr/bin/env python3
"""L2 stub — overlap harvested from the six working slots.

This file is not a working transponder. It is a map of what can rise into
transponder_wire.py versus what must stay in a slot. The live slot programs
remain the source of truth until this spine is filled in against them.

Usage we are steering toward (not implemented here):

  python transponder_wire.py --slot tcp    --name FOX   --listen 127.0.0.1:9101 --peer 127.0.0.1:9101
  python transponder_wire.py --slot http   --name FOX   --listen 127.0.0.1:9101 --peer 127.0.0.1:9102
  python transponder_wire.py --slot shm    --name FOX   --listen <tokA>         --peer <tokB>
  python transponder_wire.py --slot station --name WXYZ --listen 127.0.0.1:9101
  python transponder_wire.py --slot tuner  --name FOX   --listen 127.0.0.1:9102 --peer 127.0.0.1:9101

L2 never branches on medium inside send / request_response / close.
The only scheme-conditional tree is resolve() + CAPABILITY.require().
"""

from __future__ import annotations

from typing import Any, Callable


# ===========================================================================
# EASY — identical in every slot we actually ran
# ===========================================================================
#
# 1. The payload is a JSON *object*. Slots already agree on the fields:
#      chat:  {from, seq, kind, text, ts}
#      reply: {ok, kind:"reply", heard_by, from, seq, text}
#      tune:  {kind:"tune", name, recv, ts}          # station/tuner only
#      pulse: {from, kind:"pulse", seq, text, ts}    # station/tuner only
#
# 2. encode_msg / decode_msg as *object codec* (dict <-> JSON text).
#    Framing onto a particular medium is NOT shared. See HARD.
#
# 3. next_seq + the SEND / RECV / REPLY log shape.
#
# 4. close() as a verb. Every slot has one.
#
# 5. A capability row. The old CAPABILITY table was a guess; the rows
#    below are what the prototypes actually implemented.


def encode_msg(payload: dict) -> str:
    """Object codec only. Slots wrap this in a frame."""
    raise NotImplementedError("centralize json.dumps of a dict")


def decode_msg(raw: Any) -> dict:
    """Object codec only. Slots unwrap a frame, then call this."""
    raise NotImplementedError("centralize json.loads to a dict")


def chat_envelope(name: str, seq: int, text: str) -> dict:
    raise NotImplementedError


def reply_envelope(name: str, incoming: dict) -> dict:
    raise NotImplementedError


# ===========================================================================
# MEDIUM — same verb names, different locators
# ===========================================================================
#
# The old parse_addr() assumed scheme://host:port/path. That already
# fails for the slots we have:
#   http     two inet addrs (listen != peer)
#   tcp, ws  one inet addr  (listen == peer)
#   unix     one filesystem path
#   shm      two hex tokens; bin path is derived from the sorted pair
#   station  one inet UDP mailbox
#   tuner    two inet UDP addrs (local recv, station mailbox)
#
# A WireRef is the shared address object. The *fields that are filled*
# depend on scheme. L2 stores it. Slots interpret it.


class WireRef(dict):
    """scheme + role + local + remote. Not always host/port.

    Examples the stub is willing to name, not parse yet:

      {scheme:http,  local:{host,port}, remote:{host,port}}
      {scheme:tcp,   local:{host,port}, remote: SAME}
      {scheme:unix,  local:{path},      remote: SAME}
      {scheme:shm,   local:{token},     remote:{token}}
      {scheme:station, local:{host,port}}
      {scheme:tuner, local:{host,port}, remote:{host,port}}  # remote = station
    """


def parse_ref(scheme: str, listen: str, peer: str | None) -> WireRef:
    raise NotImplementedError("scheme-aware locator, not host:port only")


def format_ref(ref: WireRef) -> str:
    raise NotImplementedError


# Lifecycle verbs that five slots share (http/tcp/unix/ws/shm):
#
#   attach(ref)             start being present on `local`, reach `remote`
#   wait_for_peer(ref)
#   send(ref, payload)      no wait
#   request_response(ref, payload)
#   close(ref)
#
# Station/tuner drop request_response. Station.send is emit-to-registry.
# Tuner.attach is bind + tune datagram. Those still *fit the names*
# attach / send / close if CAPABILITY is allowed to say "no" to the rest.


# ===========================================================================
# HARD — unique on purpose. L2 must call these, not implement them.
# ===========================================================================
#
# attach policy
#   http     always serve AND always client (two ports)
#   tcp/ws/unix  bind-or-connect race on one name
#   shm      create-or-join the json bin, wait for present[peer]
#   station  bind join mailbox, never dial
#   tuner    bind recv port, send kind=tune, never expect ACK
#
# framing
#   http     HTTP body + Content-Length
#   tcp/unix NDJSON (newline)
#   ws       one websocket text frame
#   shm      lane array inside one file, fcntl + rename
#   udp      one datagram = one object
#
# how a reply comes back
#   http     the POST response (same request)
#   tcp/unix/ws/shm  a later kind=reply matched by seq
#   station/tuner    does not exist
#
# threads / wait
#   each slot already starts its own thread. L2 should not own an event loop.


class Slot:
    """What every slot module must expose. Unique code lives behind these."""

    scheme: str
    cap: dict

    def attach(self, ref: WireRef) -> None:
        raise NotImplementedError

    def send(self, payload: dict) -> None:
        raise NotImplementedError

    def request_response(self, payload: dict, timeout: float = 5.0) -> dict:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError


# ===========================================================================
# Table A — harvested from the prototypes, not from the old guess
# ===========================================================================

YES, NO, N_A = "yes", "no", "n/a"

CAPABILITY = {
    "http": {
        "attach": YES, "send": YES, "recv": YES, "close": YES,
        "request_response": YES, "serve": YES, "fanout": NO,
    },
    "tcp": {
        "attach": YES, "send": YES, "recv": YES, "close": YES,
        "request_response": YES, "serve": YES, "fanout": NO,
    },
    "unix": {
        "attach": YES, "send": YES, "recv": YES, "close": YES,
        "request_response": YES, "serve": YES, "fanout": NO,
    },
    "ws": {
        "attach": YES, "send": YES, "recv": YES, "close": YES,
        "request_response": YES, "serve": YES, "fanout": NO,
    },
    "shm": {
        "attach": YES, "send": YES, "recv": YES, "close": YES,
        "request_response": YES, "serve": N_A, "fanout": NO,
    },
    "station": {
        "attach": YES, "send": YES, "recv": NO, "close": YES,
        "request_response": NO, "serve": N_A, "fanout": YES,
    },
    "tuner": {
        "attach": YES, "send": NO, "recv": YES, "close": YES,
        "request_response": NO, "serve": N_A, "fanout": NO,
    },
}

# Two roles of the old "beacon" are two slot names. That is cleaner than
# one slot with a hidden --role branch inside L2.


SLOTS: dict[str, Callable[[], Slot]] = {
    # "http":    lambda: HttpSlot(),
    # "tcp":     lambda: TcpSlot(),
    # "unix":    lambda: UnixSlot(),
    # "ws":      lambda: WsSlot(),
    # "shm":     lambda: ShmSlot(),
    # "station": lambda: Station(),
    # "tuner":   lambda: Tuner(),
}


def require(scheme: str, verb: str) -> None:
    flag = CAPABILITY.get(scheme, {}).get(verb, NO)
    if flag != YES:
        raise RuntimeError(f"{scheme}.{verb} is {flag}")


def resolve(scheme: str) -> Slot:
    if scheme not in SLOTS:
        raise RuntimeError(f"slot {scheme!r} is not registered; have {sorted(SLOTS)}")
    return SLOTS[scheme]()


# ===========================================================================
# L2 verbs — one line of dispatch each. No if-http / if-shm here.
# ===========================================================================

_sessions: dict[str, Slot] = {}


def attach(scheme: str, listen: str, peer: str | None = None) -> WireRef:
    ref = parse_ref(scheme, listen, peer)
    require(scheme, "attach")
    slot = resolve(scheme)
    slot.attach(ref)
    _sessions[format_ref(ref)] = slot
    return ref


def send(ref: WireRef, payload: dict) -> None:
    require(ref["scheme"], "send")
    _sessions[format_ref(ref)].send(payload)


def request_response(ref: WireRef, payload: dict) -> dict:
    require(ref["scheme"], "request_response")
    return _sessions[format_ref(ref)].request_response(payload)


def close(ref: WireRef) -> None:
    require(ref["scheme"], "close")
    key = format_ref(ref)
    slot = _sessions.pop(key, None)
    if slot is not None:
        slot.close()


# ===========================================================================
# What the old transponder_wire.py got wrong, given the prototypes
# ===========================================================================
#
# - parse_addr / wire_id / legal_slots assume inet + path. They cannot
#   name a unix path, a pair of shm tokens, or a station mailbox.
# - CAPABILITY listed unix/ws/shm as "later". They are not later anymore.
# - CAPABILITY listed beacon as one column. We now have station AND tuner.
# - choose_scheme guessed a medium from the IP. The new plan is: the
#   caller passes --slot. Guessing can come back later as L3 policy.
# - HTTP and TCP implementations lived inside the L2 file. That is what
#   made L2 both the spine and the first two slots. The stub keeps slot
#   bodies out.
#
# Suggested file split when we actually rebuild:
#   transponder_wire.py     this spine (codec, WireRef, verbs, CAPABILITY)
#   Slots/<scheme>_slot.py  Slot subclass, unique attach/frame only
#   a thin __main__         parse --slot/--listen/--peer, call attach/send
#
# First real step that is still small: lift encode_msg/decode_msg and the
# WireRef parser, and make tcp + unix implement Slot against it. Those two
# are almost the same class already. HTTP and SHM second. Station/tuner last.
