# Balance report: M4 (the aliens)

Run: `uv run python -m beacon.runner batch --seeds 1-20 --turns 100` with six test bots, data as
committed with M4. Reproducible: the same command gives identical digests.

## Gate (docs/SPEC_M4.md)

| Band | Target | Result | |
|---|---|---|---|
| Aliens hold 15-50% of their starting cities at turn 100 | at least 15 of 20 seeds | **13 of 20** | not met |
| Aliens take at least one player city | at least 15 of 20 seeds | 16 of 20 | met |
| Every continent fallen at turn 100 | at most 2 of 20 seeds | 0 of 20 | met |
| A 100-turn game | under 12 s | 3.5-5.4 s | met |

Mean alien share at turn 100: 39% (inside the band). The seven misses are both tails: five
seeds above 50% (seeds 5, 13, 15, 19, 10 at 52-69%) and two where players almost wipe the aliens
out (seeds 16 and 14 at 0% and 5%).

## Results

| Seed | Alien cities (start → T100) | Ratio | Liberated | Player cities lost | Fallen | Time (s) |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 36 → 16 | 44% | 27 | 5 | 0 | 4.1 |
| 2 | 36 → 11 | 30% | 31 | 1 | 0 | 5.4 |
| 3 | 36 → 16 | 44% | 21 | 1 | 0 | 4.5 |
| 4 | 36 → 15 | 41% | 24 | 1 | 0 | 3.7 |
| 5 | 36 → 19 | 52% | 25 | 1 | 0 | 3.5 |
| 6 | 36 → 15 | 41% | 27 | 2 | 0 | 3.9 |
| 7 | 36 → 10 | 27% | 29 | 0 | 0 | 5.1 |
| 8 | 36 → 16 | 44% | 28 | 2 | 0 | 3.7 |
| 9 | 36 → 14 | 38% | 29 | 1 | 0 | 4.5 |
| 10 | 36 → 25 | 69% | 20 | 1 | 0 | 4.4 |
| 11 | 36 → 13 | 36% | 28 | 1 | 0 | 4.8 |
| 12 | 36 → 10 | 27% | 31 | 0 | 0 | 4.7 |
| 13 | 36 → 21 | 58% | 24 | 3 | 0 | 4.1 |
| 14 | 36 → 2 | 5% | 40 | 2 | 0 | 5.3 |
| 15 | 36 → 22 | 61% | 22 | 4 | 0 | 3.9 |
| 16 | 36 → 0 | 0% | 38 | 0 | 0 | 5.4 |
| 17 | 36 → 15 | 41% | 27 | 2 | 0 | 4.6 |
| 18 | 36 → 11 | 30% | 29 | 2 | 0 | 4.3 |
| 19 | 36 → 22 | 61% | 23 | 1 | 0 | 3.7 |
| 20 | 36 → 8 | 22% | 30 | 0 | 0 | 4.3 |

## What moved the numbers (18 tuning runs)

| Change | Effect |
|---|---|
| First pass (no cap on alien units, high decay) | aliens fielded 800 units and took every city by turn 30; 130 s per game |
| Alien army capped by city count; 8-turn grace before sieges | aliens 79/40 cities, players never liberated |
| Softer hive guard (55 to 40), fortress base (10 to 4), garrison share (50 to 30%); stronger starting armies (3 infantry, 2 artillery) | still no liberations: bot armies stalled |
| Engine fix: a move blocked by a friendly unit now routes around it | armies reach targets |
| Bot: melee attacks cities on a good trade; garrisons only near aliens; idle soldiers explore; 2 scouts | liberations 0 to ~25 per game |
| Cities that took damage this turn do not heal | sieges finish |
| Lower lost-city decay (cap 0.4% per turn, time-based only) | decay ~20 to ~3 cities per game |
| Hardening scaled by the share of cities lost | small invasions hold out longer |
| **Lost-city states by exact quota** (every seed starts with 36 alien cities, not 20-46) | in band 10 to 17; the biggest single source of spread was the starting count |
| Alien army cap 100 / 110 / 120% of cities | in band 17 / 13 / 10, captures 13 / 16 / 19: the two gates pull against each other |

The committed setting is 110%, the only one tried that passes the capture gate with the most seeds
in band.

## Reading the result

- The failing tails are driven by the test bot, not the rules: in seeds 14 and 16
  the bots chain liberations across a whole continent, and in seeds 10, 15 and 19 a continent's
  armies get stuck behind mountains or raids. A stronger M6 AI will narrow the spread.
- Results swing a lot with small changes (grace 8 to 4 moved the mean from 39% to 58%), so the
  balance is fragile and worth rechecking after every milestone.
- Players lose few cities (0-5 per game). Aliens threaten, but rarely break a garrisoned city.
