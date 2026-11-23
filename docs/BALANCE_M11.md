# Balance after M11 (ocean bridges and the leader, 2026-11-15)

Batch: `uv run python -m beacon.runner batch --seeds 1-10 --turns 100 --driver ai`.

| measure | result |
| --- | --- |
| Continents fallen | 0 of 60 |
| Player cities lost per game | 0-3 |
| Alien cities liberated per game | 17-37 (median 25; M10: 12-27, median 25) |
| Barrage started by turn 100 | 7 of 10 games (M10: 3 of 10) |
| Outcome by turn 100 | none yet |
| Leader level at turn 100 | 2-7 (median 4.5) |
| Leader children per game (6 leaders) | 30, of them 7-14 hybrids |
| Hybrids voted off the council | 0-1 per game |
| Sea bridges built by AI players | 1 in 2 of 10 games, none in the rest |
| Time per 100-turn game | 20-33 s |

Notes:
- The first batch, before the family cooldown, gave about 15 children per leader in 100 turns.
  A 20-turn cooldown after each birth brings it to 5, the first at about turn 1-4.
- Leaders add +1 to every yield in every city from the start, and more as they level, plus two
  trait bonuses: the barrage now starts in most games by turn 100.
- AI players learn Robotics late (tier 3 after Applied AI), and bridge only toward an ally's
  shore they have explored, so few bridges are built by turn 100. Humans can bridge as soon as
  they have Robotics.
