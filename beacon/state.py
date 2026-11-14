"""Game state: plain dataclasses that round-trip through JSON.

Conventions:
- Integers, strings, booleans, None, lists and string-keyed dicts only. No floats.
- Tiles live in a flat list, `index = row * width + col` (see `beacon.hexgrid`).
- City ids are their index in `cities` (cities are never deleted). Unit ids come from `next_id`
  and units live in a dict keyed by `str(id)`.
- Player ids are continent ids. Alien-owned things have owner `ALIENS`.
"""

from __future__ import annotations

import types
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from typing import Any, Union, get_args, get_origin, get_type_hints

from beacon import canonical

STATE_VERSION = 2
ALIENS = "aliens"

# City status values.
ACTIVE = "active"
DORMANT = "dormant"
EMPTY = "empty"
OVERRUN = "overrun"
CITY_STATUSES = (ACTIVE, DORMANT, EMPTY, OVERRUN)


@dataclass
class Tile:
    terrain: str
    elevation: str = "flat"
    feature: str | None = None
    resource: str | None = None
    improvement: str | None = None
    route: str | None = None
    continent: str | None = None
    city: int | None = None  # id of the city whose work area holds this tile
    built_by: str | None = None  # player who built the improvement or route here


@dataclass
class City:
    id: int
    name: str
    continent: str
    tile: int
    status: str
    owner: str | None
    pop: int
    is_capital: bool = False
    food_store: int = 0
    production_store: int = 0
    queue: list[str] = field(default_factory=list)  # "building:x", "unit:x", "project:x"
    buildings: list[str] = field(default_factory=list)
    hp: int = 0
    focus: str = "balanced"
    connected: bool = False
    bombarded: bool = False  # has used its ranged attack this turn
    damage_by: dict[str, int] = field(default_factory=dict)  # damage dealt to it, by player
    liberated_turn: int | None = None  # last turn players freed it (alien retake target)
    besieged: bool = False  # took damage this turn, so it does not heal at turn end


@dataclass
class Job:
    improvement: str
    turns_left: int


@dataclass
class Unit:
    id: int
    type: str
    owner: str
    tile: int
    hp: int
    count: int = 1  # stack size: 1, or 2 when merged
    moves_left: int = 0  # movement sub-points
    attacks_left: int = 1
    fortified: bool = False
    acted: bool = False  # moved, attacked or worked this turn (no healing)
    order: str = "none"  # none | fortify | skip | work
    job: Job | None = None


@dataclass
class CityMemory:
    """What a player last saw of a city."""

    status: str
    owner: str | None
    pop: int
    turn_seen: int


@dataclass
class Player:
    id: str
    name: str
    gold: int = 0
    research: str | None = None
    research_progress: int = 0
    techs: list[str] = field(default_factory=list)
    explored: str = "0"  # hex bitmap of explored tile indices
    known_cities: dict[str, CityMemory] = field(default_factory=dict)
    beacon_points: int = 0
    credits: dict[str, int] = field(default_factory=dict)
    fallen: bool = False  # holds no cities (DESIGN.md 13)
    times_fallen: int = 0


@dataclass
class AlienOrder:
    kind: str  # siege | raid | patrol
    target: int  # tile


@dataclass
class AlienState:
    progress: int = 0
    techs: list[str] = field(default_factory=list)
    reinforcement_store: int = 0
    surge_cooldown: int = 0
    start_cities: int = 0
    orders: dict[str, AlienOrder] = field(default_factory=dict)  # by unit id


@dataclass
class GameState:
    seed: int
    config_digest: str
    width: int
    height: int
    tiles: list[Tile]
    players: dict[str, Player]
    cities: list[City] = field(default_factory=list)
    units: dict[str, Unit] = field(default_factory=dict)
    turn: int = 0
    next_id: int = 1
    combat_seq: int = 0
    aliens: AlienState = field(default_factory=AlienState)
    version: int = STATE_VERSION

    # -- lookups -------------------------------------------------------------------------------

    def unit(self, unit_id: int) -> Unit:
        try:
            return self.units[str(unit_id)]
        except KeyError:
            raise KeyError(f"no unit {unit_id}") from None

    def sorted_units(self) -> list[Unit]:
        return sorted(self.units.values(), key=lambda u: u.id)

    def units_at(self, tile: int) -> list[Unit]:
        return [u for u in self.sorted_units() if u.tile == tile]

    def city_at(self, tile: int) -> City | None:
        # Cities never move and are never deleted, so a tile index (outside the dataclass
        # fields, hence never serialised) stays valid; it is rebuilt if cities are added.
        index = self.__dict__.get("_city_index")
        if index is None or len(index) != len(self.cities):
            index = {c.tile: c.id for c in self.cities}
            self.__dict__["_city_index"] = index
        cid = index.get(tile)
        return None if cid is None else self.cities[cid]

    def player_ids(self) -> list[str]:
        return sorted(self.players)

    def new_id(self) -> int:
        value = self.next_id
        self.next_id += 1
        return value


# -- explored bitmaps ------------------------------------------------------------------------


def bits_get(bitmap: str) -> int:
    return int(bitmap, 16)


def bits_put(value: int) -> str:
    return format(value, "x")


def bits_indices(value: int) -> list[int]:
    out = []
    i = 0
    while value:
        if value & 1:
            out.append(i)
        value >>= 1
        i += 1
    return out


# -- serialisation ---------------------------------------------------------------------------


def to_dict(obj: Any) -> Any:
    return asdict(obj)


def _convert(tp: Any, value: Any) -> Any:
    if value is None:
        return None
    origin = get_origin(tp)
    if origin is Union or origin is types.UnionType:
        args = [a for a in get_args(tp) if a is not type(None)]
        return _convert(args[0], value)
    if is_dataclass(tp):
        return from_dict(tp, value)
    if origin is list:
        (arg,) = get_args(tp)
        return [_convert(arg, v) for v in value]
    if origin is dict:
        _, arg = get_args(tp)
        return {k: _convert(arg, v) for k, v in value.items()}
    return value


def from_dict(cls: type, data: dict[str, Any]) -> Any:
    hints = get_type_hints(cls)
    kwargs = {f.name: _convert(hints[f.name], data[f.name]) for f in fields(cls) if f.name in data}
    return cls(**kwargs)


def state_to_json(state: GameState, *, indent: int | None = None) -> str:
    return canonical.dumps(to_dict(state), indent=indent)


def state_from_json(text: str) -> GameState:
    import json

    return from_dict(GameState, json.loads(text))


def state_digest(state: GameState) -> str:
    return canonical.digest(to_dict(state))


def find_floats(obj: Any, path: str = "state") -> list[str]:
    """Paths of any float values (state must be integers only)."""
    if isinstance(obj, float):
        return [path]
    if isinstance(obj, dict):
        return [p for k, v in obj.items() for p in find_floats(v, f"{path}.{k}")]
    if isinstance(obj, list):
        return [p for i, v in enumerate(obj) for p in find_floats(v, f"{path}[{i}]")]
    return []
