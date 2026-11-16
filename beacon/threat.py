"""A readable alien that reacts to you (docs/SPEC_M12.md, designer 2026-11-15).

- Heat: the attention a player draws (population, loud buildings, convoys). Hotter players are
  better strike targets and draw bigger strikes (the director, beacon/aliens.py).
- Strike plans: the director announces a siege a few turns ahead (AlienPlan); its units gather,
  then besiege on the launch turn.
- Contents: what each alien-held city holds, seen first as a rumour; freeing the city gives it.
- Other ways to free a city: sabotage, arming the resistance (uprisings), destroying nests.
"""

from __future__ import annotations

from typing import Any

from beacon import hexgrid, rng
from beacon.config import Config
from beacon.state import ACTIVE, ALIENS, OVERRUN, City, GameState, Unit
from beacon.tiles import is_passable_land

Events = list[dict[str, Any]]


# -- heat ------------------------------------------------------------------------------------------


def heat(state: GameState, cfg: Config, pid: str) -> int:
    h = cfg.alien("heat")
    total = 0
    for city in state.cities:
        if city.owner != pid or city.status != ACTIVE:
            continue
        total += city.pop * h["per_pop"]
        total += sum(h["buildings"].get(b, 0) for b in city.buildings)
        if city.convoy:
            total += h["per_convoy"]
    from beacon.techfx import total as fx  # Beacon silence (council, SPEC_M13)

    return max(0, total * (100 + fx(cfg, state.players.get(pid), "heat_pct")) // 100)


def heat_lines(state: GameState, cfg: Config, pid: str) -> list[tuple[str, int]]:
    """Where a player's heat comes from, for the tooltip."""
    h = cfg.alien("heat")
    pop = buildings = convoys = 0
    for city in state.cities:
        if city.owner == pid and city.status == ACTIVE:
            pop += city.pop * h["per_pop"]
            buildings += sum(h["buildings"].get(b, 0) for b in city.buildings)
            convoys += h["per_convoy"] if city.convoy else 0
    return [
        (k, v)
        for k, v in (("population", pop), ("buildings", buildings), ("convoys", convoys))
        if v
    ]


# -- plans -----------------------------------------------------------------------------------------


def has_uav(state: GameState, cfg: Config, city: City) -> bool:
    """A UAV patrol over the city detects strikes gathering against it (designer 2026-11-16:
    no warning without one)."""
    return any(
        u.owner == city.owner and cfg.units[u.type].get("detects_strikes")
        for u in state.units_at(city.tile)
    )


def plans_against(state: GameState, pid: str) -> list:
    return sorted(
        (p for p in state.aliens.plans.values() if p.player == pid), key=lambda p: (p.launch, p.id)
    )


def detected(state: GameState, cfg: Config, pid: str) -> list:
    """The plans against a player that its UAVs have spotted."""
    out = []
    for p in plans_against(state, pid):
        city = state.city_at(p.target)
        if city is not None and has_uav(state, cfg, city):
            out.append(p)
    return out


def plan_of(state: GameState, unit_id: int):
    return next((p for p in state.aliens.plans.values() if unit_id in p.units), None)


# -- contents, rumours and intel -----------------------------------------------------------------


def seed_contents(state: GameState, cfg: Config) -> None:
    """What every alien-held city holds (seeded at the start); a hive heart gets a guard."""
    from beacon.units import place_unit

    spec = cfg.alien("contents")
    kinds = sorted(spec)
    towns = {p.band_town for p in state.players.values()}  # a band's first town (SPEC_M14)
    for city in state.cities:
        if city.status != OVERRUN or city.id in towns:
            continue
        r = rng.stream(state.seed, "map", "contents", city.id)
        city.contents = rng.weighted_choice(r, kinds, [spec[k]["weight"] for k in kinds])
        guard = spec[city.contents].get("guard")
        if guard:
            place_unit(state, cfg, guard, ALIENS, city.tile, cfg.t("cities.work_radius"))


def rumour(cfg: Config, city: City) -> str | None:
    return cfg.alien(f"contents.{city.contents}.rumour") if city.contents else None


def update_intel(state: GameState, cfg: Config) -> Events:
    """A player recon unit (or engineers) beside an alien city learns what it holds."""
    events: Events = []
    for city in state.cities:
        if city.status != OVERRUN or not city.contents:
            continue
        for n in [city.tile, *hexgrid.neighbours(city.tile, state.width, state.height)]:
            for u in state.units_at(n):
                if u.owner not in state.players or not _scout(cfg, u):
                    continue
                player = state.players[u.owner]
                if city.id not in player.intel:
                    player.intel = sorted([*player.intel, city.id])
                    events.append(
                        {
                            "turn": state.turn,
                            "kind": "city_intel",
                            "player": u.owner,
                            "city": city.id,
                            "contents": city.contents,
                        }
                    )
    return events


def _scout(cfg: Config, u: Unit) -> bool:
    spec = cfg.units[u.type]
    return spec["role"] == "recon" or bool(spec.get("can_build"))


def give_contents(state: GameState, cfg: Config, city: City, by: str) -> Events:
    """Freeing a city gives what it held (SPEC_M12)."""
    if not city.contents or by not in state.players:
        return []
    from beacon import citizens
    from beacon.config import DOMAINS
    from beacon.units import place_unit

    kind, city.contents = city.contents, None
    spec = cfg.alien(f"contents.{kind}")
    player = state.players[by]
    got: list[str] = []
    if spec.get("pop") and city.owner == by:
        city.pop += spec["pop"]
        got.append(f"+{spec['pop']} population")
    if spec.get("citizen_points") and city.owner == by:
        city.pop += 1
        c = citizens.make(state, cfg, city, adult=True)
        r = rng.stream(state.seed, "map", "captive", city.id)
        picks = r.sample(list(DOMAINS), 3)
        each, extra = divmod(spec["citizen_points"], 3)
        c.stats = {d: each + (1 if k < extra else 0) for k, d in enumerate(picks)}
        got.append(f"{c.name}, a specialist ({spec['citizen_points']} points)")
    if spec.get("science") and player.research:
        player.research_progress += spec["science"]
        got.append(f"+{spec['science']} science")
    elif spec.get("science"):
        player.gold += spec["science"]
        got.append(f"+{spec['science']} gold (no research set)")
    if spec.get("gold"):
        player.gold += spec["gold"]
        got.append(f"+{spec['gold']} gold")
    for t in spec.get("units") or []:
        if place_unit(state, cfg, t, by, city.tile, 2) is not None:
            got.append(f"a free {t.replace('_', ' ')}")
    if spec.get("alien_tech"):
        from beacon.endgame import alien_techs

        new = [t for t in alien_techs(cfg) if t not in player.techs]
        if new:
            player.techs = sorted([*player.techs, new[0]])
            got.append(f"alien tech {new[0].replace('_', ' ')}")
    return [
        {
            "turn": state.turn,
            "kind": "contents_found",
            "player": by,
            "city": city.id,
            "contents": kind,
            "result": got,
        }
    ]


# -- sabotage and the resistance -----------------------------------------------------------------


def _beside(state: GameState, unit: Unit, city: City) -> bool:
    return hexgrid.distance(unit.tile, city.tile, state.width) == 1


def sabotage_problem(state: GameState, cfg: Config, unit: Unit, city: City) -> str | None:
    if not _scout(cfg, unit):
        return "only engineers and recon units can sabotage"
    if city.status != OVERRUN:
        return f"{city.name} is not held by the aliens"
    if not _beside(state, unit, city):
        return "the saboteur must stand beside the city"
    if unit.moves_left <= 0 or unit.acted:
        return "no moves left"
    return None


def sabotage(state: GameState, cfg: Config, unit: Unit, city: City) -> Events:
    from beacon.cities import max_hp
    from beacon.combat import damage_unit

    sb = cfg.alien("sabotage")
    loss = max_hp(cfg, city, state) * sb["hp_pct"] // 100
    city.hp = max(1, city.hp - loss)
    city.damage_by[unit.owner] = city.damage_by.get(unit.owner, 0) + loss
    city.besieged = True
    r = rng.stream(state.seed, "combat", state.turn, "sabotage", unit.id)
    hurt = r.randint(sb["damage_min"], sb["damage_max"])
    unit.moves_left, unit.acted = 0, True
    events: Events = [
        {
            "turn": state.turn,
            "kind": "sabotage",
            "player": unit.owner,
            "city": city.id,
            "damage": loss,
            "hurt": hurt,
        }
    ]
    events.extend(damage_unit(state, cfg, unit, hurt, ALIENS))
    return events


def arm_problem(state: GameState, cfg: Config, unit: Unit, city: City) -> str | None:
    rs = cfg.alien("resistance")
    if city.status != OVERRUN:
        return f"{city.name} is not held by the aliens"
    if not _beside(state, unit, city):
        return "the unit must stand beside the city"
    if unit.moves_left <= 0 or unit.acted:
        return "no moves left"
    if city.resistance >= rs["max_level"]:
        return "its resistance is as armed as it can be"
    if state.players[unit.owner].gold < rs["gold"]:
        return f"needs {rs['gold']} gold"
    return None


def arm(state: GameState, cfg: Config, unit: Unit, city: City) -> Events:
    rs = cfg.alien("resistance")
    state.players[unit.owner].gold -= rs["gold"]
    city.resistance += 1
    city.armed_by = {**city.armed_by, unit.owner: city.armed_by.get(unit.owner, 0) + 1}
    unit.moves_left, unit.acted = 0, True
    return [
        {
            "turn": state.turn,
            "kind": "resistance_armed",
            "player": unit.owner,
            "city": city.id,
            "level": city.resistance,
        }
    ]


def uprisings(state: GameState, cfg: Config) -> Events:
    from beacon.cities import max_hp

    rs = cfg.alien("resistance")
    events: Events = []
    for city in state.cities:
        if city.status != OVERRUN or city.resistance <= 0:
            continue
        r = rng.stream(state.seed, "events", state.turn, "uprising", city.id)
        if not rng.percent_roll(r, city.resistance * rs["uprising_pct"]):
            continue
        loss = max_hp(cfg, city, state) * rs["hp_pct"] // 100
        city.hp = max(1, city.hp - loss)
        city.besieged = True
        for pid, n in city.armed_by.items():
            city.damage_by[pid] = city.damage_by.get(pid, 0) + loss * n // max(1, city.resistance)
        for u in state.units_at(city.tile):
            if u.owner == ALIENS:
                u.hp = max(1, u.hp - rs["garrison_damage"])
        city.resistance -= 1
        for pid in sorted(city.armed_by):
            events.append({"turn": state.turn, "kind": "uprising", "player": pid, "city": city.id})
    return events


# -- nests -----------------------------------------------------------------------------------------


def place_nests(state: GameState, cfg: Config) -> None:
    ns = cfg.alien("nests")
    taken = {c.tile for c in state.cities} | {s.tile for s in state.sites.values()}
    taken |= {int(k) for k in state.caches}
    towns = {p.band_town for p in state.players.values()}
    for city in state.cities:
        if city.status != OVERRUN or city.id in towns:
            continue
        r = rng.stream(state.seed, "map", "nests", city.id)
        options = [
            i
            for i in hexgrid.within(city.tile, ns["radius"], state.width, state.height)
            if i not in taken
            and hexgrid.distance(i, city.tile, state.width) >= 2
            and is_passable_land(cfg, state.tiles[i])
            and state.tiles[i].nest is None
            and not state.tiles[i].improvement
        ]
        r.shuffle(options)
        for i in options[: r.randint(ns["min"], ns["max"])]:
            state.tiles[i].nest = city.id
            taken.add(i)


def nests_of(state: GameState, city: City) -> int:
    return sum(1 for t in state.tiles if t.nest == city.id)


def nest_turn(state: GameState, cfg: Config) -> Events:
    """Nests feed their cities; a player soldier on a nest destroys it."""
    from beacon.cities import max_hp
    from beacon.units import is_civilian

    ns = cfg.alien("nests")
    events: Events = []
    fed: dict[int, int] = {}
    for i, t in enumerate(state.tiles):
        if t.nest is None:
            continue
        here = [
            u
            for u in state.units_at(i)
            if u.owner in state.players and not is_civilian(cfg, u.type)
        ]
        city = state.cities[t.nest]
        if here or city.status != OVERRUN:
            t.nest = None
            if here:
                from beacon.liberation import credit

                credit(state, here[0].owner, "kills")
                events.append(
                    {
                        "turn": state.turn,
                        "kind": "nest_destroyed",
                        "player": here[0].owner,
                        "tile": i,
                        "city": city.id,
                    }
                )
            continue
        fed[city.id] = fed.get(city.id, 0) + 1
    for cid, n in fed.items():
        city = state.cities[cid]
        if not city.besieged:
            city.hp = min(max_hp(cfg, city, state), city.hp + n * ns["heal"])
        city.production_store += n * ns["production"]
    return events


# -- funding the resistance with gold (designer 2026-11-16) ---------------------------------------


def _first_town(state: GameState, pid: str, city: City) -> bool:
    p = state.players.get(pid)
    return p is not None and not p.founded and p.band_town == city.id


def fund_pct(state: GameState, cfg: Config, pid: str, city: City, gold: int) -> int:
    """Percent of defence strength `gold` takes off the city (before the cap)."""
    f = cfg.alien("funding")
    if _first_town(state, pid, city):
        return min(f["first_pct"], gold * f["first_pct"] // f["first_gold"])
    from beacon.combat import city_strength

    total = city_strength(state, cfg, city).total * 100 // max(1, 100 - city.funded_pct)
    per_pct = max(1, total // 100 * f["pct_cost_tenths"] // 10)  # gold per percent
    return gold // per_pct


def fund_quotes(state: GameState, cfg: Config, pid: str, city: City) -> list[dict[str, int]]:
    """What each offered amount would buy now (the first town: just its one offer)."""
    f = cfg.alien("funding")
    room = f["max_pct"] - city.funded_pct
    amounts = [f["first_gold"]] if _first_town(state, pid, city) else f["amounts"]
    out = []
    for gold in amounts:
        pct = min(room, fund_pct(state, cfg, pid, city, gold))
        if pct > 0:
            out.append({"gold": gold, "pct": pct})
    return out


def fund_problem(state: GameState, cfg: Config, pid: str, city: City, gold: int) -> str | None:
    if city.status != OVERRUN:
        return f"{city.name} is not held by the aliens"
    player = state.players.get(pid)
    if player is None or str(city.id) not in player.known_cities:
        return "you have not found that city"
    if gold <= 0:
        return "send some gold"
    if player.gold < gold:
        return f"needs {gold} gold; treasury has {player.gold}"
    if city.funded_pct >= cfg.alien("funding.max_pct"):
        return "its resistance has all the help it can use"
    if fund_pct(state, cfg, pid, city, gold) <= 0:
        return "too little gold to make a difference"
    return None


def fund(state: GameState, cfg: Config, pid: str, city: City, gold: int) -> Events:
    pct = min(cfg.alien("funding.max_pct") - city.funded_pct, fund_pct(state, cfg, pid, city, gold))
    state.players[pid].gold -= gold
    city.funded_pct += pct
    return [
        {
            "turn": state.turn,
            "kind": "resistance_funded",
            "player": pid,
            "city": city.id,
            "gold": gold,
            "pct": pct,
            "total_pct": city.funded_pct,
        }
    ]
