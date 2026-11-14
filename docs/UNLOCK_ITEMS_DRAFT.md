# Unlock items and bonus techs: draft stats

Status: draft for designer review. Nothing here is in `data/` yet. Every number is a placeholder.
Companion to [CONTENT_REVIEW.md](CONTENT_REVIEW.md), which proposes these items and techs. Fields
follow the existing `buildings.yaml`, `units.yaml` and `techs.yaml` schema.

## New city buildings (5)

| Building | Unlocked by | Cost | Upkeep | Yields | Yield % | Other | Requires |
|---|---|---|---|---|---|---|---|
| stock_exchange | automated_markets (T3, econ) | 160 | 1 | gold 2 | gold 25 | | market |
| biofoundry | synthetic_biology (T3, econ) | 120 | 1 | food 3, production 1 | | | |
| combined_arms_command | combined_arms (T3, mil) | 140 | 2 | | | unit production +20% | |
| orbital_battery | orbital_defence_grid (T3, mil) | 160 | 2 | | | city strength 6, city HP 50 | |
| deep_radar_station | deep_space_radar (T3, prod) | 180 | 2 | | | vision 5 | |
| antimatter_reactor | antimatter_power (T4, prod) | 280 | 3 | production 4 | production 20 | | |

Notes:
- The stock exchange and antimatter reactor both add percent yields, so their values stay within
  the factory and fusion range (25 to 35%).
- Combined arms command and orbital battery use the existing keys (`unit_production_pct`,
  `city_strength`, `city_hp`), so they need no schema change.

## Moved existing items

| Item | From | To | Reason |
|---|---|---|---|
| militia (unit) | industrial_base | militia_reserves (T1, mil) | Fits its name |
| orbital_relay (building) | nanofabrication (T4, prod) | orbital_launch (T3, prod) | Fits its name and tier |

## New units (2)

| Unit | Unlocked by | Domain | Role | Cost | Moves | Strength | Vision | Other |
|---|---|---|---|---|---|---|---|---|
| stealth_drones | stealth_tech (T4, mil) | land | recon | 110 | 4 | 12 | 3 | |
| robotic_engineers | robotics (T2, prod) | land | civilian | 70 | 2 | 0 | 1 | build speed +25% (new key) |

Notes:
- Stealth drones use the recon role, so no new role is needed. Stealth itself (hiding from aliens)
  is a rule we have not designed. For now it is just a fast scout.
- Robotic engineers need a `build_speed_pct` effect key, which is a new key, to make them faster.

## Bonus-only techs (6)

These techs unlock nothing and only apply an effect. They need the optional `effects` field on
techs, which is a schema change for the other chat.

| Tech | Tree and tier | Effect | Value |
|---|---|---|---|
| urban_planning | econ T1 | yield_pct food, in cities | 10 |
| sovereign_bonds | econ T2 | yield_pct gold, in cities | 10 |
| reactive_armour | mil T1 | unit_strength_pct, land and sea | 5 |
| ai_targeting | mil T4 | ranged_strength_pct | 10 |
| quantum_theory | prod T1 | yield_pct science, in cities | 10 |
| mass_production | prod T2 | yield_pct production, in cities | 10 |

## Effect keys

Keys already in use or proposed:

| Key | Status | Used by |
|---|---|---|
| yield_pct | existing in buildings | urban_planning, sovereign_bonds, quantum_theory, mass_production |
| unit_strength_pct | new | reactive_armour |
| ranged_strength_pct | new | ai_targeting |
| city_strength | existing in buildings | orbital_battery |
| city_hp | existing in buildings | orbital_battery |
| unit_production_pct | existing in buildings | combined_arms_command |
| build_speed_pct | new | robotic_engineers |

The new keys (`unit_strength_pct`, `ranged_strength_pct`, `build_speed_pct`) are the only schema
additions here. Each needs a decision before the other chat adds them.

## Decisions

- **Bonus-only techs apply to all cities.**
- **Stealth drones are hidden from aliens until they attack.** An attack reveals them for that
  turn. This is a new rule and needs a `stealth` flag on the unit.
- **Conflict to resolve:** the M4 spec says aliens see the whole map, including player units
  (decided). Stealth as written breaks that rule. Options:
  1. Keep the M4 rule and exempt stealth units only.
  2. Change the M4 rule so aliens do not see stealth units.
  Either way, the M4 spec needs a note.

## Open questions

- Confirm the placeholder values before any promotion.
- Which option for the stealth conflict above?
