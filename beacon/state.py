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

STATE_VERSION = 7
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
    turret: int = 0  # turret level on an improved tile (0: none); see beacon/turrets.py
    pillaged: str | None = None  # improvement aliens destroyed here (a repair crew restores it)
    turret_hp: int = 0
    nest: int | None = None  # alien nest feeding this alien city (SPEC_M12)


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
    production_store: int = 0  # carried production waiting for the next item (aliens: their store)
    progress: dict[str, int] = field(default_factory=dict)  # production put into each item (M10)
    convoy: dict[str, Any] | None = None  # {"to": city id, "kind": food|production, "pct"} (M10)
    incoming: dict[str, int] = field(default_factory=dict)  # convoy goods arriving next turn
    refuses_hybrids: bool = False  # the city's attitude, seeded at the start (SPEC_M11)
    contents: str | None = None  # what an alien-held city holds (SPEC_M12, data/aliens.yaml)
    stores: dict[str, int] = field(default_factory=dict)  # timber, stone, iron (SPEC_M16)
    layout: list[dict[str, Any]] = field(
        default_factory=list
    )  # placed buildings (id, what, x, y, done)
    walls: dict[str, str] = field(default_factory=dict)  # "x,y" -> wall material, built
    wall_orders: list[list[Any]] = field(default_factory=list)  # [x, y, material] being built
    engineers: int = -1  # the city's crew (SPEC_M17); -1 until the city first gets one
    works: list[dict[str, Any]] = field(
        default_factory=list
    )  # works the crew builds, in order: {id, what, left, total, paid} (SPEC_M17)
    resistance: int = 0  # weapons smuggled in to its people (SPEC_M12)
    funded_pct: int = 0  # its defence strength cut by gold sent to the resistance (2026-11-16)
    armed_by: dict[str, int] = field(default_factory=dict)  # resistance levels, by player
    queue: list[str] = field(default_factory=list)  # "building:x", "unit:x", "project:x"
    buildings: list[str] = field(default_factory=list)
    hp: int = 0
    focus: str = "balanced"
    connected: bool = False
    bombarded: bool = False  # has used its ranged attack this turn
    damage_by: dict[str, int] = field(default_factory=dict)  # damage dealt to it, by player
    liberated_turn: int | None = None  # last turn players freed it (alien retake target)
    besieged: bool = False  # took damage this turn, so it does not heal at turn end
    yield_carry: dict[str, int] = field(default_factory=dict)  # hundredths carried (citizens)


@dataclass
class Job:
    improvement: str
    turns_left: int
    tile: int | None = None  # where it is built, if not the unit's own hex (a sea bridge)


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
    xp: int = 0  # combats fought (attacking or attacked); see beacon/promotions.py
    promotions: list[str] = field(default_factory=list)
    gear: list[str] = field(default_factory=list)  # weapon and armour found (SPEC_M14)


@dataclass
class CityMemory:
    """What a player last saw of a city."""

    status: str
    owner: str | None
    pop: int
    turn_seen: int


@dataclass
class Leader:
    """A player's leader (docs/SPEC_M11.md): the head of the council, not a unit on the map. Age,
    XP and level follow from the turn and the player's achievements (beacon/leader.py)."""

    name: str
    sex: str  # man | woman
    look: str  # id in data/leaders.yaml looks
    start_age: int
    skills: dict[str, int]  # domain -> value; each starts at +1
    traits: list[str]
    level: int = 1
    spent: int = 0  # skill points spent so far (one per level gained)
    milestones: list[str] = field(default_factory=list)  # "<milestone>:<threshold>" reached
    choices: list[str] = field(default_factory=list)  # waiting: "<milestone>:<threshold>"/"trait"
    bonuses: list[str] = field(default_factory=list)  # "<milestone>:<option>" chosen
    outfit: str = "civilian"
    accessories: list[str] = field(default_factory=list)
    children: list[int] = field(default_factory=list)  # citizen ids, oldest first
    expecting: str | None = None  # "citizen:<id>" or "recruit:<id>": the child on the way
    due: int = -1  # turn the child is born
    rest_until: int = -1  # no new family before this turn (the cooldown after a birth)
    custom: bool = False  # made on the creation screen


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
    controller: str = "ai"  # ai | human
    character: str | None = None  # AI character (data/ai.yaml)
    allies: list[str] = field(default_factory=list)
    met: list[str] = field(default_factory=list)  # players met so far (beacon/contact.py)
    boons: list[dict[str, Any]] = field(default_factory=list)  # shard effects (like tech effects)
    flags: list[str] = field(default_factory=list)  # story choices remembered
    leader: Leader | None = None  # docs/SPEC_M11.md
    intel: list[int] = field(default_factory=list)  # alien cities whose contents are known (M12)
    influence_adjust: int = 0  # influence spent (-) and pledges (+/-) (SPEC_M13)
    agenda: str | None = None  # the leader's public agenda (data/council.yaml)
    objective: str | None = None  # secret objective (only its owner sees it)
    times_chair: int = 0
    temp_effects: list[dict[str, Any]] = field(default_factory=list)  # council measures in force
    founded: bool = True  # False in the survivor era, until the first town is taken (SPEC_M14)
    scrap: int = 0  # salvage carried by the band; production in the first city
    band_home: int | None = None  # the band's starting hex (where a fallen leader escapes to)
    band_town: int | None = None  # the band's first town (city id)
    band_claimed: bool = False  # the band has found its first town (designer 2026-11-17)
    band_finds: int = 0  # weapons, armour and survivors the band has found


