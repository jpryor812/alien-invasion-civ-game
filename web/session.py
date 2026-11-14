"""One game for one human player: the bridge between the client and the simulation.

Everything returned here is what the human player may know: the fog-safe `observe()` view plus
details of their own units and cities, and combat previews only for targets they can see. Every
action goes through `apply_command`, exactly as for the AI.
"""

from __future__ import annotations

import contextlib
import json
import re
import time
from pathlib import Path
from typing import Any

from beacon import (
    ai,
    combat,
    diplomacy,
    economy,
    endgame,
    fog,
    hexgrid,
    improvements,
    movement,
    mvp,
    recruits,
    tech,
)
from beacon.actions import apply_command, pending_decisions
from beacon.commands import CommandError, command_from_dict
from beacon.config import DOMAINS, Config
from beacon.game import new_game
from beacon.state import ACTIVE, ALIENS, GameState, state_from_json, state_to_json, to_dict
from beacon.turn import advance_turn, year
from beacon.view import observe

SAVE_DIR = Path(__file__).resolve().parent.parent / "runs" / "saves"
PUBLIC_EVENTS = frozenset(
    {
        "turn_started",
        "game_over",
        "barrage_started",
        "barrage_fired",
        "reinforcements_stopped",
        "continent_fallen",
        "continent_revived",
        "alien_tech",
        "espionage_complete",
        "alien_tech_gained",
    }
)


