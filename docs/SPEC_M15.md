# M15 — The settlement sandbox (designer, 2026-11-16)

> Retired in M17 (docs/SPEC_M17.md): its labour-and-materials loop and the Galactic Exchange were
> merged into the main game and the sandbox code was removed. Kept as a record.

Approved by the designer ("yes let's build this. go ahead and give it a shot"). A playable slice of
the material economy and the zoomed-in city view, separate from the main game, to feel the loop
before converting the whole game (docs/FUTURE_SETTLEMENTS.md). Every number is a tunable in
data/settlement.yaml.

## Goal
One city and its six neighbouring hexes, played turn by turn for about 10 minutes:
harvest goods into banks, feed people, build in hex slots with materials and labour, wall the
perimeter, survive alien raids, trade surplus at the Galactic Exchange.

## Rules
- **Goods** (stockpiled): grain, timber, stone, iron. Each has a storage cap; excess is lost at
  turn end. **Gold** is currency: only from selling, finds and the start.
- **Hexes and slots**: the centre (the city hall plus 5 slots), and six hexes around it, each
  with a terrain and maybe a resource: plains and grassland 3 slots, forest and hills 2.
- **Buildings** (each in a slot): farm (grain hex: grain), lumber camp (forest: timber), quarry
  (hills: stone), iron mine (hills with iron: iron), granary and warehouse (storage), house
  (room for people), workshop (labour). Producing buildings need one worker each.
- **People**: each eats grain every turn; a stored surplus grows the city when houses have room;
  hunger shrinks it.
- **Labour**: every turn the city has labour (a base, plus workshops). Construction costs
  materials (paid when ordered) and labour (spent over turns, in queue order).
- **Walls** stand on the territory's outer hex edges: wood, stone or iron, each with its own
  strength and HP. Every building also adds to the city's strength.
- **Raids** (seeded) come every few turns, seen two turns ahead, at one outer hex: the walls on
  that hex's outer edges plus the city's base and building strength meet the raid. Held: the
  walls take damage. Broken: the raiders wreck a building there and burn part of the stores.
- **The Galactic Exchange**: neutral alien traders who always buy and sell, at a bad spread
  (sell at a fraction of the price, buy at a premium). Prices drift each turn and sag when you
  sell a lot.

## The view (Clash of Clans meets CK3's zoom)
- A tilted, close camera on the territory: hexes as bright ground tiles, buildings standing in
  their slots, walls along the edges, warehouse levels at a glance.
- Click a hex for its slots and what can be built; click an outer edge to build or harden a wall.
- A short raid scene: raiders march in to the struck hex, meet the wall, and the result shows.
- The main game's map stays the zoomed-out view; joining the two is a later step.

## Not in this slice
Several cities, the main map, units, the council, AI. Blueprints and campaign carry-over are
noted for later (designer brainstorm 2026-11-16).

## Acceptance
- Tests: harvest and caps, eating and growth, workers, labour and the queue, walls, raids held
  and broken, the Exchange's spread and drift, determinism and save round-trips.
- pytest and ruff pass; the sandbox page is played in the browser from turn 1 to a raid.
