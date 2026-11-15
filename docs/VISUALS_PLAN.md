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

- [ ] 0. Renderer: move map drawing to WebGL (PixiJS from a pinned CDN version) or an
      optimised canvas layer cache, keeping today's look and every overlay (fog, highlights,
      shards, finds, city tiles, combat targets).
- [ ] 1. Terrain: painted textures per terrain (grassland, plains, desert, tundra, snow, coast,
      ocean), soft blending between neighbouring hexes, sandy coasts and foam, forests and jungle
      as clustered trees, hills as shaded mounds, mountains as peaks with snow, marsh.
- [ ] 2. Tile improvements and roads: farms (field rows), mines, extractors, solar, wind,
      hydroponics, military bases, turrets; roads and railways that join neighbours smoothly.
- [ ] 3. Cities in 3-4 sizes by population (towers, walls for defence buildings), capitals
      marked; alien hives with organic spires; Civ-style banners.
- [ ] 4. Units: Meshy models (human units by class; alien forms), rendered in Blender from the
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
