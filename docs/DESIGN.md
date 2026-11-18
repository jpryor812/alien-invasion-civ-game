# Beacon (working title): Design Document

Status: first draft, decided in conversation with the designer. Items marked **TUNE** are
placeholders to be settled by simulation and play. Items marked **OPEN** are undecided.

## 1. Pitch

A turn-based 4X strategy game in the family of Civilization V (hex map, cities, units, tech) with
Crusader Kings III style characters. Modern Earth has been invaded and fogged by aliens. Each of
six players leads one continent. Nobody fights each other. Everyone fights the aliens, and
everyone depends on everyone else, because a continent that falls leaves the others to face the
invasion alone.

The signature features:

1. **Cooperation with a personal score.** The world wins or loses together, but each player is
   ranked by an MVP score. You want the team to win and you want to be the one who did the most.
2. **Beacons and alien characters.** A fourth tech branch lets you call aliens from other worlds
   to your side. They are characters with stats, traits and lifespans. They can be councillors,
   be traded, be gifted, or betray you.
3. **Perpetual fog and rediscovery.** Your cities and units are all you can see. Your continent
   starts with many lost cities that you must find, reconnect and free before aliens take them.

## 2. Design pillars

- **Common foe, uncommon interests.** Every nation is safer when the others do well, and every
  player wants to finish first in contribution.
- **Liberate, do not conquer.** Expansion is recovery. There is no happiness or stability penalty
  for growing fast. The brake on growth is thin defences and the aliens.
- **Information is the scarce resource.** Fog makes scouting and beacons matter.
- **Aliens as people.** Recruits are individual, random and memorable, not stat blocks.
- **Choice density near Civ V.** Plenty to do each turn and real competing choices, but less than
  Crusader Kings III. Not an overwhelming opening: the first ten turns are scripted by goals.

## 3. Players and map

- Six playable continents: North America, South America, Europe, Asia, Africa, Oceania.
- Single player first (you plus five AI continents). Online multiplayer later, six humans, turn
  based, simultaneous turns with a timer.
- The map is hex based and large. Each continent has its own climate, terrain, resources and
  15 real cities. A player starts with just its capital (New York for North America); the other
  fourteen are held by the aliens and must be liberated (designer 2026-11-14; was three known).
  (Also 2026-11-14: continents drawn from real geography, about twice as big, cities farther
  apart; previously about 20 cities with a handful known.)
- Oceans are safe from aliens (**OPEN**: confirm aliens never cross water).
- A fallen continent can be revived (see section 13).

## 4. The turn

Each turn a player may: set city production, queue buildings, move and fight with units, explore,
found or re-found cities, build roads, railways and beacons, choose research in four trees,
manage the alien council, trade and trade deals, send aid and troops to other continents, fund
shared projects, and take part in alien espionage.

Target breadth: about Civ V. A typical mid-game turn has perhaps 10 to 20 meaningful decisions,
with trade-offs between them (production vs defence, research branch vs research branch,
helping a neighbour vs your own frontier).

## 5. Fog, exploration and lost cities

- Fog is permanent. Units see one hex around them. Leaving an area returns it fully to fog,
  terrain included, unless you have a building, road or beacon there (decided 2026-11-13).
  Cities, once discovered, stay on your map with their live status.
- A **radio beacon** built on a hex keeps it permanently revealed (mid-game tech). Any building on
  a hex also keeps it clear.
- Every lost city is held by the aliens and must be liberated in battle; a liberated city is its
  continent's again, with its farms and some of its people. (Updated 2026-11-14 by the designer:
  previously lost cities could also be dormant, reclaimed by walking in, or empty ruins rebuilt
  by a restoration team; both are gone, and so is the restoration team.)
- **Citizens** (designer 2026-11-14): a city's population is its citizens. Spare food brings
  births; a newborn is a child and must grow up (faster with more food) before it works. Each
  citizen has 6 stat points (+1 in all six domains, +3 in two, or +2 in three) and maybe a trait,
  shown like a recruit's. A grown citizen works one **improved** tile (bare tiles cannot be
  worked), adding half its stats there, or sits on the continent council, adding its full stats to
  every one of its owner's cities (designer 2026-11-15: the council is territory-wide, tile work
  is city-wide). Example: a mine gives +3 production; a +2 production/science/gold citizen on it
  makes the tile +4 production, +1 science, +1 gold; on the council it adds +2 of each to every
  city instead.