@dataclass
class DealTerms:
    """What one side gives in a deal (docs/SPEC_M6.md)."""

    gold: int = 0
    gold_per_turn: int = 0
    resources: dict[str, int] = field(default_factory=dict)  # strategic units lent
    techs: list[str] = field(default_factory=list)
    recruits: list[int] = field(default_factory=list)
    units: list[int] = field(default_factory=list)
    alliance: bool = False


@dataclass
class Deal:
    id: int
    proposer: str
    receiver: str
    give: DealTerms  # from proposer to receiver
    take: DealTerms  # from receiver to proposer
    duration: int
    proposed_turn: int
    active: bool = False
    ends_turn: int | None = None


@dataclass
class Shipment:
    """Goods or a unit at sea, or goods waiting for their convoy to reach a port."""

    id: int
    from_player: str
    to_player: str
    techs: list[str] = field(default_factory=list)
    recruits: list[int] = field(default_factory=list)
    unit: Unit | None = None
    dest_city: int | None = None
    arrive_turn: int | None = None  # None while the convoy is still overland
    convoy: int | None = None  # convoy unit id


@dataclass
class Recruit:
    """An alien character called by beacons (docs/SPEC_M5.md)."""

    id: int
    name: str
    kind: str  # recruit type id, or legendary id
    legendary: bool
    scores: dict[str, int]  # domain -> percent bonus while seated (traits already applied)
    traits: list[str]
    born: int
    lifespan: int | None  # None: immortal
    patron: str | None  # player id; None once it has betrayed
    alien_city: int | None = None  # the alien city it joined on betrayal
    seats: list[str] = field(default_factory=list)  # "general" or domains


@dataclass
class Citizen:
    """One person of a player's city (designer 2026-11-14). Born a child, grows up, then works an
    improved tile (half its stats added there) or sits on the council (full stats to its city)."""

    id: int
    city: int
    name: str
    stats: dict[str, int]  # domain -> points (6 in all)
    traits: list[str]
    born: int
    growth: int = 0  # points toward adulthood
    adult: bool = False
    job: str = "auto"  # "auto", "council" or "tile:<index>" (the player's choice)
    tile: int | None = None  # the tile it works now (set by citizens.assign)
    seats: list[str] = field(default_factory=list)  # council seat held now ("general"/a domain)
    kin: bool = False  # a child of the leader (SPEC_M11)
    hybrid: bool = False  # a child of the leader and an alien recruit
    banned_until: int = -1  # voted off the council: no seat before this turn


@dataclass
class StoryEvent:
    """An event waiting for its player's choice (docs/SPEC_M9.md)."""

    id: int
    event: str  # id in data/story.yaml events
    player: str
    turn: int
    tile: int | None = None  # where it happened


@dataclass
class Site:
    """An exploration find hidden in the fog, collected by the first player unit to reach it."""

    id: int
    tile: int
    kind: str  # an event id in data/story.yaml
    found_by: str | None = None


