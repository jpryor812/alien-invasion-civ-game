"""Procedural, Earth-flavoured world generation (docs/SPEC_M0-M3.md, M1).

Each continent sits in its own region of the map, separated by ocean. Its shape is a seeded blob;
its climate, resources and city names come from `data/continents.yaml`.
"""

from __future__ import annotations

import random

from beacon import hexgrid, rng
from beacon.config import Config
from beacon.paths import reachable, shortest_path
from beacon.state import ACTIVE, City, Tile
from beacon.tiles import is_passable_land, is_water, move_cost, potential_yields


class World:
    """Tiles and cities under construction."""

    def __init__(self, cfg: Config, seed: int):
        self.cfg = cfg
        self.seed = seed
        self.width = cfg.t("map.width")
        self.height = cfg.t("map.height")
        self.tiles = [Tile(terrain="ocean") for _ in range(self.width * self.height)]
        self.cities: list[City] = []

    def nbrs(self, i: int) -> tuple[int, ...]:
        return hexgrid.neighbours(i, self.width, self.height)

    def dist(self, a: int, b: int) -> int:
        return hexgrid.distance(a, b, self.width)


def _region(cfg: Config, order: int) -> tuple[int, int, int, int]:
    """Interior bounds (col0, col1, row0, row1), half-open, of a continent's region."""
    cols, rows = cfg.t("map.region_cols"), cfg.t("map.region_rows")
    if order >= cols * rows:
        raise ValueError(f"continent order {order} has no map region ({cols}x{rows} regions)")
    rw, rh = cfg.t("map.width") // cols, cfg.t("map.height") // rows
    margin = cfg.t("map.ocean_margin")
    c, r = order % cols, order // cols
    return c * rw + margin, (c + 1) * rw - margin, r * rh + margin, (r + 1) * rh - margin


