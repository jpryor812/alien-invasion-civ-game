# SPEC M22: fixes from play

Designer 2026-11-22.

## Rules
- Taking the first town: the leader joins the town (leaves the map and leads from it); the
  survivors stay in the field as survivors; no recon team appears. The town has its 3 rescued
  people.
- Units no longer stack (`combat.stacking: false`); stacks in old saves stay until split.
- No rations: units no longer carry food or starve in the field (`food.rations_on: false`);
  towns still feed the units in their land.
- A building's timber and stone are taken when the engineers start it (the top of the works
  list), not when it is ordered. If the town is short, the crew waits ("waiting for materials").
- Timber and stone come only from improvements: lumber camps in forests, mines on hills (and
  extractors and other works). The town's own hex, forests and hills give nothing by
  themselves; a resource adds its goods only on an improved hex.
- Shards are mined with a Mine order (a button on the unit), kept each turn the unit stays.
  When a player starts mining a shard the aliens send an alien warrior and an alien drone, which
  appear 3 hexes away and go for it.
- Meeting another civ shows each other's capitals on the map.

## Talks
- Both leaders stand in the hall, theirs on their side and yours on yours.
- Besides gold and materials, techs the other side can learn and alien recruits can be traded
  (once).

## Screen
- When the leader levels up, the leader page opens to spend the point.
- With nothing selected, a status panel on the left shows research (turns left), each town's
  current work and training (turns left, or waiting for materials), and unit counts.
