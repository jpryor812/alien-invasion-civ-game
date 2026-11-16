"""Hex improvements and routes, built by engineers over several turns."""

from __future__ import annotations

from typing import Any

from beacon import fog, tech, techfx
from beacon.config import Config
from beacon.state import City, GameState, Job, Unit
from beacon.tiles import is_passable_land


def bridge_targets(state: GameState, cfg: Config, unit: Unit) -> list[int]:
    """Shallow water hexes beside the unit where a sea bridge could go (SPEC_M11)."""
    from beacon import hexgrid

    spec = cfg.improvements["sea_bridge"]
    return [
        n
        for n in hexgrid.neighbours(unit.tile, state.width, state.height)
        if state.tiles[n].terrain in spec["terrains"]
        and state.tiles[n].route is None
        and not state.units_at(n)
    ]


def build_problem(
    state: GameState, cfg: Config, unit: Unit, improvement: str, target: int = -1
) -> str | None:
    """None if `unit` may start building `improvement` on its hex (or, for a sea bridge, on the
    shallow water hex `target` beside it), else the reason."""
    if improvement not in cfg.improvements:
        return f"unknown improvement {improvement!r}"
    spec = cfg.improvements[improvement]
    if spec["kind"] == "bridge":
        if not cfg.units[unit.type].get("can_build"):
            return f"{unit.type} cannot build improvements"
        if unit.moves_left <= 0:
            return "no moves left"
        player = state.players.get(unit.owner)
        if player is None or not tech.knows(player, spec["tech"]):
            return f"needs tech {spec['tech']}"
        if not is_passable_land(cfg, state.tiles[unit.tile]):
            return "build a bridge from the shore or from another bridge"
        if target not in bridge_targets(state, cfg, unit):
            return "a sea bridge goes on an empty shallow water hex beside the engineers"
        return None
    if target not in (-1, unit.tile):
        return f"{improvement} is built on the engineers' own hex"
    tile = state.tiles[unit.tile]
    if cfg.units[unit.type].get("can_repair") and not cfg.units[unit.type].get("can_build"):
        if tile.pillaged != improvement:
            return "repair crews only rebuild what aliens pillaged on this hex"
    elif not cfg.units[unit.type].get("can_build"):
        return f"{unit.type} cannot build improvements"
    if unit.moves_left <= 0:
        return "no moves left"
    if spec["kind"] == "tile" and cfg.units[unit.type].get("can_build"):
        return "tile works are ordered from the city (Develop city)"  # SPEC_M17
    return site_problem(state, cfg, unit.owner, unit.tile, improvement)


def site_problem(
    state: GameState, cfg: Config, owner: str, where: int, improvement: str
) -> str | None:
    """The hex-level rules for building `improvement` on `where` for `owner`."""
    spec = cfg.improvements[improvement]
    player = state.players.get(owner)
    if player is None or not tech.knows(player, spec["tech"]):
        return f"needs tech {spec['tech']}"
    tile = state.tiles[where]
    if not is_passable_land(cfg, tile):
        return "not buildable terrain"
    if state.city_at(where) is not None:
        return "city hexes already count as roads"
    if tile.terrain not in spec["terrains"] or tile.elevation not in spec["elevations"]:
        return f"{improvement} cannot go on {tile.elevation} {tile.terrain}"
    if spec["kind"] == "turret":
        if not tile.improvement or tile.built_by != owner:
            return "a turret guards one of your improved tiles (farm, mine...)"
        if tile.turret:
            return "this tile already has a turret"
        return None
    if spec["kind"] == "route":
        if tile.route == improvement:
            return "already built"
        needed = spec.get("requires_route")
        if needed and tile.route != needed:
            return f"needs {needed} first"
    else:
        if tile.improvement == improvement:
            return "already built"
        if spec.get("requires_resource") and (
            tile.resource is None or cfg.resources[tile.resource]["improvement"] != improvement
        ):
            return f"{improvement} needs a resource that uses it"
        if spec.get("requires_feature") and tile.feature not in spec["requires_feature"]:
            return f"{improvement} needs {' or '.join(spec['requires_feature'])}"
    return None