def _grow_land(w: World, cid: str, r: random.Random) -> list[int]:
    cfg = w.cfg
    col0, col1, row0, row1 = _region(cfg, cfg.continents[cid]["order"])

    def inside(i: int) -> bool:
        col, row = hexgrid.col_row(i, w.width)
        return col0 <= col < col1 and row0 <= row < row1

    interior = (col1 - col0) * (row1 - row0)
    target = cfg.t("map.land_tiles") * cfg.continents[cid]["land_pct"] // 100
    target = min(target, interior)
    base, power = cfg.t("map.blob_weight_base"), cfg.t("map.blob_weight_power")

    centre = hexgrid.index((col0 + col1) // 2, (row0 + row1) // 2, w.width)
    land = {centre}
    counts: dict[int, int] = {}
    for n in w.nbrs(centre):
        if inside(n):
            counts[n] = 1
    while len(land) < target and counts:
        cands = sorted(counts)
        pick = rng.weighted_choice(r, cands, [base + counts[c] ** power for c in cands])
        land.add(pick)
        del counts[pick]
        for n in w.nbrs(pick):
            if inside(n) and n not in land:
                counts[n] = counts.get(n, 0) + 1
    for i in land:
        w.tiles[i].terrain = "grassland"
        w.tiles[i].continent = cid
    return sorted(land)


def _paint_biomes(w: World, cid: str, land: list[int], r: random.Random) -> None:
    cfg = w.cfg
    weights = cfg.continents[cid]["biomes"]
    names = sorted(b for b in weights if weights[b] > 0)
    k = min(cfg.t("map.biome_seeds"), len(land))
    seeds = r.sample(land, k)
    seed_biomes = [rng.weighted_choice(r, names, [weights[n] for n in names]) for _ in seeds]
    for i in land:
        best = min(range(k), key=lambda s: (w.dist(i, seeds[s]), s))
        biome = cfg.biomes[seed_biomes[best]]
        tile = w.tiles[i]
        tile.terrain = biome["terrain"]
        roll = r.randrange(100)
        cumulative = 0
        for feature in sorted(biome["features"]):
            cumulative += biome["features"][feature]
            if roll < cumulative:
                if tile.terrain in cfg.features[feature]["allowed_terrains"]:
                    tile.feature = feature
                break
        if rng.percent_roll(r, cfg.t("map.hill_pct")):
            tile.elevation = "hills"


def _raise_mountains(w: World, land: list[int], r: random.Random) -> None:
    cfg = w.cfg

    def passable_connected() -> bool:
        passable = [i for i in land if is_passable_land(cfg, w.tiles[i])]
        if not passable:
            return False
        allowed = set(passable)
        return len(reachable(passable[0], w.nbrs, allowed.__contains__)) == len(passable)

    for _ in range(cfg.t("map.mountain_ranges")):
        here = r.choice(land)
        for _ in range(cfg.t("map.mountain_range_length")):
            tile = w.tiles[here]
            if tile.elevation != "mountain":
                old = (tile.elevation, tile.feature)
                tile.elevation, tile.feature = "mountain", None
                if not passable_connected():
                    tile.elevation, tile.feature = old
            options = [n for n in w.nbrs(here) if w.tiles[n].continent == w.tiles[here].continent]
            if not options:
                break
            here = r.choice(sorted(options))


def _mark_coast(w: World) -> None:
    for i, tile in enumerate(w.tiles):
        if tile.terrain != "ocean":
            continue
        for n in w.nbrs(i):
            other = w.tiles[n]
            if not is_water(w.cfg, other):
                tile.terrain = "coast"
                tile.continent = other.continent
                break


def _place_resources(w: World, cid: str, r: random.Random) -> None:
    cfg = w.cfg
    weights = cfg.continents[cid]["resources"]
    for i, tile in enumerate(w.tiles):
        if tile.continent != cid or tile.elevation == "mountain" or tile.terrain == "ocean":
            continue
        if not rng.percent_roll(r, cfg.t("map.resource_pct")):
            continue
        fits = sorted(
            res
            for res, spec in cfg.resources.items()
            if weights.get(res, 0) > 0
            and tile.terrain in spec["terrains"]
            and tile.elevation in spec["elevations"]
        )
        if fits:
            w.tiles[i].resource = rng.weighted_choice(r, fits, [weights[f] for f in fits])


def _site_score(w: World, i: int) -> int:
    cfg = w.cfg
    weights = cfg.t("cities.site_score")
    score = 0
    for t in hexgrid.within(i, cfg.t("cities.work_radius"), w.width, w.height):
        tile = w.tiles[t]
        if tile.terrain == "ocean" and tile.continent is None:
            continue
        if tile.elevation == "mountain":
            continue
        for y, v in potential_yields(cfg, tile).items():
            score += weights[y] * v
    if any(is_water(cfg, w.tiles[n]) for n in w.nbrs(i)):
        score += weights["coastal_bonus"]
    return score


def _place_cities(w: World, cid: str, land: list[int], r: random.Random) -> list[int]:
    """City sites for one continent, known cities first (spread out), then the rest."""
    cfg = w.cfg
    names = cfg.continents[cid]["cities"]
    known_n = min(cfg.t("cities.known_count"), len(names))
    min_d = cfg.t("cities.min_distance")
    cands = [i for i in land if is_passable_land(cfg, w.tiles[i])]
    score = {i: _site_score(w, i) for i in cands}
    ranked = sorted(cands, key=lambda i: (-score[i], i))
    median = score[ranked[len(ranked) // 2]]

    sites = [ranked[0]]
    good = [i for i in ranked if score[i] >= median]
    while len(sites) < known_n:
        best = max(
            good, key=lambda i: (min(w.dist(i, s) for s in sites), score[i], -i), default=None
        )
        if best is None or min(w.dist(best, s) for s in sites) < min_d:
            break
        sites.append(best)

    rest = list(ranked)
    r.shuffle(rest)
    rest.sort(key=lambda i: -score[i])  # stable: shuffle breaks ties
    for i in rest:
        if len(sites) >= len(names):
            break
        if all(w.dist(i, s) >= min_d for s in sites):
            sites.append(i)
    return sites


def _connect(w: World, a: int, b: int, owner: str) -> None:
    """Build a starting road from a to b, avoiding lost-city sites where possible (a road there
    would reveal them, since routes keep their hex in sight)."""
    cfg = w.cfg
    road = cfg.improvements["road"]["move_cost"]
    lost_sites = {c.tile for c in w.cities if c.status != ACTIVE}

    def step_avoiding(_: int, nxt: int) -> int | None:
        if nxt in lost_sites:
            return None
        return step_any(_, nxt)

    def step_any(_: int, nxt: int) -> int | None:
        tile = w.tiles[nxt]
        if not is_passable_land(cfg, tile):
            return None
        return road if tile.route else move_cost(cfg, tile)

    path = shortest_path(a, {b}, w.nbrs, step_avoiding) or shortest_path(a, {b}, w.nbrs, step_any)
    if path is None:
        raise ValueError(f"no land path between tiles {a} and {b}")
    for t in path:
        if w.tiles[t].route is None:
            w.tiles[t].route = "road"
            w.tiles[t].built_by = owner


def _assign_work_areas(w: World) -> None:
    radius = w.cfg.t("cities.work_radius")
    best: dict[int, tuple[int, int]] = {}
    for city in w.cities:
        for t in hexgrid.within(city.tile, radius, w.width, w.height):
            if w.tiles[t].continent != city.continent:
                continue
            key = (w.dist(t, city.tile), city.id)
            if t not in best or key < best[t]:
                best[t] = key
    for t, (_, city_id) in best.items():
        w.tiles[t].city = city_id


def _make_cities(w: World, cid: str, sites: list[int]) -> None:
    cfg = w.cfg
    names = cfg.continents[cid]["cities"]
    known_n = cfg.t("cities.known_count")
    pops = cfg.t("cities.start_pop")
    lost = cfg.t("cities.lost_state_weights")
    states = sorted(lost)
    r = rng.stream(w.seed, "cities", cid)
    start_buildings = cfg.t("cities.start_buildings")
    for k, tile in enumerate(sites):
        if k < known_n:
            status, role = ACTIVE, ("capital" if k == 0 else "known")
        else:
            status = rng.weighted_choice(r, states, [lost[s] for s in states])
            role = status
        city = City(
            id=len(w.cities),
            name=names[k],
            continent=cid,
            tile=tile,
            status=status,
            owner=cid if status == ACTIVE else ("aliens" if status == "overrun" else None),
            pop=pops[role],
            is_capital=(k == 0),
            buildings=sorted(start_buildings.get(role, [])),
        )
        w.cities.append(city)
        w.tiles[tile].feature = None


def generate(cfg: Config, seed: int, continents: list[str]) -> tuple[list[Tile], list[City]]:
    """Tiles and cities for the given continents (in configured order)."""
    w = World(cfg, seed)
    ordered = sorted(continents, key=lambda c: cfg.continents[c]["order"])
    lands = {}
    for cid in ordered:
        r = rng.stream(seed, "map", cid)
        land = _grow_land(w, cid, r)
        _paint_biomes(w, cid, land, r)
        _raise_mountains(w, land, r)
        lands[cid] = land
    _mark_coast(w)
    for cid in ordered:
        r = rng.stream(seed, "map", cid, "resources")
        _place_resources(w, cid, r)
    for cid in ordered:
        r = rng.stream(seed, "map", cid, "cities")
        sites = _place_cities(w, cid, lands[cid], r)
        _make_cities(w, cid, sites)
    for cid in ordered:
        mine = [c for c in w.cities if c.continent == cid]
        capital = next(c for c in mine if c.is_capital)
        for city in mine:
            if city.status == ACTIVE and not city.is_capital:
                _connect(w, capital.tile, city.tile, cid)
    _assign_work_areas(w)
    return w.tiles, w.cities
