"""City connection: a city produces only if roads, railways or friendly city tiles join it to its
owner's capital (DESIGN.md section 5)."""

from __future__ import annotations

from beacon import hexgrid
from beacon.config import Config
from beacon.paths import reachable
from beacon.state import ACTIVE, GameState


def connected_cities(state: GameState, pid: str) -> set[int]:
    own = {c.tile: c.id for c in state.cities if c.owner == pid and c.status == ACTIVE}
    capital = next(
        (c for c in state.cities if c.owner == pid and c.is_capital and c.status == ACTIVE), None
    )
    if capital is None:
        return set()
    w, h = state.width, state.height
    city_tiles = {c.tile for c in state.cities}
    net = reachable(
        capital.tile,
        lambda i: hexgrid.neighbours(i, w, h),
        lambda i: i in own or (state.tiles[i].route is not None and i not in city_tiles),
    )
    return {own[t] for t in net if t in own}


def update_connections(state: GameState, cfg: Config, pid: str) -> None:
    linked = connected_cities(state, pid)
    for city in state.cities:
        if city.owner == pid:
            city.connected = city.id in linked


def unlinked_routes(state: GameState, pid: str) -> int:
    """A player's road and rail hexes not joined to any of its cities (designer 2026-11-14: they
    cost upkeep until connected)."""
    from beacon.fog import built_tiles  # fog imports nothing from here

    mine = [t for t in built_tiles(state).get(pid, []) if state.tiles[t].route]
    if not mine:
        return 0
    starts = [c.tile for c in state.cities if c.owner == pid and c.status == ACTIVE]
    w, h = state.width, state.height
    linked: set[int] = set()
    for s in starts:
        if s in linked:
            continue
        linked |= reachable(
            s,
            lambda i: hexgrid.neighbours(i, w, h),
            lambda i: state.tiles[i].route is not None or i in starts,
        )
    return sum(1 for t in mine if t not in linked)
