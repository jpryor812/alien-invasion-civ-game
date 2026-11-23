# M10 — Playtest changes (designer feedback, 2026-11-15)

Status: draft for the designer's approval. The designer's words are quoted; everything else is a
proposal. The designer answered the three open questions on 2026-11-15 (see section 9).

## 1. Council and tiles

"People on councils don't work tiles - tiles don't get bonuses unless non-council citizens are
assigned to it, so council is territory wide and tile assignment is city wide."

- Today a council citizen already works no tile, and a tile yields only when a citizen works it.
  The change is the reach of the council: a council citizen's stats will count in full for
  **every** one of the player's cities, not just its home city (designer: full stats, every city).
- Tile work stays city-wide: a citizen works one improved tile of its own city.

## 2. Meteor remnants

"I'm not finding any meteor remnants ... Each continent should have 3-5 that each player can
find."

- Today shards fall one at a time from turn 20 (about every 20 turns), and nothing is placed at
  the start. Proposal: 3-5 remnants are placed on every continent at the start, minable like a
  shard (an engineer or scout for 5 turns) and giving a shard's reward. Starfall continues on top.
  They are shared: the first player (or the aliens) to mine one takes it (designer).

## 3. Cities, roads and convoys

"We shouldn't have to build a road for that city to produce something ... maybe connecting the
cities grants gold and obviously units go faster."

- Every active city produces food, production, science and gold from the turn it exists. Being
  unconnected no longer stops a city, and buying is allowed in any city.
- A city joined to the capital by road, railway or city tiles earns a **connection bonus** of
  +2 gold a turn (a tunable). Roads keep their faster movement.
- **Convoys** ("send production or food to a friendly city, a road between the cities is
  required"): from a city's panel, set up a convoy to another city of yours, or an ally's,
  joined to it by road or rail. Each turn it moves a chosen share (25 or 50%) of the sender's
  production or food surplus to that city, arriving after the road travel time. It can be
  cancelled at any time. The route must stay joined; a cut route pauses it.

## 4. Production and buying

"Production for an active unit/building should only apply to that unit or building, it saves if
I change to produce something else ... I have to start the marines from scratch."

- Each item keeps its own progress. Switching away keeps the old item's progress; returning to
  it later continues from there. A new item starts at 0. Overflow from a finished item carries
  to the next one, up to one turn's production.
- "I should be able to buy units/buildings for gold while producing other units or buildings":
  any allowed item can be bought at any time without touching the queue. The price falls with
  the progress that item already has.

## 5. The map

"I can't go onto the whiter fog to the right ... The earth is round, there shouldn't be an edge."

- The world wraps east to west, as a cylinder (Civ's way). North and south stay polar ice.
- "The ocean seems much more vast than the land - it can be more 60/40 land/ocean." Land
  becomes about 60% of the map.
- "Maybe more of a pangaea map - I'd like to discover a friend by turn 15." Answer (designer):
  six continents kept, larger and separated by narrow straits, so scouts and boats cross early.
- "Maybe level 1 of the beacon also allows you to meet new people without having to find their
  cities": researching Beacon Theory (beacon level 1) makes contact with every other player.

## 6. Fog

"Better to remove the fog after we discover it - it's more exciting when you complete
discovering the map."

- Explored hexes are drawn fully clear: terrain, improvements, cities and borders. Only units
  outside your sight stay hidden, as in Civ. Unexplored hexes keep the cloud.

## 7. Science

"Early science discoveries should be a lot less science cost - ideally about 10 turns on
average." "There should be an introductory science building."

- Tech costs are lowered so the first tiers take about 10 turns at a typical early science rate.
  Later tiers scale up from there, checked by a batch run.
- A new **Library** (+2 science, cheap, maintenance 1) can be built from turn 1 in every city
  without a tech. The school then requires a library.

## 8. Interface

"When we completed the action for one unit, it should pan the camera to the next unit."

- After a unit's orders are done, the camera pans to the next unit that needs orders and selects
  it, as in Civ.

## Acceptance

- Every rule above has a test; pytest and ruff pass. The 10-seed AI batch still finishes, and
  the balance notes are updated (game length, victories, first contact turn).
- In a human game, a friend is met by about turn 15 on the median seed.
- docs/ASSUMPTIONS.md records each modelling choice; DESIGN.md is updated where it changes.

## 9. Designer answers (2026-11-15)

- Council: full stats in every city.
- Remnants: shared; the first to mine one claims it.
- Map: close continents with narrow straits, about 60% land, wrapping east to west.
