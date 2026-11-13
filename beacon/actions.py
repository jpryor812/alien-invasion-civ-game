"""Applying commands, listing legal options and pending decisions.

`apply_command` validates first and raises `CommandError` without changing the state if the
command is illegal; otherwise it applies the command and returns the events produced.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from beacon import economy, improvements, tech
from beacon.commands import (
    BuildImprovement,
    Command,
    CommandError,
    Purchase,
    SetFocus,
    SetProduction,
    SetResearch,
)
from beacon.config import Config
from beacon.state import ACTIVE, City, GameState, Unit

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
