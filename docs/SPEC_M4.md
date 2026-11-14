# Spec: milestone M4, the aliens

Status: **draft for designer review** (2026-11-13). Nothing here is built yet. Numbers will live
in a new `data/aliens.yaml` (all `placeholder`). Items marked **DECIDE** need the designer;
each has a proposed default that the build will use if approved as written.

Source: DESIGN.md section 9 (the aliens), section 5 (lost cities fall over time), section 13
(fallen continents). The mothership's missile strikes and the barrage project stay in M7.

## Goal

Turn the aliens from passive garrisons into an opponent that grows, researches, attacks,
retakes cities and reacts to how the players are doing, so the cooperative game has real
pressure. M3's batch shows the gap: with passive aliens, bots free nearly every city by turn 100.

## 1. Alien state

A new `AlienState` in `GameState` (serialised like everything else):

- `progress`: points accumulated toward the next alien tech.
- `techs`: alien techs gained so far.
- `reinforcement_store`: points toward the next mothership landing.
- `surge_cooldown`: turns until another surge may fire.
- `orders`: the director's current objective per alien unit group (see section 5).

Alien cities keep using the `City` record (owner `aliens`, status `overrun`).

## 2. The tipping point: alien progress

Each turn the aliens gain progress:

```
progress += max(floor, base + per_city x alien_cities + per_pop x total_alien_pop)
```

- More cities mean faster progress, so liberating cities slows them (DESIGN.md 9).
- `floor` stops them from stalling when they are nearly beaten.
- Early game they hold about a third of all cities, so they progress quickly early, as the
  design asks.

## 3. Alien tech tree

Its own short track (about 8 techs) bought in order with `progress`, each costing more than the
last. Effects, all data-driven:

| Kind | Example effect |
|------|----------------|
| Units | unlock stronger alien units (drone, warrior, spitter, then brute, hive titan) |
| Walls | + city strength and HP for alien cities |
| Mines | + alien production per city |
| Growth | faster alien city growth |
| Regeneration | alien units heal more per turn |

The tree is fixed in v1, so its order is predictable; a seeded order is an option later.

## 4. Alien cities and spawning

- **Growth:** alien cities grow on their own simple food rule (no tiles worked) up to a cap that
  alien techs raise.
- **Spawning:** each alien city builds **alien production** per turn (from population and
  techs) and spends it on the best unlocked unit when it has room. A garrison is always rebuilt
  first.
- **Fortresses** (DESIGN.md 9, "as they shrink they harden"): every alien city gains
  `+fortress_pct` strength per city the aliens have lost since the start, up to a cap.
- **Reinforcements** (DESIGN.md 9 and 11): the mothership fills `reinforcement_store` each turn.
  When full, a group lands at a seeded alien city (or, with none left on a continent, on open
  land at least `landing_distance` from player cities). Reinforcements never stop in M4; the
  M7 barrage project stops them.
- **DECIDE (new cities):** aliens only ever hold the 120 named city sites; they do not found new
  ones. *Default: yes, named sites only.*

## 5. The invasion director

A deterministic planner that runs in the alien phase of the turn pipeline (the hook already
exists). Each turn it:

1. Scores every player city it knows of: low defence, low HP, few nearby defenders and high
   value (population, capital, recently liberated) score higher.
2. Assigns idle alien units to groups and gives each group one objective: **garrison** (keep
   each alien city defended), **siege** (gather, then attack a target city), **raid** (pillage
   roads and improvements to cut connections), or **retake** (a recently liberated city).
3. Moves and attacks with the same commands players use (attack previews, paths). A siege group
   waits until its combined strength clears `siege_ratio_pct` of the target's before it attacks.

Randomness: the director draws only from the `events` stream (seeded per turn) to break ties
and vary targets; unit movement itself is deterministic.

- **DECIDE (alien knowledge):** aliens see the whole map, including player units, so the
  director never needs scouting. Player fog is unchanged. *Default: aliens see everything (much
  simpler; the design's "aliens roam in fog" is about what players see).*
- **DECIDE (pillage):** an alien unit on a hex with a player-built improvement or route may spend
  its turn destroying it, which can disconnect cities. *Default: yes.*
- **Water:** aliens never cross water (DESIGN.md 3 and 18, assumed).

## 6. Lost cities fall over time

DESIGN.md 5: the longer you take to reach a city, the likelier it becomes overrun. Each turn,
each dormant or empty city that no player has reclaimed has a chance to become overrun:

```
chance_pct = base_pct + per_turn_pct x turn + near_pct x (alien cities within near_radius)
```

capped at `max_pct`. A city with a player military unit within `guard_radius` is safe. When it
falls, it gets a fresh alien garrison. Draws come from the `events` stream keyed by turn and
city, so they are reproducible.

## 7. Aliens taking player cities

Already supported by M3 combat: a land melee alien unit that takes a player city to 0 HP
overruns it. M4 adds:

- Player units on the hex die; the city keeps 50% of its population and loses its queue.
- If the capital falls, the player's largest remaining connected city becomes the capital
  (otherwise nothing produces). With no city left, the player has no capital.
- Each overrun city records which players had defended it (for the M7 MVP score).

## 8. Fallen and revived continents (DESIGN.md 13)

- A continent is **fallen** when its player holds fewer than `fall_threshold` cities; it
  **revives** when it climbs back to the threshold. Both are recorded as events and on the
  player (`fallen: bool`, `times_fallen`).
- A fallen player keeps playing (DESIGN.md 13). No other effect in M4; scoring and defeat rules
  use it in M7.
- **DECIDE (threshold):** *Default: fewer than 2 cities.*

## 9. Surges (anti-coasting)

When the aliens are losing fast, a surge lands extra units next to the continent with the most
liberations (DESIGN.md 9, "keep a winning player from coasting"):

- Triggers: alien cities below `surge_city_pct` of their starting count, or one player
  liberating `surge_lead` more cities than the average.
- Lands `surge_size` units of the best unlocked type on open land near that player's frontier,
  then waits `surge_cooldown` turns.

## 10. Bot updates

The test bot needs to defend, or batch numbers mean nothing: keep a garrison in every city,
bombard with cities, retreat damaged units, rebuild roads cut by pillage, and send help to a
threatened city on its own continent. It remains a test driver, not the M6 AI.

## Acceptance criteria

- Unit tests:
  - Progress follows the formula, including the floor.
  - Alien techs unlock in order and their effects apply.
  - Fortress bonus grows as cities are lost.
  - Reinforcements land on schedule.
  - Lost cities fall at the configured chance and never while guarded.
  - An alien siege takes an undefended player city; capital succession works.
  - Pillage cuts a connection.
  - Fallen and revive events fire at the threshold.
  - The director never moves across water and is fully reproducible.
- Determinism: replaying the command log plus seed reproduces the final digest (aliens act in
  the pipeline, not through the log).
- **Balance bands** (20 seeds x 100 turns, six bots), reported in `docs/BALANCE_M4.md`:
  - aliens still hold 15-50% of their starting city count at turn 100 in at least 15 of 20 seeds;
  - aliens take at least one player city in at least 15 of 20 seeds;
  - no more than 2 of 20 seeds end with every continent fallen.
- **DECIDE (bands):** these are proposed targets to tune toward, since bots are weaker than
  people. *Default: use them as the gate; tune `aliens.yaml` until they pass.*
- Performance: a 100-turn game stays under 12 s on this machine.

## Out of scope for M4

Mothership missile strikes and the barrage (M7), beacons and alien recruits (M5), AI players,
trade and cross-continent troops (M6), alien espionage (M7 or later), the defeat rule (M7).
