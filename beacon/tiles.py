"""Tile rules: what a hex yields, costs to enter and gives in defense.

Yield breakdowns are lists of `(source, yield, amount)` lines so every number can be explained.
"""

from __future__ import annotations

from beacon.config import YIELDS, Config
from beacon.state import Tile

Line = tuple[str, str, int]


def is_water(cfg: Config, tile: Tile) -> bool:
    return bool(cfg.terrains[tile.terrain]["water"])


def is_passable_land(cfg: Config, tile: Tile) -> bool:
    if is_water(cfg, tile):  # a sea bridge carries land units over shallow water (SPEC_M11)
        return tile.route == "sea_bridge"
    return bool(cfg.elevations[tile.elevation]["passable"])


def resource_active(cfg: Config, tile: Tile) -> bool:
    """A resource yields (and supplies) only with its improvement, unless it needs none."""
    if tile.resource is None:
        return False
    needed = cfg.resources[tile.resource]["improvement"]
    return needed is None or tile.improvement == needed


def yield_lines(cfg: Config, tile: Tile) -> list[Line]:
    lines: list[Line] = []

    def add(source: str, yields: dict[str, int]) -> None:
        for y in YIELDS:
            if yields.get(y):
                lines.append((source, y, yields[y]))

    add(f"terrain:{tile.terrain}", cfg.terrains[tile.terrain]["yields"])
    add(f"elevation:{tile.elevation}", cfg.elevations[tile.elevation]["yields"])
    if tile.feature:
        add(f"feature:{tile.feature}", cfg.features[tile.feature]["yields"])
    if tile.resource and resource_active(cfg, tile):
        add(f"resource:{tile.resource}", cfg.resources[tile.resource]["yields"])
    if tile.improvement:
        add(f"improvement:{tile.improvement}", cfg.improvements[tile.improvement]["yields"])
    return lines


def totals(lines: list[Line]) -> dict[str, int]:
    out = dict.fromkeys(YIELDS, 0)
    for _, y, amount in lines:
        out[y] += amount
    return out


def tile_yields(cfg: Config, tile: Tile) -> dict[str, int]:
    """Yields of a tile, each floored at 0."""
    return {y: max(0, v) for y, v in totals(yield_lines(cfg, tile)).items()}


def potential_yields(cfg: Config, tile: Tile) -> dict[str, int]:
    """Yields as if the tile's resource were improved (used to score city sites)."""
    out = totals(yield_lines(cfg, tile))
    if tile.resource and not resource_active(cfg, tile):
        for y, v in cfg.resources[tile.resource]["yields"].items():
            out[y] += v
    return {y: max(0, v) for y, v in out.items()}


def move_cost(cfg: Config, tile: Tile) -> int:
    """Sub-points to enter this tile off-road."""
    cost = max(
        cfg.terrains[tile.terrain]["move_cost"],
        cfg.elevations[tile.elevation]["move_cost"],
        cfg.features[tile.feature]["move_cost"] if tile.feature else 0,
    )
    return cost * cfg.t("movement.scale")


def defense_lines(cfg: Config, tile: Tile) -> list[tuple[str, int]]:
    lines = []
    for source, pct in (
        (f"terrain:{tile.terrain}", cfg.terrains[tile.terrain]["defense_pct"]),
        (f"elevation:{tile.elevation}", cfg.elevations[tile.elevation]["defense_pct"]),
        (
            f"feature:{tile.feature}",
            cfg.features[tile.feature]["defense_pct"] if tile.feature else 0,
        ),
        (
            f"improvement:{tile.improvement}",
            cfg.improvements[tile.improvement].get("defense_pct", 0) if tile.improvement else 0,
        ),
    ):
        if pct:
            lines.append((source, pct))
    return lines
