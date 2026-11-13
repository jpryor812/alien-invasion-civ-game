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
