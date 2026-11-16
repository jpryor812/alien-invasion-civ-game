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
    contact,
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
    ArmResistance,
    AssignBestCitizen,
    Attack,
    BuildImprovement,
    CancelJob,
    CastVote,
    ChooseEspionageTech,
    ChooseLeaderBonus,
    ChooseStory,
    CityAttack,
    Command,
    CommandError,
    CreateLeader,
    DeclineDeal,
    DeclineOffer,
    Fortify,
    FundProject,
    HoldFire,
    MergeUnits,
    MoveBuilding,
    MoveUnit,
    OfferRecruit,
    PlaceBuilding,
    PlaceWalls,
    PromoteUnit,
    ProposeDeal,
    ProposeMeasure,
    Purchase,
    RaiseSkill,
    RefoundCity,
    Sabotage,
    SeatRecruit,
    SetAgenda,
    SetCitizenJob,
    SetConvoy,
    SetFocus,
    SetProduction,
    SetResearch,
    SetWardrobe,
    ShipUnit,
    SkipUnit,
    SplitUnit,
    StartBarrage,
    StartEspionage,
    StartFamily,
    UnseatRecruit,
    UpgradeDefence,
    UpgradeTurret,
)
from beacon.config import DOMAINS, Config
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
    if isinstance(cmd, MoveUnit):
        events.extend(contact.check(state, cfg, only=cmd.player))  # a scout may sight someone
        from beacon.threat import update_intel  # a scout beside an alien city (SPEC_M12)

        events.extend(update_intel(state, cfg))
        if state.caches:
            from beacon.survivors import pick_up  # caches of the survivor start (SPEC_M14)

            events.extend(pick_up(state, cfg))
    if isinstance(cmd, Purchase):
        events.extend(contact.radio(state, cfg))  # a bought radio tower is on the air at once
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
    from beacon.layout import drop_unqueued  # placed buildings taken off the queue lose their place

    drop_unqueued(city)
    return [{"kind": "production_set", "city": city.id, "items": list(cmd.items)}]


@handles(Purchase)
def _purchase(state: GameState, cfg: Config, cmd: Purchase) -> Events:
    city = own_city(state, cmd.player, cmd.city)
    item = cmd.item or (city.queue[0] if city.queue else "")
    if not item or item.startswith("project:"):
        raise CommandError(f"{city.name} has nothing to buy")
    if item not in economy.production_options(state, cfg, city):
        raise CommandError(f"{city.name} cannot build {item}")
    problem = economy.item_allowed(state, cfg, city, item)
    if problem:
        raise CommandError(problem)
    player = state.players[cmd.player]
    price = economy.purchase_price(cfg, item, player, economy.stored(city, item), city)
    if player.gold < price:
        raise CommandError(f"{item} costs {price} gold; treasury has {player.gold}")
    from beacon import materials  # SPEC_M16: gold buys the work, not the materials

    lack = materials.short(city, materials.item_cost(cfg, city, item))
    if lack:
        raise CommandError("needs " + ", ".join(f"{n} more {g}" for g, n in sorted(lack.items())))
    done = economy.complete_item(state, cfg, city, item)
    if done is None:
        raise CommandError(f"{item} cannot be completed now (no room or no strategic resource)")
    player.gold -= price
    city.progress.pop(item, None)
    if item in city.queue:
        city.queue.remove(item)
    return [done, {"kind": "purchased", "city": city.id, "item": item, "gold": price}]


@handles(SetConvoy)
def _set_convoy(state: GameState, cfg: Config, cmd: SetConvoy) -> Events:
    from beacon import convoys

    city = own_city(state, cmd.player, cmd.city)
    if cmd.target < 0:
        city.convoy = None
        return [{"kind": "convoy_stopped", "city": city.id}]
    why = convoys.problem(state, cfg, city, cmd.target, cmd.goods, cmd.pct)
    if why:
        raise CommandError(why)
    city.convoy = {"to": cmd.target, "kind": cmd.goods, "pct": cmd.pct}
    return [
        {
            "kind": "convoy_set",
            "city": city.id,
            "to": cmd.target,
            "goods": cmd.goods,
            "pct": cmd.pct,
        }
    ]


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
    problem = improvements.build_problem(state, cfg, unit, cmd.improvement, cmd.target)
    if problem:
        raise CommandError(problem)
    improvements.start_job(state, cfg, unit, cmd.improvement, cmd.target)
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


