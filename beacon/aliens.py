"""The alien faction (docs/SPEC_M4.md): progress and tech, city growth and spawning,
reinforcements, lost-city decay, surges, raids and the invasion director.

Aliens see the whole map (designer decision). They never cross water: all their units are land
units. Their randomness comes only from the `events` stream, keyed by turn and purpose; given the
same state they always act the same way.
"""

from __future__ import annotations

from typing import Any

from beacon import combat, fog, hexgrid, rng
from beacon.cities import alien_effect, max_hp
from beacon.config import Config
from beacon.liberation import update_fallen
from beacon.movement import find_path, move_along
from beacon.state import (
    ACTIVE,
    ALIENS,
    DORMANT,
    EMPTY,
    OVERRUN,
    AlienOrder,
    City,
    GameState,
    Unit,
)
from beacon.tiles import is_passable_land
from beacon.units import can_stand, is_civilian, occupancy, place_unit

Events = list[dict[str, Any]]


def _ev(state: GameState, kind: str, **data: Any) -> dict[str, Any]:
    return {"turn": state.turn, "kind": kind, "player": ALIENS, **data}


def alien_cities(state: GameState) -> list[City]:
    return [c for c in state.cities if c.status == OVERRUN]


def unlocked_units(state: GameState, cfg: Config) -> list[str]:
    known = set(state.aliens.techs)
    return sorted(
        u
        for u, spec in cfg.units.items()
        if spec["faction"] == "alien" and spec.get("alien_tech") in (None, *known)
    )


# -- progress and tech -----------------------------------------------------------------------


