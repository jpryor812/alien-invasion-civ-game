"""Unit movement: step costs, pathfinding over turns, moving, merging and splitting.

Rules (docs/SPEC_M0-M3.md, M3):
- Roads and railways cut cost only when both hexes of a step have them.
- A unit with any moves left may always enter one more hex (it spends everything it has).
- Friendly units can be passed through; a unit must end on a hex where it may stand.
- Units never path through hostile units they can see; if the next hex holds a hostile unit they
  could not see, the move stops there.
"""

from __future__ import annotations

import heapq
from typing import Any

from beacon import fog, hexgrid
from beacon.config import Config
from beacon.state import ALIENS, DORMANT, GameState, Unit
from beacon.tiles import move_cost
from beacon.units import (
    can_stand,
    city_blocks,
    domain_allows,
    full_moves,
    hostile,
    is_civilian,
    occupancy,
    remove_unit,
)

Events = list[dict[str, Any]]


def step_cost(state: GameState, cfg: Config, a: int, b: int) -> int:
    ta, tb = state.tiles[a], state.tiles[b]
    if ta.route and tb.route:
        if ta.route == "railway" and tb.route == "railway":
            return cfg.improvements["railway"]["move_cost"]
        return cfg.improvements["road"]["move_cost"]
    return move_cost(cfg, tb)


def _blocked(
    state: GameState,
    cfg: Config,
    unit: Unit,
    tile: int,
    occ: dict[int, list[Unit]],
    seen: set[int] | None,
) -> bool:
    """Can the unit not pass through this hex at all?"""
    if not domain_allows(state, cfg, unit.type, unit.owner, tile):
        return True
    if city_blocks(state, unit.owner, tile):
        return True
    for other in occ.get(tile, []):
        if hostile(other.owner, unit.owner) and (seen is None or tile in seen):
            return True
    return False


def find_path(
    state: GameState,
    cfg: Config,
    unit: Unit,
    target: int,
    *,
    occ: dict[int, list[Unit]] | None = None,
    seen: set[int] | None = None,
    allow_occupied_target: bool = False,
    max_turns: int | None = None,
) -> tuple[list[int], int] | None:
    """Cheapest path to `target` as (tiles from start to target, turns needed beyond this one).

    Cost is (turns, sub-points used in the final turn). `seen` limits hostile blocking to visible
    hexes (None: block on every hostile, the engine's own view).
    """
    occ = occupancy(state) if occ is None else occ
    if target == unit.tile:
        return [unit.tile], 0
    full = full_moves(cfg, unit.type)
    if full <= 0:
        return None
    if not allow_occupied_target and not can_stand(
        state, cfg, occ, unit.type, unit.owner, target, ignore=unit.id
    ):
        return None
    w, h = state.width, state.height
    start_used = full - unit.moves_left
    # With no moves left, the path starts next turn.
    start = (1, 0) if start_used >= full else (0, start_used)
    best: dict[int, tuple[int, int]] = {unit.tile: start}
    prev: dict[int, int] = {}
    heap = [(start[0], start[1], unit.tile)]
    while heap:
        turns, used, tile = heapq.heappop(heap)
        if (turns, used) > best.get(tile, (turns, used)):
            continue
        if tile == target:
            path = [tile]
            while tile != unit.tile:
                tile = prev[tile]
                path.append(tile)
            return path[::-1], turns
        if max_turns is not None and turns > max_turns:
            continue
        for nxt in hexgrid.neighbours(tile, w, h):
            if nxt != target and _blocked(state, cfg, unit, nxt, occ, seen):
                continue
            if nxt == target and not domain_allows(state, cfg, unit.type, unit.owner, nxt):
                continue
            cost = step_cost(state, cfg, tile, nxt)
            cand = (turns + 1, min(full, cost)) if used >= full else (turns, min(full, used + cost))
            if cand < best.get(nxt, (cand[0] + 1, 0)):
                best[nxt] = cand
                prev[nxt] = tile
                heapq.heappush(heap, (cand[0], cand[1], nxt))
    return None


def reachable_this_turn(state: GameState, cfg: Config, unit: Unit) -> list[int]:
    """Hexes the unit could end its move on this turn (excluding where it stands)."""
    if unit.moves_left <= 0 or unit.job is not None:
        return []
    occ = occupancy(state)
    seen = fog.visible_tiles(state, cfg, unit.owner) if unit.owner != ALIENS else None
    w, h = state.width, state.height
    best = {unit.tile: unit.moves_left}
    heap = [(-unit.moves_left, unit.tile)]
    while heap:
        neg_left, tile = heapq.heappop(heap)
        left = -neg_left
        if left < best.get(tile, left) or left <= 0:
            continue
        for nxt in hexgrid.neighbours(tile, w, h):
            if _blocked(state, cfg, unit, nxt, occ, seen):
                continue
            remaining = max(0, left - step_cost(state, cfg, tile, nxt))
            if remaining > best.get(nxt, -1):
                best[nxt] = remaining
                heapq.heappush(heap, (-remaining, nxt))
    return sorted(
        t
        for t in best
        if t != unit.tile and can_stand(state, cfg, occ, unit.type, unit.owner, t, ignore=unit.id)
    )


