"""Convoys (designer 2026-11-15, SPEC_M10 section 3).

A city can send a share of its production or of its spare food to another city of its owner or of
an ally, if roads, railways or city tiles join the two. Each turn the share leaves the sender and
arrives at the receiver at its next city turn. A cut route pauses the convoy until it is joined.
"""

from __future__ import annotations

from beacon import hexgrid
from beacon.config import Config
from beacon.paths import reachable
from beacon.state import ACTIVE, City, GameState

KINDS = ("production", "food")


def joined(state: GameState, a: City, b: City) -> bool:
    """True if a road, railway or city tiles lead from city `a` to city `b`."""
    w, h = state.width, state.height
    city_tiles = {c.tile for c in state.cities if c.status == ACTIVE}
    net = reachable(
        a.tile,
        lambda i: hexgrid.neighbours(i, w, h),
        lambda i: i in city_tiles or state.tiles[i].route is not None,
    )
    return b.tile in net


def friendly(state: GameState, a: City, b: City) -> bool:
    from beacon.diplomacy import allied  # diplomacy imports economy, which imports this

    return a.owner is not None and (a.owner == b.owner or allied(state, a.owner, b.owner or ""))


def problem(state: GameState, cfg: Config, city: City, target: int, kind: str, pct: int) -> str:
    """Why this convoy cannot be set up ("" if it can)."""
    if kind not in KINDS:
        return f"a convoy carries {' or '.join(KINDS)}"
    if pct not in cfg.t("convoys.shares_pct"):
        return f"the share must be one of {cfg.t('convoys.shares_pct')}%"
    if not 0 <= target < len(state.cities) or target == city.id:
        return "no such city to send to"
    other = state.cities[target]
    if other.status != ACTIVE or not friendly(state, city, other):
        return f"{other.name} is not a friendly city"
    if not joined(state, city, other):
        return f"no road joins {city.name} to {other.name}"
    return ""


def send(state: GameState, city: City, production: int, food_surplus: int) -> tuple[int, int]:
    """Take this turn's share for the city's convoy, if it runs. Returns what the sender keeps
    (production, food surplus) and adds the share to the receiver's incoming goods."""
    c = city.convoy
    if not c:
        return production, food_surplus
    other = state.cities[c["to"]]
    if other.status != ACTIVE or not friendly(state, city, other) or not joined(state, city, other):
        return production, food_surplus  # paused until the route is whole again
    if c["kind"] == "production":
        share = production * c["pct"] // 100
        production -= share
    else:
        share = max(0, food_surplus) * c["pct"] // 100
        food_surplus -= share
    if share:
        other.incoming[c["kind"]] = other.incoming.get(c["kind"], 0) + share
    return production, food_surplus
