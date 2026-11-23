"""Fog of war: three layers per player (unexplored, explored, visible).

Explored tiles are remembered (terrain, improvements); units are shown only on visible tiles.
Cities are remembered as last seen. Vision comes from units, owned cities, and anything the
player built (improvements and routes keep their own hex clear; radio beacons see further).
"""

from __future__ import annotations

from beacon import hexgrid
from beacon.config import Config
from beacon.state import CityMemory, GameState, bits_get, bits_put


def city_vision(cfg: Config, buildings: list[str]) -> int:
    return cfg.t("cities.vision") + sum(cfg.buildings[b].get("vision", 0) for b in buildings)


def unit_vision(state: GameState, cfg: Config, unit_type: str, tile: int) -> int:
    elevation = state.tiles[tile].elevation
    return cfg.units[unit_type]["vision"] + cfg.elevations[elevation]["vision_bonus"]


def visible_tiles(state: GameState, cfg: Config, pid: str) -> set[int]:
    """What a player sees now: their own sight plus their allies' (docs/SPEC_M6.md)."""
    seen = _own_visible(state, cfg, pid)
    for ally in state.players[pid].allies if pid in state.players else []:
        seen |= _own_visible(state, cfg, ally)
    return seen


def _own_visible(state: GameState, cfg: Config, pid: str) -> set[int]:
    w, h = state.width, state.height
    seen: set[int] = set()
    for unit in state.units.values():
        if unit.owner == pid:
            seen.update(
                hexgrid.within(unit.tile, unit_vision(state, cfg, unit.type, unit.tile), w, h)
            )
    for city in state.cities:
        if city.owner == pid:
            seen.update(hexgrid.within(city.tile, city_vision(cfg, city.buildings), w, h))
    for i in built_tiles(state).get(pid, ()):
        tile = state.tiles[i]
        radius = cfg.improvements[tile.improvement].get("vision", 0) if tile.improvement else 0
        seen.update(hexgrid.within(i, radius, w, h) if radius else (i,))
    return seen


def built_tiles(state: GameState) -> dict[str, list[int]]:
    """Hexes each player has built on. Cached outside the dataclass fields (never serialised);
    anything that changes `Tile.built_by` must call `touch_built`."""
    cache = state.__dict__.get("_built_tiles")
    if cache is None:
        cache = {}
        for i, tile in enumerate(state.tiles):
            if tile.built_by is not None:
                cache.setdefault(tile.built_by, []).append(i)
        state.__dict__["_built_tiles"] = cache
    return cache


def touch_built(state: GameState) -> None:
    state.__dict__.pop("_built_tiles", None)


def remember(state: GameState, pid: str, tiles: set[int] | list[int]) -> None:
    """Mark tiles explored and record any cities on them as seen this turn."""
    player = state.players[pid]
    bits = bits_get(player.explored)
    for t in tiles:
        bits |= 1 << t
    player.explored = bits_put(bits)
    tile_set = set(tiles)
    for city in state.cities:
        if city.tile in tile_set:
            player.known_cities[str(city.id)] = CityMemory(
                status=city.status, owner=city.owner, pop=city.pop, turn_seen=state.turn
            )


def reveal_around(state: GameState, cfg: Config, pid: str, tile: int, radius: int) -> None:
    remember(state, pid, hexgrid.within(tile, radius, state.width, state.height))


def refresh(state: GameState, cfg: Config, pid: str) -> None:
    remember(state, pid, visible_tiles(state, cfg, pid))


def refresh_all(state: GameState, cfg: Config) -> None:
    for pid in state.player_ids():
        refresh(state, cfg, pid)
    share_city_maps(state)


def share_city_maps(state: GameState) -> None:
    """Allies know every city the other has discovered."""
    for pid in state.player_ids():
        player = state.players[pid]
        for ally in player.allies:
            for key, memory in state.players[ally].known_cities.items():
                if key not in player.known_cities:
                    player.known_cities[key] = memory
