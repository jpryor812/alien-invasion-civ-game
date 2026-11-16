"""A simple deterministic bot that plays a continent, so batch runs exercise every system.

It decides from the fog-safe `PlayerView` and the shared planning helpers (paths, attack
previews), and acts only through commands. It uses no randomness. It is a test driver, not the
M6 AI: it explores, connects cities by road, improves tiles, reclaims and refounds lost cities,
and attacks overrun cities when the preview favours it.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from beacon import (
    cities,
    combat,
    economy,
    hexgrid,
    improvements,
    movement,
    promotions,
    recruits,
    tech,
)
from beacon.commands import (
    AcceptOffer,
    Attack,
    BuildImprovement,
    ChooseStory,
    CityAttack,
    Command,
    CommandError,
    DeclineOffer,
    Fortify,
    MergeUnits,
    MoveUnit,
    OfferRecruit,
    PromoteUnit,
    RefoundCity,
    SeatRecruit,
    SetProduction,
    SetResearch,
    SkipUnit,
    UpgradeDefence,
)
from beacon.config import Config
from beacon.contact import on_air
from beacon.paths import reachable, shortest_path
from beacon.state import ALIENS, DORMANT, EMPTY, OVERRUN, GameState, Tile, Unit
from beacon.tiles import is_passable_land, is_water
from beacon.units import can_stand, is_civilian, max_hp, occupancy
from beacon.view import PlayerView

Submit = Callable[[Command], Any]


class Bot:
    def __init__(self, state: GameState, cfg: Config, pid: str, submit: Submit):
        self.state, self.cfg, self.pid, self._submit = state, cfg, pid, submit
        self.view = PlayerView(state, cfg, pid)
        self.w, self.h = state.width, state.height
        self._frontier_cache: list[int] | None = None
        self._sea_frontier_cache: list[int] | None = None
        self.reserved: set[int] = set()  # units given other orders this turn (AI expeditions)
        self._armed = False  # armed a resistance this turn

    # -- helpers ---------------------------------------------------------------------------

    def param(self, path: str) -> Any:
        """A bot setting (data/bots.yaml). The AI overrides some by character."""
        return self.cfg.bot(path)

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

    def known(self, status: str, continent: str | None = None) -> list[int]:
        """Tiles of known cities with this status, optionally only on one continent."""
        return sorted(
            self.view.city_tile(cid)  # type: ignore[misc]
            for cid, memory in self.view.known_cities().items()
            if memory.status == status
            and (continent is None or self.state.cities[cid].continent == continent)
        )

    def here(self, unit: Unit) -> str | None:
        return self.state.tiles[unit.tile].continent

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
                first = [t for t in self.param("research.priority") if t in options]
                best = (
                    first[0]
                    if first
                    else min(options, key=lambda t: (self.cfg.techs[t]["cost"], t))
                )
                self.submit(SetResearch(player=self.pid, tech=best))

    def _counts(self) -> dict[str, int]:
        counts = {"military": 0, "engineers": 0, "restoration": 0, "recon": 0, "boats": 0}
        for u in self.view.my_units():
            spec = self.cfg.units[u.type]
            if spec.get("can_build"):
                counts["engineers"] += 1
            elif spec.get("can_refound"):
                counts["restoration"] += 1
            elif spec["role"] == "recon" and spec["domain"] == "sea":
                counts["boats"] += 1
            elif spec["role"] == "recon":
                counts["recon"] += 1
            elif spec["role"] in ("melee", "ranged") and not spec.get("fixed"):
                counts["military"] += u.count
        return counts

    def _military_choice(self, city: Any, counts: dict[str, int]) -> str | None:
        options = economy.production_options(self.state, self.cfg, city)
        every = self.param("production.ranged_every")
        if counts["military"] % every == every - 1:
            ranged = [
                o
                for o in options
                if o.startswith("unit:")
                and self.cfg.units[o[5:]]["role"] == "ranged"
                and self.cfg.units[o[5:]]["domain"] == "land"
                and not self.cfg.units[o[5:]].get("fixed")
                and economy.resource_available(self.state, self.cfg, self.pid, o[5:])
            ]
            if ranged:
                return max(ranged, key=lambda o: (self.cfg.units[o[5:]]["ranged_strength"], o))
        for unit_type in self.param("production.military_priority"):
            item = f"unit:{unit_type}"
            if item in options and economy.resource_available(
                self.state, self.cfg, self.pid, unit_type
            ):
                return item
        return None

    def production(self) -> None:
        bot = {
            k: self.param(f"production.{k}")
            for k in (
                "capital_build_military_pct",
                "capital_priority",
                "military_per_city_pct",
                "min_military",
                "scout_boats",
                "engineers",
                "recon",
                "building_priority",
            )
        }
        counts = self._counts()
        cities = [c for c in self.view.my_cities() if c.status == "active"]
        # Every continent's city list is public (real cities): while some are still unfound in
        # the fog, scouting comes first.
        found = sum(
            1
            for k in self.view.player.known_cities
            if self.state.cities[int(k)].continent == self.pid
        )
        searching = found < len(self.cfg.continents[self.pid]["cities"])
        unmet = len(self.state.players[self.pid].met) < len(self.state.player_ids()) - 1
        for city in cities:
            head = city.queue[0] if city.queue else ""
            starved = head.startswith("unit:") and not economy.resource_available(
                self.state, self.cfg, self.pid, head[5:]
            )
            if city.queue and not starved:
                continue
            options = economy.production_options(self.state, self.cfg, city)
            item = None
            radio = f"building:{self.cfg.t('contact.radio_building')}"
            if radio in options and self.pid not in on_air(self.state, self.cfg):
                item = radio  # reach the other continents first (designer 2026-11-16)
            elif "unit:uav_patrol" in options and counts["military"] >= 2:
                item = "unit:uav_patrol"  # sees strikes coming (designer 2026-11-16)
            elif (
                city.is_capital
                and counts["military"] * 100 >= len(cities) * bot["capital_build_military_pct"]
            ):
                item = next(
                    (
                        f"building:{b}"
                        for b in bot["capital_priority"]
                        if f"building:{b}" in options
                    ),
                    None,
                )
            if item is not None:
                pass
            elif (
                unmet
                and counts["boats"] < bot["scout_boats"]
                and counts["military"] >= 2
                and "unit:scout_boat" in options
            ):
                item = "unit:scout_boat"  # other continents are found by sea
            elif (
                searching
                and counts["recon"] < bot["recon"]
                and counts["military"] >= 2  # an army before replacing lost scouts
                and "unit:recon_team" in options
            ):
                item = "unit:recon_team"
            elif counts["military"] * 100 < max(
                len(cities) * bot["military_per_city_pct"], bot["min_military"] * 100
            ):
                item = self._military_choice(city, counts)
            elif counts["engineers"] < bot["engineers"] and "unit:engineers" in options:
                item = "unit:engineers"
            elif counts["recon"] < bot["recon"] and "unit:recon_team" in options:
                item = "unit:recon_team"
            if item is None:
                order = bot["building_priority"]
                if city.is_capital:
                    order = bot["capital_priority"] + order
                for b in order:
                    if b.startswith("beacon_") and not city.is_capital:
                        continue
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
                elif kind == "scout_boat":
                    counts["boats"] += 1
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
            for city in self.view.my_cities():  # every city produces now (SPEC_M10)
                for t in cities.work_tiles(self.state, self.cfg, city):
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
        target = self.nearest(unit.tile, self.known(EMPTY, self.here(unit)))
        if target is None:
            self.submit(SkipUnit(player=self.pid, unit=unit.id))
            return
        if unit.tile != target:
            self.submit(MoveUnit(player=self.pid, unit=unit.id, target=target))
        if self.alive(unit) and unit.tile == target and unit.moves_left > 0:
            self.submit(RefoundCity(player=self.pid, unit=unit.id))

    def _frontier(self) -> list[int]:
        """Explored passable land hexes next to unexplored ones (computed once per turn)."""
        if self._frontier_cache is None:
            out = []
            for t in self.view.explored_tiles():
                tile = self.state.tiles[t]
                if is_passable_land(self.cfg, tile) and any(
                    not self.view.is_explored(n) for n in hexgrid.neighbours(t, self.w, self.h)
                ):
                    out.append(t)
            self._frontier_cache = out
        return self._frontier_cache

    def sea_explorer(self, unit: Unit) -> None:
        """Scout boats head for the nearest open-ocean edge of the known world (then coasts),
        to find the other continents."""
        if self._sea_frontier_cache is None:
            out = []
            for t in self.view.explored_tiles():
                if is_water(self.cfg, self.state.tiles[t]) and any(
                    not self.view.is_explored(n) for n in hexgrid.neighbours(t, self.w, self.h)
                ):
                    out.append(t)
            self._sea_frontier_cache = out
        home = self.pid
        options = sorted(
            (t for t in self._sea_frontier_cache if t != unit.tile),
            key=lambda t: (self.state.tiles[t].continent == home, self.dist(unit.tile, t), t),
        )
        for t in options[: self.param("explore.attempts")]:
            if self.submit(MoveUnit(player=self.pid, unit=unit.id, target=t)):
                return
        self.submit(SkipUnit(player=self.pid, unit=unit.id))

    def explorer(self, unit: Unit) -> None:
        if self.sabotage(unit):
            return
        cont = self.state.tiles[unit.tile].continent
        finds = [
            s.tile
            for s in self.state.sites.values()
            if s.found_by is None
            and self.view.is_explored(s.tile)
            and self.state.tiles[s.tile].continent == cont
            and self.dist(unit.tile, s.tile) <= self.param("explore.find_radius")
        ]
        if finds:
            near = min(finds, key=lambda t: (self.dist(unit.tile, t), t))
            if self.submit(MoveUnit(player=self.pid, unit=unit.id, target=near)):
                return
        options = sorted(
            (
                t
                for t in self._frontier()
                if t != unit.tile and self.state.tiles[t].continent == cont
            ),
            key=lambda t: (self.dist(unit.tile, t), t),
        )
        for t in options[: self.param("explore.attempts")]:
            if self.submit(MoveUnit(player=self.pid, unit=unit.id, target=t)):
                return
        self.submit(Fortify(player=self.pid, unit=unit.id))

    # -- the M12 tools: strikes, nests, resistance, sabotage ------------------------------

    def _beside_alien(self, unit: Unit):
        for n in hexgrid.neighbours(unit.tile, self.w, self.h):
            city = self.state.city_at(n)
            if (
                city is not None
                and city.status == OVERRUN
                and str(city.id) in self.view.player.known_cities
            ):
                return city
        return None

    def sabotage(self, unit: Unit) -> bool:
        """A scout beside an alien city sabotages it while it is healthy enough."""
        from beacon import threat
        from beacon.commands import Sabotage

        city = self._beside_alien(unit)
        t = self.param("tools")
        if city is None or unit.hp * 100 < max_hp(self.cfg, unit) * t["sabotage_min_hp_pct"]:
            return False
        if threat.sabotage_problem(self.state, self.cfg, unit, city) is not None:
            return False
        return self.submit(Sabotage(player=self.pid, unit=unit.id, city=city.id))

    def tools(self, unit: Unit) -> bool:
        """Defend a city a UAV saw a strike coming to; arm a resistance; clear a nest."""
        from beacon import threat
        from beacon.commands import ArmResistance

        t = self.param("tools")
        danger = [
            p.target
            for p in threat.detected(self.state, self.cfg, self.pid)
            if self.dist(unit.tile, p.target) <= t["strike_radius"]
        ]
        if danger:
            city = min(danger, key=lambda x: (self.dist(unit.tile, x), x))
            if self.dist(unit.tile, city) > 1:
                if self._approach(unit, city):
                    return True
            elif self.alive(unit) and unit.moves_left > 0:
                return self.submit(Fortify(player=self.pid, unit=unit.id))
        city = self._beside_alien(unit)
        rs = self.cfg.alien("resistance")
        if (
            city is not None
            and not self._armed
            and self.view.player.gold >= rs["gold"] + t["resistance_reserve"]
            and threat.arm_problem(self.state, self.cfg, unit, city) is None
            and self.submit(ArmResistance(player=self.pid, unit=unit.id, city=city.id))
        ):
            self._armed = True
            return True
        nests = [
            i
            for i in hexgrid.within(unit.tile, t["nest_radius"], self.w, self.h)
            if self.state.tiles[i].nest is not None
            and self.view.is_explored(i)
            and not self.state.units_at(i)
        ]
        nest = self.nearest(unit.tile, nests)
        return nest is not None and self.submit(
            MoveUnit(player=self.pid, unit=unit.id, target=nest)
        )

    # -- military --------------------------------------------------------------------------

    def _best_attack(self, unit: Unit) -> int | None:
        ratio = self.param("combat.attack_ratio_pct")
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
                weak = city.hp * 100 <= cities.max_hp(self.cfg, city, self.state) * self.param(
                    "combat.siege_city_hp_pct"
                )
                good_trade = dealt * 100 >= ratio * max(1, taken)
                if not (
                    taken == 0 or dealt >= city.hp or good_trade or (weak and taken * 2 < unit.hp)
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
        threshold = self.param("combat.merge_min_hp_pct")
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
            and not self.cfg.units[u.type].get("fixed")
        ]
        out: dict[int, int] = {}
        taken: set[int] = set()
        radius = self.param("combat.garrison_radius")
        # alien units nearby call for a garrison; alien cities do not move, so they do not
        danger = [
            u.tile
            for u in self.view.visible_units()
            if u.owner == ALIENS and self.state.city_at(u.tile) is None  # garrisons stay home
        ]
        cities = sorted(
            (
                c
                for c in self.view.my_cities()
                # cities have their own guns: hold one only with aliens near (the capital included)
                if any(self.dist(c.tile, d) <= radius for d in danger)
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
        radius = self.param("combat.threat_radius")
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
        if unit.hp * 100 < max_hp(self.cfg, unit) * self.param("combat.retreat_hp_pct"):
            home = self.nearest(unit.tile, own)
            if home is not None and home != unit.tile:
                self.submit(MoveUnit(player=self.pid, unit=unit.id, target=home))
            if self.alive(unit) and unit.moves_left > 0:
                self.submit(Fortify(player=self.pid, unit=unit.id))
            return
        if self.tools(unit):  # strikes, nests, the resistance (designer 2026-11-16)
            return
        threat = self.nearest(unit.tile, self.threats())
        if threat is not None and self._approach(unit, threat):
            return
        dormant = self.nearest(unit.tile, self.known(DORMANT, self.here(unit)))
        if dormant is not None and self.submit(
            MoveUnit(player=self.pid, unit=unit.id, target=dormant)
        ):
            return
        overrun = self.nearest(unit.tile, self.known(OVERRUN, self.here(unit)))
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

    def council(self) -> None:
        """Seat recruits greedily; gift those with no free seat; answer offers."""
        for o in sorted(self.state.offers.values(), key=lambda x: x.id):
            if o.to_player != self.pid:
                continue
            rec = self.state.recruits.get(str(o.recruit))
            fits = rec is not None and self._seats_for(rec) is not None
            if fits and self.view.player.gold >= o.price:
                self.submit(AcceptOffer(player=self.pid, offer=o.id))
            else:
                self.submit(DeclineOffer(player=self.pid, offer=o.id))
        for rec in recruits.recruits_of(self.state, self.pid):
            if rec.seats:
                continue
            seats = self._seats_for(rec)
            if seats is not None:
                self.submit(SeatRecruit(player=self.pid, recruit=rec.id, seats=seats))
                continue
            met = self.state.players[self.pid].met  # gifts need contact (M10)
            others = [p for p in self.state.player_ids() if p != self.pid and p in met]
            if not others:
                continue
            counts = {p: len(recruits.recruits_of(self.state, p)) for p in others}
            to = min(others, key=lambda p: (counts[p], p))
            self.submit(OfferRecruit(player=self.pid, recruit=rec.id, to_player=to, price=0))

    def _seats_for(self, rec) -> tuple[str, ...] | None:
        spread = self.param("recruits.general_min_domains")
        if (
            len(rec.scores) >= spread
            and recruits.seat_problem(self.state, self.cfg, rec, ["general"]) is None
        ):
            return ("general",)
        free = tuple(
            d
            for d in sorted(rec.scores)
            if recruits.seat_problem(self.state, self.cfg, rec, [d]) is None
        )
        if free:
            return free
        if recruits.seat_problem(self.state, self.cfg, rec, ["general"]) is None:
            return ("general",)
        return None

    def convoy(self, unit: Unit) -> None:
        """Trade convoys head for the nearest own port city."""
        from beacon.diplomacy import ports

        targets = [c.tile for c in ports(self.state, self.cfg, self.pid)]
        target = self.nearest(unit.tile, targets)
        if target is not None and target != unit.tile:
            self.submit(MoveUnit(player=self.pid, unit=unit.id, target=target))

    def promote(self) -> None:
        """Ranged units and units sent to attack take attack; the rest alternate, defence first
        for city guns."""
        for unit in self.view.my_units():
            while promotions.due(self.cfg, unit) > 0:
                # the class's preferred promotions, least-taken first (then attack/defence)
                cls = self.cfg.units[unit.type].get("class") or ""
                prefs = self.param("promotions.prefer").get(cls, []) + ["attack_10", "defence_10"]
                allowed = promotions.options(self.cfg, unit)
                prefs = [p for p in prefs if p in allowed]
                pick = min(prefs, key=lambda p: (unit.promotions.count(p), prefs.index(p)))
                if not self.submit(PromoteUnit(player=self.pid, unit=unit.id, promotion=pick)):
                    break
        # City guns are upgraded with gold, the most threatened city first, keeping a reserve.
        threats = self.threats()
        guns = sorted(
            (u for u in self.view.my_units() if self.cfg.units[u.type].get("fixed")),
            key=lambda u: (min((self.dist(u.tile, t) for t in threats), default=999), u.id),
        )
        for gun in guns[:1]:
            cost = promotions.upgrade_cost(self.cfg, gun)
            reserve = self.param("defences.gold_reserve_pct")
            if cost is not None and self.view.player.gold * 100 >= cost * reserve:
                self.submit(UpgradeDefence(player=self.pid, unit=gun.id))

    def answer_stories(self) -> None:
        """Events waiting for a choice: take the data's ai_choice (docs/SPEC_M9.md)."""
        from beacon import story

        for ev in story.pending(self.state, self.pid):
            pick = self.cfg.events[ev.event].get("ai_choice", 0)
            self.submit(ChooseStory(player=self.pid, story=ev.id, choice=pick))

    def starfall_duty(self) -> None:
        """A landed shard on a continent where we have units: send the nearest engineer or scout
        to mine it and the nearest soldier to guard it (docs/SPEC_M9.md, Starfall)."""
        from beacon.starfall import active, can_mine, landed

        for shard in active(self.state):
            if not landed(self.state, shard):
                continue
            cont = self.state.tiles[shard.tile].continent
            mine = [
                u
                for u in self.view.my_units()
                if self.state.tiles[u.tile].continent == cont and u.id not in self.reserved
            ]
            miners = [u for u in mine if can_mine(self.cfg, self.pid, u.type) and u.job is None]
            reach = self.param("starfall.reach")
            miners = [u for u in miners if self.dist(u.tile, shard.tile) <= reach]
            if not miners:
                continue
            miner = min(miners, key=lambda u: (self.dist(u.tile, shard.tile), u.id))
            self.reserved.add(miner.id)
            if miner.tile != shard.tile and miner.moves_left > 0:
                self.submit(MoveUnit(player=self.pid, unit=miner.id, target=shard.tile))
            guards = [
                u
                for u in mine
                if self.cfg.units[u.type]["role"] in ("melee", "ranged")
                and not self.cfg.units[u.type].get("fixed")
                and u.id not in self.reserved
                and self.dist(u.tile, shard.tile) <= reach
            ]
            for g in sorted(guards, key=lambda u: (self.dist(u.tile, shard.tile), u.id))[
                : self.param("starfall.guards")
            ]:
                self.reserved.add(g.id)
                if self.dist(g.tile, shard.tile) > 1 and g.moves_left > 0:
                    self._approach(g, shard.tile)
                if self.alive(g) and g.moves_left > 0:
                    target = self._best_attack(g)
                    if target is not None:
                        self.submit(Attack(player=self.pid, unit=g.id, target=target))

    def play(self) -> None:
        self.answer_stories()
        self.starfall_duty()
        self.promote()
        self.research()
        self.production()
        self.council()
        self.bombard()
        net = self._network()
        claimed: set[int] = set()
        garrisons = {uid: tile for tile, uid in self._garrisons().items()}
        self.play_units(net, claimed, garrisons)

    def band(self, unit: Unit) -> None:
        """A survivor band: take the caches it has seen nearby, then storm its first town once it
        has gear, six people, or the attack turn has come."""
        from beacon import survivors

        town = survivors.town_of(self.state, self.pid)
        if town is None:
            self.submit(SkipUnit(player=self.pid, unit=unit.id))
            return
        sv = self.cfg.t("survivor")
        mine = [u for u in self.view.my_units() if survivors.is_band(self.cfg, u)]
        found = self.state.players[self.pid].band_finds > 0  # the barricades are open
        ready = found and (
            any(u.gear for u in mine) or len(mine) >= 6 or self.state.turn >= sv["ai_attack_turn"]
        )
        seen = [int(k) for k in self.state.caches if self.view.is_explored(int(k))]
        cache = self.nearest(unit.tile, seen)
        near = cache is not None and (not ready or self.dist(unit.tile, cache) <= 1)
        if near and self.submit(MoveUnit(player=self.pid, unit=unit.id, target=cache)):
            return
        if not ready:
            if not found:  # nothing seen yet: scout for caches nearby
                home = self.state.players[self.pid].band_home or unit.tile
                frontier = [t for t in self._frontier() if self.dist(t, home) <= sv["radius"] + 2]
                target = self.nearest(unit.tile, frontier)
                if target is not None and self.submit(
                    MoveUnit(player=self.pid, unit=unit.id, target=target)
                ):
                    return
            self.submit(SkipUnit(player=self.pid, unit=unit.id))
            return
        if self.dist(unit.tile, town.tile) > 1:
            spots = [
                n
                for n in hexgrid.neighbours(town.tile, self.w, self.h)
                if not self.state.units_at(n) and is_passable_land(self.cfg, self.state.tiles[n])
            ]
            target = self.nearest(unit.tile, spots)
            if target is None or not self.submit(
                MoveUnit(player=self.pid, unit=unit.id, target=target)
            ):
                self.submit(SkipUnit(player=self.pid, unit=unit.id))
                return
        if (
            self.alive(unit)
            and self.dist(unit.tile, town.tile) == 1
            and unit.attacks_left > 0
            and combat.attack_problem(self.state, self.cfg, unit, town.tile) is None
        ):
            # attack while fit, or when the blow takes the town; otherwise rest and heal
            p = combat.preview_attack(self.state, self.cfg, unit, town.tile)
            takes = p["damage_to_defender"]["expected"] >= town.hp
            fit = unit.hp - p["damage_to_attacker"]["max"] >= sv["ai_min_hp"]
            if takes or fit:
                self.submit(Attack(player=self.pid, unit=unit.id, target=town.tile))
            else:
                self.submit(Fortify(player=self.pid, unit=unit.id))

    def play_units(self, net: set[int], claimed: set[int], garrisons: dict[int, int]) -> None:
        for unit in self.view.my_units():
            if self.cfg.units[unit.type].get("fixed"):
                continue  # city defences fire on their own at the end of the turn
            if not self.alive(unit) or unit.moves_left <= 0 or unit.job is not None:
                continue
            if unit.id in self.reserved:
                continue
            spec = self.cfg.units[unit.type]
            if spec.get("survivor") and not self.state.players[self.pid].founded:
                self.band(unit)  # the survivor start (SPEC_M14)
            elif spec.get("not_buildable") and spec["role"] == "civilian":
                self.convoy(unit)
            elif spec.get("can_build"):
                self.engineer(unit, net, claimed)
            elif spec.get("can_refound"):
                self.restorer(unit)
            elif spec["role"] == "civilian":
                self.submit(SkipUnit(player=self.pid, unit=unit.id))  # medics, repair crews
            elif spec["role"] == "recon" and spec["domain"] == "sea":
                self.sea_explorer(unit)
            elif spec["role"] == "recon":
                self.explorer(unit)
            elif unit.id in garrisons:
                self.guard(unit, garrisons[unit.id])
            else:
                self.view = PlayerView(self.state, self.cfg, self.pid)
                self.soldier(unit)


def take_turn(state: GameState, cfg: Config, pid: str, submit: Submit) -> None:
    Bot(state, cfg, pid, submit).play()
