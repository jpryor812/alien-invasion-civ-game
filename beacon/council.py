"""The council of continents (docs/SPEC_M13.md, designer 2026-11-15).

- Everyone sits on the council from turn 1 (radio contact).
- Influence: earned from the credit ledger and the leader's agenda; spent on proposals and extra
  votes; pledges add or take some.
- Every few turns a session opens: players' proposals plus one drawn measure. Players vote during
  the next turn (weighted by influence); the session resolves at that turn's end.
- Agendas (public) steer AI votes; secret objectives add MVP points.
"""

from __future__ import annotations

from typing import Any

from beacon import hexgrid, rng
from beacon.config import Config
from beacon.state import ACTIVE, OVERRUN, GameState, Measure, Player

Events = list[dict[str, Any]]
CHOICES = ("yes", "no", "abstain")


def _ev(state: GameState, kind: str, **data: Any) -> dict[str, Any]:
    return {"turn": state.turn, "kind": kind, **data}


# -- influence -------------------------------------------------------------------------------------


def _per(key: str) -> tuple[str, int]:
    if "_per_" in key:
        entry, _, n = key.rpartition("_per_")
        return entry, int(n)
    return key, 1


def influence(cfg: Config, player: Player) -> int:
    total = 0
    for key, w in sorted(cfg.council("influence.earn").items()):
        entry, div = _per(key)
        total += player.credits.get(entry, 0) * w // div
    if player.agenda:
        a = cfg.council(f"agendas.{player.agenda}")
        total += player.credits.get(a["credit"], 0) // a["per"] * a["influence"]
    return total + player.influence_adjust


def weight(cfg: Config, player: Player) -> int:
    return 1 + max(0, influence(cfg, player)) // cfg.council("sessions.influence_per_vote")


# -- agendas and objectives ------------------------------------------------------------------------


def deal_agendas(state: GameState, cfg: Config) -> None:
    """Seeded agendas and secret objectives (different ones while they last)."""
    agendas = sorted(cfg.council("agendas"))
    goals = sorted(cfg.council("objectives"))
    r = rng.stream(state.seed, "leader", "agendas")
    r.shuffle(agendas)
    r.shuffle(goals)
    for k, pid in enumerate(state.player_ids()):
        state.players[pid].agenda = agendas[k % len(agendas)]
        state.players[pid].objective = goals[k % len(goals)]


def objective_met(state: GameState, cfg: Config, pid: str) -> bool:
    player = state.players[pid]
    if player.objective is None:
        return False
    spec = cfg.council(f"objectives.{player.objective}")
    if "credit" in spec:
        return player.credits.get(spec["credit"], 0) >= spec["at"]
    if "chair" in spec:
        return player.times_chair >= spec["chair"]
    if "hybrids" in spec:
        from beacon.citizens import council_of

        return sum(1 for c in council_of(state, pid) if c.hybrid) >= spec["hybrids"]
    return False


def objective_points(state: GameState, cfg: Config, pid: str) -> int:
    player = state.players[pid]
    if not objective_met(state, cfg, pid):
        return 0
    return int(cfg.council(f"objectives.{player.objective}.points"))


# -- proposals and votes ---------------------------------------------------------------------------


def propose_problem(state: GameState, cfg: Config, pid: str, kind: str) -> str | None:
    if kind not in cfg.council("measures"):
        return f"unknown measure {kind!r}"
    cost = cfg.council("sessions.propose_cost")
    if influence(cfg, state.players[pid]) < cost:
        return f"needs {cost} influence"
    if pid not in members(state, cfg):
        return "build a radio tower to reach the council"
    if any(m.proposer == pid for m in state.council.proposals):
        return "you already have a proposal waiting"
    if any(m.kind == kind for m in state.council.proposals):
        return "that measure is already proposed"
    return None


def propose(state: GameState, cfg: Config, pid: str, kind: str) -> Events:
    state.players[pid].influence_adjust -= cfg.council("sessions.propose_cost")
    m = Measure(id=state.new_id(), kind=kind, proposer=pid)
    state.council.proposals = [*state.council.proposals, m]
    return [_ev(state, "measure_proposed", player=pid, measure=kind)]


