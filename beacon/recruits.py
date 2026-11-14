"""Beacons, alien recruits and councils (docs/SPEC_M5.md).

- Beacon points (a city yield) accumulate per player. Once a player knows the first beacon-tree
  tech, a recruit arrives whenever their points reach the arrival cost of their rarity level.
- A recruit scores in five domains. Seated on a council, a score of N gives its patron +N% in
  that domain (yields in every city; combat strength for military).
- Two seats per domain, three general seats. A recruit sits either on general (all its scores
  apply) or on one seat in each of several domains where it scores.
- Mortal recruits die when their lifespan runs out. Recruits with betrayal chance may leave to
  join an alien city; liberating that city brings them back to the liberator.
- Recruits can be offered to another player as a gift (price 0) or for gold.
"""

from __future__ import annotations

from typing import Any

from beacon import hexgrid, rng
from beacon.config import DOMAINS, Config
from beacon.liberation import credit
from beacon.state import OVERRUN, GameState, Offer, Recruit

Events = list[dict[str, Any]]
GENERAL = "general"


def settings(cfg: Config) -> dict[str, Any]:
    return cfg.alien("recruits")


def rarity_level(cfg: Config, techs: list[str]) -> int:
    """Number of beacon-tree rarity techs known, counted in order."""
    level = 0
    for tech in settings(cfg)["rarity_techs"]:
        if tech not in techs:
            break
        level += 1
    return level


def arrival_cost(cfg: Config, level: int) -> int | None:
    if level <= 0:
        return None
    return settings(cfg)["levels"][level - 1]["arrival_cost"]


def recruits_of(state: GameState, pid: str) -> list[Recruit]:
    return sorted((r for r in state.recruits.values() if r.patron == pid), key=lambda r: r.id)


def recruit(state: GameState, recruit_id: int) -> Recruit:
    try:
        return state.recruits[str(recruit_id)]
    except KeyError:
        raise KeyError(f"no recruit {recruit_id}") from None


# -- creating recruits -------------------------------------------------------------------------


def _trait_effects(cfg: Config, traits: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "yield_pct": {},
        "lifespan_delta": 0,
        "betrayal_permille": 0,
        "immortal": False,
        "sale_pct": 0,
    }
    for t in traits:
        eff = cfg.tables["recruit_traits"][t]["effects"]
        for d, pct in eff.get("yield_pct", {}).items():
            out["yield_pct"][d] = out["yield_pct"].get(d, 0) + pct
        out["lifespan_delta"] += eff.get("lifespan_delta", 0)
        out["betrayal_permille"] += eff.get("betrayal_permille", 0)
        out["sale_pct"] += eff.get("sale_pct", 0)
        out["immortal"] = out["immortal"] or bool(eff.get("immortal"))
    return out


def betrayal_permille(cfg: Config, r: Recruit) -> int:
    return _trait_effects(cfg, r.traits)["betrayal_permille"]


def _name(cfg: Config, r) -> str:
    n = settings(cfg)["names"]

    def word() -> str:
        return (r.choice(n["first"]) + r.choice(n["second"])).capitalize()

    return f"{word()} {word()}"


