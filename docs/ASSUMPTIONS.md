# Assumptions

Every modelling choice not fixed by `DESIGN.md`, with the reason. Numbers themselves live in
`data/*.yaml` (all `placeholder` unless noted); this file records the *shape* of the rules.

## M0: foundation

- **Package name `beacon`** (the working title). Data in `data/`, runs in `runs/` (git-ignored).
- **Integers only.** State and data hold no floats. Percentages are integer percent, rounded down
  at the point of use; movement uses `movement.scale` (30) sub-points per move so road (1/3) and
  rail (1/10) costs are exact. Reason: byte-identical results on every platform.
- **Stateless random streams** (`beacon/rng.py`): each draw site builds a generator from a SHA-256
  hash of (seed, stream, keys). No generator state is saved, and adding a draw never shifts
  another. Streams: `map`, `cities`, `combat`, `events`. Bots and AI never draw.
- **Tagging rule relaxed for tables.** A number must sit inside a mapping tagged with `status`,
  either on the value (`{value, status, note}`) or on its enclosing entry (a unit, a building).
  Reason: per-field tags on every unit stat would bury the tables. Tuning values keep per-value
  tags and notes.
- **Commands** are frozen dataclasses with a `kind`; a game is reproduced by seed, config and the
  command log. Player ids are continent ids; aliens use the owner id `aliens`.
- **City ids are list indices** (cities are never deleted); unit ids come from a counter and units
  are stored in a dict keyed by the id as a string (JSON keys are strings).
- **Explored tiles** are stored per player as a hexadecimal bitmap string.

## M1: map, cities and fog

- **All six continents from M1.** DESIGN.md's M1 says "one continent"; generating six costs
  little and avoids reworking the map in M6. AI and cross-continent play are still M6.
- **Map size 120 x 72** (8,640 tiles, about twice a Civ V standard map), regions 40 x 36 per
  continent with a 3-tile ocean margin. 96 x 64 with rounder growth produced square continents.
- **Pointy-top hexes, odd-row offset storage, no wrap.**
- **Continent shapes** grow from the region centre; a frontier tile's weight is
  `1 + land neighbours` (power 1), which gives bays and peninsulas. Each continent is one
  landmass. Mountains are placed only where they leave the passable land connected, so every
  city can be reached overland.
- **Biomes** are Voronoi regions around 10 weighted seeds per continent; no latitude model yet.
- **Hills modify yields** (-1 food, +1 production) on top of the base terrain rather than
  replacing it; forest +1 production; jungle and marsh -1 food. Yields are floored at 0.
- **No rivers, lakes or islands in v1.** Oceania is one landmass like the others.
- **No luxury resources** (the design has no happiness). Gold-yielding bonus resources (coffee,
  gold ore) stand in for trade goods.
- **City sites** are scored by potential yields within radius 2 (resources counted as improved)
  plus a coastal bonus. The capital takes the best site; the other known cities are placed to be
  as far apart as possible among above-median sites; lost cities fill the rest by score with a
  seeded tie shuffle, all at least 4 hexes apart.
- **Lost-city mix** is drawn per city from weights (dormant 40, empty 25, overrun 35), so the
  number of overrun cities varies by seed. Overrun cities start with an alien hive guard in the
  city and an alien warrior beside it.
- **Starting roads** join the capital to each known city (shortest land path, avoiding lost-city
  sites so roads do not reveal them).
- **Cities belong to their continent's player** whoever frees them; the freeing unit's owner
  gets the credit. Work areas are fixed at map generation (nearest city wins), with no tile
  buying.
- **Vision radius 1** for most units (2 for recon, +1 on hills), 1 for cities (designer
  decision 2026-11-13: units see one hex around them).
- **Anything a player built** (improvement or route, including starting roads) keeps its own hex
  visible to that player, per DESIGN.md section 5. Radio beacons see 2 hexes.
- **Fog (designer decision 2026-11-13):** hexes go fully back to fog, terrain included, when no
  unit, city or player-built thing sees them. Discovered cities stay shown with live status.
  Each player keeps an "explored" bitmap (ever seen) that reveals nothing in the view; the test
  bot plans paths from it, as a human would from memory.
