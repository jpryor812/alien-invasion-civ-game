"""Combat, Civ V style (designer decision 2026-11-13).

One attack per command. Effective strength = base x stack size x (100 + modifiers)% x wound
factor. Damage dealt to a side with strength S by an opponent with strength O is

    base_damage * (S + O)^2 / (4 * S^2)     (equal strengths: base_damage)

times a seeded roll in 100 +/- variance percent, clamped. Ranged attacks take no retaliation and
cannot capture. `preview_attack` and `attack` share every calculation, so the preview at zero
variance equals the result.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from beacon import hexgrid, rng
from beacon.cities import alien_effect
from beacon.config import Config
from beacon.liberation import credit, liberate, overrun
from beacon.recruits import council_lines, traitor_lines
from beacon.state import ALIENS, OVERRUN, City, GameState, Unit
from beacon.tiles import defense_lines, is_passable_land, is_water
from beacon.units import hostile, is_civilian, max_hp, occupancy, remove_unit

Events = list[dict[str, Any]]


@dataclass
class Strength:
    """Effective strength in hundredths, with the lines that explain it."""

    total: int
    lines: list[dict[str, Any]] = field(default_factory=list)


def _wound_pct(cfg: Config, hp: int, full: int) -> int:
    floor = cfg.t("combat.wound_floor_pct")
    return floor + (100 - floor) * max(0, hp) // full


def unit_strength(
    state: GameState,
    cfg: Config,
    unit: Unit,
    *,
    ranged: bool,
    defending: bool,
    target: int | None = None,
) -> Strength:
    spec = cfg.units[unit.type]
    base = spec["ranged_strength"] if ranged else spec["strength"]
    lines: list[dict[str, Any]] = [{"source": "base", "kind": "base", "value": base}]
    if unit.count > 1:
        lines.append({"source": "stack", "kind": "multiplier", "value": unit.count})
    mods: list[tuple[str, int]] = []
    if defending:
        mods.extend(defense_lines(cfg, state.tiles[unit.tile]))
        if unit.fortified:
            mods.append(("fortified", cfg.t("combat.fortify_pct")))
    if unit.owner in state.players:
        mods.extend(council_lines(state, unit.owner, "military"))
    if not defending and not ranged and target is not None:
        flankers = 0
        for n in hexgrid.neighbours(target, state.width, state.height):
            for other in state.units_at(n):
                if (
                    other.id != unit.id
                    and not hostile(other.owner, unit.owner)
                    and not is_civilian(cfg, other.type)
                ):
                    flankers += 1
        if flankers:
            mods.append((f"flanking x{flankers}", flankers * cfg.t("combat.flanking_pct")))
    for source, pct in mods:
        lines.append({"source": source, "kind": "pct", "value": pct})
    wound = _wound_pct(cfg, unit.hp, max_hp(cfg, unit))
    if wound != 100:
        lines.append({"source": "wounded", "kind": "pct_of", "value": wound})
    total = base * 100 * unit.count * (100 + sum(p for _, p in mods)) // 100 * wound // 100
    return Strength(total=max(1, total) if base > 0 else 0, lines=lines)


def garrison(state: GameState, cfg: Config, city: City) -> Unit | None:
    for unit in state.units_at(city.tile):
        if not is_civilian(cfg, unit.type) and unit.owner == city.owner:
            return unit
    return None


def garrisons(state: GameState, cfg: Config, city: City) -> list[Unit]:
    return [
        u
        for u in state.units_at(city.tile)
        if not is_civilian(cfg, u.type) and u.owner == city.owner
    ]


def city_strength(state: GameState, cfg: Config, city: City) -> Strength:
    lines = [
        {"source": "city_base", "kind": "base", "value": cfg.t("cities.base_strength")},
        {
            "source": "population",
            "kind": "base",
            "value": city.pop * cfg.t("cities.strength_per_pop"),
        },
    ]
    for b in city.buildings:
        if cfg.buildings[b].get("city_strength"):
            lines.append(
                {
                    "source": f"building:{b}",
                    "kind": "base",
                    "value": cfg.buildings[b]["city_strength"],
                }
            )
    pcts: list[tuple[str, int]] = []
    if city.owner == ALIENS:
        lines.append(
            {
                "source": "alien_fortress",
                "kind": "base",
                "value": cfg.alien("fortress.base_strength"),
            }
        )
        walls = alien_effect(state, cfg, "city_strength")
        if walls:
            lines.append({"source": "alien_walls", "kind": "base", "value": walls})
        pcts.append(("alien_hardening", hardening_pct(state, cfg)))
        pcts.extend(traitor_lines(state, city.id))  # betrayed recruits lend their military score
    total = sum(line["value"] for line in lines) * 100
    pcts = [(source, pct) for source, pct in pcts if pct]
    for source, pct in pcts:
        lines.append({"source": source, "kind": "pct", "value": pct})
    if pcts:
        total = total * (100 + sum(pct for _, pct in pcts)) // 100
    for guard in garrisons(state, cfg, city):  # a field unit and a city defence unit both help
        share = unit_strength(state, cfg, guard, ranged=False, defending=True).total
        extra = share * cfg.t("cities.garrison_share_pct") // 100
        lines.append(
            {"source": f"garrison:{guard.type}", "kind": "flat_hundredths", "value": extra}
        )
        total += extra
    return Strength(total=total, lines=lines)


def hardening_pct(state: GameState, cfg: Config) -> int:
    """Alien cities harden as they lose cities and as time passes (DESIGN.md 9)."""
    f = cfg.alien("fortress")
    held = sum(1 for c in state.cities if c.status == OVERRUN)
    start = state.aliens.start_cities
    lost_share = max(0, start - held) * 100 // start if start else 0
    pct = (
        lost_share * f["per_lost_share_pct"] // 100
        + state.turn // f["interval_turns"] * f["per_interval_pct"]
    )
    return min(f["cap_pct"], pct)


def raw_damage(cfg: Config, own: int, other: int) -> int:
    """Damage taken by a side of strength `own` from a side of strength `other` (both
    hundredths), before variance and clamping."""
    own = max(1, own)
    return cfg.t("combat.base_damage") * (own + other) ** 2 // (4 * own * own)


def _clamp(cfg: Config, dmg: int) -> int:
    return max(cfg.t("combat.min_damage"), min(cfg.t("combat.max_damage"), dmg))


def _range(cfg: Config, raw: int) -> dict[str, int]:
    var = cfg.t("combat.variance_pct")
    return {
        "expected": _clamp(cfg, raw),
        "min": _clamp(cfg, raw * (100 - var) // 100),
        "max": _clamp(cfg, raw * (100 + var) // 100),
    }


# -- validity ----------------------------------------------------------------------------------


def is_ranged(cfg: Config, unit: Unit) -> bool:
    return cfg.units[unit.type]["role"] == "ranged"


def defender_at(
    state: GameState, cfg: Config, attacker_owner: str, tile: int
) -> City | Unit | None:
    """What an attack on `tile` hits: a hostile city first, else a hostile military unit."""
    city = state.city_at(tile)
    if city is not None and city.owner is not None and hostile(city.owner, attacker_owner):
        return city
    for unit in state.units_at(tile):
        if hostile(unit.owner, attacker_owner) and not is_civilian(cfg, unit.type):
            return unit
    return None


def capturable(state: GameState, cfg: Config, attacker_owner: str, tile: int) -> bool:
    """Only hostile civilians stand here: a melee unit can walk in and destroy them."""
    here = state.units_at(tile)
    return bool(here) and all(
        hostile(u.owner, attacker_owner) and is_civilian(cfg, u.type) for u in here
    )


def attack_problem(
    state: GameState, cfg: Config, unit: Unit, target: int, seen: set[int] | None = None
) -> str | None:
    spec = cfg.units[unit.type]
    if spec["role"] == "civilian":
        return "civilians cannot attack"
    if spec.get("no_attack"):
        return "this unit only defends its city"
    if unit.attacks_left <= 0 or (unit.moves_left <= 0 and not spec.get("fixed")):
        return "no attack left this turn"
    if seen is not None and target not in seen:
        return "target is not visible"
    defender = defender_at(state, cfg, unit.owner, target)
    dist = hexgrid.distance(unit.tile, target, state.width)
    if defender is None:
        if (
            capturable(state, cfg, unit.owner, target)
            and not is_ranged(cfg, unit)
            and dist == 1
            and spec["domain"] == "land"
            and is_passable_land(cfg, state.tiles[target])
        ):
            return None
        return "nothing hostile to attack there"
    if is_ranged(cfg, unit):
        if dist > spec["range"]:
            return "target out of range"
        return None
    if dist != 1:
        return "melee targets must be adjacent"
    target_tile = state.tiles[target]
    if spec["domain"] == "land":
        if not is_passable_land(cfg, target_tile):
            return "land units cannot attack onto water or mountains"
    elif not is_water(cfg, target_tile) and not isinstance(defender, City):
        return "naval melee can only attack ships and cities"
    return None


# -- preview and resolution --------------------------------------------------------------------


def _sides(
    state: GameState, cfg: Config, unit: Unit, target: int
) -> tuple[Strength, Strength, Any]:
    defender = defender_at(state, cfg, unit.owner, target)
    ranged = is_ranged(cfg, unit)
    att = unit_strength(state, cfg, unit, ranged=ranged, defending=False, target=target)
    if isinstance(defender, City):
        dfn = city_strength(state, cfg, defender)
    else:
        assert defender is not None
        dfn = unit_strength(state, cfg, defender, ranged=False, defending=True)
    return att, dfn, defender


def preview_attack(state: GameState, cfg: Config, unit: Unit, target: int) -> dict[str, Any]:
    """Expected outcome of `unit` attacking `target`, for the UI and for AI decisions."""
    problem = attack_problem(state, cfg, unit, target)
    if problem:
        return {"legal": False, "reason": problem}
    if defender_at(state, cfg, unit.owner, target) is None:
        zero = {"expected": 0, "min": 0, "max": 0}
        return {
            "legal": True,
            "kind": "capture",
            "attacker": {"unit": unit.id, "hp": unit.hp},
            "defender": {"civilians": [u.id for u in state.units_at(target)], "hp": 0},
            "damage_to_defender": zero,
            "damage_to_attacker": zero,
        }
    att, dfn, defender = _sides(state, cfg, unit, target)
    ranged = is_ranged(cfg, unit)
    to_def = _range(cfg, raw_damage(cfg, dfn.total, att.total))
    to_att = (
        {"expected": 0, "min": 0, "max": 0}
        if ranged
        else _range(cfg, raw_damage(cfg, att.total, dfn.total))
    )
    return {
        "legal": True,
        "kind": "ranged" if ranged else "melee",
        "attacker": {"unit": unit.id, "hp": unit.hp, "strength": att.total, "lines": att.lines},
        "defender": {
            "city" if isinstance(defender, City) else "unit": defender.id,
            "hp": defender.hp,
            "strength": dfn.total,
            "lines": dfn.lines,
        },
        "damage_to_defender": to_def,
        "damage_to_attacker": to_att,
    }


def _roll(state: GameState, cfg: Config, raw: int, which: str) -> int:
    var = cfg.t("combat.variance_pct")
    r = rng.stream(state.seed, "combat", state.turn, state.combat_seq, which)
    return _clamp(cfg, raw * r.randrange(100 - var, 100 + var + 1) // 100)


def damage_unit(state: GameState, cfg: Config, unit: Unit, dmg: int, by: str) -> Events:
    """Apply damage; a stack below one unit's HP loses a member, at 0 HP the unit dies."""
    unit.hp -= dmg
    if unit.hp <= 0:
        credit(state, by, "kills", unit.count)
        credit(state, unit.owner, "units_lost", unit.count)
        remove_unit(state, unit)
        return [
            {
                "kind": "unit_destroyed",
                "unit": unit.id,
                "type": unit.type,
                "owner": unit.owner,
                "by": by,
                "members": unit.count,
            }
        ]
    if unit.count > 1 and unit.hp < cfg.t("combat.unit_max_hp"):
        unit.count -= 1
        credit(state, by, "kills")
        credit(state, unit.owner, "units_lost")
        return [
            {
                "kind": "stack_member_lost",
                "unit": unit.id,
                "owner": unit.owner,
                "by": by,
                "hp": unit.hp,
            }
        ]
    return []


