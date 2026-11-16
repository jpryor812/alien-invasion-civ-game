"""City layouts on a fine grid (docs/SPEC_M16.md, designer 2026-11-16).

A city's builder area is the land of its work area that it holds. A fine grid covers it:
`cells_per_hex` cells across a hex. Cell (x, y) is in city-local coordinates: its centre lies at
(x, y) x cell size from the city tile's centre, where a hex has circumradius 1 (pointy-top, odd
rows offset), so a cell is sqrt(3) / cells_per_hex wide. Buildings are squares of cells with a gap
between them; walls are single cells. Positions are integers; the geometry that decides which
cells lie inside the territory is computed, never stored.
"""

from __future__ import annotations

import math
from typing import Any

from beacon import hexgrid
from beacon.config import Config
from beacon.state import City, GameState
from beacon.tiles import is_passable_land

Cell = tuple[int, int]
HALL = "city_hall"


def L(cfg: Config, path: str) -> Any:  # noqa: N802 - short accessor
    return cfg.materials(f"layout.{path}")


def cell_size(cfg: Config) -> float:
    return math.sqrt(3) / L(cfg, "cells_per_hex")


def _offset(state: GameState, a: int, b: int) -> tuple[float, float]:
    """Centre of tile b relative to tile a, in hex circumradii (wrap-aware)."""
    w = state.width
    ca, ra = a % w, a // w
    cb, rb = b % w, b // w
    xa = ca * math.sqrt(3) + (ra & 1) * math.sqrt(3) / 2
    xb = cb * math.sqrt(3) + (rb & 1) * math.sqrt(3) / 2
    dx = xb - xa
    if state.wrap:
        span = w * math.sqrt(3)
        dx = (dx + span / 2) % span - span / 2
    return dx, (rb - ra) * 1.5


def _in_hex(px: float, py: float) -> bool:
    ax, ay = abs(px), abs(py)
    return ax <= math.sqrt(3) / 2 + 1e-9 and ay <= 1 - ax / math.sqrt(3) + 1e-9


def territory_tiles(state: GameState, cfg: Config, city: City) -> list[int]:
    radius = cfg.t("cities.work_radius")
    return [
        t
        for t in hexgrid.within(city.tile, radius, state.width, state.height)
        if (t == city.tile or state.tiles[t].city == city.id)
        and is_passable_land(cfg, state.tiles[t])
    ]


def territory(state: GameState, cfg: Config, city: City) -> set[Cell]:
    """Every cell whose centre lies on land the city holds."""
    c = cell_size(cfg)
    out: set[Cell] = set()
    for t in territory_tiles(state, cfg, city):
        ox, oy = _offset(state, city.tile, t)
        x0, x1 = math.floor((ox - 1) / c), math.ceil((ox + 1) / c)
        y0, y1 = math.floor((oy - 1) / c), math.ceil((oy + 1) / c)
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                if _in_hex(x * c - ox, y * c - oy):
                    out.add((x, y))
    return out


def size_of(cfg: Config, what: str) -> int:
    if what == HALL:
        return L(cfg, "hall_size")
    return L(cfg, "sizes").get(what, L(cfg, "default_size"))


def footprint(cfg: Config, what: str, x: int, y: int) -> set[Cell]:
    n = size_of(cfg, what)
    return {(x + i, y + j) for i in range(n) for j in range(n)}


def occupied(cfg: Config, city: City, skip: int | None = None) -> set[Cell]:
    out: set[Cell] = set()
    for e in city.layout:
        if e["id"] != skip:
            out |= footprint(cfg, e["what"], e["x"], e["y"])
    return out


def _with_gap(cells: set[Cell], gap: int) -> set[Cell]:
    return {
        (x + i, y + j) for x, y in cells for i in range(-gap, gap + 1) for j in range(-gap, gap + 1)
    }


def wall_cells(city: City) -> set[Cell]:
    out = {tuple(map(int, k.split(","))) for k in city.walls}
    return out | {(o[0], o[1]) for o in city.wall_orders}


def place_problem(
    state: GameState, cfg: Config, city: City, what: str, x: int, y: int, skip: int | None = None
) -> str | None:
    cells = footprint(cfg, what, x, y)
    if not cells <= territory(state, cfg, city):
        return "it must stand inside the city's land"
    if cells & _with_gap(occupied(cfg, city, skip), L(cfg, "gap")):
        return "too close to another building (keep a gap)"
    if cells & wall_cells(city):
        return "a wall stands there"
    return None


def _spiral(cfg: Config, city: City, state: GameState) -> list[Cell]:
    return sorted(territory(state, cfg, city), key=lambda c: (c[0] ** 2 + c[1] ** 2, c[1], c[0]))


def auto_spot(state: GameState, cfg: Config, city: City, what: str) -> Cell | None:
    """The free spot nearest the centre (top-left cell of the footprint)."""
    n = size_of(cfg, what)
    for cx, cy in _spiral(cfg, city, state):
        x, y = cx - n // 2, cy - n // 2
        if place_problem(state, cfg, city, what, x, y) is None:
            return x, y
    return None


