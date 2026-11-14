"""Cities changing hands, capital succession, fallen continents, and the credit ledger.

Cities always return to their continent's player; the credit goes to whoever freed them.
"""

from __future__ import annotations

from typing import Any

from beacon import cities, hexgrid, network
from beacon.config import Config
from beacon.state import ACTIVE, ALIENS, OVERRUN, City, GameState

Events = list[dict[str, Any]]

CREDIT_KEYS = (
    "kills",
    "units_lost",
    "cities_liberated",
    "cities_reclaimed",
    "cities_refounded",
    "cities_lost",
    "damage_dealt",
)


def credit(state: GameState, pid: str, key: str, amount: int = 1) -> None:
    if pid not in state.players or amount == 0:
        return
    if key not in CREDIT_KEYS:
        raise ValueError(f"unknown credit key {key}")
    ledger = state.players[pid].credits
    ledger[key] = ledger.get(key, 0) + amount


def ensure_capital(state: GameState, cfg: Config, pid: str) -> Events:
    """If a player has active cities but no capital, the largest becomes the capital."""
    mine = [c for c in state.cities if c.owner == pid and c.status == ACTIVE]
    if not mine or any(c.is_capital for c in mine):
        return []
    new = max(mine, key=lambda c: (c.pop, -c.id))
    new.is_capital = True
    network.update_connections(state, cfg, pid)
    return [{"kind": "capital_moved", "player": pid, "city": new.id}]


def _restore(state: GameState, cfg: Config, city: City, pop: int) -> Events:
    city.status = ACTIVE
    city.owner = city.continent if city.continent in state.players else None
    city.is_capital = False
    city.pop = max(1, pop)
    city.food_store = 0
    city.production_store = 0
    city.queue = []
    if city.owner is None:
        return []
    events = ensure_capital(state, cfg, city.owner)
    network.update_connections(state, cfg, city.owner)
    return events


def reclaim(state: GameState, cfg: Config, city: City, by: str) -> Events:
    """A military unit walks into a dormant city."""
    events = _restore(state, cfg, city, city.pop)
    city.hp = cities.max_hp(cfg, city)
    credit(state, by, "cities_reclaimed")
    return [{"kind": "city_reclaimed", "city": city.id, "by": by, "owner": city.owner}, *events]


def refound(state: GameState, cfg: Config, city: City, by: str) -> Events:
    """A restoration team rebuilds an empty city."""
    events = _restore(state, cfg, city, cfg.t("cities.refound_pop"))
    city.hp = cities.max_hp(cfg, city)
    credit(state, by, "cities_refounded")
    return [{"kind": "city_refounded", "city": city.id, "by": by, "owner": city.owner}, *events]


def liberate(state: GameState, cfg: Config, city: City, by: str) -> Events:
    """A land melee unit takes an overrun city to 0 HP and walks in."""
    loss = city.pop * cfg.t("cities.liberation_pop_loss_pct") // 100
    events = _restore(state, cfg, city, city.pop - loss)
    city.hp = cities.max_hp(cfg, city) * cfg.t("cities.liberated_hp_pct") // 100
    city.liberated_turn = state.turn
    credit(state, by, "cities_liberated")
    return [
        {
            "kind": "city_liberated",
            "city": city.id,
            "by": by,
            "owner": city.owner,
            "pop": city.pop,
            "damage_by": dict(city.damage_by),
        },
        *events,
    ]


def overrun(state: GameState, cfg: Config, city: City, defenders_radius: int = 2) -> Events:
    """Aliens take a city: its owner loses it; the capital moves if needed."""
    previous = city.owner
    defenders = sorted(
        {
            u.owner
            for u in state.units.values()
            if u.owner in state.players
            and hexgrid.distance(u.tile, city.tile, state.width) <= defenders_radius
        }
    )
    was_capital = city.is_capital
    city.status = OVERRUN
    city.owner = ALIENS
    city.is_capital = False
    city.connected = False
    city.queue = []
    city.production_store = 0
    city.food_store = 0
    city.pop = max(1, city.pop * cfg.t("cities.liberation_pop_loss_pct") // 100)
    city.hp = cities.max_hp(cfg, city, state) * cfg.t("cities.liberated_hp_pct") // 100
    city.damage_by = {}
    events: Events = [
        {
            "kind": "city_overrun",
            "city": city.id,
            "previous_owner": previous,
            "was_capital": was_capital,
            "defenders": defenders,
        }
    ]
    if previous in state.players:
        credit(state, previous, "cities_lost")
        events.extend(ensure_capital(state, cfg, previous))
        network.update_connections(state, cfg, previous)
    return events


def update_fallen(state: GameState) -> Events:
    """A continent falls when its player holds no cities, and revives when it holds one."""
    events: Events = []
    for pid in state.player_ids():
        player = state.players[pid]
        holds = any(c.owner == pid and c.status == ACTIVE for c in state.cities)
        if not holds and not player.fallen:
            player.fallen = True
            player.times_fallen += 1
            events.append({"turn": state.turn, "kind": "continent_fallen", "player": pid})
        elif holds and player.fallen:
            player.fallen = False
            events.append({"turn": state.turn, "kind": "continent_revived", "player": pid})
    return events