def measure(state: GameState, measure_id: int) -> Measure | None:
    return next((m for m in state.council.measures if m.id == measure_id), None)


def members(state: GameState, cfg: Config) -> list[str]:
    """Who sits on the council: players on the air (a radio tower; designer 2026-11-16)."""
    from beacon.contact import on_air

    return on_air(state, cfg)


def vote_problem(
    state: GameState, cfg: Config, pid: str, measure_id: int, choice: str, extra: int
) -> str | None:
    if pid not in members(state, cfg):
        return "build a radio tower to reach the council"
    m = measure(state, measure_id)
    if m is None:
        return "no such measure before the council"
    spec = cfg.council(f"measures.{m.kind}")
    if spec["kind"] == "chair":
        if choice not in members(state, cfg) and choice != "abstain":
            return "vote for a player (or abstain)"
    elif choice not in CHOICES:
        return f"vote one of {', '.join(CHOICES)}"
    if extra < 0:
        return "extra votes cannot be negative"
    cost = extra * cfg.council("sessions.extra_vote_cost")
    already = m.extra.get(pid, 0) * cfg.council("sessions.extra_vote_cost")
    if cost > already and influence(cfg, state.players[pid]) < cost - already:
        return f"needs {cost - already} influence for {extra} extra votes"
    return None


def vote(
    state: GameState, cfg: Config, pid: str, measure_id: int, choice: str, extra: int
) -> Events:
    m = measure(state, measure_id)
    assert m is not None
    unit = cfg.council("sessions.extra_vote_cost")
    state.players[pid].influence_adjust -= (extra - m.extra.get(pid, 0)) * unit
    m.votes = {**m.votes, pid: choice}
    m.extra = {**m.extra, pid: extra}
    return [_ev(state, "vote_cast", player=pid, measure=m.kind, choice=choice)]


def unvoted(state: GameState, pid: str, cfg: Config | None = None) -> list[Measure]:
    if cfg is not None and pid not in members(state, cfg):
        return []
    return [m for m in state.council.measures if pid not in m.votes]


# -- sessions --------------------------------------------------------------------------------------


def _strike_target(state: GameState) -> int | None:
    """The alien city most damaged by players, else the weakest by HP (ids break ties)."""
    held = [c for c in state.cities if c.status == OVERRUN]
    if not held:
        return None
    return max(held, key=lambda c: (sum(c.damage_by.values()), -c.hp, -c.id)).id


def open_session(state: GameState, cfg: Config) -> Events:
    s = cfg.council("sessions")
    c = state.council
    table = c.proposals[: s["max_proposals"]]
    c.proposals = c.proposals[s["max_proposals"] :]
    kinds = sorted(k for k in cfg.council("measures") if all(m.kind != k for m in table))
    r = rng.stream(state.seed, "events", state.turn, "council")
    if c.chair is None and "chair_election" in kinds:
        drawn = "chair_election"  # the first sessions elect a chair
    else:
        drawn = r.choice(kinds) if kinds else None
    if drawn is not None:
        table.append(Measure(id=state.new_id(), kind=drawn))
    for m in table:
        if cfg.council(f"measures.{m.kind}.kind") == "strike":
            m.target = _strike_target(state)
    table = [
        m
        for m in table
        if not (cfg.council(f"measures.{m.kind}.kind") == "strike" and m.target is None)
    ]
    c.measures = table
    c.sessions += 1
    return [
        _ev(state, "council_session", player=pid, measures=[m.kind for m in table])
        for pid in members(state, cfg)
    ]


def _tally(state: GameState, cfg: Config, m: Measure) -> dict[str, int]:
    out: dict[str, int] = {}
    for pid, choice in sorted(m.votes.items()):
        if choice == "abstain" or pid not in state.players:
            continue
        out[choice] = out.get(choice, 0) + weight(cfg, state.players[pid]) + m.extra.get(pid, 0)
    return out


