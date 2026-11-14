"""Unit basics: specs, layers, occupancy and placement.

A hex holds at most one military unit (a stack of two same-type units counts as one) and one
civilian. Units of different sides never share a hex.
"""

from __future__ import annotations

from typing import Any

from beacon import hexgrid
from beacon.config import Config
from beacon.state import ACTIVE, ALIENS, OVERRUN, GameState, Unit
from beacon.tiles import is_passable_land, is_water


def spec(cfg: Config, unit_type: str) -> dict[str, Any]:
    return cfg.units[unit_type]


def is_civilian(cfg: Config, unit_type: str) -> bool:
    return cfg.units[unit_type]["role"] == "civilian"


def is_fixed(cfg: Config, unit_type: str) -> bool:
    """City defence units never move and stand only on a city tile (designer, 2026-11-14)."""
    return bool(cfg.units[unit_type].get("fixed"))


def slot_kind(cfg: Config, unit_type: str) -> str:
    """Each hex holds one unit of each kind: a field military unit, a city defence unit and a
    civilian."""
    if is_fixed(cfg, unit_type):
        return "fixed"
    return "civilian" if is_civilian(cfg, unit_type) else "military"


def max_hp(cfg: Config, unit: Unit) -> int:
    return cfg.t("combat.unit_max_hp") * unit.count


def full_moves(cfg: Config, unit_type: str) -> int:
    return cfg.units[unit_type]["moves"] * cfg.t("movement.scale")


def side(owner: str) -> str:
    return ALIENS if owner == ALIENS else "humans"


def hostile(a: str, b: str) -> bool:
    """Players never fight each other; everyone fights the aliens."""
    return side(a) != side(b)


def occupancy(state: GameState) -> dict[int, list[Unit]]:
    occ: dict[int, list[Unit]] = {}
    for unit in state.sorted_units():
        occ.setdefault(unit.tile, []).append(unit)
    return occ


def domain_allows(state: GameState, cfg: Config, unit_type: str, owner: str, tile: int) -> bool:
    """Can a unit of this type stand on this hex, terrain-wise?"""
    t = state.tiles[tile]
    if cfg.units[unit_type]["domain"] == "land":
        return is_passable_land(cfg, t)
    if is_water(cfg, t):
        return True
    city = state.city_at(tile)
    return (
        city is not None
        and city.owner == owner
        and any(
            is_water(cfg, state.tiles[n])
            for n in hexgrid.neighbours(tile, state.width, state.height)
        )
    )


def city_blocks(state: GameState, owner: str, tile: int) -> bool:
    """A city held by the other side cannot be entered (it must be attacked)."""
    city = state.city_at(tile)
    if city is None:
        return False
    if city.status == OVERRUN:
        return owner != ALIENS
    if city.status == ACTIVE:
        return owner == ALIENS
    return False


def slot_free(
    cfg: Config,
    occ: dict[int, list[Unit]],
    unit_type: str,
    owner: str,
    tile: int,
    ignore: int | None = None,
) -> bool:
    kind = slot_kind(cfg, unit_type)
    for other in occ.get(tile, []):
        if other.id == ignore:
            continue
        if hostile(other.owner, owner):
            return False
        if slot_kind(cfg, other.type) == kind:
            return False
    return True


def can_stand(
    state: GameState,
    cfg: Config,
    occ: dict[int, list[Unit]],
    unit_type: str,
    owner: str,
    tile: int,
    ignore: int | None = None,
) -> bool:
    return (
        domain_allows(state, cfg, unit_type, owner, tile)
        and not city_blocks(state, owner, tile)
        and slot_free(cfg, occ, unit_type, owner, tile, ignore)
    )


def create_unit(state: GameState, cfg: Config, unit_type: str, owner: str, tile: int) -> Unit:
    unit = Unit(
        id=state.new_id(),
        type=unit_type,
        owner=owner,
        tile=tile,
        hp=cfg.t("combat.unit_max_hp"),
        moves_left=full_moves(cfg, unit_type),
    )
    state.units[str(unit.id)] = unit
    return unit


def free_tile_near(
    state: GameState, cfg: Config, unit_type: str, owner: str, near: int, max_radius: int
) -> int | None:
    """Nearest hex to `near` (ties by index) where this unit could stand, within max_radius."""
    occ = occupancy(state)
    for radius in range(max_radius + 1):
        ring = [
            t
            for t in hexgrid.within(near, radius, state.width, state.height)
            if hexgrid.distance(t, near, state.width) == radius
        ]
        for t in ring:
            if can_stand(state, cfg, occ, unit_type, owner, t):
                return t
    return None


def place_unit(
    state: GameState, cfg: Config, unit_type: str, owner: str, near: int, max_radius: int
) -> Unit | None:
    if is_fixed(cfg, unit_type):
        max_radius = 0  # city defence units are placed on the city tile or not at all
    tile = free_tile_near(state, cfg, unit_type, owner, near, max_radius)
    if tile is None:
        return None
    return create_unit(state, cfg, unit_type, owner, tile)


def remove_unit(state: GameState, unit: Unit) -> None:
    del state.units[str(unit.id)]
