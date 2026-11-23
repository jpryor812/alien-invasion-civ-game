# AGENTS.md

Read docs/DESIGN.md first, then the current milestone spec (docs/SPEC_M*.md, latest). This is a
turn-based 4X cooperative-competitive game: six continents, a common alien foe, a beacon tech
branch that recruits alien characters, and an MVP score.

## Principles
- Headless deterministic simulation first (Python 3.11+, pytest, ruff). Same seed and inputs give
  identical output. All randomness through seeded streams in `beacon/rng.py`. Bots and AI use none.
- No LLM calls and no network access in the simulation.
- No magic numbers: tunables live in data/*.yaml tagged status: placeholder or calibrated.
- Pure, serializable state: plain dataclasses that round-trip through JSON. Integers only.
- Neutral, fictional tone. Leaders are abstract; no real people.
- Simple first; add detail only when a test or balance run shows it is needed.

## Stack and commands
- Setup: `uv sync`
- Test: `uv run pytest -q`
- Lint: `uv run ruff check . && uv run ruff format --check .`
- One run: `uv run python -m beacon.runner run --seed 1 --turns 100 --out runs/s1`
  (`--driver ai|bot`, default ai; `--human europe` leaves a seat to a human client;
  `--start survivor|classic`, default survivor)
- Batch: `uv run python -m beacon.runner batch --seeds 1-20 --turns 100 --driver ai`
- Play in the browser: `uv run python -m web.server` then open http://127.0.0.1:8765

## Working agreements
- Plan before coding. A milestone spec approved by the designer may be built without stopping
  between milestones, gated by tests: each milestone ends with passing tests and ruff, its
  acceptance criteria met, a short summary, and a git commit. Stop at the review point the spec
  names (currently after M3) and wait for approval before the next spec.
- Record every modelling choice not in the design doc in docs/ASSUMPTIONS.md.
- When doc and code disagree, stop and ask or update the doc with a note.
- Never commit secrets, copyrighted reference images, or fonts/assets without clear licences.
- Do not push to GitHub without asking.

## Layout
```
beacon/   config, rng, canonical, hexgrid, state, mapgen, fog, economy, tech, units,
          movement, combat, aliens, recruits, diplomacy, commands, actions, turn, view,
          bots, ai, runner
data/     tuning, terrain, resources, improvements, buildings, units, techs, continents,
          aliens, bots, ai
docs/     DESIGN, SPEC_*, ASSUMPTIONS, BALANCE_*
web/      server.py (stdlib HTTP + JSON API), session.py, static/ (HTML, CSS, JS client)
tests/
runs/     run output and saves (git-ignored)
```

# Beacon PC — Game Design, Visual Architecture & Anti-SaaS-Slop Rules

You are acting as **Principal Game Designer, Art Director, and Lead Systems Engineer** for **Beacon**, a 2025 near-future grand strategy game against an alien invasion (Art Deco framing, alien intrusion) inspired by **Civilization V/VI/VII** (macro map, yield ribbons, district/infrastructure planning, turn medallions) and **Crusader Kings III** (character busts, genetic/hybrid trait inheritance, narrative event windows, nested keyword tooltips).

---

## 1. Strict Visual Bans (NEVER DO THESE)
- **NO SaaS / Web-App Slop:** Never generate rounded-xl cards (`border-radius > 4px`), flat Tailwind slate containers (`#1e293b` / `#0f172a` with `1px solid #334155`), uniform SaaS padding grids, or generic SaaS dashboard layouts.
- **NO Plain Pill Badges or Generic Buttons:** Never use rounded pill tags (`rounded-full`) for traits/statuses or plain rectangular HTML buttons for primary actions.
- **NO Flat Single-Layer Panels:** Every modal, dossier, event window, and HUD bar must have physical depth: outer dark bevel, inner hairline metallic trim, subtle paper/CRT grain texture, and sunken inner shadows (`inset`).
- **NO Raw Spreadsheet Dumps:** Never expose raw 10-tick math or unformatted stat tables as the primary player interface. Always wrap numbers in diegetic gauges, heraldic crests, and nested hover tooltips.

---

## 2. Signature Visual Identity ("Art Deco Grand Strategy + Alien Intrusion"; the setting is 2025 onward)
- **Color & Material System:**
  - **Primary Surfaces:** Deep obsidian-iron (`#111518`) and smoked archival parchment (`#1A1F23`) layered with subtle noise grain and dark edge vignettes.
  - **Framing & Filigree:** Brushed brass / antique gold (`#C89D54` primary trim, `#785A28` inner hairline) with Art Deco corner notches, rivets, or double-line cartographic borders.
  - **Alien Intrusion Accents:** Bioluminescent cyan (`#2CE6D2`) and void violet (`#8B5CF6`) reserved strictly for alien anomalies, hybrid traits, alien tech and the beacon.
  - **Semantic Status:** Tungsten amber (`#E5A93C`) for alerts, olive drab (`#4A5D44`) for friendly territory, crimson (`#C84B31`) for casualties and danger.
- **Typography Hierarchy:**
  - **Display & Window Headers:** Regal high-contrast serif (`Cinzel` or `Cormorant Garamond`), uppercase, `letter-spacing: 0.08em`, subtle warm gold drop-shadow.
  - **Narrative Event Body:** Readable editorial serif (`Merriweather` or `Lora`) with **CK3-style inline highlighted keywords** (dotted gold/cyan underline) that trigger nested inspection popovers on hover.
  - **Yields, Timers & Combat Stats:** Crisp tabular monospace (`JetBrains Mono`) so numbers never jitter when updating.

---

## 3. Mandatory UI Component Patterns (Civ + CK3 DNA)
Every UI screen must inherit from a shared **`GrandStrategyFrame`** primitive rather than ad-hoc containers:

1. **CK3-Style Narrative Event Windows:**
   - Top widescreen atmospheric banner/illustration with a smooth gradient fade into the dark parchment body.
   - Left/right overlapping **Character Portrait Medallion** (circular/octagonal brass bezel showing the involved citizen/leader bust).
   - Narrative text containing **inspectable inline keyword links** (hovering reveals a nested card explaining the trait, faction, or mechanic).
   - Full-width **engraved choice plaques** at the bottom with the narrative option on the left and color-coded resource/trait consequences aligned cleanly on the right.
2. **Civ-Style Top Yield Ribbon & Bottom-Right Command Medallion:**
   - Top bar displays compact icon + tabular value yields (`Gold`, `Science`, `Beacon`, and the game's other readouts) with detailed breakdown popovers on hover.
   - Primary turn/phase advancement lives in a **bottom-right circular brass-and-enamel Command Medallion**, never a standard form button.
3. **Character & Hybrid Dossiers (CK3 Style):**
   - Character bust overlaps the top-left corner of the dossier frame.
   - Traits render as **diamond/shield-shaped Heraldic Crests** (not rounded pills).
   - Stats (`Food`, `Production`, `Science`, `Gold`, `Beacon`, `Military`) render as brass-trimmed gauges; a unit's two gear slots (weapon, armor) show as sockets.

---

## 4. Multi-Layer Map Architecture (Minimum 4 Layers)
Never render a bare grid with isolated single-sprite boxes. The map must composite **at least 4 distinct layers** (combat happens on the main map; there are no separate battle scenes):
1. **Terrain & Cartography Layer:** Contoured ground textures, roads, rivers, forests, ore ridges, and subtle cartographic grid lines.
2. **Environmental Storytelling & Prop Layer:** Non-blocking surface details—shell craters, sandbag perimeters, supply crates, scorch marks, and alien crystal creep.
3. **Interactive Entities & Infrastructure Layer:** Structures and units with grounded contact shadows, directional facing and health arcs.
4. **Atmospheric & FX Overlay Layer:** Muzzle flashes, tracer arcs, smoke plumes, fog-of-war edge vignettes, shard beams and alien strike warnings.

---

## 5. Mechanics
The mechanics are those in docs/DESIGN.md and the milestone specs (designer 2026-11-21: the
mobile game's power grid, four-resource economy, salvage crafting, Overload, Field Hospital and
adaptive aliens are not part of Beacon). This file sets the visual rules only.

---

## 6. Workflow
- New mechanics: the deterministic simulation and its tests come first, then the UI in the same
  milestone, built with these visual rules.
- Visual-only changes (designer 2026-11-21) need no simulation or balance runs: restyle, check in
  the browser, commit.