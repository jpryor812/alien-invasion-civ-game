"""AI continents (DESIGN.md 15, docs/SPEC_M6.md).

An AI player is the test bot's play with its character's settings (data/ai.yaml overrides of
data/bots.yaml), plus diplomacy: it answers deals by valuing what it gives and gets, proposes
alliances and trades (tech swaps, resource lending), gives gold aid to the weakest continent,
and ships troops abroad once its own continent is quiet. Like the bot, it reads the game through
the fog-safe view, acts only through commands and uses no randomness.
"""

from __future__ import annotations

from typing import Any

from beacon import diplomacy, economy, endgame, tech
from beacon.bots import Bot, Submit
from beacon.commands import (
    AcceptDeal,
    ChooseEspionageTech,
    DeclineDeal,
    FundProject,
    MoveUnit,
    ProposeDeal,
    SetProduction,
    ShipUnit,
    StartBarrage,
    StartEspionage,
)
from beacon.config import Config
from beacon.state import ACTIVE, DORMANT, EMPTY, OVERRUN, DealTerms, GameState


class AIPlayer(Bot):
    def __init__(self, state: GameState, cfg: Config, pid: str, submit: Submit):
        super().__init__(state, cfg, pid, submit)
        self.char = cfg.ai(f"characters.{state.players[pid].character}")

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
        return [p for p in self.state.player_ids() if p != self.pid]

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
        if any("building:port" in c.queue for c in self.view.my_cities()):
            return
        for city in sorted(self.view.my_cities(), key=lambda c: (-c.pop, c.id)):
            if city.connected and "building:port" in economy.production_options(
                self.state, self.cfg, city
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

    # -- turn --------------------------------------------------------------------------------

    def play(self) -> None:
        self.respond()
        self.promote()
        self.research()
        self.ensure_port()
        self.production()
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