- **Line of sight is not blocked** by hills or mountains in v1.

## M2: cities and economy

- **A disconnected city produces nothing at all**: no growth, no starvation, no production, no
  gold or science. Its buildings still cost maintenance. DESIGN.md says a city must be
  reconnected "before it produces"; the strict reading makes roads an early priority.
- **Connection** is a chain of road, railway or own-city tiles to the owner's capital. Lost
  (unowned or alien) city tiles do not conduct. Sea links and blockades are not modelled yet.
- **Citizens** are assigned automatically each turn by the city's focus weights (no manual tile
  picking yet). The city tile is always worked and gets a centre bonus (+1 food, +2 production,
  +1 science, +1 gold). Balanced focus weighs food and production equally: with food weighted
  higher, grassland cities sat at 1 production.
- **Science per citizen** is 50% (rounded down per city), since buildings add more later.
- **Percent bonuses** from buildings apply to the city's flat subtotal of that yield, one line
  per building, each rounded down; the total is the sum of the lines.
- **Growth threshold** = 15 + 6(p-1) + (p-1)^2. A negative food store loses one citizen
  (minimum 1) and resets the store to 0. No food carry-over bonuses yet.
- **Production carries over** after completion; with an empty queue it keeps accumulating.
  A queued item that becomes invalid is dropped when it would complete. A unit that has no room
  to be placed or no spare strategic resource stalls the queue (production keeps accumulating).
- **Projects** (wealth, research) convert 50% of production to gold or science each turn while at
  the head of the queue.
- **Purchase** costs 200% of the item's production cost regardless of progress, completes
  immediately, and requires a connected city.
- **Gold**: income minus building maintenance and unit upkeep (1 gold per unit member beyond two
  free per active city). A negative treasury resets to 0 and the shortfall comes out of research
  progress before this turn's science is added.
- **Science with no research chosen** is banked in research progress (Civ-style overflow).
- **Strategic resources**: an improved strategic tile in a connected city's work area supplies
  its quantity; each unit member that needs it uses one. Supply is checked when a unit would
  complete or be bought, not when it is queued.
- **Beacon points** accumulate per player from beacon yields (none yet); they are spent from M5.
- **Tech gating pulled forward** (DESIGN.md M5 lists the trees): three trees of 7 techs; tier 0
  (present day) known at start. Several late techs unlock nothing yet; their effects belong to
  later milestones (trade, beacons).
- **Engineers** build one improvement at a time on their own hex; the job takes the listed turns
  and ends when the counter reaches 0 at the end of a turn. Moving cancels it (M3). Improvements
  cannot go on city hexes (they already count as roads) and do not remove features.
- **Starting buildings**: the capital has a food depot, workshop, market and school; other known
  cities a food depot. Starting gold 100.

## M3: units and combat

- **Damage formula**: a side of strength S facing strength O takes
  `30 x (S + O)^2 / (4 S^2)`, so equal strengths trade 30 each, 1.5:1 gives about 47 vs 21,
  2:1 about 67 vs 17. Then a seeded roll of 80-120%, clamped to 1-100. Softer than a squared
  ratio, which one-shot units at 2:1.
- **Wounded units fight weaker**: strength scales from 100% at full HP to 50% at 0 HP (Civ V
  style). City strength does not drop with damage.
- **Stacks** (designer rules): two units of one type and owner merge into one unit with
  `count = 2`, combined HP (max 200), twice the melee and ranged strength, one attack, and the
  lower of the two units' remaining moves. Merging needs combined HP of at least 100. When the
  stack drops below 100 HP (it has lost more than half of 200) one member dies and the killer is
  credited; at exactly 100 nothing dies. Splitting needs more than 100 HP: the unit that moves
  out has 100 HP and the stack's remaining moves; the rest stays. Stacks heal per member.
  Civilians do not stack. **Balance risk:** doubling both strength and HP makes a stack roughly
  four times as durable as one unit in a fight; watch this in M7 balance runs.
- **One military unit (or stack) and one civilian per hex**; units of opposing sides never share
  a hex. Players never fight each other: attacks are only possible between players and aliens.
