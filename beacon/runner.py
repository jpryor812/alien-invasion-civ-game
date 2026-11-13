"""Command-line runner: single runs, batches and replays.

    python -m beacon.runner run --seed 1 --turns 100 --out runs/s1
    python -m beacon.runner batch --seeds 1-20 --turns 100

Every player is driven by the test bot (`beacon.bots`). A run writes the final state, the event
log, the command log (enough to replay it) and a summary.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Any

from beacon import bots, canonical
from beacon.actions import apply_command
from beacon.commands import Command, CommandError, command_from_dict, command_to_dict
from beacon.config import Config, load
from beacon.game import new_game
from beacon.state import ACTIVE, ALIENS, OVERRUN, GameState, state_digest, state_to_json
from beacon.turn import advance_turn


def play(
    cfg: Config, seed: int, turns: int, continents: list[str] | None = None
) -> tuple[GameState, list[dict[str, Any]], list[dict[str, Any]]]:
    """Play `turns` turns with bots. Returns final state, event log and command log."""
    state = new_game(cfg, seed, continents)
    events: list[dict[str, Any]] = []
    log: list[dict[str, Any]] = []

    def submit(cmd: Command) -> list[dict[str, Any]]:
        entry = {"turn": state.turn, "cmd": command_to_dict(cmd)}
        try:
            out = apply_command(state, cfg, cmd)
        except CommandError as err:
            log.append({**entry, "ok": False, "error": str(err)})
            raise
        log.append({**entry, "ok": True})
        events.extend(out)
        return out

    for _ in range(turns):
        for pid in state.player_ids():
            bots.take_turn(state, cfg, pid, submit)
        events.extend(advance_turn(state, cfg))
    return state, events, log


def replay(
    cfg: Config,
    seed: int,
    turns: int,
    log: list[dict[str, Any]],
    continents: list[str] | None = None,
) -> GameState:
    """Rebuild a game from its seed and accepted commands."""
    state = new_game(cfg, seed, continents)
    accepted = [e for e in log if e["ok"]]
    i = 0
    for _ in range(turns):
        while i < len(accepted) and accepted[i]["turn"] == state.turn:
            apply_command(state, cfg, command_from_dict(accepted[i]["cmd"]))
            i += 1
        advance_turn(state, cfg)
    if i != len(accepted):
        raise ValueError("command log has entries past the final turn")
    return state


def summary(state: GameState, log: list[dict[str, Any]], elapsed_ms: int) -> dict[str, Any]:
    status_counts: dict[str, int] = {}
    for city in state.cities:
        status_counts[city.status] = status_counts.get(city.status, 0) + 1
    credits: dict[str, dict[str, int]] = {pid: dict(p.credits) for pid, p in state.players.items()}
    return {
        "seed": state.seed,
        "turn": state.turn,
        "digest": state_digest(state),
        "elapsed_ms": elapsed_ms,
        "cities": status_counts,
        "player_cities": sum(1 for c in state.cities if c.status == ACTIVE),
        "alien_cities": sum(1 for c in state.cities if c.status == OVERRUN),
        "units": {
            "players": sum(u.count for u in state.units.values() if u.owner != ALIENS),
            "aliens": sum(u.count for u in state.units.values() if u.owner == ALIENS),
        },
        "commands": len(log),
        "rejected_commands": sum(1 for e in log if not e["ok"]),
        "credits": credits,
    }


def write_run(out: Path, state: GameState, events: list, log: list, info: dict) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "final_state.json").write_text(state_to_json(state), encoding="utf-8")
    (out / "events.jsonl").write_text(
        "".join(canonical.dumps(e) + "\n" for e in events), encoding="utf-8"
    )
    (out / "commands.jsonl").write_text(
        "".join(canonical.dumps(c) + "\n" for c in log), encoding="utf-8"
    )
    (out / "summary.json").write_text(canonical.dumps(info, indent=2) + "\n", encoding="utf-8")


def _parse_seeds(text: str) -> list[int]:
    if "-" in text:
        lo, hi = text.split("-", 1)
        return list(range(int(lo), int(hi) + 1))
    return [int(s) for s in text.split(",")]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="beacon.runner")
    sub = parser.add_subparsers(dest="cmd", required=True)
    run_p = sub.add_parser("run")
    run_p.add_argument("--seed", type=int, default=1)
    run_p.add_argument("--turns", type=int, default=10)
    run_p.add_argument("--continents", default="")
    run_p.add_argument("--out", default="")
    batch_p = sub.add_parser("batch")
    batch_p.add_argument("--seeds", default="1-5")
    batch_p.add_argument("--turns", type=int, default=50)
    batch_p.add_argument("--continents", default="")
    batch_p.add_argument("--out", default="runs/batch")
    args = parser.parse_args(argv)

    cfg = load()
    continents = [c for c in args.continents.split(",") if c] or None
    if args.cmd == "run":
        start = time.perf_counter()
        state, events, log = play(cfg, args.seed, args.turns, continents)
        info = summary(state, log, int((time.perf_counter() - start) * 1000))
        out = Path(args.out or f"runs/seed{args.seed}")
        write_run(out, state, events, log, info)
        print(canonical.dumps(info, indent=2))
        return 0

    rows = []
    for seed in _parse_seeds(args.seeds):
        start = time.perf_counter()
        state, _, log = play(cfg, seed, args.turns, continents)
        row = summary(state, log, int((time.perf_counter() - start) * 1000))
        del row["credits"]
        rows.append(row)
        print(canonical.dumps(row))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "batch.json").write_text(canonical.dumps(rows, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
