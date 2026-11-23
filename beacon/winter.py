"""The galactic winter (docs/SPEC_M19.md, designer 2026-11-18): alien dust dims the sky for a
year. Crops on worked hexes give part of their food; techs make farms better and hardier. The
start is drawn from a seeded stream, so a seed always plays the same."""

from __future__ import annotations

from typing import Any

from beacon import rng, techfx
from beacon.config import Config
from beacon.state import City, GameState, Player

Events = list[dict[str, Any]]


def W(cfg: Config, key: str) -> Any:  # noqa: N802 - short accessor
    return cfg.t(f"winter.{key}")


def active(state: GameState) -> bool:
    w = state.winter
    return bool(w) and w["from"] <= state.turn < w["to"]


def turns_left(state: GameState) -> int:
    return state.winter["to"] - state.turn if active(state) else 0


def coming_in(state: GameState) -> int | None:
    w = state.winter
    return w["from"] - state.turn if w and state.turn < w["from"] else None


def start_turn(state: GameState, cfg: Config) -> Events:
    """At the start of each turn: end a winter that ran its course, announce one starting, or
    draw whether a new one is coming."""
    w, t = state.winter, state.turn
    if w and t >= w["to"]:
        state.winter, state.last_winter = {}, t
        return [{"turn": t, "kind": "winter_ended"}]
    if w and t == w["from"]:
        return [{"turn": t, "kind": "winter_began", "turns": w["to"] - w["from"]}]
    if w or t < W(cfg, "min_turn"):
        return []
    if state.last_winter >= 0 and t < state.last_winter + W(cfg, "cooldown"):
        return []
    r = rng.stream(state.seed, "events", t, "winter")
    if r.randrange(100) >= W(cfg, "chance_pct"):
        return []
    start = t + W(cfg, "warn")
    state.winter = {"from": start, "to": start + W(cfg, "turns")}
    return [{"turn": t, "kind": "winter_coming", "in": W(cfg, "warn"), "turns": W(cfg, "turns")}]


def keep_pct(cfg: Config, player: Player | None, improvement: str) -> int:
    """Share of an improvement's food a worked hex keeps this winter (100: untouched)."""
    base = cfg.improvements[improvement].get("winter_keep_pct")
    if base is None:
        return 100
    return min(100, base + techfx.total(cfg, player, "winter_keep_pct"))


def food_lines(
    state: GameState, cfg: Config, city: City, worked: list[int], player: Player | None
) -> list[tuple[str, str, int]]:
    """Farm techs on the city's worked hexes, then the winter's loss on them."""
    bonus = techfx.by_key(cfg, player, "improvement_food")
    out: list[tuple[str, str, int]] = []
    extra = loss = 0
    for t in worked:
        imp = state.tiles[t].improvement
        if imp is None:
            continue
        food = cfg.improvements[imp]["yields"].get("food", 0) + bonus.get(imp, 0)
        extra += bonus.get(imp, 0)
        if active(state):
            loss += food * (100 - keep_pct(cfg, player, imp)) // 100
    if extra:
        out.append(("better farming", "food", extra))
    if loss:
        out.append(("galactic winter", "food", -loss))
    return out
