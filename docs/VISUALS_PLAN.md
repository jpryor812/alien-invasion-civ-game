# Visuals plan (designer, 2026-11-14)

Goal: make the web client look like Civ V: painted terrain, real tile improvements, cities,
units, council portraits and an ornate interface. Reference: the Civ V screenshots the designer
shared in the session (layout and feel only; nothing copied). Stay on the localhost web client.

Rules for every slice:
- Build it, check it in the browser (preview "beacon-web-test", port 8766) at several zooms and
  in a real game, compare with the references, fix what looks wrong, then commit locally (never
  push). Tick the box and add one line of notes.
- Keep the simulation untouched; `uv run pytest -q` and ruff must stay green.
- Art must have a clear licence: hand-made in this repo, Meshy output under the designer's plan
  (key in .env as MESHY_API_KEY, never committed), or Blender renders made here. No ripped game
  art, no copyrighted fonts.
- Keep the frame rate smooth on a laptop (the map is about 27,000 hexes): cache sprites, draw
  only what is on screen.
- Check in with the designer only after both passes.

## Pass 1

- [x] 0. Renderer: move map drawing to WebGL (PixiJS from a pinned CDN version) or an
      optimised canvas layer cache, keeping today's look and every overlay (fog, highlights,
      shards, finds, city tiles, combat targets).
- [x] 1. Terrain: painted textures per terrain (grassland, plains, desert, tundra, snow, coast,
      ocean), soft blending between neighbouring hexes, sandy coasts and foam, forests and jungle
      as clustered trees, hills as shaded mounds, mountains as peaks with snow, marsh.
- [x] 2. Tile improvements and roads: farms (field rows), mines, extractors, solar, wind,
      hydroponics, military bases, turrets; roads and railways that join neighbours smoothly.
- [x] 3. Cities in 3-4 sizes by population (towers, walls for defence buildings), capitals
      marked; alien hives with organic spires; Civ-style banners.
- [x] 4. Units: Meshy models (human units by class; alien forms), rendered in Blender from the
      map camera angle into sprites; team colour; fall back to drawn sprites if Blender or Meshy
      is unavailable.
- [ ] 5. Council portraits: a portrait for each citizen and recruit (generated busts or drawn
      faces), shown on the council board, population page and event cards.
- [ ] 6. Interface skin: ornate frames, panel headers, buttons, top bar and action button in a
      Civ V-like style (bronze and teal), consistent across every screen.

## Pass 2 (improve each, in the same order)

- [ ] 1. Terrain
- [ ] 2. Tile improvements and roads
- [ ] 3. Cities and alien hives
- [ ] 4. Units
- [ ] 5. Council portraits
- [ ] 6. Interface skin

## Notes

(one line per finished slice: what changed, what is still weak)
- 0 Renderer: canvas kept (no new dependency); ground (terrain, coasts) drawn into cached 16x16-hex chunks at 8 zoom steps, rebuilt only when a tile changes; only on-screen hexes are visited. Frame 3-34 ms at 1400x860. Still weak: the cloud fog is the costliest pass at far zoom.
- 1 Terrain: seamless painted textures per terrain laid as one continuous surface in blurred masks (soft blends, no per-hex seams), beaches and a soft surf halo, faint land grid; sprites for forests (conifer/broadleaf, snowy in the cold), jungle, hills, snow-capped mountain ranges, marsh. Dev flag `web.server --reveal` shows the whole map for art checks. Still weak: coastlines keep a hex-stepped outline; forests are dense everywhere.
- 2 Improvements: painted, cached sprites per zoom step - farms as hex fields of crop strips with a farmhouse, hydroponic domes, mine shaft with timbers, rails, cart and spoil heaps, oil derrick, solar arrays, wind turbines, sandbagged base with flag, minefield posts, beacon and sensor masts; worked tiles show a small citizen figure. Roads curve from hex centres to shared edges with hubs; railways have ties and twin rails. Still weak: mines and bases are small at mid zoom; turrets keep the old icon.
- 3 Cities: cached painted sprites in four modern tiers by population (village houses, mid-rise town, towers, skyscraper metropolis) on soft paving with streets; capitals get a domed capitol and a flag in the owner's colour; concrete ring for a defence perimeter, glass dome for a plasma shield; dormant cities greyed, empty ones as rubble; alien hives as dark ground with glowing veins, leaning red spires and egg pods. Civ-style banners: bevelled plate with owner-coloured caps (population left, production turns right), gold rim on your own cities, capital star, health bar. Garrisons stand at the city's front edge. `--reveal` now also shows every city and unit. Still weak: cities are hex-sized discs rather than spreading into neighbouring hexes; hives have no animation.
- 4 Units: 13 Meshy models (390 credits; 439 left) rendered in Blender from the map angle into 256px PNGs (web/static/units, provenance in its README): infantry, engineer, tank, hover tank, howitzer, walker, drone, destroyer, and five alien forms (small insectoid, blade-armed warrior, spitter, brute, tentacled titan). Every unit type maps to the nearest model; infantry and small aliens stand as squads of three; drones hover; figures stand on a thin team-coloured base, with a small flag badge (type code, health, promotions) at their shoulder; garrisons stand at the city's edge; far zoom keeps the badge. Still weak: ships share one model; no facing or animation; the walker render is dark.
