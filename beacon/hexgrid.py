"""Hex grid maths: pointy-top hexes, odd-row offset storage, cube coordinates for distance.

Tile index = row * width + col. Odd rows are shifted half a hex to the right. No wrapping.
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


def distance(a: int, b: int, width: int) -> int:
    ax, ay, az = to_cube(*col_row(a, width))
    bx, by, bz = to_cube(*col_row(b, width))
    return max(abs(ax - bx), abs(ay - by), abs(az - bz))


@lru_cache(maxsize=4)
def _neighbour_table(width: int, height: int) -> tuple[tuple[int, ...], ...]:
    table = []
    for i in range(width * height):
        col, row = col_row(i, width)
        offsets = _ODD if row & 1 else _EVEN
        out = []
        for dc, dr in offsets:
            c, r = col + dc, row + dr
            if 0 <= c < width and 0 <= r < height:
                out.append(index(c, r, width))
        table.append(tuple(out))
    return tuple(table)


def neighbours(i: int, width: int, height: int) -> tuple[int, ...]:
    return _neighbour_table(width, height)[i]


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
