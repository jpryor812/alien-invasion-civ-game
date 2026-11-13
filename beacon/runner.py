"""Command-line runner: single runs and batches.

python -m beacon.runner run --seed 1 --turns 100 --out runs/s1
python -m beacon.runner batch --seeds 1-20 --turns 100
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Any

from beacon import canonical
from beacon.config import Config, load
from beacon.game import new_game
from beacon.state import GameState, state_digest, state_to_json
from beacon.turn import advance_turn


def play(
    cfg: Config, seed: int, turns: int, continents: list[str] | None = None
) -> tuple[GameState, list[dict[str, Any]], list[dict[str, Any]]]:
    """Play `turns` turns. Returns final state, event log and command log."""
    state = new_game(cfg, seed, continents)
    events: list[dict[str, Any]] = []
    commands: list[dict[str, Any]] = []
    for _ in range(turns):
        events.extend(advance_turn(state, cfg))
    return state, events, commands


def summary(state: GameState, elapsed_ms: int) -> dict[str, Any]:
    return {
        "seed": state.seed,
        "turn": state.turn,
        "digest": state_digest(state),
        "elapsed_ms": elapsed_ms,
    }


def write_run(out: Path, state: GameState, events: list, commands: list, info: dict) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "final_state.json").write_text(state_to_json(state), encoding="utf-8")
    (out / "events.jsonl").write_text(
        "".join(canonical.dumps(e) + "\n" for e in events), encoding="utf-8"
    )
    (out / "commands.jsonl").write_text(
        "".join(canonical.dumps(c) + "\n" for c in commands), encoding="utf-8"
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
        state, events, commands = play(cfg, args.seed, args.turns, continents)
        info = summary(state, int((time.perf_counter() - start) * 1000))
        out = Path(args.out or f"runs/seed{args.seed}")
        write_run(out, state, events, commands, info)
        print(canonical.dumps(info, indent=2))
        return 0

    rows = []
    for seed in _parse_seeds(args.seeds):
        start = time.perf_counter()
        state, events, commands = play(cfg, seed, args.turns, continents)
        rows.append(summary(state, int((time.perf_counter() - start) * 1000)))
        print(canonical.dumps(rows[-1]))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "batch.json").write_text(canonical.dumps(rows, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
