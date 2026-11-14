# Spec: milestone M5, beacons, recruits and councils

Status: approved and being built (2026-11-13). Source: DESIGN.md sections 7-8, the designer's
decisions below, and the proposed content in the `additional` blocks of `data/*.yaml`
(commit 0b79762). Numbers live in `data/aliens.yaml` (`recruits` section), `data/techs.yaml` and
`data/buildings.yaml`, all `placeholder`.

## Designer decisions (2026-11-13)

- Promote the proposed `additional` content (units, buildings, improvements, techs, alien techs,
  the recruit pool) into play.
- Recruits live 50-100 turns; some are immortal. The trait list is fixed (the 11 committed
  traits).
- Councils: two seats for each domain (food, production, military, science, beacon) and three
  general seats. A recruit on a domain seat applies its score in that domain; one recruit may sit
  on several domain seats (one seat in each domain where it scores). A recruit on a general seat
  applies all its scores.
- Two beacon levers, five levels each, with steeply rising costs: speed (how often recruits
  arrive) and rarity (how strong they are).
- Betrayal never sabotages a city: a betraying recruit leaves and joins an alien city.

## 1. Promoted content

All `additional` entries move into the active tables and the `additional` blocks go away. Effects
that need later systems are inert for now and say so in their notes: the medical team's healing,
the nanorepair crew's repairs, marines' amphibious landing (M6), and the logistics hub's trade
role (M6).

## 2. Recruit domains and scores

A recruit has a score in each of five domains: food, production, military, science, beacon. The
proposed pool used gold; gold maps to **military** (the proposed scores follow the old design's
"military, science, production, beacon").

- **Effect of a score of N** in a domain: +N% to that domain for the patron player. Food,
  production, science and beacon add N% to every city's yield; military adds N% to every unit's
  combat strength. Shown as `council:<recruit>` lines in the breakdowns.
- **Points**: a basic recruit's scores sum to the rarity level's budget; the character type
  spreads them over its focus domains with seeded rolls. Traits with `yield_pct` scale the
  recruit's own score in that domain (a scholar's science x 1.25).
- **Legendary recruits** (4, fixed scores) can arrive from rarity level 3.

## 3. Beacon levers (five levels each)

- **Speed**: the beacon building chain in a city, Beacon I-V. Each level needs the previous one,
  costs roughly double, and adds beacon points per turn. Beacon points accumulate per player.
- **Rarity**: five beacon-tree techs (the fourth tree, researched with science). Each level
  raises the beacon points a recruit costs (steeply), the recruit budget, the legendary chance and
  the immortal chance.
- When a player's beacon points reach the arrival cost at their rarity level, a recruit arrives
  and the cost is paid. Both levers together give frequent strong recruits at a steep price.

## 4. Lifespans and traits

- Each character type has a lifespan range inside 50-100 turns; `short_lived` and `cautious`
  shift it, and the result is clamped to 50-100. Immortal recruits never die of age.
- A recruit gets one or two traits from its character type's list (seeded). The immortal trait
  comes only from the rarity level's immortal chance, or from legendary recruits.
- Effects: `yield_pct` (scales the recruit's scores), `lifespan_delta`, `betrayal_permille` (sum
  of traits, per turn), `immortal`, and `sale_pct` (greedy: +25% gold when the recruit is
  sold, replacing its gold `yield_pct`, since gold is not a domain).

## 5. Councils

- Seats: two per domain, three general. Command `seat_recruit(recruit, seats)` where seats is
  either `["general"]` or a list of domains in which the recruit has a positive score. A recruit
  cannot be on general and domain seats at once. `unseat_recruit` frees all its seats.
- Recruits not seated give nothing.

## 6. Keep, sell, gift

- `offer_recruit(recruit, to_player, price)`: a gift when the price is 0. The recipient answers
  with `accept_offer(offer)` or `decline_offer(offer)`; on acceptance gold moves and the recruit
  changes patron, leaving its seats. Offers lapse at the end of the turn. This is the minimal
  trade needed now; full trade comes in M6.
- Credit ledger: `recruits_gained`, `recruits_given` (gifts), `recruits_sold`.

## 7. Death and betrayal

- At the end of each turn, a mortal recruit whose age reaches its lifespan dies.
- Each turn a recruit with betrayal chance may betray: it leaves its patron and joins the
  nearest alien city on the patron's continent (else any alien city), adding its military score
  as strength percent to that city. If no alien city exists, it simply leaves. Liberating that
  city frees the recruit, who joins the liberating player.

## 8. Bot

The test bot researches the beacon tree from mid-game, builds a beacon in its capital, seats
recruits greedily (best score per domain seat, the most balanced recruits on general seats),
gifts recruits it cannot seat to the player with the fewest recruits, and accepts offers it can
seat and afford.

## Outcome (2026-11-13)

Built. All acceptance criteria met: 91 tests pass; over 20 seeds x 100 turns the alien-share
band is 10/20 (M4: 13), captures 15/20, all-fallen 0/20, 40-76 recruits arrive per game with
3-15 betrayals, and the slowest game takes 5.8 s. See `docs/ASSUMPTIONS.md` (M5).

## Acceptance criteria

- The promoted content loads and validates; no `additional` blocks remain.
- Unit tests: arrival when beacon points reach the cost; rarity raises the budget and cost;
  scores sum to the budget and respect focus and traits; lifespans in 50-100 and immortals
  never age out; seat limits and the domain/general rules; council bonuses appear in yield and
  combat breakdowns; offers, gifts and sales move gold and recruits; betrayal moves a recruit to
  an alien city and liberation brings it back; reproducibility.
- The 20-seed x 100-turn batch still meets the M4 capture and all-fallen bands, the alien-share
  band stays within 3 seeds of M4's 13/20, recruits arrive in every game, and a 100-turn game
  stays under 12 s.
