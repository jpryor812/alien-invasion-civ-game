"""The leaders of alien-held towns (docs/SPEC_M21.md, designer 2026-11-21).

Every alien-held town has a leader with a temperament, met when a player first sees the town:
- bribable: takes the gold, defects to the player's council as a recruit, and the town's
  defense halves (as a fully funded resistance);
- greedy: looks just as fond of gold, but takes it and gives nothing;
- aggressive: on being found, turns on the player (more heat, so more alien attacks);
- stoic: will not deal.
Scouts only learn the hint ("fond of gold", "spoiling for a fight", "cold"), so a bribe is a
gamble. Seeded per town; no randomness at play time."""

from __future__ import annotations

from typing import Any

from beacon import rng
from beacon.config import Config
from beacon.state import ALIENS, OVERRUN, City, GameState

Events = list[dict[str, Any]]


def L(cfg: Config, key: str) -> Any:  # noqa: N802 - short accessor
    return cfg.alien(f"leaders.{key}")


def appoint(state: GameState, cfg: Config, city: City) -> None:
    """Give an alien-held town a leader (at the start, and when the aliens take a town)."""
    from beacon.recruits import _name

    r = rng.stream(state.seed, "events", "alien_leader", city.id, state.turn)
    temps = sorted(L(cfg, "temperaments"))
    temper = rng.weighted_choice(r, temps, [L(cfg, f"temperaments.{t}.weight") for t in temps])
    city.alien_leader = {
        "name": _name(cfg, r),
        "temper": temper,
        "face": r.randrange(1_000_000),
        "met": [],
        "answered": [],
        "angry": [],
        "dealt": "",  # bribed or cheated
    }


def appoint_all(state: GameState, cfg: Config) -> None:
    for city in state.cities:
        if city.status == OVERRUN and not city.alien_leader:
            appoint(state, cfg, city)


def hint(cfg: Config, city: City) -> str:
    return L(cfg, f"temperaments.{city.alien_leader['temper']}.hint")


def bribe_cost(state: GameState, cfg: Config, city: City) -> int:
    from beacon.combat import city_strength

    return max(
        L(cfg, "bribe_min"),
        city_strength(state, cfg, city).total // 100 * L(cfg, "bribe_per_strength"),
    )


def can_bribe(cfg: Config, city: City) -> bool:
    return bool(L(cfg, f"temperaments.{city.alien_leader['temper']}.offers_bribe"))


def meet(state: GameState, cfg: Config) -> Events:
    """Players meet the leaders of alien-held towns they now know."""
    events: Events = []
    for pid in state.player_ids():
        player = state.players[pid]
        for key in sorted(player.known_cities, key=int):
            city = state.cities[int(key)]
            lead = city.alien_leader
            if city.status != OVERRUN or city.owner != ALIENS or not lead or pid in lead["met"]:
                continue
            lead["met"] = sorted([*lead["met"], pid])
            if lead["temper"] == "aggressive":
                lead["angry"] = sorted([*lead["angry"], pid])
            events.append(
                {
                    "turn": state.turn,
                    "kind": "alien_leader_met",
                    "player": pid,
                    "city": city.id,
                    "angry": lead["temper"] == "aggressive",
                }
            )
    return events


def pending(state: GameState, pid: str) -> list[int]:
    """Towns whose leader this player met and has not answered yet."""
    return [
        c.id
        for c in state.cities
        if c.alien_leader
        and c.status == OVERRUN
        and pid in c.alien_leader["met"]
        and pid not in c.alien_leader["answered"]
    ]


def answer_problem(state: GameState, cfg: Config, pid: str, city: City, bribe: bool) -> str | None:
    lead = city.alien_leader
    if not lead or city.status != OVERRUN or pid not in lead["met"]:
        return "you have not met this town's leader"
    if not bribe:
        return None
    if lead["dealt"]:
        return f"{lead['name']} will not deal again"
    if not can_bribe(cfg, city):
        return f"{lead['name']} will not take a bribe"
    cost = bribe_cost(state, cfg, city)
    if state.players[pid].gold < cost:
        return f"needs {cost} gold; treasury has {state.players[pid].gold}"
    return None


def answer(state: GameState, cfg: Config, pid: str, city: City, bribe: bool) -> Events:
    lead = city.alien_leader
    if pid not in lead["answered"]:
        lead["answered"] = sorted([*lead["answered"], pid])
    if not bribe:
        return [{"kind": "alien_leader_left", "player": pid, "city": city.id}]
    cost = bribe_cost(state, cfg, city)
    state.players[pid].gold -= cost
    if lead["temper"] != "bribable":
        lead["dealt"] = "cheated"
        return [
            {
                "kind": "alien_bribe_taken",
                "player": pid,
                "city": city.id,
                "gold": cost,
                "name": lead["name"],
            }
        ]
    lead["dealt"] = "bribed"
    from beacon.recruits import make_recruit

    rec = make_recruit(state, cfg, pid, L(cfg, "recruit_level"))
    rec.name = lead["name"]
    city.funded_pct = max(city.funded_pct, cfg.alien("funding.max_pct"))  # defense halves
    return [
        {
            "kind": "alien_leader_defected",
            "player": pid,
            "city": city.id,
            "gold": cost,
            "name": lead["name"],
            "recruit": rec.id,
        }
    ]


def angry_heat(state: GameState, cfg: Config, pid: str) -> int:
    """Heat from aggressive leaders this player has found, while their towns stand."""
    n = sum(
        1
        for c in state.cities
        if c.status == OVERRUN and c.alien_leader and pid in c.alien_leader["angry"]
    )
    return n * L(cfg, "aggressive_heat")
