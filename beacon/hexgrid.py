"""Hex grid maths: pointy-top hexes, odd-row offset storage, cube coordinates for distance.

Tile index = row * width + col. Odd rows are shifted half a hex to the right.

A map may wrap east to west (the world is round, designer 2026-11-15, SPEC_M10): column 0 then
neighbors the last column. Whether a map wraps is a property of the game (GameState.wrap); the
game registers its width here with `set_wrap` when it is created or loaded, so every function
below handles the seam. Wrapping maps need an even width (odd rows are offset).
"""

from __future__ import annotations

from functools import lru_cache

# Neighbour offsets (dcol, drow) for even and odd rows, in a fixed order (E, NE, NW, W, SW, SE).
_EVEN = ((1, 0), (0, -1), (-1, -1), (-1, 0), (-1, 1), (0, 1))
_ODD = ((1, 0), (1, -1), (0, -1), (-1, 0), (0, 1), (1, 1))


def index(col: int, row: int, width: int) -> int:
    return row * width + col


def col_row(i: int, width: int) -> tuple[int, int]:
    return i % width, i // width


def to_cube(col: int, row: int) -> tuple[int, int, int]:
    x = col - (row - (row & 1)) // 2
    z = row
    return x, -x - z, z


_WRAP: set[int] = set()  # widths of maps that wrap east to west


def set_wrap(width: int, on: bool = True) -> None:
    if on:
        if width % 2:
            raise ValueError("a wrapping map needs an even width")
        _WRAP.add(width)
    else:
        _WRAP.discard(width)


def wraps(width: int) -> bool:
    return width in _WRAP


def distance(a: int, b: int, width: int) -> int:
    ac, ar = col_row(a, width)
    bc, br = col_row(b, width)
    ax, ay, az = to_cube(ac, ar)
    best = None
    for shift in (0, width, -width) if width in _WRAP else (0,):
        bx, by, bz = to_cube(bc + shift, br)
        d = max(abs(ax - bx), abs(ay - by), abs(az - bz))
        best = d if best is None else min(best, d)
    return best


@lru_cache(maxsize=8)
def _neighbour_table(width: int, height: int, wrap: bool) -> tuple[tuple[int, ...], ...]:
    table = []
    for i in range(width * height):
        col, row = col_row(i, width)
        offsets = _ODD if row & 1 else _EVEN
        out = []
        for dc, dr in offsets:
            c, r = col + dc, row + dr
            if wrap:
                c %= width
            if 0 <= c < width and 0 <= r < height:
                out.append(index(c, r, width))
        table.append(tuple(out))
    return tuple(table)


def neighbours(i: int, width: int, height: int) -> tuple[int, ...]:
    return _neighbour_table(width, height, width in _WRAP)[i]


def within(i: int, radius: int, width: int, height: int) -> list[int]:
    """All tiles within `radius` of `i` (including `i`), in ascending index order."""
    seen = {i}
    frontier = [i]
    for _ in range(radius):
        nxt = []
        for t in frontier:
            for n in neighbours(t, width, height):
                if n not in seen:
                    seen.add(n)
                    nxt.append(n)
        frontier = nxt
    return sorted(seen)