def _clear_hostiles(state: GameState, cfg: Config, tile: int, by: str) -> Events:
    events: Events = []
    for other in state.units_at(tile):
        if hostile(other.owner, by):
            events.extend(damage_unit(state, cfg, other, other.hp, by))
    return events


def _advance(state: GameState, cfg: Config, unit: Unit, target: int) -> Events:
    from beacon.movement import _enter

    occ = occupancy(state)
    if any(
        hostile(o.owner, unit.owner) and not is_civilian(cfg, o.type) for o in occ.get(target, [])
    ):
        return []
    events = _clear_hostiles(state, cfg, target, unit.owner)  # captured civilians are lost
    events.extend(_enter(state, cfg, unit, target))
    events.append({"kind": "unit_advanced", "unit": unit.id, "to": target})
    return events


def attack(state: GameState, cfg: Config, unit: Unit, target: int) -> Events:
    problem = attack_problem(state, cfg, unit, target)
    if problem:
        raise ValueError(problem)
    if defender_at(state, cfg, unit.owner, target) is None:
        unit.attacks_left -= 1
        unit.moves_left = 0
        unit.fortified = False
        unit.acted = True
        events: Events = [{"kind": "civilians_captured", "attacker": unit.id, "target": target}]
        events.extend(_advance(state, cfg, unit, target))
        return events
    att, dfn, defender = _sides(state, cfg, unit, target)
    ranged = is_ranged(cfg, unit)
    land_melee = not ranged and cfg.units[unit.type]["domain"] == "land"
    to_def = _roll(state, cfg, raw_damage(cfg, dfn.total, att.total), "defender")
    to_att = 0 if ranged else _roll(state, cfg, raw_damage(cfg, att.total, dfn.total), "attacker")
    state.combat_seq += 1
    unit.attacks_left -= 1
    unit.moves_left = 0
    unit.fortified = False
    unit.acted = True
    if unit.order == "fortify":
        unit.order = "none"

    events = [
        {
            "kind": "attack",
            "attacker": unit.id,
            "attacker_type": unit.type,
            "target": target,
            "defender_kind": "city" if isinstance(defender, City) else "unit",
            "defender": defender.id,
            "damage_to_defender": to_def,
            "damage_to_attacker": to_att,
            "ranged": ranged,
        }
    ]
    credit(state, unit.owner, "damage_dealt", to_def)

    if isinstance(defender, City):
        city = defender
        floor = 0 if land_melee else 1
        city.hp = max(floor, city.hp - to_def)
        city.besieged = True
        city.damage_by[unit.owner] = city.damage_by.get(unit.owner, 0) + to_def
        if to_att:
            events.extend(damage_unit(state, cfg, unit, to_att, city.owner or ALIENS))
        attacker_alive = str(unit.id) in state.units
        if city.hp <= 0 and attacker_alive and land_melee:
            events.extend(_clear_hostiles(state, cfg, city.tile, unit.owner))
            if city.status == OVERRUN and unit.owner != ALIENS:
                events.extend(liberate(state, cfg, city, unit.owner))
            elif unit.owner == ALIENS:
                events.extend(overrun(state, cfg, city))
            events.extend(_advance(state, cfg, unit, target))
        return events

    events.extend(damage_unit(state, cfg, defender, to_def, unit.owner))
    if to_att:
        events.extend(damage_unit(state, cfg, unit, to_att, defender.owner))
    defender_dead = str(defender.id) not in state.units
    attacker_alive = str(unit.id) in state.units
    if defender_dead and attacker_alive and not ranged:
        events.extend(_advance(state, cfg, unit, target))
    return events


