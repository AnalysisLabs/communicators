#!/usr/bin/env python3
"""Client terminal — NegativeCom.

    python chat_client.py
    python chat_client.py --prompt "What is the weather on the packet strait?"
"""

from __future__ import annotations

import argparse
import time

from boot_wire import boot, default_ref
from transponder_module import NegativeCom


class ChatClient(NegativeCom):
    def __init__(self, config=None):
        super().__init__(config)
        self.negative = self
        self.replies = []

    def from_N(self, payload):
        if payload.get("kind") == "bot_reply":
            part = payload.get("part", "?")
            text = payload.get("text", "")
            print(f"[client] {part}: {text}", flush=True)
            self.replies.append(payload)
        super().from_N(payload)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--prompt", default="What is the weather on the packet strait?")
    p.add_argument("--favored", default="tcp")
    p.add_argument("--wait", type=float, default=40.0, help="seconds to stay up listening after the prompt")
    args = p.parse_args()

    client = ChatClient({})
    time.sleep(0.4)
    wire = boot(client, "CLIENT", default_ref(), favored=args.favored)
    print(f"[client] ready on {wire.scheme} {wire.slot.addr_s()}", flush=True)
    print(f"[client] to_N prompt: {args.prompt!r}", flush=True)
    client.to_N({"kind": "prompt", "text": args.prompt})
    print("[client] listening for three replies…", flush=True)
    deadline = time.time() + args.wait
    try:
        while time.time() < deadline and len(client.replies) < 3:
            time.sleep(0.2)
    except KeyboardInterrupt:
        print(flush=True)
    finally:
        print(f"[client] got {len(client.replies)} replies", flush=True)
        wire.close()
    return 0 if len(client.replies) >= 3 else 1


if __name__ == "__main__":
    raise SystemExit(main())
