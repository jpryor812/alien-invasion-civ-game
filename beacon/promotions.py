"""Unit experience and promotions (designer, 2026-11-14).

Every combat a unit takes part in, attacking or attacked, earns it 1 experience. A promotion
becomes due at 2 experience, then each time the total doubles (4, 8, 16), then each time it grows
by half (24, 36, 54, 81...). The player picks one option per promotion; for now every unit has
the same two (+10% attack or +10% defence); unit-specific options can be added in the data.
"""

from __future__ import annotations

from beacon.config import Config
from beacon.state import GameState, Unit


def thresholds(cfg: Config, upto: int) -> list[int]:
    """Experience needed for each promotion, ascending, up to `upto`."""
    p = cfg.t("promotions.steps")
    out, need = [], p["first"]
    while need <= upto:
        out.append(need)
        need = need * 2 if need < p["double_until"] else need * p["then_pct"] // 100
    return out


def next_threshold(cfg: Config, xp: int) -> int:
    p = cfg.t("promotions.steps")
    need = p["first"]
    while need <= xp:
        need = need * 2 if need < p["double_until"] else need * p["then_pct"] // 100
    return need


def earned(cfg: Config, unit: Unit) -> int:
    return len(thresholds(cfg, unit.xp))


def due(cfg: Config, unit: Unit) -> int:
    """Promotions earned but not yet chosen."""
    return max(0, earned(cfg, unit) - len(unit.promotions))


def options(cfg: Config, unit: Unit) -> list[str]:
    """Promotions this unit type may take (every type has the general ones for now)."""
    opts = cfg.t("promotions.options")
    return sorted(k for k, v in opts.items() if not v.get("units") or unit.type in v["units"])


def promote_problem(state: GameState, cfg: Config, unit: Unit, choice: str) -> str | None:
    if cfg.units[unit.type]["role"] == "civilian":
        return "civilians do not earn promotions"
    if due(cfg, unit) <= 0:
        return f"no promotion due (next at {next_threshold(cfg, unit.xp)} experience)"
    if choice not in options(cfg, unit):
        return f"unknown promotion {choice!r}"
    return None


def strength_pct(cfg: Config, unit: Unit, defending: bool) -> int:
    key = "defence_pct" if defending else "attack_pct"
    opts = cfg.t("promotions.options")
    return sum(opts[p].get(key, 0) for p in unit.promotions if p in opts)


def gain(state: GameState, unit: Unit) -> None:
    """One combat's experience, for player units only (aliens do not promote)."""
    if unit.owner in state.players and str(unit.id) in state.units:
        unit.xp += 1
