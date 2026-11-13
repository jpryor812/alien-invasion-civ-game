# CLAUDE.md

Read docs/DESIGN.md first. This is a turn-based 4X cooperative-competitive game: six continents,
a common alien foe, a beacon tech branch that recruits alien characters, and an MVP score.

## Principles
- Headless deterministic simulation first (Python 3.11+, pytest, ruff). Same seed and inputs give
  identical output. All randomness through seeded streams in one module.
- No LLM calls and no network access in the simulation.
- No magic numbers: tunables live in data/*.yaml tagged status: placeholder or calibrated.
- Pure, serializable state: plain dataclasses that round-trip through JSON.
- Neutral, fictional tone. Leaders are abstract; no real people.
- Simple first; add detail only when a test or balance run shows it is needed.

## Working agreements
- Plan before coding; wait for approval before each milestone.
- One milestone at a time, ending with passing tests, a short summary of what was built and
  assumed, and a git commit.
- Record every modelling choice not in the design doc in docs/ASSUMPTIONS.md.
- When doc and code disagree, stop and ask or update the doc with a note.
- Never commit secrets or fonts/assets without clear licences.
