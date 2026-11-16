# M13 — The council of continents (designer, 2026-11-15)

Approved by the designer. Models: Dead of Winter (shared crises, votes, personal goals),
CK3 (leaders with agendas), Civ V (rivals who want what you want).

Why: the continents worked alone until about turn 16 and the MVP score was invisible, so
cooperation had no friction and there was no rival. The other leaders become the competition:
not war, but influence, the chair and credit for saving the world.

## 1. Radio contact from turn 1
- Every player has met every other at the start (radio). Their land and cities are still found
  by exploring. Replaces meeting by exploration (beacon/contact.py); beacon contact stays as a
  no-op.

## 2. Influence
- A new per-player resource. Earned: freeing a city, aid given (per 50 gold, per unit, per
  tech), shards claimed, keeping council pledges. Spent: proposing a measure, extra votes.
- Shown in the top bar.

## 3. Council sessions
- Every 5 turns (`council.session_turns`) the council meets. Up to three measures are on the
  table: one drawn from data/council.yaml by seed, plus any proposed by players (paid in
  influence).
- Each player votes yes, no or abstains, weighted 1 + influence / 50 (rounded down); a player
  may spend influence for extra weight. Measures pass on a weighted majority of votes cast.
- Measures (first set): **joint strike** (every member's units near a named alien city get +15%
  attack for 5 turns), **fuel quota** (a strategic resource from the richest to the poorest),
  **evacuation** (aid to a falling continent: each member pays gold), **chair election** (the
  chair breaks ties and picks next session's drawn measure), **research pact** (+10% science
  for all, -5% gold), **beacon silence** (everyone's heat -25% and beacon output -25% for 5
  turns).
- Pledges: some measures ask for contributions; paying them earns influence, refusing costs it.

## 4. Agendas and secret objectives
- Each leader has a public **agenda** (seeded for the AI, chosen for the human from three at
  creation): Liberator, Scientist, Merchant, Warden, Mystic. Agendas set how AIs vote and give
  the leader a small bonus for actions that match.
- Each player has one **secret objective** (seeded), worth MVP points at the end if met, e.g.
  "free 3 cities on another continent", "hold the chair 3 times", "have 2 hybrids on the
  council". Shown to its owner only.
- Later (designer: not yet): a hidden collaborator who wins with the aliens.

## 5. Visible competition
- The top bar shows your MVP rank and influence; the Scores screen shows everyone's.

## Acceptance
- Tests: contact at start, influence earning and spending, sessions on schedule, weighted votes,
  each measure's effect, AI voting by agenda, objectives scored, save round-trips.
- pytest and ruff pass; batch finishes; the council session screen checked in the browser.
