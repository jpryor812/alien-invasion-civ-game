"""The endgame (docs/SPEC_M7.md): mothership strikes, the world barrage, alien espionage,
late-game radar, and victory and defeat.

- The mothership strikes player cities until the barrage fires; reinforcements stop for good
  once any player researches the barrage tech.
- The barrage is one shared megaproject: started by a player who knows the tech, built with any
  player's production or gold, fired once paid for and at least `min_turns` old with its host
  city in player hands.
- Espionage operations are gold-funded, solo or shared; the largest contributor picks one of the
  offered alien techs.
- Victory: mothership destroyed and no alien city left. Defeat: all six continents fallen at once.
  The turn limit ends the game unfinished.
"""

from __future__ import annotations

from typing import Any

from beacon import cities, rng
from beacon.config import Config
from beacon.liberation import credit
from beacon.state import ACTIVE, OVERRUN, CityMemory, GameState, Project

Events = list[dict[str, Any]]
SHARED, SOLO = "shared", "solo"


def _ev(state: GameState, kind: str, **data: Any) -> dict[str, Any]:
    return {"turn": state.turn, "kind": kind, **data}


# -- the barrage ---------------------------------------------------------------------------------


def barrage(state: GameState) -> Project | None:
    return next((p for p in state.projects.values() if p.kind == "barrage"), None)


def barrage_running(state: GameState) -> Project | None:
    b = barrage(state)
    return b if b is not None and not b.done else None


def barrage_needs(state: GameState) -> Project | None:
    """The running barrage, if it still needs progress."""
    b = barrage_running(state)
    return b if b is not None and b.progress < b.cost else None


def host_held(state: GameState, b: Project) -> bool:
    host = state.cities[b.host_city] if b.host_city is not None else None
    return host is not None and host.status == ACTIVE and host.owner in state.players


def start_barrage_problem(state: GameState, cfg: Config, pid: str, city_id: int) -> str | None:
    if cfg.t("endgame.barrage_tech") not in state.players[pid].techs:
        return f"needs {cfg.t('endgame.barrage_tech')}"
    if barrage(state) is not None:
        return "the barrage is already under way"
    if not 0 <= city_id < len(state.cities):
        return f"no city {city_id}"
    city = state.cities[city_id]
    if city.owner != pid or city.status != ACTIVE or not city.connected:
        return "the host must be one of your connected cities"
    return None


def start_barrage(state: GameState, cfg: Config, pid: str, city_id: int) -> Events:
    b = Project(
        id=state.new_id(),
        kind="barrage",
        starter=pid,
        mode=SHARED,
        started_turn=state.turn,
        cost=cfg.t("endgame.barrage.cost"),
        host_city=city_id,
    )
    state.projects[str(b.id)] = b
    return [_ev(state, "barrage_started", player=pid, project=b.id, city=city_id)]


def contribute(state: GameState, cfg: Config, project: Project, pid: str, amount: int) -> int:
    """Add progress from one player; returns the amount accepted."""
    if project.done or amount <= 0:
        return 0
    if project.kind == "barrage" and not host_held(state, project):
        return 0  # paused while the host city is lost
    amount = min(amount, project.cost - project.progress)  # nothing past the cost
    if amount <= 0:
        return 0
    project.progress += amount
    project.contributions[pid] = project.contributions.get(pid, 0) + amount
    credit(state, pid, "barrage" if project.kind == "barrage" else "espionage_gold", amount)
    return amount


def city_contribution(state: GameState, cfg: Config, pid: str, production: int) -> int:
    """A city building `project:barrage` puts all its production into the barrage."""
    b = barrage_needs(state)
    return contribute(state, cfg, b, pid, production) if b is not None else 0


def fund_problem(state: GameState, pid: str, project: Project | None, gold: int) -> str | None:
    if project is None or project.done:
        return "no open project"
    if gold <= 0:
        return "fund a positive amount"
    if state.players[pid].gold < gold:
        return f"the treasury has {state.players[pid].gold} gold"
    if project.mode == SOLO and project.starter != pid:
        return "only its starter funds a solo operation"
    if project.kind == "barrage" and not host_held(state, project):
        return "the barrage is paused while its host city is lost"
    return None