def progress_rate(state: GameState, cfg: Config) -> int:
    p = cfg.alien("progress")
    held = alien_cities(state)
    pop = sum(c.pop for c in held)
    return max(p["floor"], p["base"] + p["per_city"] * len(held) + pop * p["per_pop_pct"] // 100)


def research(state: GameState, cfg: Config) -> Events:
    al = state.aliens
    al.progress += progress_rate(state, cfg)
    events: Events = []
    for tech in cfg.alien_tech_order():
        if tech in al.techs:
            continue
        cost = cfg.alien_techs[tech]["cost"]
        if al.progress < cost:
            break
        al.progress -= cost
        al.techs.append(tech)
        events.append(_ev(state, "alien_tech", tech=tech))
    return events


# -- cities ----------------------------------------------------------------------------------


def _military_on(state: GameState, cfg: Config, tile: int) -> Unit | None:
    for u in state.units_at(tile):
        if not is_civilian(cfg, u.type):
            return u
    return None


def city_turn(state: GameState, cfg: Config) -> Events:
    """Growth and spawning for every alien city."""
    c = cfg.alien("cities")
    events: Events = []
    units = [u for u in state.units.values() if u.owner == ALIENS]
    options = [u for u in unlocked_units(state, cfg) if u in c["spawn_weights"]]
    for city in alien_cities(state):
        city.food_store += c["food_per_turn"] + alien_effect(state, cfg, "growth")
        cap = c["max_pop"] + alien_effect(state, cfg, "max_pop")
        if city.food_store >= c["growth_threshold"]:
            city.food_store -= c["growth_threshold"]
            if city.pop < cap:
                city.pop += 1
        city.production_store += (
            c["base_production"]
            + c["production_per_pop"] * city.pop
            + alien_effect(state, cfg, "production")
        )
        if _military_on(state, cfg, city.tile) is None:
            want = c["garrison"]
        elif len(units) * 100 >= len(alien_cities(state)) * c["units_per_city_pct"]:
            continue
        else:
            nearby = sum(
                1
                for u in units
                if hexgrid.distance(u.tile, city.tile, state.width) <= c["nearby_radius"]
            )
            if nearby >= c["max_units_nearby"] or not options:
                continue
            r = rng.stream(state.seed, "events", state.turn, "spawn", city.id)
            want = rng.weighted_choice(r, options, [c["spawn_weights"][o] for o in options])
        cost = cfg.units[want]["cost"]
        if city.production_store < cost:
            continue
        unit = place_unit(state, cfg, want, ALIENS, city.tile, c["nearby_radius"])
        if unit is None:
            continue
        city.production_store -= cost
        units.append(unit)
        events.append(_ev(state, "alien_spawned", city=city.id, unit=unit.id, type=want))
    return events


def heal(state: GameState, cfg: Config) -> None:
    extra = alien_effect(state, cfg, "heal")
    if not extra:
        return
    for u in state.units.values():
        if u.owner == ALIENS:
            u.hp = min(cfg.t("combat.unit_max_hp") * u.count, u.hp + extra * u.count)


# -- reinforcements, surges, decay -------------------------------------------------------------


def _open_land(state: GameState, cfg: Config, continent: str, away: int) -> list[int]:
    """Passable land on a continent at least `away` hexes from every player city."""
    player_tiles = [c.tile for c in state.cities if c.owner in state.players]
    occ = occupancy(state)
    return [
        i
        for i, t in enumerate(state.tiles)
        if t.continent == continent
        and is_passable_land(cfg, t)
        and state.city_at(i) is None
        and not occ.get(i)
        and all(hexgrid.distance(i, p, state.width) >= away for p in player_tiles)
    ]


def _land_group(
    state: GameState, cfg: Config, unit_types: list[str], near: int, kind: str
) -> Events:
    events: Events = []
    radius = cfg.alien("cities.nearby_radius")
    for unit_type in unit_types:
        unit = place_unit(state, cfg, unit_type, ALIENS, near, radius)
        if unit is not None:
            events.append(_ev(state, kind, unit=unit.id, type=unit_type, tile=unit.tile))
    return events


def reinforcements(state: GameState, cfg: Config) -> Events:
    r_cfg = cfg.alien("reinforcements")
    al = state.aliens
    if al.reinforcements_stopped or not al.mothership_alive:
        return []
    al.reinforcement_store += r_cfg["per_turn"]
    if al.reinforcement_store < r_cfg["cost"]:
        return []
    al.reinforcement_store -= r_cfg["cost"]
    r = rng.stream(state.seed, "events", state.turn, "reinforcements")
    held = alien_cities(state)
    if held:
        near = r.choice(held).tile
    else:
        continents = sorted({c.continent for c in state.cities})
        spots = _open_land(state, cfg, r.choice(continents), r_cfg["landing_distance"])
        if not spots:
            return []
        near = r.choice(spots)
    return _land_group(state, cfg, list(r_cfg["units"]), near, "alien_reinforcement")


def surge(state: GameState, cfg: Config) -> Events:
    s = cfg.alien("surge")
    al = state.aliens
    if al.reinforcements_stopped or not al.mothership_alive:
        return []  # surges come from the mothership too
    if al.surge_cooldown > 0:
        al.surge_cooldown -= 1
        return []
    held = len(alien_cities(state))
    libs = {pid: p.credits.get("cities_liberated", 0) for pid, p in state.players.items()}
    leader = max(sorted(libs), key=lambda pid: libs[pid], default=None)
    if leader is None:
        return []
    avg = sum(libs.values()) // max(1, len(libs))
    losing = al.start_cities and held * 100 < al.start_cities * s["city_pct"]
    if not losing and libs[leader] - avg < s["lead"]:
        return []
    frontier = [c for c in state.cities if c.owner == leader and c.status == ACTIVE]
    if not frontier:
        return []
    capital = next((c for c in frontier if c.is_capital), frontier[0])
    target = max(
        frontier, key=lambda c: (hexgrid.distance(c.tile, capital.tile, state.width), -c.id)
    )
    ring = [
        t
        for t in hexgrid.within(target.tile, s["distance"], state.width, state.height)
        if hexgrid.distance(t, target.tile, state.width) == s["distance"]
        and state.tiles[t].continent == target.continent
        and is_passable_land(cfg, state.tiles[t])
    ]
    if not ring:
        return []
    r = rng.stream(state.seed, "events", state.turn, "surge")
    best = sorted(
        (u for u in unlocked_units(state, cfg) if u in cfg.alien("cities.spawn_weights")),
        key=lambda u: (-cfg.units[u]["strength"], u),
    )
    types = [best[i % len(best)] for i in range(s["size"])] if best else []
    al.surge_cooldown = s["cooldown"]
    events = [_ev(state, "alien_surge", target_player=leader, city=target.id)]
    events.extend(_land_group(state, cfg, types, r.choice(ring), "alien_surge_unit"))
    return events


def decay(state: GameState, cfg: Config) -> Events:
    """Unreached dormant and empty cities may fall to the aliens (DESIGN.md 5)."""
    d = cfg.alien("decay")
    events: Events = []
    held = alien_cities(state)
    guards = [
        u for u in state.units.values() if u.owner in state.players and not is_civilian(cfg, u.type)
    ]
    garrison = cfg.alien("cities.garrison")
    for city in state.cities:
        if city.status not in (DORMANT, EMPTY):
            continue
        if any(
            hexgrid.distance(u.tile, city.tile, state.width) <= d["guard_radius"] for u in guards
        ):
            continue
        near = sum(
            1 for c in held if hexgrid.distance(c.tile, city.tile, state.width) <= d["near_radius"]
        )
        chance = min(
            d["cap_permille"],
            d["base_permille"]
            + state.turn // d["interval_turns"] * d["per_interval_permille"]
            + near * d["near_permille"],
        )
        r = rng.stream(state.seed, "events", state.turn, "decay", city.id)
        if r.randrange(1000) >= chance:
            continue
        for u in state.units_at(city.tile):  # civilians standing in an empty city are lost
            combat.damage_unit(state, cfg, u, u.hp, ALIENS)
        previous = city.status
        city.status, city.owner = OVERRUN, ALIENS
        city.pop = max(1, city.pop)
        city.hp = max_hp(cfg, city, state)
        place_unit(state, cfg, garrison, ALIENS, city.tile, 0)
        events.append(_ev(state, "city_fell", city=city.id, previous=previous))
    return events


# -- raids -----------------------------------------------------------------------------------


def pillage(state: GameState, cfg: Config, unit: Unit) -> Events:
    tile = state.tiles[unit.tile]
    if tile.built_by not in state.players or state.city_at(unit.tile) is not None:
        return []
    if tile.improvement:
        lost, tile.improvement = tile.improvement, None
    elif tile.route:
        lost, tile.route = tile.route, None
    else:
        return []
    owner = tile.built_by
    if tile.improvement is None and tile.route is None:
        tile.built_by = None
        fog.touch_built(state)
    unit.moves_left = 0
    unit.acted = True
    return [_ev(state, "pillaged", unit=unit.id, tile=unit.tile, lost=lost, owner=owner)]


# -- director ----------------------------------------------------------------------------------


class Director:
    def __init__(self, state: GameState, cfg: Config):
        self.state, self.cfg = state, cfg
        self.d = cfg.alien("director")
        self.w, self.h = state.width, state.height
        self.events: Events = []
        self._defence: dict[int, int] = {}

    def dist(self, a: int, b: int) -> int:
        return hexgrid.distance(a, b, self.w)

    def continent(self, tile: int) -> str | None:
        return self.state.tiles[tile].continent

    def alive(self, unit: Unit) -> bool:
        return str(unit.id) in self.state.units

    def defence(self, city: City) -> int:
        """City strength plus nearby player military strength (hundredths)."""
        if city.id not in self._defence:
            total = combat.city_strength(self.state, self.cfg, city).total
            for u in self.state.units.values():
                if (
                    u.owner in self.state.players
                    and not is_civilian(self.cfg, u.type)
                    and self.dist(u.tile, city.tile) <= 2
                    and u.tile != city.tile
                ):
                    total += combat.unit_strength(
                        self.state, self.cfg, u, ranged=False, defending=True
                    ).total
            self._defence[city.id] = total
        return self._defence[city.id]

    def strength_near(self, tile: int) -> int:
        return sum(
            combat.unit_strength(self.state, self.cfg, u, ranged=False, defending=False).total
            for u in self.state.units.values()
            if u.owner == ALIENS
            and self.dist(u.tile, tile) <= self.d["gather_radius"]
            and self.state.city_at(u.tile) is None
        )

    # -- order choice --------------------------------------------------------------------

    def siege_target(self, unit: Unit) -> int | None:
        from beacon.endgame import barrage_running

        cont = self.continent(unit.tile)
        running = barrage_running(self.state)
        host = running.host_city if running is not None else None
        best = None
        for city in self.state.cities:
            if city.status != ACTIVE or city.owner not in self.state.players:
                continue
            if self.continent(city.tile) != cont:
                continue
            value = self.d["value_base"] + city.pop * self.d["value_per_pop"]
            if city.is_capital:
                value += self.d["value_capital"]
            if host is not None and city.id == host:
                value += self.cfg.t("endgame.barrage.host_siege_value")  # the aliens know
            if city.liberated_turn is not None and (
                self.state.turn - city.liberated_turn <= self.d["retake_turns"]
            ):
                value += self.d["value_retake"]
            score = (
                value
                - self.defence(city) * self.d["defence_per_strength"] // 100
                - self.dist(unit.tile, city.tile) * self.d["distance_penalty"]
            )
            key = (score, -city.tile)
            if best is None or key > best[0]:
                best = (key, city.tile)
        return None if best is None else best[1]

    def raid_target(self, unit: Unit) -> int | None:
        cont = self.continent(unit.tile)
        options = [
            i
            for i in hexgrid.within(unit.tile, self.d["raid_radius"], self.w, self.h)
            if self.state.tiles[i].built_by in self.state.players
            and self.continent(i) == cont
            and self.state.city_at(i) is None
            and (self.state.tiles[i].route or self.state.tiles[i].improvement)
        ]
        return min(options, key=lambda i: (self.dist(unit.tile, i), i), default=None)

    def patrol_target(self, unit: Unit) -> int | None:
        cont = self.continent(unit.tile)
        options = [
            i
            for i in hexgrid.within(unit.tile, self.d["patrol_radius"], self.w, self.h)
            if self.continent(i) == cont
            and is_passable_land(self.cfg, self.state.tiles[i])
            and i != unit.tile
        ]
        if not options:
            return None
        return rng.stream(self.state.seed, "events", self.state.turn, "patrol", unit.id).choice(
            options
        )

    def hunt_target(self, unit: Unit) -> int | None:
        """A lone player unit outside cities to pick off, weakest first (stored as its id)."""
        cont = self.continent(unit.tile)
        best = None
        for u in self.state.units.values():
            if u.owner not in self.state.players or self.state.city_at(u.tile) is not None:
                continue
            if self.continent(u.tile) != cont:
                continue
            d = self.dist(unit.tile, u.tile)
            if d > self.d["hunt_radius"]:
                continue
            weak = combat.unit_strength(self.state, self.cfg, u, ranged=False, defending=True).total
            key = (weak, d, u.id)
            if best is None or key < best[0]:
                best = (key, u.id)
        return None if best is None else best[1]

    def gather_cohort(self, leader: Unit, target: int) -> None:
        """Nearby aliens without a siege join the leader's siege (a cohort of seeded size)."""
        r = rng.stream(self.state.seed, "events", self.state.turn, "cohort", leader.id)
        size = r.randint(self.d["cohort_min"], self.d["cohort_max"])
        orders = self.state.aliens.orders
        near = sorted(
            (
                u
                for u in self.state.units.values()
                if u.owner == ALIENS
                and u.id != leader.id
                and not is_civilian(self.cfg, u.type)
                and self.dist(u.tile, leader.tile) <= self.d["cohort_radius"]
                and not (
                    self.state.city_at(u.tile) is not None
                    and _military_on(self.state, self.cfg, u.tile) is u
                )
                and (str(u.id) not in orders or orders[str(u.id)].kind != "siege")
            ),
            key=lambda u: (self.dist(u.tile, leader.tile), u.id),
        )
        for u in near[: size - 1]:
            orders[str(u.id)] = AlienOrder(kind="siege", target=target)

    def order_for(self, unit: Unit) -> AlienOrder | None:
        orders = self.state.aliens.orders
        current = orders.get(str(unit.id))
        if current is not None and self.order_valid(unit, current):
            return current
        kinds = sorted(self.d["weights"])
        if self.state.turn < self.d["grace_turns"]:
            kinds = ["patrol"]
        elif self.state.turn < self.d["city_grace_turns"]:
            kinds = [k for k in kinds if k != "siege"]  # warm-up: no attacks on player cities
        r = rng.stream(self.state.seed, "events", self.state.turn, "order", unit.id)
        for _ in range(len(kinds)):
            kind = rng.weighted_choice(r, kinds, [self.d["weights"][k] for k in kinds])
            target = {
                "siege": self.siege_target,
                "raid": self.raid_target,
                "patrol": self.patrol_target,
                "hunt": self.hunt_target,
            }[kind](unit)
            if target is not None:
                orders[str(unit.id)] = AlienOrder(kind=kind, target=target)
                if kind == "siege":
                    self.gather_cohort(unit, target)
                return orders[str(unit.id)]
        orders.pop(str(unit.id), None)
        return None

    def order_valid(self, unit: Unit, order: AlienOrder) -> bool:
        tile = self.state.tiles[order.target]
        if order.kind == "siege":
            city = self.state.city_at(order.target)
            return city is not None and city.status == ACTIVE and city.owner in self.state.players
        if order.kind == "raid":
            return tile.built_by in self.state.players and bool(tile.route or tile.improvement)
        if order.kind == "hunt":
            prey = self.state.units.get(str(order.target))
            return (
                prey is not None
                and self.state.city_at(prey.tile) is None
                and self.dist(unit.tile, prey.tile) <= 2 * self.d["hunt_radius"]
            )
        return unit.tile != order.target

    # -- acting ----------------------------------------------------------------------------

    def favourable(self, unit: Unit, target: int, allow_city: bool) -> int | None:
        p = combat.preview_attack(self.state, self.cfg, unit, target)
        if not p["legal"]:
            return None
        if "city" in p["defender"] and not allow_city:
            return None
        dealt = p["damage_to_defender"]["expected"]
        taken = p["damage_to_attacker"]["expected"]
        if p["kind"] == "capture":
            return 1000
        if taken >= unit.hp:
            return None
        if dealt >= p["defender"]["hp"] or dealt * 100 >= self.d["attack_ratio_pct"] * max(
            1, taken
        ):
            return dealt - taken
        return None

    def best_attack(self, unit: Unit, allow_city: bool) -> int | None:
        reach = max(1, self.cfg.units[unit.type]["range"])
        best = None
        for t in hexgrid.within(unit.tile, reach, self.w, self.h):
            score = self.favourable(unit, t, allow_city)
            if score is not None and (best is None or (score, -t) > best[0]):
                best = ((score, -t), t)
        return None if best is None else best[1]

    def attack(self, unit: Unit, target: int) -> None:
        self.events.extend(combat.attack(self.state, self.cfg, unit, target))
        self._defence.clear()

    def move_toward(self, unit: Unit, target: int, stop_at: int = 0) -> bool:
        occ = occupancy(self.state)
        if stop_at > 0 or not can_stand(
            self.state, self.cfg, occ, unit.type, ALIENS, target, ignore=unit.id
        ):
            spots = [
                t
                for t in hexgrid.within(target, max(1, stop_at), self.w, self.h)
                if t != target
                and (t == unit.tile or can_stand(self.state, self.cfg, occ, unit.type, ALIENS, t))
            ]
            if not spots:
                return False
            target = min(spots, key=lambda t: (self.dist(unit.tile, t), t))
            if target == unit.tile:
                return False
        found = find_path(self.state, self.cfg, unit, target, occ=occ)
        if found is None or len(found[0]) < 2:
            return False
        moved = move_along(self.state, self.cfg, unit, found[0])
        if not moved:
            found = find_path(self.state, self.cfg, unit, target, occ=occ, avoid_friends=True)
            if found is not None and len(found[0]) >= 2:
                moved = move_along(self.state, self.cfg, unit, found[0])
        self.events.extend(dict(e, turn=self.state.turn, player=ALIENS) for e in moved)
        return bool(moved)

    def act(self, unit: Unit) -> None:
        city_here = self.state.city_at(unit.tile)
        is_garrison = (
            city_here is not None
            and city_here.status == OVERRUN
            and _military_on(self.state, self.cfg, unit.tile) is unit
        )
        target = self.best_attack(unit, allow_city=False)
        if target is not None:
            self.attack(unit, target)
            return
        if is_garrison:
            unit.fortified = True
            return
        # an undefended alien city nearby takes priority
        empty = [
            c.tile
            for c in alien_cities(self.state)
            if _military_on(self.state, self.cfg, c.tile) is None
            and self.dist(c.tile, unit.tile) <= self.d["gather_radius"]
        ]
        if empty:
            self.move_toward(unit, min(empty, key=lambda t: (self.dist(unit.tile, t), t)))
            return
        order = self.order_for(unit)
        if order is None:
            return
        if order.kind == "siege":
            city = self.state.city_at(order.target)
            assert city is not None
            ready = (
                self.strength_near(city.tile) * 100
                >= self.defence(city) * self.d["siege_ratio_pct"]
            )
            reach = max(1, self.cfg.units[unit.type]["range"])
            if (
                ready
                and self.dist(unit.tile, city.tile) <= reach
                and combat.attack_problem(self.state, self.cfg, unit, city.tile) is None
            ):
                self.attack(unit, city.tile)
                return
            stop = 1 if ready else self.d["gather_radius"] - 1
            if self.dist(unit.tile, city.tile) > stop:
                self.move_toward(unit, city.tile, stop_at=stop)
            return
        if order.kind == "hunt":
            prey = self.state.units[str(order.target)]
            if self.dist(unit.tile, prey.tile) <= max(1, self.cfg.units[unit.type]["range"]):
                if self.favourable(unit, prey.tile, allow_city=False) is not None:
                    self.attack(unit, prey.tile)
                return
            if not self.move_toward(unit, prey.tile, stop_at=1):
                self.state.aliens.orders.pop(str(unit.id), None)
            return
        if order.kind == "raid":
            if unit.tile == order.target:
                self.events.extend(pillage(self.state, self.cfg, unit))
                self.state.aliens.orders.pop(str(unit.id), None)
            elif not self.move_toward(unit, order.target):
                self.state.aliens.orders.pop(str(unit.id), None)
            return
        if not self.move_toward(unit, order.target):
            self.state.aliens.orders.pop(str(unit.id), None)

    def run(self) -> Events:
        for unit in [u for u in self.state.sorted_units() if u.owner == ALIENS]:
            if self.alive(unit) and unit.moves_left > 0 and unit.attacks_left > 0:
                self.act(unit)
        live = {str(u.id) for u in self.state.units.values()}
        for key in [k for k in self.state.aliens.orders if k not in live]:
            del self.state.aliens.orders[key]
        return self.events


def alien_phase(state: GameState, cfg: Config) -> Events:
    events: Events = []
    events.extend(research(state, cfg))
    heal(state, cfg)
    events.extend(decay(state, cfg))
    events.extend(city_turn(state, cfg))
    events.extend(reinforcements(state, cfg))
    events.extend(surge(state, cfg))
    events.extend(Director(state, cfg).run())
    from beacon.endgame import strikes

    events.extend(strikes(state, cfg))
    events.extend(update_fallen(state))
    for e in events:
        e.setdefault("turn", state.turn)
    return events
