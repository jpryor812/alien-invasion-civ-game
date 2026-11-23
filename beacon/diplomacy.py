"""Deals, aid, alliances, shipping goods and troops between continents (docs/SPEC_M6.md).

Players never fight each other. A deal trades gold (lump or per turn), lent strategic resources,
techs, recruits, units and alliance between two players; the receiver accepts or declines, and
proposals lapse at the end of the turn. A one-sided deal is aid.

Delivery: gold, lent resources, units and alliance take effect at once; techs and recruits travel
as a shipment by sea from the giver's port (a connected coastal city with a Port), arriving after
ceil(distance / speed) turns. A giver with no port sends a convoy unit from its capital, which
must reach a port before the sea leg starts; aliens can capture a lone convoy.

Troops abroad: a unit in its owner's port can be shipped to a known coastal city on another
continent (any player's, or a dormant or empty one to rescue a fallen continent). It keeps its
owner, costs gold, and is off the map while at sea.
"""

from __future__ import annotations

from typing import Any

from beacon import economy, hexgrid, tech, techfx
from beacon.cities import is_coastal
from beacon.config import Config
from beacon.liberation import credit
from beacon.state import (  # noqa: F401  (Deal re-exported for actions)
    ACTIVE,
    DORMANT,
    EMPTY,
    City,
    Deal,
    DealTerms,
    GameState,
    Shipment,
    Unit,
)
from beacon.units import place_unit, remove_unit

Events = list[dict[str, Any]]
TERM_KEYS = (
    "gold",
    "gold_per_turn",
    "resources",
    "techs",
    "recruits",
    "units",
    "alliance",
    "materials",
    "materials_per_turn",
)


def terms_from(data: dict[str, Any]) -> DealTerms:
    unknown = set(data) - set(TERM_KEYS)
    if unknown:
        raise ValueError(f"unknown deal terms {sorted(unknown)}")
    return DealTerms(
        gold=int(data.get("gold", 0)),
        gold_per_turn=int(data.get("gold_per_turn", 0)),
        resources={k: int(v) for k, v in data.get("resources", {}).items()},
        techs=list(data.get("techs", [])),
        recruits=[int(r) for r in data.get("recruits", [])],
        units=[int(u) for u in data.get("units", [])],
        alliance=bool(data.get("alliance", False)),
        materials={k: int(v) for k, v in data.get("materials", {}).items()},
        materials_per_turn={k: int(v) for k, v in data.get("materials_per_turn", {}).items()},
    )


def is_empty(t: DealTerms) -> bool:
    return not (
        t.gold
        or t.gold_per_turn
        or t.resources
        or t.techs
        or t.recruits
        or t.units
        or t.alliance
        or t.materials
        or t.materials_per_turn
    )


# -- materials in deals (SPEC_M21): drawn from the giver's towns, richest first, into the
# receiver's capital ----------------------------------------------------------------------------


