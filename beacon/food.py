"""Food for people and the army (docs/SPEC_M18.md, designer 2026-11-18).

A town's spare food goes into its store, the bank that pays for its army and for births. Every
unit carries rations: inside its owner's land the nearest town feeds it (from what is left after
the citizens have eaten) and its rations refill; outside, or when the town cannot feed it, it eats
a ration a turn, and with none left it starves. No randomness.
"""

from __future__ import annotations

from typing import Any

from beacon import hexgrid
from beacon.config import Config
from beacon.state import ACTIVE, City, GameState, Unit

Events = list[dict[str, Any]]


def F(cfg: Config, key: str) -> Any:  # noqa: N802 - short accessor
    return cfg.t(f"food.{key}")


# -- what people eat --------------------------------------------------------------------------


def eats(cfg: Config, adult: bool) -> int:
    return cfg.t("economy.food_per_pop") if adult else F(cfg, "child_eats")


def store_cap(cfg: Config, city: City) -> int:
    extra = F(cfg, "granary_cap") if F(cfg, "granary") in city.buildings else 0
    return F(cfg, "store_cap") + extra


# -- rations ----------------------------------------------------------------------------------


def rations(cfg: Config, unit: Unit) -> int:
    return F(cfg, "rations") if unit.rations < 0 else unit.rations


def eats_food(cfg: Config, unit: Unit) -> bool:
    return bool(cfg.units[unit.type].get("eats", True))


def _towns(state: GameState, pid: str) -> list[City]:
    """Towns that feed `pid`'s units: its own and its allies' (an ally's land is friendly)."""
    friends = {pid, *(state.players[pid].allies if pid in state.players else ())}
    return [c for c in state.cities if c.owner in friends and c.status == ACTIVE]


def feeder(
    state: GameState, cfg: Config, unit: Unit, towns: list[City] | None = None
) -> City | None:
    """The town that feeds this unit: the nearest friendly town within supply_radius (ties to
    the lower city id), or None when it is outside friendly land."""
    radius = F(cfg, "supply_radius")
    best: tuple[int, int] | None = None
    found = None
    for c in towns if towns is not None else _towns(state, unit.owner):
        d = hexgrid.distance(unit.tile, c.tile, state.width)
        if d <= radius and (best is None or (d, c.id) < best):
            best, found = (d, c.id), c
    return found


def armies(state: GameState, cfg: Config, pid: str) -> dict[int, list[Unit]]:
    """City id (of `pid`) -> the units it feeds this turn: units of `pid` and its allies whose
    nearest friendly town it is, by unit id."""
    towns: dict[str, list[City]] = {}
    out: dict[int, list[Unit]] = {}
    friends = {pid, *state.players[pid].allies}
    for u in state.sorted_units():
        if u.owner not in friends or not eats_food(cfg, u):
            continue
        if u.owner not in towns:
            towns[u.owner] = _towns(state, u.owner)
        c = feeder(state, cfg, u, towns[u.owner])
        if c is not None and c.owner == pid:
            out.setdefault(c.id, []).append(u)
    return out


def army_food(state: GameState, cfg: Config, city: City) -> int:
    """Food this town's army would eat this turn (for display)."""
    if city.owner not in state.players:
        return 0
    return F(cfg, "unit_eats") * len(armies(state, cfg, city.owner).get(city.id, []))


def feed(state: GameState, cfg: Config, city: City, army: list[Unit], surplus: int) -> int:
    """The town feeds what it can of its army from its spare food and store, soldiers by id;
    returns the surplus left. Units it cannot feed live on rations (see `field`)."""
    cost = F(cfg, "unit_eats")
    can = max(0, surplus + city.food_store) // cost if cost else len(army)
    for u in army[:can]:
        u.fed = state.turn
        u.rations = F(cfg, "rations")
    return surplus - cost * min(can, len(army))


def field(state: GameState, cfg: Config, pid: str) -> Events:
    """Units no town fed this turn eat a ration, or starve."""
    from beacon.units import remove_unit

    events: Events = []
    for u in state.sorted_units():
        if u.owner != pid or not eats_food(cfg, u) or u.fed == state.turn:
            continue
        left = rations(cfg, u)
        if left > 0:
            u.rations = left - 1
            if u.rations == 0:
                events.append(
                    {"turn": state.turn, "kind": "rations_out", "player": pid, "unit": u.id}
                )
            continue
        u.rations = 0
        u.hp -= F(cfg, "starve_hp")
        if u.hp <= 0:
            remove_unit(state, u)
            events.append(
                {
                    "turn": state.turn,
                    "kind": "unit_starved",
                    "player": pid,
                    "unit": u.id,
                    "type": u.type,
                    "tile": u.tile,
                }
            )
        else:
            events.append(
                {
                    "turn": state.turn,
                    "kind": "unit_hungry",
                    "player": pid,
                    "unit": u.id,
                    "hp": u.hp,
                    "at_home": feeder(state, cfg, u) is not None,  # its town is short of food
                }
            )
    return events


def refill_near(state: GameState, cfg: Config, pid: str, tile: int, radius: int) -> int:
    """A food crate: every unit of `pid` within `radius` hexes refills its rations."""
    n = 0
    for u in state.sorted_units():
        if u.owner == pid and hexgrid.distance(u.tile, tile, state.width) <= radius:
            u.rations = F(cfg, "rations")
            n += 1
    return n


# -- freed towns ------------------------------------------------------------------------------


def damaged_farm(state: GameState, cfg: Config, city: City) -> int | None:
    """The aliens left the town's best farmland damaged: a farm to repair. Returns the hex."""
    from beacon.cities import work_tiles
    from beacon.tiles import tile_yields

    farm = F(cfg, "repair_farm")
    spec = cfg.improvements[farm]
    land = [
        i
        for i in work_tiles(state, cfg, city)
        if i != city.tile
        and state.tiles[i].terrain in spec["terrains"]
        and state.tiles[i].elevation in spec["elevations"]
        and not state.tiles[i].feature
        and state.tiles[i].improvement in (None, farm)
        and not state.tiles[i].route
    ]
    if not land:
        return None
    best = max(land, key=lambda i: (tile_yields(cfg, state.tiles[i])["food"], -i))
    state.tiles[best].improvement = None
    state.tiles[best].pillaged = farm
    return best
