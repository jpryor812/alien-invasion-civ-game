# SPEC M20: a gentler first town, growing borders, and fixes from play

Designer 2026-11-19, after playing M18-M19.

## The first town
- Nothing is built for you. The damaged farm and the broken radio tower are on the map, and
  repairing them is one engineer-turn each (free of materials).
- Repairing the farm is a required step: until it is ordered, the "Repair the farm" prompt
  leads every turn and the advisor explains "this is how your citizens earn food"; the builder
  opens on the Land tab with the damaged farm marked. (Other freed towns also have a damaged
  farm, with an ordinary prompt.)
- Then the advisor suggests the radio tower (talk to the other continents) and the barracks
  (train soldiers), not forced.
- Each player's first barracks is cheap: a quarter of its materials and labour.
- After the town is taken the citizens page opens, with a note on tiles, the council and
  training soldiers.

## Prompts
- "Develop city" is a prompt only when the town has an engineer with nothing to build.
  Clicking the town opens it as before.

## Borders
- A town's land starts at its own hex and the six around it. Each citizen born claims one more
  hex next to its land (the best for food and production, preferring hexes that were already
  the town's natural area), up to 3 hexes out, never another town's.
- Towns not held by a player keep the old area (2 hexes).

## The council
- Seats stay (citizens and recruits add their stats). Sessions, proposals, votes and influence
  are off until they are redesigned (`sessions.enabled: false` in data/council.yaml).
- Freeing a citizen's seat leaves it Unassigned (it no longer jumps straight back on), so
  another member can take the seat.

## Meeting another leader
- When radio contact is made, a meeting screen shows both leaders facing each other with a
  greeting, and the options we have: propose an alliance, propose a trade, send aid, or part.

## Shards and crates
- Meteor remnants (the purple beams) can be mined by the band too, not only scouts and road
  crews; the hex label says who can mine it and shows progress.
- More crates: besides those near the band, a dozen lie across the player's continent.

## Gear and people
- A unit that finds gear it cannot use carries it (up to 2 items). Inside its own land it
  leaves the gear in the nearest town's armoury. A unit standing in a town takes gear from
  its armoury (Equip, in the unit panel; the AI equips automatically).
- Any unit standing in its own town's land can join that town as a grown citizen (survivors
  too); its gear goes to the armoury.

## The citizens page
- Each citizen's job list includes "Train as ..." at a barracks.
- A note shows that the leader can start a family (a child for the town), with a button.

## The land
- The builder's Land tab and an advisor tip say plainly that forests take timber camps
  (timber) and hills take mines (stone).
