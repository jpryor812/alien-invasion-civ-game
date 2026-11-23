"""AI continents (DESIGN.md 15, docs/SPEC_M6.md).

An AI player is the test bot's play with its character's settings (data/ai.yaml overrides of
data/bots.yaml), plus diplomacy: it answers deals by valuing what it gives and gets, proposes
alliances and trades (tech swaps, resource lending), gives gold aid to the weakest continent,
and ships troops abroad once its own continent is quiet. Like the bot, it reads the game through
the fog-safe view, acts only through commands and uses no randomness.
"""

from __future__ import annotations

from typing import Any

from beacon import diplomacy, economy, endgame, hexgrid, improvements, leader, tech, works
from beacon.bots import Bot, Submit
from beacon.commands import (
    AcceptDeal,
    BuildImprovement,
    ChooseEspionageTech,
    ChooseLeaderBonus,
    DeclineDeal,
    FundProject,
    MoveUnit,
    ProposeDeal,
    RaiseSkill,
    SetProduction,
    ShipUnit,
    StartBarrage,
    StartEspionage,
    StartFamily,
)
from beacon.config import Config
from beacon.paths import shortest_path
from beacon.state import ACTIVE, DORMANT, EMPTY, OVERRUN, DealTerms, GameState, Unit
from beacon.tiles import is_passable_land


