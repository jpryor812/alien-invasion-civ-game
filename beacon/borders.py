"""A town's land (docs/SPEC_M20.md, designer 2026-11-19): it starts at the town's hex and the six
around it, and each citizen born claims one more hex next to it, up to `max_radius` out. Towns not
held by a player keep the old area from map generation (`border` empty)."""

from __future__ import annotations

from typing import Any

from beacon import hexgrid
from beacon.config import Config
from beacon.state import City, GameState
from beacon.tiles import tile_yields

Events = list[dict[str, Any]]


def B(cfg: Config, key: str) -> Any:  # noqa: N802 - short accessor
    return cfg.t(f"borders.{key}")


def _taken(state: GameState, city: City) -> set[int]:
    """Hexes in another town's land."""
    out: set[int] = set()
    for c in state.cities:
        if c.id != city.id and c.border:
            out.update(c.border)
        elif c.id != city.id and c.owner in state.players:
            out.add(c.tile)
    return out


def _ok(state: GameState, city: City, t: int, taken: set[int]) -> bool:
    """A hex the town may claim: on its continent, not another town's land, and either free,
    its own natural area, or an alien-held town's area away from that town's hex."""
    tile = state.tiles[t]
    if tile.continent != city.continent or t in taken:
        return False
    if tile.city is None or tile.city == city.id:
        return True
    other = state.cities[tile.city]
    return (
        other.owner not in state.players
        and not other.border
        and hexgrid.distance(t, other.tile, state.width) > 1
    )


def start(state: GameState, cfg: Config, city: City) -> None:
    """The town's own hex and the ring around it (on its continent, not another town's)."""
    taken = _taken(state, city)
    ring = hexgrid.within(city.tile, B(cfg, "start_radius"), state.width, state.height)
    city.border = sorted({city.tile} | {t for t in ring if _ok(state, city, t, taken)})
    for t in city.border:
        state.tiles[t].city = city.id


def _score(state: GameState, cfg: Config, city: City, t: int) -> tuple[int, ...]:
    tile = state.tiles[t]
    y = tile_yields(cfg, tile)
    natural = 1 if tile.city == city.id else 0
    land = 0 if cfg.terrains[tile.terrain].get("water") else 1
    return (
        natural,
        land,
        y["food"] * 2 + y["production"] * 2 + y["gold"] + y["science"],
        1 if tile.resource else 0,
        -hexgrid.distance(t, city.tile, state.width),
        -t,
    )


def grow(state: GameState, cfg: Config, city: City) -> int | None:
    """Claim the best hex next to the town's land; returns it, or None if none is free."""
    if not city.border:
        return None
    taken = _taken(state, city)
    have = set(city.border)
    near = {
        n
        for t in city.border
        for n in hexgrid.neighbours(t, state.width, state.height)
        if n not in have
        and hexgrid.distance(n, city.tile, state.width) <= B(cfg, "max_radius")
        and _ok(state, city, n, taken)
    }
    if not near:
        return None
    best = max(near, key=lambda t: _score(state, cfg, city, t))
    city.border = sorted(have | {best})
    state.tiles[best].city = city.id
    return best


def owns(state: GameState, city: City, t: int) -> bool:
    if city.border:
        return t in city.border
    return t == city.tile or state.tiles[t].city == city.id