def start_job(
    state: GameState, cfg: Config, unit: Unit, improvement: str, target: int = -1
) -> None:
    turns = cfg.improvements[improvement]["turns"]
    turns += techfx.total(cfg, state.players.get(unit.owner), "build_turns")  # Robotics
    if cfg.units[unit.type].get("can_repair") and state.tiles[unit.tile].pillaged == improvement:
        turns = cfg.t("repair.turns")
    unit.job = Job(
        improvement=improvement,
        turns_left=max(1, turns),
        tile=target if cfg.improvements[improvement]["kind"] == "bridge" else None,
    )
    unit.order = "work"
    unit.moves_left = 0
    unit.acted = True
    unit.fortified = False


def progress_jobs(state: GameState, cfg: Config, pid: str) -> list[dict[str, Any]]:
    events = []
    for unit in state.sorted_units():
        if unit.owner != pid or unit.job is None:
            continue
        unit.job.turns_left -= 1
        if unit.job.turns_left > 0:
            continue
        imp = unit.job.improvement
        where = unit.job.tile if unit.job.tile is not None else unit.tile
        tile = state.tiles[where]
        if cfg.improvements[imp]["kind"] in ("route", "bridge"):
            tile.route = imp
        elif cfg.improvements[imp]["kind"] == "turret":
            from beacon.turrets import build  # turrets imports combat, which imports a lot

            build(tile, cfg)
        else:
            tile.improvement = imp
            if tile.pillaged == imp:
                tile.pillaged = None
        tile.built_by = pid
        fog.touch_built(state)
        unit.job = None
        unit.order = "none"
        events.append(
            {
                "turn": state.turn,
                "kind": "improvement_built",
                "player": pid,
                "tile": where,
                "improvement": imp,
            }
        )
    return events


def auto_improve(state: GameState, cfg: Config, city: City, n: int, owner: str) -> None:
    """Give a city up to `n` improved tiles in its work area (its farmland and mines at the start,
    or what survives when it is liberated). Each picks the improvement with the best balanced
    yield that fits the tile and needs no tech beyond what the owner knows."""
    from beacon.cities import work_tiles  # cities imports nothing from here; keep imports light
    from beacon.tiles import tile_yields

    player = state.players.get(owner)
    weights = cfg.t("economy.focus_weights")["food"]  # farmland first, so the city can eat
    have = sum(1 for t in work_tiles(state, cfg, city) if state.tiles[t].improvement)
    options: list[tuple[int, int, str]] = []
    for t in work_tiles(state, cfg, city):
        tile = state.tiles[t]
        if tile.improvement or not is_passable_land(cfg, tile):
            continue
        best: tuple[int, str] | None = None
        for imp, spec in sorted(cfg.improvements.items()):
            if spec["kind"] != "tile" or not spec["yields"] and not spec.get("requires_resource"):
                continue
            if player is None or not tech.knows(player, spec["tech"]):
                continue
            if tile.terrain not in spec["terrains"] or tile.elevation not in spec["elevations"]:
                continue
            if spec.get("requires_resource") and (
                tile.resource is None or cfg.resources[tile.resource]["improvement"] != imp
            ):
                continue
            tile.improvement = imp
            score = sum(weights[y] * v for y, v in tile_yields(cfg, tile).items())
            tile.improvement = None
            if best is None or score > best[0]:
                best = (score, imp)
        if best is not None and best[0] > 0:
            options.append((-best[0], t, best[1]))
    for _, t, imp in sorted(options)[: max(0, n - have)]:
        state.tiles[t].improvement = imp
        state.tiles[t].built_by = owner
    fog.touch_built(state)


# -- tile works ordered from the city (docs/SPEC_M17.md) -----------------------------------------


def tile_problem(
    state: GameState, cfg: Config, city: City, tile: int, improvement: str
) -> str | None:
    """None if the city's crew may build `improvement` on `tile` of its land."""
    from beacon import layout, works

    spec = cfg.improvements.get(improvement)
    if spec is None or spec["kind"] != "tile":
        return "only tile works (farms, mines, camps...) are built by the city's engineers"
    if tile not in layout.territory_tiles(state, cfg, city):
        return "that hex is not this city's land"
    if works.tile_ordered(city, tile):
        return "engineers are already working there"
    if any(u.tile == tile and u.owner != city.owner for u in state.units.values()):
        return "another unit stands there"
    return site_problem(state, cfg, city.owner or "", tile, improvement)
