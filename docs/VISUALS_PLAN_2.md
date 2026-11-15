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
- [x] 2. Forests, jungle, hills and mountains rendered in Blender from Poly Haven models and
      textures: dense canopy hex sprites (several variants, some autumn), jungle canopy, rolling
      textured hills, big rocky snow-capped mountains.
- [x] 3. Territory borders in each owner's colour with an inner glow, and farms as patchwork
      fields with farmhouses; other improvements kept consistent with the new ground.
- [x] 4. Cities rendered in Blender: clusters of textured houses and towers (built from simple
      parts with Poly Haven textures) in four tiers, spreading over neighbours; alien hives to
      match; Civ-style banners (capital crown, name, population, defence shield).
- [x] 5. Units: larger formations (infantry 6-9 figures, guns 2-3, vehicles 2-3), Civ-style unit
      flags (owner-coloured shield or disc with a white class icon), a glowing ground ring for
      the selected unit.
- [x] 6. Interface layout: the unit panel at the bottom left with a big round portrait (the unit
      render) and stats; minimap and action button at the bottom right in one frame; a thin dark
      top bar; a combat preview panel styled like the references.

## Pass 2 (improve each, in the same order)

- [x] 1. Terrain textures
- [x] 2. Forests, hills, mountains
- [x] 3. Borders and farms
- [x] 4. Cities
- [ ] 5. Units
- [ ] 6. Interface layout

## Notes

(one line per finished slice: what changed, what is still weak)
- 1 Terrain: six CC0 Poly Haven aerial textures (web/static/terrain, sources in its README) replace the painted ground. Grassland and plains share the drone-shot grass, graded green or gold; desert uses rippled beach sand, beaches flat sand, tundra mossy rocky ground, snow the aerial snow field. Each is graded in code, softened with the old painted tones, and laid world-aligned with one tile per about three hexes. The painted textures stand in until the photos load, then the ground rebuilds. A thin light hex grid now covers land and water as in the references, and water is more teal. Still weak: grassland is fairly uniform (Civ's has more patchwork tone); the first build of a screen takes about 1.6 s while the textures are made.
- 2 Features: rendered in Blender from CC0 Poly Haven assets (web/static/features, sources in its README). The camera sits 55 degrees up and each scene is stretched so it projects onto the hex. Forests are 80-92 copies of tree_small_02 over a darkened forest floor (4 variants), tinted per hex: lush green, warmer, autumn, or dark blue-green in the cold. Jungle is denser and deep green (2 variants). Hills are rendered relief in plain grey (3 variants), re-centred on mid-grey and laid in overlay blend, so they shade any terrain without changing its colour. Mountains are 5-7 boulder_01 copies stretched into peaks with snow above a height line (3 variants), drawn about 1.2 hexes wide so neighbouring peaks join into ranges. The Poly Haven firs rendered brown and sparse, so they are not used. Still weak: forests read as soft dark masses at mid zoom (Civ's canopies have brighter crowns); mountains are all the same rock colour on every terrain.
- 3 Borders and farms: territory borders are drawn each frame from each tile's city, client-side only. A three-layer line (dark under-stroke, the owner's colour, a pale inner edge) runs along every edge where ownership changes, inset slightly so two neighbours' borders sit side by side, with an inner glow fading toward the hex centre. Cities of the same owner share one border; alien land is red. Farms are now a patchwork of rectangular fields in greens, golds and ploughed browns, with crop rows, hedgerows and a farmstead (house, barn, trees), in six variants at different angles. Still weak: borders follow hex edges straight (Civ smooths them); fields stop at the hex edge rather than flowing into the next farm.
- 4 Cities: towns are generated and rendered in Blender (web/static/cities, sources in its README) from house, mid-rise and tower blocks in street blocks inside the hex. They use Poly Haven CC0 terracotta roofs, plaster walls with procedural window rows, a concrete facade and asphalt paving. Four tiers by population (village with no paving, town, city with a few towers, metropolis with a tower core), two variants each, plus three paving-free suburb renders for the neighbouring hexes. The client draws them warmed and with more contrast, and paints the walls, capitol dome and flag, and plasma shield over them; dormant cities are greyed. Banners now show a gold crown for the capital and a Civ-style defence shield with the city's strength. The view sends the strength for every known city, the only server change (`web/session.py`). Alien hives keep the painted art. Still weak: the renders are small and muted next to Civ's warm, dense towns; towers are plain boxes.
- 5 Units: formations as in Civ, figures in staggered ranks: infantry 8, tanks, guns and hover tanks 3, walkers 2, drones 4, small aliens 6, warriors 5, spitters 3, brutes 2. Figures are smaller and the base ellipse fits the formation. The flag above each unit is now Civ's style: a disc in the owner's colour (red for aliens) with a dark rim, a pale inner ring and a white class icon, plus the type code, health and promotions as before. The selected unit stands in a pulsing gold ring on the ground, and the old hex outline pulse is kept. Still weak: flags are discs only (Civ varies the shape); no unit facing; formations do not thin out as units take damage.
- 6 Layout: Civ's corners. The unit panel now sits at the bottom left with the unit's render in a big round bronze frame (ringed in the owner's colour) breaking out of the panel; city and turret panels keep the top left. The action button and minimap share one bronze-cornered frame at the bottom right, button above. The top bar is thinner (34 px) and darker. The combat preview (already Civ's structure: outcome banner, strengths with modifiers, HP bars) gets a gilded Cinzel banner and framed sides. Still weak: the action buttons in the unit panel are text, not round icons as in Civ; no left-hand icon strip.
- P2.1 Terrain: a patchwork layer. Each land hex leans toward one of several shades for its terrain (grassland greens and golds, plains ochres, desert sands, tundra greys), filled per hex, blurred so neighbours blend, and laid in soft-light at 60%. Wide grasslands now read as a quilt, as in the references, without hiding the photo detail. The first build of a screen is about 1.35 s, cached after. Still weak: tones change by whole hexes; Civ also shows field-like streaks inside a hex.
- P2.2 Features: forests and jungles were re-rendered with a stronger, higher sun, a rim light and a lighter forest floor, so crowns catch the light and the hexes read as canopy rather than dark patches; the client tints were rebalanced to match. Mountains now sit on a soft shadow where they meet the ground and are graded to their land: warm sandstone in the desert, cold grey in tundra, pale in snow. Still weak: forests still fill whole hexes edge to edge (Civ's thin out at the borders); all mountains share one boulder model.
- P2.3 Borders and farms: border edges are now joined into chains per owner. Each corner is inset toward the owner's hexes that touch it, and two passes of corner cutting round the steps, so borders curve around territories as in Civ (about 34 ms for a whole frame with borders). Farm patchworks reach slightly past their hex, so neighbouring farms join into one field. Still weak: the inner glow still follows straight hex edges under the curved line.
- P2.4 Cities: all eleven renders were redone. Towns fill the whole hex with smaller, denser plots; villages and towns have trees between the houses; some mid-rises have pitched roofs; towers are stepped (base, shaft, crown) with rooftop masts; a warmer, stronger sun. Suburbs are denser too. Still weak: alien hives keep the painted art; every city of a tier looks alike apart from two layouts.
