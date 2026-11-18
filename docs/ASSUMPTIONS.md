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

## M7: mothership, barrage, espionage, endings and MVP

- **Mothership strikes**: 2.5% chance per turn while the mothership lives; one player city (the
  barrage host ten times likelier once the project runs) drops to 40% HP and loses 25% of its
  population, and counts as besieged (no healing that turn).
- **Reinforcements and surges stop** for good as soon as any player knows Orbital Barrage (DESIGN.md
  11, "researching it can stop reinforcements"); surges count as mothership landings.
- **The barrage**: Orbital Barrage is military tier 5 (cost 1,500, needs Railguns and Deep Space
  Radar). One barrage per game, hosted in a connected city of a player who knows the tech. Anyone
  may contribute, with or without the tech: production from a city building `project:barrage`, or
  gold at 50%. It fires at 3,000 progress and at least 20 turns after it started, with the host in
  player hands; contributions stop at the cost and gold is only charged for what is taken. The
  director adds 80 to the host's siege score.
- **Late-game hunt**: Deep Space Radar and Stellar Chorus reveal every alien-held city to their
  owner each turn.
- **Espionage**: gold-funded only (800); solo (starter funds and gains) or shared (anyone funds,
  everyone gains). Offers 3 alien techs that some recipient lacks; the largest contributor chooses
  within one turn, else the first offered is taken. The alien tree has six techs, each unlocking a
  unit (xeno trooper, plasma lancer) or a building (bio-reactor, phase scanner, translation hub,
  chitin bulwark); research cannot reach them.
- **Endings**: victory when the mothership is destroyed and no alien city remains (checked at
  the end of every turn, either order); defeat when all six continents have fallen at once. No
  turn limit (designer, 2026-11-13); batch runs stop at a horizon only to measure. The runner
  stops at either outcome.
- **MVP**: weighted ledger in `data/mvp.yaml`. Liberation credit is split by the damage each
  player dealt to the city (100 hundredths per city; the liberator gets rounding). Population
  saved counts freed, reclaimed and refounded cities' population. Unit-turns abroad accrue each
  turn. Weights fitted on the M7 batch so builders and fighters both average in the top half.
- **AI endgame**: after its character's research list, every AI pursues the path to Deep Space
  Radar and Orbital Barrage; the first to learn it starts the barrage in its capital; each
  character sends a share of its most productive cities (25-50%) and half its spare gold to the
  barrage while it needs progress; it opens espionage operations above a gold reserve (shared,
  except isolationists) and funds shared ones; as chooser it takes the first offered tech.
- **Balance**: 7/20 victories by turn 200 (turns 131-195), 0 defeats, barrage fired in every game,
  espionage in 16/20, slowest game 19.8 s. See `docs/BALANCE_M7.md`.

## M8: the web client (first playable)

- **No build step, no new dependencies**: `web/server.py` uses the Python standard library
  (`http.server`), the client is plain HTML, CSS and JavaScript drawing on a canvas. One game per
  server process, in memory; saves are JSON states in `runs/saves/` (git-ignored).
- **The server stays fog-safe**: the client gets `observe()` plus details of the player's own
  units and cities, and combat previews only for targets the player can see. Known leaks
  accepted for now: a selected unit's reachable hexes are highlighted even where they run into
  fog (Civ does the same), and the diplomacy screen shows each AI's character.
- **Turn order with a human**: the human acts first; on Next turn the five AIs act in player
  order, then the turn resolves. Events shown are the player's own plus world events.
- **Look**: original flat vector art, nothing taken from Civ V; the reference screenshots shaped
  the layout only (top bar, unit and city panels, combat preview, tech columns, minimap, Next
  turn button). Units are badges with a three-letter type code; aliens are violet with a green
  rim; stacks show ×2.
- **Ending a turn with open decisions** asks for a second press instead of a browser dialog (superseded 2026-11-14 by the action button, below).

## After M8: real geography, city defence, action button (designer, 2026-11-14)

- **Real geography**: each continent is its real outline (whole-degree lon/lat polygons in
  `data/continents.yaml`), fitted into its own box on a 192 x 116 map at its own scale, so all six
  have similar land (about 870-1080 hexes, roughly twice the procedural continents). Distances
  are true within a continent, not between continents. Islands near a continent (Britain,
  Ireland, Japan, Sri Lanka, Madagascar, Tasmania, New Guinea) are joined to it by the shortest
  causeway so every continent stays one landmass; New Zealand and island chains are left out.
  Seas inside a continent are cut out as lakes (the Caspian).
- **Climate and relief**: biomes come from hand-placed climate seeds (nearest seed wins, with a
  seeded blend at the borders); mountain ranges and hill country follow real ranges (Rockies,
  Andes, Alps, Himalaya and so on). Mountains never cut a continent's passable land in two and
  never sit on or beside a city. The seed still varies forests, extra hills, resources and which
  lost cities are dormant, ruined or held by aliens; the shapes and city sites are fixed.
- **Cities**: 15 real cities per continent, chosen to stay at least 5 hexes apart (a test checks
  it; Paris sits a little south of its true spot to keep 5 from London). Three are known at the
  start, chosen spread out: New York, Los Angeles, Mexico City; Sao Paulo, Buenos Aires, Bogota;
  London, Berlin, Rome; Beijing, Delhi, Tokyo; Cairo, Lagos, Johannesburg; Sydney, Perth, Darwin.
- **Starting roads are unowned**: the known cities are still joined to the capital by road (so
  they produce from turn 1), but nobody owns those roads, so they no longer show through the fog
  (owned routes stay in sight); they appear only where the map is explored, and alien raiders
  ignore them.
- **Starting forces**: two infantry are the only field army. The recon team, two engineers and
  the restoration team are kept (exploration and roads start on turn 1, and the bigger
  continents need it). Every known city starts with a city artillery.
- **City defence units** (`fixed: true` in `data/units.yaml`): city artillery (ranged; fires but
  never moves) and home guard (melee; never moves or attacks, `no_attack: true`). They are placed
  only on a city tile, one per city, in their own slot beside a field unit and a civilian. Every
  own military unit in a city adds its garrison share to the city's strength. They die if the
  city falls. They are part of the city, not units anyone commands: the map does not draw them and
  the city panel lists them under Defences. At the end of every turn, before the aliens move,
  each city gun fires at the weakest visible enemy in range (ties by hex), for humans and AI
  alike. Bots never count defence units as field army.
- **Bots scout first**: every continent's city list is public (real cities), so while some of its
  own cities are still unfound, a bot builds its recon teams before more military.
- **Next-turn button**: it names the next decision (choose research, choose production, unit
  needs orders, answer a proposal...) and opens it; it says Next turn only when nothing is left.
  Shift-click or Shift+Enter ends the turn anyway. This replaces the press-twice confirmation.

- **Balance after the change** (20 AI seeds to turn 200): 11/20 victories (turns 160-183, in the
  30-70% band), 0 defeats, barrage fired in every game, the other nine end with 1-2 alien cities
  left. Games are slower on the bigger map: 25-60 s per 200 turns (was up to 20 s).
