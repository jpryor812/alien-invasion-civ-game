"""Applying commands, listing legal options and pending decisions.

`apply_command` validates first and raises `CommandError` without changing the state if the
command is illegal; otherwise it applies the command and returns the events produced.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from beacon import combat, economy, fog, hexgrid, improvements, liberation, movement, tech
from beacon.commands import (
    Attack,
    BuildImprovement,
    CityAttack,
    Command,
    CommandError,
    Fortify,
    MergeUnits,
    MoveUnit,
    Purchase,
    RefoundCity,
    SetFocus,
    SetProduction,
    SetResearch,
    SkipUnit,
    SplitUnit,
)
from beacon.config import Config
from beacon.state import ACTIVE, EMPTY, City, GameState, Unit
from beacon.units import is_civilian

Events = list[dict[str, Any]]
Handler = Callable[[GameState, Config, Any], Events]
HANDLERS: dict[type[Command], Handler] = {}


def handles(cls: type[Command]) -> Callable[[Handler], Handler]:
    def deco(fn: Handler) -> Handler:
        HANDLERS[cls] = fn
        return fn

    return deco


def apply_command(state: GameState, cfg: Config, cmd: Command) -> Events:
    if cmd.player not in state.players:
        raise CommandError(f"unknown player {cmd.player!r}")
    handler = HANDLERS.get(type(cmd))
    if handler is None:
        raise CommandError(f"no handler for {cmd.kind}")
    events = handler(state, cfg, cmd)
    for e in events:
        e.setdefault("turn", state.turn)
        e.setdefault("player", cmd.player)
    return events


# -- lookups with ownership checks --------------------------------------------------------------


def own_city(state: GameState, pid: str, city_id: int) -> City:
    if not 0 <= city_id < len(state.cities):
        raise CommandError(f"no city {city_id}")
    city = state.cities[city_id]
    if city.owner != pid or city.status != ACTIVE:
        raise CommandError(f"{city.name} is not an active city of {pid}")
    return city


def own_unit(state: GameState, pid: str, unit_id: int) -> Unit:
    unit = state.units.get(str(unit_id))
    if unit is None or unit.owner != pid:
        raise CommandError(f"{pid} has no unit {unit_id}")
    return unit


# -- research and cities ------------------------------------------------------------------------


@handles(SetResearch)
def _set_research(state: GameState, cfg: Config, cmd: SetResearch) -> Events:
    player = state.players[cmd.player]
    if cmd.tech not in tech.available(cfg, player):
        raise CommandError(f"{cmd.tech} is not available to research")
    player.research = cmd.tech
    return [{"kind": "research_set", "tech": cmd.tech}]


@handles(SetProduction)
def _set_production(state: GameState, cfg: Config, cmd: SetProduction) -> Events:
    city = own_city(state, cmd.player, cmd.city)
    buildings = [i for i in cmd.items if i.startswith("building:")]
    if len(buildings) != len(set(buildings)):
        raise CommandError("a building appears twice in the queue")
    for item in cmd.items:
        problem = economy.item_allowed(state, cfg, city, item)
        if problem:
            raise CommandError(f"{city.name} cannot produce {item}: {problem}")
    city.queue = list(cmd.items)
    return [{"kind": "production_set", "city": city.id, "items": list(cmd.items)}]


@handles(Purchase)
def _purchase(state: GameState, cfg: Config, cmd: Purchase) -> Events:
    city = own_city(state, cmd.player, cmd.city)
    if not city.connected:
        raise CommandError(f"{city.name} is not connected")
    if not city.queue or city.queue[0].startswith("project:"):
        raise CommandError(f"{city.name} has nothing to buy at the head of its queue")
    item = city.queue[0]
    problem = economy.item_allowed(state, cfg, city, item)
    if problem:
        raise CommandError(problem)
    price = economy.item_cost(cfg, item) * cfg.t("economy.purchase_pct") // 100
    player = state.players[cmd.player]
    if player.gold < price:
        raise CommandError(f"{item} costs {price} gold; treasury has {player.gold}")
    done = economy.complete_item(state, cfg, city, item)
    if done is None:
        raise CommandError(f"{item} cannot be completed now (no room or no strategic resource)")
    player.gold -= price
    city.queue.pop(0)
    return [done, {"kind": "purchased", "city": city.id, "item": item, "gold": price}]


@handles(SetFocus)
def _set_focus(state: GameState, cfg: Config, cmd: SetFocus) -> Events:
    city = own_city(state, cmd.player, cmd.city)
    if cmd.focus not in economy.FOCUSES:
        raise CommandError(f"unknown focus {cmd.focus!r}")
    city.focus = cmd.focus
    return [{"kind": "focus_set", "city": city.id, "focus": cmd.focus}]


@handles(BuildImprovement)
def _build(state: GameState, cfg: Config, cmd: BuildImprovement) -> Events:
    unit = own_unit(state, cmd.player, cmd.unit)
    problem = improvements.build_problem(state, cfg, unit, cmd.improvement)
    if problem:
        raise CommandError(problem)
    improvements.start_job(state, cfg, unit, cmd.improvement)
    return [{"kind": "job_started", "unit": unit.id, "improvement": cmd.improvement}]


# -- units ------------------------------------------------------------------------------------


def _seen(state: GameState, cfg: Config, pid: str) -> set[int]:
    return fog.visible_tiles(state, cfg, pid)


@handles(MoveUnit)
def _move(state: GameState, cfg: Config, cmd: MoveUnit) -> Events:
    unit = own_unit(state, cmd.player, cmd.unit)
    if not 0 <= cmd.target < len(state.tiles):
        raise CommandError(f"no tile {cmd.target}")
    if unit.moves_left <= 0:
        raise CommandError("no moves left")
    found = movement.find_path(state, cfg, unit, cmd.target, seen=_seen(state, cfg, cmd.player))
    if found is None or len(found[0]) < 2:
        raise CommandError(f"no path for unit {unit.id} to tile {cmd.target}")
    events = movement.move_along(state, cfg, unit, found[0])
    if not events:
        raise CommandError(f"unit {unit.id} cannot make progress toward {cmd.target} this turn")
    return events


@handles(Attack)
def _attack(state: GameState, cfg: Config, cmd: Attack) -> Events:
    unit = own_unit(state, cmd.player, cmd.unit)
    problem = combat.attack_problem(state, cfg, unit, cmd.target, _seen(state, cfg, cmd.player))
    if problem:
        raise CommandError(problem)
    return combat.attack(state, cfg, unit, cmd.target)


@handles(CityAttack)
def _city_attack(state: GameState, cfg: Config, cmd: CityAttack) -> Events:
    city = own_city(state, cmd.player, cmd.city)
    problem = combat.city_attack_problem(
        state, cfg, city, cmd.target, _seen(state, cfg, cmd.player)
    )
    if problem:
        raise CommandError(problem)
    return combat.city_attack(state, cfg, city, cmd.target)


@handles(MergeUnits)
def _merge(state: GameState, cfg: Config, cmd: MergeUnits) -> Events:
    unit = own_unit(state, cmd.player, cmd.unit)
    into = own_unit(state, cmd.player, cmd.into)
    problem = movement.merge_problem(state, cfg, unit, into)
    if problem:
        raise CommandError(problem)
    found = movement.find_path(
        state,
        cfg,
        unit,
        into.tile,
        seen=_seen(state, cfg, cmd.player),
        allow_occupied_target=True,
        max_turns=0,
    )
    if found is None or found[1] > 0:
        raise CommandError("the other unit cannot be reached this turn")
    return movement.merge(state, cfg, unit, into, found[0])


@handles(SplitUnit)
def _split(state: GameState, cfg: Config, cmd: SplitUnit) -> Events:
    unit = own_unit(state, cmd.player, cmd.unit)
    problem = movement.split_problem(state, cfg, unit, cmd.target)
    if problem:
        raise CommandError(problem)
    return movement.split(state, cfg, unit, cmd.target)


@handles(Fortify)
def _fortify(state: GameState, cfg: Config, cmd: Fortify) -> Events:
    unit = own_unit(state, cmd.player, cmd.unit)
    if is_civilian(cfg, unit.type):
        raise CommandError("civilians cannot fortify")
    if unit.job is not None:
        raise CommandError("unit is working")
    unit.fortified = True
    unit.order = "fortify"
    return [{"kind": "unit_fortified", "unit": unit.id}]


@handles(SkipUnit)
def _skip(state: GameState, cfg: Config, cmd: SkipUnit) -> Events:
    unit = own_unit(state, cmd.player, cmd.unit)
    unit.order = "skip"
    return [{"kind": "unit_skipped", "unit": unit.id}]


@handles(RefoundCity)
def _refound(state: GameState, cfg: Config, cmd: RefoundCity) -> Events:
    unit = own_unit(state, cmd.player, cmd.unit)
    if not cfg.units[unit.type].get("can_refound"):
        raise CommandError(f"{unit.type} cannot refound cities")
    if unit.moves_left <= 0:
        raise CommandError("no moves left")
    city = state.city_at(unit.tile)
    if city is None or city.status != EMPTY:
        raise CommandError("refounding needs an empty city on the unit's hex")
    events = liberation.refound(state, cfg, city, cmd.player)
    from beacon.units import remove_unit

    remove_unit(state, unit)
    return events


def legal_commands(state: GameState, cfg: Config, pid: str) -> list[Command]:
    """Every legal command for a player right now (moves list each reachable hex)."""
    out: list[Command] = []
    player = state.players[pid]
    out += [SetResearch(player=pid, tech=t) for t in tech.available(cfg, player)]
    seen = _seen(state, cfg, pid)
    for city in state.cities:
        if city.owner != pid or city.status != ACTIVE:
            continue
        out += [
            SetProduction(player=pid, city=city.id, items=(item,))
            for item in economy.production_options(state, cfg, city)
        ]
        out += [SetFocus(player=pid, city=city.id, focus=f) for f in economy.FOCUSES]
        if city.queue and not city.queue[0].startswith("project:") and city.connected:
            price = economy.item_cost(cfg, city.queue[0]) * cfg.t("economy.purchase_pct") // 100
            if player.gold >= price:
                out.append(Purchase(player=pid, city=city.id))
        for t in hexgrid.within(city.tile, cfg.t("cities.attack_range"), state.width, state.height):
            if combat.city_attack_problem(state, cfg, city, t, seen) is None:
                out.append(CityAttack(player=pid, city=city.id, target=t))
    for unit in state.sorted_units():
        if unit.owner != pid:
            continue
        out += [
            MoveUnit(player=pid, unit=unit.id, target=t)
            for t in movement.reachable_this_turn(state, cfg, unit)
        ]
        reach = max(1, cfg.units[unit.type]["range"])
        for t in hexgrid.within(unit.tile, reach, state.width, state.height):
            if combat.attack_problem(state, cfg, unit, t, seen) is None:
                out.append(Attack(player=pid, unit=unit.id, target=t))
        for n in hexgrid.neighbours(unit.tile, state.width, state.height):
            if movement.split_problem(state, cfg, unit, n) is None:
                out.append(SplitUnit(player=pid, unit=unit.id, target=n))
        for other in state.sorted_units():
            if other.owner == pid and movement.merge_problem(state, cfg, unit, other) is None:
                found = movement.find_path(
                    state,
                    cfg,
                    unit,
                    other.tile,
                    seen=seen,
                    allow_occupied_target=True,
                    max_turns=0,
                )
                if found is not None and found[1] == 0:
                    out.append(MergeUnits(player=pid, unit=unit.id, into=other.id))
        for imp in sorted(cfg.improvements):
            if improvements.build_problem(state, cfg, unit, imp) is None:
                out.append(BuildImprovement(player=pid, unit=unit.id, improvement=imp))
        city = state.city_at(unit.tile)
        if (
            cfg.units[unit.type].get("can_refound")
            and unit.moves_left > 0
            and city is not None
            and city.status == EMPTY
        ):
            out.append(RefoundCity(player=pid, unit=unit.id))
        if not is_civilian(cfg, unit.type) and unit.job is None:
            out.append(Fortify(player=pid, unit=unit.id))
        out.append(SkipUnit(player=pid, unit=unit.id))
    return out


# -- decisions ----------------------------------------------------------------------------------


def pending_decisions(state: GameState, cfg: Config, pid: str) -> list[dict[str, Any]]:
    """What still needs this player this turn (the UI's 'unit needs orders' prompts)."""
    out: list[dict[str, Any]] = []
    player = state.players[pid]
    if player.research is None and tech.available(cfg, player):
        out.append({"kind": "choose_research"})
    for city in state.cities:
        if city.owner == pid and city.status == ACTIVE and not city.queue:
            out.append({"kind": "choose_production", "city": city.id})
    for unit in state.sorted_units():
        if unit.owner == pid and unit.moves_left > 0 and unit.order == "none" and unit.job is None:
            out.append({"kind": "unit_needs_orders", "unit": unit.id})
    return out