- **Movement**: terrain costs 1 move, hills/forest/jungle/marsh 2 (largest applies), roads 1/3
  and rail 1/10 when both hexes have them. A unit with any moves left may enter one more hex.
  No zone of control, no embarkation (sea transport is M6), no line-of-sight blocking.
- **Paths** route around hostile units the player can see; an unseen hostile on the path stops
  the move on the hex before it. The pathfinder knows true terrain (including unexplored
  hexes), a small knowledge leak accepted for v1.
- **Attacks** cost the attack and all remaining moves. Melee needs adjacency; land units cannot
  attack onto water or mountains; naval melee attacks only ships and cities. Ranged units need
  the target hex visible to their owner (spotters matter: artillery sees 1 hex, shoots 2). Recon
  units may make weak melee attacks.
- **Modifiers**: hills +25%, forest +25%, jungle +25%, marsh -15%, military base improvement
  +25%, fortified +25% (applies immediately when ordered; Civ V waits a turn), flanking +10% per
  other non-hostile military unit next to the defender (allies from other continents count).
- **A melee winner advances** into the hex; hostile civilians there are destroyed.
- **Cities in combat**: strength = 10 + 2 x pop + walls/base bonuses (+10 for alien-held), plus
  50% of the garrison's defensive strength; 200 HP (+100 with a defence perimeter), healing 20
  per turn; bombard once per turn at range 2 with no retaliation. Only land melee can take a
  city to 0 HP; ranged and naval attacks stop at 1 HP.
- **Liberation**: the garrison dies, the city loses 50% of its population (rounded down),
  returns at 50% HP with an empty queue to its continent's player; the attacker's owner gets the
  credit, and damage dealt per player is kept on the city for split credit in M7.
- **Reclaim** happens when a player's military land unit enters a dormant city; **refounding**
  consumes a restoration team on an empty city's hex (population 1).
- **Credit ledger** per player: kills, units lost, cities liberated, reclaimed and refounded,
  damage dealt.
- **Test bot** (`beacon/bots.py`, settings in `data/bots.yaml`) reads the fog-safe view, uses
  attack previews and acts only through commands. It is deliberately simple; 4-17% of its
  commands are rejected (mostly unreachable targets) and logged.
- **Performance budget** (this Mac, Python 3.13): a 100-turn, six-bot game takes about 6 s
  (max 7.1 s over seeds 1-20); the 20-seed batch takes about 2 minutes. Pathfinding dominates.
- **Passive aliens until M4**: with no alien movement or growth, bots free nearly every city by
  turn 100 (0-14 alien cities left across seeds 1-20). That is expected, not a balance result.

## Open items noticed (not blocking M0-M3)

- Resolved 2026-11-13: defeat is all six continents fallen at once; a continent falls when it
  holds no cities.
- Several tier 3-4 techs unlock nothing yet (automated_markets, post_scarcity, nanofabrication,
  global_logistics); they get effects with trade (M6) and the beacon tree (M5).

## M4: the aliens

- **Alien state** (`GameState.aliens`): progress toward the next alien tech, techs, reinforcement
  store, surge cooldown, starting city count, and one standing order per alien unit.
- **Tipping point**: progress per turn = max(8, 2 + 1 per alien city + 20% of alien population).
  Eight alien techs (walls, spitters, mines, growth, regeneration, brutes, stronger walls,
  titans) are bought in a fixed order.
- **Alien cities** work no tiles. They grow on their own food rule (cap 6 + techs) and make
  production from population; they rebuild a missing garrison first, then spawn units by weight.
  The aliens field at most 110% of their city count in units (reinforcements and surges ignore
  the cap). Without a cap they built 800 units and swept every continent by turn 30.
- **Fortresses**: alien cities get +4 strength (+ wall techs) and a hardening bonus of 80% of
  the share of starting cities lost plus 5% per 20 turns, capped at 80%. Scaling by share rather
  than count keeps the last cities of every invasion hard to take.
- **No healing under siege** (both sides): a city that took damage this turn does not heal at
  turn end. Without it, a city's 20 HP per turn healing out-paced early sieges.
- **Reinforcements**: one store point per turn; every 15 turns a warrior and a drone land beside a
  seeded alien city (or on open land if none remain). Never stopped until the M7 barrage.
