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
    leader,
    movement,
    mvp,
    recruits,
    tech,
    turrets,
)
from beacon import threat as threat_mod
from beacon.actions import apply_command, pending_decisions
from beacon.commands import CommandError, command_from_dict
from beacon.config import DOMAINS, Config
from beacon.game import new_game
from beacon.state import ACTIVE, ALIENS, GameState, state_from_json, state_to_json, to_dict
from beacon.turn import advance_turn, year
from beacon.view import observe
from web import profile

SAVE_DIR = Path(__file__).resolve().parent.parent / "runs" / "saves"
PUBLIC_EVENTS = frozenset(
    {
        "shard_warning",
        "shard_landed",
        "shard_claimed",
        "shard_faded",
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
    def __init__(self, cfg: Config, seed: int = 1, human: str = "europe", start: str | None = None):
        self.cfg = cfg
        self.reveal = False  # developer only (web.server --reveal): the whole map, for art
        self.profile_path = profile.PROFILE  # the career profile (tests point it elsewhere)
        self.new(seed, human, start)

    # -- lifecycle ---------------------------------------------------------------------------

    def new(self, seed: int, human: str, start: str | None = None) -> None:
        state = new_game(self.cfg, seed, start=start or self.cfg.t("start.mode"))
        if human not in state.players:
            raise ValueError(f"unknown player {human!r}")
        state.players[human].controller = "human"
        self.state, self.human = state, human
        self.events: list[dict[str, Any]] = []
        self.game_id = f"{int(time.time())}-{seed}-{human}"  # its row in the career profile

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
        self.game_id = f"save-{name}-{state.seed}-{self.human}"

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
        if data.get("kind") == "set_wardrobe":  # cosmetics unlock from the career (SPEC_M11)
            career = self.career()
            items = [("outfits", data.get("outfit"))] + [
                ("accessories", a) for a in data.get("accessories") or []
            ]
            for kind, item in items:
                if (
                    item in self.cfg.leader(f"wardrobe.{kind}")
                    and not self.reveal
                    and not profile.unlocked(self.cfg, career, kind, item)
                ):
                    return {"ok": False, "error": f"{item} is not unlocked in your career yet"}
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
        with contextlib.suppress(OSError):
            credits = s.players[self.human].credits
            profile.record(self.game_id, credits, s.outcome == "victory", self.profile_path)
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
            cy = economy.city_yields(s, cfg, c)  # SPEC_M10: every active city produces
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
                turns = max(
                    0,
                    -(
                        -(economy.item_cost(cfg, head, s.players[me]) - economy.stored(c, head))
                        // prod
                    ),
                )
            city_rows.append({"id": c.id, "production": prod, "head": head, "turns": turns})
        upkeep = (
            economy.maintenance(s, cfg, me)
            + economy.unit_upkeep(s, cfg, me)
            + economy.road_upkeep(s, cfg, me)
        )
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
            ["Unconnected roads", -economy.road_upkeep(s, cfg, me)],
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
                "wrap": s.wrap,
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
                **self._story_view(),
                **self._threat_view(),
                "leader": None  # the top-left badge (SPEC_M11)
                if (lead := self.state.players[self.human].leader) is None
                else {
                    "name": lead.name,
                    "look": lead.look,
                    "outfit": lead.outfit,
                    "level": lead.level,
                    "alert": leader.points(self.cfg, lead) > 0 or bool(lead.choices),
                },
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
        if self.reveal:  # developer view for art testing: every hex, seen
            v["tiles"] = {str(i): {**to_dict(t), "visible": True} for i, t in enumerate(s.tiles)}
            v["explored"] = list(range(len(s.tiles)))
            v["cities"] = {str(c.id): to_dict(c) for c in s.cities}
            v["units"] = [to_dict(u) for u in sorted(s.units.values(), key=lambda u: u.id)]
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
            c["strength"] = combat.city_strength(s, cfg, city).total  # the banner's shield
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
        met = pid == self.human or pid in s.players[self.human].met
        if not met:  # an unmet continent: only that it exists (designer 2026-11-14)
            return {
                "id": pid,
                "name": p.name,
                "met": False,
                "fallen": False,
                "allied": False,
                "character": None,
                "controller": None,
                "cities": None,
                "gold": None,
            }
        return {
            "id": pid,
            "name": p.name,
            "met": True,
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
            "bridges": [  # shallow water hexes beside the engineers (SPEC_M11)
                t
                for t in improvements.bridge_targets(s, cfg, unit)
                if improvements.build_problem(s, cfg, unit, "sea_bridge", t) is None
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
            "sabotage": [  # SPEC_M12
                c.id for c in s.cities if threat_mod.sabotage_problem(s, cfg, unit, c) is None
            ],
            "arm": [c.id for c in s.cities if threat_mod.arm_problem(s, cfg, unit, c) is None],
            "arm_gold": cfg.alien("resistance.gold"),
            "spec": cfg.units[unit.type],
            "promotion": self._promotion_info(unit),
        }

    def _threat_view(self) -> dict[str, Any]:
        """Announced strikes on your cities, your heat (SPEC_M12)."""
        from beacon import threat
        from beacon.state import bits_get

        s, cfg, me = self.state, self.cfg, self.human
        bits = bits_get(s.players[me].explored)
        strikes = []
        for p in threat.detected(s, cfg, me):  # only cities with a UAV patrol get a warning
            city = s.city_at(p.target)
            if city is None:
                continue
            seen = True  # the drones see where it gathers
            strength = sum(
                combat.unit_strength(s, cfg, s.units[str(u)], ranged=False, defending=False).total
                for u in p.units
                if str(u) in s.units
            )
            strikes.append(
                {
                    "id": p.id,
                    "city": city.id,
                    "city_name": city.name,
                    "target": p.target,
                    "turns": max(0, p.launch - s.turn),
                    "source": p.source if seen else None,
                    "units": len(p.units) if seen else None,
                    "strength": strength // 100 if seen else None,
                    "defence": combat.city_strength(s, cfg, city).total // 100,
                }
            )
        from beacon import council

        rank = [r["player"] for r in mvp.ranking(s, cfg)]
        player = s.players[me]
        town = s.cities[player.band_town] if player.band_town is not None else None
        return {
            # SPEC_M14: the survivor start - explored caches, the band's first town
            "founded": player.founded,
            "band_town": None if player.founded or town is None else town.tile,
            "scrap": player.scrap,
            "caches": sorted(int(k) for k in s.caches if (bits >> int(k)) & 1),
            "influence": council.influence(cfg, s.players[me]),
            "mvp_rank": rank.index(me) + 1,
            "council_open": bool(s.council.measures),
            "chair": s.council.chair,
            "strikes": strikes,
            "heat": threat.heat(s, cfg, me),
            "heat_lines": threat.heat_lines(s, cfg, me),
            "uprising_pct": cfg.alien("resistance.uprising_pct"),
        }

    def _story_view(self) -> dict[str, Any]:
        """Events, finds and shards for the client (docs/SPEC_M9.md). Finds show only on explored
        hexes, and not what they are; shards are public (everyone sees the sky)."""
        from beacon import starfall, story
        from beacon.state import bits_get

        s, cfg, me = self.state, self.cfg, self.human
        bits = bits_get(s.players[me].explored)
        sf = starfall.settings(cfg)

        def card(event_id: str) -> dict[str, Any]:
            e = cfg.events[event_id]
            return {
                "event": event_id,
                "title": e["title"],
                "body": e["body"],
                "picture": e["picture"],
                "big": bool(e.get("big")),
            }

        pending = [
            {
                **card(ev.event),
                "story": ev.id,
                "tile": ev.tile,
                "choices": [
                    {"label": c["label"], "detail": c.get("detail", "")}
                    for c in cfg.events[ev.event]["choices"]
                ],
            }
            for ev in story.pending(s, me)
        ]
        cards = [
            {
                **card(e["event"]),
                "result": e.get("result", []),
                "tile": e.get("tile"),
                "key": f"{e.get('turn')}-{e['event']}-{e.get('tile')}",
            }
            for e in self.events
            if e.get("kind") in ("story_event", "story_chosen")
            and e.get("player") == me
            and not e.get("pending")
        ]
        shards = []
        for sh in starfall.active(s):
            if sh.remnant and not (bits >> sh.tile) & 1:
                continue  # a remnant shows once its hex is explored (it must be found)
            row = {
                "id": sh.id,
                "center": sh.cone_center,
                "radius": sh.cone_radius,
                "impact_turn": sh.impact_turn,
                "landed": starfall.landed(s, sh),
                "progress": dict(sh.progress),
                "needed": sf["mine_turns"],
                "fades_turn": None if sh.remnant else sh.impact_turn + sf["fade_turns"],
                "remnant": sh.remnant,
            }
            if row["landed"]:
                row.update(
                    tile=sh.tile,
                    kind=sh.kind,
                    name=sf["kinds"][sh.kind]["name"],
                    reward=_effect_text(starfall.reward(cfg, sh.kind, s.turn)),
                )
            shards.append(row)
        claimed = [
            {
                "key": f"shard-{e['shard']}",
                "name": e["name"],
                "by": e["by"],
                "find": e["find"],
                "tile": e["tile"],
                "quote": sf["kinds"][e["find"]]["quote"],
                "reward": _effect_text(e.get("effects") or {}),
            }
            for e in self.events
            if e.get("kind") == "shard_claimed"
        ]
        return {
            "story_pending": pending,
            "story_cards": cards,
            "shards": shards,
            "shards_claimed": claimed,
            "sites": [
                x.tile for x in s.sites.values() if x.found_by is None and (bits >> x.tile) & 1
            ],
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
            "kin": c.kin,
            "hybrid": c.hybrid,
            "banned_until": c.banned_until,
        }

    def builder(self, city_id: int) -> dict[str, Any]:
        """The city builder (SPEC_M16): land, layout, walls, stores and what can be built."""
        from beacon import layout, materials, tech

        s, cfg, me = self.state, self.cfg, self.human
        if not 0 <= city_id < len(s.cities) or s.cities[city_id].owner != me:
            raise ValueError(f"no city {city_id} of yours")
        c = s.cities[city_id]
        layout.ensure(s, cfg, c)
        cy = economy.city_yields(s, cfg, c)
        tiles = []
        for t in layout.territory_tiles(s, cfg, c):
            ox, oy = layout._offset(s, c.tile, t)
            tile = s.tiles[t]
            tiles.append(
                {
                    "tile": t,
                    "x": round(ox * 1000),  # thousandths of a hex radius
                    "y": round(oy * 1000),
                    "terrain": tile.terrain,
                    "elevation": tile.elevation,
                    "feature": tile.feature,
                    "improvement": tile.improvement,
                    "resource": tile.resource,
                }
            )
        queued = [i.split(":", 1)[1] for i in c.queue if i.startswith("building:")]
        catalog = {}
        for b in sorted(cfg.buildings):
            why = economy.building_allowed(s, cfg, c, b)
            if why == "already built":
                continue
            catalog[b] = {
                "name": b.replace("_", " ").capitalize(),
                "note": note(cfg, "buildings", b),
                "size": layout.size_of(cfg, b),
                "production": cfg.buildings[b]["cost"],
                "materials": materials.building_cost(cfg, b),
                "why": why,
                "placed": layout.pending(c, b) is not None,
                "queued": b in queued,
            }
        player = s.players[me]
        walls = {
            m: {
                "name": w["name"],
                "cost": w["cost"],
                "production": w["production"],
                "strength": w["strength"],
                "hp": w["hp"],
                "why": None
                if not w["tech"] or tech.knows(player, w["tech"])
                else f"needs tech {w['tech']}",
            }
            for m, w in cfg.materials("walls").items()
        }
        return {
            "city": {"id": c.id, "name": c.name, "hp": c.hp, "max_hp": _city_max_hp(s, cfg, c)},
            "strength": combat.city_strength(s, cfg, c).total // 100,
            "cells_per_hex": cfg.materials("layout.cells_per_hex"),
            "gap": cfg.materials("layout.gap"),
            "cells": sorted(layout.territory(s, cfg, c)),
            "tiles": tiles,
            "layout": [dict(e, size=layout.size_of(cfg, e["what"])) for e in c.layout],
            "walls": [[*map(int, k.split(",")), m] for k, m in sorted(c.walls.items())],
            "wall_orders": [list(o) for o in c.wall_orders],
            "wall_totals": layout.wall_totals(cfg, c),
            "stores": {g: c.stores.get(g, 0) for g in materials.goods(cfg)},
            "caps": materials.caps(cfg, c),
            "income": materials.income(s, cfg, c, cy.worked),
            "catalog": catalog,
            "wall_types": walls,
            "queue": list(c.queue),
            "production": cy.totals["production"],
        }

    def city_detail(self, city_id: int) -> dict[str, Any]:
        s, cfg, me = self.state, self.cfg, self.human
        if not 0 <= city_id < len(s.cities) or s.cities[city_id].owner != me:
            raise ValueError(f"no city {city_id} of yours")
        c = s.cities[city_id]
        cy = economy.city_yields(s, cfg, c)
        prod = cy.totals["production"]
        options = []
        from beacon import materials

        for item in economy.production_options(s, cfg, c):
            kind, _, ident = item.partition(":")
            if item == "walls":  # the wall pieces laid in the builder (SPEC_M16)
                kind = ident = "walls"
            cost = economy.item_cost(cfg, item, s.players[me], c) if kind != "project" else None
            needs = materials.item_cost(cfg, c, item)
            options.append(
                {
                    "item": item,
                    "kind": kind,
                    "id": ident,
                    "cost": cost,
                    "turns": (
                        -(-max(0, cost - economy.stored(c, item)) // prod)
                        if cost is not None and prod > 0
                        else None
                    ),
                    "note": note(cfg, "buildings" if kind == "building" else "units", ident)
                    if kind in ("building", "unit")
                    else f"{len(c.wall_orders)} wall pieces laid out in the builder"
                    if kind == "walls"
                    else "",
                    "info": describe(cfg, kind, ident) if kind != "walls" else {},
                    "materials": needs,
                    "short": materials.short(c, needs),
                    "progress": economy.stored(c, item),
                    "price": economy.purchase_price(
                        cfg, item, s.players[me], economy.stored(c, item), c
                    )
                    if cost
                    else None,
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
            "stores": {g: c.stores.get(g, 0) for g in materials.goods(cfg)},
            "caps": materials.caps(cfg, c),
            "income": materials.income(s, cfg, c, cy.worked),
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
                    "effects": _tech_effects(cfg, t),
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
            "session": self._session(),
            "leader": {  # the leader heads the council (SPEC_M11)
                "name": player.leader.name,
                "look": player.leader.look,
                "outfit": player.leader.outfit,
                "level": player.leader.level,
                "skills": player.leader.skills,
            }
            if (player := s.players[me]).leader
            else None,
        }

    def _session(self) -> dict[str, Any]:
        """The council of continents (SPEC_M13): the open session, proposals, measures in force,
        agendas (public) and your secret objective."""
        from beacon import council

        s, cfg, me = self.state, self.cfg, self.human
        c = s.council
        specs = cfg.council("measures")

        def row(m) -> dict[str, Any]:
            spec = specs[m.kind]
            return {
                "id": m.id,
                "kind": m.kind,
                "name": spec["name"],
                "info": spec["info"],
                "chair": spec["kind"] == "chair",
                "proposer": m.proposer,
                "target": None if m.target is None else s.cities[m.target].name,
                "votes": dict(m.votes),
                "mine": m.votes.get(me),
                "extra": m.extra.get(me, 0),
            }

        every = cfg.council("sessions.session_turns")
        player = s.players[me]
        objective = cfg.council(f"objectives.{player.objective}") if player.objective else None
        return {
            "member": me in council.members(s, cfg),
            "open": [row(m) for m in c.measures],
            "proposals": [row(m) for m in c.proposals],
            "next_session": (s.turn // every + 1) * every,  # the next turn with a vote
            "chair": c.chair,
            "results": c.results,
            "active": [
                {"name": specs[a["measure"]]["name"], "until": a["until"]} for a in c.active
            ],
            "influence": council.influence(cfg, player),
            "weight": council.weight(cfg, player),
            "extra_cost": cfg.council("sessions.extra_vote_cost"),
            "propose_cost": cfg.council("sessions.propose_cost"),
            "can_propose": {
                k: council.propose_problem(s, cfg, me, k)
                for k in specs
                if specs[k]["kind"] != "chair"
            },
            "measures": {k: {"name": v["name"], "info": v["info"]} for k, v in specs.items()},
            "players": [
                {
                    "id": pid,
                    "name": s.players[pid].name,
                    "leader": s.players[pid].leader.name if s.players[pid].leader else None,
                    "agenda": cfg.council(f"agendas.{s.players[pid].agenda}.name")
                    if s.players[pid].agenda
                    else None,
                    "influence": council.influence(cfg, s.players[pid]),
                    "weight": council.weight(cfg, s.players[pid]),
                }
                for pid in s.player_ids()
            ],
            "objective": None
            if objective is None
            else {
                "name": objective["name"],
                "info": objective["info"],
                "points": objective["points"],
                "met": council.objective_met(s, cfg, me),
            },
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

    # -- the leader (SPEC_M11) ---------------------------------------------------------------

    def career(self) -> dict[str, int]:
        credits = self.state.players[self.human].credits
        return profile.totals(profile.load(self.profile_path), (self.game_id, credits))

    def leader(self) -> dict[str, Any]:
        """The leader screen: the human's leader, family, wardrobe and career, other leaders."""
        s, cfg, me = self.state, self.cfg, self.human
        player = s.players[me]
        lead = player.leader
        if lead is None:
            raise ValueError("no leader")
        traits = cfg.leader("traits.list")
        stones = cfg.leader("milestones.list")
        xp = leader.xp(cfg, player)

        def trait_row(t: str) -> dict[str, Any]:
            return {"id": t, "name": traits[t]["name"], "note": traits[t]["info"]}

        def choice_row(choice: str) -> dict[str, Any]:
            if choice == "trait":
                title = f"Level {cfg.leader('traits.third_trait_level')}: a third trait"
                opts = [trait_row(t) for t in leader.options(cfg, lead, choice)]
            else:
                stone, at = choice.split(":")
                title = f"{stones[stone]['name']} ({pretty_key(stones[stone]['key'])}: {at})"
                opts = [
                    {"id": o, "name": spec["name"], "note": spec["info"]}
                    for o, spec in stones[stone]["options"].items()
                ]
            return {"id": choice, "title": title, "options": opts}

        def person(c) -> dict[str, Any]:
            return {
                "id": c.id,
                "name": c.name,
                "adult": c.adult,
                "hybrid": c.hybrid,
                "stats": c.stats,
                "city": s.cities[c.city].name,
                "growth": c.growth,
                "growth_needed": cfg.t("citizens.growing_up.needed"),
                "seats": c.seats,
            }

        children = [person(s.citizens[str(k)]) for k in lead.children if str(k) in s.citizens]
        candidates = [
            {
                "id": f"recruit:{r.id}",
                "name": r.name,
                "kind": "alien recruit",
                "total": sum(r.scores.values()),
            }
            for r in recruits.recruits_of(s, me)
            if r.seats
        ]
        people = sorted(
            (c for c in citizens.of_player(s, me) if c.adult and not c.kin),
            key=lambda c: (-sum(c.stats.values()), c.id),
        )
        candidates += [
            {
                "id": f"citizen:{c.id}",
                "name": c.name,
                "kind": f"citizen of {s.cities[c.city].name}",
                "total": sum(c.stats.values()),
            }
            for c in people[:12]
        ]
        expecting = None
        if lead.expecting is not None:
            who = leader.partner_of(s, lead.expecting)
            expecting = {"partner": getattr(who, "name", "?"), "due": lead.due}
        career = self.career()
        wardrobe = {
            kind: [
                {
                    "id": item,
                    "name": spec["name"],
                    "unlocked": self.reveal or profile.unlocked(cfg, career, kind, item),
                    "unlock": spec["unlock"],
                }
                for item, spec in cfg.leader(f"wardrobe.{kind}").items()
            ]
            for kind in ("outfits", "accessories")
        }
        start = cfg.leader("start")
        others = [
            {
                "player": pid,
                "continent": s.players[pid].name,
                "name": s.players[pid].leader.name,
                "look": s.players[pid].leader.look,
                "outfit": s.players[pid].leader.outfit,
                "level": s.players[pid].leader.level,
                "age": leader.age(cfg, s, s.players[pid].leader),
            }
            for pid in sorted(player.met)
            if s.players[pid].leader is not None
        ]
        return {
            "name": lead.name,
            "sex": lead.sex,
            "look": lead.look,
            "title": f"President of {player.name}",
            "continent": player.name,
            "age": leader.age(cfg, s, lead),
            "start_age": lead.start_age,
            "level": lead.level,
            "xp": xp,
            "xp_level": leader.xp_for_level(cfg, lead.level),
            "xp_next": leader.xp_for_level(cfg, lead.level + 1),
            "points": leader.points(cfg, lead),
            "skills": {d: lead.skills[d] for d in DOMAINS},
            "military_strength": cfg.t("citizens.military_strength"),
            "traits": [trait_row(t) for t in lead.traits],
            "choices": [choice_row(c) for c in lead.choices],
            "bonuses": [
                {
                    "name": stones[b.split(":")[0]]["options"][b.split(":")[1]]["name"],
                    "note": stones[b.split(":")[0]]["options"][b.split(":")[1]]["info"],
                }
                for b in lead.bonuses
            ],
            "outfit": lead.outfit,
            "accessories": list(lead.accessories),
            "children": children,
            "expecting": expecting,
            "family_block": leader.family_block(s, cfg, me),
            "partners": candidates,
            "birth_turns": cfg.leader("family.birth_turns"),
            "wardrobe": wardrobe,
            "career": career,
            "can_create": s.turn == 0,
            "custom": lead.custom,
            "agenda": player.agenda,
            "catalog": {
                "agendas": [
                    {"id": k, "name": v["name"], "note": v["info"]}
                    for k, v in sorted(cfg.council("agendas").items())
                ],
                "looks": [{"id": k, "sex": v} for k, v in leader.looks(cfg).items()],
                "traits": [trait_row(t) for t in sorted(traits)],
                "skill_points": start["skill_points"],
                "skill_max": start["skill_max"],
                "age_min": start["age_min"],
                "age_max": start["age_max"],
                "trait_count": start["traits"],
            },
            "milestones": [
                {
                    "name": spec["name"],
                    "key": pretty_key(spec["key"]),
                    "have": s.players[me].credits.get(spec["key"], 0),
                    "at": spec["at"],
                }
                for spec in stones.values()
            ],
            "others": others,
        }

    def cities_overview(self) -> dict[str, Any]:
        """Every city of yours on one page (Civ's city list)."""
        s, cfg, me = self.state, self.cfg, self.human
        seen = fog.visible_tiles(s, cfg, me)
        aliens_seen = [u.tile for u in s.units.values() if u.owner == ALIENS and u.tile in seen]
        rows = []
        for c in s.cities:
            if c.owner != me or c.status != ACTIVE:
                continue
            cy = economy.city_yields(s, cfg, c)
            prod = cy.totals["production"]
            head = c.queue[0] if c.queue else None
            turns = None
            if head and not head.startswith("project:") and prod > 0:
                turns = max(
                    0,
                    -(
                        -(economy.item_cost(cfg, head, s.players[me]) - economy.stored(c, head))
                        // prod
                    ),
                )
            surplus = cy.surplus_food
            need = economy.growth_threshold(cfg, c.pop) - c.food_store
            people = citizens.of_city(s, c.id)
            defences = [u for u in s.units_at(c.tile) if cfg.units[u.type].get("fixed")]
            rows.append(
                {
                    "id": c.id,
                    "name": c.name,
                    "capital": c.is_capital,
                    "pop": c.pop,
                    "grows_in": -(-need // surplus) if surplus > 0 else None,
                    "food": surplus,
                    "yields": cy.totals,
                    "connected": c.connected,
                    "building": head,
                    "turns": turns,
                    "hp": c.hp,
                    "max_hp": _city_max_hp(s, cfg, c),
                    "idle": sum(1 for x in people if x.adult and x.tile is None and not x.seats),
                    "children": sum(1 for x in people if not x.adult),
                    "defences": len(defences),
                    "threatened": any(
                        hexgrid.distance(t, c.tile, s.width) <= 3 for t in aliens_seen
                    ),
                }
            )
        return {"cities": rows}

    def units_overview(self) -> dict[str, Any]:
        """Every unit of yours on one page, with where it is and what it is doing."""
        from beacon import promotions

        s, cfg, me = self.state, self.cfg, self.human
        mine = [c for c in s.cities if c.owner == me and c.status == ACTIVE]
        rows = []
        for u in s.sorted_units():
            if u.owner != me:
                continue
            spec = cfg.units[u.type]
            here = s.city_at(u.tile)
            near = min(mine, key=lambda c: hexgrid.distance(c.tile, u.tile, s.width), default=None)
            where = (
                f"in {here.name}"
                if here is not None
                else f"{hexgrid.distance(near.tile, u.tile, s.width)} from {near.name}"
                if near is not None
                else "abroad"
            )
            doing = (
                f"building {u.job.improvement} ({u.job.turns_left})"
                if u.job
                else {"fortify": "fortified", "skip": "waiting", "work": "working"}.get(
                    u.order, "needs orders" if u.moves_left > 0 else "done"
                )
            )
            rows.append(
                {
                    "id": u.id,
                    "type": u.type,
                    "role": "defence" if spec.get("fixed") else spec["role"],
                    "domain": spec["domain"],
                    "count": u.count,
                    "hp": u.hp,
                    "max_hp": cfg.t("combat.unit_max_hp") * u.count,
                    "moves": u.moves_left // cfg.t("movement.scale"),
                    "full_moves": spec["moves"],
                    "xp": u.xp,
                    "promotions": list(u.promotions),
                    "due": promotions.due(cfg, u),
                    "where": where,
                    "abroad": s.tiles[u.tile].continent != me,
                    "doing": doing,
                    "tile": u.tile,
                }
            )
        return {"units": rows}

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
        if u.get("class") and u["class"] not in ("civilian",):
            lines.append(f"Class: {u['class']}")
        for k, pct in (u.get("bonus_vs") or {}).items():
            lines.append(f"+{pct}% against {'cities' if k == 'city' else k + ' units'}")
        if u.get("rough_defence_pct"):
            lines.append(f"+{u['rough_defence_pct']}% defence on hills, forest, jungle or marsh")
        if u.get("open_attack_pct"):
            lines.append(f"+{u['open_attack_pct']}% attacking units on open flat ground")
        if u.get("heal_adjacent"):
            lines.append(
                f"Heals your units on and next to its hex by {u['heal_adjacent']} HP a turn"
            )
            tags.append("military")
        if u.get("can_repair"):
            lines.append("Rebuilds a pillaged improvement in 1 turn")
            tags.append("production")
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


def pretty_key(key: str) -> str:
    return {
        "cities_liberated": "cities freed",
        "kills": "aliens defeated",
        "leader_children": "children grown",
        "shards_claimed": "shards claimed",
    }.get(key, key.replace("_", " "))


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
    if src.startswith("leader:"):
        return f"Leader ({src[7:]})"
    if src.startswith("citizen:") and src.endswith("(council)"):
        return "Citizens on the council"
    if src.startswith("council:"):
        return "Alien council (" + src.split(" ")[-1] + ")" if " " in src else "Alien council"
    if src.startswith("building:"):
        name = src[9:].split(" ")[0].replace("_", " ").capitalize()
        return f"{name} (+%)" if "%" in src else name
    return src.replace("_", " ").capitalize()


EFFECT_TAGS = {
    "growth_pct": ["food"],
    "build_turns": ["production"],
    "unit_cost_pct": ["production", "military"],
    "free_upkeep_per_city": ["gold", "military"],
    "flanking_pct": ["military"],
    "class_defence_pct": ["defence"],
    "ranged_attack_pct": ["military"],
    "hunt_immune": ["sight"],
    "ship_time_pct": ["military"],
    "city_strength": ["defence"],
    "keep_research_on_deficit": ["science"],
    "purchase_pct": ["gold"],
}


def _tech_effects(cfg: Config, t: str) -> dict[str, Any]:
    """What a tech does besides unlocking things: its effects (beacon/techfx.py) and the rules
    that key off it (alliances, recruit rarity, radar, the barrage)."""
    from beacon import techfx

    effects = cfg.techs[t].get("effects") or {}
    lines = techfx.describe(effects)
    tags: set[str] = set()
    for k, v in effects.items():
        if k in ("yield_pct", "city_yields"):
            tags.update(v)
        tags.update(EFFECT_TAGS.get(k, []))
    if t == cfg.t("trade.alliance_tech"):
        lines.append("Lets you form alliances (both sides need it)")
    rarity = cfg.alien("recruits")["rarity_techs"]
    if t in rarity:
        lines.append(f"Beacon recruits up to rarity {rarity.index(t) + 1}")
        tags.add("beacon")
    if t in cfg.t("endgame.radar_techs"):
        lines.append("Reveals every alien city to you")
        tags.add("sight")
    if t == cfg.t("endgame.barrage_tech"):
        lines.append("Stops alien reinforcements and unlocks the world barrage")
        tags.add("military")
    return {"lines": lines, "tags": sorted(tags)}


def _effect_text(effects: dict[str, Any]) -> list[str]:
    from beacon import techfx

    lines = techfx.describe({k: v for k, v in effects.items() if k != "shard"})
    if effects.get("unit_strength_pct"):
        lines.append(f"+{effects['unit_strength_pct']}% strength for all your units")
    return lines
