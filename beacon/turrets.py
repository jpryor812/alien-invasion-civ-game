"""Turrets on improved tiles (designer, 2026-11-14).

Engineers can build a turret on an improved tile. At the end of each turn it fires at the weakest
enemy next to it. Aliens must destroy it before they can pillage the tile, so a turret buys time
to bring troops. Turrets are upgraded with gold: each level adds strength and HP.
"""

from __future__ import annotations

from typing import Any

from beacon import combat, fog, hexgrid
from beacon.config import Config
from beacon.state import GameState, Tile, Unit
from beacon.units import hostile

Events = list[dict[str, Any]]


def spec(cfg: Config) -> dict[str, Any]:
    return cfg.t("turrets")


def strength(cfg: Config, level: int) -> int:
    """Turret strength in hundredths (as unit strengths are)."""
    s = spec(cfg)
    return (s["strength_base"] + s["strength_per_level"] * (level - 1)) * 100


def max_hp(cfg: Config, level: int) -> int:
    s = spec(cfg)
    return s["hp_base"] + s["hp_per_level"] * (level - 1)


def build(tile: Tile, cfg: Config) -> None:
    tile.turret = 1
    tile.turret_hp = max_hp(cfg, 1)


def upgrade_cost(cfg: Config, tile: Tile) -> int | None:
    s = spec(cfg)
    if tile.turret <= 0 or tile.turret >= s["max_level"]:
        return None
    return s["upgrade_cost_base"] + s["upgrade_cost_step"] * (tile.turret - 1)


def upgrade_problem(state: GameState, cfg: Config, pid: str, i: int) -> str | None:
    if not 0 <= i < len(state.tiles):
        return f"no tile {i}"
    tile = state.tiles[i]
    if tile.turret <= 0 or tile.built_by != pid:
        return "no turret of yours there"
    cost = upgrade_cost(cfg, tile)
    if cost is None:
        return "the turret is at its top level"
    if state.players[pid].gold < cost:
        return f"needs {cost} gold"
    return None


def upgrade(state: GameState, cfg: Config, pid: str, i: int) -> Events:
    tile = state.tiles[i]
    cost = upgrade_cost(cfg, tile)
    assert cost is not None
    state.players[pid].gold -= cost
    tile.turret += 1
    tile.turret_hp = max_hp(cfg, tile.turret)  # an upgrade also repairs it
    return [{"kind": "turret_upgraded", "tile": i, "level": tile.turret, "gold": cost}]


def fire(state: GameState, cfg: Config) -> Events:
    """Every turret shoots the weakest visible enemy next to it (ties by hex)."""
    events: Events = []
    for i, tile in enumerate(state.tiles):
        if tile.turret <= 0 or tile.built_by not in state.players:
            continue
        pid = tile.built_by
        seen = fog.visible_tiles(state, cfg, pid)
        targets: list[tuple[int, int, Unit]] = []
        for n in hexgrid.within(i, spec(cfg)["range"], state.width, state.height):
            if n == i or n not in seen:
                continue
            for u in state.units_at(n):
                if hostile(u.owner, pid) and cfg.units[u.type]["role"] != "civilian":
                    targets.append((u.hp, n, u))
        if not targets:
            continue
        _, n, victim = min(targets, key=lambda x: (x[0], x[1]))
        dfn = combat.unit_strength(state, cfg, victim, ranged=False, defending=True).total
        dmg = combat._roll(
            state, cfg, combat.raw_damage(cfg, dfn, strength(cfg, tile.turret)), "defender"
        )
        state.combat_seq += 1
        events.append(
            {
                "kind": "turret_fired",
                "tile": i,
                "target": n,
                "defender": victim.id,
                "damage_to_defender": dmg,
                "player": pid,
            }
        )
        events.extend(combat.damage_unit(state, cfg, victim, dmg, pid))
    return events


def assault(state: GameState, cfg: Config, unit: Unit, i: int) -> Events:
    """An alien unit next to a turret attacks it; at 0 HP the turret is destroyed."""
    tile = state.tiles[i]
    att = combat.unit_strength(state, cfg, unit, ranged=False, defending=False).total
    dmg = combat._roll(
        state, cfg, combat.raw_damage(cfg, strength(cfg, tile.turret), att), "defender"
    )
    state.combat_seq += 1
    unit.attacks_left -= 1
    unit.moves_left = 0
    unit.acted = True
    tile.turret_hp -= dmg
    events: Events = [
        {
            "kind": "turret_attacked",
            "tile": i,
            "attacker": unit.id,
            "damage": dmg,
            "owner": tile.built_by,
        }
    ]
    if tile.turret_hp <= 0:
        tile.turret, tile.turret_hp = 0, 0
        events.append({"kind": "turret_destroyed", "tile": i, "owner": tile.built_by})
    return events
