"""Story events and exploration finds (docs/SPEC_M9.md, designer 2026-11-14).

An event either happens at once (its outcomes apply) or waits for its player's choice. Outcomes
are data (data/story.yaml): gold, science, a citizen, a unit, a recruit, an alien ambush, a flag.
Exploration finds are events too: the first player unit to reach one fires it.
"""

from __future__ import annotations

from typing import Any

from beacon import citizens, hexgrid, rng, tech
from beacon.config import Config
from beacon.state import ACTIVE, ALIENS, GameState, Site, StoryEvent
from beacon.tiles import is_passable_land
from beacon.units import place_unit

Events = list[dict[str, Any]]


def _nearest_city(state: GameState, pid: str, tile: int | None):
    mine = [c for c in state.cities if c.owner == pid and c.status == ACTIVE]
    if not mine:
        return None
    if tile is None:
        return next((c for c in mine if c.is_capital), mine[0])
    return min(mine, key=lambda c: (hexgrid.distance(c.tile, tile, state.width), c.id))


def apply(
    state: GameState, cfg: Config, pid: str, outcomes: list[dict[str, Any]], tile: int | None
) -> list[str]:
    """Apply outcomes; return what happened, in words, for the event card."""
    from beacon.recruits import make_recruit, rarity_level  # recruits imports a lot

    player = state.players[pid]
    said: list[str] = []
    for o in outcomes:
        if "gold" in o:
            player.gold += o["gold"]
            said.append(f"+{o['gold']} gold")
        if "science" in o:
            player.research_progress += o["science"]
            tech.progress(cfg, player, 0, state.turn)
            said.append(f"+{o['science']} science")
        if "citizen" in o:
            city = _nearest_city(state, pid, tile)
            if city is not None:
                city.pop += o["citizen"]
                citizens.sync(state, cfg, city)
                said.append(f"+{o['citizen']} citizen in {city.name}")
        if "unit" in o:
            at = (
                tile if tile is not None else getattr(_nearest_city(state, pid, None), "tile", None)
            )
            if at is not None and place_unit(state, cfg, o["unit"], pid, at, 2) is not None:
                said.append(f"a new {o['unit'].replace('_', ' ')}")
        if o.get("recruit"):
            rec = make_recruit(state, cfg, pid, max(1, rarity_level(cfg, player.techs)))
            said.append(f"{rec.name} joins you")
        ambush = "alien_unit" in o and tile is not None
        if ambush and place_unit(state, cfg, o["alien_unit"], ALIENS, tile, 1) is not None:
            said.append("an alien attack")
        if "flag" in o and o["flag"] not in player.flags:
            player.flags = sorted([*player.flags, o["flag"]])
    return said


def fire(state: GameState, cfg: Config, pid: str, event_id: str, tile: int | None = None) -> Events:
    """An event happens to a player: at once, or as a choice to make."""
    spec = cfg.events[event_id]
    if spec.get("choices"):
        sid = state.new_id()
        state.story_events[str(sid)] = StoryEvent(
            id=sid, event=event_id, player=pid, turn=state.turn, tile=tile
        )
        return [
            {
                "kind": "story_event",
                "player": pid,
                "event": event_id,
                "story": sid,
                "tile": tile,
                "pending": True,
            }
        ]
    said = apply(state, cfg, pid, spec.get("outcomes") or [], tile)
    return [
        {
            "kind": "story_event",
            "player": pid,
            "event": event_id,
            "tile": tile,
            "pending": False,
            "result": said,
        }
    ]


def choice_problem(state: GameState, cfg: Config, pid: str, story: int, choice: int) -> str | None:
    ev = state.story_events.get(str(story))
    if ev is None or ev.player != pid:
        return "no such event waiting for you"
    if not 0 <= choice < len(cfg.events[ev.event]["choices"]):
        return "no such choice"
    return None


def choose(state: GameState, cfg: Config, pid: str, story: int, choice: int) -> Events:
    ev = state.story_events.pop(str(story))
    spec = cfg.events[ev.event]["choices"][choice]
    said = apply(state, cfg, pid, spec.get("outcomes") or [], ev.tile)
    return [
        {
            "kind": "story_chosen",
            "player": pid,
            "event": ev.event,
            "story": ev.id,
            "choice": choice,
            "label": spec["label"],
            "tile": ev.tile,
            "result": said,
        }
    ]


def pending(state: GameState, pid: str) -> list[StoryEvent]:
    return sorted((e for e in state.story_events.values() if e.player == pid), key=lambda e: e.id)


# -- exploration finds -------------------------------------------------------------------------


def place_sites(state: GameState, cfg: Config) -> None:
    """Hide finds on every continent (seeded): away from cities and from each other."""
    s = cfg.story("sites")
    kinds = sorted(s["weights"])
    city_tiles = [c.tile for c in state.cities]
    for cid in sorted({c.continent for c in state.cities}):
        r = rng.stream(state.seed, "map", "sites", cid)
        options = [
            i
            for i, t in enumerate(state.tiles)
            if t.continent == cid
            and is_passable_land(cfg, t)
            and all(
                hexgrid.distance(i, c, state.width) >= s["min_city_distance"] for c in city_tiles
            )
        ]
        r.shuffle(options)
        chosen: list[int] = []
        for i in options:
            if len(chosen) >= s["per_continent"]:
                break
            if all(hexgrid.distance(i, j, state.width) >= 4 for j in chosen):
                chosen.append(i)
        for i in sorted(chosen):
            kind = rng.weighted_choice(r, kinds, [s["weights"][k] for k in kinds])
            sid = state.new_id()
            state.sites[str(sid)] = Site(id=sid, tile=i, kind=kind)


def site_at(state: GameState, tile: int) -> Site | None:
    return next((s for s in state.sites.values() if s.tile == tile and s.found_by is None), None)


def explore(state: GameState, cfg: Config, pid: str, tile: int) -> Events:
    """A player's land unit reached `tile`: collect any find there."""
    site = site_at(state, tile)
    if site is None:
        return []
    site.found_by = pid
    return [
        {"kind": "site_found", "player": pid, "site": site.id, "find": site.kind, "tile": tile},
        *fire(state, cfg, pid, site.kind, tile),
    ]
