"""Gear and people moving between units and towns (docs/SPEC_M20.md, designer 2026-11-19).

A unit that finds gear it does not use carries it (up to `pack_size` items); inside its own land
it leaves it in the nearest town's armoury, where a unit standing in the town can take it. Any
unit standing in its own town's land can join the town as a grown citizen."""

from __future__ import annotations

from typing import Any

from beacon import hexgrid
from beacon.config import Config
from beacon.state import ACTIVE, City, GameState, Unit

Events = list[dict[str, Any]]


def pack_size(cfg: Config) -> int:
    return cfg.t("survivor.pack_size")


def carries_only(cfg: Config, unit: Unit) -> bool:
    """Scouts and civilians carry gear rather than use it."""
    return cfg.units[unit.type]["role"] in ("recon", "civilian")


def home_of(state: GameState, unit: Unit) -> City | None:
    """The unit's own town whose land it stands in (nearest town if several), or None."""
    from beacon import borders

    best = None
    for c in state.cities:
        if c.owner == unit.owner and c.status == ACTIVE and borders.owns(state, c, unit.tile):
            d = hexgrid.distance(unit.tile, c.tile, state.width)
            if best is None or (d, c.id) < best[0]:
                best = ((d, c.id), c)
    return best[1] if best else None


def store(city: City, items: list[str]) -> None:
    for g in items:
        city.armoury[g] = city.armoury.get(g, 0) + 1


def deposit(state: GameState, cfg: Config) -> Events:
    """End of turn: units carrying gear inside their own land leave it in the town's armoury."""
    events: Events = []
    for u in state.sorted_units():
        if not u.pack or u.owner not in state.players:
            continue
        town = home_of(state, u)
        if town is None:
            continue
        items, u.pack = u.pack, []
        store(town, items)
        events.append(
            {
                "turn": state.turn,
                "kind": "gear_stored",
                "player": u.owner,
                "unit": u.id,
                "city": town.id,
                "items": items,
            }
        )
    return events


def equip_problem(state: GameState, cfg: Config, unit: Unit, item: str) -> str | None:
    city = state.city_at(unit.tile)
    if city is None or city.owner != unit.owner:
        return "stand in one of your towns to take gear from its armoury"
    if city.armoury.get(item, 0) <= 0:
        return f"{city.name}'s armoury has no {item.replace('_', ' ')}"
    if carries_only(cfg, unit):
        return "scouts and civilians carry gear but do not use it"
    from beacon.survivors import ARMOUR, WEAPONS, settings

    if item not in WEAPONS and item not in ARMOUR:
        return f"{item} is not gear"
    loot = settings(cfg)["loot"]
    slot = WEAPONS if item in WEAPONS else ARMOUR
    key = "attack" if slot is WEAPONS else "defence"
    have = [g for g in unit.gear if g in slot]
    if have and loot[have[0]].get(key, 0) >= loot[item].get(key, 0):
        return "it already has gear as good"
    return None


def equip(state: GameState, cfg: Config, unit: Unit, item: str) -> Events:
    from beacon.survivors import ARMOUR, WEAPONS

    city = state.city_at(unit.tile)
    assert city is not None
    slot = WEAPONS if item in WEAPONS else ARMOUR
    old = [g for g in unit.gear if g in slot]
    unit.gear = [g for g in unit.gear if g not in slot] + [item]
    city.armoury[item] -= 1
    if city.armoury[item] == 0:
        del city.armoury[item]
    store(city, old)
    return [{"kind": "gear_equipped", "unit": unit.id, "item": item, "city": city.id}]


def join_problem(state: GameState, cfg: Config, unit: Unit) -> str | None:
    if cfg.units[unit.type].get("fixed"):
        return "city defences cannot join a town"
    if unit.type == "band_leader":
        return "the leader leads; it does not join a town as a citizen"
    if home_of(state, unit) is None:
        return "stand inside one of your towns' land to join it"
    return None


def join(state: GameState, cfg: Config, unit: Unit) -> Events:
    """The unit settles in the town as a grown citizen; its gear goes to the armoury."""
    from beacon import citizens
    from beacon.units import remove_unit

    town = home_of(state, unit)
    assert town is not None
    store(town, [*unit.gear, *unit.pack])
    remove_unit(state, unit)
    town.pop += 1
    citizens.sync(state, cfg, town)
    return [
        {
            "kind": "unit_joined_city",
            "unit": unit.id,
            "type": unit.type,
            "city": town.id,
            "pop": town.pop,
        }
    ]
