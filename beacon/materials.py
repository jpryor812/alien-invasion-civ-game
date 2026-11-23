"""Materials in the main game (docs/SPEC_M16.md, designer 2026-11-16): timber, stone and iron that
each city gathers from the tiles it works, stores up to a cap, and spends on buildings, walls and
industrial units (paid when the item completes)."""

from __future__ import annotations

from typing import Any

from beacon.config import Config
from beacon.state import City, GameState


def M(cfg: Config, path: str) -> Any:  # noqa: N802 - short accessor
    return cfg.materials(path)


def goods(cfg: Config) -> list[str]:
    return list(M(cfg, "goods.list"))


def caps(cfg: Config, city: City) -> dict[str, int]:
    base = M(cfg, "goods.cap")
    extra = M(cfg, "goods.storehouse_cap") if "storehouse" in city.buildings else 0
    return {g: base[g] + extra for g in goods(cfg)}


def tile_goods(cfg: Config, tile: Any) -> dict[str, int]:
    s = M(cfg, "sources")
    out = dict.fromkeys(goods(cfg), 0)
    for table, key in (
        ("features", tile.feature),
        ("elevations", tile.elevation),
        ("improvements", tile.improvement),
        ("resources", tile.resource if tile.improvement else None),  # improved only (M22)
    ):
        for g, n in (s[table].get(key) or {}).items() if key else []:
            out[g] += n
    return out


def income(state: GameState, cfg: Config, city: City, worked: list[int]) -> dict[str, int]:
    out = dict.fromkeys(goods(cfg), 0)
    for g, n in M(cfg, "sources.centre").items():
        out[g] += n
    for t in [city.tile, *worked]:
        for g, n in tile_goods(cfg, state.tiles[t]).items():
            out[g] += n
    return out


def gather(state: GameState, cfg: Config, city: City, worked: list[int]) -> dict[str, int]:
    got = income(state, cfg, city, worked)
    cap = caps(cfg, city)
    for g in goods(cfg):
        city.stores[g] = min(cap[g], city.stores.get(g, 0) + got[g])
    return got


def building_cost(cfg: Config, b: str) -> dict[str, int]:
    spec = cfg.buildings[b]
    if spec.get("materials") is not None:
        return dict(spec["materials"])
    c = M(cfg, "costs")
    cost = spec["cost"]
    out = {"timber": cost * c["timber_pct"] // 100}
    if cost >= c["stone_from"]:
        out["stone"] = cost * c["stone_pct"] // 100
    tier = cfg.techs[spec["tech"]]["tier"] if spec.get("tech") in cfg.techs else 0
    if tier >= c["iron_tier"]:
        out["iron"] = cost * c["iron_pct"] // 100
    return {g: n for g, n in out.items() if n}


def unit_cost(cfg: Config, u: str) -> dict[str, int]:
    spec = cfg.units[u]
    pct = M(cfg, "costs.units").get(spec.get("class") or "", {})
    return {g: spec["cost"] * p // 100 for g, p in pct.items() if spec["cost"] * p // 100}


def wall_cost(cfg: Config, city: City) -> dict[str, int]:
    out: dict[str, int] = {}
    for _, _, m in city.wall_orders:
        for g, n in M(cfg, f"walls.{m}.cost").items():
            out[g] = out.get(g, 0) + n
    return out


def item_cost(cfg: Config, city: City, item: str) -> dict[str, int]:
    kind, _, ident = item.partition(":")
    if kind == "building":
        return building_cost(cfg, ident)
    if kind == "unit":
        return unit_cost(cfg, ident)
    if item == "walls":
        return wall_cost(cfg, city)
    return {}


def short(city: City, cost: dict[str, int]) -> dict[str, int]:
    return {g: n - city.stores.get(g, 0) for g, n in cost.items() if city.stores.get(g, 0) < n}


def pay(city: City, cost: dict[str, int]) -> None:
    for g, n in cost.items():
        city.stores[g] = city.stores.get(g, 0) - n


def start_stores(cfg: Config, city: City) -> None:
    for g, n in M(cfg, "goods.start").items():
        city.stores[g] = max(city.stores.get(g, 0), n)


def needs_barracks(cfg: Config, unit_type: str) -> bool:
    spec = cfg.units[unit_type]
    return spec["role"] in ("melee", "ranged") and not spec.get("fixed")
