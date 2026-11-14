# Balance report: M6 (AI continents, trade, aid, troops abroad)

Runs: `uv run python -m beacon.runner batch --seeds 1-20 --turns 100 --driver ai` (and `--driver bot`
for the baseline). Six players per game; characters are dealt per seed. Reproducible.

## Gates (docs/SPEC_M6.md)

| Gate | Target | AI result | |
|---|---|---|---|
| Deals made | every game | every game (16-55 accepted) | met |
| Aid given | every game | every game (121-1418 gold) | met |
| Troops abroad | at least half the games | 17 of 20 | met |
| Every continent fallen | none | 0 of 20 | met |
| AI frees at least as many cities as the bot | mean | 25.6 vs 25.4 | met |
| 100 turns | under 15 s | max 8.8 s | met |

M4/M5 bands under AI play (kept where AI play allows):

| Band | M4 gate | AI | Bot |
|---|---|---|---|
| Aliens hold 15-50% at turn 100 | 15/20 | 11/20 | 13/20 |
| Aliens take a player city | 15/20 | 15/20 | 15/20 |
| Mean alien share at turn 100 | - | 46% | 46% |
| Recruits per game | - | 32-54 | 47-73 |

## Characters (seeds 1-10, averages per player)

| Character | Players | Liberated | Reclaimed + refounded | Kills | Cities held | Cities lost | Aid gold | Units shipped | Deals proposed |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| builder | 16 | 3.8 | 5.6 | 20.8 | 13.2 | 0.2 | 182.0 | 0.9 | 60.4 |
| fighter | 15 | 5.7 | 4.9 | 22.4 | 13.1 | 0.5 | 50.8 | 3.2 | 42.7 |
| isolationist | 13 | 2.2 | 3.5 | 23.3 | 9.8 | 0.5 | 2.8 | 0.0 | 0.2 |
| trader | 16 | 5.1 | 6.6 | 20.3 | 15.6 | 0.2 | 103.8 | 2.3 | 53.4 |

## Notes

- A bot bug found here also affected the M5 runs: the bot picked the strongest ranged unit without
  checking strategic resources, so cities without oil queued rocket batteries forever. Fixed (and
  stalled queues are now replanned); the bot baseline above includes the fix.
- Aid was rare at first: the AI only helped a continent holding under half its cities. Raised to
  85% (`data/ai.yaml` aid.need_pct); at 50% a quarter of games had no aid, at 75% one game.
- Fighters and traders liberate most; isolationists hold the fewest cities and almost never trade
  or ship troops, as intended. Builders give the most aid.
- Deal counts include alliance proposals, tech swaps, resource lending and aid.