- **Director**: aliens see the whole map (designer). Each unit holds an order: siege (weight 6),
  raid (2) or patrol (3), with a seeded choice and targets. Siege targets score on population,
  capital and recent liberation minus defence and distance; units gather within 3 hexes and
  attack once nearby alien strength reaches 100% of the city's defence. Raids pillage
  player-built improvements first, then routes. Patrols roam to seeded hexes within 6, which
  produces the designer's shock encounters. Any unit attacks a neighbour when the trade is good
  (or it can kill), garrisons never leave their city, and units refill empty alien cities nearby.
  No sieges or raids in the first 8 turns.
- **Melee units capture lone civilians** (both sides): attacking a hex holding only enemy
  civilians destroys them and moves in, with no combat.
- **Lost-city decay**: each unreached dormant or empty city falls with chance 0.1% per 25 turns
  elapsed (cap 0.4% per turn), never with a player military unit within 2 hexes. It gets a hive
  guard. Distance to alien cities no longer matters (it made decay the main source of alien
  cities).
- **Lost-city states by quota** (changes M1): each continent's 16 lost cities are split exactly
  40/25/35 (dormant/empty/overrun), then shuffled with the seed, so every game starts with 36
  alien cities. Independent rolls gave 20 to 46, the largest source of balance spread.
- **Captured player cities** keep half their population, lose their queue, and record which
  players had units nearby. If the capital falls, the largest remaining city becomes capital.
- **Fallen continents** (designer): fallen when the player holds no cities, revived when they
  hold one again; tracked on the player (`fallen`, `times_fallen`).
- **Surges**: when aliens hold under 40% of their starting cities, or one player has liberated 4
  more cities than average, 3 of the strongest unlocked units land 3 hexes from that player's
  farthest city; 15-turn cooldown.
- **Engine fix**: a move whose leg would end on a friendly-occupied hex now reroutes around
  friendly units instead of failing (it left armies stuck for turns).
- **Starting armies** raised to 3 infantry and 2 artillery; infantry costs 60 and artillery 90.
- **Test bot**: garrisons the capital and cities within 6 hexes of known aliens; cities bombard;
  units hunt aliens near own cities, shell alien cities and assault them on a good trade; idle
  soldiers explore; two scouts and two restoration teams.
- **Performance**: caches for city lookup, tuning values and player-built hexes (rebuilt when
  improvements change), and per-search hex checks. A 100-turn game takes 3.5-5.4 s.
- **Balance gate**: 2 of 3 bands met, the alien-share band at 13/20 instead of 15/20. See
  `docs/BALANCE_M4.md`.

## M5: beacons, recruits and councils

- **Promoted content**: all `additional` entries (19 units, 14 buildings, 7 improvements, 19
  techs, 10 alien techs, the recruit pool) are now active. Effects needing later systems are
  inert: medical team healing, nanorepair crew repairs, marines' landings and the logistics hub's
  trade role. New alien unit types joined the alien spawn weights.
- **Six council domains** (designer, 2026-11-13, after first mapping gold to military): food,
  production, military, science, gold, beacon, two seats each, plus three general seats. The
  proposal's gold scores are restored (legends, merchant focus, greedy's +25% gold); berserker
  boosts military, and soldiers focus on military and production. `sale_pct` stays available as a
  trait effect but no trait uses it.
- **Scores are percent**: a seated recruit's score N gives +N% to that yield (food, production,
  science, gold, beacon) in every city, or +N%
  combat strength to every unit for military. Percent bonuses apply to the city's flat subtotal,
  like buildings. Percent rather than flat yields keeps one recruit meaningful at any empire size.
- **Recruit rolls** (stream `recruits`): character type by weight; the level's budget split one
  point at a time over the type's focus domains; one or two traits from the type's list; trait
  `yield_pct` scales the recruit's own scores; lifespan from the type's range plus trait shifts,
  clamped to 50-100; an extra immortal chance by rarity level. Legendary recruits (unique per
  game) can arrive from rarity 3. Names are fictional syllable pairs.