def _passes(state: GameState, m: Measure, tally: dict[str, int]) -> bool:
    yes, no = tally.get("yes", 0), tally.get("no", 0)
    if yes != no:
        return yes > no
    chair = state.council.chair
    return chair is not None and m.votes.get(chair) == "yes"


def resolve(state: GameState, cfg: Config) -> Events:
    c = state.council
    events: Events = []
    results = []
    for m in c.measures:
        spec = cfg.council(f"measures.{m.kind}")
        tally = _tally(state, cfg, m)
        if spec["kind"] == "chair":
            if tally:
                top = max(tally.values())
                tied = sorted(p for p, v in tally.items() if v == top)
                winner = c.chair if c.chair in tied else tied[0]
                c.chair = winner
                state.players[winner].times_chair += 1
                results.append({"measure": m.kind, "passed": True, "chair": winner, "tally": tally})
                events.append(_ev(state, "chair_elected", player=winner, chair=winner))
            continue
        passed = _passes(state, m, tally)
        results.append({"measure": m.kind, "passed": passed, "tally": tally, "target": m.target})
        events.append(_ev(state, "measure_result", measure=m.kind, passed=passed, tally=tally))
        if passed:
            events.extend(_enact(state, cfg, m))
    c.results = results
    c.measures = []
    return events


def _enact(state: GameState, cfg: Config, m: Measure) -> Events:
    spec = cfg.council(f"measures.{m.kind}")
    c = state.council
    if spec["kind"] == "effect":
        until = state.turn + spec["turns"]
        c.active = [*c.active, {"measure": m.kind, "until": until, "effects": spec["effects"]}]
        for pid in state.player_ids():  # read by beacon/techfx.py like tech effects
            p = state.players[pid]
            p.temp_effects = [
                *p.temp_effects,
                {"source": spec["name"], "until": until, **spec["effects"]},
            ]
        return []
    if spec["kind"] == "strike" and m.target is not None:
        c.active = [
            *c.active,
            {
                "measure": m.kind,
                "until": state.turn + spec["turns"],
                "city": m.target,
                "pct": spec["pct"],
                "radius": spec["radius"],
                "effects": {},
            },
        ]
        return []
    if spec["kind"] == "relief":
        alive = [p for p in members(state, cfg) if not state.players[p].fallen]
        counts = {
            p: sum(1 for x in state.cities if x.owner == p and x.status == ACTIVE) for p in alive
        }
        if not counts:
            return []
        poor = min(counts, key=lambda p: (counts[p], p))
        events: Events = []
        pay = cfg.council("influence")
        for pid in alive:
            if pid == poor:
                continue
            player = state.players[pid]
            if player.gold >= spec["gold"]:
                player.gold -= spec["gold"]
                state.players[poor].gold += spec["gold"]
                player.influence_adjust += pay["pledge_paid"]
            else:
                player.influence_adjust += pay["pledge_missed"]
        events.append(_ev(state, "relief_paid", player=poor, receiver=poor))
        return events
    return []


def strike_pct(state: GameState, target_tile: int) -> int:
    """Joint strike bonus for attacking at `target_tile`."""
    out = 0
    for a in state.council.active:
        if a.get("measure") != "joint_strike":
            continue
        city = state.cities[a["city"]]
        if hexgrid.distance(city.tile, target_tile, state.width) <= a["radius"]:
            out = max(out, a["pct"])
    return out


def end_of_turn(state: GameState, cfg: Config) -> Events:
    """Resolve an open session, expire measures, open the next session on schedule."""
    events: Events = []
    c = state.council
    if c.measures:
        events.extend(resolve(state, cfg))
    c.active = [a for a in c.active if a["until"] > state.turn]
    for pid in state.player_ids():
        p = state.players[pid]
        p.temp_effects = [e for e in p.temp_effects if e["until"] > state.turn]
    every = cfg.council("sessions.session_turns")
    if (state.turn + 1) % every == 0:
        events.extend(open_session(state, cfg))
    return events
