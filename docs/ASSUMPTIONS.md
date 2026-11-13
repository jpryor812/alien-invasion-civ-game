# Assumptions

Every modelling choice not fixed by `DESIGN.md`, with the reason. Numbers themselves live in
`data/*.yaml` (all `placeholder` unless noted); this file records the *shape* of the rules.

## M0: foundation

- **Package name `beacon`** (the working title). Data in `data/`, runs in `runs/` (git-ignored).
- **Integers only.** State and data hold no floats. Percentages are integer percent, rounded down
  at the point of use; movement uses `movement.scale` (30) sub-points per move so road (1/3) and
  rail (1/10) costs are exact. Reason: byte-identical results on every platform.
- **Stateless random streams** (`beacon/rng.py`): each draw site builds a generator from a SHA-256
  hash of (seed, stream, keys). No generator state is saved, and adding a draw never shifts
  another. Streams: `map`, `cities`, `combat`, `events`. Bots and AI never draw.
- **Tagging rule relaxed for tables.** A number must sit inside a mapping tagged with `status`,
  either on the value (`{value, status, note}`) or on its enclosing entry (a unit, a building).
  Reason: per-field tags on every unit stat would bury the tables. Tuning values keep per-value
  tags and notes.
- **Commands** are frozen dataclasses with a `kind`; a game is reproduced by seed, config and the
  command log. Player ids are continent ids; aliens use the owner id `aliens`.
- **City ids are list indices** (cities are never deleted); unit ids come from a counter and units
  are stored in a dict keyed by the id as a string (JSON keys are strings).
- **Explored tiles** are stored per player as a hexadecimal bitmap string.
