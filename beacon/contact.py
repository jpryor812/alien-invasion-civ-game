"""Meeting other continents (designer, 2026-11-14).

Nobody knows where the other continents are at the start (and their places are shuffled every
game). Two players meet when one of them sees the other's land or units: from then on they can
trade, ally, give aid, gift recruits and ship troops to each other, and they swap the locations of
their cities. A continent that falls becomes known to everyone, so it can still be rescued.
"""

from __future__ import annotations

from typing import Any

from beacon import fog
from beacon.config import Config
from beacon.state import ACTIVE, CityMemory, GameState

Events = list[dict[str, Any]]


def met(state: GameState, a: str, b: str) -> bool:
    return a == b or b in state.players[a].met


def _share_cities(state: GameState, to: str, of: str) -> None:
    player = state.players[to]
    for city in state.cities:
        if city.continent != of:
            continue
        shareable = city.status == ACTIVE or state.players[of].fallen
        if shareable and str(city.id) not in player.known_cities:
            player.known_cities[str(city.id)] = CityMemory(
                status=city.status, owner=city.owner, pop=city.pop, turn_seen=state.turn
            )


def meet(state: GameState, a: str, b: str, how: str) -> Events:
    if met(state, a, b):
        return []
    state.players[a].met = sorted({*state.players[a].met, b})
    state.players[b].met = sorted({*state.players[b].met, a})
    _share_cities(state, a, b)
    _share_cities(state, b, a)
    return [{"turn": state.turn, "kind": "contact_made", "player": a, "other": b, "how": how}]


def check(state: GameState, cfg: Config, only: str | None = None) -> Events:
    """Players meet when one sees the other's land (its continent's hexes) or units."""
    events: Events = []
    ids = state.player_ids()
    seers = [only] if only is not None else ids
    units_by_owner: dict[str, set[int]] = {}
    for u in state.units.values():
        if u.owner in state.players:
            units_by_owner.setdefault(u.owner, set()).add(u.tile)
    for a in seers:
        unmet = [b for b in ids if not met(state, a, b)]
        if not unmet:
            continue
        seen = fog.visible_tiles(state, cfg, a)
        for b in unmet:
            sees_land = any(state.tiles[t].continent == b for t in seen)
            if sees_land or seen & units_by_owner.get(b, set()):
                events.extend(meet(state, a, b, "sighted"))
    return events


def fallen_known(state: GameState) -> Events:
    """A fallen continent is known to everyone (so a rescue can be sent)."""
    events: Events = []
    for pid in state.player_ids():
        if not state.players[pid].fallen:
            continue
        for other in state.player_ids():
            if not met(state, other, pid):
                events.extend(meet(state, other, pid, "distress"))
    return events
