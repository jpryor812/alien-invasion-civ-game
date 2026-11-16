# M16 — Materials and the city builder in the main game (designer, 2026-11-16)

Approved by the designer, with these answers:
- Economy: tiles yield goods into each city's stores; buildings and walls cost materials plus
  labour (production) and are placed in the builder. Units keep production, but military units
  need a **barracks**, and industrial units (artillery, armour, ships) also cost materials.
  AI cities use all of it.
- Placement: a fine grid (about 8 cells across a hex), free-feeling like Clash of Clans.
- Art: Meshy for 8 hero buildings; improved Blender models for the rest and for wall pieces;
  Poly Haven ground.
- Defence: what a city has built decides how it fares; the old bought defence buildings
  (perimeter, plasma shield, chitin bulwark) become wall materials in the builder.
- Later (designer): citizens crafting weapons to defend themselves (Fallout Shelter style);
  a Clash-style separate mode fed by blueprints and rewards from the main game.

## 1. Materials
- Three stored goods per city: **timber, stone, iron** (food stays the main game's food).
- Worked tiles (and the city's own tile) yield them: forest and jungle timber, hills stone,
  mines stone and iron, extractors on timber resources timber. Data in data/materials.yaml.
- Each city stores up to a cap per good; a warehouse-type building raises it (the food depot
  for now raises nothing; a new **storehouse** building does).
- Shown on the city screen and the builder: stores, caps and per-turn income.

## 2. What things cost
- Every building has a materials cost (data, with a default rule by production cost and tech
  tier); paid when it completes. If the stores are short, it waits ("needs 12 stone").
- Industrial units (classes armour, artillery, naval) cost iron (and timber for ships) on
  completion the same way.
- Military units (melee and ranged land and sea units, not recon or city defences) need a
  barracks (the military base) in the city.

## 3. The city layout (fine grid)
- A city's builder area is its territory: the hexes of its work area that it holds, drawn as
  one fluid shape with only its outer border. A fine grid of cells (8 across a hex) covers it.
- Every building has a footprint in cells (city hall 4x4, most 2x2 or 3x3). Buildings may not
  overlap, and keep a gap of at least one cell from other buildings (a wall or path may run
  there). Everything must lie inside the territory.
- Placing a building orders it (it joins the queue with its position); a building ordered from
  the queue without a place is placed automatically when it completes. Placed buildings can be
  moved for free.
- **Walls** are laid cell by cell (drag), in a material: wood (from the start), stone (from the
  start, costs stone), steel (Mechanized Warfare), plasma (Directed Energy), chitin (Organic
  Armour). Each piece costs materials and a little production (a "walls" queue item) and adds
  strength and HP to the city.

## 4. Defence
- City strength gains a line per wall material (pieces x strength) and city HP gains the
  pieces' HP. Every building already adds HP or strength where its data says so.
- Defence perimeter, plasma shield and chitin bulwark are removed as buildings; existing data
  for walls moves to the wall materials.

## 5. AI
- AI cities build a barracks before military units, keep materials flowing (they work the
  tiles as before), place buildings automatically, and lay a wall ring once they have the
  stone, upgrading the material as techs allow.

## 6. The builder view (client)
- A **City builder** button on the city panel switches the map to the builder: a close,
  tilted camera on the city's territory; the ground textured by terrain without hex lines;
  only the territory's border drawn; buildings standing where they were placed.
- Build menu: choose a building, a blue ghost follows the cursor (red where it cannot go),
  click to place. Wall tool: choose a material and drag to lay pieces. Select a building to
  move it. Stores, caps and costs shown; a button returns to the map.

## 7. Art
- Meshy (about 8 models, "low-poly stylised game building" prompts): city hall, library,
  market, workshop, barracks, factory, radio tower, granary. The rest from the improved
  Blender kit; wall pieces per material from the kit. All rendered at the builder's camera.

## Acceptance
- Tests: materials income and caps, building and unit material costs, barracks rule, placement
  validity (territory, overlap, gap), auto-placement, moving, walls (cost, strength, HP), AI
  layouts and walls, save round-trips.
- pytest and ruff pass; the 10-seed batch still finishes; the builder checked in the browser.
