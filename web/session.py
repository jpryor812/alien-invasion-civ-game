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
    citizens,
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
    turrets,
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
                "capital": cfg.continents[c]["cities"][0]["name"],
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
        # Where gold, science and beacon points come from (hover the top bar): by source kind
        # across all cities, and by city.
        sources: dict[str, dict[str, int]] = {y: {} for y in ("gold", "science", "beacon")}
        by_city: dict[str, list[list[Any]]] = {y: [] for y in ("gold", "science", "beacon")}
        for c in mine:
            cy = economy.city_yields(s, cfg, c) if c.connected else None
            prod = cy.totals["production"] if cy else 0
            if cy:
                science += cy.totals["science"]
                gold_in += cy.totals["gold"]
                for src, y, amount in cy.lines:
                    if y in sources:
                        label = _source_label(src)
                        sources[y][label] = sources[y].get(label, 0) + amount
                for y in sources:
                    if cy.totals[y]:
                        by_city[y].append([c.name, cy.totals[y]])
            head = c.queue[0] if c.queue else None
            turns = None
            if head and not head.startswith("project:") and prod > 0:
                turns = max(0, -(-(economy.item_cost(cfg, head) - c.production_store) // prod))
            city_rows.append({"id": c.id, "production": prod, "head": head, "turns": turns})
        upkeep = economy.maintenance(s, cfg, me) + economy.unit_upkeep(s, cfg, me)
        unlinked = [c.name for c in mine if not c.connected]
        breakdown = {
            y: {
                "sources": sorted(sources[y].items(), key=lambda kv: -kv[1]),
                "cities": by_city[y],
                "unlinked": unlinked,
            }
            for y in sources
        }
        breakdown["gold"]["costs"] = [
            ["Building upkeep", -economy.maintenance(s, cfg, me)],
            ["Unit upkeep", -economy.unit_upkeep(s, cfg, me)],
        ]
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
                    "breakdown": breakdown,
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
                "has_barrage_tech": cfg.t("endgame.barrage_tech") in player.techs,
                "turret_rules": {
                    **cfg.t("turrets"),
                    "costs": {
                        str(i): turrets.upgrade_cost(cfg, s.tiles[i])
                        for i, t in enumerate(s.tiles)
                        if t.turret and t.built_by == me
                    },
                },
                "worked": {
                    str(c.tile): {
                        "citizen": c.name,
                        "city": s.cities[c.city].name,
                        "bonus": citizens.tile_bonus(cfg, c),
                    }
                    for c in citizens.of_player(s, me)
                    if c.tile is not None
                },
                "ranking": [[r["player"], r["total"]] for r in mvp.ranking(s, cfg)],
                "unit_types": {
                    u: {
                        k: spec[k]
                        for k in ("role", "domain", "strength", "ranged_strength", "range", "moves")
                    }
                    | {"fixed": bool(spec.get("fixed")), "no_attack": bool(spec.get("no_attack"))}
                    for u, spec in cfg.units.items()
                },
            }
        )
        for key, t in v["tiles"].items():
            if t.get("improvement"):
                t["yields"] = _tile_yields(cfg, s.tiles[int(key)])  # what the tile gives a city
        for unit in v["units"]:
            if unit["owner"] == me and str(unit["id"]) in s.units:
                unit["promotion"] = self._promotion_info(s.units[str(unit["id"])])
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
            "build_info": {
                i: self._build_info(unit.tile, i)
                for i in sorted(cfg.improvements)
                if improvements.build_problem(s, cfg, unit, i) is None
            },
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
            "promotion": self._promotion_info(unit),
        }

    def _promotion_info(self, unit) -> dict[str, Any]:
        from beacon import promotions

        cfg = self.cfg
        if cfg.units[unit.type].get("fixed"):  # city guns: gold upgrades, no experience
            return {
                "fixed": True,
                "level": unit.promotions.count(promotions.GOLD_UPGRADE),
                "upgrade_cost": promotions.upgrade_cost(cfg, unit),
                "strength_pct": cfg.t("defences.upgrade.strength_pct"),
            }
        raw = cfg.raw["tuning"]["promotions"]["options"]
        return {
            "xp": unit.xp,
            "next": promotions.next_threshold(cfg, unit.xp),
            "due": promotions.due(cfg, unit),
            "taken": list(unit.promotions),
            "options": [
                {"id": o, "note": raw[o].get("note", "")} for o in promotions.options(cfg, unit)
            ],
        }

    def _build_info(self, tile_index: int, imp: str) -> dict[str, Any]:
        """What building `imp` here would do: its description plus the tile's yields before and
        after (and which city it would feed)."""
        from beacon.tiles import tile_yields

        cfg, tile = self.cfg, self.state.tiles[tile_index]
        before = tile_yields(cfg, tile)
        if cfg.improvements[imp]["kind"] == "route":
            after = before
        else:
            old = tile.improvement
            tile.improvement = imp
            after = tile_yields(cfg, tile)
            tile.improvement = old
        city = self.state.cities[tile.city] if tile.city is not None else None
        return {
            **describe(cfg, "improvement", imp),
            "before": before,
            "after": after,
            "city": city.name if city is not None and city.owner == self.human else None,
        }

    def _citizen_row(self, c, surplus: int) -> dict[str, Any]:
        s, cfg = self.state, self.cfg
        traits = cfg.raw["tuning"]["citizens"]["traits"]
        on_tile = c.tile is not None
        return {
            "id": c.id,
            "name": c.name,
            "stats": c.stats,
            "traits": [{"id": t, "note": traits[t].get("note", "")} for t in c.traits],
            "adult": c.adult,
            "growth": c.growth,
            "growth_needed": cfg.t("citizens.growing_up.needed"),
            "turns_to_grow": None if c.adult else citizens.turns_to_grow(cfg, c, surplus),
            "job": c.job,
            "tile": c.tile,
            "seats": c.seats,
            "improvement": s.tiles[c.tile].improvement if on_tile else None,
            # hundredths, so the client can show +1.5
            "bonus": citizens.tile_bonus(cfg, c)
            if on_tile
            else {y: v * 100 for y, v in citizens.council_bonus(cfg, c).items()}
            if c.seats
            else {},
            "military": citizens.council_military(cfg, c) if c.seats else 0,
            "born": c.born,
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
                    "info": describe(cfg, kind, ident),
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
            "citizens": [self._citizen_row(x, cy.surplus_food) for x in citizens.of_city(s, c.id)],
            "workable": [
                {
                    "tile": t,
                    "improvement": s.tiles[t].improvement,
                    "yields": _tile_yields(cfg, s.tiles[t]),
                }
                for t in citizens.workable(s, cfg, c)
            ],
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
        science = self.view()["economy"]["science_per_turn"]
        rows = []
        for t, spec in sorted(
            cfg.techs.items(), key=lambda kv: (kv[1]["tier"], kv[1]["tree"], kv[0])
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
                    "unlocks": [
                        {"item": u, **describe(cfg, *u.split(":", 1))}
                        for u in sorted(unlocks.get(t, []))
                    ],
                    "turns": None
                    if status == "known" or spec["tree"] == "alien" or not science
                    else -(
                        -max(
                            0,
                            spec["cost"]
                            - (player.research_progress if status == "researching" else 0),
                        )
                        // science
                    ),
                }
            )
        return {"techs": rows, "research": player.research, "progress": player.research_progress}

    def council(self) -> dict[str, Any]:
        s, cfg, me = self.state, self.cfg, self.human
        rs = cfg.alien("recruits")
        mine = recruits.recruits_of(s, me)
        people = [c for c in citizens.of_player(s, me) if c.seats]
        seats = {d: sum(1 for r in mine if d in r.seats) for d in DOMAINS}
        seats["general"] = sum(1 for r in mine if "general" in r.seats)
        for c in people:
            for seat in c.seats:
                seats[seat] += 1
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
            "citizens": [
                dict(
                    self._citizen_row(c, 0),
                    city=s.cities[c.city].name,
                )
                for c in people
            ],
            # The seat board (designer 2026-11-14): every seat with who sits there, and every
            # member who could sit - alien recruits and grown citizens of every city.
            "board": {
                seat: [m for m in self._members() if seat in m["seats"]]
                for seat in ["general", *DOMAINS]
            },
            "members": self._members(),
        }

    def _members(self) -> list[dict[str, Any]]:
        s, me = self.state, self.human
        out = []
        for r in recruits.recruits_of(s, me):
            out.append(
                {
                    "kind": "recruit",
                    "id": r.id,
                    "name": r.name,
                    "where": "alien recruit" + (" (legendary)" if r.legendary else ""),
                    "scores": {d: f"+{v}%" for d, v in r.scores.items() if v},
                    "seats": list(r.seats),
                    "pinned": True,
                    "traits": list(r.traits),
                }
            )
        for c in citizens.of_player(s, me):
            if not c.adult:
                continue
            city = s.cities[c.city]
            out.append(
                {
                    "kind": "citizen",
                    "id": c.id,
                    "name": c.name,
                    "where": f"citizen of {city.name}",
                    "scores": {d: f"+{v}" for d, v in c.stats.items() if v},
                    "seats": list(c.seats),
                    "pinned": c.job.startswith("council"),
                    "job": c.job,
                    "tile": c.tile,
                    "traits": list(c.traits),
                }
            )
        return out

    def population(self) -> dict[str, Any]:
        """Every city's citizens and what they do (the Population screen)."""
        s, cfg, me = self.state, self.cfg, self.human
        rows = []
        for c in s.cities:
            if c.owner != me or c.status != ACTIVE:
                continue
            cy = economy.city_yields(s, cfg, c)
            people = citizens.of_city(s, c.id)
            rows.append(
                {
                    "id": c.id,
                    "name": c.name,
                    "pop": c.pop,
                    "surplus_food": cy.surplus_food,
                    "growth": [c.food_store, economy.growth_threshold(cfg, c.pop)],
                    "on_tiles": sum(1 for x in people if x.tile is not None),
                    "on_council": sum(1 for x in people if x.seats),
                    "children": sum(1 for x in people if not x.adult),
                    "idle": sum(1 for x in people if x.adult and x.tile is None and not x.seats),
                    "citizens": [self._citizen_row(x, cy.surplus_food) for x in people],
                    "workable": [
                        {
                            "tile": t,
                            "improvement": s.tiles[t].improvement,
                            "yields": _tile_yields(cfg, s.tiles[t]),
                        }
                        for t in citizens.workable(s, cfg, c)
                    ],
                }
            )
        return {"cities": rows}

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


