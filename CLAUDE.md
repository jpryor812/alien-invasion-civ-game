# CLAUDE.md

Read docs/DESIGN.md first, then the current milestone spec (docs/SPEC_M0-M3.md). This is a
turn-based 4X cooperative-competitive game: six continents, a common alien foe, a beacon tech
branch that recruits alien characters, and an MVP score.

## Principles
- Headless deterministic simulation first (Python 3.11+, pytest, ruff). Same seed and inputs give
  identical output. All randomness through seeded streams in `beacon/rng.py`. Bots and AI use none.
- No LLM calls and no network access in the simulation.
- No magic numbers: tunables live in data/*.yaml tagged status: placeholder or calibrated.
- Pure, serializable state: plain dataclasses that round-trip through JSON. Integers only.
- Neutral, fictional tone. Leaders are abstract; no real people.
- Simple first; add detail only when a test or balance run shows it is needed.

## Stack and commands
- Setup: `uv sync`
- Test: `uv run pytest -q`
- Lint: `uv run ruff check . && uv run ruff format --check .`
- One run: `uv run python -m beacon.runner run --seed 1 --turns 100 --out runs/s1`
- Batch: `uv run python -m beacon.runner batch --seeds 1-20 --turns 100`

## Working agreements
- Plan before coding. A milestone spec approved by the designer may be built without stopping
  between milestones, gated by tests: each milestone ends with passing tests and ruff, its
  acceptance criteria met, a short summary, and a git commit. Stop at the review point the spec
  names (currently after M3) and wait for approval before the next spec.
- Record every modelling choice not in the design doc in docs/ASSUMPTIONS.md.
- When doc and code disagree, stop and ask or update the doc with a note.
- Never commit secrets, copyrighted reference images, or fonts/assets without clear licences.
- Do not push to GitHub without asking.

## Layout
```
beacon/   config, rng, canonical, hexgrid, state, mapgen, fog, economy, tech, units,
          combat, commands, turn, view, bots, runner
data/     tuning, terrain, resources, improvements, buildings, units, techs, continents, bots
docs/     DESIGN, SPEC_M0-M3, ASSUMPTIONS
tests/
runs/     run output (git-ignored)
```
