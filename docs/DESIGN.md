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
  about 20 cities, of which only a handful (for example Toronto, New York, Los Angeles and Mexico
  City for North America) are known at the start.
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
- Lost cities are in three states: **dormant** (still standing, not producing), **empty**
  (needs re-founding) and **overrun** (taken by aliens, must be liberated in battle). The longer
  you take to reach a city, the likelier it becomes overrun (**TUNE**).
- A city must be reconnected by road or railway to a connected city before it produces.
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

## 7. Four tech trees

| Tree | Purpose |
|------|---------|
| Economic | gold, trade, growth, ports |
| Production | buildings, industry, infrastructure |
| Military | units, defence, weapons |
| Beacon | alien recruitment, alien power, alien council |

Trees pull against one another (you cannot research everything) and sometimes merge (a late tech
needs two trees). Science, production and buildings feed the beacon tree, but beacon is its own
branch and its own investment.

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
should be balanced so a builder and a fighter can both finish near the top.

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

- Game length: start at 150 to 200 turns, tune toward Civ V robustness.
- Late-game boredom once few alien cities remain (deferred by the designer until after the
  first playable version).
- Do aliens ever cross water? (assumed no.) Aliens see through fog (decided 2026-11-13).
- Turn limit without victory: not yet decided.
- Trait list and recruit lifespans.
- MVP weights.
- Number of beacon investment levels and cost curves.
