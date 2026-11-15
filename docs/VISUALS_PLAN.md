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
- [x] 5. Council portraits: a portrait for each citizen and recruit (generated busts or drawn
      faces), shown on the council board, population page and event cards.
- [x] 6. Interface skin: ornate frames, panel headers, buttons, top bar and action button in a
      Civ V-like style (bronze and teal), consistent across every screen.

## Pass 2 (improve each, in the same order)

- [x] 1. Terrain
- [x] 2. Tile improvements and roads
- [x] 3. Cities and alien hives
- [x] 4. Units
- [x] 5. Council portraits
- [x] 6. Interface skin

## Notes

(one line per finished slice: what changed, what is still weak)
- 0 Renderer: canvas kept (no new dependency); ground (terrain, coasts) drawn into cached 16x16-hex chunks at 8 zoom steps, rebuilt only when a tile changes; only on-screen hexes are visited. Frame 3-34 ms at 1400x860. Still weak: the cloud fog is the costliest pass at far zoom.
- 1 Terrain: seamless painted textures per terrain laid as one continuous surface in blurred masks (soft blends, no per-hex seams), beaches and a soft surf halo, faint land grid; sprites for forests (conifer/broadleaf, snowy in the cold), jungle, hills, snow-capped mountain ranges, marsh. Dev flag `web.server --reveal` shows the whole map for art checks. Still weak: coastlines keep a hex-stepped outline; forests are dense everywhere.
- 2 Improvements: painted, cached sprites per zoom step - farms as hex fields of crop strips with a farmhouse, hydroponic domes, mine shaft with timbers, rails, cart and spoil heaps, oil derrick, solar arrays, wind turbines, sandbagged base with flag, minefield posts, beacon and sensor masts; worked tiles show a small citizen figure. Roads curve from hex centres to shared edges with hubs; railways have ties and twin rails. Still weak: mines and bases are small at mid zoom; turrets keep the old icon.
- 3 Cities: cached painted sprites in four modern tiers by population (village houses, mid-rise town, towers, skyscraper metropolis) on soft paving with streets; capitals get a domed capitol and a flag in the owner's colour; concrete ring for a defence perimeter, glass dome for a plasma shield; dormant cities greyed, empty ones as rubble; alien hives as dark ground with glowing veins, leaning red spires and egg pods. Civ-style banners: bevelled plate with owner-coloured caps (population left, production turns right), gold rim on your own cities, capital star, health bar. Garrisons stand at the city's front edge. `--reveal` now also shows every city and unit. Still weak: cities are hex-sized discs rather than spreading into neighbouring hexes; hives have no animation.
- 4 Units: 13 Meshy models (390 credits; 439 left) rendered in Blender from the map angle into 256px PNGs (web/static/units, provenance in its README): infantry, engineer, tank, hover tank, howitzer, walker, drone, destroyer, and five alien forms (small insectoid, blade-armed warrior, spitter, brute, tentacled titan). Every unit type maps to the nearest model; infantry and small aliens stand as squads of three; drones hover; figures stand on a thin team-coloured base, with a small flag badge (type code, health, promotions) at their shoulder; garrisons stand at the city's edge; far zoom keeps the badge. Still weak: ships share one model; no facing or animation; the walker render is dark.
- 5 Portraits: a seeded painter draws a bust for every citizen and recruit from its id, cached as an image (no credits, no assets). Fictional humans vary in skin, hair (short, swept, long, curls, buzz, bun), eyes, brows, beards, glasses, scarves and clothes, and children are drawn smaller. Alien recruits have elongated crania, two or four glowing eyes, crests or frills, mandibles and robes, and a halo when legendary. Shown in bronze rings on the council board and Population screen, and as faces on the Survivors and Outcast event cards. Still weak: a cartoon style next to the 3D units; no age or expression variety; the other event pictures are still placeholders.
- 6 Skin: one CSS layer over every screen. Panels, modals, tooltips, the title menu and advisor cards are deep teal with a woven texture, a double bronze frame and bracketed corners. Headings use Cinzel (SIL Open Font Licence, Google Fonts) between tapering bronze rules. Buttons are bevelled teal plates in bronze, primary buttons gold. The top bar is bronze-edged with a jewel at its centre. The action button is a ringed medallion that glows while waiting. The minimap frame is bronze, cards and seats share the frame colours, and scrollbars are bronze. Still weak: the yield and top-bar icons are plain glyphs; the tech-tree level heads and some small labels keep the monospace font; no painted textures in the frames.
- P2.1 Terrain: coastlines are now organic. Land hexes are blurred into a field (half a wide blur, half a narrow one so one-hex islands survive), wobbled by world-aligned value noise and cut at three levels: land, a beach band inside it and a surf band outside it. The field is built at quarter resolution and scaled up. Hexes next to unexplored ones count as land. Water is a deep-ocean base with one widely blurred shallows layer, so the depth line no longer steps. Forests grow in 2-4 clumps with clearings and a darker forest floor, in six variants per hex (7-14 trees). Every layer fills its hexes in one path, so blur runs once: a full screen of new chunks builds in about 0.2-0.45 s (was 0.15-1.4 s). Still weak: the boundaries between land types are still soft hexes.
- P2.2 Improvements: mines are now a pithead filling the hex: spoil heaps, a timber headframe with its winding wheel, a shed, a shaft mouth, rails with sleepers and a loaded ore cart. Military bases are a sandbagged compound with a gate, two barracks, a watchtower, an armoured car and a flag. Turrets are a painted, cached emplacement: an octagonal concrete pad and an armoured gun house with one barrel per level and gold level pips (plus a health bar when the view sends max health). Still weak: extractors, beacons and masts are thin line art; roads have no bridges over rivers or coasts.
- P2.3 Cities: towns and cities spill suburbs onto open neighbouring land (1, 3 or 5 hexes by tier, picked by a hash so they stay put). Suburbs are cached sprites of paving, houses, mid-rises and trees, drawn pulled toward the city so they join it. A hive spreads red creep onto 1-4 neighbours, with veins, small spires and pods. Hives now breathe: a slow pulsing glow from the heart and spores drifting up, drawn each frame (cheap: one gradient and a few dots). Still weak: suburbs ignore roads; city edges are still soft ellipses.
- P2.4 Units: two more Meshy models (60 credits; 379 left). The scout boat is now a patrol boat and the attack submarine a surfaced submarine; destroyers and railgun cruisers keep the destroyer. The walker was re-rendered with more exposure, so it reads on dark ground. Idle motion: drones bob, hover tanks float, ships rock on the swell (a per-unit phase, no state). Still weak: no facing toward the move direction; land vehicles share the tank model; no attack animation.
- P2.5 Portraits: citizens now have an age (young, grown, older with forehead lines, crow's feet and greying hair) and a mood (calm, warm with dimples, stern brows, wry half-smile). Hair strands catch the light, a cool rim light sits on the shadow side, and a brush-stroke overlay gives a painted finish. Event and Starfall pictures are now painted scenes instead of glyphs: a ruined school with a smoking chimney, the outcast in a ringed crater (the alien warrior render), split ship wreckage with glowing seams, a lamplit cache under a fallen overpass, a cut-open bunker with an engineer, cracks with red eyes and the brood climbing out (alien renders), and burning crystal shards in their crater, coloured by kind. The aliens' wormhole is in every sky. Still weak: portraits remain stylised busts; scenes are silhouettes rather than full illustrations.
- P2.6 Skin: a bronze medallion icon set (turn, gold, science, beacon, food, production, mothership; shared gradients defined once) in the top bar, the city panel's yield boxes and the Cities table. One heading face: Cinzel now also sets the tech-tree level heads, seat heads, list groups, table heads and the turn splash. Every pop-up has a gilded header band behind its title, and panel titles have a bronze rule. Still weak: the unit panel's action buttons are text only; there is no sound.
