"""The local career profile (docs/SPEC_M11.md): totals carried from game to game.

Each game the human plays keeps its own row (its achievements so far); the career totals are the
sums. Career milestones unlock outfits and accessories for the leader. These are cosmetic only:
gameplay bonuses never carry over (designer). Stored in runs/profile.json (git-ignored); with
accounts once multiplayer exists.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from beacon.config import Config

PROFILE = Path(__file__).resolve().parent.parent / "runs" / "profile.json"
COUNTED = ("cities_liberated", "shards_claimed", "leader_children", "kills")


def load(path: Path = PROFILE) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"games": {}}
    return data if isinstance(data.get("games"), dict) else {"games": {}}


def record(game_id: str, credits: dict[str, int], won: bool, path: Path = PROFILE) -> None:
    """Store this game's achievements so far under its id."""
    data = load(path)
    data["games"][game_id] = {k: int(credits.get(k, 0)) for k in COUNTED} | {"won": int(won)}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, sort_keys=True), encoding="utf-8")


def totals(data: dict[str, Any], current: tuple[str, dict[str, int]] | None = None) -> dict:
    """Career totals, counting the game in progress (`current`: its id and credits) as well."""
    games = dict(data["games"])
    if current is not None:
        gid, credits = current
        games[gid] = {k: int(credits.get(k, 0)) for k in COUNTED} | {
            "won": games.get(gid, {}).get("won", 0)
        }
    out = {k: sum(g.get(k, 0) for g in games.values()) for k in COUNTED}
    out["games_played"] = len(games)
    out["games_won"] = sum(g.get("won", 0) for g in games.values())
    return out


def unlocked(cfg: Config, career: dict[str, int], kind: str, item: str) -> bool:
    need = cfg.leader(f"wardrobe.{kind}.{item}.unlock")
    return need is None or all(career.get(k, 0) >= v for k, v in need.items())
