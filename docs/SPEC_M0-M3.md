# Spec: milestones M0 to M3

Status: approved for an autonomous build on 2026-11-13 (test gates, review after M3). Numbers live
in `data/*.yaml` and are all `placeholder` unless noted. Every choice not in `DESIGN.md` is also
listed in `ASSUMPTIONS.md`.

## Decisions taken with the designer (2026-11-13)

- **Era:** the game starts in 2025 (present-day technology already known) and researches into
  near-future technology. Not 1939.
- **Combat:** Civ V model. Each attack is one command: strength against strength, damage taken off
  hit points (HP), terrain and flanking modifiers, small seeded variance, a shared
  `preview_attack()` that the UI will reuse. Ranged attacks draw no retaliation.
- **Stacking:** at most two units on a hex, and only two of the same unit type with the same owner.
  The stack is one unit with twice the strength (melee and ranged), one attack per turn, and HP
  equal to the members' combined HP (max 200). If the stack drops below 100 HP (it has lost more
  than half of 200), one member dies. A stack can split: the unit that moves out leaves at full HP
  (100) and the remainder stays. Applies to land, ranged and sea units; not to civilians.
  Otherwise one military unit per hex, plus one civilian (Civ V layering).
- **Map:** procedural and Earth-flavoured: each continent is generated per seed with its own
  climate mix and real city names placed by rules. It will not look like the real continent.
- **Tooling:** uv, Python 3.11+ (3.13 installed), pytest, ruff, PyYAML.
- **Process:** M0 to M3 run without per-milestone approval, gated by tests; one commit per
  milestone; the designer reviews after M3.

## Cross-cutting rules (M0)

- **Package:** `beacon/`. Data in `data/`. Runs written to `runs/` (git-ignored).
- **Integers only in state.** Yields, HP, strength and movement are integers. Percentages are
  integer percent; movement uses `movement.scale` sub-points per move. No floats in saved state.
- **Randomness:** stateless named streams, `rng.stream(seed, name, *keys)`, seeded by SHA-256 of
  the inputs. No generator state to save. Adding a draw in one place never shifts another.
  Bots and (later) AI use no randomness.
- **State:** plain dataclasses, JSON round-trip, canonical encoding (sorted keys, compact),
  `state_digest()` for golden tests. Dict keys in state are strings.
- **Commands:** every player action is a command dataclass. `apply_command(state, cfg, cmd)`
  validates (raising `CommandError`) and returns events. `legal_commands(...)` enumerates options.
  `pending_decisions(...)` lists what still needs the player (unit needs orders, choose
  production, choose research). `advance_turn(state, cfg)` runs the end-of-turn pipeline.
  A run is fully reproduced by seed + config + command log.
- **Explainable numbers:** every yield and every combat strength is a list of
  `(source, amount)` lines whose sum (flat) or product (percent) gives the total.
- **Data validation:** every number in a data file must sit under a mapping tagged
  `status: placeholder | calibrated` (on the value itself or on an ancestor entry). The loader
  rejects untagged numbers, unknown ids and missing required fields.
- **Fog-safe views:** `observe(state, cfg, player)` returns only what that player can know.
  Bots read only views.

## Turn pipeline

Players issue commands in any order (later: simultaneously with a timer). Then
`advance_turn`:

1. Alien phase (hook; empty until M4).
2. Each player in id order: recompute connections; each city in id order: work tiles, yields,
   growth, production; gold upkeep and deficit; research; engineer jobs.
3. Units: heal if they did not act, reset moves and attacks. Cities heal.
4. Fog memory updated. Turn counter increments.

Year shown = `time.start_year + turn // time.turns_per_year`.

## M1: map, terrain, cities, fog

- **Grid:** pointy-top hexes, odd-row offset storage (`index = row * width + col`), cube maths for
  distance. No wrap.
- **World layout:** the map is split into `region_cols x region_rows` regions, one per continent,
  separated by ocean. Default 96 x 64 tiles, about 480 land tiles per continent.
- **Continent shape:** seeded blob growth from the region centre, favouring tiles with more land
  neighbours, so shapes are compact but irregular.
- **Terrain:** base terrain (grassland, plains, desert, tundra, snow; coast and ocean for water),
  elevation (flat, hills, mountain), feature (forest, jungle, marsh). Biome regions per continent
  come from weighted Voronoi seeds (see `continents.yaml`). Mountain ranges are random walks that
  never cut the passable land in two. No rivers in v1.
- **Resources:** bonus (food, production, gold) and strategic (oil, aluminum, uranium,
  rare earths). There is no luxury class because the design has no happiness. Resource yields
  apply only once the matching improvement is built (fish need none).
- **Cities:** each continent has 20 named sites (`continents.yaml`); the first 4 are known at the
  start and the first is the capital. Sites are scored by nearby yields and placed at least
  `cities.min_distance` apart, known cities spread out first. Lost cities are dormant, empty or
  overrun by weighted draw. Starting roads join the capital to each known city.
- **City ownership:** cities always belong to the player of their continent, whoever frees them.
  Credit for freeing goes to the unit's owner. Each city owns the tiles within
  `cities.work_radius`, nearest city first. Borders are static (no tile buying in v1).
- **Fog:** three layers per player: unexplored, explored (terrain remembered, units not shown),
  visible. Vision comes from units (radius by type, +1 on hills), cities (radius, +radio tower),
  radio beacons (radius), and any improvement or route the player built (its own hex).
  The doc says units see "the hexes they stand on"; v1 uses radius 1 so units can see adjacent
  targets (tunable). Cities are remembered as last seen.