- Every city produces from the turn it exists (designer 2026-11-15, replacing "a city must be
  reconnected before it produces"). A road or railway to the capital adds gold each turn and
  carries strategic resources and convoys; roads still speed units. A convoy sends a share of a
  city's production or spare food to a friendly city joined to it by road (docs/SPEC_M10.md).
- Production goes into the item being built and stays with it; switching keeps each item's own
  progress. Any allowed item can be bought with gold at any time, cheaper for progress made.
- The world wraps east to west, and is about 60% land: the six continents sit across straits a
  hex wide. Researching Beacon Theory makes contact with every player. Explored land stays clear
  of fog; only units out of sight are hidden. Each continent starts with 3-5 meteor remnants to
  find and mine (docs/SPEC_M10.md).
- Hex improvements: resource extraction, farmland, military bases, roads, railways, beacons.
- Resources work as in Civ: developing a resource tile grants the resource and bonus yield.
- Aliens roam in fog. A large alien force can arrive unseen beside a city. Scouting and beacons
  prevent that.

## 6. Economy, cities and units

- Yields: food, production, science, gold, and beacon points.
- Cities grow, build, and have defence strength. Buildings include farms, factories, walls,
  ports, labs, beacons and military bases.
- Units are shown on the map as in Civ V. Melee and ranged units, terrain and altitude bonuses.
- **Combat** follows the Civ V model (decided 2026-11-13, replacing "auto-resolved when units
  meet"): each attack is one command, strength against strength, damage taken off hit points,
  terrain and flanking modifiers, a small seeded variance and a damage preview for both sides.
  Ranged units attack without retaliation. A melee winner advances into the hex.
- **Stacking** (decided 2026-11-13): one military unit per hex, except that two units of the same
  type and owner may merge into one stack with double strength, one attack, and combined hit
  points. If the stack loses more than half its 200 hit points, one member dies. A stack can split;
  the unit that moves out is the full-health one. Applies to land, ranged and sea units.
- **Era** (decided 2026-11-13): the game starts in 2025 with present-day technology known and
  researches into near-future technology.
- Units can be moved to another continent (by sea) to fight beside its owner. They keep your
  ownership, so kills and liberations count for your MVP score. Moving costs transport and
  upkeep (**TUNE**).

## 7. The tech tree

(Updated 2026-11-14 by the designer: one branching tree instead of four separate trees.) Two
starter branches, each tech opening two more: 2, then 4, 8 and 16 techs, and it keeps branching
past that. Every tech has one parent, so choosing a branch is a real commitment. The screen shows
the tree left to right with projected turns, and tags on each unlock (military, science, food...)
show what a branch is good for instead of labelling trees.

- Urban Planning: International Accords (alliances, finance, farming) and Beacon Theory (the
  beacon rarity chain, radio beacons, deep space radar, the Orbital Barrage).
- Advanced Manufacturing: Applied AI (science, industry) and Mechanized Warfare (the army).

Alien technology can also be gained through espionage (section 10), outside the normal trees.

## 8. Beacons and aliens

- A **beacon** is a building in a city. Beacons attract aliens to your territory.
- Two investment levers: **more beacons** gives more frequent alien arrivals; **stronger
  beacons** gives stronger aliens that arrive less often. Both together give frequent strong
  aliens, at rapidly rising cost (**TUNE**).
- A recruit is a random character, as in Crusader Kings III. Six scores (decided 2026-11-13): **food, production,
  military, science, gold, beacon**. Some are specialists, some are generalists.
- **Traits** (random, each with effects): examples to be designed, such as loyal, ambitious,
  traitor, mortal, immortal, short-lived, berserker, scholar. Some recruits die, some are
  immortal, some may turn traitor.
- **Councils** (decided 2026-11-13): two seats on each domain council (food, production,
  military, science, gold, beacon) and three general seats. A recruit on a domain seat applies its score
  in that domain and may sit on one seat in several domains; a recruit on a general seat applies
  all its scores. A score of N is +N% in that domain.
- **Beacon levers** (decided 2026-11-13): five speed levels (Beacon I-V buildings) and five
  rarity levels (beacon-tree techs), both with steeply rising costs.
- **Lifespans and betrayal** (decided 2026-11-13): recruits live 50-100 turns, some are immortal.
  A betraying recruit never sabotages: it leaves and joins an alien city, and freeing that city
  brings it back.
- A recruit can be **kept, sold or gifted** to another continent. Trade is how a weak continent
  gets help and how a strong beacon continent profits.
- Recruits are mostly random, with a few named legendary characters.

## 9. The aliens

- They hold many cities at the start and progress quickly early. They have their own tech tree
  (better units, walls, mines, growth) that makes captured cities harder to retake.
- **Tipping point:** alien progress depends on how many cities they hold. As you liberate cities
  they slow down. A floor stops them from stalling, and surge events keep a winning player from
  coasting (**TUNE**).
- The longer a continent takes to explore, the more cities fall.
- As they shrink they harden into fewer, stronger fortresses supported by the mothership.
- Aliens keep reappearing from the mothership until the reinforcements are stopped (section 11).

## 10. Alien espionage

- A project funded by one player or by several. Its reward is an **alien technology** that is not
  in the normal trees, so it cannot be gained any other way and is not known in advance.
- Funding is either self-funded (only you receive the tech) or collaborative (everyone receives
  it). The largest contributor chooses which of the offered techs is gained.
- There is no espionage between humans. No sabotage between players.

## 11. Mothership and the missile barrage

- The mothership hovers over Earth. It spawns reinforcements and occasionally, somewhat randomly,
  strikes a city with a **missile barrage of its own** that severely damages it.
- The **world barrage** is a late-game shared project, researched and built by the continents.
  It can be researched and fired before every alien city is freed. It is a defended megaproject:
  building it takes many turns and the aliens learn where it is being developed and target those
  cities more.
- Researching it can stop reinforcements before the mothership is destroyed. Aliens already on
  Earth keep improving.
- Destroying the mothership ends reinforcements and the mothership's strikes. It does not end
  the game by itself: it is one of the two victory conditions (section 12). Remaining alien cities
  still progress, so humanity can still lose.
- From the start of the barrage project to its completion is a fixed number of turns (**TUNE**).
- Late-game anti-coasting ideas, to be worked on after the first playable version: shrinking
  aliens become fortresses, spawns scale with how close the barrage is, mothership strikes
  continue, and MVP credit keeps counting through the finish. Known risk: when only a few alien
  cities remain the outcome is obvious and the mop-up may be dull (**OPEN**, deliberately
  deferred).

## 12. Winning, losing and MVP

**Shared outcome**
- **Victory (decided):** the mothership is destroyed **and** every alien city on Earth has been
  liberated. Both are required, in either order. The game ends on the turn the second one is met.
  Because fog hides cities, late-game tools for locating the last alien cities (high-tier
  beacons, a costly sweep) are needed so the final hunt is not a chore (**TUNE**).
- **Defeat (decided 2026-11-13):** all six continents fallen at once. Defeat is possible even
  after the mothership is destroyed.
- If the world loses, everyone loses. There are no lone survivors. Scores still show how each
  player played.

**MVP (individual)**
Players are ranked by an MVP score from: aliens killed, cities liberated (credit split by
contribution when helped), population saved, aid given, units contributed abroad, alien
contribution (recruits, espionage funding), and the barrage project. Weights are **TUNE** and
should be balanced so a builder and a fighter can both finish near the top (first tuning in M7:
`data/mvp.yaml`, `docs/BALANCE_M7.md`).

## 13. Fallen and revived continents

A continent falls when it holds no cities (decided 2026-11-13). Its player is not
removed. Another continent can send forces to liberate cities there, and the continent revives,
weak (few cities, low population), so a rescue is a real investment. This applies to AI and human
players alike.

## 14. Trade and diplomacy

- Trade between **port cities** is safe and quick, with a short delay that grows with distance.
- Overland trade passes through fog and is at risk, so needs an escort. Reaching a port makes the
  goods safe at sea.
- Tradable: resources, gold, units, alien recruits, research/technology, and shared projects.
- Diplomacy is cooperative: aid, trade, shared funding, alliances. There is no war between
  players. Tension comes from limited resources, who gets help first, who funds what, and who earns
  the MVP.

## 15. AI

AI continents run the same rules as players, deterministically, with no LLM calls in the game.
They differ by character (builder, fighter, trader, isolationist) so a single-player game has
varied partners.

## 16. Technical approach

- **Headless simulation first**, in Python, no UI: a deterministic, seeded engine with plain data
  state that serialises to JSON, tested and tunable in batch runs, as for a previous project.
- Then a web client with a Civ V style hex map and units.
- No magic numbers: all tunables in data files, tagged placeholder or calibrated.

## 17. Milestones (proposed, each needs approval before starting)

- **M0:** repo, tooling, config, seeded RNG, empty state.
- **M1:** hex map, terrain, resources, cities (known and lost), fog. (All six continents are
  generated from M1, since it costs little; AI and cross-continent play remain M6.)
- **M2:** cities and economy: yields, production, buildings, roads and railways, and tech gating
  for the economic, production and military trees (pulled forward from M5; the beacon tree stays
  in M5).
- **M3:** units and auto-resolved combat, with terrain bonuses.
- **M4:** the aliens: growth, tech, tipping point, invasion director.
- **M5:** four trees, beacons, recruit characters, councils, traits.
- **M6:** six continents, AI, trade, aid and cross-continent troops.
- **M7:** mothership, barrage project, MVP score, endings, balance runs.
- **M8:** web client.

## 18. Open questions

- Game length: no turn limit; AI games are won around turns 130-200 (M7 balance runs).
- Late-game boredom once few alien cities remain (deferred by the designer until after the
  first playable version).
- Do aliens ever cross water? (assumed no.) Aliens see through fog (decided 2026-11-13).
- Turn limit (decided 2026-11-13): none. A game runs until victory or defeat.
- Trait list and recruit lifespans.
- Later (designer 2026-11-16): eras, material banks instead of production points, walls built
  from materials, a city builder view and battle scenes - see docs/FUTURE_SETTLEMENTS.md.
- MVP weights.
- Number of beacon investment levels and cost curves.

## M11: ocean bridges and the leader (designer 2026-11-15, docs/SPEC_M11.md)

- **Sea bridges.** Engineers with Robotics build a sea bridge over shallow water beside the
  shore or another bridge (6 turns). Bridged hexes are land at road speed: armies, roads and
  convoys cross, continents join, and aliens can cross and pillage them too. Deep ocean cannot
  be bridged. AI players bridge toward their allies.
- **The leader.** Every player has a leader (generated for the AI; made on a creation screen by
  the human): name, look, age and two traits. The leader heads the 16-seat council and is not a
  unit. Six skills start at +1 and count in every city (military as city strength); XP from
  achievements raises levels, each giving a skill point, and milestones offer bonuses for the
  game. A third trait comes at level 5. The leader ages but never dies.
- **Family.** The leader can start a family with a grown citizen or a seated alien recruit; the
  child is born in the capital. Hybrid children are stronger, some cities refuse to let them work
  their land, and on the council they risk being voted out.
- **Leader screen.** The leader stands full height on a backdrop (Meshy renders), with traits,
  skills, XP, choices, family, wardrobe, milestones and career. Outfits and accessories unlock
  from a local career profile and are cosmetic only.

## M12: a readable alien (designer 2026-11-15, docs/SPEC_M12.md)

- The aliens plan their strikes three turns ahead (units gather, then strike). A city with a UAV
  patrol (Drone Warfare, mid-game) sees it coming: a red arrow and a countdown on the city, and a
  Threats list. Without one, the first sign is the attack (designer 2026-11-16).
- Heat: population and loud buildings (beacons, industry, labs) draw the aliens' attention.
- Each alien city holds something (survivors, a lab, a captive, arms, wealth, a hive heart),
  first heard as a rumour and confirmed by scouts; freeing the city gives it. Choosing which city
  to free first replaces choosing where to found a city.
- Other ways to free a city: sabotage, arming the resistance (uprisings), destroying nests.
- docs/PRESSURE_AUDIT.md maps every building and unit to the pressure it answers.

## M13: the council of continents (designer 2026-11-15, docs/SPEC_M13.md)

- Everyone is on the council from turn 1 by radio; land and cities are still found by exploring.
- Influence, earned by freeing cities, aid, shards and the leader's agenda, weighs votes and pays
  for proposals. Every 5 turns the council votes on measures: research pact, beacon silence,
  shared arsenals, relief fund, joint strike, chair election.
- Each leader has a public agenda (how they vote) and a secret objective worth MVP points. The
  top bar shows influence and MVP rank.
- Noted for later (designer): a hidden collaborator who secretly wins with the aliens.

## M14: the survivor start (designer 2026-11-15, docs/SPEC_M14.md)

- The normal start: no city, just the leader (30 attack) and four survivors (20; designer 2026-11-17). Crates nearby
  hold rifles, armour, alien weapons, more survivors and scrap.
- The band's first town is its old capital, lightly held. Its barricades hold until the band has
  found something; then it falls in a few turns (usually by turn 10) and becomes the capital: the
  survivors move in, scrap becomes production, and research and building begin.
- If the leader falls first, it escapes with two survivors. A Classic start (cities and an army)
  remains as an option.
- Contact is by radio only (designer 2026-11-16): a player reaches other continents and the
  council once a city of theirs has a radio tower (cheap; the first thing a new city builds).

## M15: the settlement sandbox (designer 2026-11-16, docs/SPEC_M15.md)

*Retired in M17: the sandbox's ideas (materials and labour, storage, the Galactic Exchange) now
live in the main game, and the sandbox page is gone.*

- A playable prototype of the material economy and the close-up city view, separate from the
  main game (title menu: Settlement Sandbox): goods from staffed buildings in hex slots, storage,
  people who eat grain, construction with materials and labour, walls on the outer edges, raids
  every few turns, and the Galactic Exchange. If the loop feels right it replaces production
  points in the main game, and the close-up view becomes the zoomed-in map (docs/FUTURE_SETTLEMENTS.md).
- Persistence (designer brainstorm 2026-11-16): standard games start fresh; ideas for later are
  city blueprints saved to the career profile (still paid in materials), a legacy campaign that
  carries the best city into a harder next game, a Clash-style home base, and asynchronous
  multiplayer.

## M16: materials and the city builder (designer 2026-11-16, docs/SPEC_M16.md)

- Cities gather timber, stone and iron from the land they work (forests with lumber camps, hills
  with mines) and store them. Buildings and walls cost materials plus work; tanks, artillery and
  ships also cost iron. Soldiers are trained only where there is a barracks.
- The **City builder** (button on the city panel) switches to a close view of the city's land:
  no hex lines, only its border. Choose a building, a blue ghost follows the cursor, click to
  place; drag to lay walls of wood, stone and later steel, chitin or plasma. What you build and
  what you build it from decide the city's strength and HP.
- Art: eight Meshy buildings (city hall, library, market, barracks, workshop, factory, radio
  tower, food depot) and Blender models for the rest.

## M17: labour and materials, one game (designer 2026-11-16, docs/SPEC_M17.md)

- Each city has a crew of **engineers**. Buildings, walls and tile works (farms, mines, camps)
  are works: their materials are paid when ordered, and the crew's labour decides the turns -
  more engineers, faster building. Engineers are trained from the city (and cost a little gold).
- Production trains units and engineers and runs projects; gold buys units, not buildings.
- The **Galactic Exchange** trades materials for gold in any city; prices move with trade.
- **Develop city** opens the builder, the one city screen: crew, works, training, land and the
  Exchange. The map's engineers unit is now the road crew (roads, railways, turrets, bridges).
- The settlement sandbox is retired.


## M18: food, rations and the rescued town (designer 2026-11-18, docs/SPEC_M18.md)

- A grown citizen eats 2 food, a child 4. A farm makes 20 food, so most food comes from farms.
- Spare food fills each town's store, the bank that pays for births (20 food, plus 5 per
  citizen) and feeds the army. The store holds 60, or 180 with a granary (the food depot). Births
  can be paused to bank food.
- Every unit carries 10 rations. Within 4 hexes of a friendly town it is fed by that town (2 food
  a turn) and its rations refill; elsewhere it eats a ration a turn, and with none left loses 10
  HP a turn. Food crates refill rations; so does freeing a town.
- A freed town keeps 30 food and has a damaged farm; the band's first town also has a broken
  radio tower. Each repair is one engineer-turn and goes first. The band's first town rescues 3
  people, so with 4 survivors it starts with up to 7 citizens.

## M19: months, the galactic winter and better farms (designer 2026-11-18, docs/SPEC_M19.md)

- A turn is a month (Jan 2025, Feb 2025 ...); the leader ages a year every 12 turns.
- The galactic winter: a seeded random event from turn 24 (3% a turn, at least 36 turns apart),
  warned 3 turns ahead, lasting 12 turns. Crops give half their food, pastures three quarters.
- Pastures (livestock): 12 food and 1 production, on hills too. Urban Planning gives farms +5,
  International Accords pastures +4, Vertical Farming hardier crops (75% in winter), Climate
  Engineering no winter loss.