class Session:
    def __init__(self, cfg: Config, seed: int = 1, human: str = "europe"):
        self.cfg = cfg
        self.new(seed, human)

    # -- lifecycle ---------------------------------------------------------------------------

    def new(self, seed: int, human: str) -> None:
        state = new_game(self.cfg, seed)
        if human not in state.players:
            raise ValueError(f"unknown player {human!r}")
        state.players[human].controller = "human"
        self.state, self.human = state, human
        self.events: list[dict[str, Any]] = []

    def save(self, name: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", name):
            raise ValueError("save names use letters, digits, - and _ (up to 40)")
        SAVE_DIR.mkdir(parents=True, exist_ok=True)
        (SAVE_DIR / f"{name}.json").write_text(state_to_json(self.state), encoding="utf-8")
        meta = {"name": name, **self.status(), "saved_at": int(time.time())}
        (SAVE_DIR / f"{name}.meta.json").write_text(json.dumps(meta), encoding="utf-8")
        return name

    def load(self, name: str) -> None:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", name):
            raise ValueError("bad save name")
        path = SAVE_DIR / f"{name}.json"
        if not path.exists():
            raise ValueError(f"no save {name!r}")
        state = state_from_json(path.read_text(encoding="utf-8"))
        if state.config_digest != self.cfg.digest:
            raise ValueError("this save was made with different game data")
        self.state = state
        self.human = next(p for p, pl in state.players.items() if pl.controller == "human")
        self.events = []

    @staticmethod
    def saves() -> list[dict[str, Any]]:
        """Saved games, newest first, with what the menus show about them."""
        if not SAVE_DIR.exists():
            return []
        out = []
        for path in SAVE_DIR.glob("*.json"):
            if path.name.endswith(".meta.json"):
                continue
            meta_path = path.with_name(f"{path.stem}.meta.json")
            meta: dict[str, Any] = {"name": path.stem, "saved_at": int(path.stat().st_mtime)}
            if meta_path.exists():
                meta.update(json.loads(meta_path.read_text(encoding="utf-8")))
            out.append(meta)
        return sorted(out, key=lambda m: (-m["saved_at"], m["name"]))

    def status(self) -> dict[str, Any]:
        s = self.state
        return {
            "turn": s.turn,
            "year": year(self.cfg, s.turn),
            "player": self.human,
            "player_name": s.players[self.human].name,
            "seed": s.seed,
            "outcome": s.outcome,
        }

    def continents(self) -> list[dict[str, Any]]:
        cfg = self.cfg
        return [
            {
                "id": c,
                "name": cfg.continents[c]["name"],
                "note": note(cfg, "continents", c),
                "capital": cfg.continents[c]["cities"][0],
            }
            for c in cfg.continent_ids()
        ]

    # -- acting ------------------------------------------------------------------------------

    def command(self, data: dict[str, Any]) -> dict[str, Any]:
        if self.state.outcome is not None:
            return {"ok": False, "error": "the game is over"}
        data = dict(data, player=self.human)
        try:
            cmd = command_from_dict(data)
            events = apply_command(self.state, self.cfg, cmd)
        except (CommandError, ValueError, TypeError, KeyError) as err:
            return {"ok": False, "error": str(err)}
        self.events.extend(events)
        return {"ok": True, "events": events}

    def end_turn(self) -> dict[str, Any]:
        if self.state.outcome is not None:
            return {"ok": False, "error": "the game is over"}
        s, cfg = self.state, self.cfg

        def submit(cmd):  # AI commands go through the same validation
            return apply_command(s, cfg, cmd)

        for pid in s.player_ids():
            if s.players[pid].controller != "human":
                ai.take_turn(s, cfg, pid, submit)
        events = advance_turn(s, cfg)
        self.events = [e for e in events if self._mine(e)]
        with contextlib.suppress(OSError):
            self.save("autosave")  # so Continue works after a restart
        return {"ok": True, "events": self.events}

    def _mine(self, e: dict[str, Any]) -> bool:
        me = self.human
        return (
            e.get("player") == me
            or e.get("kind") in PUBLIC_EVENTS
            or (e.get("kind") in ("unit_destroyed", "stack_member_lost") and e.get("owner") == me)
            or (e.get("kind") == "city_overrun" and e.get("previous_owner") == me)
            or (e.get("kind") == "mothership_strike" and e.get("player") == me)
        )

    # -- the view ------------------------------------------------------------------------------

    def view(self) -> dict[str, Any]:
        s, cfg, me = self.state, self.cfg, self.human
        v = observe(s, cfg, me)
        player = s.players[me]
        mine = [c for c in s.cities if c.owner == me and c.status == ACTIVE]
        science = gold_in = 0
        city_rows = []
        for c in mine:
            cy = economy.city_yields(s, cfg, c) if c.connected else None
            prod = cy.totals["production"] if cy else 0
            if cy:
                science += cy.totals["science"]
                gold_in += cy.totals["gold"]
            head = c.queue[0] if c.queue else None
            turns = None
            if head and not head.startswith("project:") and prod > 0:
                turns = max(0, -(-(economy.item_cost(cfg, head) - c.production_store) // prod))
            city_rows.append({"id": c.id, "production": prod, "head": head, "turns": turns})
        upkeep = economy.maintenance(s, cfg, me) + economy.unit_upkeep(s, cfg, me)
        research = None
        if player.research:
            cost = cfg.techs[player.research]["cost"]
            left = max(0, cost - player.research_progress)
            research = {
                "tech": player.research,
                "cost": cost,
                "progress": player.research_progress,
                "turns": -(-left // science) if science else None,
            }
        v.update(
            {
                "seed": s.seed,
                "width": s.width,
                "height": s.height,
                "year": year(cfg, s.turn),
                "me": me,
                "explored": fog_explored(s, me),
                "economy": {
                    "gold": player.gold,
                    "gold_per_turn": gold_in - upkeep,
                    "science_per_turn": science,
                    "beacon_points": player.beacon_points,
                    "rarity": recruits.rarity_level(cfg, player.techs),
                    "arrival_cost": recruits.arrival_cost(
                        cfg, recruits.rarity_level(cfg, player.techs)
                    ),
                },
                "research": research,
                "my_cities": city_rows,
                "players": [self._player_row(pid) for pid in s.player_ids()],
                "pending": pending_decisions(s, cfg, me),
                "events": self.events,
                "outcome": s.outcome,
                "outcome_turn": s.outcome_turn,
                "mothership_alive": s.aliens.mothership_alive,
                "ranking": [[r["player"], r["total"]] for r in mvp.ranking(s, cfg)],
                "unit_types": {
                    u: {
                        k: spec[k]
                        for k in ("role", "domain", "strength", "ranged_strength", "range", "moves")
                    }
                    for u, spec in cfg.units.items()
                },
            }
        )
        for unit in v["units"]:
            spec = cfg.units[unit["type"]]
            unit["max_hp"] = cfg.t("combat.unit_max_hp") * unit["count"]
            unit["full_moves"] = spec["moves"] * cfg.t("movement.scale")
        for key, c in v["cities"].items():
            city = s.cities[int(key)]
            c.setdefault("tile", city.tile)
            c["max_hp"] = _city_max_hp(s, cfg, city)
            c["hp_now"] = (
                city.hp
                if city.tile in fog.visible_tiles(s, cfg, me) or (city.owner == me)
                else None
            )
            c["continent"] = city.continent
        return v

    def _player_row(self, pid: str) -> dict[str, Any]:
        s = self.state
        p = s.players[pid]
        return {
            "id": pid,
            "name": p.name,
            "character": p.character,
            "controller": p.controller,
            "cities": sum(1 for c in s.cities if c.owner == pid and c.status == ACTIVE),
            "fallen": p.fallen,
            "allied": pid in s.players[self.human].allies,
            "gold": p.gold if pid == self.human else None,
        }

    # -- details -------------------------------------------------------------------------------

    def unit_options(self, unit_id: int) -> dict[str, Any]:
        s, cfg, me = self.state, self.cfg, self.human
        unit = s.units.get(str(unit_id))
        if unit is None or unit.owner != me:
            raise ValueError(f"no unit {unit_id} of yours")
        seen = fog.visible_tiles(s, cfg, me)
        reach = max(1, cfg.units[unit.type]["range"])
        attacks = []
        for t in hexgrid.within(unit.tile, reach, s.width, s.height):
            if combat.attack_problem(s, cfg, unit, t, seen) is None:
                attacks.append({"tile": t, "preview": combat.preview_attack(s, cfg, unit, t)})
        known = {int(k) for k in s.players[me].known_cities}
        ships = [
            {
                "city": c,
                "name": s.cities[c].name,
                "price": diplomacy.ship_price(s, cfg, s.city_at(unit.tile), s.cities[c]),
            }
            for c in sorted(known)
            if s.city_at(unit.tile) is not None
            and diplomacy.ship_problem(s, cfg, unit, c, known) is None
        ]
        city = s.city_at(unit.tile)
        return {
            "unit": to_dict(unit),
            "reachable": movement.reachable_this_turn(s, cfg, unit),
            "attacks": attacks,
            "builds": [
                i
                for i in sorted(cfg.improvements)
                if improvements.build_problem(s, cfg, unit, i) is None
            ],
            "merges": [
                o.id
                for o in s.sorted_units()
                if o.owner == me
                and o.id != unit.id
                and movement.merge_problem(s, cfg, unit, o) is None
                and hexgrid.distance(o.tile, unit.tile, s.width) <= 3
            ],
            "splits": [
                n
                for n in hexgrid.neighbours(unit.tile, s.width, s.height)
                if movement.split_problem(s, cfg, unit, n) is None
            ],
            "refound": bool(
                cfg.units[unit.type].get("can_refound")
                and city is not None
                and city.status == "empty"
                and unit.moves_left > 0
            ),
            "ships": ships,
            "spec": cfg.units[unit.type],
        }

    def city_detail(self, city_id: int) -> dict[str, Any]:
        s, cfg, me = self.state, self.cfg, self.human
        if not 0 <= city_id < len(s.cities) or s.cities[city_id].owner != me:
            raise ValueError(f"no city {city_id} of yours")
        c = s.cities[city_id]
        cy = economy.city_yields(s, cfg, c)
        prod = cy.totals["production"] if c.connected else 0
        options = []
        for item in economy.production_options(s, cfg, c):
            kind, _, ident = item.partition(":")
            cost = economy.item_cost(cfg, item) if kind != "project" else None
            options.append(
                {
                    "item": item,
                    "kind": kind,
                    "id": ident,
                    "cost": cost,
                    "turns": (
                        -(-max(0, cost - c.production_store) // prod)
                        if cost is not None and prod > 0
                        else None
                    ),
                    "note": note(cfg, "buildings" if kind == "building" else "units", ident)
                    if kind != "project"
                    else "",
                    "price": cost * cfg.t("economy.purchase_pct") // 100 if cost else None,
                }
            )
        seen = fog.visible_tiles(s, cfg, me)
        bombard = [
            t
            for t in hexgrid.within(c.tile, cfg.t("cities.attack_range"), s.width, s.height)
            if combat.city_attack_problem(s, cfg, c, t, seen) is None
        ]
        return {
            "city": to_dict(c),
            "max_hp": _city_max_hp(s, cfg, c),
            "lines": [list(line) for line in cy.lines],
            "totals": cy.totals,
            "food_eaten": cy.food_eaten,
            "growth_threshold": economy.growth_threshold(cfg, c.pop),
            "worked": cy.worked,
            "options": options,
            "strength": combat.city_strength(s, cfg, c).total,
            "bombard": bombard,
            "focuses": list(economy.FOCUSES),
        }

    def techs(self) -> dict[str, Any]:
        s, cfg, me = self.state, self.cfg, self.human
        player = s.players[me]
        available = set(tech.available(cfg, player))
        unlocks: dict[str, list[str]] = {}
        for table, kind in (
            (cfg.buildings, "building"),
            (cfg.units, "unit"),
            (cfg.improvements, "improvement"),
        ):
            for ident, spec in table.items():
                if spec.get("tech") and not spec.get("not_buildable"):
                    unlocks.setdefault(spec["tech"], []).append(f"{kind}:{ident}")
        rows = []
        for t, spec in sorted(
            cfg.techs.items(), key=lambda kv: (kv[1]["tree"], kv[1]["tier"], kv[0])
        ):
            status = (
                "known"
                if t in player.techs
                else "researching"
                if t == player.research
                else "available"
                if t in available
                else "locked"
            )
            rows.append(
                {
                    "id": t,
                    "tree": spec["tree"],
                    "tier": spec["tier"],
                    "cost": spec["cost"],
                    "prereqs": spec["prereqs"],
                    "note": note(cfg, "techs", t),
                    "status": status,
                    "unlocks": sorted(unlocks.get(t, [])),
                }
            )
        return {"techs": rows, "research": player.research, "progress": player.research_progress}

    def council(self) -> dict[str, Any]:
        s, cfg, me = self.state, self.cfg, self.human
        rs = cfg.alien("recruits")
        mine = recruits.recruits_of(s, me)
        seats = {d: sum(1 for r in mine if d in r.seats) for d in DOMAINS}
        seats["general"] = sum(1 for r in mine if "general" in r.seats)
        return {
            "recruits": [
                dict(to_dict(r), age=s.turn - r.born, betrayal=recruits.betrayal_permille(cfg, r))
                for r in mine
            ],
            "seats_used": seats,
            "seats_per_domain": rs["seats_per_domain"],
            "general_seats": rs["general_seats"],
            "domains": list(DOMAINS),
            "bonus": {d: sum(p for _, p in recruits.council_lines(s, me, d)) for d in DOMAINS},
            "offers": [to_dict(o) for o in s.offers.values() if o.to_player == me],
        }

    def diplomacy(self) -> dict[str, Any]:
        s, cfg, me = self.state, self.cfg, self.human
        player = s.players[me]
        return {
            "players": [self._player_row(pid) for pid in s.player_ids() if pid != me],
            "alliance_tech": cfg.t("trade.alliance_tech"),
            "has_alliance_tech": cfg.t("trade.alliance_tech") in player.techs,
            "incoming": [to_dict(d) for d in s.deals.values() if d.receiver == me and not d.active],
            "active": [
                to_dict(d) for d in s.deals.values() if d.active and me in (d.proposer, d.receiver)
            ],
            "giftable_techs": {
                pid: [t for t in player.techs if t in tech.available(cfg, s.players[pid])]
                for pid in s.player_ids()
                if pid != me
            },
            "shipments": [
                to_dict(x) for x in s.shipments.values() if me in (x.from_player, x.to_player)
            ],
        }

    def projects(self) -> dict[str, Any]:
        s, cfg, me = self.state, self.cfg, self.human
        b = endgame.barrage(s)
        return {
            "barrage": to_dict(b) if b else None,
            "barrage_tech": cfg.t("endgame.barrage_tech"),
            "has_barrage_tech": cfg.t("endgame.barrage_tech") in s.players[me].techs,
            "barrage_cost": cfg.t("endgame.barrage.cost"),
            "barrage_min_turns": cfg.t("endgame.barrage.min_turns"),
            "host_name": s.cities[b.host_city].name if b and b.host_city is not None else None,
            "espionage": [
                to_dict(p)
                for p in s.projects.values()
                if p.kind == "espionage" and (p.mode == "shared" or p.starter == me)
            ],
            "espionage_cost": cfg.t("endgame.espionage.cost"),
            "my_operation": endgame.open_operation(s, me) is not None,
            "mothership_alive": s.aliens.mothership_alive,
            "reinforcements_stopped": s.aliens.reinforcements_stopped,
            "alien_cities_known": sum(
                1 for k in s.players[me].known_cities if s.cities[int(k)].status == "overrun"
            ),
        }

    def scores(self) -> dict[str, Any]:
        return {
            "ranking": mvp.ranking(self.state, self.cfg),
            "outcome": self.state.outcome,
            "outcome_turn": self.state.outcome_turn,
            "names": {pid: p.name for pid, p in self.state.players.items()},
        }


def note(cfg: Config, file: str, ident: str) -> str:
    """An entry's `note` from the raw data (loaded tables drop tagging metadata)."""
    entry = cfg.raw.get(file, {}).get(file, {}).get(ident, {})
    return str(entry.get("note", "")) if isinstance(entry, dict) else ""


def fog_explored(state: GameState, pid: str) -> list[int]:
    from beacon.state import bits_get, bits_indices

    return bits_indices(bits_get(state.players[pid].explored))


def _city_max_hp(state: GameState, cfg: Config, city) -> int:
    from beacon.cities import max_hp

    return max_hp(cfg, city, state if city.owner == ALIENS else None)