## M2: cities and economy

- **Yields:** food, production, science, gold, beacon points. Beacon points accumulate but are
  spent from M5.
- **Citizens:** each population point works one owned tile, chosen by the city's focus weights
  (balanced, food, production, science, gold). The city tile is always worked and gets a centre
  bonus. Science also comes from population.
- **Growth:** surplus food fills a store; the threshold rises with population; a negative store
  loses one population.
- **Connection:** a city produces only if it is joined to its owner's capital by an unbroken chain
  of road, railway or city tiles. A disconnected city produces nothing at all, which makes
  engineers and roads a real early priority.
- **Production:** a queue per city of buildings, units and projects (convert to gold or research).
  Overflow carries over. Gold can buy the current item outright at a multiple of its cost.
- **Buildings:** 14 in `buildings.yaml`, each with cost, maintenance, flat and percent yields, and
  extras (city strength, HP, vision, unit production).
- **Improvements:** built by engineers over several turns: farm, mine, extractor, road, railway,
  radio beacon, military base. Moving cancels the job.
- **Gold:** income minus building maintenance and unit upkeep (beyond a free allowance per city).
  If the treasury goes negative, the shortfall is taken from research progress and gold resets to 0.
- **Strategic resources:** each improved, connected strategic tile supplies its quantity. Each unit
  member that needs it uses one. A unit cannot be completed without spare supply.
- **Tech gating (pulled forward from M5):** economic, production and military trees, 7 techs
  each, with prerequisites and two cross-tree merges. Present-day techs are known at the start.
  The beacon tree arrives in M5.

## M3: units and combat

- **Units:** `units.yaml`: recon, infantry, mechanized infantry, tank, artillery, engineers,
  restoration team, destroyer, and future units (exo infantry, railgun artillery, hover tank,
  railgun cruiser). Placeholder alien units for tests and garrisons: drone, warrior, spitter,
  hive guard.
- **Movement:** sub-point movement; terrain costs; roads and railways cut cost only when both hexes
  have them; mountains impassable; land units stay on land and naval units on water (and in
  friendly coastal cities). A unit with any moves left may always enter one more hex. Friendly
  units can be passed through; a move stops on bumping into an unseen enemy. No zone of control
  and no embarkation in v1 (sea transport is M6).
- **Combat:** effective strength = base x stack size x (100 + modifiers)% x wound factor, where
  wound factor runs from 100% at full HP down to `combat.wound_floor_pct` at 0 HP.
  Damage to a side = `base_damage x ((A + D) / 2D)^2` for the defender (and the mirror for the
  attacker), times a seeded variance in `100 +/- variance_pct`, clamped. Modifiers: terrain
  defence (hills, forest, jungle, marsh), fortified, military base, flanking (+% per other friendly
  military unit next to the defender, melee only).
- **Melee:** costs the attack and all moves; both sides take damage; if the defender dies the
  attacker advances. **Ranged:** within range, target visible, no retaliation, cannot capture.
- **Cities in combat:** strength from base, population, buildings and a share of the garrison;
  HP with walls. Cities heal each turn and can bombard once per turn. A land melee unit that takes
  an alien city to 0 HP liberates it: the garrison dies, population drops, the city returns to its
  continent's player and the attacker gets the credit. Ranged attacks leave cities at 1 HP.
- **Lost cities:** a player military land unit entering a dormant city reclaims it. A restoration
  team refounds an empty city. Overrun cities hold an alien garrison and must be liberated.
- **Credit ledger:** per player: kills, units lost, liberations, reclaims, refounds, damage dealt,
  and damage dealt to each city (for split liberation credit in M7).
- **Bot:** a simple deterministic bot (`beacon/bots.py`) explores, connects cities, reclaims and
  liberates, so batch runs exercise every system. It is a test driver, not the M6 AI.

## Acceptance criteria

**M0**
- `uv run pytest -q`, `uv run ruff check .` and `uv run ruff format --check .` pass.
- The loader rejects an untagged number, an unknown id reference and a missing required field.
- An initial state round-trips through JSON to identical bytes; no floats appear in state.
- RNG streams are reproducible and independent of each other.
- `uv run python -m beacon.runner run --seed 1 --turns 5` writes a run folder.

**M1**
- Same seed gives the same map digest (golden hash); different seeds differ.
- Each continent is one contiguous landmass within 10% of its land target; passable land is
  connected; at least 18 of 20 cities placed, 4 known, capital connected by roads to each known
  city; every city at least `min_distance` from every other.
- All three lost states occur across a six-continent map.
- `observe()` hides unexplored tiles and units outside vision; exploring by moving grows memory.

**M2**
- Every yield total equals the sum of its breakdown.
- A city grows on the growth formula and starves correctly.
- A queued building completes and changes the city's yields; tech gating blocks unknown items.
- A disconnected city produces nothing; building the missing road connects it.
- A tank cannot be completed without oil supply; purchase costs and deficit rules hold.

**M3**
- Movement costs, road and rail costs, impassable terrain and one-unit-per-hex hold.
- Merge, split and stack-collapse rules hold, and a stack fights at twice the strength.
- `preview_attack()` expected damage equals the resolved damage at zero variance; ranged attacks
  take no retaliation; flanking and terrain modifiers apply.
- A melee unit liberates an overrun city; a ranged unit cannot; the ledger records the credit.
- A replay of the command log reproduces the final state digest.
- 20 seeds x 100 turns with six bot players finish deterministically, within a time budget
  recorded in `docs/ASSUMPTIONS.md`.
