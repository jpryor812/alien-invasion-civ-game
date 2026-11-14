# Spec: milestone M6, AI continents, trade, aid and troops abroad

Status: **draft for designer review** (2026-11-13). Nothing here is built. Items marked
**DECIDE** need the designer; each has a proposed default the build will use if approved.
Source: DESIGN.md section 6 (troops abroad), section 13 (rescuing fallen continents), section 14
(trade and diplomacy), section 15 (AI). All six continents and their players already exist.

## Goal

Make the six continents depend on each other. Until now each player has fought alone with the
test bot. After M6, deterministic AI players with distinct characters trade, send aid and ship
troops to help each other, and one seat can be left for a human driving the game through
commands.

## 1. Players: human and AI

- Each player is `human` or `ai` (new `Player.controller`). The runner fills AI seats; a human
  seat waits for commands from outside (the later web client). Default single-player setup: one
  human, five AI, per DESIGN.md section 3. Batch runs use six AI players.
- The AI uses the same commands and fog-safe view as everyone else and **no randomness**.
- **Characters** (DESIGN.md 15): builder, fighter, trader, isolationist. Each is a set of weights
  in `data/ai.yaml`: production split (military, buildings, beacons), research tree preferences,
  how much it trades, how readily it sends aid and troops, and how much risk it accepts in attacks.
  - **builder**: economy and beacons first, defends well, sends gold aid.
  - **fighter**: large army, liberates aggressively, sends troops abroad.
  - **trader**: ports early, makes many deals, sells recruits.
  - **isolationist**: defends its own continent, rarely trades or helps until things get bad.
- **DECIDE (character assignment):** *default: drawn per seed on the `map` stream, so the five AI
  continents get at least three different characters.*
- The test bot stays as a simple baseline: batches compare AI against it.

## 2. Diplomacy is cooperative

No war between players (DESIGN.md 14). Diplomacy has three parts:

- **Deals** (section 3): trading goods, gold and help.
- **Aid** (section 4): gifts of gold, units and recruits, which count toward the MVP score.
- **Alliances:** a standing agreement between two players.
  - **DECIDE (alliance effect):** *default: allies share vision (each sees what the other's units
    and cities see) and can enter each other's cities.*

## 3. Trade

### What can be traded

| Item | Detail |
|---|---|
| Gold | a lump sum, or per turn for 10, 20 or 30 turns |
| Strategic resources | lend N units of a resource for a duration; the receiver's supply rises and the sender's falls |
| Technology | give a tech the receiver can research now (prerequisites met) |
| Recruits | already possible since M5 (offers) |
| Units | hand over a unit standing in or next to the receiver's city |

### Deals

- A deal is a proposal: the proposer's items for the receiver's items. The receiver accepts or
  declines; proposals lapse at the end of the turn.
- Per-turn parts run for their duration and stop if either side can no longer pay.
- AI players value items by character (for example, a fighter values oil highly).

### Delivery: ports and the overland leg

DESIGN.md 14: trade between port cities is safe and quick, with a short delay that grows with
distance; overland trade is at risk and needs an escort.

- **Sea leg:** goods (gold, resources, techs, recruits) travel between the two players'
  connected Port cities, arriving after `ceil(sea distance / shipping speed)` turns. The sea is
  safe because aliens never cross water.
- **Overland leg:** a player without a connected port sends goods as a **convoy unit** (civilian)
  from its capital. The convoy must physically reach a coastal city before the sea leg starts.
  - Aliens can capture an unescorted convoy, like any lone civilian.
  - A military unit on the same hex escorts it.
- **DECIDE (convoys):** *default: yes, build the overland convoy as described. The lighter
  alternative is to require a port to trade at all.*

## 4. Aid

- **Gifts:** gold, units and recruits given with nothing in return.
- **Credit:** gifts count toward the giver's MVP credit (new ledger keys `aid_gold`,
  `aid_units`), alongside the existing `recruits_given`.
- **AI aid:** AI players give to the weakest continent according to character. A fallen
  continent (DESIGN.md 13) is the top priority for rescue.

## 5. Troops abroad

DESIGN.md 6 says troops can serve on another continent. They keep their owner, so kills and
liberations count for that owner, and moving them costs transport and upkeep.

- **Shipping:** a land unit in one of its owner's coastal cities is sent with
  `ship_unit(unit, destination)`.
  - The destination is any friendly coastal city on another continent: the player's own, an
    ally's, or any player's (**DECIDE**, below).
  - Shipping costs gold by distance. The unit is off the map for `ceil(sea distance / shipping
    speed)` turns, then appears in or next to the destination city.
- **Upkeep:** units abroad cost extra upkeep (`abroad_upkeep_pct`).
- **Liberation abroad:** cities freed abroad still go to the continent's owner, and the credit
  goes to the liberator. Both rules exist since M3.
- **Rescue:** if a fallen continent's player has no cities, foreign troops can still land at an
  empty or dormant city. That city is reclaimed for the fallen player, and the continent
  revives weak.
- **DECIDE (who can host troops):** *default: any player's coastal city, with no alliance
  needed, since nobody is at war.*
- **DECIDE (naval units and embarking):** *default: still no naval combat and no units on the
  water. Shipping is abstract and takes turns. Naval units stay as coastal defence and
  bombardment.*

## 6. Turn order with many actors

All players' commands apply as they arrive within a turn: AI players act in player-id order, and
a human acts whenever they act. The end-of-turn pipeline then resolves shipping arrivals,
per-turn deal payments, then the existing phases. Real simultaneous multiplayer with a timer is a
later client and server concern, and the simulation does not change for it.

## 7. Data and state

- `data/ai.yaml`: character weights and AI thresholds.
- `data/tuning.yaml`: trade, shipping and aid tunables.
- New state: `Player.controller`, `Player.character`, `Player.allies`, `GameState.deals` (proposed
  and active), `GameState.shipments` (goods and units in transit). All of it serialises like
  everything else.

## Acceptance criteria

- **Unit tests:**
  - Deals: propose, accept, decline, lapse. Per-turn payments run and stop.
  - Resources: lending moves strategic supply.
  - Tech gifts respect prerequisites.
  - Delivery: port delay grows with distance; convoys are needed without a port, can be
    captured, and are protected by escorts.
  - Troops abroad: shipping costs and delays; abroad units keep their owner and credit; extra
    upkeep applies.
  - Rescue: troops can rescue a fallen continent.
  - Alliances share vision.
  - The AI uses no randomness and acts only through commands.
  - Replay of a mixed human and AI game is exact.
- **Batch** (20 seeds x 100 turns, six AI players). The M4 and M5 bands hold, where AI play
  allows. Also:
  - deals are made in every game;
  - aid is given in every game;
  - troops serve abroad in at least half the games;
  - no game ends with all six continents fallen;
  - AI continents free at least as many cities on average as the test bot;
  - every game hits 100 turns in under 15 s.
- **Report:** `docs/BALANCE_M6.md` compares the four AI characters and the bot.

## Out of scope for M6

The mothership, the barrage project and the victory and defeat checks (M7); alien espionage and
other shared projects (M7); MVP scoring (M7); the web client (M8); naval combat.