- **Client, 2026-11-14 (later)**: the tech screen is one timeline, present on the left and
  future on the right, not split by tree; each tech shows projected turns at the current science
  rate (cost left divided by science per turn, rounded up) and tags on what it unlocks (military,
  defence, food, production, science, gold, beacon, sight, movement). Production items and tech
  unlocks have hover cards listing their effects from the data. Top-bar numbers open their
  screens (science: tech, beacon: council, gold: diplomacy, mothership: projects). Choosing
  production closes the city panel; a city with something queued shows "Change production"
  instead of the list. Alien cities and units are red; Asia's colour moved to violet.

## Citizens, one-move hexes, healing, city alert, branching tree (designer, 2026-11-14)

- **No dormant cities or ruins**: every lost city starts held by the aliens (lost_state_weights
  is overrun 100); the restoration team is removed. The engine still understands the dormant and
  empty states, unused.
- **Citizens** (`beacon/citizens.py`, tuning `citizens`): one per population point. Stats are 6
  points in a seeded pattern (+1 all six, +3 in two, +2 in three, equal weights); 60% have one
  trait (quick, skilled, statesman, frugal, devoted). Births still come from the food store
  reaching the growth threshold; a child gains `8 + 3 x food surplus` growth points a turn and
  grows up at 100 (about 5 turns well fed, 13 with no surplus; quick doubles it). Children eat but
  do not work.
- **Working**: only improved tiles (farm, mine, extractor and the like; roads do not count) can
  be worked, one citizen each; the tile gives its yield plus half the citizen's stats, not
  rounded (designer: +3 is +1.5). Yields are integers, so the city sums citizens' halves in
  hundredths and carries the remainder to the next turn (+1.5 is +1, then +2). Military stats
  count only on the council.
- **Council**: the continent council (shared with alien recruits; 3 general and 2 per domain).
  A citizen there gives its full stats to its home city as flat yields, and military as city
  strength (2 per point). Recruits come first: auto citizens give up seats to them; only citizens
  the player put on the council keep their seats against recruits.
- **Jobs**: Auto (default), Council or a chosen improved tile. Auto workers feed the city first
  (most food while it would starve), then follow the city's focus; auto citizens with no tile left
  take free council seats. Placement is redone each turn and after any command that changes
  cities, seats or jobs.
- **Starting land**: a capital starts with 6 improved tiles and other known cities with 4, chosen
  food-first; a liberated city gets improved tiles for its surviving population.
- **Movement**: every land hex costs one move (hills, forest, jungle and marsh included); roads
  and railways stay faster. Defence bonuses are unchanged.
- **Healing**: a unit that does not move or attack (fortified or resting) heals 20 HP a turn in
  its own territory, cities included, and 10 outside, per stack member.
- **City alert**: when a visible enemy is within a city's attack range (2), the city appears in
  Needs attention as "can attack" and the action button takes you there; Hold fire dismisses it
  for the turn.
- **Tech tree**: every tech has at most one parent. Level 1: Urban Planning and Advanced
  Manufacturing; levels 2-4 have 4, 8 and 16 techs; level 5 has 13 and level 6 one (Stellar
  Chorus). Costs by level: 100, 200, 380, 600, 950, 1500 (the Orbital Barrage 1500). The
  present-day techs stay known at the start. Fortification Doctrine (walls) moved to level 5 under
  Militia Reserves.
- **Balance after these changes** (20 AI seeds to turn 200): 5/20 victories (turns 180-199),
  below the 30-70% band; 0 defeats; unfinished games end with 1-27 alien cities left (most under
  10). Every continent now has 12 alien cities to take (72, against 24 before), so the war is
  longer. Softer hardening (3% per 20 turns, cap 60%) did not help (3/20), so it was reverted.
  Slowest game 128 s (citizens and the bigger war). Open for the designer: accept longer games or
  retune (fewer alien garrison units, stronger early artillery...).

## Alien raids and unit promotions (designer, 2026-11-14)

- **Warm-up**: no alien attack on a player city (siege or mothership strike) before turn 25
  (`director.city_grace_turns`). Before turn 8 aliens only patrol; from turn 8 they also raid
  improvements and hunt.
- **Hunters**: a new order. A hunter picks the weakest player unit outside cities within 8 hexes
  on its continent (scouts, engineers, stragglers) and stalks it, attacking when the odds favour
  it.
- **Cohorts**: a unit that starts a siege pulls 1-4 nearby aliens (a seeded cohort of 2-5) onto the
  same city. Sieges weigh the city's defence (its strength plus nearby player units) twice as
  heavily as before, so weakly defended, lightly garrisoned cities draw them; they still attack
  only once the cohort's strength matches the defence.
- **Experience**: each combat a player unit takes part in, attacking or attacked (city fire
  included), gives 1 experience. Promotions fall due at 2, 4, 8, 16, then x1.5 (24, 36, 54, 81...).
  Each promotion is a choice of +10% attack or +10% defence for now (data `promotions.options`,
  ready for unit-specific options); bonuses add up. A due promotion shows in Needs attention and
  on the action button. Aliens gain no experience.
- **Stacks**: merging keeps the more experienced member's record; splitting copies it to both.
- **AI choices**: ranged units take attack, city guns defence, others alternate (attack first).
- **Balance after raids and promotions** (20 AI seeds to turn 200): 1/20 victories, 0 defeats,
  no continent fell; players lost 0-6 cities each game to sieges after turn 25; 0-31 alien cities
  left at turn 200 (median about 6). Still open for the designer (see the balance note above).
  Slowest game 153 s.

## Starting land, merging, turrets, council board, breakdowns (designer, 2026-11-14)

- **Slower war accepted**: the designer is fine with fewer victories by turn 200 now that every
  lost city is alien-held; the 30-70% band no longer applies.
- **Starting forces**: the capital has 2 infantry, 1 engineer and the scout; every other starting
  city has 1 infantry and 1 engineer; each starting city still has its city artillery.
- **No starting improvements**: farms and mines must be built (start_improved 0; liberated cities
  get none either). So new cities are not hungry: the capital starts at 3 population and the
  others at 2 (from 5 and 3), and the city centre gives 2 food (from 1). Until farms are built
  the citizens sit on the council.
- **Merging**: moving a unit onto a unit of the same type merges them; the merge button is gone.
- **Cancel job**: engineers can stop building (the work is lost). If the job began on an earlier
  turn they get their full moves back at once; if it began this turn they move next turn.
- **City guns**: no experience. Gold upgrades instead, up to 5 levels, each +15% attack and
  defence; level k costs 60 + 40 x (k - 1) gold. Bots upgrade the most threatened gun when they
  hold three times the price.
- **Turrets**: engineers build one (2 turns) on any of their improved tiles. Level 1 has strength
  18 and 60 HP; each gold upgrade (50, 80, 110 gold; up to level 4) adds 8 strength and 30 HP and
  repairs it. At the end of each turn a turret fires at the weakest visible enemy next to it. A
  raider must destroy it before the tile can be pillaged. Bots do not build turrets yet.
