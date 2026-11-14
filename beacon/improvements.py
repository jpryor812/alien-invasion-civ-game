"""Hex improvements and routes, built by engineers over several turns."""

from __future__ import annotations

from typing import Any

from beacon import fog, tech
from beacon.config import Config
from beacon.state import City, GameState, Job, Unit
from beacon.tiles import is_passable_land


def build_problem(state: GameState, cfg: Config, unit: Unit, improvement: str) -> str | None:
    """None if `unit` may start building `improvement` on its hex, else the reason."""
    if improvement not in cfg.improvements:
        return f"unknown improvement {improvement!r}"
    spec = cfg.improvements[improvement]
    if not cfg.units[unit.type].get("can_build"):
        return f"{unit.type} cannot build improvements"
    if unit.moves_left <= 0:
        return "no moves left"
    player = state.players.get(unit.owner)
    if player is None or not tech.knows(player, spec["tech"]):
        return f"needs tech {spec['tech']}"
    tile = state.tiles[unit.tile]
    if not is_passable_land(cfg, tile):
        return "not buildable terrain"
    if state.city_at(unit.tile) is not None:
        return "city hexes already count as roads"
    if tile.terrain not in spec["terrains"] or tile.elevation not in spec["elevations"]:
        return f"{improvement} cannot go on {tile.elevation} {tile.terrain}"
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
    return None


def start_job(state: GameState, cfg: Config, unit: Unit, improvement: str) -> None:
    unit.job = Job(improvement=improvement, turns_left=cfg.improvements[improvement]["turns"])
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
        tile = state.tiles[unit.tile]
        if cfg.improvements[imp]["kind"] == "route":
            tile.route = imp
        else:
            tile.improvement = imp
        tile.built_by = pid
        fog.touch_built(state)
        unit.job = None
        unit.order = "none"
        events.append(
            {
                "turn": state.turn,
                "kind": "improvement_built",
                "player": pid,
                "tile": unit.tile,
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