def fund(state: GameState, cfg: Config, pid: str, project: Project, gold: int) -> Events:
    rate = cfg.t("endgame.barrage.gold_to_progress_pct") if project.kind == "barrage" else 100
    accepted = contribute(state, cfg, project, pid, gold * rate // 100)
    gold = -(-accepted * 100 // rate)  # only pay for what the project could take
    state.players[pid].gold -= gold
    return [
        _ev(state, "project_funded", player=pid, project=project.id, gold=gold, progress=accepted)
    ]


def _fire_if_ready(state: GameState, cfg: Config) -> Events:
    b = barrage_running(state)
    if b is None or b.progress < b.cost or not host_held(state, b):
        return []
    if state.turn - b.started_turn < cfg.t("endgame.barrage.min_turns"):
        return []
    b.done = True
    state.aliens.mothership_alive = False
    state.aliens.reinforcements_stopped = True
    return [
        _ev(
            state,
            "barrage_fired",
            project=b.id,
            city=b.host_city,
            contributions=dict(b.contributions),
        )
    ]


# -- the mothership ------------------------------------------------------------------------------


def strikes(state: GameState, cfg: Config) -> Events:
    if not state.aliens.mothership_alive:
        return []
    m = cfg.t("endgame.mothership")
    r = rng.stream(state.seed, "events", state.turn, "strike")
    if r.randrange(1000) >= m["strike_permille"]:
        return []
    targets = [c for c in state.cities if c.status == ACTIVE and c.owner in state.players]
    if not targets:
        return []
    b = barrage_running(state)
    weights = [m["host_weight"] if b is not None and c.id == b.host_city else 1 for c in targets]
    city = rng.weighted_choice(r, targets, weights)
    full = cities.max_hp(cfg, city, state)
    city.hp = max(1, min(city.hp, full * m["strike_hp_pct"] // 100))
    lost = city.pop * m["strike_pop_pct"] // 100
    city.pop = max(1, city.pop - lost)
    city.besieged = True
    return [_ev(state, "mothership_strike", player=city.owner, city=city.id, pop_lost=lost)]


def stop_reinforcements(state: GameState, cfg: Config) -> Events:
    if state.aliens.reinforcements_stopped:
        return []
    tech_id = cfg.t("endgame.barrage_tech")
    who = sorted(pid for pid, p in state.players.items() if tech_id in p.techs)
    if not who:
        return []
    state.aliens.reinforcements_stopped = True
    return [_ev(state, "reinforcements_stopped", player=who[0])]


# -- radar ---------------------------------------------------------------------------------------


def radar(state: GameState, cfg: Config) -> None:
    """Players with a radar tech know every alien-held city."""
    radar_techs = set(cfg.t("endgame.radar_techs"))
    held = [c for c in state.cities if c.status == OVERRUN]
    for player in state.players.values():
        if radar_techs & set(player.techs):
            for c in held:
                player.known_cities[str(c.id)] = CityMemory(c.status, c.owner, c.pop, state.turn)


# -- espionage -----------------------------------------------------------------------------------


def alien_techs(cfg: Config) -> list[str]:
    return sorted(t for t, spec in cfg.techs.items() if spec["tree"] == "alien")


def open_operation(state: GameState, pid: str) -> Project | None:
    return next(
        (
            p
            for p in state.projects.values()
            if p.kind == "espionage" and p.starter == pid and not p.done
        ),
        None,
    )


def start_espionage_problem(state: GameState, pid: str, mode: str) -> str | None:
    if mode not in (SHARED, SOLO):
        return "mode must be shared or solo"
    if open_operation(state, pid) is not None:
        return "you already run an operation"
    return None


def start_espionage(state: GameState, cfg: Config, pid: str, mode: str) -> Events:
    p = Project(
        id=state.new_id(),
        kind="espionage",
        starter=pid,
        mode=mode,
        started_turn=state.turn,
        cost=cfg.t("endgame.espionage.cost"),
    )
    state.projects[str(p.id)] = p
    return [_ev(state, "espionage_started", player=pid, project=p.id, mode=mode)]


def recipients(state: GameState, p: Project) -> list[str]:
    return [p.starter] if p.mode == SOLO else state.player_ids()


def _complete_espionage(state: GameState, cfg: Config, p: Project) -> Events:
    p.done = True
    who = recipients(state, p)
    pool = [t for t in alien_techs(cfg) if any(t not in state.players[x].techs for x in who)]
    r = rng.stream(state.seed, "events", state.turn, "espionage", p.id)
    p.offered = sorted(r.sample(pool, min(cfg.t("endgame.espionage.offered"), len(pool))))
    p.chooser = max(sorted(p.contributions), key=lambda x: p.contributions[x], default=p.starter)
    p.choose_by = state.turn + cfg.t("endgame.espionage.choose_turns")
    if not p.offered:
        del state.projects[str(p.id)]
        return [_ev(state, "espionage_empty", player=p.starter, project=p.id)]
    return [
        _ev(state, "espionage_complete", player=p.chooser, project=p.id, offered=list(p.offered))
    ]


def choose(state: GameState, cfg: Config, p: Project, tech_id: str) -> Events:
    for x in recipients(state, p):
        player = state.players[x]
        if tech_id not in player.techs:
            player.techs = sorted([*player.techs, tech_id])
    del state.projects[str(p.id)]
    return [
        _ev(
            state,
            "alien_tech_gained",
            player=p.chooser,
            project=p.id,
            tech=tech_id,
            recipients=recipients(state, p),
        )
    ]


def choose_problem(state: GameState, pid: str, p: Project | None, tech_id: str) -> str | None:
    if p is None or p.kind != "espionage" or not p.offered:
        return "no espionage result to choose from"
    if p.chooser != pid:
        return "only the largest contributor chooses"
    if tech_id not in p.offered:
        return f"{tech_id} is not on offer"
    return None


# -- end of turn and outcome ---------------------------------------------------------------------


def end_of_turn(state: GameState, cfg: Config) -> Events:
    events = stop_reinforcements(state, cfg)
    events += _fire_if_ready(state, cfg)
    for key in sorted(state.projects, key=int):
        p = state.projects.get(key)
        if p is None or p.kind != "espionage":
            continue
        if not p.done and p.progress >= p.cost:
            events += _complete_espionage(state, cfg, p)
        elif p.done and p.offered and p.choose_by is not None and state.turn >= p.choose_by:
            events += choose(state, cfg, p, p.offered[0])
    for pid in state.player_ids():
        abroad = sum(
            u.count
            for u in state.units.values()
            if u.owner == pid and state.tiles[u.tile].continent != pid
        )
        credit(state, pid, "unit_turns_abroad", abroad)
    radar(state, cfg)
    return events


def check_outcome(state: GameState, cfg: Config) -> Events:
    if state.outcome is not None:
        return []
    outcome = None
    if not state.aliens.mothership_alive and not any(c.status == OVERRUN for c in state.cities):
        outcome = "victory"
    elif state.players and all(p.fallen for p in state.players.values()):
        outcome = "defeat"
    elif state.turn >= cfg.t("time.max_turns"):
        outcome = "turn_limit"
    if outcome is None:
        return []
    state.outcome, state.outcome_turn = outcome, state.turn
    return [_ev(state, "game_over", outcome=outcome)]