def stock(state: GameState, pid: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for c in state.cities:
        if c.owner == pid and c.status == "active":
            for g, n in c.stores.items():
                out[g] = out.get(g, 0) + n
    return out


def move_materials(state: GameState, giver: str, receiver: str, goods: dict[str, int]) -> bool:
    """Move goods between treasuries; False (and nothing moved) if the giver is short."""
    have = stock(state, giver)
    if any(have.get(g, 0) < n for g, n in goods.items()):
        return False
    to = capital(state, receiver)
    if to is None:
        return False
    for g, n in sorted(goods.items()):
        left = n
        towns = [c for c in state.cities if c.owner == giver and c.status == "active"]
        for c in sorted(towns, key=lambda c: (-c.stores.get(g, 0), c.id)):
            take = min(left, c.stores.get(g, 0))
            c.stores[g] = c.stores.get(g, 0) - take
            left -= take
            if not left:
                break
        to.stores[g] = to.stores.get(g, 0) + n
    return True


def ports(state: GameState, cfg: Config, pid: str) -> list[City]:
    return [
        c
        for c in state.cities
        if c.owner == pid
        and c.status == ACTIVE
        and c.connected
        and "port" in c.buildings
        and is_coastal(state, cfg, c)
    ]


def capital(state: GameState, pid: str) -> City | None:
    return next((c for c in state.cities if c.owner == pid and c.is_capital), None)


def sea_turns(cfg: Config, distance: int) -> int:
    speed = cfg.t("trade.shipping.speed")
    return max(1, -(-distance // speed))


def allied(state: GameState, a: str, b: str) -> bool:
    return b in state.players[a].allies


# -- validation --------------------------------------------------------------------------------


def terms_problem(
    state: GameState, cfg: Config, giver: str, receiver: str, t: DealTerms, duration: int
) -> str | None:
    """None if `giver` can give `t` to `receiver`, else the reason."""
    g, r = state.players[giver], state.players[receiver]
    if t.gold < 0 or t.gold_per_turn < 0 or any(v <= 0 for v in t.resources.values()):
        return "amounts must be positive"
    goods = {**t.materials, **t.materials_per_turn}
    if any(v <= 0 for v in goods.values()):
        return "amounts must be positive"
    from beacon import materials as mats

    for good in goods:
        if good not in mats.goods(cfg):
            return f"{good} is not a material"
    have = stock(state, giver)
    for good, n in t.materials.items():
        if have.get(good, 0) < n:
            return f"{giver} has only {have.get(good, 0)} {good}"
    if t.materials_per_turn and duration not in cfg.t("trade.deals.durations"):
        return f"duration must be one of {cfg.t('trade.deals.durations')}"
    if t.gold > g.gold:
        return f"{giver} has only {g.gold} gold"
    if (t.gold_per_turn or t.resources) and duration not in cfg.t("trade.deals.durations"):
        return f"duration must be one of {cfg.t('trade.deals.durations')}"
    if t.resources:
        supply = economy.resource_supply(state, cfg, giver)
        usage = economy.resource_usage(state, cfg, giver)
        for res, n in t.resources.items():
            if res not in supply:
                return f"{res} is not a strategic resource"
            if supply[res] - usage.get(res, 0) < n:
                return f"{giver} has no {n} spare {res}"
    for name in t.techs:
        if name not in g.techs:
            return f"{giver} does not know {name}"
        if name not in tech.available(cfg, r):
            return f"{receiver} cannot learn {name} yet"
    for rid in t.recruits:
        rec = state.recruits.get(str(rid))
        if rec is None or rec.patron != giver:
            return f"{giver} has no recruit {rid}"
    for uid in t.units:
        unit = state.units.get(str(uid))
        if unit is None or unit.owner != giver:
            return f"{giver} has no unit {uid}"
        near = any(
            c.owner == receiver and hexgrid.distance(c.tile, unit.tile, state.width) <= 1
            for c in state.cities
        )
        if not near:
            return f"unit {uid} must stand in or next to a {receiver} city"
    if t.alliance:
        needed = cfg.t("trade.alliance_tech")
        if needed not in g.techs or needed not in r.techs:
            return f"both sides need {needed} to ally"
        if allied(state, giver, receiver):
            return "already allied"
    return None


def deal_problem(state: GameState, cfg: Config, deal: Deal) -> str | None:
    """None if the deal can go ahead now. An alliance is mutual: set it on both sides."""
    if deal.proposer == deal.receiver:
        return "a deal needs two players"
    if is_empty(deal.give) and is_empty(deal.take):
        return "the deal is empty"
    if deal.give.alliance != deal.take.alliance:
        return "an alliance must be on both sides of the deal"
    return terms_problem(
        state, cfg, deal.proposer, deal.receiver, deal.give, deal.duration
    ) or terms_problem(state, cfg, deal.receiver, deal.proposer, deal.take, deal.duration)


def propose(
    state: GameState,
    cfg: Config,
    proposer: str,
    receiver: str,
    give: DealTerms,
    take: DealTerms,
    duration: int,
) -> Deal:
    deal = Deal(
        id=state.new_id(),
        proposer=proposer,
        receiver=receiver,
        give=give,
        take=take,
        duration=duration,
        proposed_turn=state.turn,
    )
    state.deals[str(deal.id)] = deal
    return deal


# -- executing ---------------------------------------------------------------------------------


def _ship_goods(state: GameState, cfg: Config, giver: str, receiver: str, t: DealTerms) -> Events:
    if not t.techs and not t.recruits:
        return []
    for rid in t.recruits:
        rec = state.recruits[str(rid)]
        rec.patron, rec.seats = None, []
    shipment = Shipment(
        id=state.new_id(),
        from_player=giver,
        to_player=receiver,
        techs=list(t.techs),
        recruits=list(t.recruits),
    )
    state.shipments[str(shipment.id)] = shipment
    return _depart_or_convoy(state, cfg, shipment)


def _depart_or_convoy(state: GameState, cfg: Config, shipment: Shipment) -> Events:
    giver, receiver = shipment.from_player, shipment.to_player
    home = ports(state, cfg, giver)
    dest = capital(state, receiver)
    if home:
        target = dest.tile if dest else home[0].tile
        port = min(home, key=lambda c: (hexgrid.distance(c.tile, target, state.width), c.id))
        shipment.arrive_turn = state.turn + sea_turns(
            cfg, hexgrid.distance(port.tile, target, state.width)
        )
        return [
            {
                "turn": state.turn,
                "kind": "shipment_sailed",
                "player": giver,
                "shipment": shipment.id,
                "to": receiver,
                "arrives": shipment.arrive_turn,
            }
        ]
    origin = capital(state, giver)
    if origin is None:
        shipment.arrive_turn = state.turn + 1  # nothing to protect: it simply goes
        return []
    convoy = place_unit(state, cfg, "trade_convoy", giver, origin.tile, cfg.t("cities.work_radius"))
    if convoy is None:
        shipment.arrive_turn = state.turn + 1
        return []
    shipment.convoy = convoy.id
    return [
        {
            "turn": state.turn,
            "kind": "convoy_formed",
            "player": giver,
            "shipment": shipment.id,
            "unit": convoy.id,
        }
    ]


def _apply_now(state: GameState, cfg: Config, giver: str, receiver: str, t: DealTerms) -> Events:
    g, r = state.players[giver], state.players[receiver]
    g.gold -= t.gold
    r.gold += t.gold
    if t.materials:
        move_materials(state, giver, receiver, t.materials)
    for uid in t.units:
        unit = state.units[str(uid)]
        unit.owner = receiver
        unit.fortified = False
    if t.alliance and receiver not in g.allies:
        g.allies = sorted([*g.allies, receiver])
        r.allies = sorted([*r.allies, giver])
    return _ship_goods(state, cfg, giver, receiver, t)


def accept(state: GameState, cfg: Config, deal: Deal) -> Events:
    events: Events = [
        {
            "turn": state.turn,
            "kind": "deal_accepted",
            "player": deal.receiver,
            "deal": deal.id,
            "proposer": deal.proposer,
        }
    ]
    events += _apply_now(state, cfg, deal.proposer, deal.receiver, deal.give)
    events += _apply_now(state, cfg, deal.receiver, deal.proposer, deal.take)
    for giver, t, other in (
        (deal.proposer, deal.give, deal.take),
        (deal.receiver, deal.take, deal.give),
    ):
        if is_empty(other) and not is_empty(t):
            credit(state, giver, "aid_gold", t.gold + t.gold_per_turn * deal.duration)
            credit(state, giver, "aid_units", len(t.units))
            credit(state, giver, "aid_techs", len(t.techs))
            credit(state, giver, "recruits_given", len(t.recruits))
    lasting = any(
        x.gold_per_turn or x.resources or x.materials_per_turn for x in (deal.give, deal.take)
    )
    if lasting:
        deal.active = True
        deal.ends_turn = state.turn + deal.duration
    else:
        del state.deals[str(deal.id)]
    return events


def end_of_turn(state: GameState, cfg: Config) -> Events:
    """Per-turn payments, deal expiry, lapsed proposals, convoys and arrivals."""
    events: Events = []
    for key in sorted(state.deals, key=int):
        deal = state.deals[key]
        if not deal.active:
            del state.deals[key]  # an unanswered proposal lapses
            continue
        broken = False
        for giver, receiver, t in (
            (deal.proposer, deal.receiver, deal.give),
            (deal.receiver, deal.proposer, deal.take),
        ):
            if t.gold_per_turn:
                if state.players[giver].gold < t.gold_per_turn:
                    broken = True
                    continue
                state.players[giver].gold -= t.gold_per_turn
                state.players[receiver].gold += t.gold_per_turn
            if t.materials_per_turn and not move_materials(
                state, giver, receiver, t.materials_per_turn
            ):
                broken = True
        if broken or (deal.ends_turn is not None and state.turn + 1 >= deal.ends_turn):
            del state.deals[key]
            events.append(
                {
                    "turn": state.turn,
                    "kind": "deal_ended",
                    "player": deal.proposer,
                    "deal": deal.id,
                    "broken": broken,
                }
            )
    for key in sorted(state.shipments, key=int):
        s = state.shipments[key]
        if s.arrive_turn is None:
            events += _convoy_step(state, cfg, s)
        elif state.turn + 1 >= s.arrive_turn:
            events += _arrive(state, cfg, s)
    return events


def _convoy_step(state: GameState, cfg: Config, s: Shipment) -> Events:
    convoy = state.units.get(str(s.convoy)) if s.convoy is not None else None
    if convoy is None:
        for rid in s.recruits:
            state.recruits.pop(str(rid), None)
        del state.shipments[str(s.id)]
        return [
            {"turn": state.turn, "kind": "convoy_lost", "player": s.from_player, "shipment": s.id}
        ]
    city = state.city_at(convoy.tile)
    if city is not None and city in ports(state, cfg, s.from_player):
        remove_unit(state, convoy)
        s.convoy = None
        dest = capital(state, s.to_player)
        dist = hexgrid.distance(city.tile, dest.tile if dest else city.tile, state.width)
        s.arrive_turn = state.turn + sea_turns(cfg, dist)
        return [
            {
                "turn": state.turn,
                "kind": "shipment_sailed",
                "player": s.from_player,
                "shipment": s.id,
                "to": s.to_player,
                "arrives": s.arrive_turn,
            }
        ]
    return []


def _arrive(state: GameState, cfg: Config, s: Shipment) -> Events:
    events: Events = []
    if s.unit is not None:
        placed = _land_unit(state, cfg, s)
        if not placed:
            return []  # no room yet: try again next turn
        events += placed
    receiver = state.players[s.to_player]
    for name in s.techs:
        if name not in receiver.techs:
            receiver.techs = sorted([*receiver.techs, name])
    for rid in s.recruits:
        rec = state.recruits.get(str(rid))
        if rec is not None:
            rec.patron = s.to_player
    del state.shipments[str(s.id)]
    events.append(
        {
            "turn": state.turn,
            "kind": "shipment_arrived",
            "player": s.to_player,
            "shipment": s.id,
            "from": s.from_player,
        }
    )
    return events


# -- troops abroad -----------------------------------------------------------------------------


def ship_problem(
    state: GameState, cfg: Config, unit: Unit, city_id: int, known: set[int]
) -> str | None:
    if unit.job is not None or unit.moves_left <= 0:
        return "the unit cannot move this turn"
    if cfg.units[unit.type]["domain"] != "land":
        return "only land units are shipped"
    here = state.city_at(unit.tile)
    if here is None or here not in ports(state, cfg, unit.owner):
        return "units sail from their owner's connected port city"
    if not 0 <= city_id < len(state.cities):
        return f"no city {city_id}"
    dest = state.cities[city_id]
    if city_id not in known:
        return "destination unknown"
    if dest.continent == here.continent:
        return "destination must be on another continent"
    if not is_coastal(state, cfg, dest):
        return "destination must be coastal"
    if dest.status not in (ACTIVE, DORMANT, EMPTY) or (
        dest.status == ACTIVE and dest.owner not in state.players
    ):
        return "destination must be a player city, or a dormant or empty one"
    price = ship_price(state, cfg, here, dest)
    if state.players[unit.owner].gold < price:
        return f"shipping costs {price} gold"
    return None


def ship_price(state: GameState, cfg: Config, here: City, dest: City) -> int:
    s = cfg.t("trade.shipping")
    dist = hexgrid.distance(here.tile, dest.tile, state.width)
    return s["unit_base_gold"] + s["unit_per_10_hexes_gold"] * dist // 10


def ship_unit(state: GameState, cfg: Config, unit: Unit, city_id: int) -> Events:
    here = state.city_at(unit.tile)
    assert here is not None
    dest = state.cities[city_id]
    price = ship_price(state, cfg, here, dest)
    state.players[unit.owner].gold -= price
    remove_unit(state, unit)
    unit.fortified, unit.order, unit.acted = False, "none", True
    shipment = Shipment(
        id=state.new_id(),
        from_player=unit.owner,
        to_player=unit.owner,
        unit=unit,
        dest_city=city_id,
        arrive_turn=state.turn
        + max(
            1,
            sea_turns(cfg, hexgrid.distance(here.tile, dest.tile, state.width))
            * (
                100 + techfx.total(cfg, state.players[unit.owner], "ship_time_pct")
            )  # Orbital Launch
            // 100,
        ),
    )
    state.shipments[str(shipment.id)] = shipment
    return [
        {
            "turn": state.turn,
            "kind": "unit_shipped",
            "player": unit.owner,
            "unit": unit.id,
            "to_city": city_id,
            "arrives": shipment.arrive_turn,
            "gold": price,
        }
    ]


def _land_unit(state: GameState, cfg: Config, s: Shipment) -> Events:
    from beacon.movement import _enter
    from beacon.units import free_tile_near

    unit = s.unit
    assert unit is not None and s.dest_city is not None
    dest = state.cities[s.dest_city]
    tile = free_tile_near(state, cfg, unit.type, unit.owner, dest.tile, cfg.t("cities.work_radius"))
    if tile is None:
        return []
    unit.tile = tile
    state.units[str(unit.id)] = unit
    s.unit = None
    events: Events = [
        {
            "turn": state.turn,
            "kind": "unit_landed",
            "player": unit.owner,
            "unit": unit.id,
            "city": dest.id,
        }
    ]
    events += _enter(state, cfg, unit, tile)  # fog; a military unit reclaims a dormant city
    return events


def units_abroad(state: GameState, pid: str) -> int:
    """Unit members on another continent (player ids are continent ids)."""
    return sum(
        u.count
        for u in state.units.values()
        if u.owner == pid and state.tiles[u.tile].continent != pid
    )
