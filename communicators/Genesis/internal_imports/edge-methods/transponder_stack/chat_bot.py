#!/usr/bin/env python3
"""Chatbot terminal — PositiveCom.

    python chat_bot.py
    python chat_bot.py --interval 10
"""

from __future__ import annotations

import argparse
import threading
import time

from boot_wire import boot, default_ref
from transponder_module import PositiveCom


class ChatBot(PositiveCom):
    def __init__(self, config=None):
        super().__init__(config)
        self.positive = self
        self.interval = 10.0

    def from_P(self, payload):
        if payload.get("kind") == "prompt":
            print(f"[bot] prompt: {payload.get('text')!r}", flush=True)
            token = payload.get("communicator_token")
            threading.Thread(target=self._reply_triple, args=(token,), daemon=True).start()
        super().from_P(payload)

    def _reply_triple(self, token):
        beats = [
            ("impatient", "Working on it — here is the answer while I finish the rest."),
            ("title", "Title: Packet-Strait Weather for Transponders"),
            ("summary", "Summary: One prompt, three beats: answer, title, then a short wrap-up."),
        ]
        for i, (part, text) in enumerate(beats):
            if i:
                time.sleep(self.interval)
            print(f"[bot] to_P {part}: {text}", flush=True)
            self.to_P({
                "communicator_token": token,
                "kind": "bot_reply",
                "part": part,
                "text": text,
            })


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--interval", type=float, default=10.0)
    p.add_argument("--favored", default="tcp")
    args = p.parse_args()

    bot = ChatBot({"positive_address": {"port": 0}})
    bot.interval = args.interval
    wire = boot(bot, "BOT", default_ref(), favored=args.favored)
    print(f"[bot] ready on {wire.scheme} {wire.slot.addr_s()}", flush=True)
    print("[bot] waiting for a prompt…", flush=True)
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print(flush=True)
    finally:
        wire.close()


if __name__ == "__main__":
    raise SystemExit(main())
