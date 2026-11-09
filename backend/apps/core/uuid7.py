"""UUIDv7 generator (RFC 9562).

UUIDv7 is sortable by creation time, which makes it a good primary key for
things that are listed chronologically (transactions, reminders, …) without
exposing a sequential integer in URLs."""
from __future__ import annotations

import os
import time
from uuid import UUID


def uuid7() -> UUID:
    ms = int(time.time() * 1000) & ((1 << 48) - 1)
    rand_a = int.from_bytes(os.urandom(2), "big") & 0x0FFF
    rand_b = int.from_bytes(os.urandom(8), "big") & ((1 << 62) - 1)
    value = (ms << 80) | (0x7 << 76) | (rand_a << 64) | (0b10 << 62) | rand_b
    return UUID(int=value)