def _enter(state: GameState, cfg: Config, unit: Unit, tile: int) -> Events:
    """Side effects of a unit entering a hex: fog, reclaiming dormant cities."""
    events: Events = []
    unit.tile = tile
    if unit.owner in state.players:
        fog.reveal_around(
            state, cfg, unit.owner, tile, fog.unit_vision(state, cfg, unit.type, tile)
        )
    city = state.city_at(tile)
    if (
        city is not None
        and city.status == DORMANT
        and unit.owner in state.players
        and not is_civilian(cfg, unit.type)
    ):
        from beacon.liberation import reclaim

        events.extend(reclaim(state, cfg, city, unit.owner))
    return events


def move_along(state: GameState, cfg: Config, unit: Unit, path: list[int]) -> Events:
    """Walk a path as far as this turn's moves allow, stopping before unseen hostiles and on the
    last hex where the unit may stand."""
    events: Events = []
    occ = occupancy(state)
    walked = [unit.tile]
    moves = unit.moves_left
    for nxt in path[1:]:
        if moves <= 0:
            break
        if any(hostile(o.owner, unit.owner) for o in occ.get(nxt, [])):
            events.append({"kind": "move_interrupted", "unit": unit.id, "tile": nxt})
            if unit.owner in state.players:
                fog.reveal_around(state, cfg, unit.owner, nxt, 0)
            break
        moves = max(0, moves - step_cost(state, cfg, walked[-1], nxt))
        walked.append(nxt)
    # back up to the last hex the unit may end on
    while len(walked) > 1 and not can_stand(
        state, cfg, occ, unit.type, unit.owner, walked[-1], ignore=unit.id
    ):
        walked.pop()
    if len(walked) == 1:
        return events
    origin = unit.tile
    for tile in walked[1:]:
        events.extend(_enter(state, cfg, unit, tile))
    unit.moves_left = moves
    unit.job = None
    unit.fortified = False
    unit.acted = True
    if unit.order in ("fortify", "work"):
        unit.order = "none"
    events.insert(0, {"kind": "unit_moved", "unit": unit.id, "from": origin, "to": unit.tile})
    return events


# -- stacks ------------------------------------------------------------------------------------


def merge_problem(state: GameState, cfg: Config, unit: Unit, into: Unit) -> str | None:
    if unit.id == into.id:
        return "a unit cannot merge with itself"
    if unit.owner != into.owner or unit.type != into.type:
        return "only two units of the same type and owner can merge"
    if is_civilian(cfg, unit.type):
        return "civilians do not stack"
    if unit.count != 1 or into.count != 1:
        return f"stacks hold at most {cfg.t('combat.stack_size')} units"
    if unit.hp + into.hp < cfg.t("combat.unit_max_hp"):
        return "combined HP too low to form a stack"
    if unit.moves_left <= 0:
        return "no moves left"
    return None


def merge(state: GameState, cfg: Config, unit: Unit, into: Unit, path: list[int]) -> Events:
    """`unit` walks `path` (ending on `into`'s hex) and joins it."""
    moves = unit.moves_left
    for a, b in zip(path, path[1:], strict=False):
        moves = max(0, moves - step_cost(state, cfg, a, b))
    events: Events = []
    for tile in path[1:-1]:
        events.extend(_enter(state, cfg, unit, tile))
    into.count = 2
    into.hp += unit.hp
    into.moves_left = min(into.moves_left, moves)
    into.attacks_left = min(into.attacks_left, unit.attacks_left)
    into.fortified = False
    into.acted = True
    into.job = None
    if into.order != "skip":
        into.order = "none"
    remove_unit(state, unit)
    events.append({"kind": "units_merged", "unit": into.id, "absorbed": unit.id, "hp": into.hp})
    return events


def split_problem(state: GameState, cfg: Config, unit: Unit, target: int) -> str | None:
    if unit.count < 2:
        return "only a stack can split"
    if unit.hp <= cfg.t("combat.unit_max_hp"):
        return "the stack has too little HP to split"
    if unit.moves_left <= 0:
        return "no moves left"
    if target not in hexgrid.neighbours(unit.tile, state.width, state.height):
        return "split target must be adjacent"
    occ = occupancy(state)
    if not can_stand(state, cfg, occ, unit.type, unit.owner, target):
        return "cannot move onto that hex"
    return None


def split(state: GameState, cfg: Config, unit: Unit, target: int) -> Events:
    """The full-HP member moves to `target`; the remainder stays (designer rule)."""
    from beacon.units import create_unit

    full_hp = cfg.t("combat.unit_max_hp")
    mover = create_unit(state, cfg, unit.type, unit.owner, unit.tile)
    mover.hp = full_hp
    mover.moves_left = unit.moves_left
    mover.attacks_left = unit.attacks_left
    unit.count = 1
    unit.hp -= full_hp
    unit.fortified = False
    events = [{"kind": "unit_split", "unit": unit.id, "new_unit": mover.id, "stayer_hp": unit.hp}]
    events.extend(move_along(state, cfg, mover, [unit.tile, target]))
    return events
