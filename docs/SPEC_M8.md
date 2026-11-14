# Spec: milestone M8, the web client (first playable)

Status: approved to build (2026-11-13, "go ahead to M8"), with the defaults below. The designer
reviews after M8, playing it.

## Goal

A human plays one continent against five AI continents in the browser, with the Civ V-style
layout from the designer's reference screenshots, used for layout only (DESIGN.md 16; no Civ art,
icons or names). The simulation stays the single source of truth: the client only shows the fog-safe
view and sends the same commands the AI sends.

## Defaults (for review)

1. **Stack**: no build step and no new dependencies. A small Python HTTP server (`web/server.py`,
   standard library only) serves a JSON API and static files; the client is plain HTML, CSS and
   JavaScript (`web/static/`) drawing the map on a canvas. Easy to run anywhere, easy to replace
   later with a richer front end.
2. **Look**: original flat vector art. Pointy-top hexes in terrain colours with simple shapes for
   hills, mountains, forest, jungle and marsh; cities as walled discs with a name banner (population,
   HP bar, production); units as round badges in the owner's colour with a short type code and a
   health bar; aliens in a sickly violet. Dark slate panels with brass accents. No external fonts or
   images.
3. **Fog** (designer rules): visible hexes in full colour; explored hexes shown as dim fog with
   their outline only (terrain is hidden again); unexplored hexes as dark cloud. Discovered cities
   stay drawn with live status.
4. **One game per server**, in memory, with save and load to `runs/saves/`. Single player: one
   human seat (default Europe), five AIs. Multiplayer with a turn timer comes later.

## Screens

- **Map**: pan (drag), zoom (wheel), click to select, minimap (click to jump).
- **Top bar**: turn and year, gold and its change per turn, science per turn and current research
  with turns left, beacon points, rarity level, alliances, MVP rank. Buttons for the screens below.
- **Unit panel**: type, strength, moves, HP, stack size; actions (fortify, skip, build improvement,
  refound, split, merge, ship abroad); reachable hexes highlighted; hovering an enemy in reach shows
  the combat preview (both sides' strength lines and expected damage), clicking attacks.
- **City panel**: population and growth, every yield with its breakdown, buildings, production
  queue with costs and turns, change production, buy, focus, bombard.
- **Next turn**: shows the first pending decision ("unit needs orders", "choose production", ...)
  and jumps to it; Enter ends the turn once nothing is pending (or with a confirm).
- **Tech tree**: five trees in columns by tier, with prerequisites, costs, what each unlocks, and
  status (known, available, researching, locked); click to research.
- **Council**: recruits with scores, traits, lifespan; seats per council; seat and unseat; offer to
  another player.
- **Diplomacy**: the other continents (character, cities, fallen, allied); incoming deals and offers
  to accept or decline; propose gold aid, alliance, a tech gift.
- **Projects**: barrage status and contributions, start and fund it; espionage operations, start,
  fund, choose the alien tech.
- **Scores**: MVP ranking with each player's lines; the outcome when the game ends.
- **Event log**: this turn's events for the player.

## Outcome (2026-11-13)

Built and play-tested in the browser: map with fog, unit selection and movement, combat
preview, city panel and production, tech tree and research, diplomacy and projects screens, end
turn with AI players, save and load. 9 API tests; 128 tests pass in all.

## Acceptance criteria

- `uv run python -m web.server` serves the game on `http://127.0.0.1:8765`.
- API tests (pytest): a new game, the fog-safe view (no hidden units or terrain leak), unit
  options, a move, an attack preview, city details, production change, tech list and research,
  end turn with AI players, save and load round trip, and rejection of illegal commands with a
  message.
- Play-tested in the browser: the map draws with fog, units can be selected, moved and made to
  attack, a city's production changed, research chosen, turns advanced; screenshots reviewed.
- Python lint and tests pass.
