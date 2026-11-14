"""City helpers shared by economy, combat and setup."""

from __future__ import annotations

from beacon import hexgrid
from beacon.config import Config
from beacon.state import ALIENS, City, GameState
from beacon.tiles import is_water


def max_hp(cfg: Config, city: City, state: GameState | None = None) -> int:
    """City HP: base + buildings, + alien wall techs for alien cities (needs `state`)."""
    hp = cfg.t("cities.base_hp") + sum(cfg.buildings[b].get("city_hp", 0) for b in city.buildings)
    if state is not None and city.owner == ALIENS:
        hp += alien_effect(state, cfg, "city_hp")
    return hp


def alien_effect(state: GameState, cfg: Config, key: str) -> int:
    """Sum of one effect over the alien techs gained so far."""
    return sum(cfg.alien_techs[t]["effects"].get(key, 0) for t in state.aliens.techs)


def is_coastal(state: GameState, cfg: Config, city: City) -> bool:
    return any(
        is_water(cfg, state.tiles[n])
        for n in hexgrid.neighbours(city.tile, state.width, state.height)
    )


def work_tiles(state: GameState, cfg: Config, city: City) -> list[int]:
    """Tiles in this city's work area, excluding the city's own tile, in index order."""
    area = hexgrid.within(city.tile, cfg.t("cities.work_radius"), state.width, state.height)
    return [t for t in area if state.tiles[t].city == city.id and t != city.tile]
