"""Cities and economy: worked tiles, yields with breakdowns, growth, production, gold, research.

Every yield total is the sum of its breakdown lines `(source, yield, amount)`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from beacon import tech
from beacon.cities import is_coastal, max_hp, work_tiles
from beacon.config import YIELDS, Config
from beacon.recruits import council_lines
from beacon.state import ACTIVE, City, GameState, Player
from beacon.tiles import Line, resource_active, tile_yields, totals
from beacon.units import hostile, occupancy, place_unit

PROJECTS = ("wealth", "research")
COUNCIL_YIELDS = ("food", "production", "science", "gold", "beacon")  # military: combat
PROJECT_YIELD = {"wealth": "gold", "research": "science"}
FOCUSES = ("balanced", "food", "production", "science", "gold")


@dataclass
class CityYields:
    lines: list[Line]
    totals: dict[str, int]
    worked: list[int]
    food_eaten: int

    @property
    def surplus_food(self) -> int:
        return self.totals["food"] - self.food_eaten


# -- yields ------------------------------------------------------------------------------------


def choose_worked(state: GameState, cfg: Config, city: City) -> list[int]:
    weights = cfg.t("economy.focus_weights")[city.focus]
    occ = occupancy(state)
    options = []
    for t in work_tiles(state, cfg, city):
        if any(hostile(u.owner, city.owner or "") for u in occ.get(t, [])):
            continue
        ty = tile_yields(cfg, state.tiles[t])
        options.append((-sum(weights[y] * ty[y] for y in YIELDS), t))
    options.sort()
    return sorted(t for _, t in options[: city.pop])


def city_yields(state: GameState, cfg: Config, city: City) -> CityYields:
    lines: list[Line] = []

    def add(source: str, yields: dict[str, int]) -> None:
        for y in YIELDS:
            if yields.get(y):
                lines.append((source, y, yields[y]))

    add("city_tile", tile_yields(cfg, state.tiles[city.tile]))
    add("city_centre", cfg.t("economy.city_center_yields"))
    worked = choose_worked(state, cfg, city)
    worked_sum = dict.fromkeys(YIELDS, 0)
    for t in worked:
        for y, v in tile_yields(cfg, state.tiles[t]).items():
            worked_sum[y] += v
    add("worked_tiles", worked_sum)
    add("population", {"science": city.pop * cfg.t("economy.science_per_pop_pct") // 100})
    for b in city.buildings:
        add(f"building:{b}", cfg.buildings[b]["yields"])
    subtotal = totals(lines)
    for b in city.buildings:
        for y, pct in cfg.buildings[b]["yield_pct"].items():
            bonus = max(0, subtotal[y]) * pct // 100
            if bonus:
                lines.append((f"building:{b} +{pct}%", y, bonus))
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
        food_eaten=city.pop * cfg.t("economy.food_per_pop"),
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
    return None


def item_allowed(state: GameState, cfg: Config, city: City, item: str) -> str | None:
    kind, _, ident = item.partition(":")
    if kind == "building":
        return building_allowed(state, cfg, city, ident) if ident in cfg.buildings else "unknown"
    if kind == "unit":
        return unit_allowed(state, cfg, city, ident) if ident in cfg.units else "unknown"
    if kind == "project":
        return None if ident in PROJECTS else "unknown project"
    return f"unknown item kind {kind!r}"


def production_options(state: GameState, cfg: Config, city: City) -> list[str]:
    items = [f"building:{b}" for b in sorted(cfg.buildings)]
    items += [f"unit:{u}" for u in sorted(cfg.units)]
    items += [f"project:{p}" for p in PROJECTS]
    return [i for i in items if item_allowed(state, cfg, city, i) is None]


def item_cost(cfg: Config, item: str) -> int:
    kind, _, ident = item.partition(":")
    if kind == "building":
        return cfg.buildings[ident]["cost"]
    if kind == "unit":
        return cfg.units[ident]["cost"]
    raise ValueError(f"{item} has no cost")


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
    kind, _, ident = item.partition(":")
    if kind == "building":
        city.buildings = sorted([*city.buildings, ident])
        city.hp = min(max_hp(cfg, city), city.hp + cfg.buildings[ident].get("city_hp", 0))
        return {"kind": "building_completed", "city": city.id, "building": ident}
    if not resource_available(state, cfg, city.owner, ident):
        return None
    unit = place_unit(state, cfg, ident, city.owner, city.tile, cfg.t("cities.work_radius"))
    if unit is None:
        return None
    return {"kind": "unit_completed", "city": city.id, "unit": unit.id, "type": ident}


def unit_bonus_lines(cfg: Config, city: City, production: int) -> list[Line]:
    lines = []
    for b in city.buildings:
        pct = cfg.buildings[b].get("unit_production_pct", 0)
        if pct:
            lines.append((f"building:{b} units +{pct}%", "production", production * pct // 100))
    return lines


def process_city(
    state: GameState, cfg: Config, city: City, player: Player
) -> tuple[list[dict[str, Any]], int]:
    """One turn for a connected, active city: growth and production. Adds its gold and beacon
    points to `player` and returns (events, science) for the caller to settle research."""
    events: list[dict[str, Any]] = []
    cy = city_yields(state, cfg, city)

    # growth
    city.food_store += cy.surplus_food
    threshold = growth_threshold(cfg, city.pop)
    if city.food_store >= threshold:
        city.food_store -= threshold
        city.pop += 1
        events.append({"kind": "city_grew", "city": city.id, "pop": city.pop})
    elif city.food_store < 0:
        city.food_store = 0
        if city.pop > 1:
            city.pop -= 1
            events.append({"kind": "city_starved", "city": city.id, "pop": city.pop})

    # production
    production = cy.totals["production"]
    head = city.queue[0] if city.queue else None
    if head and head.startswith("project:"):
        out = PROJECT_YIELD[head.split(":", 1)[1]]
        cy.totals[out] += production * cfg.t("economy.project_conversion_pct") // 100
    else:
        if head and head.startswith("unit:"):
            production += sum(v for _, _, v in unit_bonus_lines(cfg, city, production))
        city.production_store += production
        if head and city.production_store >= item_cost(cfg, head):
            if item_allowed(state, cfg, city, head) is not None:
                city.queue.pop(0)
                events.append({"kind": "item_dropped", "city": city.id, "item": head})
            else:
                done = complete_item(state, cfg, city, head)
                if done is None:
                    events.append({"kind": "production_stalled", "city": city.id, "item": head})
                else:
                    city.production_store -= item_cost(cfg, head)
                    city.queue.pop(0)
                    events.append(done)

    player.gold += cy.totals["gold"]
    player.beacon_points += cy.totals["beacon"]
    for e in events:
        e.setdefault("turn", state.turn)
        e.setdefault("player", player.id)
    return events, cy.totals["science"]


def maintenance(state: GameState, cfg: Config, pid: str) -> int:
    return sum(
        cfg.buildings[b]["maintenance"]
        for c in state.cities
        if c.owner == pid and c.status == ACTIVE
        for b in c.buildings
    )


def unit_upkeep(state: GameState, cfg: Config, pid: str) -> int:
    members = sum(u.count for u in state.units.values() if u.owner == pid)
    cities_n = sum(1 for c in state.cities if c.owner == pid and c.status == ACTIVE)
    free = cfg.t("economy.free_units_per_city") * cities_n
    abroad = sum(
        u.count
        for u in state.units.values()
        if u.owner == pid and state.tiles[u.tile].continent != pid
    )
    extra = abroad * cfg.t("economy.unit_upkeep") * cfg.t("trade.abroad_upkeep_pct") // 100
    return max(0, members - free) * cfg.t("economy.unit_upkeep") + extra


def player_turn(state: GameState, cfg: Config, pid: str) -> list[dict[str, Any]]:
    """Process every connected city of a player, then gold and research."""
    player = state.players[pid]
    events: list[dict[str, Any]] = []
    science = 0
    for city in state.cities:
        if city.owner != pid or city.status != ACTIVE or not city.connected:
            continue
        city_events, city_science = process_city(state, cfg, city, player)
        events.extend(city_events)
        science += city_science
    cost = maintenance(state, cfg, pid) + unit_upkeep(state, cfg, pid)
    player.gold -= cost
    if player.gold < 0:
        shortfall = -player.gold
        player.gold = 0
        player.research_progress = max(0, player.research_progress - shortfall)
        events.append(
            {"turn": state.turn, "kind": "gold_deficit", "player": pid, "shortfall": shortfall}
        )
    events.extend(tech.progress(cfg, player, science, state.turn))
    return events