- **Raids**: raid weight 2 to 4; aliens no longer raid within 2 hexes of a player city (city guns
  cover that), and each turret level makes a tile count as 3 hexes further away.
- **Melee capture**: a land melee unit that takes a city to 0 HP moves in and frees it (already
  the rule; checked).
- **Council board**: three general seats on top, two seats per domain below; every recruit and
  grown citizen is listed and can be moved seat to seat. A citizen can be given a specific seat
  (job "council:<seat>"). On a domain seat a citizen now adds only that domain's stat (as a
  recruit does); on a general seat, all of them.
- **Population screen**: every city's citizens, what each does, children growing up and idle
  citizens; each city panel links to its own page.
- **Top bar**: hovering gold, science or beacon shows where it comes from (by kind of source and
  by city, with upkeep for gold and any unconnected cities); clicking still opens the screen.
- **Prices**: production items show their gold purchase price next to cost and turns.
- **Balance after these changes** (20 AI seeds to turn 200): 2/20 victories (turns 174 and 198),
  0 defeats, no continent fell; players lost 1-10 cities each game to sieges; 0-41 alien cities
  left at turn 200. Slowest game 99 s.

## Combat preview, city tiles, council clarity, road upkeep (designer, 2026-11-14)

- **Fortify** is refused for a unit that attacked this turn.
- **City fire**: selecting a city that can fire marks its targets red at once; click one to fire.
- **Combat preview**: an outcome banner (decisive victory ... likely defeat), both strengths with
  every modifier, and an HP bar per side whose flashing red part is the expected damage.
- **City tiles**: a selected city outlines its improved tiles on the map with their yields; a
  worked tile shows a green check and its worker, a free one a gold +. Clicking a + puts the
  city's best grown citizen for that tile there (`assign_best_citizen`, by the city's focus).
- **Council**: seated members appear only on the board; the pool lists the unassigned. Members
  placed by Auto carry an "auto" tag. After each council change a message gives the change in
  gold, science and beacon per turn. (With Auto, citizens who have no tile are already seated,
  so seating one often changes nothing; moving one from a general to a domain seat lowers the
  total, since a domain seat counts only its own domain.)
- **Unconnected roads**: 1 gold a turn per road or rail hex of yours not joined to one of your
  cities (shown in the gold breakdown).

## One starting city (designer, 2026-11-14)

- **Start**: each player holds only its capital (known_count 1); the other 14 cities of its
  continent are alien-held. The capital keeps its army: 2 infantry, 1 engineer, the scout and
  its city artillery.
- **Easy first target**: the alien city nearest each capital is held by a single hatchling
  instead of a hive guard and a warrior (and starts at half HP, though it heals before most
  armies arrive).
- **Capitals are strong**: +15 strength and +100 HP (like Civ's palace). Without it, three
  capitals fell to the first sieges after turn 25 and their continents fell.
- **Bots**: keep at least 4 military units however few cities they have; hold a city only when
  alien units outside alien cities are near (city guns cover the rest); rebuild lost scouts only
  once they have 2 military units.
- **Result (quick check, 3 seeds to turn 60)**: first liberations by turns 5-19 on several
  continents; the aliens often retake that city around turn 30; no capital fell.
- **Batch (20 AI seeds to turn 200)**: 0 victories, 0 defeats; in one game Africa and South
  America fell. At turn 200, 52-80 of the 84 alien cities were still held (players held 10-38
  cities in all). The war barely advances with one starting city and no starting farms: open for
  the designer (retune before relying on balance numbers).

## Retune for the one-city start (designer, 2026-11-14)

- **Capital**: starts with 5 citizens (designer), still 2 infantry, 1 engineer and the scout. The
  palace adds +3 food and +1 production, so 5 citizens are fed before any farm is built.
- **Alien cities**: one hive guard each (was a hive guard and a warrior); a city with an enemy
  soldier next to it does not heal; retaking freed cities is valued 10 (was 25).
- **Alien scaling**: tech progress and the army cap were set for 24 alien cities and ran three
  times too strong with 84. Progress is now 2 + 15% of alien population (no per-city term), about
  40 a turn at the start; the army cap is 45% of alien cities (about 37 units, was 110%).
- **Result**: 6 AI seeds to turn 200: 0 victories, no continent fell, 8-41 alien cities left. To
  turn 300: victories on turns 236 and 264, the other four with 1-7 alien cities left; players
  lost 7-16 cities along the way. Games take 70-140 s to 300 turns.

## Discovery: shuffled continents and contact (designer, 2026-11-14)

- **Shuffled world**: each continent keeps its real shape, cities and size (its box `size`), but
  where the boxes sit changes every game: a seeded shuffle into two rows of three, seeded order,
  seeded ocean gaps (at least 3 columns) and seeded vertical offsets. The map is 216 x 128 (was
  192 x 116) so any three continents fit in a row. Port Hedland and Vladivostok were replaced by
  Exmouth and Khabarovsk so cities stay 5 hexes apart whatever the row parity.
- **Contact**: nobody knows the other continents at the start (the M6 rule that every nation
  knew every active city is gone). Two players meet when one sees the other's land (its
  continent's hexes, coasts included) or units; checked after every move and at the end of each
  turn. Meeting is mutual and swaps the locations of both players' cities. A fallen continent
  becomes known to everyone ("distress"), so it can still be rescued.
- **Gated by contact**: proposing deals (trade, aid, alliances), offering recruits and shipping
  troops to another continent's cities. World projects (the barrage, espionage) are not gated.
- **Scout boat**: a cheap (40), fast (5 moves, sight 2) unarmed sea scout, available from the
  start in coastal cities. Bots and AIs build one once they have 2 military units and still have
  someone to meet; it sails to the nearest open-ocean edge of the known world.
- **Batch after discovery (10 AI seeds to turn 300)**: 10/10 victories on turns 219-299, no
  defeats, no continent fell; 26-72 deals, 9-24 units shipped and 6-12 alliances per game once
  contact was made. Slowest game 114 s.

## Information screens (designer, 2026-11-14)

- **Cities**: every city on one page (population and turns to grow, food surplus, production,
  science, gold, beacon, what it builds and when, notes such as not connected, aliens near, idle
  citizens), sortable, with totals; click a row to go to the city.
- **Units**: every unit with where it is, HP, moves, experience and what it is doing, filtered by
  military, scouts and civilians, city defences, needing orders, promotion due or abroad; click a
  row to select it.
- **Turn summary**: after each turn, what happened, grouped (cities, research, war, world), each
  entry clickable; it can be switched off.
- **Log**: the events of the last 40 turns of this browser session; entries in the side panel and
  the log jump to the place on the map (a flashing hex).

## Filling placeholder content (designer, 2026-11-14)

- **Tech effects** (`beacon/techfx.py`, `effects` in data/techs.yaml): the 16 techs that unlocked
  nothing now give bonuses. Urban Planning: births and growing up 25% faster. Robotics: engineers
  build 1 turn faster. Mass Production: units 15% cheaper. Quantum Theory: +10% science. Reactive
  Armour: armour +15% defence. Militia Reserves: unlocks the home guard and +1 free unit per city.
  Combined Arms: +10% per flanker. Stealth Tech: alien hunters ignore your recon. AI Targeting:
  ranged attacks +15%. Orbital Launch: troops by sea arrive 50% sooner. Orbital Defence Grid: +5
  strength for every city. Sovereign Bonds: +10% gold and an empty treasury no longer drains
  research. Carbon Markets: +2 gold per city. Automated Markets: buying costs 25% less. Synthetic
  Biology: +2 food per city. Antimatter Power: +20% production. Tech cards now list effects and the
  rules a tech switches on (alliances, recruit rarity, radar, the barrage).
- **Support units**: the medical team heals your units on and next to its hex by 10 HP a turn
  (whether or not they fought); the nanorepair crew rebuilds an improvement aliens pillaged on its
  hex in 1 turn (hexes remember what was pillaged). Bots do not use either yet.
- **Unit classes and matchups**: every unit has a class (infantry, armour, artillery, recon,
  naval, civilian, light, heavy, defence). Infantry +25% defence on hills, forest, jungle or
  marsh; armour +25% attacking units on open flat ground; artillery +25% against cities (marines
  +15%); anti-tank teams +50% against armour and heavy aliens; swarm drones +25% against light
  units and artillery.
- **Class promotions**: besides +10% attack or defence, infantry can take Dig in (+20% defence)
  or Field medic (+10 healing); armour Blitz (+1 move), Breakthrough (+20% vs infantry) or Field
  medic; artillery Siege master (+25% vs cities) or Barrage (+15% attack); naval Barrage or Sea
  legs (+1 move); recon Blitz. Bots prefer their class's options.
- **Batch after the content (10 AI seeds to turn 300)**: 9/10 victories on turns 199-284 (the
  tenth ends with 2 alien cities left), no defeats, no continent fell. Slowest game 130 s.

## M9 steps 1-3: events, exploration finds, Starfall (docs/SPEC_M9.md)

- **Events** live in data/story.yaml (`events`): title, picture key, body, and either outcomes
  or 1-3 choices. Outcomes: gold, science, a citizen in the nearest city, a unit, a recruit, an
  alien ambush, a flag. A choice event waits in Needs attention ("An event awaits") until
  answered; AIs take the data's `ai_choice`. Pictures are placeholder art (a painted-sky gradient
  and a glyph) until the graphics push.
