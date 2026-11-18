# SPEC M18: food, rations and the rescued town

Designer 2026-11-18. Food is the thing you balance between your people, their children and your
army. Farms make most of it; the spare goes into a bank (the town's food store) that pays for the
army and for births.

## Town food
- A grown citizen eats 2 food a turn, a child 4 (children are an investment).
- A farm adds 20 food to its hex; a hydroponic plot (Vertical Farming, desert and tundra) adds 30.
  Food buildings scale with it (about x5). Bare hexes still yield nothing to citizens.
- Spare food goes into the town's store. A birth costs 20 food, plus 5 for each citizen past the
  first.
- The store is capped (the granary): 60, or 180 with a Granary (the `food_depot` building).
  Food past the cap is lost.
- Births can be paused per town ("Allow births" off), to bank food for the army.
- Children grow up in about 6 turns in a well-fed town, about 13 with no spare food.
- When the store runs out, soldiers go hungry first (see below), then the youngest citizen dies
  (children before adults).

## The army's food
- Every unit carries rations, up to 10.
- Inside your land (within the work radius of one of your towns) a unit eats 2 food a turn from
  the nearest town's spare food and store, and its rations refill. A town feeds its army only
  from what is left after its citizens have eaten.
- Outside your land, or when its town cannot feed it, a unit eats 1 ration a turn.
- With no rations left, it loses 10 HP a turn, and can starve to death.
- The homeless band starts with full rations and has no land: it lives on rations until it takes
  a town.
- Food crates (a new cache kind) refill the rations of every unit of the finder within 3 hexes.
- A freed town has some food in its store (what the aliens kept), 30.

## Freed towns
- The band's first town keeps 3 rescued people (after the battle), and every survivor without
  gear moves in: up to 7 citizens, plus the leader, who leads from the town.
- Every freed town has a damaged farm on its best farmland, and the band's town also has a broken
  radio tower. Each repair is 8 labour (one engineer-turn), free of materials, and goes to the top
  of the town's works, so a town with 2 engineers repairs both on the first turn.

## The AI
- Trains soldiers only while the town can feed them (spare food after its army of at least 2).
- Builds a Granary once the town nears the store cap.
- Brings units home before their rations run out.

## The client
- The city panel shows the food line, for example "+6 food (citizens -10, children -8,
  army -4)", the store against the birth cost and the cap, and the "Allow births" switch.
- Units show their rations; a warning when they are low outside your land; events when a unit
  starves or a food crate is found.