- **Speed lever**: Beacon I-V in a city (cost 80-1280, +3 to +8 beacon points each, cumulative).
  More cities with beacons also means more speed. **Rarity lever**: beacon-tree techs 1-5 (cost
  150-2000) set arrival cost (40-320 points), budget (10-28), legendary and immortal chances.
  One recruit can arrive per player per turn.
- **Councils**: seats are only constrained per player; seat changes are free and immediate.
- **Offers** (minimal trade before M6): offer a recruit to one player at a price (0 = gift); the
  recipient accepts or declines; offers lapse at turn end.
- **Betrayal**: chance per turn from traits. The recruit joins the alien city nearest the old
  patron's capital (same continent first), lending its military score as strength percent. If no
  alien city exists, it is simply gone. Liberating the city hands the recruit to the liberator.
- **Bot**: researches beacon theory and signal amplification first; its capital builds Beacon
  I-III once it has half a military unit per city; seats recruits greedily (general if they
  score in 3+ domains); gifts recruits it cannot seat; accepts offers it can seat.
- **Balance**: 20 seeds x 100 turns: alien share in band 10/20 (M4 13), captures 15/20,
  all-fallen 0/20, 40-76 recruits per game, 3-15 betrayals, slowest game 5.8 s. The new alien
  techs 9-18 and betrayals make aliens slightly stronger than in M4.

## M6: AI continents, trade, aid and troops abroad

- **Controllers**: every player is `ai` unless the runner marks it `human` (`--human europe`); a
  human seat issues no commands in the runner (a client will drive it). Batches run six AIs.
- **AI = test bot + character**: the AI reuses the bot's play with per-character overrides of
  `data/bots.yaml` values (`data/ai.yaml`), plus diplomacy. Characters are dealt per seed in a
  shuffled cycle, so any five players include at least three characters. No randomness in the AI.
- **Nations in contact**: from turn 0 every player knows where every active city is (live status
  from then on). Lost cities elsewhere stay unknown until seen. Without this, nobody could aim aid
  or troops at another continent.
- **Alliances** (designer): need International Accords (economic, tier 1, cost 100) on both sides;
  mutual; allies share vision and their maps of discovered cities. Any AI accepts an alliance.
- **Deals**: gold (lump, or per turn for 10/20/30 turns), strategic resources lent for a duration,
  techs the receiver can research now, recruits, units standing in or next to a receiver's city,
  and alliance. One-sided deals are aid and credit the giver (`aid_gold`, `aid_units`,
  `aid_techs`, `recruits_given`). Proposals lapse at turn end; per-turn gold stops early if the
  payer cannot pay. Lent resources apply at once for the deal's duration.
- **Delivery**: gold, resources, units and alliances apply at once (treated as financial or
  standing arrangements). Techs and recruits travel: from the giver's port (connected coastal city
  with a Port) to the receiver's capital at 20 hexes per turn (minimum one turn); without a port,
  a trade convoy forms at the giver's capital and must walk to a port first. Aliens capture a
  lone convoy (goods lost); a military unit on its hex escorts it. Sea routes ignore geography
  (straight hex distance) and are safe (aliens never cross water).
- **Troops abroad**: a land unit in its owner's port can ship to any known coastal city on another
  continent that is a player city, or dormant or empty (rescue). Cost 10 + 3 gold per 10 hexes;
  arrival after the same sea delay; it lands on or next to the destination, and a military unit
  landing on a dormant city reclaims it for that continent's player. Units on another continent
  cost +100% upkeep. No naval combat, no embarking (designer default).
- **AI diplomacy**: values items in gold (techs at research cost, resources 3 gold per unit-turn,
  recruits 8 per score point, units at production cost, alliance 150); accepts when value received
  is at least its character's ratio of value given. Proposes alliances (if its character allies),
  tech swaps and resource lending every trade interval, gold aid to a fallen continent or to a
  player holding at most 85% of its city count, and ships a share of its field units abroad once
  its own continent has at most one known alien city.
- **Bot fixes found in M6**: ranged unit choice now checks strategic resources, and a city whose
  queued unit cannot get its resource is replanned (both affected M5 balance runs). Soldiers only
  chase cities on the continent they stand on.
- **Balance**: see `docs/BALANCE_M6.md`. All M6 gates met; M4 bands under AI play: captures 15/20,
  alien-share band 11/20.