def _new_id(city: City) -> int:
    return max((e["id"] for e in city.layout), default=0) + 1


def ensure(state: GameState, cfg: Config, city: City) -> None:
    """Give a player city its hall and a place for every building it already has."""
    if city.owner not in state.players:
        return
    from beacon import works  # every player city has a crew (SPEC_M17)

    works.ensure_crew(cfg, city)
    pieces = {(x, y) for w in city.works if w["what"] == "walls" for x, y, _ in w["cells"]}
    loose = [o for o in city.wall_orders if (o[0], o[1]) not in pieces]
    if loose:  # pieces ordered before M17 (unpaid then): the crew builds them now
        works.add(city, "walls", works.wall_labour(cfg, loose), {}, cells=[list(o) for o in loose])
    if "walls" in city.queue:
        city.queue = [i for i in city.queue if i != "walls"]
    if not any(e["what"] == HALL for e in city.layout):
        n = size_of(cfg, HALL)
        city.layout.insert(
            0, {"id": _new_id(city), "what": HALL, "x": -(n // 2), "y": -(n // 2), "done": True}
        )
    placed = {e["what"] for e in city.layout}
    for b in city.buildings:
        if b not in placed:
            spot = auto_spot(state, cfg, city, b)
            if spot is not None:
                city.layout.append(
                    {"id": _new_id(city), "what": b, "x": spot[0], "y": spot[1], "done": True}
                )


def pending(city: City, what: str) -> dict[str, Any] | None:
    return next((e for e in city.layout if e["what"] == what and not e["done"]), None)


def order(cfg: Config, city: City, what: str, x: int, y: int) -> dict[str, Any]:
    entry = {"id": _new_id(city), "what": what, "x": x, "y": y, "done": False}
    city.layout.append(entry)
    return entry


def complete(state: GameState, cfg: Config, city: City, what: str) -> None:
    """A building finished: its placed entry stands; unplaced, it goes to the nearest spot."""
    entry = pending(city, what)
    if entry is not None:
        entry["done"] = True
        return
    ensure(state, cfg, city)


def drop_unqueued(city: City) -> None:
    """Placed buildings no longer in the queue lose their place."""
    queued = {i.split(":", 1)[1] for i in city.queue if i.startswith("building:")}
    city.layout = [e for e in city.layout if e["done"] or e["what"] in queued]


# -- walls ----------------------------------------------------------------------------------------


def wall_problem(
    state: GameState, cfg: Config, city: City, cells: list[Cell], material: str
) -> str | None:
    spec = cfg.materials("walls").get(material)
    if spec is None:
        return f"unknown wall {material!r}"
    player = state.players.get(city.owner or "")
    from beacon import tech

    if spec["tech"] and (player is None or not tech.knows(player, spec["tech"])):
        return f"needs tech {spec['tech']}"
    if not cells:
        return "no cells"
    land = territory(state, cfg, city)
    blocked = occupied(cfg, city)
    order_list = list(cfg.materials("walls"))
    for c in cells:
        if c not in land:
            return "walls stand inside the city's land"
        if c in blocked:
            return "a building stands there"
        cur = city.walls.get(f"{c[0]},{c[1]}")
        if cur is not None and order_list.index(cur) >= order_list.index(material):
            return "a wall as strong already stands there"
    return None


def order_walls(city: City, cells: list[Cell], material: str) -> None:
    taken = {(o[0], o[1]) for o in city.wall_orders}
    city.wall_orders = [
        *city.wall_orders,
        *([x, y, material] for x, y in cells if (x, y) not in taken),
    ]


def wall_production(cfg: Config, city: City) -> int:
    return max(1, sum(cfg.materials(f"walls.{m}.production") for _, _, m in city.wall_orders))


def finish_walls(city: City) -> int:
    n = len(city.wall_orders)
    for x, y, m in city.wall_orders:
        city.walls[f"{x},{y}"] = m
    city.wall_orders = []
    return n


def wall_totals(cfg: Config, city: City) -> dict[str, dict[str, int]]:
    """Per material - pieces, strength (whole points), HP."""
    out: dict[str, dict[str, int]] = {}
    for m in city.walls.values():
        row = out.setdefault(m, {"pieces": 0, "tenths": 0, "hp": 0})
        row["pieces"] += 1
        row["tenths"] += cfg.materials(f"walls.{m}.strength")
        row["hp"] += cfg.materials(f"walls.{m}.hp")
    for row in out.values():
        row["strength"] = row.pop("tenths") // 10
    return out


def ai_ring(state: GameState, cfg: Config, city: City) -> list[Cell]:
    """A square ring around the centre, inside the land and clear of buildings."""
    r = L(cfg, "ai_ring")
    land, blocked = territory(state, cfg, city), occupied(cfg, city)
    ring = [(x, y) for x in range(-r, r + 1) for y in range(-r, r + 1) if max(abs(x), abs(y)) == r]
    return [c for c in ring if c in land and c not in blocked]
