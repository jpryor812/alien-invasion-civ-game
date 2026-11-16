"""Works: buildings, walls and tile works built by a city's engineers (docs/SPEC_M17.md).

Ordering a work pays its materials at once. Each turn the city's crew puts `per_engineer` labour
apiece into its works in order: the first takes what it needs and the rest passes on, so a work's
turns are the labour left before and in it over the crew's labour a turn. Cancelling refunds.
"""

from __future__ import annotations

from typing import Any

from beacon import economy, fog, layout, materials, techfx
from beacon.config import Config
from beacon.state import City, GameState

Events = list[dict[str, Any]]


def W(cfg: Config, path: str) -> Any:  # noqa: N802 - short accessor
    return cfg.materials(path)


# -- the crew -------------------------------------------------------------------------------------


def ensure_crew(cfg: Config, city: City, start: int | None = None) -> None:
    """A city's first crew: `start` if given, else the capital or ordinary start."""
    if city.engineers < 0:
        if start is None:
            start = W(cfg, "labour.capital_start" if city.is_capital else "labour.start")
        city.engineers = start


def crew(city: City) -> int:
    return max(0, city.engineers)


def rate(state: GameState, cfg: Config, city: City) -> int:
    """Labour the crew puts in a turn (Robotics and the Builder trait add labour_pct)."""
    pct = techfx.total(cfg, state.players.get(city.owner or ""), "labour_pct")
    return crew(city) * W(cfg, "labour.per_engineer") * (100 + pct) // 100


def engineer_cost(cfg: Config, city: City) -> int:
    """Production to train one more engineer."""
    return W(cfg, "engineers.cost") + W(cfg, "engineers.cost_step") * crew(city)


# -- labour each work needs -----------------------------------------------------------------------


