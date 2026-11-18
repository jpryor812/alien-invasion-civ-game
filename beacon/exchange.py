"""The Galactic Exchange (docs/SPEC_M17.md, from the M15 sandbox): neutral alien traders who buy
and sell timber, stone and iron for gold. One price index per good, shared by every player, moves
with trade and drifts back toward 100. No randomness."""

from __future__ import annotations

from typing import Any

from beacon import materials
from beacon.config import Config
from beacon.state import City, GameState


def X(cfg: Config, path: str) -> Any:  # noqa: N802 - short accessor
    return cfg.materials(f"exchange.{path}")


def index(state: GameState, good: str) -> int:
    return state.exchange.get(good, 100)


def quotes(state: GameState, cfg: Config, pid: str | None = None) -> dict[str, dict[str, int]]:
    """Gold per unit: what the Exchange pays (sell) and asks (buy) now. A Merchant's agenda
    (exchange_pct) gets better prices both ways."""
    from beacon import techfx

    bonus = techfx.total(cfg, state.players.get(pid or ""), "exchange_pct")
    out = {}
    for g in materials.goods(cfg):
        p = X(cfg, "base")[g] * index(state, g)
        out[g] = {
            "sell": max(1, p * X(cfg, "sell_pct") * (100 + bonus) // 1000000),
            "buy": -(-p * X(cfg, "buy_pct") * (100 - bonus) // 1000000),
            "index": index(state, g),
        }
    return out


def trade_problem(
    state: GameState, cfg: Config, city: City, good: str, amount: int, side: str
) -> str | None:
    if good not in materials.goods(cfg):
        return f"unknown good {good!r}"
    if amount <= 0:
        return "trade a positive amount"
    q = quotes(state, cfg, city.owner)[good]
    if side == "sell":
        have = city.stores.get(good, 0)
        return None if have >= amount else f"only {have} {good} to sell"
    if side == "buy":
        gold = state.players[city.owner or ""].gold
        if gold < q["buy"] * amount:
            return f"needs {q['buy'] * amount} gold; treasury has {gold}"
        room = materials.caps(cfg, city)[good] - city.stores.get(good, 0)
        return None if amount <= room else f"room for only {max(0, room)} more {good}"
    return "side is buy or sell"


def trade(
    state: GameState, cfg: Config, city: City, good: str, amount: int, side: str
) -> list[dict[str, Any]]:
    q = quotes(state, cfg, city.owner)[good]
    player = state.players[city.owner or ""]
    step = X(cfg, "step_pct") * (amount // 10)
    if side == "sell":
        city.stores[good] -= amount
        gold = q["sell"] * amount
        player.gold += gold
        state.exchange[good] = max(X(cfg, "min_pct"), index(state, good) - step)
    else:
        gold = q["buy"] * amount
        player.gold -= gold
        city.stores[good] = city.stores.get(good, 0) + amount
        state.exchange[good] = min(X(cfg, "max_pct"), index(state, good) + step)
    return [
        {
            "kind": "traded",
            "city": city.id,
            "side": side,
            "good": good,
            "amount": amount,
            "gold": gold,
        }
    ]


def drift(state: GameState, cfg: Config) -> None:
    """Once a turn: each index moves revert_pct back toward 100."""
    r = X(cfg, "revert_pct")
    for g in list(state.exchange):
        v = state.exchange[g]
        state.exchange[g] = v - min(r, v - 100) if v > 100 else v + min(r, 100 - v)
        if state.exchange[g] == 100:
            del state.exchange[g]
