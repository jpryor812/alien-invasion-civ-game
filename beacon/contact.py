"""Meeting other continents (designer, 2026-11-14).

Nobody knows where the other continents are at the start (and their places are shuffled every
game). Two players meet when one of them sees the other's land or units: from then on they can
trade, ally, give aid, gift recruits and ship troops to each other, and they swap the locations of
their cities. A continent that falls becomes known to everyone, so it can still be rescued.
"""

from __future__ import annotations

from typing import Any

from beacon import fog, hexgrid
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


def meet(state: GameState, a: str, b: str, how: str, share: bool = True) -> Events:
    if met(state, a, b):
        return []
    state.players[a].met = sorted({*state.players[a].met, b})
    state.players[b].met = sorted({*state.players[b].met, a})
    if share:
        _share_cities(state, a, b)
        _share_cities(state, b, a)
    _share_capital(state, a, b)  # each sees the other's capital (designer 2026-11-22, M22)
    _share_capital(state, b, a)
    return [{"turn": state.turn, "kind": "contact_made", "player": a, "other": b, "how": how}]


def _share_capital(state: GameState, to: str, of: str) -> None:
    from beacon.fog import remember

    cap = next(
        (c for c in state.cities if c.owner == of and c.is_capital and c.status == ACTIVE), None
    )
    if cap is None:
        return
    state.players[to].known_cities[str(cap.id)] = CityMemory(
        status=cap.status, owner=cap.owner, pop=cap.pop, turn_seen=state.turn
    )
    remember(state, to, hexgrid.within(cap.tile, 1, state.width, state.height))


def check(state: GameState, cfg: Config, only: str | None = None) -> Events:
    """Players meet when one sees the other's land (its continent's hexes) or units. Off while
    contact is by radio only (designer 2026-11-16)."""
    events: Events = []
    if cfg.t("contact.radio_building"):
        return events
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


def beacon_contact(state: GameState, cfg: Config, pid: str) -> Events:
    """Beacon level 1 (designer 2026-11-15, SPEC_M10): the first beacon reaches every other
    continent, so its player meets everyone without finding their cities."""
    if cfg.t("contact.beacon_tech") not in state.players[pid].techs:
        return []
    if cfg.t("contact.radio_building"):
        return []  # radio only (designer 2026-11-16)
    events: Events = []
    for other in state.player_ids():
        events.extend(meet(state, pid, other, "beacon"))
    return events


def on_air(state: GameState, cfg: Config) -> list[str]:
    """Players with a radio tower in a city they hold (designer 2026-11-16)."""
    building = cfg.t("contact.radio_building")
    return [
        pid
        for pid in state.player_ids()
        if any(
            c.owner == pid and c.status == ACTIVE and building in c.buildings for c in state.cities
        )
    ]


def radio(state: GameState, cfg: Config) -> Events:
    """Everyone on the air meets everyone else on the air; no city locations are shared."""
    ids = on_air(state, cfg)
    events: Events = []
    for a in ids:
        for b in ids:
            if a < b:
                events.extend(meet(state, a, b, "radio", share=False))
    return events


def fallen_known(state: GameState, cfg: Config) -> Events:
    """A fallen continent is known to everyone (so a rescue can be sent). Off while contact is by
    radio only."""
    events: Events = []
    if cfg.t("contact.radio_building"):
        return events
    for pid in state.player_ids():
        if not state.players[pid].fallen:
            continue
        for other in state.player_ids():
            if not met(state, other, pid):
                events.extend(meet(state, other, pid, "distress"))
    return events