@handles(ChooseStory)
def _choose_story(state: GameState, cfg: Config, cmd: ChooseStory) -> Events:
    from beacon import story  # story imports citizens and units

    problem = story.choice_problem(state, cfg, cmd.player, cmd.story, cmd.choice)
    if problem:
        raise CommandError(problem)
    return story.choose(state, cfg, cmd.player, cmd.story, cmd.choice)


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
    if not contact.met(state, cmd.player, cmd.to_player):
        raise CommandError(f"you have not met {cmd.to_player} yet")
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
    if not contact.met(state, cmd.player, cmd.to_player):
        raise CommandError(f"you have not met {cmd.to_player} yet")
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
    dest = state.cities[cmd.city] if 0 <= cmd.city < len(state.cities) else None
    if dest is not None and not contact.met(state, cmd.player, dest.continent):
        raise CommandError(f"you have not met {dest.continent} yet")
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
        if city.queue and not city.queue[0].startswith("project:"):
            head = city.queue[0]
            price = economy.purchase_price(cfg, head, player, economy.stored(city, head), city)
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
            if cfg.improvements[imp]["kind"] == "bridge":
                for t in improvements.bridge_targets(state, cfg, unit):
                    if improvements.build_problem(state, cfg, unit, imp, t) is None:
                        out.append(
                            BuildImprovement(player=pid, unit=unit.id, improvement=imp, target=t)
                        )
            elif improvements.build_problem(state, cfg, unit, imp) is None:
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
    for ev in sorted(state.story_events.values(), key=lambda e: e.id):
        if ev.player == pid:
            out.append({"kind": "story_choice", "story": ev.id, "event": ev.event})
    if player.research is None and tech.available(cfg, player) and player.founded:
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
    from beacon.council import unvoted  # SPEC_M13

    if unvoted(state, pid, cfg):
        out.append({"kind": "council_vote"})
    for project in sorted(state.projects.values(), key=lambda p: p.id):
        if project.kind == "espionage" and project.offered and project.chooser == pid:
            out.append({"kind": "choose_espionage_tech", "project": project.id})
    return out


REPLACE_CITIZENS = (
    ChooseStory,
    Attack,
    MoveUnit,
    SeatRecruit,
    UnseatRecruit,
    SetCitizenJob,
    AssignBestCitizen,
    AcceptOffer,
)


# -- the leader (docs/SPEC_M11.md) ---------------------------------------------------------------


def _leader_of(state: GameState, pid: str):
    lead = state.players[pid].leader
    if lead is None:
        raise CommandError("no leader")
    return lead


@handles(CreateLeader)
def _create_leader(state: GameState, cfg: Config, cmd: CreateLeader) -> Events:
    from beacon import leader

    if state.turn != 0:
        raise CommandError("the leader is made before the first turn ends")
    skills = {d: int(cmd.skills.get(d, 0)) for d in DOMAINS}
    problem = leader.create_problem(
        cfg, cmd.name, cmd.sex, cmd.look, cmd.age, cmd.traits, dict(cmd.skills)
    )
    if problem:
        raise CommandError(problem)
    old = _leader_of(state, cmd.player)
    old.name, old.sex, old.look, old.start_age = cmd.name.strip(), cmd.sex, cmd.look, cmd.age
    old.traits, old.custom, old.skills = sorted(cmd.traits), True, skills
    return [{"kind": "leader_created", "name": old.name}]


@handles(RaiseSkill)
def _raise_skill(state: GameState, cfg: Config, cmd: RaiseSkill) -> Events:
    from beacon import leader

    lead = _leader_of(state, cmd.player)
    problem = leader.raise_problem(cfg, lead, cmd.skill)
    if problem:
        raise CommandError(problem)
    leader.raise_skill(lead, cmd.skill)
    return [{"kind": "leader_skill", "skill": cmd.skill, "value": lead.skills[cmd.skill]}]


@handles(ChooseLeaderBonus)
def _choose_leader_bonus(state: GameState, cfg: Config, cmd: ChooseLeaderBonus) -> Events:
    from beacon import leader

    lead = _leader_of(state, cmd.player)
    problem = leader.choose_problem(cfg, lead, cmd.choice, cmd.option)
    if problem:
        raise CommandError(problem)
    leader.choose(cfg, lead, cmd.choice, cmd.option)
    return [{"kind": "leader_bonus", "choice": cmd.choice, "option": cmd.option}]


@handles(StartFamily)
def _start_family(state: GameState, cfg: Config, cmd: StartFamily) -> Events:
    from beacon import leader

    problem = leader.family_problem(state, cfg, cmd.player, cmd.partner)
    if problem:
        raise CommandError(problem)
    leader.start_family(state, cfg, cmd.player, cmd.partner)
    due = state.players[cmd.player].leader.due
    return [{"kind": "family_started", "partner": cmd.partner, "due": due}]


@handles(SetWardrobe)
def _set_wardrobe(state: GameState, cfg: Config, cmd: SetWardrobe) -> Events:
    from beacon import leader

    lead = _leader_of(state, cmd.player)
    problem = leader.wardrobe_problem(cfg, cmd.outfit, cmd.accessories)
    if problem:
        raise CommandError(problem)
    lead.outfit, lead.accessories = cmd.outfit, sorted(cmd.accessories)
    return [{"kind": "wardrobe_set", "outfit": cmd.outfit}]


