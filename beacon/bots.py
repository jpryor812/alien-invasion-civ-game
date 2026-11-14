"""A simple deterministic bot that plays a continent, so batch runs exercise every system.

It decides from the fog-safe `PlayerView` and the shared planning helpers (paths, attack
previews), and acts only through commands. It uses no randomness. It is a test driver, not the
M6 AI: it explores, connects cities by road, improves tiles, reclaims and refounds lost cities,
and attacks overrun cities when the preview favours it.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from beacon import cities, combat, economy, hexgrid, improvements, movement, tech
from beacon.commands import (
    Attack,
    BuildImprovement,
    CityAttack,
    Command,
    CommandError,
    Fortify,
    MergeUnits,
    MoveUnit,
    RefoundCity,
    SetProduction,
    SetResearch,
    SkipUnit,
)
from beacon.config import Config
from beacon.paths import reachable, shortest_path
from beacon.state import ALIENS, DORMANT, EMPTY, OVERRUN, GameState, Tile, Unit
from beacon.tiles import is_passable_land
from beacon.units import can_stand, is_civilian, max_hp, occupancy
from beacon.view import PlayerView

Submit = Callable[[Command], Any]


class Bot:
    def __init__(self, state: GameState, cfg: Config, pid: str, submit: Submit):
        self.state, self.cfg, self.pid, self._submit = state, cfg, pid, submit
        self.view = PlayerView(state, cfg, pid)
        self.w, self.h = state.width, state.height

    # -- helpers ---------------------------------------------------------------------------

    def submit(self, cmd: Command) -> bool:
        try:
            self._submit(cmd)
            return True
        except CommandError:
            return False

    def dist(self, a: int, b: int) -> int:
        return hexgrid.distance(a, b, self.w)

    def nearest(self, origin: int, tiles: list[int]) -> int | None:
        return min(tiles, key=lambda t: (self.dist(origin, t), t), default=None)

    def known(self, status: str) -> list[int]:
        return sorted(
            self.view.city_tile(cid)  # type: ignore[misc]
            for cid, memory in self.view.known_cities().items()
            if memory.status == status
        )

    def remembered(self, i: int) -> Tile | None:
        """Terrain of a hex the player has ever explored. The rules re-fog terrain, but the bot
        plans as a human would, from memory of what it has seen (a test-bot allowance)."""
        return self.state.tiles[i] if self.view.is_explored(i) else None

    def alive(self, unit: Unit) -> bool:
        return str(unit.id) in self.state.units

    # -- research and production -----------------------------------------------------------

    def research(self) -> None:
        player = self.view.player
        if player.research is None:
            options = tech.available(self.cfg, player)
            if options:
                best = min(options, key=lambda t: (self.cfg.techs[t]["cost"], t))
                self.submit(SetResearch(player=self.pid, tech=best))

    def _counts(self) -> dict[str, int]:
        counts = {"military": 0, "engineers": 0, "restoration": 0, "recon": 0}
        for u in self.view.my_units():
            spec = self.cfg.units[u.type]
            if spec.get("can_build"):
                counts["engineers"] += 1
            elif spec.get("can_refound"):
                counts["restoration"] += 1
            elif spec["role"] == "recon":
                counts["recon"] += 1
            elif spec["role"] in ("melee", "ranged"):
                counts["military"] += u.count
        return counts

    def _military_choice(self, city: Any, counts: dict[str, int]) -> str | None:
        options = economy.production_options(self.state, self.cfg, city)
        every = self.cfg.bot("production.ranged_every")
        if counts["military"] % every == every - 1:
            ranged = [
                o
                for o in options
                if o.startswith("unit:")
                and self.cfg.units[o[5:]]["role"] == "ranged"
                and self.cfg.units[o[5:]]["domain"] == "land"
            ]
            if ranged:
                return max(ranged, key=lambda o: (self.cfg.units[o[5:]]["ranged_strength"], o))
        for unit_type in self.cfg.bot("production.military_priority"):
            item = f"unit:{unit_type}"
            if item in options and economy.resource_available(
                self.state, self.cfg, self.pid, unit_type
            ):
                return item
        return None

    def production(self) -> None:
        bot = self.cfg.bot("production")
        counts = self._counts()
        cities = [c for c in self.view.my_cities() if c.status == "active"]
        empties = self.known(EMPTY)
        for city in cities:
            if city.queue:
                continue
            options = economy.production_options(self.state, self.cfg, city)
            item = None
            if counts["military"] * 100 < len(cities) * bot["military_per_city_pct"]:
                item = self._military_choice(city, counts)
            elif counts["engineers"] < bot["engineers"] and "unit:engineers" in options:
                item = "unit:engineers"
            elif (
                empties
                and counts["restoration"] < bot["restoration_teams"]
                and "unit:restoration_team" in options
            ):
                item = "unit:restoration_team"
            elif counts["recon"] < bot["recon"] and "unit:recon_team" in options:
                item = "unit:recon_team"
            if item is None:
                for b in bot["building_priority"]:
                    if f"building:{b}" in options:
                        item = f"building:{b}"
                        break
            if item is None:
                item = self._military_choice(city, counts) or "project:wealth"
            if self.submit(SetProduction(player=self.pid, city=city.id, items=(item,))):
                kind = item.split(":", 1)[1]
                if kind == "engineers":
                    counts["engineers"] += 1
                elif kind == "restoration_team":
                    counts["restoration"] += 1
                elif kind == "recon_team":
                    counts["recon"] += 1
                elif item.startswith("unit:"):
                    counts["military"] += 1

    # -- engineers -------------------------------------------------------------------------

    def _network(self) -> set[int]:
        capital = next((c for c in self.view.my_cities() if c.is_capital), None)
        if capital is None:
            return set()
        own = {c.tile for c in self.view.my_cities()}
        lost = {self.view.city_tile(cid) for cid in self.view.known_cities()} - own
        return reachable(
            capital.tile,
            lambda i: hexgrid.neighbours(i, self.w, self.h),
            lambda i: i in own or (self.state.tiles[i].route is not None and i not in lost),
        )

    def _road_todo(self, city_tile: int, net: set[int]) -> int | None:
        """First hex without a road on the cheapest known path from a city to the network."""
        lost = {self.view.city_tile(cid) for cid in self.view.known_cities()}
        lost -= {c.tile for c in self.view.my_cities()}

        def step(_: int, b: int) -> int | None:
            tile = self.remembered(b)
            if tile is None or not is_passable_land(self.cfg, tile) or b in lost:
                return None
            return 0 if tile.route else 1

        path = shortest_path(city_tile, net, lambda i: hexgrid.neighbours(i, self.w, self.h), step)
        if path is None:
            return None
        return next((t for t in path[1:] if self.state.tiles[t].route is None), None)

    def _improvement_for(self, tile_i: int) -> str | None:
        tile = self.state.tiles[tile_i]
        if tile.improvement is not None or not is_passable_land(self.cfg, tile):
            return None
        options = []
        if tile.resource and self.cfg.resources[tile.resource]["improvement"]:
            options.append(self.cfg.resources[tile.resource]["improvement"])
        options += ["mine", "farm"]
        for imp in options:
            spec = self.cfg.improvements[imp]
            if (
                tile.terrain in spec["terrains"]
                and tile.elevation in spec["elevations"]
                and tech.knows(self.view.player, spec["tech"])
                and not (spec.get("requires_resource") and tile.resource is None)
            ):
                return imp
        return None

    def engineer(self, unit: Unit, net: set[int], claimed: set[int]) -> None:
        targets: list[tuple[int, str]] = []
        for city in self.view.my_cities():
            if not city.connected:
                todo = self._road_todo(city.tile, net)
                if todo is not None and todo not in claimed:
                    targets.append((todo, "road"))
        if not targets:
            for city in self.view.my_cities():
                if not city.connected:
                    continue
                for t in economy.work_tiles(self.state, self.cfg, city):
                    imp = self._improvement_for(t)
                    if imp and t not in claimed and self.state.city_at(t) is None:
                        targets.append((t, imp))
        if not targets:
            self.submit(SkipUnit(player=self.pid, unit=unit.id))
            return
        tile, imp = min(targets, key=lambda ti: (self.dist(unit.tile, ti[0]), ti[0]))
        claimed.add(tile)
        if unit.tile == tile:
            if improvements.build_problem(self.state, self.cfg, unit, imp) is None:
                self.submit(BuildImprovement(player=self.pid, unit=unit.id, improvement=imp))
                return
            self.submit(SkipUnit(player=self.pid, unit=unit.id))
            return
        if not self.submit(MoveUnit(player=self.pid, unit=unit.id, target=tile)):
            self.submit(SkipUnit(player=self.pid, unit=unit.id))
            return
        if (
            self.alive(unit)
            and unit.tile == tile
            and unit.moves_left > 0
            and improvements.build_problem(self.state, self.cfg, unit, imp) is None
        ):
            self.submit(BuildImprovement(player=self.pid, unit=unit.id, improvement=imp))

    # -- other civilians and recon ---------------------------------------------------------

    def restorer(self, unit: Unit) -> None:
        target = self.nearest(unit.tile, self.known(EMPTY))
        if target is None:
            self.submit(SkipUnit(player=self.pid, unit=unit.id))
            return
        if unit.tile != target:
            self.submit(MoveUnit(player=self.pid, unit=unit.id, target=target))
        if self.alive(unit) and unit.tile == target and unit.moves_left > 0:
            self.submit(RefoundCity(player=self.pid, unit=unit.id))

    def explorer(self, unit: Unit) -> None:
        start = unit.tile
        seen = {start}
        frontier = [start]
        attempts = self.cfg.bot("explore.attempts")
        while frontier and attempts > 0:
            frontier.sort(key=lambda t: (self.dist(start, t), t))
            nxt: list[int] = []
            for t in frontier:
                tile = self.remembered(t)
                if tile is None:
                    continue
                if t != start and any(
                    not self.view.is_explored(n) for n in hexgrid.neighbours(t, self.w, self.h)
                ):
                    if self.submit(MoveUnit(player=self.pid, unit=unit.id, target=t)):
                        return
                    attempts -= 1
                    if attempts <= 0:
                        break
                for n in hexgrid.neighbours(t, self.w, self.h):
                    nt = self.remembered(n)
                    if n not in seen and nt is not None and is_passable_land(self.cfg, nt):
                        seen.add(n)
                        nxt.append(n)
            frontier = nxt
        self.submit(Fortify(player=self.pid, unit=unit.id))

    # -- military --------------------------------------------------------------------------

    def _best_attack(self, unit: Unit) -> int | None:
        ratio = self.cfg.bot("combat.attack_ratio_pct")
        reach = max(1, self.cfg.units[unit.type]["range"])
        best = None
        for t in hexgrid.within(unit.tile, reach, self.w, self.h):
            if not self.view.is_visible(t):
                continue
            p = combat.preview_attack(self.state, self.cfg, unit, t)
            if not p["legal"]:
                continue
            dealt = p["damage_to_defender"]["expected"]
            taken = p["damage_to_attacker"]["expected"]
            if taken >= unit.hp:
                continue
            if "city" in p["defender"]:
                # Siege: shell cities freely; melee attacks on a good trade, to finish the
                # city, or once it is weakened if the unit can afford the losses.
                city = self.state.cities[p["defender"]["city"]]
                weak = city.hp * 100 <= cities.max_hp(self.cfg, city, self.state) * self.cfg.bot(
                    "combat.siege_city_hp_pct"
                )
                good_trade = dealt * 100 >= ratio * max(1, taken)
                if not (
                    taken == 0
                    or dealt >= city.hp
                    or good_trade
                    or (weak and taken * 2 < unit.hp)
                ):
                    continue
            elif dealt * 100 < ratio * max(1, taken):
                continue
            key = (dealt >= p["defender"]["hp"], dealt - taken, -t)
            if best is None or key > best[0]:
                best = (key, t)
        return None if best is None else best[1]

    def _try_merge(self, unit: Unit) -> Unit:
        if unit.count != 1 or is_civilian(self.cfg, unit.type):
            return unit
        threshold = self.cfg.bot("combat.merge_min_hp_pct")
        stack_hp = self.cfg.t("combat.unit_max_hp") * self.cfg.t("combat.stack_size")
        for n in hexgrid.neighbours(unit.tile, self.w, self.h):
            for other in self.state.units_at(n):
                if (
                    other.owner == self.pid
                    and other.type == unit.type
                    and movement.merge_problem(self.state, self.cfg, unit, other) is None
                    and (unit.hp + other.hp) * 100 >= stack_hp * threshold
                    and self.submit(MergeUnits(player=self.pid, unit=unit.id, into=other.id))
                ):
                    return other
        return unit

    def _approach(self, unit: Unit, city_tile: int) -> bool:
        occ = occupancy(self.state)
        spots = [
            n
            for n in hexgrid.within(
                city_tile, max(1, self.cfg.units[unit.type]["range"]), self.w, self.h
            )
            if n != city_tile
            and (n == unit.tile or can_stand(self.state, self.cfg, occ, unit.type, self.pid, n))
        ]
        spot = self.nearest(unit.tile, spots)
        if spot is None or spot == unit.tile:
            return False
        return self.submit(MoveUnit(player=self.pid, unit=unit.id, target=spot))

    def _garrisons(self) -> dict[int, int]:
        """Assign one land military unit to the capital and to every own city within
        garrison_radius of known aliens (city tile -> unit id), nearest first. Units already
        standing in such a city keep it."""
        mil = [
            u
            for u in self.view.my_units()
            if self.cfg.units[u.type]["role"] in ("melee", "ranged")
            and self.cfg.units[u.type]["domain"] == "land"
        ]
        out: dict[int, int] = {}
        taken: set[int] = set()
        radius = self.cfg.bot("combat.garrison_radius")
        danger = self.known(OVERRUN) + [
            u.tile for u in self.view.visible_units() if u.owner == ALIENS
        ]
        cities = sorted(
            (
                c
                for c in self.view.my_cities()
                if c.is_capital or any(self.dist(c.tile, d) <= radius for d in danger)
            ),
            key=lambda c: c.id,
        )
        for city in cities:
            here = next((u for u in mil if u.tile == city.tile), None)
            if here is not None:
                out[city.tile] = here.id
                taken.add(here.id)
        for city in cities:
            if city.tile in out:
                continue
            free = [u for u in mil if u.id not in taken]
            best = min(free, key=lambda u: (self.dist(u.tile, city.tile), u.id), default=None)
            if best is not None:
                out[city.tile] = best.id
                taken.add(best.id)
        return out

    def guard(self, unit: Unit, city_tile: int) -> None:
        """Hold a city: ranged garrisons fire, melee garrisons never leave the walls."""
        if unit.tile != city_tile:
            self.submit(MoveUnit(player=self.pid, unit=unit.id, target=city_tile))
        if not self.alive(unit) or unit.moves_left <= 0:
            return
        if unit.tile == city_tile and self.cfg.units[unit.type]["role"] == "ranged":
            target = self._best_attack(unit)
            if target is not None:
                self.submit(Attack(player=self.pid, unit=unit.id, target=target))
                return
        if unit.order != "fortify":
            self.submit(Fortify(player=self.pid, unit=unit.id))

    def bombard(self) -> None:
        for city in self.view.my_cities():
            best = None
            for t in hexgrid.within(city.tile, self.cfg.t("cities.attack_range"), self.w, self.h):
                if combat.city_attack_problem(self.state, self.cfg, city, t, self.view.visible):
                    continue
                victim = combat.defender_at(self.state, self.cfg, self.pid, t)
                key = (-(victim.hp if victim else 0), -t)
                if best is None or key > best[0]:
                    best = (key, t)
            if best is not None:
                self.submit(CityAttack(player=self.pid, city=city.id, target=best[1]))

    def threats(self) -> list[int]:
        """Visible alien units near own cities."""
        own = [c.tile for c in self.view.my_cities()]
        radius = self.cfg.bot("combat.threat_radius")
        return sorted(
            u.tile
            for u in self.view.visible_units()
            if u.owner == ALIENS and any(self.dist(u.tile, t) <= radius for t in own)
        )

    def soldier(self, unit: Unit) -> None:
        if self.cfg.units[unit.type]["domain"] != "land":
            self.submit(Fortify(player=self.pid, unit=unit.id))
            return
        unit = self._try_merge(unit)
        if not self.alive(unit) or unit.moves_left <= 0:
            return
        target = self._best_attack(unit)
        if target is not None:
            self.submit(Attack(player=self.pid, unit=unit.id, target=target))
            return
        own = [c.tile for c in self.view.my_cities()]
        if unit.hp * 100 < max_hp(self.cfg, unit) * self.cfg.bot("combat.retreat_hp_pct"):
            home = self.nearest(unit.tile, own)
            if home is not None and home != unit.tile:
                self.submit(MoveUnit(player=self.pid, unit=unit.id, target=home))
            if self.alive(unit) and unit.moves_left > 0:
                self.submit(Fortify(player=self.pid, unit=unit.id))
            return
        threat = self.nearest(unit.tile, self.threats())
        if threat is not None and self._approach(unit, threat):
            return
        dormant = self.nearest(unit.tile, self.known(DORMANT))
        if dormant is not None and self.submit(
            MoveUnit(player=self.pid, unit=unit.id, target=dormant)
        ):
            return
        overrun = self.nearest(unit.tile, self.known(OVERRUN))
        in_reach = overrun is not None and self.dist(unit.tile, overrun) <= max(
            1, self.cfg.units[unit.type]["range"]
        )
        if overrun is not None and not in_reach and self._approach(unit, overrun):
            return
        if overrun is None and dormant is None:
            self.explorer(unit)  # nothing known to free: go and find some
            return
        self.submit(Fortify(player=self.pid, unit=unit.id))

    # -- turn ------------------------------------------------------------------------------

    def play(self) -> None:
        self.research()
        self.production()
        self.bombard()
        net = self._network()
        claimed: set[int] = set()
        garrisons = {uid: tile for tile, uid in self._garrisons().items()}
        for unit in self.view.my_units():
            if not self.alive(unit) or unit.moves_left <= 0 or unit.job is not None:
                continue
            spec = self.cfg.units[unit.type]
            if spec.get("can_build"):
                self.engineer(unit, net, claimed)
            elif spec.get("can_refound"):
                self.restorer(unit)
            elif spec["role"] == "recon":
                self.explorer(unit)
            elif unit.id in garrisons:
                self.guard(unit, garrisons[unit.id])
            else:
                self.view = PlayerView(self.state, self.cfg, self.pid)
                self.soldier(unit)


def take_turn(state: GameState, cfg: Config, pid: str, submit: Submit) -> None:
    Bot(state, cfg, pid, submit).play()
