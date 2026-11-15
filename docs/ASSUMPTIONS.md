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

