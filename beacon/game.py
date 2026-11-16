"""Creating a new game: map, cities, players, starting units, alien garrisons, fog."""

from __future__ import annotations

from beacon import (
    cities,
    citizens,
    contact,
    council,
    fog,
    hexgrid,
    improvements,
    leader,
    mapgen,
    network,
    rng,
    starfall,
    story,
    survivors,
    threat,
)
from beacon.config import Config
from beacon.state import ACTIVE, ALIENS, OVERRUN, GameState, Player
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


def new_game(
    cfg: Config, seed: int, continents: list[str] | None = None, start: str = "classic"
) -> GameState:
    """A new game. `start` is "classic" (cities and an army) or "survivor" (SPEC_M14: a band
    that must take its first town); the runner and the web session pass cfg's start.mode."""
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
        wrap=bool(cfg.t("map.wrap")),
    )
    radius = cfg.t("cities.work_radius")
    for city in state.cities:
        city.hp = cities.max_hp(cfg, city)
    # The alien city nearest each capital is lightly held, so a first liberation comes early.
    near: set[int] = set()
    for capital in (c for c in state.cities if c.is_capital):
        alien = [
            c for c in state.cities if c.status == OVERRUN and c.continent == capital.continent
        ]
        if alien:
            first = min(
                alien, key=lambda c: (hexgrid.distance(c.tile, capital.tile, state.width), c.id)
            )
            near.add(first.id)
    for city in state.cities:
        if city.status == OVERRUN:
            key = "near_list" if city.id in near else "list"
            if city.id in near:
                city.hp = city.hp * cfg.t("aliens.near_hp_pct") // 100
            for unit_type in cfg.t(f"aliens.garrison.{key}"):
                place_unit(state, cfg, unit_type, ALIENS, city.tile, radius)
    for pid in state.player_ids():
        capital = next(c for c in state.cities if c.owner == pid and c.is_capital)
        for entry in cfg.t("start.units.list"):
            for _ in range(entry["count"]):
                if place_unit(state, cfg, entry["type"], pid, capital.tile, radius) is None:
                    raise ValueError(f"no room for starting {entry['type']} near {capital.name}")
        for city in (c for c in state.cities if c.owner == pid and not c.is_capital):
            for entry in cfg.t("start.other_cities.list"):
                for _ in range(entry["count"]):
                    if place_unit(state, cfg, entry["type"], pid, city.tile, radius) is None:
                        raise ValueError(f"no room for starting {entry['type']} near {city.name}")
        for city in (c for c in state.cities if c.owner == pid):
            for unit_type in cfg.t("start.city_units.list"):
                if place_unit(state, cfg, unit_type, pid, city.tile, 0) is None:
                    raise ValueError(f"no room for {unit_type} in {city.name}")
    state.aliens.start_cities = sum(1 for c in state.cities if c.status == OVERRUN)
    assign_characters(cfg, state)
    taken: tuple[str, ...] = ()
    for pid in state.player_ids():  # every player has a leader (SPEC_M11)
        state.players[pid].leader = leader.generate(cfg, seed, pid, taken)
        taken += (state.players[pid].leader.name,)
    leader.seed_attitudes(state, cfg)
    council.deal_agendas(state, cfg)  # agendas and secret objectives (SPEC_M13)
    # Nobody knows the other continents at the start: they meet by exploring (beacon/contact.py,
    # designer 2026-11-14; replaces the M6 rule that everyone knew everyone's cities).
    # Only improved tiles can be worked (designer 2026-11-14): known cities start with farmland.
    improved = cfg.t("cities.start_improved")
    for city in state.cities:
        if city.status == ACTIVE and city.owner in state.players:
            role = "capital" if city.is_capital else "known"
            improvements.auto_improve(state, cfg, city, improved[role], city.owner)
    if start == "survivor":
        story.place_sites(state, cfg)  # caches avoid finds, so finds come first
        survivors.setup(state, cfg)
    elif start != "classic":
        raise ValueError(f"unknown start {start!r}")
    citizens.assign_all(state, cfg)
    if start == "classic":
        story.place_sites(state, cfg)  # exploration finds (docs/SPEC_M9.md)
    starfall.place_remnants(state, cfg)  # meteor remnants (docs/SPEC_M10.md)
    threat.seed_contents(state, cfg)  # what alien cities hold, and their nests (SPEC_M12)
    threat.place_nests(state, cfg)
    for pid in state.player_ids():
        network.update_connections(state, cfg, pid)
    contact.radio(state, cfg)  # capitals with a radio tower are in contact (designer 2026-11-16)
    fog.refresh_all(state, cfg)
    return state