def make_recruit(state: GameState, cfg: Config, pid: str, level: int) -> Recruit:
    s = settings(cfg)
    lv = s["levels"][level - 1]
    r = rng.stream(state.seed, "recruits", state.turn, pid, state.next_id)
    taken = {x.kind for x in state.recruits.values() if x.legendary}
    legends = sorted(k for k in cfg.tables["legendary_recruits"] if k not in taken)
    if legends and r.randrange(1000) < lv["legendary_permille"]:
        kind = r.choice(legends)
        spec = cfg.tables["legendary_recruits"][kind]
        traits = list(spec["traits"])
        scores = {d: spec["scores"].get(d, 0) for d in DOMAINS}
        name, legendary, base_life = spec["name"], True, spec["lifespan"]
    else:
        types = sorted(cfg.tables["recruit_types"])
        kind = rng.weighted_choice(
            r, types, [cfg.tables["recruit_types"][t]["weight"] for t in types]
        )
        spec = cfg.tables["recruit_types"][kind]
        scores = dict.fromkeys(DOMAINS, 0)
        for _ in range(lv["budget"]):
            scores[r.choice(spec["focus"])] += 1
        pool = sorted(spec["traits"])
        traits = sorted(r.sample(pool, 1 + r.randrange(min(s["max_traits"], len(pool)))))
        if r.randrange(1000) < lv["immortal_permille"]:
            traits.append("immortal")
        lo, hi = spec["lifespan"]
        base_life = r.randint(lo, hi)
        name, legendary = _name(cfg, r), False
    eff = _trait_effects(cfg, traits)
    for d, pct in eff["yield_pct"].items():
        if scores.get(d):
            scores[d] = scores[d] * (100 + pct) // 100
    lifespan = None
    if not eff["immortal"]:
        lifespan = max(s["min_lifespan"], min(s["max_lifespan"], base_life + eff["lifespan_delta"]))
    rec = Recruit(
        id=state.new_id(),
        name=name,
        kind=kind,
        legendary=legendary,
        scores={d: v for d, v in scores.items() if v},
        traits=traits,
        born=state.turn,
        lifespan=lifespan,
        patron=pid,
    )
    state.recruits[str(rec.id)] = rec
    return rec


def arrivals(state: GameState, cfg: Config, pid: str) -> Events:
    player = state.players[pid]
    level = rarity_level(cfg, player.techs)
    cost = arrival_cost(cfg, level)
    if cost is None or player.beacon_points < cost:
        return []
    player.beacon_points -= cost
    rec = make_recruit(state, cfg, pid, level)
    credit(state, pid, "recruits_gained")
    return [
        {
            "turn": state.turn,
            "kind": "recruit_arrived",
            "player": pid,
            "recruit": rec.id,
            "name": rec.name,
            "legendary": rec.legendary,
            "scores": dict(rec.scores),
            "traits": list(rec.traits),
            "level": level,
        }
    ]


# -- councils ----------------------------------------------------------------------------------


def seat_problem(state: GameState, cfg: Config, rec: Recruit, seats: list[str]) -> str | None:
    s = settings(cfg)
    if rec.patron is None:
        return "this recruit has no patron"
    if not seats:
        return "choose at least one seat"
    if len(set(seats)) != len(seats):
        return "a recruit takes at most one seat per council"
    if GENERAL in seats:
        if seats != [GENERAL]:
            return "a recruit on a general seat sits on no other council"
        used = sum(
            1 for o in recruits_of(state, rec.patron) if o.id != rec.id and GENERAL in o.seats
        )
        if used >= s["general_seats"]:
            return "all general seats are taken"
        return None
    for d in seats:
        if d not in DOMAINS:
            return f"unknown council {d!r}"
        if rec.scores.get(d, 0) <= 0:
            return f"{rec.name} has no {d} score"
        used = sum(1 for o in recruits_of(state, rec.patron) if o.id != rec.id and d in o.seats)
        if used >= s["seats_per_domain"]:
            return f"both {d} seats are taken"
    return None


def council_lines(state: GameState, pid: str, domain: str) -> list[tuple[str, int]]:
    """(source, percent) lines for a player's council bonus in one domain."""
    lines = []
    for rec in recruits_of(state, pid):
        if (GENERAL in rec.seats or domain in rec.seats) and rec.scores.get(domain):
            lines.append((f"council:{rec.name}", rec.scores[domain]))
    return lines


# -- ageing, betrayal, offers ------------------------------------------------------------------


def _nearest_alien_city(state: GameState, pid: str) -> int | None:
    held = [c for c in state.cities if c.status == OVERRUN]
    if not held:
        return None
    home = next((c for c in state.cities if c.owner == pid and c.is_capital), None)
    origin = home.tile if home else held[0].tile
    same = [c for c in held if home is not None and c.continent == home.continent] or held
    return min(same, key=lambda c: (hexgrid.distance(c.tile, origin, state.width), c.id)).id


