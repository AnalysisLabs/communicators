#!/usr/bin/env python3
"""Dev-harness texts. Not part of the production wire.

Canned lines used to prove origin across two terminals. Production
Imago code should not call this class. Slot.burst() and the CLI do.
"""

from __future__ import annotations

import time


class Demo:
    SILLY = {
        "FOX": [
            "quartz-fox juggles 17 pinecones under a magenta lighthouse",
            "FOX-only proverb: never trust a teapot that quotes Hegel",
            "FOX payload zebra-plaid #3 — this line must not appear on FOX as inbound from itself",
        ],
        "OTTER": [
            "otter-kelp accordion solo in B-flat minor, volume 11",
            "OTTER-only proverb: a polite cyclone still rearranges the furniture",
            "OTTER payload marmalade-submarine #9 — origin stamp is the point",
        ],
    }

    PULSES = [
        "WXYZ lighthouse-tick, barometer 29.92 and falling",
        "WXYZ shipping forecast: fog in the packet strait",
        "WXYZ pulse-stamp quartz-fox is not the sender of this line",
        "WXYZ time-pips: three short, one long, tea kettle optional",
    ]

    @staticmethod
    def silly_for(name: str) -> list[str]:
        if name in Demo.SILLY:
            return list(Demo.SILLY[name])
        return [
            f"{name} recites the serial number of a leftover moon: 7Q-NEBULA",
            f"{name} claims the spoon is a diplomat from the cutlery republic",
            f"{name} unique-stamp {int(time.time())} — look for this exact token",
        ]

    @staticmethod
    def pulse_text(seq: int) -> str:
        return Demo.PULSES[seq % len(Demo.PULSES)] + f"  [seq {seq}]"
