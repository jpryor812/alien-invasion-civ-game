"""The end-of-turn pipeline (see docs/SPEC_M0-M3.md, "Turn pipeline")."""

from __future__ import annotations

from typing import Any

from beacon.config import Config
from beacon.state import GameState


def year(cfg: Config, turn: int) -> int:
    return cfg.t("time.start_year") + turn // cfg.t("time.turns_per_year")


def advance_turn(state: GameState, cfg: Config) -> list[dict[str, Any]]:
    """Resolve the end of the current turn and start the next. Returns the events produced."""
    events: list[dict[str, Any]] = []
    state.turn += 1
    events.append({"turn": state.turn, "kind": "turn_started", "year": year(cfg, state.turn)})
    return events
