"""The end-of-turn pipeline (see docs/SPEC_M0-M3.md, "Turn pipeline")."""

from __future__ import annotations

from typing import Any

from beacon import (
    cities,
    citizens,
    combat,
    contact,
    council,
    diplomacy,
    economy,
    endgame,
    fog,
    hexgrid,
    improvements,
    leader,
    liberation,
    network,
    recruits,
    starfall,
    survivors,
    threat,
)
from beacon.config import Config
from beacon.state import GameState
from beacon.units import full_moves, max_hp


def year(cfg: Config, turn: int) -> int:
    return cfg.t("time.start_year") + turn // cfg.t("time.turns_per_year")


def date(cfg: Config, turn: int) -> str:
    """The turn's month and year, e.g. "Mar 2025" (a turn is a month, SPEC_M19)."""
    months = cfg.t("time.months")
    per = cfg.t("time.turns_per_year")
    return f"{months[(turn % per) * len(months) // per]} {year(cfg, turn)}"


def alien_phase(state: GameState, cfg: Config) -> list[dict[str, Any]]:
    from beacon import aliens

    return aliens.alien_phase(state, cfg)


def heal_amount(state: GameState, cfg: Config, unit) -> int:
    heal = cfg.t("combat.heal")
    city = state.city_at(unit.tile)
    if city is not None and city.owner == unit.owner:
        per = heal["city"]
    else:
        owner_city = state.tiles[unit.tile].city
        own = owner_city is not None and state.cities[owner_city].owner == unit.owner
        per = heal["own_territory"] if own else heal["neutral"]
    from beacon.promotions import heal_bonus  # promotions imports nothing from turn

    return (per + heal_bonus(cfg, unit)) * unit.count


def reset_units(state: GameState, cfg: Config) -> None:
    # medics heal their side's units on and next to their hex, acted or not
    medics = [
        (u.owner, u.tile, cfg.units[u.type]["heal_adjacent"])
        for u in state.sorted_units()
        if cfg.units[u.type].get("heal_adjacent")
    ]
    for owner, tile, amount in medics:
        for n in (tile, *hexgrid.neighbours(tile, state.width, state.height)):
            for u in state.units_at(n):
                if u.owner == owner and cfg.units[u.type]["role"] != "civilian":
                    u.hp = min(max_hp(cfg, u), u.hp + amount * u.count)
    for unit in state.sorted_units():
        if not unit.acted:
            unit.hp = min(max_hp(cfg, unit), unit.hp + heal_amount(state, cfg, unit))
        unit.acted = False
        unit.attacks_left = 1
        if unit.order == "skip":
            unit.order = "none"
        from beacon.promotions import moves_bonus

        bonus = moves_bonus(cfg, unit) * cfg.t("movement.scale")  # Blitz, Sea Legs
        unit.moves_left = 0 if unit.job is not None else full_moves(cfg, unit.type) + bonus
        if unit.job is not None:
            unit.acted = True  # working units do not heal


def heal_cities(state: GameState, cfg: Config) -> None:
    from beacon.units import hostile, is_civilian

    for city in state.cities:
        city.bombarded = False
        # a city with an enemy soldier next to it does not heal (sieges make progress)
        pressed = any(
            hostile(u.owner, city.owner or "") and not is_civilian(cfg, u.type)
            for n in hexgrid.neighbours(city.tile, state.width, state.height)
            for u in state.units_at(n)
        )
        if not city.besieged and not pressed:
            city.hp = min(cities.max_hp(cfg, city, state), city.hp + cfg.t("cities.heal_per_turn"))
        city.besieged = False


def advance_turn(state: GameState, cfg: Config) -> list[dict[str, Any]]:
    """Resolve the end of the current turn and start the next. Returns the events produced."""
    events: list[dict[str, Any]] = []
    events.extend(combat.defences_fire(state, cfg))
    events.extend(alien_phase(state, cfg))
    events.extend(threat.uprisings(state, cfg))  # SPEC_M12
    events.extend(threat.nest_turn(state, cfg))
    for pid in state.player_ids():
        network.update_connections(state, cfg, pid)
        events.extend(economy.player_turn(state, cfg, pid))
        events.extend(improvements.progress_jobs(state, cfg, pid))
        network.update_connections(state, cfg, pid)
    from beacon import food  # units no town fed eat rations (SPEC_M18), after every town ate

    for pid in state.player_ids():
        events.extend(food.field(state, cfg, pid))
    events.extend(diplomacy.end_of_turn(state, cfg))
    events.extend(endgame.end_of_turn(state, cfg))
    for pid in state.player_ids():
        events.extend(recruits.arrivals(state, cfg, pid))
    events.extend(recruits.end_of_turn(state, cfg))
    events.extend(leader.end_of_turn(state, cfg))  # births, votes, levels (SPEC_M11)
    events.extend(council.end_of_turn(state, cfg))  # sessions and measures (SPEC_M13)
    from beacon import exchange  # the Galactic Exchange drifts back toward its base (SPEC_M17)

    exchange.drift(state, cfg)
    events.extend(survivors.pick_up(state, cfg))  # the survivor start (SPEC_M14)
    from beacon import armoury  # carried gear goes to the armoury (SPEC_M20)

    events.extend(armoury.deposit(state, cfg))
    for pid in state.player_ids():  # a band that sighted its first town (designer 2026-11-17)
        events.extend(survivors.claim_town(state, cfg, pid))
    events.extend(survivors.escape(state, cfg))
    from beacon import alien_leaders  # leaders of towns seen this turn (SPEC_M21)

    alien_leaders.appoint_all(state, cfg)  # old saves
    events.extend(alien_leaders.meet(state, cfg))
    reset_units(state, cfg)
    heal_cities(state, cfg)
    state.turn += 1
    fog.refresh_all(state, cfg)
    events.append({"turn": state.turn, "kind": "turn_started", "year": date(cfg, state.turn)})
    from beacon import winter  # SPEC_M19

    events.extend(winter.start_turn(state, cfg))
    events.extend(liberation.update_fallen(state))
    events.extend(contact.check(state, cfg))
    events.extend(starfall.end_of_turn(state, cfg))
    events.extend(contact.fallen_known(state, cfg))
    events.extend(contact.radio(state, cfg))  # radio towers (designer 2026-11-16)
    events.extend(threat.update_intel(state, cfg))
    citizens.assign_all(state, cfg)
    events.extend(endgame.check_outcome(state, cfg))
    return events