- **Exploration finds**: 6 per continent, at least 3 hexes from any city and 4 from each other,
  seeded. Survivors (choose: +1 citizen in your nearest city, or a free infantry here), banished
  alien (a recruit), wreckage (+100 science once), supply cache (+60 gold), armoury (a free
  infantry), ambush (an alien warrior). A find shows as "?" on explored hexes and fires for the
  first player land unit that steps on it. AI scouts head for finds they have seen.
- **Starfall**: first warning on turn 20, then every 20-26 turns while no shard is active. The
  warning marks a 7-hex circle 3 turns ahead; the landed shard's hex is known to all and shines
  through the fog. An engineer or land scout (any land unit for the aliens) on the hex at the end
  of a turn mines one turn; 5 turns claims it (whoever gets there first; soldiers guard). Rewards
  grow by 100% of base per 100 turns: Preserving Compound (+15% growth), Starmetal (+10%
  production), New Elements (+10% science), Exotic Matter (+2 beacon per city), Living Alloy (+8%
  unit strength). Aliens claiming one gain 300 tech progress (scaled the same way). An unclaimed
  shard burns out 25 turns after landing. Claimed shards are permanent player bonuses and count
  for the MVP score (15 each).
- **AI**: the aliens send their nearest free unit to mine each landed shard with 2 escorts; AI
  players within 30 hexes on the same continent send their nearest engineer or scout plus 2
  guards. AIs do not ship units to shards on other continents yet.
- **Batch (10 AI seeds to turn 300)**: 5/10 victories (turns 200-279; the rest end with 1-14
  alien cities left), no defeats, no continent fell; players claimed 3-9 shards per game. In 3
  games to turn 200, humans won 12 of 17 claimed shards (71%, the designer's 60-70% target) and 4
  burnt out unclaimed. Victories fell from 9/10: shards the aliens claim speed their tech. Slowest
  game 167 s.

## M10 playtest changes (designer 2026-11-15, docs/SPEC_M10.md)

- **Council reach.** A council citizen's full stats count in every active city of its owner,
  and its military counts toward every city's strength. Tile work stays city-wide.
- **Connection.** Cities produce without a road. A city joined to the capital earns
  `economy.connection_gold` (2) a turn, shown as a "connection" line; the capital earns none.
  Strategic resources and ports still need the city to be connected: that is the remaining value
  of a road besides gold, speed and convoys.
- **Per-item production.** `City.progress` holds production per item. An item finishing keeps its
  overflow for the next item, capped at one turn's production (`City.production_store` now holds
  that carry for player cities; alien cities still use it as their store). With nothing queued, a
  turn's production waits for the next item, one turn's worth at most.
- **Buying.** `Purchase.item` buys any allowed production option; without it, the queue head.
  The price is the full price times the share of cost not yet produced, at least 1 gold. A bought
  item leaves the queue if it was in it, and its progress is cleared.
- **Convoys.** A city may have one convoy: 25% or 50% (`convoys.shares_pct`) of its production
  or of its positive food surplus, to its owner's or an ally's active city joined by roads,
  railways or active city tiles. The share is taken at the sender's turn and arrives at the
  receiver's next city turn (`City.incoming`), standing in for road travel time. A cut route
  pauses it. AI players do not use convoys yet.
- **Remnants.** 3-5 per continent (`remnants.*`), placed at the start (seeded per continent) at
  least 4 hexes from cities and 5 from each other, not on finds. They are shards with
  `remnant: true`: mined like landed shards, never fade, and do not delay Starfall (the next
  shard falls when no *falling* shard is active). The client shows a remnant once its hex is
  explored.
- **Beacon contact.** Learning `contact.beacon_tech` (beacon_theory) meets every other player at
  once ("beacon" contact).
- **Library.** A new building (cost 45, +2 science, maintenance 1, industrial_base) available
  from turn 1; the school now requires it, and capitals start with both.
- **Tech costs.** All costs about 25% lower (tier 1: 80, tier 2: 150, tier 3: 280, tier 4: 450,
  tier 5: 720 and 1150, tier 6: 1150).
