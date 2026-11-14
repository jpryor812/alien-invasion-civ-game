"""Applying commands, listing legal options and pending decisions.

`apply_command` validates first and raises `CommandError` without changing the state if the
command is illegal; otherwise it applies the command and returns the events produced.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from beacon import (
    citizens,
    combat,
    diplomacy,
    economy,
    endgame,
    fog,
    hexgrid,
    improvements,
    liberation,
    movement,
    promotions,
    recruits,
    tech,
)
from beacon.commands import (
    AcceptDeal,
    AcceptOffer,
    AssignBestCitizen,
    Attack,
    BuildImprovement,
    CancelJob,
    ChooseEspionageTech,
    CityAttack,
    Command,
    CommandError,
    DeclineDeal,
    DeclineOffer,
    Fortify,
    FundProject,
    HoldFire,
    MergeUnits,
    MoveUnit,
    OfferRecruit,
    PromoteUnit,
    ProposeDeal,
    Purchase,
    RefoundCity,
    SeatRecruit,
    SetCitizenJob,
    SetFocus,
    SetProduction,
    SetResearch,
    ShipUnit,
    SkipUnit,
    SplitUnit,
    StartBarrage,
    StartEspionage,
    UnseatRecruit,
    UpgradeDefence,
    UpgradeTurret,
)
from beacon.config import Config
from beacon.state import ACTIVE, EMPTY, City, GameState, Unit
from beacon.units import full_moves, is_civilian

Events = list[dict[str, Any]]
Handler = Callable[[GameState, Config, Any], Events]
HANDLERS: dict[type[Command], Handler] = {}


def handles(cls: type[Command]) -> Callable[[Handler], Handler]:
    def deco(fn: Handler) -> Handler:
        HANDLERS[cls] = fn
        return fn

    return deco


# Commands after which citizens are placed again (a city changed hands, a seat or a job changed).
REPLACE_CITIZENS: tuple[type[Command], ...] = ()


def apply_command(state: GameState, cfg: Config, cmd: Command) -> Events:
    if cmd.player not in state.players:
        raise CommandError(f"unknown player {cmd.player!r}")
    handler = HANDLERS.get(type(cmd))
    if handler is None:
        raise CommandError(f"no handler for {cmd.kind}")
    events = handler(state, cfg, cmd)
    if isinstance(cmd, REPLACE_CITIZENS):
        citizens.assign_all(state, cfg)  # cities, seats or tiles changed: re-place everyone
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
    # Moving onto a unit of the same type merges the two (designer 2026-11-14: no merge button).
    twin = next(
        (
            u
            for u in state.units_at(cmd.target)
            if u.owner == cmd.player and u.id != unit.id and u.type == unit.type
        ),
        None,
    )
    if twin is not None and movement.merge_problem(state, cfg, unit, twin) is None:
        return _merge(state, cfg, MergeUnits(player=cmd.player, unit=unit.id, into=twin.id))
    seen = _seen(state, cfg, cmd.player)
    found = movement.find_path(state, cfg, unit, cmd.target, seen=seen)
    if found is None or len(found[0]) < 2:
        raise CommandError(f"no path for unit {unit.id} to tile {cmd.target}")
    events = movement.move_along(state, cfg, unit, found[0])
    if not events:
        # This turn's leg ended on a friendly-occupied hex; route around friendly units.
        detour = movement.find_path(state, cfg, unit, cmd.target, seen=seen, avoid_friends=True)
        if detour is not None and len(detour[0]) >= 2:
            events = movement.move_along(state, cfg, unit, detour[0])
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


@handles(SetCitizenJob)
def _citizen_job(state: GameState, cfg: Config, cmd: SetCitizenJob) -> Events:
    c = state.citizens.get(str(cmd.citizen))
    if c is None:
        raise CommandError(f"no citizen {cmd.citizen}")
    problem = citizens.job_problem(state, cfg, cmd.player, c, cmd.job)
    if problem:
        raise CommandError(problem)
    c.job = cmd.job
    return [{"kind": "citizen_job", "citizen": c.id, "job": cmd.job}]


@handles(UpgradeDefence)
def _upgrade_defence(state: GameState, cfg: Config, cmd: UpgradeDefence) -> Events:
    unit = own_unit(state, cmd.player, cmd.unit)
    problem = promotions.upgrade_problem(state, cfg, unit)
    if problem:
        raise CommandError(problem)
    cost = promotions.upgrade_cost(cfg, unit)
    assert cost is not None
    state.players[cmd.player].gold -= cost
    unit.promotions.append(promotions.GOLD_UPGRADE)
    return [{"kind": "defence_upgraded", "unit": unit.id, "gold": cost}]


@handles(UpgradeTurret)
def _upgrade_turret(state: GameState, cfg: Config, cmd: UpgradeTurret) -> Events:
    from beacon import turrets  # turrets imports combat

    problem = turrets.upgrade_problem(state, cfg, cmd.player, cmd.tile)
    if problem:
        raise CommandError(problem)
    return turrets.upgrade(state, cfg, cmd.player, cmd.tile)


@handles(CancelJob)
def _cancel_job(state: GameState, cfg: Config, cmd: CancelJob) -> Events:
    unit = own_unit(state, cmd.player, cmd.unit)
    if unit.job is None:
        raise CommandError("this unit is not working on anything")
    started_earlier = unit.job.turns_left < cfg.improvements[unit.job.improvement]["turns"]
    imp = unit.job.improvement
    unit.job = None
    unit.order = "none"
    if started_earlier:  # it has not spent this turn yet: it may move away at once
        unit.moves_left = full_moves(cfg, unit.type)
    return [{"kind": "job_cancelled", "unit": unit.id, "improvement": imp}]


@handles(PromoteUnit)
def _promote(state: GameState, cfg: Config, cmd: PromoteUnit) -> Events:
    unit = own_unit(state, cmd.player, cmd.unit)
    problem = promotions.promote_problem(state, cfg, unit, cmd.promotion)
    if problem:
        raise CommandError(problem)
    unit.promotions.append(cmd.promotion)
    return [{"kind": "unit_promoted", "unit": unit.id, "promotion": cmd.promotion}]


@handles(AssignBestCitizen)
def _assign_best(state: GameState, cfg: Config, cmd: AssignBestCitizen) -> Events:
    city = own_city(state, cmd.player, cmd.city)
    if cmd.tile not in citizens.workable(state, cfg, city):
        raise CommandError("that tile has no improvement in this city's area")
    c = citizens.best_for_tile(state, cfg, city, cmd.tile)
    if c is None:
        raise CommandError(f"{city.name} has no grown citizen free for that tile")
    c.job = f"tile:{cmd.tile}"
    return [{"kind": "citizen_job", "citizen": c.id, "job": c.job, "name": c.name}]


@handles(HoldFire)
def _hold_fire(state: GameState, cfg: Config, cmd: HoldFire) -> Events:
    city = own_city(state, cmd.player, cmd.city)
    city.bombarded = True
    return []


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
    if unit.attacks_left < 1:
        raise CommandError("a unit that attacked this turn cannot fortify")
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


# -- recruits and councils ----------------------------------------------------------------------


def own_recruit(state: GameState, pid: str, recruit_id: int):
    rec = state.recruits.get(str(recruit_id))
    if rec is None or rec.patron != pid:
        raise CommandError(f"{pid} has no recruit {recruit_id}")
    return rec


@handles(SeatRecruit)
def _seat(state: GameState, cfg: Config, cmd: SeatRecruit) -> Events:
    rec = own_recruit(state, cmd.player, cmd.recruit)
    problem = recruits.seat_problem(state, cfg, rec, list(cmd.seats))
    if problem:
        raise CommandError(problem)
    rec.seats = list(cmd.seats)
    return [{"kind": "recruit_seated", "recruit": rec.id, "seats": list(cmd.seats)}]


@handles(UnseatRecruit)
def _unseat(state: GameState, cfg: Config, cmd: UnseatRecruit) -> Events:
    rec = own_recruit(state, cmd.player, cmd.recruit)
    rec.seats = []
    return [{"kind": "recruit_unseated", "recruit": rec.id}]


@handles(OfferRecruit)
def _offer(state: GameState, cfg: Config, cmd: OfferRecruit) -> Events:
    rec = own_recruit(state, cmd.player, cmd.recruit)
    if cmd.to_player not in state.players or cmd.to_player == cmd.player:
        raise CommandError(f"cannot offer to {cmd.to_player!r}")
    if cmd.price < 0:
        raise CommandError("price cannot be negative")
    if any(o.recruit == rec.id for o in state.offers.values()):
        raise CommandError(f"{rec.name} is already on offer")
    o = recruits.offer(state, rec, cmd.to_player, cmd.price)
    return [
        {
            "kind": "recruit_offered",
            "offer": o.id,
            "recruit": rec.id,
            "to": cmd.to_player,
            "price": cmd.price,
        }
    ]


def _incoming(state: GameState, pid: str, offer_id: int):
    o = state.offers.get(str(offer_id))
    if o is None or o.to_player != pid:
        raise CommandError(f"no offer {offer_id} for {pid}")
    return o


@handles(AcceptOffer)
def _accept(state: GameState, cfg: Config, cmd: AcceptOffer) -> Events:
    o = _incoming(state, cmd.player, cmd.offer)
    rec = state.recruits.get(str(o.recruit))
    if rec is None or rec.patron != o.from_player:
        del state.offers[str(o.id)]
        raise CommandError("that recruit is no longer available")
    if state.players[cmd.player].gold < o.price:
        raise CommandError(f"the price is {o.price} gold")
    return recruits.accept(state, cfg, o)


@handles(DeclineOffer)
def _decline(state: GameState, cfg: Config, cmd: DeclineOffer) -> Events:
    o = _incoming(state, cmd.player, cmd.offer)
    del state.offers[str(o.id)]
    return [{"kind": "offer_declined", "offer": o.id}]


# -- diplomacy and troops abroad -----------------------------------------------------------------


@handles(ProposeDeal)
def _propose(state: GameState, cfg: Config, cmd: ProposeDeal) -> Events:
    if cmd.to_player not in state.players:
        raise CommandError(f"unknown player {cmd.to_player!r}")
    try:
        give, take = diplomacy.terms_from(dict(cmd.give)), diplomacy.terms_from(dict(cmd.take))
    except (ValueError, TypeError) as err:
        raise CommandError(str(err)) from None
    probe = diplomacy.Deal(
        id=0,
        proposer=cmd.player,
        receiver=cmd.to_player,
        give=give,
        take=take,
        duration=cmd.duration,
        proposed_turn=state.turn,
    )
    problem = diplomacy.deal_problem(state, cfg, probe)
    if problem:
        raise CommandError(problem)
    deal = diplomacy.propose(state, cfg, cmd.player, cmd.to_player, give, take, cmd.duration)
    return [{"kind": "deal_proposed", "deal": deal.id, "to": cmd.to_player}]


def _incoming_deal(state: GameState, pid: str, deal_id: int):
    deal = state.deals.get(str(deal_id))
    if deal is None or deal.receiver != pid or deal.active:
        raise CommandError(f"no open deal {deal_id} for {pid}")
    return deal


@handles(AcceptDeal)
def _accept_deal(state: GameState, cfg: Config, cmd: AcceptDeal) -> Events:
    deal = _incoming_deal(state, cmd.player, cmd.deal)
    problem = diplomacy.deal_problem(state, cfg, deal)  # things may have changed since
    if problem:
        raise CommandError(problem)
    return diplomacy.accept(state, cfg, deal)


@handles(DeclineDeal)
def _decline_deal(state: GameState, cfg: Config, cmd: DeclineDeal) -> Events:
    deal = _incoming_deal(state, cmd.player, cmd.deal)
    del state.deals[str(deal.id)]
    return [{"kind": "deal_declined", "deal": deal.id}]


@handles(ShipUnit)
def _ship(state: GameState, cfg: Config, cmd: ShipUnit) -> Events:
    unit = own_unit(state, cmd.player, cmd.unit)
    known = {int(k) for k in state.players[cmd.player].known_cities}
    problem = diplomacy.ship_problem(state, cfg, unit, cmd.city, known)
    if problem:
        raise CommandError(problem)
    return diplomacy.ship_unit(state, cfg, unit, cmd.city)


# -- endgame projects -----------------------------------------------------------------------------


@handles(StartBarrage)
def _start_barrage(state: GameState, cfg: Config, cmd: StartBarrage) -> Events:
    problem = endgame.start_barrage_problem(state, cfg, cmd.player, cmd.city)
    if problem:
        raise CommandError(problem)
    return endgame.start_barrage(state, cfg, cmd.player, cmd.city)


@handles(FundProject)
def _fund(state: GameState, cfg: Config, cmd: FundProject) -> Events:
    project = state.projects.get(str(cmd.project))
    problem = endgame.fund_problem(state, cmd.player, project, cmd.gold)
    if problem:
        raise CommandError(problem)
    assert project is not None
    return endgame.fund(state, cfg, cmd.player, project, cmd.gold)


@handles(StartEspionage)
def _start_espionage(state: GameState, cfg: Config, cmd: StartEspionage) -> Events:
    problem = endgame.start_espionage_problem(state, cmd.player, cmd.mode)
    if problem:
        raise CommandError(problem)
    return endgame.start_espionage(state, cfg, cmd.player, cmd.mode)


@handles(ChooseEspionageTech)
def _choose(state: GameState, cfg: Config, cmd: ChooseEspionageTech) -> Events:
    project = state.projects.get(str(cmd.project))
    problem = endgame.choose_problem(state, cmd.player, project, cmd.tech)
    if problem:
        raise CommandError(problem)
    assert project is not None
    return endgame.choose(state, cfg, project, cmd.tech)


def _seat_options(state: GameState, cfg: Config, rec) -> list[tuple[str, ...]]:
    options = [("general",)] + [(d,) for d in sorted(rec.scores)]
    if len(rec.scores) > 1:
        options.append(tuple(sorted(rec.scores)))
    return [o for o in options if recruits.seat_problem(state, cfg, rec, list(o)) is None]


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
    for rec in recruits.recruits_of(state, pid):
        out += [
            SeatRecruit(player=pid, recruit=rec.id, seats=o) for o in _seat_options(state, cfg, rec)
        ]
        if rec.seats:
            out.append(UnseatRecruit(player=pid, recruit=rec.id))
        if not any(o.recruit == rec.id for o in state.offers.values()):
            out += [
                OfferRecruit(player=pid, recruit=rec.id, to_player=other, price=0)
                for other in state.player_ids()
                if other != pid
            ]
    for o in sorted(state.offers.values(), key=lambda x: x.id):
        if o.to_player == pid:
            if player.gold >= o.price:
                out.append(AcceptOffer(player=pid, offer=o.id))
            out.append(DeclineOffer(player=pid, offer=o.id))
    known = {int(k) for k in player.known_cities}
    for deal in sorted(state.deals.values(), key=lambda d: d.id):
        if deal.receiver == pid and not deal.active:
            if diplomacy.deal_problem(state, cfg, deal) is None:
                out.append(AcceptDeal(player=pid, deal=deal.id))
            out.append(DeclineDeal(player=pid, deal=deal.id))
    for unit in state.sorted_units():
        if unit.owner == pid and state.city_at(unit.tile) is not None:
            out += [
                ShipUnit(player=pid, unit=unit.id, city=c)
                for c in sorted(known)
                if diplomacy.ship_problem(state, cfg, unit, c, known) is None
            ]
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
    seen: set[int] | None = None
    for city in state.cities:
        if city.owner != pid or city.status != ACTIVE or city.bombarded:
            continue
        # An enemy within the city's range: alert, so the player can fire (or hold fire).
        if seen is None:
            seen = _seen(state, cfg, pid)
        if any(
            combat.city_attack_problem(state, cfg, city, t, seen) is None
            for t in hexgrid.within(
                city.tile, cfg.t("cities.attack_range"), state.width, state.height
            )
        ):
            out.append({"kind": "city_can_attack", "city": city.id})
    for unit in state.sorted_units():
        if unit.owner == pid and promotions.due(cfg, unit) > 0:
            out.append({"kind": "unit_promotion", "unit": unit.id})
    for unit in state.sorted_units():
        if unit.owner == pid and unit.moves_left > 0 and unit.order == "none" and unit.job is None:
            out.append({"kind": "unit_needs_orders", "unit": unit.id})
    for rec in recruits.recruits_of(state, pid):
        if not rec.seats and _seat_options(state, cfg, rec):
            out.append({"kind": "recruit_unseated", "recruit": rec.id})
    for o in sorted(state.offers.values(), key=lambda x: x.id):
        if o.to_player == pid:
            out.append({"kind": "offer_received", "offer": o.id})
    for deal in sorted(state.deals.values(), key=lambda d: d.id):
        if deal.receiver == pid and not deal.active:
            out.append({"kind": "deal_received", "deal": deal.id})
    for project in sorted(state.projects.values(), key=lambda p: p.id):
        if project.kind == "espionage" and project.offered and project.chooser == pid:
            out.append({"kind": "choose_espionage_tech", "project": project.id})
    return out


REPLACE_CITIZENS = (
    Attack,
    MoveUnit,
    SeatRecruit,
    UnseatRecruit,
    SetCitizenJob,
    AssignBestCitizen,
    AcceptOffer,
)
