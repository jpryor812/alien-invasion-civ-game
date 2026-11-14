# Spec: milestone M7, mothership, barrage, espionage, endings and MVP

Status: approved to build (2026-11-13, "go ahead with M7"). DESIGN.md sections 10-12 give the
rules; where they leave a detail open, the default below is used and listed under **Defaults to
review**. Numbers live in `data/tuning.yaml` (`endgame`), `data/techs.yaml`, `data/mvp.yaml`.

## 1. The mothership

- **Strikes**: while the mothership is alive, each turn it strikes one player city with chance
  `strike_permille` per thousand. The target is seeded, weighted toward the barrage host city once
  the project is under way ("the aliens learn where it is being developed"). A strike leaves the
  city at `strike_hp_pct` of its HP (at least 1) and kills `strike_pop_pct` of its population.
- **Reinforcements** (since M4) stop for good once any player researches the barrage tech
  (DESIGN.md 11: "researching it can stop reinforcements").
- **Destroyed** when the barrage fires: strikes and reinforcements end. Alien cities keep growing
  and researching.

## 2. The world barrage (shared megaproject)

- Tech **Orbital Barrage** (military tier 5, prerequisites Railguns and Deep Space Radar) is the
  research half.
- Any player who knows it starts the project in one of their connected cities (`start_barrage`).
  There is one barrage per game. Any player who knows the tech contributes:
  - production: a city with `project:barrage` at the head of its queue sends all its production;
  - gold: `fund_project` converts gold at `gold_to_progress_pct`.
- **Firing**: the barrage fires when progress reaches its cost **and** at least `min_turns` have
  passed since it started ("a fixed number of turns"). It needs the host city in player hands; if
  aliens take the host city, the project pauses until the city is freed.
- **Defended megaproject**: the director scores the host city far higher as a siege target, and
  mothership strikes favour it.

## 3. Finding the last alien cities

DESIGN.md 12 asks for late-game tools so the final hunt is not a chore:

- **Deep Space Radar** (existing production tech) reveals every alien-held city to the player
  who knows it, now and whenever a city falls.
- **Beacon rarity 5** (Stellar Chorus) does the same. A recruit network that strong hears every
  hive.

## 4. Alien espionage (DESIGN.md 10)

- `start_espionage(mode)` opens an operation:
  - **solo**: only the starter funds it and only the starter gets the reward;
  - **shared**: anyone can fund it and every player gets the reward.
- Gold funds operations (`fund_project`). An operation completes at `espionage_cost`.
- **Reward**: three alien techs offered at random from the alien tree (techs no recipient knows).
  The largest contributor chooses one with `choose_espionage_tech`; if they have not chosen by the
  end of the next turn, the first offered is taken.
- **The alien tree**: six techs that research cannot reach. Each unlocks one unit or building
  (xeno troopers, plasma lancers, bio-reactors, phase scanners, translation hubs, chitin
  bulwarks).
- No espionage between players.

## 5. Endings (DESIGN.md 12)

- **Victory**: the mothership is destroyed and no alien city remains, in either order. The game
  ends on the turn the second is met.
- **Defeat**: all six continents fallen at once.
- **Turn limit** (`time.max_turns`, 200): the game ends without a win.
- The outcome and its turn are stored on the state. The runner stops at an outcome.

## 6. MVP score

Each player's score is a weighted sum of credit-ledger entries (`data/mvp.yaml`), shown line by
line:

| Entry | Source |
|---|---|
| Aliens killed | kills |
| Cities liberated | a share per liberation, split by the damage each player dealt to the city |
| Cities reclaimed and refounded | reclaims and refounds |
| Population saved | population of every city the player freed, reclaimed or refounded |
| Aid | aid gold, aid units, aid techs, recruits given |
| Units abroad | unit-turns spent on another continent |
| Alien contribution | recruits gained and espionage gold |
| Barrage | production and gold put into the barrage |

The game reports a ranking whatever the outcome ("scores still show how each player played").

## Outcome (2026-11-13)

Built. All gates met (see `docs/BALANCE_M7.md`); 119 tests pass. Changes after the first batch:
barrage funding capped at its cost, espionage cost 800, fortress cap 70%, MVP weights refitted.

## Defaults to review

1. **Turn limit**: 200 turns without victory ends the game unfinished, which is not a win; scores
   still rank. (DESIGN.md 18 leaves this open.)
2. **Strike strength**: 2.5% chance per turn; the city drops to 40% HP and loses 25% of its
   population.
3. **Barrage**: costs 3,000 progress; at least 20 turns from start to firing; gold converts at
   50%.
4. **Espionage**: an operation costs 800 gold; three techs offered (400 let every player gain all six).
5. **Weights**: chosen so that builder and fighter characters both average in the top half
   (DESIGN.md 12).

## Acceptance criteria

- **Unit tests**:
  - strikes and their targeting;
  - reinforcements stop on research;
  - barrage start, contributions, minimum turns, pause while the host is lost, and firing;
  - radar reveal;
  - espionage, both solo and shared, including the choice and its default;
  - victory in either order, defeat, and the turn limit;
  - MVP lines sum to the total, and liberation credit splits by damage;
  - replay is exact.
- **Batch**: 20 seeds, up to 200 turns, six AIs. Targets:
  - victory in 30-70% of games;
  - defeat in at most 10%;
  - the barrage fires in at least half the games;
  - espionage completes in at least half the games;
  - fighter and builder characters both average in the top half of the MVP ranking;
  - a 200-turn game under 30 s.
- Report in `docs/BALANCE_M7.md`.
