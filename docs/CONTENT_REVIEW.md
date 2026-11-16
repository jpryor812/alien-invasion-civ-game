# Content review: units, buildings and techs

Status: review notes for the designer. Based on the data as of commit `0b79762` (active content
plus the `additional` blocks). Nothing here has been applied to `data/`. Later milestones may
have changed the data since.

## Verdict

The shape is sound: four trees, five tiers, units and buildings gated by tech, improvements built
by engineers. The content has grown faster than the unlocks that should use it, so we should
prune and give each tech a job before adding more units or buildings.

## Numbers

- Techs: 40 in total (21 active, 19 additional).
- Techs that unlock nothing: 17 of 40. Of the 21 active techs, 3 are empty (automated_markets,
  nanofabrication until its additional items are promoted, post_scarcity until arcology is
  promoted).
- Units: 19 active player and alien units, plus 13 player and 6 alien units in `additional`.
- Buildings: 14 active, plus 14 in `additional`.
- Improvements: 7 active, plus 7 in `additional`.

## Tech to unlock map

`*` marks an additional item or tech.

**Economic**

| Tech | Unlocks |
|---|---|
| market_economy (T0) | food_depot, market, port |
| digital_finance (T1) | financial_center |
| urban_planning* (T1) | nothing |
| vertical_farming (T1) | vertical_farm, hydroponic_plot* |
| biotech_medicine (T2) | hospital, medical_team* |
| global_logistics (T2) | logistics_hub* |
| sovereign_bonds* (T2) | nothing |
| automated_markets (T3) | nothing |
| carbon_markets* (T3) | nothing |
| climate_engineering* (T3) | climate_dome* |
| synthetic_biology* (T3) | nothing |
| post_scarcity (T4) | arcology* |

**Military**

| Tech | Unlocks |
|---|---|
| modern_warfare (T0) | recon_team, infantry, tank, artillery, destroyer, marines*, anti_tank_team*, military_base, air_defence_battery*, shipyard* |
| fortification_doctrine (T1) | defence_perimeter, military_base (improvement) |
| mechanized_warfare (T1) | mech_infantry, armoured_recon*, self_propelled_howitzer*, rocket_battery*, armoury*, minefield* |
| militia_reserves* (T1) | nothing |
| reactive_armour* (T1) | nothing |
| drone_warfare (T2) | drone_recon, swarm_drones* |
| powered_exoskeletons (T2) | exo_infantry, walker* |
| combined_arms* (T3) | nothing |
| orbital_defence_grid* (T3) | nothing |
| railguns (T3) | railgun_artillery, railgun_cruiser, attack_submarine* |
| ai_targeting* (T4) | nothing |
| directed_energy* (T4) | plasma_cannon*, plasma_shield* |
| hover_armour (T4) | hover_tank |
| stealth_tech* (T4) | nothing |

**Production**

| Tech | Unlocks |
|---|---|
| industrial_base (T0) | engineers, restoration_team, militia*, survey_team*, workshop, school, water_treatment*, solar_array*, wind_turbines* |
| advanced_manufacturing (T1) | factory |
| high_speed_rail (T1) | metro*, railway |
| quantum_theory* (T1) | nothing (prerequisite only) |
| applied_ai (T2) | research_lab, data_centre* |
| mass_production* (T2) | nothing |
| radio_beacon_network (T2) | radio_tower, sensor_array*, radio_beacon, sensor_mast* |
| robotics* (T2) | nothing |
| deep_space_radar* (T3) | nothing |
| fusion_power (T3) | fusion_plant, geothermal_vent* |
| orbital_launch* (T3) | nothing |
| antimatter_power* (T4) | nothing |
| nanofabrication (T4) | nanorepair_crew*, autonomous_factory*, orbital_relay*, hyperloop* |
| quantum_computing* (T4) | quantum_lab* |

## Problems

1. **Empty techs.** 17 techs unlock nothing. Most are Stellaris-flavoured additions.
2. **Wrong homes.** militia sits under industrial_base, and it belongs under militia_reserves.
   orbital_relay sits under nanofabrication, and it belongs under orbital_launch. Vision is spread
   across six sources.