# -- freeing cities other than by siege (docs/SPEC_M12.md) -----------------------------------------


def _alien_city(state: GameState, city_id: int) -> City:
    if not 0 <= city_id < len(state.cities):
        raise CommandError(f"no city {city_id}")
    return state.cities[city_id]


@handles(Sabotage)
def _sabotage(state: GameState, cfg: Config, cmd: Sabotage) -> Events:
    from beacon import threat

    unit, city = own_unit(state, cmd.player, cmd.unit), _alien_city(state, cmd.city)
    problem = threat.sabotage_problem(state, cfg, unit, city)
    if problem:
        raise CommandError(problem)
    return threat.sabotage(state, cfg, unit, city)


@handles(ArmResistance)
def _arm_resistance(state: GameState, cfg: Config, cmd: ArmResistance) -> Events:
    from beacon import threat

    unit, city = own_unit(state, cmd.player, cmd.unit), _alien_city(state, cmd.city)
    problem = threat.arm_problem(state, cfg, unit, city)
    if problem:
        raise CommandError(problem)
    return threat.arm(state, cfg, unit, city)


# -- the council of continents (docs/SPEC_M13.md) -------------------------------------------------


@handles(ProposeMeasure)
def _propose_measure(state: GameState, cfg: Config, cmd: ProposeMeasure) -> Events:
    from beacon import council

    problem = council.propose_problem(state, cfg, cmd.player, cmd.measure)
    if problem:
        raise CommandError(problem)
    return council.propose(state, cfg, cmd.player, cmd.measure)


@handles(CastVote)
def _cast_vote(state: GameState, cfg: Config, cmd: CastVote) -> Events:
    from beacon import council

    problem = council.vote_problem(state, cfg, cmd.player, cmd.measure, cmd.choice, cmd.extra)
    if problem:
        raise CommandError(problem)
    return council.vote(state, cfg, cmd.player, cmd.measure, cmd.choice, cmd.extra)


@handles(SetAgenda)
def _set_agenda(state: GameState, cfg: Config, cmd: SetAgenda) -> Events:
    if state.turn != 0:
        raise CommandError("the agenda is chosen before the first turn ends")
    if cmd.agenda not in cfg.council("agendas"):
        raise CommandError(f"unknown agenda {cmd.agenda!r}")
    state.players[cmd.player].agenda = cmd.agenda
    return [{"kind": "agenda_set", "agenda": cmd.agenda}]


# -- the city builder (docs/SPEC_M16.md) -----------------------------------------------------------


@handles(PlaceBuilding)
def _place_building(state: GameState, cfg: Config, cmd: PlaceBuilding) -> Events:
    from beacon import layout

    city = own_city(state, cmd.player, cmd.city)
    layout.ensure(state, cfg, city)
    if cmd.building not in cfg.buildings:
        raise CommandError(f"unknown building {cmd.building!r}")
    problem = economy.building_allowed(state, cfg, city, cmd.building)
    if problem:
        raise CommandError(problem)
    if layout.pending(city, cmd.building) is not None:
        raise CommandError(f"{cmd.building} is already placed and waiting to be built")
    problem = layout.place_problem(state, cfg, city, cmd.building, cmd.x, cmd.y)
    if problem:
        raise CommandError(problem)
    entry = layout.order(cfg, city, cmd.building, cmd.x, cmd.y)
    item = f"building:{cmd.building}"
    if item not in city.queue:
        city.queue = [*city.queue, item]
    return [
        {"kind": "building_placed", "city": city.id, "building": cmd.building, "entry": entry["id"]}
    ]


@handles(MoveBuilding)
def _move_building(state: GameState, cfg: Config, cmd: MoveBuilding) -> Events:
    from beacon import layout

    city = own_city(state, cmd.player, cmd.city)
    entry = next((e for e in city.layout if e["id"] == cmd.entry), None)
    if entry is None:
        raise CommandError("no such building in this city")
    problem = layout.place_problem(state, cfg, city, entry["what"], cmd.x, cmd.y, skip=entry["id"])
    if problem:
        raise CommandError(problem)
    entry["x"], entry["y"] = cmd.x, cmd.y
    return [{"kind": "building_moved", "city": city.id, "entry": entry["id"]}]


@handles(PlaceWalls)
def _place_walls(state: GameState, cfg: Config, cmd: PlaceWalls) -> Events:
    from beacon import layout

    city = own_city(state, cmd.player, cmd.city)
    layout.ensure(state, cfg, city)
    cells = [(int(c[0]), int(c[1])) for c in cmd.cells]
    problem = layout.wall_problem(state, cfg, city, cells, cmd.material)
    if problem:
        raise CommandError(problem)
    layout.order_walls(city, cells, cmd.material)
    if "walls" not in city.queue:
        city.queue = [*city.queue, "walls"]
    return [{"kind": "walls_ordered", "city": city.id, "pieces": len(cells)}]