def betray(state: GameState, rec: Recruit) -> dict[str, Any]:
    previous = rec.patron
    city = _nearest_alien_city(state, previous) if previous else None
    rec.patron, rec.seats, rec.alien_city = None, [], city
    if previous:
        credit(state, previous, "recruits_lost")
    if city is None:
        del state.recruits[str(rec.id)]
    return {
        "turn": state.turn,
        "kind": "recruit_betrayed",
        "player": previous,
        "recruit": rec.id,
        "name": rec.name,
        "alien_city": city,
    }


def end_of_turn(state: GameState, cfg: Config) -> Events:
    """Deaths, betrayals and lapsed offers, after the turn's arrivals."""
    events: Events = []
    for rec in sorted(state.recruits.values(), key=lambda x: x.id):
        if rec.patron is None:
            continue
        if rec.lifespan is not None and state.turn - rec.born >= rec.lifespan:
            del state.recruits[str(rec.id)]
            events.append(
                {
                    "turn": state.turn,
                    "kind": "recruit_died",
                    "player": rec.patron,
                    "recruit": rec.id,
                    "name": rec.name,
                }
            )
            continue
        chance = betrayal_permille(cfg, rec)
        if (
            chance
            and rng.stream(state.seed, "recruits", state.turn, "betray", rec.id).randrange(1000)
            < chance
        ):
            events.append(betray(state, rec))
    for key in list(state.offers):
        del state.offers[key]
    return events


def freed_by_liberation(state: GameState, city_id: int, by: str) -> Events:
    """Recruits held in a liberated alien city join the liberator."""
    events = []
    for rec in sorted(state.recruits.values(), key=lambda x: x.id):
        if rec.alien_city == city_id and rec.patron is None:
            rec.patron, rec.alien_city = by, None
            credit(state, by, "recruits_gained")
            events.append(
                {
                    "turn": state.turn,
                    "kind": "recruit_freed",
                    "player": by,
                    "recruit": rec.id,
                    "name": rec.name,
                    "city": city_id,
                }
            )
    return events


def traitor_lines(state: GameState, city_id: int) -> list[tuple[str, int]]:
    """Strength percent a betraying recruit lends its alien city (its military score)."""
    return [
        (f"traitor:{r.name}", r.scores.get("military", 0))
        for r in sorted(state.recruits.values(), key=lambda x: x.id)
        if r.alien_city == city_id and r.scores.get("military")
    ]


def offer(state: GameState, rec: Recruit, to: str, price: int) -> Offer:
    o = Offer(
        id=state.new_id(),
        recruit=rec.id,
        from_player=rec.patron or "",
        to_player=to,
        price=price,
        turn=state.turn,
    )
    state.offers[str(o.id)] = o
    return o


def sale_price(cfg: Config, rec: Recruit, price: int) -> int:
    """Gold the seller receives: the agreed price plus any trait bonus (greedy)."""
    return price * (100 + _trait_effects(cfg, rec.traits)["sale_pct"]) // 100


def accept(state: GameState, cfg: Config, o: Offer) -> Events:
    rec = recruit(state, o.recruit)
    buyer, seller = state.players[o.to_player], state.players[o.from_player]
    buyer.gold -= o.price
    seller.gold += sale_price(cfg, rec, o.price)
    rec.patron, rec.seats = o.to_player, []
    del state.offers[str(o.id)]
    credit(state, o.from_player, "recruits_sold" if o.price else "recruits_given")
    credit(state, o.to_player, "recruits_gained")
    return [
        {
            "turn": state.turn,
            "kind": "recruit_transferred",
            "player": o.to_player,
            "recruit": rec.id,
            "from": o.from_player,
            "price": o.price,
        }
    ]
