"""Cities and economy: worked tiles, yields with breakdowns, growth, production, gold, research.

Every yield total is the sum of its breakdown lines `(source, yield, amount)`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from beacon import citizens, tech, techfx
from beacon.cities import is_coastal, max_hp
from beacon.config import YIELDS, Config
from beacon.recruits import council_lines
from beacon.state import ACTIVE, City, GameState, Player
from beacon.tiles import Line, resource_active, tile_yields, totals
from beacon.units import place_unit, slot_kind

PROJECTS = ("wealth", "research", "barrage")
COUNCIL_YIELDS = ("food", "production", "science", "gold", "beacon")  # military: combat
PROJECT_YIELD = {"wealth": "gold", "research": "science"}
FOCUSES = ("balanced", "food", "production", "science", "gold")


@dataclass
class CityYields:
    lines: list[Line]
    totals: dict[str, int]
    worked: list[int]
    food_eaten: int
    fraction: dict[str, int]  # hundredths left over from citizens' half stats (see citizens.py)

    @property
    def surplus_food(self) -> int:
        return self.totals["food"] - self.food_eaten


# -- yields ------------------------------------------------------------------------------------


def city_yields(state: GameState, cfg: Config, city: City) -> CityYields:
    lines: list[Line] = []

    def add(source: str, yields: dict[str, int]) -> None:
        for y in YIELDS:
            if yields.get(y):
                lines.append((source, y, yields[y]))

    add("city_tile", tile_yields(cfg, state.tiles[city.tile]))
    add("city_centre", cfg.t("economy.city_center_yields"))
    if city.connected and not city.is_capital:  # SPEC_M10: a road to the capital pays
        add("connection", {"gold": cfg.t("economy.connection_gold")})
    if city.is_capital:
        cap = cfg.t("cities.capital")
        add("palace", {"food": cap["food"], "production": cap["production"]})
    worked, people, fraction = citizens.city_lines(state, cfg, city)
    lines.extend(people)
    from beacon import winter  # farm techs and the galactic winter (SPEC_M19)

    lines.extend(winter.food_lines(state, cfg, city, worked, state.players.get(city.owner or "")))
    add("population", {"science": city.pop * cfg.t("economy.science_per_pop_pct") // 100})
    for b in city.buildings:
        add(f"building:{b}", cfg.buildings[b]["yields"])
    owner = state.players.get(city.owner or "")
    for t, value in techfx.lines(cfg, owner, "city_yields"):
        add(f"tech:{t}", value)
    subtotal = totals(lines)
    for b in city.buildings:
        for y, pct in cfg.buildings[b]["yield_pct"].items():
            bonus = max(0, subtotal[y]) * pct // 100
            if bonus:
                lines.append((f"building:{b} +{pct}%", y, bonus))
    for t, value in techfx.lines(cfg, owner, "yield_pct"):
        for y, pct in value.items():
            bonus = max(0, subtotal[y]) * pct // 100
            if bonus:
                lines.append((f"tech:{t} +{pct}%", y, bonus))
    if city.owner in state.players:
        for y in COUNCIL_YIELDS:
            for source, pct in council_lines(state, city.owner, y):
                bonus = max(0, subtotal[y]) * pct // 100
                if bonus:
                    lines.append((f"{source} +{pct}%", y, bonus))
    return CityYields(
        lines=lines,
        totals=totals(lines),
        worked=worked,
        food_eaten=citizens.food_eaten(state, cfg, city),
        fraction=fraction,
    )


def growth_threshold(cfg: Config, pop: int) -> int:
    k = max(0, pop - 1)
    return (
        cfg.t("economy.growth_base")
        + cfg.t("economy.growth_per_pop") * k
        + cfg.t("economy.growth_quad") * k * k
    )


# -- production options ------------------------------------------------------------------------


def building_allowed(state: GameState, cfg: Config, city: City, b: str) -> str | None:
    """None if the city may build `b`, else the reason it may not."""
    spec = cfg.buildings[b]
    player = state.players.get(city.owner or "")
    if player is None:
        return "city has no player owner"
    if b in city.buildings:
        return "already built"
    if not tech.knows(player, spec["tech"]):
        return f"needs tech {spec['tech']}"
    req = spec.get("requires_building")
    if req and req not in city.buildings:
        return f"needs building {req}"
    if spec.get("coastal") and not is_coastal(state, cfg, city):
        return "needs a coastal city"
    return None


def unit_allowed(state: GameState, cfg: Config, city: City, u: str) -> str | None:
    spec = cfg.units[u]
    player = state.players.get(city.owner or "")
    if player is None:
        return "city has no player owner"
    if spec["faction"] != "player" or spec.get("not_buildable"):
        return "not a buildable unit"
    if not tech.knows(player, spec["tech"]):
        return f"needs tech {spec['tech']}"
    if spec["domain"] == "sea" and not is_coastal(state, cfg, city):
        return "needs a coastal city"
    from beacon.materials import needs_barracks  # designer 2026-11-16

    barracks = cfg.materials("barracks.building")
    if needs_barracks(cfg, u) and barracks not in city.buildings:
        return "needs a barracks"
    if spec.get("fixed") and any(
        other.owner == city.owner and slot_kind(cfg, other.type) == slot_kind(cfg, u)
        for other in state.units_at(city.tile)
    ):
        return (
            "the city already has one" if spec.get("air") else "the city already has a defense unit"
        )
    return None


def item_allowed(state: GameState, cfg: Config, city: City, item: str) -> str | None:
    if item == "walls":  # SPEC_M17: walls are works for the crew now
        return "walls are built by the city's engineers"
    if item == "engineer":  # one more engineer for the crew (SPEC_M17)
        return None if city.owner in state.players else "city has no player owner"
    kind, _, ident = item.partition(":")
    if kind == "building":
        return building_allowed(state, cfg, city, ident) if ident in cfg.buildings else "unknown"
    if kind == "unit":
        return unit_allowed(state, cfg, city, ident) if ident in cfg.units else "unknown"
    if kind == "project":
        if ident not in PROJECTS:
            return "unknown project"
        if ident == "barrage":
            from beacon.endgame import barrage_needs  # endgame imports this module's users

            if barrage_needs(state) is None:
                return "the barrage is not under way or is fully paid"
        return None
    return f"unknown item kind {kind!r}"


def production_options(state: GameState, cfg: Config, city: City) -> list[str]:
    """What the production queue can hold: engineers, units and projects (SPEC_M17 - buildings
    and walls are works for the crew)."""
    items = ["engineer", *(f"unit:{u}" for u in sorted(cfg.units))]
    items += [f"project:{p}" for p in PROJECTS]
    return [i for i in items if item_allowed(state, cfg, city, i) is None]


def building_options(state: GameState, cfg: Config, city: City) -> list[str]:
    """Buildings the city may order as works now (materials aside)."""
    from beacon import works

    return [
        b
        for b in sorted(cfg.buildings)
        if building_allowed(state, cfg, city, b) is None
        and not works.ordered(city, f"building:{b}")
    ]


def item_cost(
    cfg: Config, item: str, player: Player | None = None, city: City | None = None
) -> int:
    """Production cost; units cost less with Mass Production (tech effect unit_cost_pct). Walls
    (SPEC_M16) cost the production of the pieces the city has ordered."""
    if item == "engineer":
        from beacon import works

        return (
            works.engineer_cost(cfg, city) if city is not None else cfg.materials("engineers.cost")
        )
    kind, _, ident = item.partition(":")
    if kind == "building":
        return cfg.buildings[ident]["cost"]
    if kind == "unit":
        pct = 100 + techfx.total(cfg, player, "unit_cost_pct")
        return cfg.units[ident]["cost"] * pct // 100
    raise ValueError(f"{item} has no cost")


def purchase_price(
    cfg: Config, item: str, player: Player | None, progress: int = 0, city: City | None = None
) -> int:
    """Gold to buy an item outright (Automated Markets lowers it: tech effect purchase_pct). The
    production already put into the item lowers the price in proportion (SPEC_M10)."""
    cost = item_cost(cfg, item, player, city)
    base = cost * cfg.t("economy.purchase_pct") // 100
    full = base * (100 + techfx.total(cfg, player, "purchase_pct")) // 100
    left = max(0, cost - progress)
    return max(1, full * left // cost) if cost else full


def stored(city: City, item: str | None) -> int:
    """Production already put into `item` in this city (each item keeps its own, SPEC_M10)."""
    return city.progress.get(item, 0) if item else 0


# -- strategic resources -----------------------------------------------------------------------


def resource_supply(state: GameState, cfg: Config, pid: str) -> dict[str, int]:
    linked = {c.id for c in state.cities if c.owner == pid and c.status == ACTIVE and c.connected}
    supply = {r: 0 for r, spec in cfg.resources.items() if spec["category"] == "strategic"}
    for tile in state.tiles:
        if tile.city in linked and tile.resource in supply and resource_active(cfg, tile):
            supply[tile.resource] += cfg.resources[tile.resource]["quantity"]
    for res, n in lent(state, pid).items():
        supply[res] += n
    return supply


def lent(state: GameState, pid: str) -> dict[str, int]:
    """Net strategic resources a player has lent out (negative) or borrowed (positive) through
    active deals (docs/SPEC_M6.md)."""
    out: dict[str, int] = {}
    for deal in state.deals.values():
        if not deal.active:
            continue
        for giver, receiver, terms in (
            (deal.proposer, deal.receiver, deal.give),
            (deal.receiver, deal.proposer, deal.take),
        ):
            for res, n in terms.resources.items():
                if giver == pid:
                    out[res] = out.get(res, 0) - n
                if receiver == pid:
                    out[res] = out.get(res, 0) + n
    return out


def resource_usage(state: GameState, cfg: Config, pid: str) -> dict[str, int]:
    usage: dict[str, int] = {}
    for unit in state.units.values():
        res = cfg.units[unit.type].get("requires_resource")
        if unit.owner == pid and res:
            usage[res] = usage.get(res, 0) + unit.count
    return usage


def resource_available(state: GameState, cfg: Config, pid: str, unit_type: str) -> bool:
    res = cfg.units[unit_type].get("requires_resource")
    if not res:
        return True
    return resource_supply(state, cfg, pid)[res] - resource_usage(state, cfg, pid).get(res, 0) > 0


# -- completing items --------------------------------------------------------------------------


def complete_item(state: GameState, cfg: Config, city: City, item: str) -> dict[str, Any] | None:
    """Finish an item. Returns an event, or None if it cannot complete yet (unit has no room or
    no strategic resource)."""
    from beacon import layout, materials  # SPEC_M16

    cost = materials.item_cost(cfg, city, item)
    if materials.short(city, cost):
        return None
    if item == "engineer":  # SPEC_M17
        from beacon import works

        works.ensure_crew(cfg, city)
        city.engineers += 1
        return {"kind": "engineer_trained", "city": city.id, "engineers": city.engineers}
    kind, _, ident = item.partition(":")
    if kind == "building":
        materials.pay(city, cost)
        city.buildings = sorted([*city.buildings, ident])
        layout.complete(state, cfg, city, ident)
        city.hp = min(max_hp(cfg, city), city.hp + cfg.buildings[ident].get("city_hp", 0))
        return {"kind": "building_completed", "city": city.id, "building": ident}
    if not resource_available(state, cfg, city.owner, ident):
        return None
    unit = place_unit(state, cfg, ident, city.owner, city.tile, cfg.t("cities.work_radius"))
    if unit is None:
        return None
    materials.pay(city, cost)
    return {"kind": "unit_completed", "city": city.id, "unit": unit.id, "type": ident}


def unit_bonus_lines(cfg: Config, city: City, production: int) -> list[Line]:
    lines = []
    for b in city.buildings:
        pct = cfg.buildings[b].get("unit_production_pct", 0)
        if pct:
            lines.append((f"building:{b} units +{pct}%", "production", production * pct // 100))
    return lines


def process_city(
    state: GameState, cfg: Config, city: City, player: Player, army: list[Any] | None = None
) -> tuple[list[dict[str, Any]], int]:
    """One turn for an active city: growth and production. Adds its gold and beacon
    points to `player` and returns (events, science) for the caller to settle research."""
    events: list[dict[str, Any]] = []
    cy = city_yields(state, cfg, city)
    # carry fractions of citizens' half stats (+1.5 is +1 one turn and +2 the next)
    for y, v in cy.fraction.items():
        carry = city.yield_carry.get(y, 0) + v
        if carry >= 100:
            cy.totals[y] += carry // 100
        city.yield_carry[y] = carry % 100

    # convoys: goods that arrived for this city, and the share this city sends away (SPEC_M10)
    from beacon import convoys  # convoys imports diplomacy, which imports this module

    arrived, city.incoming = city.incoming, {}
    production_in, surplus = convoys.send(
        state, city, cy.totals["production"], cy.surplus_food + arrived.get("food", 0)
    )
    # the town feeds its army from what its citizens leave (SPEC_M18)
    from beacon import food

    surplus = food.feed(state, cfg, city, army or [], surplus)
    # growth: food brings births, and children grow up faster in a well-fed city
    events.extend(citizens.grow(state, cfg, city, surplus))
    growth = techfx.total(cfg, player, "growth_pct")  # Urban Planning
    city.food_store += surplus * (100 + growth) // 100 if surplus > 0 else surplus
    city.food_store = min(city.food_store, food.store_cap(cfg, city))  # the granary
    threshold = growth_threshold(cfg, city.pop)
    if city.grow and city.food_store >= threshold:
        city.food_store -= threshold
        city.pop += 1
        events.append({"kind": "city_grew", "city": city.id, "pop": city.pop})
        events.append(citizens.born(state, cfg, city))
    elif city.food_store < 0:
        city.food_store = 0
        if city.pop > 1:
            city.pop -= 1
            citizens.remove_youngest(state, city)
            events.append({"kind": "city_starved", "city": city.id, "pop": city.pop})

    # materials from the tiles it works (SPEC_M16)
    from beacon import materials

    materials.gather(state, cfg, city, cy.worked)
    # the crew's labour on the city's works (SPEC_M17)
    from beacon import works

    events.extend(works.progress(state, cfg, city))
    # production
    production = production_in + arrived.get("production", 0)
    head = city.queue[0] if city.queue else None
    if head == "project:barrage":
        from beacon.endgame import city_contribution

        city_contribution(state, cfg, player.id, production)
    elif head and head.startswith("project:"):
        out = PROJECT_YIELD[head.split(":", 1)[1]]
        cy.totals[out] += production * cfg.t("economy.project_conversion_pct") // 100
    else:
        if head and head.startswith("unit:"):
            production += sum(v for _, _, v in unit_bonus_lines(cfg, city, production))
        # each item keeps its own progress; switching away keeps it, a new item starts at 0.
        # What is left over when an item finishes carries to the next, up to one turn's worth.
        if head is None:
            city.production_store = production
        else:
            carry, city.production_store = city.production_store, 0
            city.progress[head] = city.progress.get(head, 0) + production + carry
            cost = item_cost(cfg, head, player, city)
            if city.progress[head] >= cost:
                if item_allowed(state, cfg, city, head) is not None:
                    city.queue.pop(0)
                    events.append({"kind": "item_dropped", "city": city.id, "item": head})
                else:
                    done = complete_item(state, cfg, city, head)
                    if done is None:
                        from beacon import materials

                        lack = materials.short(city, materials.item_cost(cfg, city, head))
                        events.append(
                            {"kind": "production_stalled", "city": city.id, "item": head}
                            | ({"needs": lack} if lack else {})
                        )
                    else:
                        over = city.progress.pop(head) - cost
                        city.production_store = min(over, production)
                        city.queue.pop(0)
                        events.append(done)

    player.gold += cy.totals["gold"]
    player.beacon_points += cy.totals["beacon"]
    for e in events:
        e.setdefault("turn", state.turn)
        e.setdefault("player", player.id)
    return events, cy.totals["science"]


def maintenance(state: GameState, cfg: Config, pid: str) -> int:
    from beacon import works  # the crew's pay (SPEC_M17)

    return works.upkeep(state, cfg, pid) + sum(
        cfg.buildings[b]["maintenance"]
        for c in state.cities
        if c.owner == pid and c.status == ACTIVE
        for b in c.buildings
    )


def road_upkeep(state: GameState, cfg: Config, pid: str) -> int:
    from beacon.network import unlinked_routes  # network imports nothing from here at load

    return unlinked_routes(state, pid) * cfg.t("economy.unlinked_road_upkeep")


def unit_upkeep(state: GameState, cfg: Config, pid: str) -> int:
    members = sum(
        u.count
        for u in state.units.values()
        if u.owner == pid and not cfg.units[u.type].get("no_upkeep")  # the survivor band
    )
    cities_n = sum(1 for c in state.cities if c.owner == pid and c.status == ACTIVE)
    per_city = cfg.t("economy.free_units_per_city")
    per_city += techfx.total(
        cfg, state.players.get(pid), "free_upkeep_per_city"
    )  # Militia Reserves
    free = per_city * cities_n
    abroad = sum(
        u.count
        for u in state.units.values()
        if u.owner == pid and state.tiles[u.tile].continent != pid
    )
    extra = abroad * cfg.t("economy.unit_upkeep") * cfg.t("trade.abroad_upkeep_pct") // 100
    return max(0, members - free) * cfg.t("economy.unit_upkeep") + extra


def player_turn(state: GameState, cfg: Config, pid: str) -> list[dict[str, Any]]:
    """Process every active city of a player, then gold and research."""
    player = state.players[pid]
    events: list[dict[str, Any]] = []
    science = 0
    citizens.assign(state, cfg, pid)
    from beacon import food  # SPEC_M18

    armies = food.armies(state, cfg, pid)
    for city in state.cities:
        if city.owner != pid or city.status != ACTIVE:  # SPEC_M10: no road needed to produce
            continue
        city_events, city_science = process_city(state, cfg, city, player, armies.get(city.id))
        events.extend(city_events)
        science += city_science
    events.extend(citizens.train(state, cfg, pid))  # citizens become soldiers (2026-11-17)
    cost = (
        maintenance(state, cfg, pid) + unit_upkeep(state, cfg, pid) + road_upkeep(state, cfg, pid)
    )
    player.gold -= cost
    if player.gold < 0:
        shortfall = -player.gold
        player.gold = 0
        if not techfx.total(cfg, player, "keep_research_on_deficit"):  # Sovereign Bonds
            player.research_progress = max(0, player.research_progress - shortfall)
        events.append(
            {"turn": state.turn, "kind": "gold_deficit", "player": pid, "shortfall": shortfall}
        )
    learned = tech.progress(cfg, player, science, state.turn)
    events.extend(learned)
    if any(e["tech"] == cfg.t("contact.beacon_tech") for e in learned):
        from beacon.contact import beacon_contact  # contact imports fog, which imports this

        events.extend(beacon_contact(state, cfg, pid))
    return events
