# Balance after M12-M14 (2026-11-16)

Batches: `uv run python -m beacon.runner batch --seeds 1-10 --turns 100 --driver ai`
(M12 and M13 with the classic start; M14 with the survivor start, the new default).

| measure | M12 | M13 | M14 (survivor) |
| --- | --- | --- | --- |
| Continents fallen | 0 of 60 | 0 of 60 | 0 of 60 |
| Player cities lost per game | 0-1 | 0-2 | 0 |
| Alien cities liberated per game | 11-39 (median 25) | 13-34 (median 25.5) | 15-30 (median 22) |
| Barrage started by turn 100 | 9 of 10 | 5 of 10 | 4 of 10 |
| First town taken | - | - | all 60 bands; median turn 7; 47 by turn 10; last turn 19 |
| Outcome by turn 100 | none | none | none |
| Time per game | 21-36 s | 19-35 s | 15-27 s |

Notes:
- Announced strikes (M12) give defenders three turns: players now rarely lose cities. Heat and
  the cohort size are the levers if the aliens need more bite.
- The council (M13) elects a chair in every game; secret objectives are met by 0-1 players by
  turn 100, since most need mid-game progress.
- The survivor start delays every economy by about 7 turns and leaves each player one city at
  first, so the barrage comes later.
