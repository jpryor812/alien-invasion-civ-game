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

## M1: map, cities and fog

- **All six continents from M1.** DESIGN.md's M1 says "one continent"; generating six costs
  little and avoids reworking the map in M6. AI and cross-continent play are still M6.
- **Map size 120 x 72** (8,640 tiles, about twice a Civ V standard map), regions 40 x 36 per
  continent with a 3-tile ocean margin. 96 x 64 with rounder growth produced square continents.
- **Pointy-top hexes, odd-row offset storage, no wrap.**
- **Continent shapes** grow from the region centre; a frontier tile's weight is
  `1 + land neighbours` (power 1), which gives bays and peninsulas. Each continent is one
  landmass. Mountains are placed only where they leave the passable land connected, so every
  city can be reached overland.
- **Biomes** are Voronoi regions around 10 weighted seeds per continent; no latitude model yet.
- **Hills modify yields** (-1 food, +1 production) on top of the base terrain rather than
  replacing it; forest +1 production; jungle and marsh -1 food. Yields are floored at 0.
- **No rivers, lakes or islands in v1.** Oceania is one landmass like the others.
- **No luxury resources** (the design has no happiness). Gold-yielding bonus resources (coffee,
  gold ore) stand in for trade goods.
- **City sites** are scored by potential yields within radius 2 (resources counted as improved)
  plus a coastal bonus. The capital takes the best site; the other known cities are placed to be
  as far apart as possible among above-median sites; lost cities fill the rest by score with a
  seeded tie shuffle, all at least 4 hexes apart.
- **Lost-city mix** is drawn per city from weights (dormant 40, empty 25, overrun 35), so the
  number of overrun cities varies by seed. Overrun cities start with an alien hive guard in the
  city and an alien warrior beside it.
- **Starting roads** join the capital to each known city (shortest land path, avoiding lost-city
  sites so roads do not reveal them).
- **Cities belong to their continent's player** whoever frees them; the freeing unit's owner
  gets the credit. Work areas are fixed at map generation (nearest city wins), with no tile
  buying.
- **Vision radius 1** for most units (2 for recon, +1 on hills), 1 for cities. DESIGN.md says
  units see "the hexes your units stand on"; radius 0 would leave units unable to see adjacent
  attackers or targets. Tunable in `units.yaml` and `tuning.yaml`.
- **Anything a player built** (improvement or route, including starting roads) keeps its own hex
  visible to that player, per DESIGN.md section 5. Radio beacons see 2 hexes.
- **Three fog layers.** Explored tiles keep terrain and improvements; units appear only on
  visible tiles; cities are remembered as last seen.
- **Line of sight is not blocked** by hills or mountains in v1.

## M2: cities and economy

- **A disconnected city produces nothing at all**: no growth, no starvation, no production, no
  gold or science. Its buildings still cost maintenance. DESIGN.md says a city must be
  reconnected "before it produces"; the strict reading makes roads an early priority.
- **Connection** is a chain of road, railway or own-city tiles to the owner's capital. Lost
  (unowned or alien) city tiles do not conduct. Sea links and blockades are not modelled yet.
- **Citizens** are assigned automatically each turn by the city's focus weights (no manual tile
  picking yet). The city tile is always worked and gets a centre bonus (+1 food, +2 production,
  +1 science, +1 gold). Balanced focus weighs food and production equally: with food weighted
  higher, grassland cities sat at 1 production.
- **Science per citizen** is 50% (rounded down per city), since buildings add more later.
- **Percent bonuses** from buildings apply to the city's flat subtotal of that yield, one line
  per building, each rounded down; the total is the sum of the lines.
- **Growth threshold** = 15 + 6(p-1) + (p-1)^2. A negative food store loses one citizen
  (minimum 1) and resets the store to 0. No food carry-over bonuses yet.
- **Production carries over** after completion; with an empty queue it keeps accumulating.
  A queued item that becomes invalid is dropped when it would complete. A unit that has no room
  to be placed or no spare strategic resource stalls the queue (production keeps accumulating).
- **Projects** (wealth, research) convert 50% of production to gold or science each turn while at
  the head of the queue.
- **Purchase** costs 200% of the item's production cost regardless of progress, completes
  immediately, and requires a connected city.
- **Gold**: income minus building maintenance and unit upkeep (1 gold per unit member beyond two
  free per active city). A negative treasury resets to 0 and the shortfall comes out of research
  progress before this turn's science is added.
- **Science with no research chosen** is banked in research progress (Civ-style overflow).
- **Strategic resources**: an improved strategic tile in a connected city's work area supplies
  its quantity; each unit member that needs it uses one. Supply is checked when a unit would
  complete or be bought, not when it is queued.
- **Beacon points** accumulate per player from beacon yields (none yet); they are spent from M5.
- **Tech gating pulled forward** (DESIGN.md M5 lists the trees): three trees of 7 techs; tier 0
  (present day) known at start. Several late techs unlock nothing yet; their effects belong to
  later milestones (trade, beacons).
- **Engineers** build one improvement at a time on their own hex; the job takes the listed turns
  and ends when the counter reaches 0 at the end of a turn. Moving cancels it (M3). Improvements
  cannot go on city hexes (they already count as roads) and do not remove features.
- **Starting buildings**: the capital has a food depot, workshop, market and school; other known
  cities a food depot. Starting gold 100.