class AIPlayer(Bot):
    def __init__(self, state: GameState, cfg: Config, pid: str, submit: Submit):
        super().__init__(state, cfg, pid, submit)
        self.char = cfg.ai(f"characters.{state.players[pid].character}")
        self._bridge: tuple[int, int] | None | bool = False  # not looked for yet this turn

    def param(self, path: str) -> Any:
        if path == "research.priority":
            return [
                *self.char["overrides"].get(path, self.cfg.bot(path)),
                *self.cfg.ai("endgame.research"),
            ]
        return self.char["overrides"].get(path, self.cfg.bot(path))

    # -- valuing deals -----------------------------------------------------------------------

    def value(self, t: DealTerms, duration: int) -> int:
        v = self.cfg.ai("value")
        total = t.gold + t.gold_per_turn * duration
        total += sum(t.resources.values()) * v["resource_per_turn"] * duration
        total += sum(self.cfg.techs[x]["cost"] for x in t.techs) * v["tech_pct"] // 100
        for rid in t.recruits:
            rec = self.state.recruits.get(str(rid))
            if rec is not None:
                total += sum(rec.scores.values()) * v["recruit_per_point"]
        for uid in t.units:
            unit = self.state.units.get(str(uid))
            if unit is not None:
                total += self.cfg.units[unit.type]["cost"] * v["unit_pct"] // 100
        if t.alliance:
            total += v["alliance"]
        if t.materials or t.materials_per_turn:  # at the Exchange's buying price (SPEC_M21)
            from beacon.exchange import quotes

            q = quotes(self.state, self.cfg, self.pid)
            total += sum(q[g]["sell"] * n for g, n in t.materials.items() if g in q)
            total += sum(
                q[g]["sell"] * n * duration for g, n in t.materials_per_turn.items() if g in q
            )
        return total

    def respond(self) -> None:
        for deal in sorted(self.state.deals.values(), key=lambda d: d.id):
            if deal.receiver != self.pid or deal.active:
                continue
            gets = self.value(deal.give, deal.duration)
            gives = self.value(deal.take, deal.duration)
            ok = gets * 100 >= gives * self.char["accept_ratio_pct"]
            if deal.give.alliance and not self.char["allies"] and not ok:
                ok = True  # every AI accepts an alliance offered to it
            if not (ok and self.submit(AcceptDeal(player=self.pid, deal=deal.id))):
                self.submit(DeclineDeal(player=self.pid, deal=deal.id))

    # -- proposing ---------------------------------------------------------------------------

    def others(self) -> list[str]:
        """Players this AI has met (diplomacy needs contact, designer 2026-11-14)."""
        met = self.state.players[self.pid].met
        return [p for p in self.state.player_ids() if p != self.pid and p in met]

    def propose(self, to: str, give: dict, take: dict, duration: int = 0) -> bool:
        duration = duration or self.cfg.t("trade.deals.durations")[0]
        return self.submit(
            ProposeDeal(player=self.pid, to_player=to, give=give, take=take, duration=duration)
        )

    def alliances(self) -> None:
        if not self.char["allies"]:
            return
        needed = self.cfg.t("trade.alliance_tech")
        me = self.view.player
        if needed not in me.techs:
            return
        for other in self.others():
            if other in me.allies or needed not in self.state.players[other].techs:
                continue
            if self.propose(other, {"alliance": True}, {"alliance": True}):
                return  # one proposal per turn

    def trades(self) -> None:
        interval = self.char["trade_interval"]
        if not interval or self.state.turn % interval:
            return
        others = self.others()
        if not others:
            return  # nobody met yet
        partner = others[(self.state.turn // interval) % len(others)]
        me, them = self.view.player, self.state.players[partner]
        mine = [t for t in me.techs if t in tech.available(self.cfg, them)]
        theirs = [t for t in them.techs if t in tech.available(self.cfg, me)]
        if mine and theirs:
            cost = self.cfg.techs
            want = min(theirs, key=lambda t: (cost[t]["cost"], t))
            offer = [t for t in mine if cost[t]["cost"] >= cost[want]["cost"]]
            if offer:
                give = min(offer, key=lambda t: (cost[t]["cost"], t))
                self.propose(partner, {"techs": [give]}, {"techs": [want]})
        supply = economy.resource_supply(self.state, self.cfg, self.pid)
        usage = economy.resource_usage(self.state, self.cfg, self.pid)
        their_supply = economy.resource_supply(self.state, self.cfg, partner)
        for res in sorted(supply):
            if supply[res] - usage.get(res, 0) >= 1 and their_supply.get(res, 0) == 0:
                durations = self.cfg.t("trade.deals.durations")
                self.propose(
                    partner,
                    {"resources": {res: 1}},
                    {"gold_per_turn": self.char["lend_price"]},
                    durations[1],
                )
                break

    def aid(self) -> None:
        interval = self.char["aid_interval"]
        me = self.view.player
        if not interval or self.state.turn % interval or me.gold <= self.char["aid_reserve"]:
            return
        mine = sum(1 for c in self.state.cities if c.owner == self.pid and c.status == ACTIVE)

        def need(pid: str) -> tuple[int, int, str]:
            p = self.state.players[pid]
            held = sum(1 for c in self.state.cities if c.owner == pid and c.status == ACTIVE)
            return (0 if p.fallen else 1, held, pid)

        if not self.others():
            return  # nobody met yet
        target = min(self.others(), key=need)
        standing, held, _ = need(target)
        if standing == 1 and held * 100 > mine * self.cfg.ai("aid.need_pct"):
            return  # nobody has fallen or is clearly weaker than us
        gift = (me.gold - self.char["aid_reserve"]) * self.char["aid_share_pct"] // 100
        if gift > 0:
            self.propose(target, {"gold": gift}, {})

    # -- ports and expeditions -----------------------------------------------------------------

    def ensure_port(self) -> None:
        if diplomacy.ports(self.state, self.cfg, self.pid):
            return
        if any(works.ordered(c, "building:port") for c in self.view.my_cities()):
            return
        for city in sorted(self.view.my_cities(), key=lambda c: (-c.pop, c.id)):
            if (
                city.connected
                and "port" in economy.building_options(self.state, self.cfg, city)
                and works.building_problem(self.state, self.cfg, city, "port") is None
            ):
                self.submit(
                    SetProduction(
                        player=self.pid, city=city.id, items=("building:port", *city.queue)
                    )
                )
                return

    def expedition_target(self) -> int | None:
        """A known coastal city on the continent that most needs help."""
        from beacon.cities import is_coastal

        known = {int(k) for k in self.view.player.known_cities}
        best = None
        for pid in self.others():
            p = self.state.players[pid]
            alien = sum(
                1
                for cid in known
                if self.state.cities[cid].continent == pid
                and self.state.cities[cid].status == OVERRUN
            )
            score = (1 if p.fallen else 0, alien, pid)
            if alien == 0 and not p.fallen:
                continue
            if best is None or score > best[0]:
                best = (score, pid)
        if best is None:
            return None
        cont = best[1]
        options = sorted(
            cid
            for cid in known
            if self.state.cities[cid].continent == cont
            and is_coastal(self.state, self.cfg, self.state.cities[cid])
            and (
                (
                    self.state.cities[cid].status == ACTIVE
                    and self.state.cities[cid].owner in self.state.players
                )
                or self.state.cities[cid].status in (DORMANT, EMPTY)
            )
        )
        return options[0] if options else None

    def expeditions(self, garrisons: set[int]) -> None:
        share = self.char["abroad_share_pct"]
        if not share:
            return
        quiet = len(self.known(OVERRUN, self.pid)) <= self.cfg.ai("expedition.quiet_overrun")
        port_cities = diplomacy.ports(self.state, self.cfg, self.pid)
        if not quiet or not port_cities:
            return
        dest = self.expedition_target()
        if dest is None:
            return
        field = [
            u
            for u in self.view.my_units()
            if self.here(u) == self.pid
            and self.cfg.units[u.type]["role"] in ("melee", "ranged")
            and self.cfg.units[u.type]["domain"] == "land"
            and not self.cfg.units[u.type].get("fixed")
            and u.id not in garrisons
        ]
        abroad = sum(1 for u in self.view.my_units() if self.here(u) != self.pid)
        total = len(field) + abroad
        wanted = total * share // 100 - abroad
        known = {int(k) for k in self.view.player.known_cities}
        port_tiles = [c.tile for c in port_cities]
        for unit in sorted(
            field, key=lambda u: (min(self.dist(u.tile, t) for t in port_tiles), u.id)
        )[: max(0, wanted)]:
            self.reserved.add(unit.id)
            if unit.tile in port_tiles:
                if diplomacy.ship_problem(self.state, self.cfg, unit, dest, known) is None:
                    self.submit(ShipUnit(player=self.pid, unit=unit.id, city=dest))
            else:
                self.submit(
                    MoveUnit(
                        player=self.pid, unit=unit.id, target=self.nearest(unit.tile, port_tiles)
                    )
                )

    # -- endgame -------------------------------------------------------------------------------

    def endgame(self) -> None:
        me = self.view.player
        mine = [c for c in self.view.my_cities() if c.status == ACTIVE]
        b = endgame.barrage(self.state)
        if b is None and self.cfg.t("endgame.barrage_tech") in me.techs:
            hosts = [c for c in mine if c.connected]
            if hosts:
                host = next((c for c in hosts if c.is_capital), max(hosts, key=lambda c: c.pop))
                self.submit(StartBarrage(player=self.pid, city=host.id))
                b = endgame.barrage(self.state)
        running = endgame.barrage_needs(self.state)
        if running is not None and endgame.host_held(self.state, running):
            want = max(1, len(mine) * self.char["barrage_share_pct"] // 100)
            prod = sorted(
                (c for c in mine if c.connected),
                key=lambda c: (
                    -economy.city_yields(self.state, self.cfg, c).totals["production"],
                    c.id,
                ),
            )
            for city in prod[:want]:
                if not city.queue or city.queue[0] != "project:barrage":
                    self.submit(
                        SetProduction(player=self.pid, city=city.id, items=("project:barrage",))
                    )
            spare = me.gold - self.char["aid_reserve"]
            gift = spare * self.cfg.ai("endgame.barrage_gold_pct") // 100
            if gift > 0:
                self.submit(FundProject(player=self.pid, project=running.id, gold=gift))
        elif running is None:
            for city in mine:
                if city.queue and city.queue[0] == "project:barrage":
                    self.submit(SetProduction(player=self.pid, city=city.id, items=()))
        self.espionage()

    def espionage(self) -> None:
        me = self.view.player
        for p in sorted(self.state.projects.values(), key=lambda x: x.id):
            if p.kind == "espionage" and p.offered and p.chooser == self.pid:
                best = max(p.offered, key=lambda t: (t in self.char.get("espionage_prefs", []), t))
                self.submit(ChooseEspionageTech(player=self.pid, project=p.id, tech=best))
        reserve = self.char["espionage_reserve"]
        if endgame.open_operation(self.state, self.pid) is None and me.gold > reserve:
            pool = [t for t in endgame.alien_techs(self.cfg) if t not in me.techs]
            if pool:
                self.submit(StartEspionage(player=self.pid, mode=self.char["espionage_mode"]))
        for p in sorted(self.state.projects.values(), key=lambda x: x.id):
            if p.kind != "espionage" or p.done or me.gold <= reserve:
                continue
            if p.starter == self.pid or p.mode == "shared":
                gold = min(me.gold - reserve, p.cost - p.progress)
                if gold > 0:
                    self.submit(FundProject(player=self.pid, project=p.id, gold=gold))

    # -- the council of continents (SPEC_M13) ------------------------------------------------

    def parliament(self) -> None:
        """Vote by agenda (likes yes, dislikes no, else yes; a relief fund it cannot pay, no;
        chair: itself when it has the most influence, else the most influential player), and
        propose the first liked measure when influence allows."""
        from beacon import council
        from beacon.commands import CastVote, ProposeMeasure

        me = self.state.players[self.pid]
        agenda = self.cfg.council(f"agendas.{me.agenda}") if me.agenda else {}
        likes, dislikes = agenda.get("likes", []), agenda.get("dislikes", [])
        for m in council.unvoted(self.state, self.pid, self.cfg):
            spec = self.cfg.council(f"measures.{m.kind}")
            if spec["kind"] == "chair":
                choice = max(
                    council.members(self.state, self.cfg),
                    key=lambda p: (
                        council.influence(self.cfg, self.state.players[p]),
                        p == self.pid,
                        p,
                    ),
                )
            elif m.kind in dislikes or spec["kind"] == "relief" and me.gold < spec["gold"]:
                choice = "no"
            else:
                choice = "yes"
            self.submit(CastVote(player=self.pid, measure=m.id, choice=choice, extra=0))
        reserve = self.cfg.council("ai.propose_reserve")
        cost = self.cfg.council("sessions.propose_cost")
        if council.influence(self.cfg, me) >= cost + reserve:
            for kind in likes:
                if council.propose_problem(self.state, self.cfg, self.pid, kind) is None:
                    self.submit(ProposeMeasure(player=self.pid, measure=kind))
                    break

    # -- the leader (SPEC_M11) ----------------------------------------------------------------

    def lead(self) -> None:
        """Spend skill points on the lowest skill, take the first bonus offered, and start a
        family whenever allowed: with the best seated recruit, else the best grown citizen."""
        from beacon.config import DOMAINS
        from beacon.recruits import recruits_of

        me = self.state.players[self.pid].leader
        if me is None:
            return
        while leader.points(self.cfg, me) > 0:
            low = min(DOMAINS, key=lambda d: (me.skills[d], DOMAINS.index(d)))
            if not self.submit(RaiseSkill(player=self.pid, skill=low)):
                break
        for choice in list(me.choices):
            opts = leader.options(self.cfg, me, choice)
            if opts:
                self.submit(ChooseLeaderBonus(player=self.pid, choice=choice, option=opts[0]))
        if not self.cfg.leader("ai.family"):
            return
        seated = [r for r in recruits_of(self.state, self.pid) if r.seats]
        people = [
            c
            for c in self.state.citizens.values()
            if self.state.cities[c.city].owner == self.pid and c.adult and not c.kin
        ]
        partners = [
            f"recruit:{r.id}" for r in sorted(seated, key=lambda r: (-sum(r.scores.values()), r.id))
        ] + [
            f"citizen:{c.id}"
            for c in sorted(people, key=lambda c: (-sum(c.stats.values()), c.id))[:1]
        ]
        for partner in partners:
            if leader.family_problem(self.state, self.cfg, self.pid, partner) is None:
                self.submit(StartFamily(player=self.pid, partner=partner))
                break

    # -- sea bridges (SPEC_M11) ---------------------------------------------------------------

    def bridge_site(self, net: set[int]) -> tuple[int, int] | None:
        """(shore hex, water hex) of the next sea bridge toward the nearest allied shore the
        player has explored, or None. Plans from memory only (explored hexes)."""
        spec = self.cfg.improvements["sea_bridge"]
        me = self.state.players[self.pid]
        if not net or not me.allies or not tech.knows(me, spec["tech"]):
            return None
        capital = next((c for c in self.view.my_cities() if c.is_capital), None)
        if capital is None:
            return None
        shores = {
            i
            for i in self.view.explored_tiles()
            if self.state.tiles[i].continent in me.allies
            and is_passable_land(self.cfg, self.state.tiles[i])
        }
        if not shores:
            return None
        cost = self.cfg.ai("bridges.water_cost")

        def wet(t) -> bool:
            return t.terrain in spec["terrains"] and t.route is None

        def step(_: int, b: int) -> int | None:
            tile = self.remembered(b)
            if tile is None:
                return None
            if wet(tile):
                return cost
            if not is_passable_land(self.cfg, tile):
                return None
            return 0 if tile.route else 1

        path = shortest_path(
            capital.tile, shores, lambda i: hexgrid.neighbours(i, self.w, self.h), step
        )
        if path is None:
            return None
        water = [k for k, i in enumerate(path) if wet(self.state.tiles[i])]
        if not water or len(water) > self.cfg.ai("bridges.max_water"):
            return None
        return path[water[0] - 1], path[water[0]]

    def engineer(self, unit: Unit, net: set[int], claimed: set[int]) -> None:
        if self._bridge is False:
            self._bridge = self.bridge_site(net)
        site = self._bridge
        if site is None or site[1] in claimed:
            return super().engineer(unit, net, claimed)
        shore, water = site
        claimed.add(water)
        if unit.tile != shore and not self.submit(
            MoveUnit(player=self.pid, unit=unit.id, target=shore)
        ):
            return super().engineer(unit, net, claimed)
        if (
            self.alive(unit)
            and unit.tile == shore
            and improvements.build_problem(self.state, self.cfg, unit, "sea_bridge", water) is None
        ):
            self.submit(
                BuildImprovement(
                    player=self.pid, unit=unit.id, improvement="sea_bridge", target=water
                )
            )

    # -- turn --------------------------------------------------------------------------------

    def play(self) -> None:
        self.respond()
        self.answer_stories()
        self.starfall_duty()
        self.promote()
        self.lead()
        self.parliament()
        self.research()
        self.ensure_port()
        self.production()
        self.buildings()  # SPEC_M17
        self.enlist()  # citizens as soldiers (2026-11-17)
        self.land()
        self.births()  # SPEC_M19
        self.meet_leaders()  # SPEC_M21
        self.market()
        self.walls()  # SPEC_M16
        self.council()
        self.bombard()
        self.alliances()
        self.trades()
        self.aid()
        self.endgame()
        net = self._network()
        garrisons = {uid: tile for tile, uid in self._garrisons().items()}
        self.expeditions(set(garrisons))
        self.play_units(net, set(), garrisons)


def take_turn(state: GameState, cfg: Config, pid: str, submit: Submit) -> None:
    AIPlayer(state, cfg, pid, submit).play()