def building_labour(cfg: Config, b: str) -> int:
    return max(1, cfg.buildings[b]["cost"] * W(cfg, "labour.building_pct") // 100)


def wall_labour(cfg: Config, cells: list[list[Any]]) -> int:
    per = W(cfg, "labour.per_wall")
    return max(1, sum(W(cfg, f"walls.{m}.production") * per for _, _, m in cells))


def tile_labour(state: GameState, cfg: Config, city: City, improvement: str) -> int:
    turns = cfg.improvements[improvement]["turns"]
    turns += techfx.total(cfg, state.players.get(city.owner or ""), "build_turns")
    return max(1, turns) * W(cfg, "labour.per_engineer")


# -- the list of works ----------------------------------------------------------------------------


def _new_id(city: City) -> int:
    return max((w["id"] for w in city.works), default=0) + 1


def add(city: City, what: str, labour: int, paid: dict[str, int], **extra: Any) -> dict[str, Any]:
    job = {"id": _new_id(city), "what": what, "left": labour, "total": labour, "paid": paid}
    job.update(extra)
    city.works.append(job)
    return job


def ordered(city: City, what: str) -> dict[str, Any] | None:
    return next((w for w in city.works if w["what"] == what), None)


def tile_ordered(city: City, tile: int) -> dict[str, Any] | None:
    return next(
        (w for w in city.works if w["what"].startswith("tile:") and w["tile"] == tile), None
    )


def short_text(lack: dict[str, int]) -> str:
    return "needs " + ", ".join(f"{n} more {g}" for g, n in sorted(lack.items()))


def turns(state: GameState, cfg: Config, city: City) -> list[int | None]:
    """Turns until each work is done (None: no crew)."""
    r = rate(state, cfg, city)
    out: list[int | None] = []
    left = 0
    for w in city.works:
        left += w["left"]
        out.append(-(-left // r) if r > 0 else None)
    return out


# -- ordering -------------------------------------------------------------------------------------


def building_problem(state: GameState, cfg: Config, city: City, b: str) -> str | None:
    if b not in cfg.buildings:
        return f"unknown building {b!r}"
    why = economy.building_allowed(state, cfg, city, b)
    if why:
        return why
    if ordered(city, f"building:{b}"):
        return "already being built"
    lack = materials.short(city, materials.building_cost(cfg, b))
    return short_text(lack) if lack else None


def order_building(
    state: GameState, cfg: Config, city: City, b: str, spot: tuple[int, int] | None = None
) -> dict[str, Any]:
    """Pay and order a building (the caller checked building_problem); placed at `spot` or at
    the free spot nearest the centre."""
    if spot is None:
        spot = layout.auto_spot(state, cfg, city, b)
    if spot is not None:
        layout.order(cfg, city, b, spot[0], spot[1])
    cost = materials.building_cost(cfg, b)
    materials.pay(city, cost)
    return add(city, f"building:{b}", building_labour(cfg, b), cost)


def order_walls(
    state: GameState, cfg: Config, city: City, cells: list[tuple[int, int]], material: str
) -> dict[str, Any] | None:
    """Pay for and order the new pieces (cells already ordered are skipped)."""
    taken = {(o[0], o[1]) for o in city.wall_orders}
    new = [[x, y, material] for x, y in cells if (x, y) not in taken]
    if not new:
        return None
    cost: dict[str, int] = {}
    for g, n in W(cfg, f"walls.{material}.cost").items():
        cost[g] = n * len(new)
    materials.pay(city, cost)
    city.wall_orders = [*city.wall_orders, *new]
    return add(city, "walls", wall_labour(cfg, new), cost, cells=new)


def walls_cost(cfg: Config, n: int, material: str) -> dict[str, int]:
    return {g: k * n for g, k in W(cfg, f"walls.{material}.cost").items()}


def order_tile(
    state: GameState, cfg: Config, city: City, tile: int, improvement: str
) -> dict[str, Any]:
    return add(
        city,
        f"tile:{improvement}",
        tile_labour(state, cfg, city, improvement),
        {},
        tile=tile,
        improvement=improvement,
    )


def cancel(cfg: Config, city: City, work_id: int) -> dict[str, Any] | None:
    job = next((w for w in city.works if w["id"] == work_id), None)
    if job is None:
        return None
    city.works.remove(job)
    for g, n in job["paid"].items():
        city.stores[g] = city.stores.get(g, 0) + n  # refunds may pass the cap
    if job["what"].startswith("building:"):
        b = job["what"].split(":", 1)[1]
        city.layout = [e for e in city.layout if e["done"] or e["what"] != b]
    elif job["what"] == "walls":
        gone = {(x, y) for x, y, _ in job["cells"]}
        city.wall_orders = [o for o in city.wall_orders if (o[0], o[1]) not in gone]
    return job


# -- each turn ------------------------------------------------------------------------------------


def _finish(state: GameState, cfg: Config, city: City, job: dict[str, Any]) -> dict[str, Any]:
    what = job["what"]
    if what.startswith("building:"):
        b = what.split(":", 1)[1]
        if b not in city.buildings:
            city.buildings = sorted([*city.buildings, b])
        layout.complete(state, cfg, city, b)
        hp = cfg.buildings[b].get("city_hp", 0)
        city.hp = min(economy.max_hp(cfg, city), city.hp + hp)
        return {"kind": "building_completed", "city": city.id, "building": b}
    if what == "walls":
        gained = 0
        for x, y, m in job["cells"]:
            city.walls[f"{x},{y}"] = m
            gained += W(cfg, f"walls.{m}.hp")
        done = {(x, y) for x, y, _ in job["cells"]}
        city.wall_orders = [o for o in city.wall_orders if (o[0], o[1]) not in done]
        city.hp = min(economy.max_hp(cfg, city), city.hp + gained)
        return {"kind": "walls_built", "city": city.id, "pieces": len(job["cells"])}
    tile = state.tiles[job["tile"]]
    tile.improvement = job["improvement"]
    if tile.pillaged == job["improvement"]:
        tile.pillaged = None
    tile.built_by = city.owner
    fog.touch_built(state)
    return {
        "kind": "improvement_built",
        "city": city.id,
        "tile": job["tile"],
        "improvement": job["improvement"],
    }


def progress(state: GameState, cfg: Config, city: City) -> Events:
    """One turn of the crew's labour."""
    ensure_crew(cfg, city)
    r = rate(state, cfg, city)
    events: Events = []
    while r > 0 and city.works:
        job = city.works[0]
        use = min(r, job["left"])
        job["left"] -= use
        r -= use
        if job["left"] > 0:
            break
        city.works.pop(0)
        events.append(_finish(state, cfg, city, job))
    return events


def upkeep(state: GameState, cfg: Config, pid: str) -> int:
    from beacon.state import ACTIVE

    n = sum(crew(c) for c in state.cities if c.owner == pid and c.status == ACTIVE)
    return n * W(cfg, "engineers.upkeep")
