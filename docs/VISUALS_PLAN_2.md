# Visuals plan, round 2 (designer, 2026-11-15)

Round 1 (docs/VISUALS_PLAN.md) drew almost everything in code. Round 2 moves to real art: CC0
textures and models from Poly Haven (now switched on in the Blender add-on), rendered in Blender
from the map camera, as the units already are. The target is the five Civ V screenshots the
designer shared on 2026-11-15. They are references for layout and feel only: nothing is copied,
and the images are never committed.

## What the references show (and where we fall short)

- Terrain: photographic, painted textures with fine detail; saturated yellow-greens and ochres. A
  thin, light hex grid shows on land and on water alike. Ours: soft procedural blobs, and the grid
  is on land only and nearly invisible.
- Forests: dense canopy seen from above, filling the hex edge to edge as one mass, with autumn
  tints in places. Ours: separate cartoon trees in clumps.
- Mountains and hills: big rocky masses with snow and shadow; hills as rolling, textured ground.
  Ours: small drawn peaks and mounds.
- Farms: a patchwork of rectangular fields in several greens and golds, spreading across hexes,
  with small farmhouses. Ours: one hex of strips.
- Borders: every civ's territory has a thick border in its colour with a soft glow inside. Ours:
  none (tiles do record their city, so this needs no simulation change).
- Cities: dense clusters of many small textured houses with roofs, spreading over the city hex and
  its neighbours; a banner with a crown for the capital, the name, the population and a defence
  shield. Ours: drawn boxes on a paved disc.
- Units: each unit is a formation of many figures (8-12 soldiers, 3-4 cannons); above it, a round
  or shield-shaped flag in the owner's colour with a white class icon. Selection is a glowing ring
  on the ground. Ours: 3 figures and a small badge.
- Interface: thin dark top bar with icons; teal panels with gold trim; a unit panel at the bottom
  left with a big round portrait and its stats; the minimap at the bottom right in a frame, with
  the action button above it; a combat preview panel. Diplomacy is a leader standing in a 3D
  scene with trade panels. Ours: close in colour, different in layout.
- Water: deep teal with glints, pale shallows, white surf along the shore, hex grid visible.

Not in scope: rivers (the simulation has none, and decorative rivers would mislead), leader
scenes for diplomacy (leaders come later, SPEC_M9 steps 4-6).

## Rules (as round 1)

- Build each slice, check it in the browser (preview "beacon-web-test", port 8766, reveal save
  "visual-test") at several zooms against the references, fix what looks wrong, commit locally
  (never push), tick it off with one line of notes.
- Simulation untouched; pytest and ruff stay green.
- Art: Poly Haven assets are CC0. Meshy output on the designer's account (379 credits left, so
  use them sparingly). Blender renders made here. Record every asset's source in a README next
  to it. No ripped game art, no copyrighted fonts.
- Keep the frame rate smooth: cache, draw only what is on screen, keep chunk builds fast.
- Check in with the designer only after both passes.

## Pass 1

- [x] 1. Terrain textures: Poly Haven CC0 ground textures (grass, dry grass, sand, rock, snow,
      tundra-like soil) prepared as seamless web textures per terrain; a more saturated palette;
      a thin light hex grid over land and water as in the references; water with depth, glints
      and the surf kept.
- [ ] 2. Forests, jungle, hills and mountains rendered in Blender from Poly Haven models and
      textures: dense canopy hex sprites (several variants, some autumn), jungle canopy, rolling
      textured hills, big rocky snow-capped mountains.
- [ ] 3. Territory borders in each owner's colour with an inner glow, and farms as patchwork
      fields with farmhouses; other improvements kept consistent with the new ground.
- [ ] 4. Cities rendered in Blender: clusters of textured houses and towers (built from simple
      parts with Poly Haven textures) in four tiers, spreading over neighbours; alien hives to
      match; Civ-style banners (capital crown, name, population, defence shield).
- [ ] 5. Units: larger formations (infantry 6-9 figures, guns 2-3, vehicles 2-3), Civ-style unit
      flags (owner-coloured shield or disc with a white class icon), a glowing ground ring for
      the selected unit.
- [ ] 6. Interface layout: the unit panel at the bottom left with a big round portrait (the unit
      render) and stats; minimap and action button at the bottom right in one frame; a thin dark
      top bar; a combat preview panel styled like the references.

## Pass 2 (improve each, in the same order)

- [ ] 1. Terrain textures
- [ ] 2. Forests, hills, mountains
- [ ] 3. Borders and farms
- [ ] 4. Cities
- [ ] 5. Units
- [ ] 6. Interface layout

## Notes

(one line per finished slice: what changed, what is still weak)
- 1 Terrain: six CC0 Poly Haven aerial textures (web/static/terrain, sources in its README) replace the painted ground. Grassland and plains share the drone-shot grass, graded green or gold; desert uses rippled beach sand, beaches flat sand, tundra mossy rocky ground, snow the aerial snow field. Each is graded in code, softened with the old painted tones, and laid world-aligned with one tile per about three hexes. The painted textures stand in until the photos load, then the ground rebuilds. A thin light hex grid now covers land and water as in the references, and water is more teal. Still weak: grassland is fairly uniform (Civ's has more patchwork tone); the first build of a screen takes about 1.6 s while the textures are made.