3. **Overlap.**
   - Nine melee land units: infantry, militia, marines, mech, exo, walker, tank, hover tank, swarm
     drones.
   - Six ranged land units: artillery, howitzer, rocket battery, anti-tank team, railgun artillery,
     plasma cannon.
   - Four scouts: recon team, drone recon, armoured recon, survey team.
   - Seven food buildings and improvements: food depot, vertical farm, water treatment, hospital,
     arcology, climate dome, hydroponic plot.
4. **Beacon tree.** The design has four trees. The data had three at this commit. Recruits,
   councils and beacon tech need a home (the other chat's M5 work addresses this).
5. **Techs have no effects.** They only gate unlocks. Reactive armour, mass production and
   robotics cannot do anything beyond unlocking an item.
6. **Late game.** The barrage project (M7) and naval transport (M6) have no tech or unit yet.

## Proposed changes

**Keep, and give each tech one unlock:**

| Tech | Proposed unlock (new item) |
|---|---|
| orbital_defence_grid | orbital battery (city strength) |
| deep_space_radar | deep radar station (vision) |
| synthetic_biology | biofoundry (food) |
| robotics | robotic engineers (faster engineers) |
| antimatter_power | antimatter reactor (production) |
| stealth_tech | stealth drones (unit) |

**Move:**
- militia to militia_reserves.
- orbital_relay to orbital_launch.

**Merge or cut:**
- urban_planning, sovereign_bonds and carbon_markets: fold into financial_center and
  climate_engineering.
- reactive_armour: into fortification_doctrine.
- ai_targeting: into stealth_tech.
- combined_arms and mass_production: cut unless needed.
- rocket_battery: into self-propelled howitzer.
- exo_infantry: replaced by walker.
- sensor_mast: into radio beacon.
- survey_team: cut, or merge the vision sources.

quantum_theory stays as a stepping stone, since it is a real prerequisite.

**Net effect:** about 7 new items and about 8 fewer techs or items, rather than +30.

## Decisions

1. **Beacon tree:** later, not now.
2. **Military percent key:** accepted. Recruits use `military_pct` for unit strength and unit
   production. It sits outside the point budget.
3. **Most techs unlock items. Some techs are bonus-only.** A bonus-only tech gives a flat or percent
   effect and unlocks nothing. Techs that are only a stepping stone with no effect should be merged.
   This needs an optional `effects` field on techs, a schema change for the other chat to make.

## Empty techs: proposed fix

Each empty tech either unlocks a new item (`item`) or becomes bonus-only (`bonus`). Proposed effect
keys: `yield_pct`, `unit_strength_pct`, `ranged_strength_pct`, `city_strength`, `city_hp`.

| Tech | Proposal | Detail |
|---|---|---|
| urban_planning (econ T1) | bonus | food +10% in cities |
| sovereign_bonds (econ T2) | bonus | gold +10% in cities |
| automated_markets (econ T3) | item | stock_exchange building (gold) |
| carbon_markets (econ T3) | cut | fold into climate_engineering |
| synthetic_biology (econ T3) | item | biofoundry building (food) |
| militia_reserves (mil T1) | item | militia unit, moved from industrial_base |
| reactive_armour (mil T1) | bonus | unit_strength_pct +5 |
| combined_arms (mil T3) | item | combined_arms_command building (unit production) |
| orbital_defence_grid (mil T3) | item | orbital_battery building (city strength) |
| ai_targeting (mil T4) | bonus | ranged_strength_pct +10 |
| stealth_tech (mil T4) | item | stealth_drones unit |
| quantum_theory (prod T1) | bonus | science +10% in cities |
| mass_production (prod T2) | bonus | production +10% in cities |
| robotics (prod T2) | item | robotic_engineers unit (faster engineers) |
| deep_space_radar (prod T3) | item | deep_radar_station building (vision) |
| orbital_launch (prod T3) | item | orbital_relay building, moved from nanofabrication |
| antimatter_power (prod T4) | item | antimatter_reactor building (production) |

Result for the 17 empty techs: 10 unlock new items, 6 become bonus-only, and 1 is cut
(carbon_markets). Each new building, unit or bonus needs its numbers tagged placeholder.
