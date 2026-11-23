"""Fog-safe player views. Bots and (later) AI and UI read the game only through these.

`PlayerView` answers questions with what the player can know (designer rules, 2026-11-13):
- terrain only on hexes visible now: within a unit's sight, a city's sight, or anything the
  player built (fog.visible_tiles); hexes go fully back to fog when units leave;
- every city the player has discovered, with its live status, wherever it is;
- units only on visible hexes.
`explored` (ever seen) is kept for exploration targets but reveals no terrain.
`observe()` serialises a view for clients.
"""

from __future__ import annotations

from typing import Any

from beacon import fog
from beacon.config import Config
from beacon.state import (
    OVERRUN,
    City,
    CityMemory,
    GameState,
    Player,
    Tile,
    Unit,
    bits_get,
    to_dict,
)


class PlayerView:
    def __init__(self, state: GameState, cfg: Config, pid: str):
        self._state = state
        self.cfg = cfg
        self.pid = pid
        self.visible = fog.visible_tiles(state, cfg, pid)
        self._explored = bits_get(state.players[pid].explored)
        self._known_city_tiles = {
            state.cities[int(k)].tile for k in state.players[pid].known_cities
        } | {c.tile for c in state.cities if c.owner == pid}

    # -- map ---------------------------------------------------------------------------------

    @property
    def turn(self) -> int:
        return self._state.turn

    @property
    def width(self) -> int:
        return self._state.width

    @property
    def height(self) -> int:
        return self._state.height

    @property
    def player(self) -> Player:
        return self._state.players[self.pid]

    def is_explored(self, i: int) -> bool:
        return bool(self._explored >> i & 1)

    def is_visible(self, i: int) -> bool:
        return i in self.visible

    def tile(self, i: int) -> Tile | None:
        """Terrain of a hex the player can see now (or a discovered city's hex)."""
        if i in self.visible or i in self._known_city_tiles:
            return self._state.tiles[i]
        return None

    def shown_tiles(self) -> list[int]:
        return sorted(self.visible | self._known_city_tiles)

    def explored_tiles(self) -> list[int]:
        bits, out, i = self._explored, [], 0
        while bits:
            if bits & 1:
                out.append(i)
            bits >>= 1
            i += 1
        return out

    # -- units and cities --------------------------------------------------------------------

    def my_units(self) -> list[Unit]:
        return [u for u in self._state.sorted_units() if u.owner == self.pid]

    def visible_units(self) -> list[Unit]:
        """Every unit the player can see: their own and anyone's on visible hexes."""
        return [
            u for u in self._state.sorted_units() if u.owner == self.pid or u.tile in self.visible
        ]

    def my_cities(self) -> list[City]:
        return [c for c in self._state.cities if c.owner == self.pid]

    def known_cities(self) -> dict[int, CityMemory]:
        """Every city the player has discovered, with its live status."""
        out = {}
        for key in self.player.known_cities:
            city = self._state.cities[int(key)]
            out[city.id] = CityMemory(city.status, city.owner, city.pop, self.turn)
        for city in self.my_cities():
            out[city.id] = CityMemory(city.status, city.owner, city.pop, self.turn)
        return out

    def city_tile(self, city_id: int) -> int | None:
        """Location of a known city."""
        if (
            str(city_id) in self.player.known_cities
            or self._state.cities[city_id].owner == self.pid
        ):
            return self._state.cities[city_id].tile
        return None

    def city_name(self, city_id: int) -> str | None:
        return self._state.cities[city_id].name if self.city_tile(city_id) is not None else None


def observe(state: GameState, cfg: Config, pid: str) -> dict[str, Any]:
    """A JSON-ready snapshot of what player `pid` knows."""
    view = PlayerView(state, cfg, pid)
    tiles = {}
    for i in view.shown_tiles():
        entry = to_dict(state.tiles[i])
        entry["visible"] = i in view.visible
        tiles[str(i)] = entry
    # explored land stays clear once discovered (designer 2026-11-15, SPEC_M10): what never
    # changes (terrain, relief, features, resources) and whose land it is; improvements, routes
    # and units there stay hidden until the hex is in sight again
    for i in view.explored_tiles():
        if str(i) in tiles:
            continue
        t = state.tiles[i]
        tiles[str(i)] = {
            "terrain": t.terrain,
            "elevation": t.elevation,
            "feature": t.feature,
            "resource": t.resource,
            "continent": t.continent,
            "city": t.city,
            "nest": t.nest,
            "visible": False,
        }
    cities = {}
    for cid, memory in view.known_cities().items():
        city = state.cities[cid]
        if city.owner == pid:
            cities[str(cid)] = to_dict(city)
        else:
            cities[str(cid)] = {"name": city.name, "tile": city.tile, **to_dict(memory)}
            if memory.status == OVERRUN and city.status == OVERRUN:  # SPEC_M12
                from beacon.threat import rumour

                cities[str(cid)]["rumour"] = rumour(cfg, city)
                if cid in view.player.intel:
                    cities[str(cid)]["contents"] = city.contents
                cities[str(cid)]["resistance"] = city.armed_by.get(pid, 0) and city.resistance
    return {
        "turn": state.turn,
        "player": to_dict(view.player),
        "tiles": tiles,
        "cities": cities,
        "units": [to_dict(u) for u in view.visible_units()],
    }
