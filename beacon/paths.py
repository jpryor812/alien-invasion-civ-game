"""Generic deterministic shortest paths on the tile graph."""

from __future__ import annotations

import heapq
from collections.abc import Callable, Iterable


def shortest_path(
    start: int,
    goals: set[int],
    neighbours: Callable[[int], Iterable[int]],
    step_cost: Callable[[int, int], int | None],
) -> list[int] | None:
    """Cheapest path from `start` to any tile in `goals` (inclusive of both ends).

    `step_cost(a, b)` returns the cost of stepping a -> b, or None if the step is not allowed.
    Ties are broken by tile index, so the result is deterministic.
    """
    if start in goals:
        return [start]
    best = {start: 0}
    prev: dict[int, int] = {}
    heap = [(0, start)]
    while heap:
        cost, tile = heapq.heappop(heap)
        if cost > best.get(tile, cost):
            continue
        if tile in goals:
            path = [tile]
            while tile != start:
                tile = prev[tile]
                path.append(tile)
            return path[::-1]
        for nxt in neighbours(tile):
            step = step_cost(tile, nxt)
            if step is None:
                continue
            new = cost + step
            if new < best.get(nxt, new + 1):
                best[nxt] = new
                prev[nxt] = tile
                heapq.heappush(heap, (new, nxt))
    return None


def reachable(
    start: int,
    neighbours: Callable[[int], Iterable[int]],
    allowed: Callable[[int], bool],
) -> set[int]:
    """All tiles connected to `start` through tiles where `allowed` is true."""
    seen = {start}
    stack = [start]
    while stack:
        tile = stack.pop()
        for nxt in neighbours(tile):
            if nxt not in seen and allowed(nxt):
                seen.add(nxt)
                stack.append(nxt)
    return seen
