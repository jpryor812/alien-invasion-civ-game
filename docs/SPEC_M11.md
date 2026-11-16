# M11 — Ocean bridges and the leader (designer, 2026-11-15)

Status: draft for the designer's approval. The designer's words are quoted. Choices already
made are marked (designer); the rest are proposals, and every number is a tunable.

Designer's choices (2026-11-15): Meshy 3D renders for the leader; the leader ages but never dies;
anyone, aliens too, can cross bridges; this round builds the bridges and the full leader
(creation, screen, skills, XP and levels, traits, wardrobe, the 16-seat council, AI leaders,
families and hybrids). The five story events from SPEC_M9 section 4 come later.

## 1. Ocean bridges

"A technology to build cross-ocean bridges so we can connect continents by land and move
faster."

- New tech **Ocean Engineering** (production tree, tier 3, 280 science; prereq Applied AI).
- New route **sea bridge**, built by engineers on a **shallow water** (coast) hex next to land or
  to another bridge, over 6 turns. Deep ocean cannot be bridged. The engineers stand on the land
  or bridge hex beside it while they build.
- A bridged hex is passable to land units at road speed and counts as a road: it connects cities
  (connection gold, strategic resources), carries convoys, and joins continents. Ships still sail
  through it.
- Anyone can cross, aliens too (designer). Aliens can pillage a bridge like any improvement, and
  engineers repair it.
- The one-hex straits from M10 need one bridge; wider seas need a chain.
- AI players build a bridge toward an ally's continent once they have the tech.

## 2. The leader

"I like this view where you can see them, so we can eventually show off outfits and accessories
and their stats which can eventually be upgraded - and this is also where traits will be shown."

### Who
- Every player has a leader (the AI continents too). The leader is not a unit on the map.
- **Creation** at the start of a new game: name, sex, look (one of the rendered looks, below), and
  two traits chosen from a list. The AI's leaders are generated from the seed.
- **Age**: chosen from 30 to 55 at the start, plus one year every 4 turns (a turn is a quarter).
  The leader never dies in a game (designer).

### Skills, XP and levels
- Six skills, one per domain (food, production, military, science, gold, beacon), each starting
  at +1 (designer, SPEC_M9).
- The leader sits at the head of the council: each skill adds its value to that yield in every
  city, as a council member does (military adds city strength).
- **XP** comes from achievements: freeing a city, defeating alien units, claiming shards, a child
  growing up, finishing a wonder-style project. Each level gives one skill point to spend
  (designer: "each level lets the leader raise a skill"), and some levels are milestones from the
  SPEC_M9 table that offer a choice of 2-3 bonuses for this game.
- **Traits**: a leader has two at the start (for example Steady: +10% city strength; Visionary:
  +10% science; Quartermaster: unit upkeep -1). A third can be earned at level 5. They show on the
  leader screen with tooltips, as in the references.

### The council (16 seats)
- The leader heads the council, then 3 vice-presidents (the general seats) and 2 specialists in
  each of the six domains (designer, SPEC_M9). The board shows the leader at its head.

### Family and hybrids (SPEC_M9, designer answers)
- A **Start a family** button with a cooldown: choose a human partner (any grown citizen) or an
  alien recruit. A child is born in the capital a few turns later; once that child is grown, you
  may start another.
- A human partner's child is a citizen with the usual 6 stat points. A **hybrid**'s stat points
  are the average of the leader's (6) and the alien parent's total (designer); it may carry one
  alien trait.
- Each city has an **attitude** to hybrids, seeded at the start (most accept, some refuse). A
  hybrid cannot work tiles in a refusing city but can sit on the council. A hybrid on the council
  has a small chance each turn of being voted out.
- The family shows on the leader screen: partner and children, with their portraits.

### The leader screen (after the references)
- A new **Leader** button in the top bar, and the screen at game start:
  - the leader standing in a full-height render, on a scene backdrop;
  - name, title ("President of Europe"), age, sex;
  - the traits row; the six skills with their values, the XP bar and points to spend;
  - the family row; the wardrobe (outfit and accessory slots); career totals.
- The creation screen uses the same layout, with choices in place of values.

### Art: Meshy 3D renders (designer)
- 379 Meshy credits are left (about 12 models). Proposal:
  - **4 leader looks**, 2 men and 2 women, in a civilian commander's coat: 4 models.
  - **2 alternate outfits** (field uniform, dress uniform) for each look, unlocked by career
    milestones: 8 models at the most. If credits run short, the uniforms go to 2 looks first.
  - Each model is rendered in Blender as a full-height figure from the front, at about 1024 px.
  - Accessories (medals, sashes, insignia, a beret) are small separate models or painted
    overlays, placed from the same camera so they line up with the figure.
  - Portraits for council cards and banners are cropped from the same renders.
- Age shows as greying hair in the render (a tint in the client), not new models.

### Wardrobe and career (across games)
- Career totals (cities freed, shards claimed, children, games won) are kept in a local profile
  file (runs/profile.json, git-ignored) and carry from game to game.
- Career milestones unlock outfits and accessories. These are **cosmetic only**: gameplay
  bonuses never carry over (designer, SPEC_M9).

## 3. Not in this round
- The five story events: refugee column, captured soldier, infection, council defection,
  resistance (SPEC_M9 section 4).
- Leaders in diplomacy scenes (a leader standing in a scene while you trade).
- Custom looks beyond the rendered set.

## Acceptance
- Tests for bridges (building, crossing, connection, pillage), leader skills and council effect,
  XP and levels, traits, families and hybrid stats, city attitudes and votes, AI leaders, and
  save round-trips.
- pytest and ruff pass. The 10-seed batch still finishes, and its notes cover bridges built and
  leader levels reached.
- The leader and creation screens are checked in the browser against the references.
- docs/ASSUMPTIONS.md records each modelling choice; DESIGN.md is updated.