YIELD_WORD = {
    "food": "food",
    "production": "production",
    "science": "science",
    "gold": "gold",
    "beacon": "beacon points",
}
PROJECT_INFO = {
    "wealth": (["Turns this city's production into gold."], ["gold"]),
    "research": (["Turns this city's production into science."], ["science"]),
    "barrage": (
        ["Sends production to the world barrage that destroys the mothership."],
        ["military"],
    ),
}


def describe(cfg: Config, kind: str, ident: str) -> dict[str, Any]:
    """What a building, unit, improvement or project does, as short lines, plus tags naming
    what it helps (food, production, science, gold, beacon, military, defence, sight, movement)."""
    lines: list[str] = []
    tags: list[str] = []
    if kind == "project":
        text, tags = PROJECT_INFO.get(ident, ([], []))
        return {"lines": list(text), "tags": list(tags), "note": ""}
    if kind == "building":
        b = cfg.buildings[ident]
        for y, v in sorted(b.get("yields", {}).items()):
            lines.append(f"+{v} {YIELD_WORD.get(y, y)} per turn")
            tags.append(y)
        for y, v in sorted(b.get("yield_pct", {}).items()):
            lines.append(f"+{v}% {YIELD_WORD.get(y, y)} in this city")
            tags.append(y)
        if b.get("city_strength"):
            lines.append(f"+{b['city_strength']} city defence strength")
            tags.append("defence")
        if b.get("city_hp"):
            lines.append(f"+{b['city_hp']} city HP")
            tags.append("defence")
        if b.get("unit_production_pct"):
            lines.append(f"+{b['unit_production_pct']}% production toward units")
            tags.append("military")
        if b.get("vision"):
            lines.append(f"City sees {b['vision']} more hexes")
            tags.append("sight")
        if b.get("requires_building"):
            lines.append(f"Needs a {b['requires_building'].replace('_', ' ')} first")
        if b.get("coastal"):
            lines.append("Coastal cities only")
        if b.get("maintenance"):
            lines.append(f"Upkeep {b['maintenance']} gold per turn")
        return {"lines": lines, "tags": sorted(set(tags)), "note": note(cfg, "buildings", ident)}
    if kind == "unit":
        u = cfg.units[ident]
        role = u["role"]
        if role == "civilian":
            if u.get("can_build"):
                lines.append("Builds roads, railways, farms, mines and extractors")
                tags.append("production")
            if u.get("can_refound"):
                lines.append("Rebuilds a ruined city (used up)")
                tags.append("food")
            if not lines:
                lines.append("Does not fight")
        else:
            lines.append(
                f"Strength {u['strength']}" + (" (defence only)" if u.get("no_attack") else "")
            )
            if u["ranged_strength"]:
                lines.append(f"Ranged strength {u['ranged_strength']}, range {u['range']}")
            tags.append("defence" if u.get("fixed") else "military")
        if u.get("fixed"):
            lines.append("City defence: never moves, stays in its city")
        else:
            lines.append(f"Moves {u['moves']}, sees {u['vision']}")
        if role == "recon":
            lines.append("Scout: finds lost cities in the fog")
            tags.append("sight")
        if u["domain"] == "sea":
            lines.append("Ship: coastal cities only")
        if u.get("requires_resource"):
            lines.append(f"Needs 1 {u['requires_resource'].replace('_', ' ')}")
        return {"lines": lines, "tags": sorted(set(tags)), "note": note(cfg, "units", ident)}
    if kind == "improvement":
        m = cfg.improvements[ident]
        for y, v in sorted(m.get("yields", {}).items()):
            lines.append(f"+{v} {YIELD_WORD.get(y, y)} on its hex")
            tags.append(y)
        if m.get("defense_pct"):
            lines.append(f"+{m['defense_pct']}% defence on its hex")
            tags.append("defence")
        if m.get("vision"):
            lines.append(f"Reveals {m['vision']} hexes around it")
            tags.append("sight")
        if m.get("kind") == "route":
            lines.append("Faster movement; joins cities to the capital")
            tags.append("movement")
        lines.append(f"Engineers build it in {m['turns']} turns")
        return {"lines": lines, "tags": sorted(set(tags)), "note": note(cfg, "improvements", ident)}
    return {"lines": [], "tags": [], "note": ""}


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


def _tile_yields(cfg: Config, tile: Any) -> dict[str, int]:
    from beacon.tiles import tile_yields

    return tile_yields(cfg, tile)


def _source_label(src: str) -> str:
    """A readable name for a yield line's source (see economy.city_yields)."""
    if src in ("city_tile", "city_centre"):
        return "City centres"
    if src == "worked_tiles":
        return "Worked tiles"
    if src == "citizens_on_tiles":
        return "Citizens on tiles (half stats)"
    if src == "population":
        return "Population"
    if src.startswith("citizen:") and src.endswith("(council)"):
        return "Citizens on the council"
    if src.startswith("council:"):
        return "Alien council (" + src.split(" ")[-1] + ")" if " " in src else "Alien council"
    if src.startswith("building:"):
        name = src[9:].split(" ")[0].replace("_", " ").capitalize()
        return f"{name} (+%)" if "%" in src else name
    return src.replace("_", " ").capitalize()
