"""Tech effects (designer, 2026-11-14): bonuses a known tech gives its player, beyond what it
unlocks. Each tech in data/techs.yaml may have `effects`; this module sums them.

Keys (all integers):
  yield_pct {yield: pct}     percent bonus to a yield in every city
  city_yields {yield: n}     flat yield in every city
  growth_pct                 faster births and children growing up
  build_turns                change to engineers' build time (negative is faster; at least 1)
  labour_pct                 percent more labour from each city's engineers (SPEC_M17)
  unit_cost_pct              change to units' production cost
  free_upkeep_per_city       extra units per city with no gold upkeep
  flanking_pct               extra strength per flanking unit
  class_defence_pct {class: pct}  defence bonus for a unit class
  ranged_attack_pct          bonus to ranged attacks
  hunt_immune [class]        unit classes alien hunters ignore
  ship_time_pct              change to the time troops take by sea
  city_strength              flat strength for every city
  keep_research_on_deficit   1: an empty treasury no longer drains research
  purchase_pct               change to the gold price of buying
  fund_pct                   percent more effect from gold sent to a resistance
  exchange_pct               percent better prices at the Galactic Exchange
  improvement_food {imp: n}  more food from each worked hex with that improvement (SPEC_M19)
  winter_keep_pct            share of crop food kept in the galactic winter, added (SPEC_M19)
"""

from __future__ import annotations

from typing import Any

from beacon.config import Config
from beacon.state import Player


def _effects(cfg: Config, player: Player | None) -> list[dict[str, Any]]:
    if player is None:
        return []
    from beacon.leader import effects  # leader imports only config, state, rng and hexgrid

    techs = [cfg.techs[t].get("effects") or {} for t in player.techs if t in cfg.techs]
    lead = [e for _, e in effects(cfg, player.leader)]  # leader traits and bonuses (SPEC_M11)
    council = list(player.temp_effects)  # council measures in force (SPEC_M13)
    agenda = _agenda(cfg, player)  # the agenda's perk (designer 2026-11-17)
    return techs + list(player.boons) + lead + council + agenda  # with Starfall shards


def _agenda(cfg: Config, player: Player) -> list[dict[str, Any]]:
    if not player.agenda:
        return []
    spec = cfg.council("agendas").get(player.agenda) or {}
    return [spec["effects"]] if spec.get("effects") else []


def total(cfg: Config, player: Player | None, key: str) -> int:
    """Sum of an integer effect over the player's known techs."""
    return sum(int(e.get(key, 0)) for e in _effects(cfg, player))


def by_key(cfg: Config, player: Player | None, key: str) -> dict[str, int]:
    """Sum of a {name: n} effect over the player's known techs."""
    out: dict[str, int] = {}
    for e in _effects(cfg, player):
        for k, v in (e.get(key) or {}).items():
            out[k] = out.get(k, 0) + int(v)
    return out


def lines(cfg: Config, player: Player | None, key: str) -> list[tuple[str, Any]]:
    """(source, value) for each known tech or claimed shard with this effect, for breakdowns."""
    if player is None:
        return []
    out = [
        (t, cfg.techs[t]["effects"][key])
        for t in player.techs
        if t in cfg.techs and (cfg.techs[t].get("effects") or {}).get(key)
    ]
    out += [(f"shard {b['shard']}", b[key]) for b in player.boons if b.get(key)]
    from beacon.leader import effects

    out += [(src, e[key]) for src, e in effects(cfg, player.leader) if e.get(key)]
    out += [(f"council: {e['source']}", e[key]) for e in player.temp_effects if e.get(key)]
    out += [(f"agenda {player.agenda}", e[key]) for e in _agenda(cfg, player) if e.get(key)]
    return out


def listed(cfg: Config, player: Player | None, key: str) -> set[str]:
    out: set[str] = set()
    for e in _effects(cfg, player):
        out.update(e.get(key) or [])
    return out


DESCRIBE = {
    "growth_pct": "Cities grow {v}% faster; children grow up {v}% faster",
    "build_turns": "Engineers build {n} turn faster",
    "labour_pct": "+{v}% labour from engineers",
    "fund_pct": "Gold to a resistance goes {v}% further",
    "exchange_pct": "{v}% better prices at the Galactic Exchange",
    "unit_cost_pct": "Units cost {n}% less production",
    "free_upkeep_per_city": "+{v} unit per city free of gold upkeep",
    "flanking_pct": "+{v}% strength per flanking unit",
    "ranged_attack_pct": "Ranged attacks +{v}%",
    "ship_time_pct": "Troops by sea arrive {n}% sooner",
    "city_strength": "+{v} strength for every city",
    "keep_research_on_deficit": "An empty treasury no longer drains research",
    "purchase_pct": "Buying with gold costs {n}% less",
}


def describe(effects: dict[str, Any]) -> list[str]:
    """Readable lines for a tech's effects (tech tree cards)."""
    out = []
    for k, v in (effects or {}).items():
        if k == "yield_pct":
            out += [f"+{p}% {y} in every city" for y, p in v.items()]
        elif k == "city_yields":
            out += [f"+{n} {y} in every city" for y, n in v.items()]
        elif k == "class_defence_pct":
            out += [f"{c.capitalize()} units +{p}% defence" for c, p in v.items()]
        elif k == "hunt_immune":
            out.append(f"Alien hunters ignore your {', '.join(v)} units")
        elif k in DESCRIBE:
            out.append(DESCRIBE[k].format(v=v, n=abs(int(v))))
    return out
