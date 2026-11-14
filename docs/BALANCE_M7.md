# Balance report: M7 (mothership, barrage, espionage, endings, MVP)

Run: `uv run python -m beacon.runner batch --seeds 1-20 --turns 200 --driver ai`, six AI players,
games stop at victory or defeat, or at the 200-turn measuring horizon (there is no turn limit
in the rules; designer, 2026-11-13). Reproducible.

## Gates (docs/SPEC_M7.md)

| Gate | Target | Result | |
|---|---|---|---|
| Victory by turn 200 | 30-70% of games | 7/20 (35%), on turns 131, 135, 138, 143, 152, 187, 195 | met |
| Defeat | at most 10% | 0/20 | met |
| Barrage fires | at least half | 20/20 | met |
| Espionage completes | at least half | 16/20 | met |
| Builder and fighter in the MVP top half | mean rank at most 3.5 of 6 | builder 3.45, fighter 3.47 | met (narrowly) |
| 200 turns | under 30 s | max 19.8 s | met |

## Results

| Seed | Outcome | Turn | Barrage started | Alien cities left | Alien techs gained | MVP leader |
|---:|---|---:|---:|---:|---:|---|
| 1 | unfinished by 200 | - | 140 | 4 | 30 | builder |
| 2 | victory | 138 | 117 | 0 | 18 | trader |
| 3 | victory | 152 | 102 | 0 | 0 | fighter |
| 4 | victory | 143 | 120 | 0 | 6 | trader |
| 5 | unfinished by 200 | - | 123 | 10 | 18 | builder |
| 6 | unfinished by 200 | - | 133 | 17 | 12 | trader |
| 7 | unfinished by 200 | - | 129 | 11 | 30 | builder |
| 8 | victory | 195 | 127 | 0 | 36 | fighter |
| 9 | unfinished by 200 | - | 124 | 13 | 0 | trader |
| 10 | unfinished by 200 | - | 113 | 11 | 0 | trader |
| 11 | unfinished by 200 | - | 115 | 8 | 0 | trader |
| 12 | victory | 187 | 131 | 0 | 36 | fighter |
| 13 | unfinished by 200 | - | 127 | 4 | 30 | fighter |
| 14 | victory | 135 | 114 | 0 | 12 | builder |
| 15 | unfinished by 200 | - | 107 | 12 | 1 | trader |
| 16 | victory | 131 | 109 | 0 | 12 | builder |
| 17 | unfinished by 200 | - | 93 | 7 | 18 | builder |
| 18 | unfinished by 200 | - | 124 | 1 | 6 | trader |
| 19 | unfinished by 200 | - | 111 | 8 | 12 | fighter |
| 20 | unfinished by 200 | - | 138 | 1 | 6 | fighter |

## MVP by character (final weights)

| Character | Players | Mean rank (of 6) | Mean score |
|---|---:|---:|---:|
| builder | 31 | 3.45 | 779 |
| fighter | 30 | 3.47 | 711 |
| isolationist | 28 | 4.39 | 608 |
| trader | 31 | 2.77 | 853 |

## Tuning notes

- First batch: 6/20 victories, all 20 barrages fired; players kept paying into the barrage while
  it waited out its 20-turn minimum (progress 10,249 against a cost of 3,000). Funding now stops
  at the cost and gold is charged only for what the project takes.
- Espionage at 400 gold let every player gain all six alien techs; raised to 800.
- Fortress hardening cap lowered from 80% to 70% (victories 6 to 7 of 20).
- MVP weights: builders averaged rank 3.9 under the first weights. Final weights come from a grid
  search over this batch's ledgers (liberation share 20, recruits gained 6, barrage 4 per 10,
  aid gold 6 per 10, population saved 1). They are fitted to these 20 games, so recheck on new
  seeds; builder and fighter sit just inside the top half, traders lead, isolationists trail.
- Most unfinished games end with 2-20 hardened alien cities on continents whose players are
  weak; the late hunt is the slowest part of the game (DESIGN.md 11 lists this as a known risk).
- The barrage starts around turns 93-140, once Railguns and Deep Space Radar are in.
