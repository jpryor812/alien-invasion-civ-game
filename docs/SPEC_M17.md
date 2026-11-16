# M17: labour and materials, one game (designer 2026-11-16)

The designer's call after M16: building is "labour plus materials - so must have the materials and
then depending on how many engineers we have, is how many turns it would take to build after
spending the resources". The settlement sandbox (M15) is retired; what it proved lives on in the
main game.

## Rules

1. **Engineers are a city crew.** Every city has `engineers` (a count, not map units). A player
   city starts with `labour.start` of them (the capital `labour.capital_start`, a band's first town
   `labour.town_start`). More are trained from the city's queue (the "engineer" item, production
   cost `engineers.cost` + `engineers.cost_step` per engineer the city already has); each costs
   `engineers.upkeep` gold a turn.
2. **Works.** Buildings, walls and tile works (farm, mine, lumber camp...) are *works*, not queue
   items. Ordering one pays its materials at once; a city short of them cannot order it. A work
   needs labour: a building its production cost (`labour.building_pct`), wall pieces their
   `production` x `labour.per_wall`, a tile work its turns x `labour.per_engineer`.
3. **Labour.** Each engineer adds `labour.per_engineer` labour a turn (+`labour_pct` from techs and
   the leader). The city's labour goes to its works in order: the first takes what it needs and the
   rest passes on. So turns = labour left / (engineers x per engineer). Cancelling a work refunds
   its materials.
4. **Production** now trains units and engineers and runs projects. Gold still buys units; it no
   longer buys buildings.
5. **The Galactic Exchange** (from the sandbox): any city trades timber, stone and iron for gold.
   The Exchange pays `exchange.sell_pct` and asks `exchange.buy_pct` of a base price scaled by a
   shared price index (percent) that moves `exchange.step_pct` per 10 units traded, stays within
   `min_pct`-`max_pct`, and drifts `revert_pct` back toward 100 each turn. No randomness.
6. **Map engineers.** Starting and founding engineers are gone (the crew replaces them). The
   `engineers` unit stays trainable as the **road crew** for roads, railways, turrets and sea
   bridges only; tile works are refused on the map ("ordered from the city").
7. **One city screen.** The builder is the city screen: crew, works with turns, the production
   queue, materials and the Exchange. The map's city panel keeps a short summary and "Develop city".
8. **Sandbox retired.** `beacon/settlement.py`, `data/settlement.yaml`, `web/sandbox.py`, the
   sandbox page and its tests are removed; its art stays as builder fallbacks.

## AI

Orders one affordable building at a time as a work (same priorities), trains engineers up to
`ai.crew` per city, sends its crew to improve worked tiles, and uses road crews for roads and
bridges only. Sells surplus materials and buys what a wanted building lacks when it has gold.

## Acceptance

- Ordering pays materials; turns fall as engineers are added; completion places the building.
- Tile works through the crew; map tile works refused; walls through labour.
- Exchange buy/sell moves prices and gold deterministically.
- AI 10-seed batch: cities still build, liberations and first-town timing comparable to M16.
- Tests and ruff pass; the sandbox is gone from the menu, server and data.
