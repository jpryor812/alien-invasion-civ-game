"""World generation from real geography (docs/SPEC_M0-M3.md, M1; designer 2026-11-14).

Each continent is drawn from its real outline, fitted into its own region of the map and
separated from the others by ocean. Climate zones, mountain ranges and cities come from
`data/continents.yaml`; the seed varies forests, hills, resources and which lost cities are
dormant, ruined or held by aliens.
"""

from __future__ import annotations

import random

from beacon import hexgrid, rng
from beacon.config import Config
from beacon.paths import reachable, shortest_path
from beacon.state import ACTIVE, City, Tile
from beacon.tiles import is_passable_land, is_water, move_cost


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


# Hex centres in a fixed-point plane: x in thousandths of half a hex width, y in thousandths of a
# hex width, so a row is ~1732 (sqrt(3)/2 x 2000) below the one above. Integer maths only.
_COL = 2000
_HALF = 1000
_ROW = 1732


def _region(cfg: Config, box: list[int]) -> tuple[int, int, int, int]:
    """Interior bounds (col0, col1, row0, row1), half-open, of a continent's box."""
    col0, row0, col1, row1 = box
    if not (0 <= col0 < col1 <= cfg.t("map.width") and 0 <= row0 < row1 <= cfg.t("map.height")):
        raise ValueError(f"continent box {box} does not fit the map")
    margin = cfg.t("map.ocean_margin")
    return col0 + margin, col1 - margin, row0 + margin, row1 - margin


def _centre(i: int, width: int) -> tuple[int, int]:
    col, row = hexgrid.col_row(i, width)
    return col * _COL + (row & 1) * _HALF, row * _ROW


