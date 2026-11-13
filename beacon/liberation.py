"""Recovering lost cities and keeping the credit ledger.

Cities always return to their continent's player; the credit goes to whoever freed them.
"""

from __future__ import annotations

from typing import Any

from beacon import cities, network
from beacon.config import Config
from beacon.state import ACTIVE, ALIENS, OVERRUN, City, GameState

Events = list[dict[str, Any]]

CREDIT_KEYS = (
    "kills",
    "units_lost",
    "cities_liberated",
    "cities_reclaimed",
    "cities_refounded",
    "damage_dealt",
)


def credit(state: GameState, pid: str, key: str, amount: int = 1) -> None:
    if pid not in state.players or amount == 0:
        return
    if key not in CREDIT_KEYS:
        raise ValueError(f"unknown credit key {key}")
    ledger = state.players[pid].credits
    ledger[key] = ledger.get(key, 0) + amount


def _restore(state: GameState, cfg: Config, city: City, pop: int) -> None:
    city.status = ACTIVE
    city.owner = city.continent if city.continent in state.players else None
    city.pop = max(1, pop)
    city.food_store = 0
    city.production_store = 0
    city.queue = []
    if city.owner is not None:
        network.update_connections(state, cfg, city.owner)


def reclaim(state: GameState, cfg: Config, city: City, by: str) -> Events:
    """A military unit walks into a dormant city."""
    _restore(state, cfg, city, city.pop)
    city.hp = cities.max_hp(cfg, city)
    credit(state, by, "cities_reclaimed")
    return [{"kind": "city_reclaimed", "city": city.id, "by": by, "owner": city.owner}]


def refound(state: GameState, cfg: Config, city: City, by: str) -> Events:
    """A restoration team rebuilds an empty city."""
    _restore(state, cfg, city, cfg.t("cities.refound_pop"))
    city.hp = cities.max_hp(cfg, city)
    credit(state, by, "cities_refounded")
    return [{"kind": "city_refounded", "city": city.id, "by": by, "owner": city.owner}]


def liberate(state: GameState, cfg: Config, city: City, by: str) -> Events:
    """A land melee unit takes an overrun city to 0 HP and walks in."""
    loss = city.pop * cfg.t("cities.liberation_pop_loss_pct") // 100
    _restore(state, cfg, city, city.pop - loss)
    city.hp = cities.max_hp(cfg, city) * cfg.t("cities.liberated_hp_pct") // 100
    credit(state, by, "cities_liberated")
    return [
        {
            "kind": "city_liberated",
            "city": city.id,
            "by": by,
            "owner": city.owner,
            "pop": city.pop,
            "damage_by": dict(city.damage_by),
        }
    ]


def overrun(state: GameState, cfg: Config, city: City) -> Events:
    """Aliens take a city (used from M4 on)."""
    previous = city.owner
    city.status = OVERRUN
    city.owner = ALIENS
    city.queue = []
    city.hp = cities.max_hp(cfg, city) * cfg.t("cities.liberated_hp_pct") // 100
    city.damage_by = {}
    if previous in state.players:
        network.update_connections(state, cfg, previous)
    return [{"kind": "city_overrun", "city": city.id, "previous_owner": previous}]
