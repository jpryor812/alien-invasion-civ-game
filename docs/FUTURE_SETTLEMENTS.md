# Future: eras, materials, a settlement builder and battle scenes (designer, 2026-11-16)

Status: a note for later, not a spec. Not core yet and a lot of work; recorded so it shapes the
choices made before then. The vibe the designer wants: Civ meets Fallout - starting over after
an invasion, scavenging, rebuilding by hand.

## 1. Eras (designer)
1. **Liberation** - the survivor band finds gear and takes back its first town (built, M14).
2. **Rebuild** - refound and rebuild that city: radio, materials, walls.
3. **Retribution** - take back the other cities, once the first is retaken.
4. **Elimination** (working name) - destroy the mothership (the barrage, M7).

Cheapest first step: name the eras on screen (a banner when one begins, the era in the top bar)
over what exists; each later system can then belong to an era.

## 2. Materials instead of production points (designer)
- Each worked resource tile adds to a **material bank**: timber, stone, iron/steel, leather,
  later alien alloys. Buildings cost materials, not production points over turns.
- Open questions: does production remain for units, or do units cost materials too? Are banks
  per city or per player (convoys could move them)? How do materials appear on tiles without a
  resource (terrain: forest timber, hills stone)?
- Keep the simulation rules: integers, seeded, data in YAML, deterministic.

## 3. Walls and buildings made of something (designer)
- Walls are built, not bought: wooden palisades first, then stone, then iron or alien alloy as
  they are discovered; upgrading hardens existing walls.
- City strength is the sum of what was built and what it was built from (each building adds,
  the material sets how much). This answers the pressure audit: every building protects.

## 4. A custom builder view (designer)
- Building switches from the tabletop map to a close view of the city where the player places
  pieces (walls, towers, houses), as in Fallout 4's settlement mode (reference screenshots in
  the conversation; not stored in the repo).
- Suggested scope (Claude): a snapping grid builder in a 3D view of one city (three.js in the
  browser, reusing the Meshy/Poly Haven assets and the Blender pipeline), not a first-person
  free-build: far less work, and the placed pieces map cleanly to simulation data (piece type,
  material, position) that the rules can score.
- Avoid copying Fallout's look (its green terminal UI is distinctive): our own art direction.

## 5. Battle scenes (designer)
- When a city is attacked, show a short scene of it defending itself, as Millennia's auto-battle
  view does (reference screenshot), but more compelling.
- Designer's idea: AI video models. Notes (Claude):
  - The simulation decides the outcome (deterministic, no network); a scene only shows it.
  - Generated video per battle is slow and costly, and hard to keep consistent with the city the
    player built. Two ways to get most of the effect:
    - a real-time 3D replay in the builder view, driven by the combat log (the actual walls and
      units, always consistent, free to run);
    - pre-generated AI video clips for set pieces (first liberation, the mothership's fall,
      a city falling), cached and reused, generated outside the game.
  - Video models fit cut-scenes better than every battle.

## Order, when the time comes
1. Era banners (cheap). 2. Materials and walls in the rules (the core change; needs balance
batches). 3. The builder view. 4. Battle replays, then AI video set pieces.
