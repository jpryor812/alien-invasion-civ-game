"""Unit experience and promotions (designer, 2026-11-14).

Every combat a unit takes part in, attacking or attacked, earns it 1 experience. A promotion
becomes due at 2 experience, then each time the total doubles (4, 8, 16), then each time it grows
by half (24, 36, 54, 81...). The player picks one option per promotion; for now every unit has
the same two (+10% attack or +10% defense); unit-specific options can be added in the data.
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
    cls = cfg.units[unit.type].get("class")
    return sorted(
        k
        for k, v in opts.items()
        if (not v.get("units") or unit.type in v["units"])
        and (not v.get("classes") or cls in v["classes"])
    )


def promote_problem(state: GameState, cfg: Config, unit: Unit, choice: str) -> str | None:
    if cfg.units[unit.type]["role"] == "civilian":
        return "civilians do not earn promotions"
    if due(cfg, unit) <= 0:
        return f"no promotion due (next at {next_threshold(cfg, unit.xp)} experience)"
    if choice not in options(cfg, unit):
        return f"unknown promotion {choice!r}"
    return None


GOLD_UPGRADE = "gold_upgrade"


def strength_pct(cfg: Config, unit: Unit, defending: bool) -> int:
    key = "defence_pct" if defending else "attack_pct"
    opts = cfg.t("promotions.options")
    pct = sum(opts[p].get(key, 0) for p in unit.promotions if p in opts)
    return pct + unit.promotions.count(GOLD_UPGRADE) * cfg.t("defences.upgrade.strength_pct")


def gain(state: GameState, cfg: Config, unit: Unit) -> None:
    """One combat's experience, for player field units only (aliens do not promote; city guns
    are upgraded with gold instead)."""
    if (
        unit.owner in state.players
        and str(unit.id) in state.units
        and not cfg.units[unit.type].get("fixed")
    ):
        unit.xp += 1


def upgrade_cost(cfg: Config, unit: Unit) -> int | None:
    """Gold for a city gun's next upgrade level, or None at the top level."""
    u = cfg.t("defences.upgrade")
    level = unit.promotions.count(GOLD_UPGRADE)
    if level >= u["max_level"]:
        return None
    return u["cost_base"] + u["cost_step"] * level


def upgrade_problem(state: GameState, cfg: Config, unit: Unit) -> str | None:
    if not cfg.units[unit.type].get("fixed"):
        return "only city defenses are upgraded with gold; field units earn promotions"
    cost = upgrade_cost(cfg, unit)
    if cost is None:
        return "already at the top level"
    if state.players[unit.owner].gold < cost:
        return f"needs {cost} gold"
    return None


def _taken(cfg: Config, unit: Unit) -> list[dict]:
    opts = cfg.t("promotions.options")
    return [opts[p] for p in unit.promotions if p in opts]


def vs_pct(cfg: Config, unit: Unit, key: str | None) -> int:
    """Promotion bonus against a class (or "city")."""
    return sum((o.get("vs") or {}).get(key or "", 0) for o in _taken(cfg, unit))


def heal_bonus(cfg: Config, unit: Unit) -> int:
    return sum(o.get("heal", 0) for o in _taken(cfg, unit))


def moves_bonus(cfg: Config, unit: Unit) -> int:
    return sum(o.get("moves", 0) for o in _taken(cfg, unit))
