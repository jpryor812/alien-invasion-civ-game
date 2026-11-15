# Balance after M10 (designer playtest changes, 2026-11-15)

Batch: `uv run python -m beacon.runner batch --seeds 1-10 --turns 100 --driver ai`.

| measure | result |
| --- | --- |
| Continents fallen | 0 of 60 |
| Player cities lost per game | 0-2 |
| Alien cities liberated per game | 12-27 (median 25) |
| Shards and remnants claimed by players per game | 14-22 |
| Barrage started by turn 100 | 3 of 10 games |
| Outcome by turn 100 | none yet (games run past turn 100, as before M10) |
| Time per 100-turn game | 16-27 s |

First contact (seeds 1-4, 30 turns, AI players): the median player met another by about turn
16, counting a player not met by turn 30 as turn 99; 7 of 24 players had not met anyone by turn
30. AI scouts do not go looking for neighbours, so a human who scouts the coast should do
better. Beacon Theory now meets everyone at once (tier 2, about 150 science).

Notes: the remnants roughly triple the shards claimed early. Cities producing without roads and
cheaper techs give AI players more to spend, without making the aliens fall faster by turn 100.
