"""Creating a new game: map, cities, players, starting units, alien garrisons, fog."""

from __future__ import annotations

from beacon import cities, fog, mapgen
from beacon.config import Config
from beacon.state import ALIENS, OVERRUN, GameState, Player
from beacon.units import place_unit


def new_players(cfg: Config, continents: list[str]) -> dict[str, Player]:
    start_techs = sorted(t for t, spec in cfg.techs.items() if spec["known_at_start"])
    return {
        cid: Player(
            id=cid,
            name=cfg.continents[cid]["name"],
            gold=cfg.t("economy.start_gold"),
            techs=list(start_techs),
        )
        for cid in continents
    }


def new_game(cfg: Config, seed: int, continents: list[str] | None = None) -> GameState:
    continents = sorted(continents or cfg.continent_ids(), key=lambda c: cfg.continents[c]["order"])
    tiles, city_list = mapgen.generate(cfg, seed, continents)
    state = GameState(
        seed=seed,
        config_digest=cfg.digest,
        width=cfg.t("map.width"),
        height=cfg.t("map.height"),
        tiles=tiles,
        players=new_players(cfg, continents),
        cities=city_list,
    )
    radius = cfg.t("cities.work_radius")
    for city in state.cities:
        city.hp = cities.max_hp(cfg, city)
    for city in state.cities:
        if city.status == OVERRUN:
            for unit_type in cfg.t("aliens.garrison.list"):
                place_unit(state, cfg, unit_type, ALIENS, city.tile, radius)
    for pid in state.player_ids():
        capital = next(c for c in state.cities if c.owner == pid and c.is_capital)
        for entry in cfg.t("start.units.list"):
            for _ in range(entry["count"]):
                if place_unit(state, cfg, entry["type"], pid, capital.tile, radius) is None:
                    raise ValueError(f"no room for starting {entry['type']} near {capital.name}")
    fog.refresh_all(state, cfg)
    return state