def city_attack_problem(
    state: GameState, cfg: Config, city: City, target: int, seen: set[int] | None = None
) -> str | None:
    if city.bombarded:
        return "the city has already fired this turn"
    if hexgrid.distance(city.tile, target, state.width) > cfg.t("cities.attack_range"):
        return "target out of range"
    if seen is not None and target not in seen:
        return "target is not visible"
    defender = defender_at(state, cfg, city.owner or "", target)
    if not isinstance(defender, Unit):
        return "no hostile unit there"
    return None


def city_attack(state: GameState, cfg: Config, city: City, target: int) -> Events:
    problem = city_attack_problem(state, cfg, city, target)
    if problem:
        raise ValueError(problem)
    defender = defender_at(state, cfg, city.owner or "", target)
    assert isinstance(defender, Unit)
    att = city_strength(state, cfg, city)
    dfn = unit_strength(state, cfg, defender, ranged=False, defending=True)
    dmg = _roll(state, cfg, raw_damage(cfg, dfn.total, att.total), "defender")
    state.combat_seq += 1
    city.bombarded = True
    owner = city.owner or ALIENS
    credit(state, owner, "damage_dealt", dmg)
    events: Events = [
        {
            "kind": "city_attack",
            "city": city.id,
            "target": target,
            "defender": defender.id,
            "damage_to_defender": dmg,
        }
    ]
    events.extend(damage_unit(state, cfg, defender, dmg, owner))
    return events


def defences_fire(state: GameState, cfg: Config) -> Events:
    """City defence guns are part of their city: at the end of each turn every one that has not
    fired shoots the weakest visible enemy in range (ties by hex). Nobody gives them orders."""
    from beacon import fog

    events: Events = []
    for pid in state.player_ids():
        seen = fog.visible_tiles(state, cfg, pid)
        for unit in state.sorted_units():
            spec = cfg.units[unit.type]
            if unit.owner != pid or not spec.get("fixed") or spec.get("no_attack"):
                continue
            if str(unit.id) not in state.units:
                continue
            best = None
            for t in hexgrid.within(unit.tile, spec["range"], state.width, state.height):
                if attack_problem(state, cfg, unit, t, seen) is not None:
                    continue
                victim = defender_at(state, cfg, pid, t)
                key = (victim.hp if victim else 0, t)
                if best is None or key < best:
                    best = key
            if best is not None:
                events.extend(attack(state, cfg, unit, best[1]))
    return events