class _Projection:
    """Fits a continent's lon/lat shapes into its region, keeping proportions."""

    def __init__(self, cfg: Config, cid: str):
        geo = cfg.continents[cid]["geo"]
        self.xs = geo["x_scale_pct"]
        pts = [p for shape in [geo["outline"], *geo["islands"]] for p in shape]
        self.x0 = min(p[0] for p in pts) * self.xs
        x1 = max(p[0] for p in pts) * self.xs
        y0 = min(p[1] for p in pts) * 100
        self.y1 = max(p[1] for p in pts) * 100
        span_x, span_y = max(1, x1 - self.x0), max(1, self.y1 - y0)
        col0, col1, row0, row1 = _region(cfg, geo["box"])
        room_x, room_y = (col1 - col0 - 1) * _COL, (row1 - row0 - 1) * _ROW
        if room_x * span_y <= room_y * span_x:
            num, den = room_x, span_x
        else:
            num, den = room_y, span_y
        self.num, self.den = num * geo["size_pct"], den * 100
        self.ox = col0 * _COL + (room_x - span_x * self.num // self.den) // 2
        self.oy = row0 * _ROW + (room_y - span_y * self.num // self.den) // 2

    def point(self, lon: int, lat: int) -> tuple[int, int]:
        return (
            self.ox + (lon * self.xs - self.x0) * self.num // self.den,
            self.oy + (self.y1 - lat * 100) * self.num // self.den,
        )

    def shape(self, pts: list[list[int]]) -> list[tuple[int, int]]:
        return [self.point(lon, lat) for lon, lat in pts]


def _inside(x: int, y: int, poly: list[tuple[int, int]]) -> bool:
    """Even-odd ray test, integers only."""
    hit = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y):
            # x < xi + (y - yi) * (xj - xi) / (yj - yi), multiplied through by (yj - yi)
            lhs = (x - xi) * (yj - yi)
            rhs = (y - yi) * (xj - xi)
            if (lhs < rhs) if yj > yi else (lhs > rhs):
                hit = not hit
        j = i
    return hit


def _nearest_hex(w: World, x: int, y: int) -> int:
    row = max(0, min(w.height - 1, (y + _ROW // 2) // _ROW))
    best = None
    for r in (row - 1, row, row + 1):
        if not 0 <= r < w.height:
            continue
        col = max(0, min(w.width - 1, (x - (r & 1) * _HALF + _HALF) // _COL))
        for c in (col - 1, col, col + 1):
            if not 0 <= c < w.width:
                continue
            i = hexgrid.index(c, r, w.width)
            cx, cy = _centre(i, w.width)
            key = ((cx - x) ** 2 + (cy - y) ** 2, i)
            if best is None or key < best:
                best = key
    assert best is not None
    return best[1]


def _components(w: World, tiles: set[int]) -> list[list[int]]:
    seen: set[int] = set()
    out = []
    for t in sorted(tiles):
        if t in seen:
            continue
        comp = reachable(t, w.nbrs, tiles.__contains__)
        seen |= comp
        out.append(sorted(comp))
    return sorted(out, key=lambda c: (-len(c), c[0]))


def _causeway(w: World, island: list[int], main: set[int], allowed: set[int]) -> list[int]:
    """Shortest run of water hexes joining an island to the main landmass."""
    frontier = list(island)
    came: dict[int, int | None] = {t: None for t in island}
    while frontier:
        nxt = []
        for t in frontier:
            for n in w.nbrs(t):
                if n in came or (n not in allowed and n not in main):
                    continue
                came[n] = t
                if n in main:
                    path = []
                    step = came[n]
                    while step is not None and step not in island:
                        path.append(step)
                        step = came[step]
                    return path
                nxt.append(n)
        frontier = nxt
    raise ValueError("an island cannot reach the main landmass")


def _draw_land(w: World, cid: str, proj: _Projection) -> list[int]:
    cfg = w.cfg
    geo = cfg.continents[cid]["geo"]
    col0, col1, row0, row1 = _region(cfg, geo["box"])
    area = [hexgrid.index(c, r, w.width) for r in range(row0, row1) for c in range(col0, col1)]
    shapes = [proj.shape(geo["outline"]), *(proj.shape(p) for p in geo["islands"])]
    lakes = [proj.shape(p) for p in geo["lakes"]]
    land = set()
    for i in area:
        x, y = _centre(i, w.width)
        if any(_inside(x, y, s) for s in shapes) and not any(_inside(x, y, s) for s in lakes):
            land.add(i)
    comps = _components(w, land)
    main = set(comps[0])
    for comp in comps[1:]:
        if len(comp) < cfg.t("map.min_island_tiles"):
            continue
        water = set(area) - land
        main |= set(comp) | set(_causeway(w, comp, main, water))
    for i in main:
        w.tiles[i].terrain = "grassland"
        w.tiles[i].continent = cid
    return sorted(main)


def _paint_biomes(w: World, cid: str, land: list[int], proj: _Projection, r: random.Random) -> None:
    cfg = w.cfg
    seeds = [
        (b, _nearest_hex(w, *proj.point(lon, lat)))
        for b, lon, lat in cfg.continents[cid]["geo"]["biome_seeds"]
    ]
    blend = cfg.t("map.biome_blend_pct")
    for i in land:
        ranked = sorted(range(len(seeds)), key=lambda s: (w.dist(i, seeds[s][1]), s))
        pick = ranked[0]
        if len(ranked) > 1 and rng.percent_roll(r, blend):
            second = ranked[1]
            if w.dist(i, seeds[second][1]) - w.dist(i, seeds[pick][1]) <= 1:
                pick = second
        biome = cfg.biomes[seeds[pick][0]]
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


def _ridge_tiles(w: World, proj: _Projection, pts: list[list[int]]) -> list[int]:
    out: list[int] = []
    xy = proj.shape(pts)
    for (ax, ay), (bx, by) in zip(xy, xy[1:], strict=False):
        steps = max(1, (abs(bx - ax) + abs(by - ay)) // _HALF)
        for k in range(steps + 1):
            t = _nearest_hex(w, ax + (bx - ax) * k // steps, ay + (by - ay) * k // steps)
            if not out or out[-1] != t:
                out.append(t)
    return out


def _raise_ridges(
    w: World, cid: str, land: list[int], proj: _Projection, keep: set[int], r: random.Random
) -> None:
    """Mountain ranges and hill country along the continent's ridges. Mountains never cut the
    passable land in two and never sit on or next to a city site."""
    cfg = w.cfg
    land_set = set(land)
    flank = cfg.t("map.ridge_flank_hill_pct")

    def passable_connected() -> bool:
        passable = [i for i in land if is_passable_land(cfg, w.tiles[i])]
        allowed = set(passable)
        return len(reachable(passable[0], w.nbrs, allowed.__contains__)) == len(passable)

    for ridge in cfg.continents[cid]["geo"]["ridges"]:
        for t in _ridge_tiles(w, proj, ridge["points"]):
            if t not in land_set or t in keep:
                continue
            tile = w.tiles[t]
            if ridge["kind"] == "hills":
                tile.elevation = "hills"
                continue
            if tile.elevation == "mountain":
                continue
            old = (tile.elevation, tile.feature)
            tile.elevation, tile.feature = "mountain", None
            if not passable_connected():
                tile.elevation, tile.feature = old
                continue
            for n in w.nbrs(t):
                if n in land_set and w.tiles[n].elevation == "flat" and rng.percent_roll(r, flank):
                    w.tiles[n].elevation = "hills"


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


def _city_sites(w: World, cid: str, land: list[int], proj: _Projection) -> list[int]:
    """Each city sits on the hex of its real location, or the nearest open land hex."""
    cfg = w.cfg
    open_land = [i for i in land if is_passable_land(cfg, w.tiles[i])]
    sites: list[int] = []
    for city in cfg.continents[cid]["cities"]:
        x, y = proj.point(city["lon"], city["lat"])
        spot = min(
            (i for i in open_land if i not in sites),
            key=lambda i: (
                (_centre(i, w.width)[0] - x) ** 2 + (_centre(i, w.width)[1] - y) ** 2,
                i,
            ),
        )
        sites.append(spot)
    return sites


def _connect(w: World, a: int, b: int) -> None:
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
            w.tiles[t].route = "road"  # unowned: it shows only where the map is explored


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


def _lost_quota(states: list[str], weights: list[int], n: int) -> list[str]:
    """Exactly n lost-city states in proportion to the weights (largest remainder), so every
    continent starts with about the same alien share."""
    total = sum(weights)
    counts = [n * wt // total for wt in weights]
    remainders = sorted(range(len(states)), key=lambda i: (-(n * weights[i] % total), states[i]))
    for i in remainders[: n - sum(counts)]:
        counts[i] += 1
    return [s for s, c in zip(states, counts, strict=True) for _ in range(c)]


def _make_cities(w: World, cid: str, sites: list[int]) -> None:
    cfg = w.cfg
    names = [c["name"] for c in cfg.continents[cid]["cities"]]
    known_n = cfg.t("cities.known_count")
    pops = cfg.t("cities.start_pop")
    lost = cfg.t("cities.lost_state_weights")
    states = sorted(lost)
    r = rng.stream(w.seed, "cities", cid)
    start_buildings = cfg.t("cities.start_buildings")
    lost_states = _lost_quota(states, [lost[s] for s in states], max(0, len(sites) - known_n))
    r.shuffle(lost_states)
    for k, tile in enumerate(sites):
        if k < known_n:
            status, role = ACTIVE, ("capital" if k == 0 else "known")
        else:
            status = lost_states[k - known_n]
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
    lands, sites = {}, {}
    for cid in ordered:
        r = rng.stream(seed, "map", cid)
        proj = _Projection(cfg, cid)
        land = _draw_land(w, cid, proj)
        _paint_biomes(w, cid, land, proj, r)
        sites[cid] = _city_sites(w, cid, land, proj)
        keep = {n for s in sites[cid] for n in hexgrid.within(s, 1, w.width, w.height)}
        _raise_ridges(w, cid, land, proj, keep, r)
        lands[cid] = land
    _mark_coast(w)
    for cid in ordered:
        r = rng.stream(seed, "map", cid, "resources")
        _place_resources(w, cid, r)
    for cid in ordered:
        _make_cities(w, cid, sites[cid])
    for cid in ordered:
        mine = [c for c in w.cities if c.continent == cid]
        capital = next(c for c in mine if c.is_capital)
        for city in mine:
            if city.status == ACTIVE and not city.is_capital:
                _connect(w, capital.tile, city.tile)
    _assign_work_areas(w)
    return w.tiles, w.cities
