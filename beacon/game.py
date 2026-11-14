"""Creating a new game: map, cities, players, starting units, alien garrisons, fog."""

from __future__ import annotations

from beacon import cities, citizens, fog, improvements, mapgen, network, rng
from beacon.config import Config
from beacon.state import ACTIVE, ALIENS, OVERRUN, CityMemory, GameState, Player
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


def assign_characters(cfg: Config, state: GameState) -> None:
    """Deal the AI characters out in a seeded order, cycling, so any five players include at
    least three different characters."""
    chars = sorted(cfg.ai("characters"))
    r = rng.stream(state.seed, "map", "characters")
    r.shuffle(chars)
    for k, pid in enumerate(state.player_ids()):
        state.players[pid].character = chars[k % len(chars)]


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
        for city in (c for c in state.cities if c.owner == pid):
            for unit_type in cfg.t("start.city_units.list"):
                if place_unit(state, cfg, unit_type, pid, city.tile, 0) is None:
                    raise ValueError(f"no room for {unit_type} in {city.name}")
    state.aliens.start_cities = sum(1 for c in state.cities if c.status == OVERRUN)
    assign_characters(cfg, state)
    # Modern nations are in contact: each knows where the others' cities are (docs/SPEC_M6.md).
    for pid in state.player_ids():
        player = state.players[pid]
        for city in state.cities:
            if city.status == ACTIVE and str(city.id) not in player.known_cities:
                player.known_cities[str(city.id)] = CityMemory(
                    status=city.status, owner=city.owner, pop=city.pop, turn_seen=0
                )
    # Only improved tiles can be worked (designer 2026-11-14): known cities start with farmland.
    improved = cfg.t("cities.start_improved")
    for city in state.cities:
        if city.status == ACTIVE and city.owner in state.players:
            role = "capital" if city.is_capital else "known"
            improvements.auto_improve(state, cfg, city, improved[role], city.owner)
    citizens.assign_all(state, cfg)
    for pid in state.player_ids():
        network.update_connections(state, cfg, pid)
    fog.refresh_all(state, cfg)
    return state
