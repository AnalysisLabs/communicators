"""Stand-in Genesis names so transponder_module can run outside the prefix.

WSTamer and UnixSocketClientSync are obsolete. Wire owns the session.
"""

from __future__ import annotations

import json
import uuid


def truncate(n, obj):
    text = obj if isinstance(obj, str) else json.dumps(obj, default=str)
    return text if len(text) <= n else text[:n] + "…"


class _Manifest:
    def info(self, *args, **kwargs):
        print("[manifest]", *args, flush=True)

    def warning(self, *args, **kwargs):
        print("[manifest:warn]", *args, flush=True)


manifest = _Manifest()


class _Freight:
    def upgrades(self, payload=None, message=None):
        raw = payload if payload is not None else message
        if raw is None:
            raw = {}
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode("utf-8")
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                raw = {"text": raw}
        if not isinstance(raw, dict):
            raw = {"value": raw}
        out = dict(raw)
        if "communicator_token" not in out:
            out["communicator_token"] = str(uuid.uuid4())
        return out

    def dumps(self, payload):
        if not isinstance(payload, dict):
            payload = {"value": payload}
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    def get(self, freight_obj=None, key=None):
        if isinstance(freight_obj, dict):
            return freight_obj.get(key)
        return None


freight = _Freight()


def singleton(cls):
    return cls


def aux_multiton(cls):
    return cls


def unix_client(cls):
    return cls


def unix_server(cls):
    return cls


def generate_unique_socket_path():
    return f"/tmp/comm_shim_{uuid.uuid4().hex}.sock"