@dataclass
class Shard:
    """A deep-space shard: warned, then landed, then mined (Starfall, docs/SPEC_M9.md)."""

    id: int
    kind: str
    tile: int
    warn_turn: int
    impact_turn: int
    cone_center: int
    cone_radius: int
    progress: dict[str, int] = field(default_factory=dict)  # miner (player id or aliens) -> turns
    claimed_by: str | None = None
    claimed_turn: int | None = None
    remnant: bool = False  # placed at the start, waiting to be found (SPEC_M10)


@dataclass
class Offer:
    id: int
    recruit: int
    from_player: str
    to_player: str
    price: int
    turn: int


@dataclass
class AlienOrder:
    kind: str  # siege | raid | patrol | hunt | mine | escort
    target: int  # tile (hunt: the hunted unit's id)


@dataclass
class AlienPlan:
    """An announced alien strike (SPEC_M12): units gather, then besiege `target` at `launch`."""

    id: int
    target: int  # the player city's tile
    player: str  # its owner when announced
    source: int  # where the strike gathers
    launch: int  # turn the siege begins
    units: list[int] = field(default_factory=list)


@dataclass
class Measure:
    """A measure before the council (SPEC_M13)."""

    id: int
    kind: str  # id in data/council.yaml measures
    proposer: str | None = None  # None: drawn by the council
    target: int | None = None  # joint strike: the alien city id
    votes: dict[str, str] = field(
        default_factory=dict
    )  # player -> yes | no | abstain | <candidate>
    extra: dict[str, int] = field(default_factory=dict)  # extra votes bought, by player


@dataclass
class CouncilState:
    sessions: int = 0
    measures: list[Measure] = field(default_factory=list)  # the open session (votes this turn)
    proposals: list[Measure] = field(default_factory=list)  # waiting for the next session
    active: list[dict[str, Any]] = field(default_factory=list)  # passed measures in force
    chair: str | None = None
    results: list[dict[str, Any]] = field(default_factory=list)  # the last session's outcomes


@dataclass
class AlienState:
    progress: int = 0
    techs: list[str] = field(default_factory=list)
    reinforcement_store: int = 0
    surge_cooldown: int = 0
    start_cities: int = 0
    orders: dict[str, AlienOrder] = field(default_factory=dict)  # by unit id
    mothership_alive: bool = True
    reinforcements_stopped: bool = False  # once the barrage is researched (DESIGN.md 11)
    plans: dict[str, AlienPlan] = field(default_factory=dict)  # announced strikes (SPEC_M12)


@dataclass
class Project:
    """A shared project: the world barrage or an espionage operation (docs/SPEC_M7.md)."""

    id: int
    kind: str  # barrage | espionage
    starter: str
    mode: str  # shared | solo
    started_turn: int
    cost: int
    progress: int = 0
    host_city: int | None = None  # barrage only
    contributions: dict[str, int] = field(default_factory=dict)
    done: bool = False
    offered: list[str] = field(default_factory=list)  # espionage: alien techs on offer
    chooser: str | None = None
    choose_by: int | None = None


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
    council: CouncilState = field(default_factory=CouncilState)  # SPEC_M13
    caches: dict[str, str] = field(default_factory=dict)  # tile -> loot (survivor start, M14)
    recruits: dict[str, Recruit] = field(default_factory=dict)
    citizens: dict[str, Citizen] = field(default_factory=dict)
    story_events: dict[str, StoryEvent] = field(default_factory=dict)
    sites: dict[str, Site] = field(default_factory=dict)
    shards: dict[str, Shard] = field(default_factory=dict)
    next_shard_turn: int = -1  # -1: not scheduled yet
    offers: dict[str, Offer] = field(default_factory=dict)
    deals: dict[str, Deal] = field(default_factory=dict)
    shipments: dict[str, Shipment] = field(default_factory=dict)
    projects: dict[str, Project] = field(default_factory=dict)
    outcome: str | None = None  # victory | defeat (no turn limit)
    outcome_turn: int | None = None
    exchange: dict[str, int] = field(default_factory=dict)  # Galactic Exchange index % (M17)
    wrap: bool = False  # the map wraps east to west (SPEC_M10); hexgrid.set_wrap registers it
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
        return sorted((u for u in self.units.values() if u.tile == tile), key=lambda u: u.id)

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

    from beacon import hexgrid

    state = from_dict(GameState, json.loads(text))
    if state.wrap:
        hexgrid.set_wrap(state.width)
    return state


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