- **Map.** The map wraps east to west (`map.wrap`; even width; `GameState.wrap`, registered with
  `hexgrid.set_wrap` on creation and load). Each continent's real outline is grown to
  `map.land_per_continent` (2750) land hexes inside its box, faster where more land surrounds a
  hex and slower near the box edge (`map.land_edge_pct`), so land is 60% of the map and every
  continent is the same size. Boxes in a row overlap by a column and the two rows by a row
  (`map.layout_gap_min`, `map.row_gap`: -1), leaving straits one hex wide that scouts see across;
  the spare width is one open ocean at a seeded column, the spare height polar sea. Grown land
  takes the biome of the nearest real biome seed, so large interiors can be one biome. Europe's
  box was enlarged to 60 x 58 so it can reach the same land.
- **Fog.** The view sends explored hexes out of sight with their static fields only (terrain,
  relief, feature, resource, continent, owning city); improvements, routes and units there stay
  hidden. The client draws explored land clear.
- **Camera.** After a unit command, if that unit no longer needs orders, the client selects the
  next unit that does and centres on it.

## M11: ocean bridges and the leader (designer 2026-11-15, docs/SPEC_M11.md)

- **Sea bridge tech.** Robotics (tier 3, production, under Applied AI) unlocks the sea bridge
  instead of a new Ocean Engineering tech: the tree keeps exactly two children per tech (2, 4,
  8, 16), as the designer set it and `test_tech_tree_branches_two_four_eight_sixteen` checks.
  The AI's endgame research list now includes Applied AI and Robotics before the radio beacons.
- **Sea bridge.** A route (`kind: bridge`) built over 6 turns on an empty coast (shallow) hex
  beside engineers standing on passable land or on another bridge (`BuildImprovement.target`;
  `Job.tile` holds the hex). A bridged hex is passable land for land units, moves at road speed,
  counts as a road for connections, convoys and upkeep, and ships still sail through it. Any
  unit may cross, aliens too. Aliens pillage it like a road; the wrecker steps ashore to a free
  land hex beside it. Engineers rebuild it as new (no quick repair). Remnants and finds may in
  rare cases land on a bridged hex.
- **AI bridges.** An AI with Robotics and an ally sends one engineer a turn to bridge toward the
  nearest explored land of an allied continent (the far shore of a strait, which scouts see):
  the cheapest path over explored hexes from its capital, where each unbridged shallow hex costs
  4 land steps (`bridges.water_cost`), and only if the path needs at most 4 bridges
  (`bridges.max_water`). Aiming at an allied city instead found no path, since the AI has not
  explored the ally's interior.
- **Leader data.** `data/leaders.yaml` (a new data file, `cfg.leader()`): looks, names, start,
  traits, XP, milestones, family, hybrids, wardrobe, AI. Descriptions are `info` (the loader
  strips `note` as metadata). Leaders use one RNG stream, `leader`, with sub-keys (make,
  attitude, hybrid, vote).
- **Generated leaders.** Every player gets a leader from the seed: a look (and its sex), a name
  not used by another player, an age of 30-55 and two traits. A human may remake theirs with
  `CreateLeader` only on turn 0 (the creation screen opens once at the start of a new game).
- **Age.** Start age plus one year every 4 turns; the leader never dies.
- **Skills.** Six skills at +1. Each yield skill is a line `leader:<name>` in every one of the
  owner's active cities, like a council member in a general seat; military adds
  skill x `citizens.military_strength` to every city's strength. The leader is the 16th seat,
  above the 3 general and 12 domain seats, and does not use one of them.
- **XP and levels.** XP is computed from the player's MVP credit ledger (30 per city freed or
  reclaimed, 15 per city refounded, 2 per alien defeated, 20 per shard claimed, 15 per child of
  the leader grown up; a new credit key `leader_children`, not scored by the MVP). Level L needs
  40(L-1) + 20(L-1)(L-2)/2 XP. Levels are counted at the end of each turn. Each level gives one
  skill point (`RaiseSkill`); points not spent stay.
- **Traits.** Ten leader traits, each an effect in the tech-effect format (`techfx`), so they
  apply wherever tech effects do: Steady +5 city strength, Visionary/Provider/Industrious/
  Merchant/Mystic +10% of one yield, Quartermaster +1 free upkeep per city, Tactician +10%
  flanking, Builder engineers 1 turn faster, Nurturing +25% growth. A third trait is chosen at
  level 5.
- **Milestones.** Liberator (cities freed 1/5/10), Hunter (aliens defeated 10/20/30), Parent of
  the nation (children grown 1/3/5), Starcatcher (shards 1/3). Each threshold offers 2-3 bonuses
  in the tech-effect format for this game (`ChooseLeaderBonus`). The SPEC_M9 examples that need
  new mechanics (half production for the next unit, +1 citizen in a freed city, a free veteran
  unit, earlier shard warnings, the resistance milestone) wait for a later round.
