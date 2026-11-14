"""MVP score (DESIGN.md 12, docs/SPEC_M7.md): each player's weighted credit ledger, line by line.

Weights live in data/mvp.yaml. A weight named `<key>_per_10` scores the ledger entry divided by 10;
`liberation_share` is in hundredths of a city, so it is divided by 100.
"""

from __future__ import annotations

from typing import Any

from beacon.config import Config
from beacon.state import GameState


def _divisor(weight_key: str) -> tuple[str, int]:
    if weight_key.endswith("_per_10"):
        return weight_key[: -len("_per_10")], 10
    if weight_key == "liberation_share":
        return weight_key, 100
    return weight_key, 1


def score(state: GameState, cfg: Config, pid: str) -> dict[str, Any]:
    weights = cfg.mvp("weights")
    ledger = state.players[pid].credits
    lines = []
    for wkey in sorted(weights):
        entry, div = _divisor(wkey)
        raw = ledger.get(entry, 0)
        points = raw * weights[wkey] // div
        if raw:
            lines.append({"entry": entry, "raw": raw, "points": points})
    return {"player": pid, "total": sum(line["points"] for line in lines), "lines": lines}


def ranking(state: GameState, cfg: Config) -> list[dict[str, Any]]:
    """Players from highest to lowest score (ties by id)."""
    scores = [score(state, cfg, pid) for pid in state.player_ids()]
    return sorted(scores, key=lambda s: (-s["total"], s["player"]))
