"""The settlement sandbox session (docs/SPEC_M15.md): one city, played turn by turn in the browser.

GET  /api/sandbox            the city as the client draws it
POST /api/sandbox/new        {"seed": int}
POST /api/sandbox/command    {"kind": build | wall | trade | cancel | demolish | end_turn, ...}
"""

from __future__ import annotations

from typing import Any

from beacon import settlement as st
from beacon.config import Config


class Sandbox:
    def __init__(self, cfg: Config, seed: int = 1):
        self.cfg = cfg
        self.new(seed)

    def new(self, seed: int) -> None:
        self.s = st.new(self.cfg, seed)

    def command(self, data: dict[str, Any]) -> dict[str, Any]:
        cfg, s = self.cfg, self.s
        kind = data.get("kind")
        try:
            if kind == "build":
                events = st.build(cfg, s, int(data["hex"]), str(data["what"]))
            elif kind == "wall":
                events = st.wall(cfg, s, int(data["hex"]), int(data["edge"]), str(data["what"]))
            elif kind == "trade":
                events = st.trade(cfg, s, str(data["good"]), int(data["amount"]), str(data["side"]))
            elif kind == "cancel":
                events = st.cancel(cfg, s, int(data["index"]))
            elif kind == "demolish":
                events = st.demolish(cfg, s, int(data["hex"]), str(data["what"]))
            elif kind == "end_turn":
                events = st.end_turn(cfg, s)
            else:
                return {"ok": False, "error": f"unknown command {kind!r}"}
        except (st.SettlementError, KeyError, ValueError, TypeError) as err:
            return {"ok": False, "error": str(err)}
        return {"ok": True, "events": events}

    def view(self) -> dict[str, Any]:
        cfg, s = self.cfg, self.s
        r = cfg.settlement("raids")
        builds = {
            k: {
                "name": v["name"],
                "info": v["info"],
                "cost": v.get("cost", {}),
                "labour": v.get("labour", 0),
                "makes": v.get("makes", {}),
                "needs": v.get("needs"),
                "strength": v.get("strength", 0),
            }
            for k, v in cfg.settlement("buildings").items()
            if not v.get("fixed")
        }
        walls = {
            k: {
                "name": v["name"],
                "cost": v["cost"],
                "labour": v["labour"],
                "strength": v["strength"],
                "hp": v["hp"],
            }
            for k, v in cfg.settlement("walls").items()
        }
        staffed = st.staffed(cfg, s)
        idle = len(st.producers(cfg, s)) - len(staffed)
        hexes = []
        for i, h in enumerate(s.hexes):
            hexes.append(
                {
                    "q": h.q,
                    "r": h.r,
                    "terrain": h.terrain,
                    "resource": h.resource,
                    "slots": h.slots,
                    "buildings": list(h.buildings),
                    "queued": [o.what for o in s.queue if o.kind == "building" and o.hex == i],
                    "outer": st.outer_edges(s, i),
                    "defence": st.defence(cfg, s, i),
                    "can_build": {k: st.build_problem(cfg, s, i, k) for k in builds},
                }
            )
        warn = s.next_raid - s.turn
        return {
            "turn": s.turn,
            "seed": s.seed,
            "goods": dict(s.goods),
            "caps": st.caps(cfg, s),
            "harvest": st.harvest(cfg, s),
            "eats": s.pop * cfg.settlement("people.eats"),
            "gold": s.gold,
            "pop": s.pop,
            "room": st.room(cfg, s),
            "grow_cost": cfg.settlement("people.grow_cost"),
            "labour": st.labour(cfg, s),
            "idle_buildings": idle,
            "strength": st.city_strength(cfg, s),
            "hexes": hexes,
            "walls": {k: dict(w) for k, w in s.walls.items()},
            "queue": [
                {
                    "kind": o.kind,
                    "what": o.what,
                    "hex": o.hex,
                    "edge": o.edge,
                    "labour_left": o.labour_left,
                }
                for o in s.queue
            ],
            "raid": {
                "turns": warn,
                "seen": warn <= r["warning"],
                "hex": s.raid_hex if warn <= r["warning"] else None,
                "strength": st.raid_strength(cfg, s) if warn <= r["warning"] else None,
                "count": s.raids,
            },
            "quotes": st.quotes(cfg, s),
            "goods_info": {g: {"name": cfg.settlement(f"goods.{g}.name")} for g in st.GOODS},
            "buildings": builds,
            "wall_types": walls,
            "log": s.log,
        }