- **Family.** `StartFamily` with a grown citizen (not the leader's own child) or an alien
  recruit seated on the council, while no child is on the way and every child of the leader has
  grown up, and 20 turns after the last birth (`family.cooldown_turns`; without it the first
  batch gave about 15 children per leader in 100 turns, with it 5). The child is born in the
  capital 3 turns later (+1 population there) as a citizen marked `kin`. Partners are not
  limited by sex.
- **Hybrids.** A hybrid's stat points are (leader's current skill total + the recruit's score
  total) / 2, rounded down (designer: "the average of the leader's 6 and the alien parent's
  total"; the leader's total grows with levels), spread over the domains in proportion to both
  parents' values (largest remainders first). Its "alien trait" is one citizen trait at 50%,
  since recruit traits act on council percentages, not on citizens.
- **Attitudes and votes.** 25% of cities refuse hybrids, seeded per city at the start (no event
  or building changes it yet). A hybrid in a refusing city takes a council seat if one is free
  and otherwise idles. Each turn a hybrid on the council is voted out with 3% chance: no seat for
  10 turns (`Citizen.banned_until`), and it moves to its owner's nearest accepting city if its
  own refuses.
- **AI leaders.** Spend points on their lowest skill (ties in domain order), take the first
  option of every choice, and start a family whenever allowed, with their highest-scoring seated
  recruit, else their best grown citizen.
- **Wardrobe and career.** `SetWardrobe` checks only that the items exist; the web session
  checks career unlocks before sending it. The career profile is `runs/profile.json`: one row
  per game (keyed by start time, seed and continent, or by save name after a load), updated at
  each end of turn; totals sum the rows. The developer `--reveal` flag unlocks everything.
- **Art.** Each outfit is its own Meshy model, so faces differ slightly between outfits of one
  look. Greying hair is a soft lightening over the crown from age 50. Accessories are CSS
  overlays placed on the figure.
- **Recruit gifts (fix).** The bots and AI offer spare recruits only to players they have met
  (offers to unmet players were rejected; leaders made them common enough to notice).

## M12: a readable alien that reacts to you (designer 2026-11-15, docs/SPEC_M12.md)

- **Strike plans.** Every siege the director picks is announced as an `AlienPlan`: the unit and
  its cohort get `gather` orders (they hold, fortified, but still take favourable attacks), and
  the plan launches as siege orders `plans.strike_turns` (3) turns later. A plan whose target is
  no longer a player city, or whose units are all dead, is dropped. Raids, hunts and patrols are
  not announced.
- **Who sees a plan.** Revised (designer 2026-11-16): only a city with a UAV patrol on its tile
  gets the warning - the city, the turns left, where the strike gathers and its strength; the
  announcement and launch events reach the player only then too. The UAV (`uav_patrol`, Drone
  Warfare, 60 production) is a fixed, civilian-role unit with its own "air" slot, so it stands
  beside the city's guns; it never moves or fights, sees 4 hexes, pays normal unit upkeep, and
  a city holds one. AI players do not build it yet (they do not read plans).
- **Heat.** Population x 1, plus listed buildings (beacons 3-8, factories 3-4, labs 2-3, fusion 3,
  ports and shipyards 1-2, radio and sensor 1-2), plus 2 per active convoy. A strike target's
  value rises by heat x 2%, and the cohort gains one unit per 25 heat (at most 3).
- **Contents.** Seeded per alien city at the start (map stream, by city id): survivors (+2
  population), captive (a citizen with 9 points over 3 domains), lab (+60 science, or gold
  with no research set), cache (two infantry), depot (+120 gold), hive heart (an extra alien
  brute guard; +100 science and the first unknown alien tech). Only cities alien-held at the
  start have contents; cities lost later have none.
- **Rumours and intel.** A known alien city shows its rumour category. Full contents come from a
  recon unit or engineers standing on or beside it (checked after moves and at turn end), kept
  in `Player.intel`. Espionage does not reveal contents yet.
- **Sabotage.** Engineers or recon beside an alien city, with moves and not having acted: -15%
  of its maximum HP (counted as the saboteur's damage for liberation shares), the saboteur takes
  5-25 damage (combat stream). Ends the unit's turn.
- **Resistance.** Any unit beside an alien city, 40 gold, one level a turn, up to 3. Each turn
  a city rises with chance 15% x level: -40% of its maximum HP, its garrison -30 HP, one level
  used. Uprising damage is shared among the arming players.
- **Nests.** 1-2 per alien city, 2-3 hexes away on open land, not on cities, finds or
  improvements. Each heals its city 5 HP a turn (if not besieged) and adds 1 production to its
  store. A player soldier (not a civilian) on a nest at turn end destroys it (counts as a kill).
- **AI.** AI players do not sabotage, arm resistance or read plans yet; they defend as before.
- **Balance.** Cities lost per game fell from 0-3 (M11) to 0-1, since announced strikes give
  defenders 3 turns. Heat and cohort size are the levers if the aliens need more bite.

## M13: the council of continents (designer 2026-11-15, docs/SPEC_M13.md)

- **Radio contact.** `contact.radio_start` (true): every player has met every other at the
  start, so trades, aid, alliances and gifts are open from turn 1. Radio contact shares no city
  locations; those are still found by exploring. Sighting and beacon contact still exist but
  have nothing left to do while radio is on.
- **Influence.** Computed from the credit ledger (cities freed or reclaimed 10, aid 1 per 50
  gold, 3 per unit, 5 per tech, shards 5, recruits given 3), plus the agenda bonus, plus
  `Player.influence_adjust` (proposals -15, extra votes -10 each, pledges +2 paid, -5 missed).
  Influence can go below zero through missed pledges; vote weight never drops below 1.
- **Sessions.** A session opens at the end of every turn T with (T+1) divisible by 5: up to two
  waiting proposals (oldest first) and one drawn measure (seeded; the chair election while no
  chair sits). Players vote during turn T+1; votes not cast count as abstentions. The session
  resolves at the end of T+1. The SPEC's "the chair picks the next drawn measure" is not built:
  the chair only breaks ties.
- **Weights.** 1 + influence / 50 (rounded down) plus extra votes bought. A measure passes when
  weighted yes beats weighted no; on a tie it passes only if the chair voted yes. A chair
  election goes to the most weighted candidate; ties keep the sitting chair, else the lowest id.
- **Measures.** Research pact (+10% science, -5% gold), beacon silence (heat -25% via a new
  `heat_pct` effect, beacon -25%), shared arsenals (units -10% production), all for 5 turns and
  for every player through `Player.temp_effects` (read by techfx like tech effects); relief fund
  (every other player pays 30 gold to the living player with the fewest cities, if it can);
  joint strike (+15% attack for 5 turns for attacks on hexes within 2 of the alien city players
  have damaged most, else the weakest). The SPEC's fuel quota became "shared arsenals" (lending
  strategic resources has no shared-vote form yet); evacuation is the relief fund.
- **Agendas.** Five public agendas (liberator, scientist, merchant, warden, mystic), dealt by seed
  so the six players get all five; the human may change theirs on the creation screen (turn 0).
  Each gives influence for one credit (for example 5 per city freed) and lists measures the AI
  supports or opposes; anything else the AI votes yes, except a relief fund it cannot pay. AI
  chair votes go to the most influential player (itself on a tie). AI leaders propose the first
  liked measure when they have 20 influence to spare after the cost.
- **Secret objectives.** Six, dealt by seed so no two players share one: free 3 cities on
  another continent (a new credit `cities_liberated_abroad`), be elected chair 3 times, claim 3
  shards, give 300 aid gold, defeat 40 aliens, have 2 hybrids on the council. Worth 30-40 MVP
  points once met (hybrids: while it holds).
- **Later (designer):** a hidden collaborator who wins with the aliens.

## M14: the survivor start (designer 2026-11-15, docs/SPEC_M14.md)

- **Start modes.** `start.mode` (survivor) is the normal start for the web client and the runner;
  `new_game(..., start="classic")` keeps the old start, and `new_game` itself defaults to classic so
  older tests keep their worlds. The runner and session take `--start` / `start`; the New Game
  screen has a "Classic start" box.
- **Setup.** The classic start is built, then every player unit is removed and every city a player
  held becomes alien-held. The old capital is the band's **first town**: population capped at 2,
  not a capital (it becomes the capital when freed), full HP, garrisoned by one alien hatchling,
  with no contents and no nests; it neither grows nor spawns until taken. Other formerly held
  cities get a hive guard. The band (leader 20 attack, four survivors 10, both not buildable, no
  gold upkeep, vision 2 and 1) stands on a seeded hex 3 from the town.
- **Caches.** 8 per band within 7 hexes (seeded, on the player's continent, off cities, finds and
  nests): 2 within 3 hexes always hold a rifle or armour, the rest by weight (weapon 4, armour 3,
  alien weapon 1, survivor 3, scrap 3). Any player unit stepping on one takes it (after its move,
  or at turn end). Gear goes to that unit if its slot is free or the find is better, else to the
  nearest band unit that can use it. Weapons add attack (+5, alien +12), armour defence (+5), as a
  flat addition to base strength.
- **Barricades.** The designer's rule ("no capture without a weapon or armour upgrade or an
  additional citizen") is a rule, not a number: a first town cannot fall below 1 HP until its band
  has found at least one weapon, armour or survivor (`Player.band_finds`, kept even if units fall).
  Tuning combat alone could not do it: a passive town always falls to attrition. Scripted assaults
  on 9 towns: a bare band never takes it in 14 turns; one weapon or one more survivor takes it by
  turns 3-7.
- **Founding.** Freeing any city of one's own continent while unfounded founds: the leader leaves
  the map, survivors without gear join the city's population, geared survivors stay as units,
  scrap goes into its production store, and engineers, a recon team and the city's defence unit
  appear. Unfounded players are not "fallen", and have no research prompt (no city, no science).
- **Escape.** At turn end an unfounded player with no leader unit gets its leader and 2 survivors
  back near the band's starting hex.
- **Hiding.** Alien hunters ignore band units farther than 2 hexes (1 in forest or hills). Aliens
  still see the whole map and still attack adjacent band units opportunistically.
- **AI bands.** Loot caches they have seen, scout the frontier near home while they have found
  nothing, and storm the town once they have a find and (gear, six people, or turn 9); a unit
  attacks only if it keeps 20 HP after the worst counter-blow, or the blow takes the town; else
  it rests.
- **Balance (10 seeds, 100 turns).** Every band took its first town: median turn 7, 47 of 60 by
  turn 10, the last on turn 19. No player city was lost and no continent fell; liberations per
  game 15-30 (median 22, classic M13 25.5).

## Before the first playtest (designer 2026-11-16)

- **Crates and the town.** No crate in the band's sight at the start: the two gear crates lie one
  hex past it (nearer than the town; the nearest unseen hexes where coast crowds the edge), the
  rest out of sight within 7 hexes. The town starts 4 hexes away, out of sight and unknown (the
  band finds its old towns again), at 70% HP. AI bands still head for it directly (they remember
  where their capital was). AI first towns (10 seeds): all 60 taken, median turn 9, 39 by turn
  10, the last on turn 25; first finds on turn 1.
- **Barricades stay silent.** The rule is unchanged but no screen or advisor names it; the
  advisor only says crates may hold gear and the town is near.
- **Radio contact.** Players meet only by radio: a city holding a radio tower puts its player on
  the air, and everyone on the air has met (no city locations shared). Sighting, beacon and
  distress contact are off (`contact.radio_building`; `null` restores them). The radio tower costs
  12 production (about 2 turns for a first city), needs no new tech, has no maintenance and still
  widens city sight. Classic capitals start with one; a survivor band's old towns lost theirs.
  Only players on the air sit on the council (vote, propose, receive relief, stand for chair).
  Diplomacy, aid and gifts still need contact, so they wait for the radio too.
- **AI tools.** The first city builds the radio tower first; every city builds a UAV patrol once
  it has Drone Warfare (now on the AI's research path after Mechanized Warfare) and two military
  units; soldiers within 6 hexes of a city whose UAV saw a strike go to defend it; a unit beside a
  known alien city arms its resistance (one a turn, keeping 120 gold spare); idle soldiers clear
  nests within 4 hexes; scouts beside an alien city sabotage it while above 60% HP. Seed 3 over
  100 turns: 34-56 resistance armings, 28-36 nests cleared, 13-19 UAVs, 0-3 sabotages.

## M15: the settlement sandbox (designer 2026-11-16, docs/SPEC_M15.md)

- **Separate from the main game.** Its own state (`beacon/settlement.py`, `data/settlement.yaml`),
  its own session and API (`web/sandbox.py`, `/api/sandbox`), its own page (`sandbox.html`, linked
  from the title menu). Deterministic and integer-only like the main game, seeded through the
  `events` stream.
- **Layout.** The city hall hex (6 slots, the hall takes one) and six ring hexes dealt by seed
  from a fixed mix: two grain (plains and grassland, 3 slots), two forest (timber, 2 slots), two
  hills (stone and iron, 2 slots). A farm and a lumber camp stand at the start.
- **Goods.** Grain, timber, stone, iron, each with a storage cap (granaries and warehouses add);
  excess is lost at the turn's end. Gold is separate and comes only from the start (60) and the
  Exchange.
- **Workers.** Producing buildings (farm, lumber camp, quarry, iron mine, workshop) need one person
  each, staffed in that order; people beyond them only eat. Each person eats 2 grain; growth costs
  30 grain from the store when there is room (6, plus 3 a house); hunger loses one person a turn.
- **Construction.** Materials are paid when ordered; labour (3 a turn, plus 3 a staffed workshop)
  goes to the queue in order. Cancelling returns the materials (up to storage). Slots count
  queued buildings.
- **Strength.** Every building adds strength (city hall 10, watchtower 8, others 1-2), all of it
  counting against a raid on any hex (city_share_pct 100). Walls on the struck hex's outer edges
  add theirs (wood 10, stone 22, iron 40); hardening replaces a wall.
- **Raids.** Turn 6, then every 5 turns; strength 18 + 9 per raid; seen 2 turns ahead (hex and
  strength). Held - the walls there lose 60% of the raid's strength as HP, shared. Broken - the
  walls lose its full strength, the building with the most labour on that hex is wrecked, and 25%
  of every store burns. A scripted sensible player held 38 of 50 raids (30 turns, 10 seeds).
- **The Exchange.** Sells at 60% and buys at 160% of the current price; each price index drifts
  up to 8% a turn (seeded) and back toward 100, sags 2% per 10 sold, rises as much per 10 bought,
  within 50-180%.
- **The view.** A canvas with a 35-degree tilt: raised hex slabs with the photo ground textures
  and painted forest sprites, rocks drawn in code, buildings as Blender renders
  (web/static/settlement), walls drawn along edges with HP bars, a raid warning (arrows and a
  countdown), and a short raid scene (raiders march in, hit the wall, the result shows).

## M16: materials and the city builder (designer 2026-11-16, docs/SPEC_M16.md)

- **Materials.** Each city stores timber, stone and iron (caps 150/150/80; a new storehouse
  building adds 150 each). They come from the city's own hex (+1 timber, +1 stone) and from worked
  tiles: forest or jungle +2 timber, hills +1 stone, mine +2 stone +1 iron, the new **lumber camp**
  improvement (forest or jungle, no tech) +3 timber, extractor +1 timber, some resources more. Only
  worked (improved) tiles count, as for food. Food stays the main game's food (no grain bank).
- **Costs.** A building costs 30% of its production in timber, plus 20% in stone from production
  80, plus 10% in iron from tech tier 3, unless its data lists `materials`. Industrial units cost
  iron (armour 25%, artillery 20%, naval 20% plus 10% timber). Materials are paid when the item
  completes; short stores stall it with a "needs" event. Gold buys the work, never the materials.
- **Barracks.** Melee and ranged units (land and sea, not recon, civilians or city defences) need
  the military base (now called the barracks) in the city. Classic capitals start with one; a
  band's old town loses its barracks and radio to the aliens.
- **Layout.** Fine grid of 8 cells across a hex; a city's land is every cell whose centre lies
  on a passable land hex of its work area that it holds. Footprints are squares (city hall 4,
  most 2, large buildings 3); a 1-cell gap between buildings; walls may stand in gaps. Placing a
  building orders it (queue + position); a building queued without a place is set at the free
  spot nearest the centre when it completes; existing buildings and freed cities' buildings are
  placed the same way. Removing a placed building from the queue frees its place. Moving is free.
- **Walls.** One piece per cell: wood (timber 1, 1 production, 0.1 strength, 2 HP), stone (stone 1,
  1, 0.2, 3), steel (Mechanized Warfare; iron 1 + stone 1, 2, 0.3, 4), chitin (Organic Armour), plasma
  (Directed Energy). A "walls" queue item builds every piece laid out. Defence perimeter, plasma
  shield and chitin bulwark are no longer buildings. City strength gains a line per material
  (tenths summed, rounded down); city HP gains the pieces' HP.
- **AI.** Picks only items it has the materials for (and re-chooses when the head is short),
  builds a barracks in the capital early, engineers build lumber camps on forest, and every few
  turns (staggered) lays a square ring 6 cells from the centre in the best material it knows when
  the stores allow, upgrading later.
- **Balance (10 seeds, 100 turns, survivor start).** First towns as before (median turn 9). Cities
  freed per game 15-32 (median 26.5). The barrage started by turn 100 in 1 of 10 games (4 of 10
  before materials): building now waits on timber and stone.
- **Later (designer).** Citizens crafting weapons to defend themselves; a Clash-style separate mode
  fed by blueprints and rewards from the main game.

## Leader creation revision (designer 2026-11-16)

- **15 skill points.** At creation the player spreads 15 points over the six skills, at most 5 in
  one, and must spend them all to start (`start.skill_points`, `start.skill_max`; replaces +1 in
  every skill). AI leaders get theirs spread one point at a time by seed, under the same cap.
  Levels still add one point each, with no cap. Hybrids average the leader's current total
  (now 15 and up) with the alien parent's.
- **Start.** The creation screen ends with a Start button: it saves the leader (and agenda) and
  begins the game; the "keep the generated leader" option is gone (closing the screen still keeps
  it).
- **The band's leader.** The band's lead unit shows the leader's name and portrait (other
  players' show as "<continent>'s leader"); it is still the 20-strength band_leader unit, with
  four 10-strength survivors.


## Develop city: engineers and production from the builder (designer 2026-11-16)
- "Choose production" is now "Develop city" and opens the city builder. The city panel no longer
  lists buildings and units with turns and gold; it shows the queue and the button.
- The builder gains a Land tab (click a hex of the city's land, choose a farm, mine, camp...) and a
  Train tab (units and projects join the end of the queue), and shows the queue with remove and buy.
- Tile works are ordered per city (`ImproveTile`): the free engineer on the city's land nearest the
  hex walks there and starts the job. Only engineers standing on that city's land can be sent, so
  engineers trained elsewhere must be walked over first; none free means "train some".
- Engineers no longer ask for orders on the map, and the map no longer offers them tile works.
  Roads, railways, turrets and sea bridges stay map orders (they reach beyond a city's land).
  The AI still orders tile works from the map as before (same rules, same result).

## M17: labour and materials (docs/SPEC_M17.md, designer 2026-11-16)
- Engineers are a per-city count (the crew), not units. Each gives 8 labour a turn (placeholder);
  a building needs labour equal to its old production cost, so a 45-cost library takes 3 turns with
  2 engineers. Works are built top first; the first takes what it needs and the rest passes on.
- Materials are paid when a work is ordered and refunded in full on cancel; refunds may exceed the
  store cap. A city short of materials cannot order the work (the Exchange can cover a shortfall).
- Training an engineer costs production (30 + 15 per engineer the city has) and each costs 1 gold
  a turn. Capitals start with 2, other cities 1, a band's first town 2; a freed or captured city
  gets 1 when it first works.
- The Builder trait and Robotics now also give +25% labour (labour_pct); their -1 turn still
  shortens tile works.
- The map's engineers unit stays as the road crew for roads, railways, turrets and sea bridges;
  starting and founding engineers units are removed. Repair crews still rebuild pillaged works.
- The Exchange has no random drift (the sandbox had a seeded one): prices move only with trade and
  drift 2 points a turn back to 100. One index per good, shared by all players.
- The AI orders one building at a time (its old priorities), keeps a crew of 3, improves worked
  tiles with the crew, sells stores at 90% of cap and buys small shortfalls when it has gold.
- Old saves: buildings left in a production queue still finish from production; wall pieces
  ordered before M17 become a crew work (still unpaid, as they were never charged).
- Balance after M17 (10 seeds, 100 turns, survivor start): first town median turn 9 (as M16);
  cities freed median 62 (M16: 26.5); the barrage starts in 10 of 10 games (M16: 1). With
  buildings off the production queue, all production trains units, so AI armies roughly double.
  Needs tuning (alien strength or unit costs) once the designer has played it.
- The AI re-chooses a filler project (wealth, research) every turn instead of keeping it, since
  projects never finish and buildings no longer empty the queue.

## Funding the resistance (designer 2026-11-16)
- Any player may send gold to the resistance in an alien-held city it has found (no unit needed:
  word reaches them). The city's defence strength falls by the funded percent (the last step of
  city_strength, after garrisons), up to 50% in all, until the city is freed.
- The band's first town: 100 gold (the whole starting treasury) buys 50% and opens its
  barricades. A to-do item and a dialog offer it once the band has found the town; "Not now"
  hides it for the session. Elsewhere 1% costs strength x 0.5 gold (a 40-strength city: 20 gold
  a percent, so 500 gold buys 25%); offers are 100, 250 and 500 gold. Placeholder.
- AI bands fund their first town as soon as they know it, then attack.
- Leader creation keeps its scroll position on every click and shows the points left beside the
  Skills heading and the Start button.

## The homeless start and agenda perks (designer 2026-11-17)
- No first town is assigned: the first alien-held town of its own continent the band sights
  becomes its first town (the old capital if several are sighted at once, else the nearest). It
  is weakened when found like the old capital (pop 2, 70% HP, a hatchling garrison, no radio,
  barracks or nests), and 100 gold to its resistance takes 50% off. Checked after each band move
  and each turn. Old saves: a band that has sighted a town claims it on its next move.
- The leader has 30 strength and survivors 20 (were 20 and 10).
- The first attack click on an unfunded alien city opens the funding offer ("Attack without it"
  attacks); the attack preview warns "Fund the resistance first".
- Fortify and Skip close the unit panel when no other unit needs orders.
- Agenda perks (tech-effect format in data/council.yaml): Liberator - resistance gold goes 25%
  further; Scientist - +10% science; Merchant - 10% better Exchange prices; Warden - +3 city
  strength; Mystic - +10% beacon. They stack with traits.
- Batch (10 seeds, 100 turns): AI bands take their first town at median turn 3 (fund, then
  attack at once); cities freed median 70.5; the barrage starts in 10 of 10.
