"""The end-of-turn pipeline (see docs/SPEC_M0-M3.md, "Turn pipeline")."""

from __future__ import annotations

from typing import Any

from beacon import cities, economy, fog, improvements, network
from beacon.config import Config
from beacon.state import GameState
from beacon.units import full_moves, max_hp


def year(cfg: Config, turn: int) -> int:
    return cfg.t("time.start_year") + turn // cfg.t("time.turns_per_year")


def alien_phase(state: GameState, cfg: Config) -> list[dict[str, Any]]:
    """Alien growth, movement and attacks arrive in M4."""
    return []


def heal_amount(state: GameState, cfg: Config, unit) -> int:
    heal = cfg.t("combat.heal")
    city = state.city_at(unit.tile)
    if city is not None and city.owner == unit.owner:
        per = heal["city"]
    else:
        owner_city = state.tiles[unit.tile].city
        own = owner_city is not None and state.cities[owner_city].owner == unit.owner
        per = heal["own_territory"] if own else heal["neutral"]
    return per * unit.count


def reset_units(state: GameState, cfg: Config) -> None:
    for unit in state.sorted_units():
        if not unit.acted:
            unit.hp = min(max_hp(cfg, unit), unit.hp + heal_amount(state, cfg, unit))
        unit.acted = False
        unit.attacks_left = 1
        if unit.order == "skip":
            unit.order = "none"
        unit.moves_left = 0 if unit.job is not None else full_moves(cfg, unit.type)
        if unit.job is not None:
            unit.acted = True  # working units do not heal


def heal_cities(state: GameState, cfg: Config) -> None:
    for city in state.cities:
        city.bombarded = False
        city.hp = min(cities.max_hp(cfg, city), city.hp + cfg.t("cities.heal_per_turn"))


def advance_turn(state: GameState, cfg: Config) -> list[dict[str, Any]]:
    """Resolve the end of the current turn and start the next. Returns the events produced."""
    events: list[dict[str, Any]] = []
    events.extend(alien_phase(state, cfg))
    for pid in state.player_ids():
        network.update_connections(state, cfg, pid)
        events.extend(economy.player_turn(state, cfg, pid))
        events.extend(improvements.progress_jobs(state, cfg, pid))
        network.update_connections(state, cfg, pid)
    reset_units(state, cfg)
    heal_cities(state, cfg)
    state.turn += 1
    fog.refresh_all(state, cfg)
    events.append({"turn": state.turn, "kind": "turn_started", "year": year(cfg, state.turn)})
    return events
