"""The settlement sandbox (docs/SPEC_M15.md, designer 2026-11-16).

One city and its six neighbouring hexes. Goods come from land (staffed buildings in hex slots)
into banks with storage caps; people eat grain; construction costs materials (paid when ordered)
and labour (spent over turns); walls stand on the territory's outer hex edges; alien raids come
every few turns at one outer hex; the Galactic Exchange buys and sells at a bad spread.

Separate from the main game (its own state); deterministic, integers only, seeded through the
`events` stream. Hexes use axial coordinates: the centre is (0, 0); ring hex i sits in direction
i; DIRS lists the six directions (pointy-top: E, NE, NW, W, SW, SE).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from beacon import canonical, rng
from beacon.config import Config
from beacon.state import from_dict, to_dict

Events = list[dict[str, Any]]
DIRS = ((1, 0), (1, -1), (0, -1), (-1, 0), (-1, 1), (0, 1))
GOODS = ("grain", "timber", "stone", "iron")
PRODUCER_ORDER = ("farm", "lumber_camp", "quarry", "iron_mine", "workshop")


class SettlementError(ValueError):
    """A command that cannot be carried out."""


@dataclass
class SHex:
    q: int
    r: int
    terrain: str
    resource: str | None
    slots: int
    buildings: list[str] = field(default_factory=list)


@dataclass
class Order:
    kind: str  # building | wall
    what: str  # building id or wall material
    hex: int
    edge: int = -1  # wall: direction 0-5 of the outer edge
    labour_left: int = 0


@dataclass
class Settlement:
    seed: int
    hexes: list[SHex]
    goods: dict[str, int]
    gold: int
    pop: int
    turn: int = 0
    walls: dict[str, dict[str, Any]] = field(default_factory=dict)  # "hex:dir" -> material, hp
    queue: list[Order] = field(default_factory=list)
    prices: dict[str, int] = field(default_factory=dict)  # price index, percent of base
    raids: int = 0  # raids so far
    next_raid: int = 0
    raid_hex: int = 1
    log: list[dict[str, Any]] = field(default_factory=list)  # the last turn's events


def S(cfg: Config, path: str) -> Any:  # noqa: N802 - short accessor for data/settlement.yaml
    return cfg.settlement(path)


# -- making one -----------------------------------------------------------------------------------


def new(cfg: Config, seed: int) -> Settlement:
    t = S(cfg, "terrain")
    ring = list(t["ring"])
    rng.stream(seed, "events", "settlement", "layout").shuffle(ring)
    hexes = [
        SHex(q=0, r=0, terrain=t["centre"]["terrain"], resource=None, slots=t["centre"]["slots"])
    ]
    hexes[0].buildings = ["city_hall"]
    for i, spec in enumerate(ring):
        dq, dr = DIRS[i]
        hexes.append(
            SHex(
                q=dq,
                r=dr,
                terrain=spec["terrain"],
                resource=spec.get("resource"),
                slots=spec["slots"],
            )
        )
    start = S(cfg, "start")
    s = Settlement(
        seed=seed,
        hexes=hexes,
        goods={g: start["goods"].get(g, 0) for g in GOODS},
        gold=start["gold"],
        pop=start["pop"],
        prices=dict.fromkeys(GOODS, 100),
    )
    # a farm and a lumber camp already stand, so grain and timber flow from the first turn
    for resource, kind in (("grain", "farm"), ("timber", "lumber_camp")):
        h = next(i for i, x in enumerate(hexes) if x.resource == resource)
        hexes[h].buildings.append(kind)
    r = S(cfg, "raids")
    s.next_raid = r["first"]
    s.raid_hex = _raid_hex(s)
    return s


def _raid_hex(s: Settlement) -> int:
    return rng.stream(s.seed, "events", "settlement", "raid", s.raids).randint(1, 6)


# -- what the city has ----------------------------------------------------------------------------


def caps(cfg: Config, s: Settlement) -> dict[str, int]:
    goods = S(cfg, "goods")
    out = {g: goods[g]["cap"] for g in GOODS}
    for h in s.hexes:
        for b in h.buildings:
            for g, n in (S(cfg, f"buildings.{b}").get("store") or {}).items():
                out[g] += n
    return out


def room(cfg: Config, s: Settlement) -> int:
    return S(cfg, "people.room") + sum(
        S(cfg, f"buildings.{b}").get("room", 0) for h in s.hexes for b in h.buildings
    )


def producers(cfg: Config, s: Settlement) -> list[tuple[int, str]]:
    """(hex, building) for every building that needs a worker, in staffing order."""
    out = []
    for kind in PRODUCER_ORDER:
        for i, h in enumerate(s.hexes):
            out += [(i, kind)] * h.buildings.count(kind)
    return out


def staffed(cfg: Config, s: Settlement) -> list[tuple[int, str]]:
    return producers(cfg, s)[: s.pop]


def labour(cfg: Config, s: Settlement) -> int:
    bonus = sum(S(cfg, f"buildings.{kind}").get("labour_bonus", 0) for _, kind in staffed(cfg, s))
    return S(cfg, "labour.base") + bonus


def harvest(cfg: Config, s: Settlement) -> dict[str, int]:
    out = dict.fromkeys(GOODS, 0)
    for _, kind in staffed(cfg, s):
        for g, n in (S(cfg, f"buildings.{kind}").get("makes") or {}).items():
            out[g] += n
    return out


def city_strength(cfg: Config, s: Settlement) -> int:
    """Every building adds strength (designer 2026-11-16)."""
    return sum(S(cfg, f"buildings.{b}").get("strength", 0) for h in s.hexes for b in h.buildings)


def outer_edges(s: Settlement, hex_index: int) -> list[int]:
    """Directions of a hex's edges on the territory's border."""
    h = s.hexes[hex_index]
    inside = {(x.q, x.r) for x in s.hexes}
    return [d for d, (dq, dr) in enumerate(DIRS) if (h.q + dq, h.r + dr) not in inside]


def walls_on(s: Settlement, hex_index: int) -> list[tuple[str, dict[str, Any]]]:
    return [(k, w) for k, w in sorted(s.walls.items()) if int(k.split(":")[0]) == hex_index]


def defence(cfg: Config, s: Settlement, hex_index: int) -> int:
    r = S(cfg, "raids")
    walls = sum(S(cfg, f"walls.{w['material']}.strength") for _, w in walls_on(s, hex_index))
    return city_strength(cfg, s) * r["city_share_pct"] // 100 + walls


def raid_strength(cfg: Config, s: Settlement) -> int:
    r = S(cfg, "raids")
    return r["base"] + r["per_raid"] * s.raids


def price(cfg: Config, s: Settlement, good: str) -> int:
    return max(1, S(cfg, f"goods.{good}.price") * s.prices[good] // 100)


def quotes(cfg: Config, s: Settlement) -> dict[str, dict[str, int]]:
    """What the Exchange pays (sell) and asks (buy) per unit now."""
    ex = S(cfg, "exchange")
    return {
        g: {
            "sell": max(1, price(cfg, s, g) * ex["sell_pct"] // 100),
            "buy": -(-price(cfg, s, g) * ex["buy_pct"] // 100),
        }
        for g in GOODS
    }


# -- commands -------------------------------------------------------------------------------------


def _used_slots(s: Settlement, hex_index: int) -> int:
    queued = sum(1 for o in s.queue if o.kind == "building" and o.hex == hex_index)
    return len(s.hexes[hex_index].buildings) + queued


def _pay(s: Settlement, cost: dict[str, int]) -> None:
    for g, n in cost.items():
        s.goods[g] -= n


def _afford(s: Settlement, cost: dict[str, int]) -> str | None:
    short = [f"{n - s.goods[g]} {g}" for g, n in sorted(cost.items()) if s.goods[g] < n]
    return f"short of {', '.join(short)}" if short else None


def build_problem(cfg: Config, s: Settlement, hex_index: int, kind: str) -> str | None:
    if not 0 <= hex_index < len(s.hexes):
        return "no such hex"
    spec = S(cfg, "buildings").get(kind)
    if spec is None or spec.get("fixed"):
        return f"cannot build {kind!r}"
    h = s.hexes[hex_index]
    if spec.get("needs") and h.resource != spec["needs"]:
        return f"needs a {spec['needs']} hex"
    if _used_slots(s, hex_index) >= h.slots:
        return "no free slot on this hex"
    return _afford(s, spec["cost"])


def build(cfg: Config, s: Settlement, hex_index: int, kind: str) -> Events:
    problem = build_problem(cfg, s, hex_index, kind)
    if problem:
        raise SettlementError(problem)
    spec = S(cfg, f"buildings.{kind}")
    _pay(s, spec["cost"])
    s.queue.append(Order(kind="building", what=kind, hex=hex_index, labour_left=spec["labour"]))
    return [{"kind": "ordered", "what": kind, "hex": hex_index}]


def wall_problem(
    cfg: Config, s: Settlement, hex_index: int, edge: int, material: str
) -> str | None:
    if not 0 <= hex_index < len(s.hexes):
        return "no such hex"
    if edge not in outer_edges(s, hex_index):
        return "walls stand on the territory's outer edges"
    spec = S(cfg, "walls").get(material)
    if spec is None:
        return f"unknown wall {material!r}"
    key = f"{hex_index}:{edge}"
    if any(o.kind == "wall" and o.hex == hex_index and o.edge == edge for o in s.queue):
        return "work on this wall is already ordered"
    current = s.walls.get(key)
    if current is not None:
        order = list(S(cfg, "walls"))
        if order.index(material) <= order.index(current["material"]) and current["hp"] >= S(
            cfg, f"walls.{current['material']}.hp"
        ):
            return "this wall is already as strong"
    return _afford(s, spec["cost"])


def wall(cfg: Config, s: Settlement, hex_index: int, edge: int, material: str) -> Events:
    problem = wall_problem(cfg, s, hex_index, edge, material)
    if problem:
        raise SettlementError(problem)
    spec = S(cfg, f"walls.{material}")
    _pay(s, spec["cost"])
    s.queue.append(
        Order(kind="wall", what=material, hex=hex_index, edge=edge, labour_left=spec["labour"])
    )
    return [{"kind": "ordered", "what": f"{material} wall", "hex": hex_index, "edge": edge}]


def cancel(cfg: Config, s: Settlement, index: int) -> Events:
    """Cancel a queued order; its materials come back (up to storage)."""
    if not 0 <= index < len(s.queue):
        raise SettlementError("no such order")
    o = s.queue.pop(index)
    table = "buildings" if o.kind == "building" else "walls"
    cap = caps(cfg, s)
    for g, n in S(cfg, f"{table}.{o.what}.cost").items():
        s.goods[g] = min(cap[g], s.goods[g] + n)
    return [{"kind": "cancelled", "what": o.what}]


def trade(cfg: Config, s: Settlement, good: str, amount: int, side: str) -> Events:
    if good not in GOODS:
        raise SettlementError(f"unknown good {good!r}")
    if amount <= 0:
        raise SettlementError("trade a positive amount")
    ex = S(cfg, "exchange")
    q = quotes(cfg, s)[good]
    step = ex["sale_drop_pct"] * (amount // 10)
    if side == "sell":
        if s.goods[good] < amount:
            raise SettlementError(f"only {s.goods[good]} {good} to sell")
        s.goods[good] -= amount
        s.gold += q["sell"] * amount
        s.prices[good] = max(ex["min_pct"], s.prices[good] - step)
        return [{"kind": "sold", "good": good, "amount": amount, "gold": q["sell"] * amount}]
    if side == "buy":
        cost = q["buy"] * amount
        if s.gold < cost:
            raise SettlementError(f"needs {cost} gold")
        if s.goods[good] + amount > caps(cfg, s)[good]:
            raise SettlementError("not enough storage")
        s.gold -= cost
        s.goods[good] += amount
        s.prices[good] = min(ex["max_pct"], s.prices[good] + step)
        return [{"kind": "bought", "good": good, "amount": amount, "gold": cost}]
    raise SettlementError("side is buy or sell")


def demolish(cfg: Config, s: Settlement, hex_index: int, kind: str) -> Events:
    if not 0 <= hex_index < len(s.hexes) or kind not in s.hexes[hex_index].buildings:
        raise SettlementError("no such building here")
    if S(cfg, f"buildings.{kind}").get("fixed"):
        raise SettlementError("the city hall stays")
    s.hexes[hex_index].buildings.remove(kind)
    return [{"kind": "demolished", "what": kind, "hex": hex_index}]


# -- the turn -------------------------------------------------------------------------------------


def end_turn(cfg: Config, s: Settlement) -> Events:
    events: Events = []
    # 1. construction: labour goes to the queue in order
    work = labour(cfg, s)
    done: list[Order] = []
    for o in s.queue:
        if work <= 0:
            break
        spent = min(work, o.labour_left)
        o.labour_left -= spent
        work -= spent
        if o.labour_left == 0:
            done.append(o)
    for o in done:
        s.queue.remove(o)
        if o.kind == "building":
            s.hexes[o.hex].buildings.append(o.what)
        else:
            s.walls[f"{o.hex}:{o.edge}"] = {"material": o.what, "hp": S(cfg, f"walls.{o.what}.hp")}
        events.append({"kind": "built", "what": o.what, "hex": o.hex, "edge": o.edge})
    # 2. harvest
    got = harvest(cfg, s)
    for g, n in got.items():
        s.goods[g] += n
    events.append({"kind": "harvest", "goods": {g: n for g, n in got.items() if n}})
    # 3. people eat, then grow or go hungry
    p = S(cfg, "people")
    need = s.pop * p["eats"]
    if s.goods["grain"] >= need:
        s.goods["grain"] -= need
        if s.pop < room(cfg, s) and s.goods["grain"] >= p["grow_cost"]:
            s.goods["grain"] -= p["grow_cost"]
            s.pop += 1
            events.append({"kind": "grew", "pop": s.pop})
    else:
        s.goods["grain"] = 0
        if s.pop > 1:
            s.pop -= 1
        events.append({"kind": "hunger", "pop": s.pop})
    # 4. storage
    cap = caps(cfg, s)
    lost = {g: s.goods[g] - cap[g] for g in GOODS if s.goods[g] > cap[g]}
    for g, n in lost.items():
        s.goods[g] -= n
    if lost:
        events.append({"kind": "spoiled", "goods": lost})
    # 5. the raid
    if s.turn >= s.next_raid:
        events.extend(_raid(cfg, s))
    elif s.next_raid - s.turn <= S(cfg, "raids.warning"):
        events.append({"kind": "raid_coming", "hex": s.raid_hex, "turns": s.next_raid - s.turn})
    # 6. the Exchange's prices drift
    ex = S(cfg, "exchange")
    for g in GOODS:
        r = rng.stream(s.seed, "events", "settlement", "price", s.turn, g)
        step = r.randint(-ex["drift_pct"], ex["drift_pct"]) + (100 - s.prices[g]) // 10
        s.prices[g] = max(ex["min_pct"], min(ex["max_pct"], s.prices[g] + step))
    s.turn += 1
    s.log = events
    return events


def _raid(cfg: Config, s: Settlement) -> Events:
    r = S(cfg, "raids")
    hx, strength = s.raid_hex, raid_strength(cfg, s)
    hold = defence(cfg, s, hx)
    walls = walls_on(s, hx)
    held = hold >= strength
    events: Events = []
    if walls:
        damage = strength * r["wall_damage_pct"] // 100 if held else strength
        each = -(-damage // len(walls))
        for key, w in walls:
            w["hp"] -= each
            if w["hp"] <= 0:
                del s.walls[key]
                events.append({"kind": "wall_fell", "hex": hx, "edge": int(key.split(":")[1])})
    wrecked, burned = None, {}
    if not held:
        h = s.hexes[hx]
        if h.buildings:
            wrecked = max(h.buildings, key=lambda b: (S(cfg, f"buildings.{b}").get("labour", 0), b))
            h.buildings.remove(wrecked)
        for g in GOODS:
            n = s.goods[g] * r["burn_pct"] // 100
            if n:
                s.goods[g] -= n
                burned[g] = n
    events.insert(
        0,
        {
            "kind": "raid",
            "hex": hx,
            "strength": strength,
            "defence": hold,
            "held": held,
            "wrecked": wrecked,
            "burned": burned,
        },
    )
    s.raids += 1
    s.next_raid += r["every"]
    s.raid_hex = _raid_hex(s)
    return events


# -- saving ---------------------------------------------------------------------------------------


def to_json(s: Settlement) -> str:
    return canonical.dumps(to_dict(s))


def from_json(text: str) -> Settlement:
    return from_dict(Settlement, json.loads(text))
