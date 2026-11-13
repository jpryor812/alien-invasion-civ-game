"""Research: the economic, production and military trees (beacon tree arrives in M5)."""

from __future__ import annotations

from typing import Any

from beacon.config import Config
from beacon.state import Player


def available(cfg: Config, player: Player) -> list[str]:
    known = set(player.techs)
    return sorted(
        t
        for t, spec in cfg.techs.items()
        if t not in known and all(p in known for p in spec["prereqs"])
    )


def knows(player: Player, tech: str | None) -> bool:
    return tech is None or tech in player.techs


def progress(cfg: Config, player: Player, science: int, turn: int) -> list[dict[str, Any]]:
    """Add science and learn the current tech if paid for. Overflow carries over."""
    events = []
    player.research_progress += science
    if player.research is not None:
        cost = cfg.techs[player.research]["cost"]
        if player.research_progress >= cost:
            player.research_progress -= cost
            player.techs = sorted([*player.techs, player.research])
            events.append(
                {"turn": turn, "kind": "tech_learned", "player": player.id, "tech": player.research}
            )
            player.research = None
    return events
