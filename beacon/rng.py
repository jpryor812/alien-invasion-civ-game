"""Named, seeded random streams. All randomness in the simulation comes from here.

Streams are stateless: each draw site asks for a generator keyed by (master seed, stream name,
keys...), for example `stream(seed, "combat", turn, seq)`. The generator's seed is a SHA-256 hash
of those inputs, so:

- the same inputs give the same numbers on any machine and any Python run;
- adding a draw in one place never shifts the numbers drawn anywhere else;
- there is no generator state to save, so a resumed game replays exactly.

Bots and AI players must never call this module.
"""

from __future__ import annotations

import hashlib
import json
import random
from collections.abc import Sequence
from typing import TypeVar

STREAMS = frozenset({"map", "cities", "combat", "events"})

T = TypeVar("T")


def derive_seed(master_seed: int, name: str, *keys: int | str) -> int:
    if name not in STREAMS:
        raise ValueError(f"unknown RNG stream '{name}'; register it in beacon.rng.STREAMS")
    payload = json.dumps([master_seed, name, *keys], separators=(",", ":"))
    return int.from_bytes(hashlib.sha256(payload.encode("utf-8")).digest()[:8], "big")


def stream(master_seed: int, name: str, *keys: int | str) -> random.Random:
    """A fresh generator for one draw site."""
    return random.Random(derive_seed(master_seed, name, *keys))


def weighted_choice(rng: random.Random, items: Sequence[T], weights: Sequence[int]) -> T:
    """Pick one item with integer weights, using only integer draws."""
    if len(items) != len(weights) or not items:
        raise ValueError("weighted_choice needs equal, non-empty items and weights")
    total = sum(weights)
    if total <= 0:
        raise ValueError("weighted_choice needs a positive total weight")
    roll = rng.randrange(total)
    for item, weight in zip(items, weights, strict=True):
        if roll < weight:
            return item
        roll -= weight
    raise AssertionError("unreachable")


def percent_roll(rng: random.Random, percent: int) -> bool:
    """True with probability `percent` / 100."""
    return rng.randrange(100) < percent
