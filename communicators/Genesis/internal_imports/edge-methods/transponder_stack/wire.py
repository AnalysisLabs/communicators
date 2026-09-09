#!/usr/bin/env python3
"""T2 Wire: attach a duplex slot, send dicts, deliver inbound to a callback.

Favored medium is tcp. Fallback row for this standalone run:
    tcp -> unix -> shm
WebSocket is a first-class slot and can be selected explicitly; it is not
on the default fallback row.
"""

from codec import Codec
from locators import Locators
from shm_slot import ShmSlot
from tcp_socket_slot import TcpSlot
from unix_socket_slot import UnixSlot
from websocket_slot import WsSlot


class SlotRefused(RuntimeError):
    @externalmethod
    def __init__(self, slot: str, verb: str, flag: str, detail: str = ""):
        self.slot = slot
        self.verb = verb
        self.flag = flag
        extra = f" ({detail})" if detail else ""
        super().__init__(f"{slot} refuses {verb}: {flag}{extra}")



class Wire:
    encode_msg = staticmethod(Codec.encode_msg)
    decode_msg = staticmethod(Codec.decode_msg)

    FEATURES = {
        "tcp": {"verbs": {"attach": "yes", "send": "yes", "recv": "yes"}},
        "unix": {"verbs": {"attach": "yes", "send": "yes", "recv": "yes"}},
        "ws": {"verbs": {"attach": "yes", "send": "yes", "recv": "yes"}},
        "shm": {"verbs": {"attach": "yes", "send": "yes", "recv": "yes"}},
    }

    FALLBACK = {
        "loopback": {"tcp": "unix", "unix": "shm"},
    }

    @internalmethod
    def __init__(self, favored: str = "tcp", scope: str = "loopback"):
        self.favored = favored
        self.scope = scope
        self.slot = None
        self.scheme = None
        self.on_message = None
        self.name = None

    @dualmethod
    def require(self, slot: str, verb: str) -> None:
        row = FEATURES.get(slot)
        if row is None:
            raise SlotRefused(slot, verb, "no", "unknown slot")
        flag = row["verbs"].get(verb, "no")
        if flag != "yes":
            raise SlotRefused(slot, verb, flag)

    @dualmethod
    def candidates(self) -> list[str]:
        start = self.favored or "tcp"
        out = [start]
        seen = {start}
        cur = start
        while True:
            nxt = FALLBACK.get(self.scope, {}).get(cur)
            if nxt is None or nxt in seen:
                break
            out.append(nxt)
            seen.add(nxt)
            cur = nxt
        return out

    @internalmethod
    def _make_slot(self, scheme: str, name: str, ref: dict):
        if scheme == "tcp":
            host, port = Locators.parse_hostport(ref["inet"])
            return TcpSlot(name, (host, port))
        if scheme == "ws":
            host, port = Locators.parse_hostport(ref["inet"])
            return WsSlot(name, (host, port))
        if scheme == "unix":
            path = Locators.parse_sockpath(ref.get("path") or ref["inet"])
            return UnixSlot(name, path)
        if scheme == "shm":
            mine = Locators.parse_token(ref["mine"])
            peer = Locators.parse_token(ref["peer"])
            return ShmSlot(name, mine, peer)
        raise SlotRefused(scheme, "attach", "no", "no constructor")

    @internalmethod
    def _hook(self, incoming: dict) -> None:
        cb = self.on_message
        if cb is None:
            return
        cb(incoming)

    @externalmethod
    def attach(self, *, name: str, ref: dict, on_message, timeout: float = 12.0, schemes=None):
        self.name = name
        self.on_message = on_message
        errors = []
        wanted = list(schemes) if schemes is not None else self.candidates()
        for scheme in wanted:
            self.require(scheme, "attach")
            slot = None
            try:
                slot = self._make_slot(scheme, name, ref)
                slot.on_payload = self._hook
                slot.attach(timeout)
                self.slot = slot
                self.scheme = scheme
                print(f"[Wire {name}] attached scheme={scheme} {slot.addr_s()}", flush=True)
                return scheme
            except Exception as e:
                errors.append(f"{scheme}: {type(e).__name__}: {e}")
                print(f"[Wire {name}] attach fail {scheme}: {e}", flush=True)
                if slot is not None:
                    try:
                        slot.close()
                    except Exception:
                        pass
        raise RuntimeError(f"Wire.attach exhausted {wanted}: {errors}")

    @externalmethod
    def send(self, payload: dict) -> None:
        if self.slot is None:
            raise RuntimeError("Wire.send before attach")
        self.require(self.scheme, "send")
        if not hasattr(self.slot, "_write"):
            raise SlotRefused(self.scheme, "send", "no", "slot has no _write")
        self.slot._write(payload)

    @externalmethod
    def close(self) -> None:
        if self.slot is not None:
            try:
                self.slot.close()
            except Exception:
                pass
            self.slot = None
