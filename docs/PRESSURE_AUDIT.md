# Pressure audit (SPEC_M12, 2026-11-15)

For each building and unit, the pressure it answers on the turn a player builds it. A pressure is
something the player can see: an announced strike, heat, a rumour, a hungry or slow city, a
council need. Rows marked **weak** answer only "a bigger number"; they are tied to a pressure
here or flagged for a later change.

## Buildings

| building | pressure it answers | notes |
| --- | --- | --- |
| food_depot, water_treatment, vertical_farm, climate_dome | the city is not growing; refugees (survivors, captives) need feeding | M14: freed cities arrive with survivors |
| workshop, factory, autonomous_factory, fusion_plant, metro | a strike is coming and the city cannot build defenders in time | factories add heat: the cost of answering |
| library, school, research_lab, data_centre, quantum_lab | the next tech answers a threat (Robotics for bridges, the barrage) | labs add heat |
| market, financial_center, logistics_hub | gold buys units the turn a strike is announced; resistance costs gold | **weak** until buying under a countdown is common |
| port, shipyard | reaching an ally's continent; aid | heat 1-2 |
| military_base, air_defence_battery, defence_perimeter, plasma_shield, chitin_bulwark | an announced strike's strength is above the city's defence | the Threats list shows both numbers |
| radio_tower, sensor_array, phase_scanner | **weak**: no pressure yet | tie to seeing strike sources and alien city contents from afar (later) |
| hospital | wounded units after a strike | **weak**: tie to healing (later) |
| armoury | **weak**: no effect beyond the queue | tie to gear in M14 (better weapons) |
| orbital_relay | **weak** | later: sight of plans on other continents |
| beacon_i-v, translation_hub | recruits answer council gaps; beacons are the loudest heat | the core trade-off: speed against attention |
| bio_reactor | production for a strike, at alien-tech cost | |

## Units

| unit | pressure it answers |
| --- | --- |
| infantry, militia, marines, mech/exo infantry, home_guard, xeno_trooper | defend against an announced strike; take a weakened city |
| tank, hover_tank, walker, swarm_drones | break a strike before it launches (attack the gathering force) |
| artillery, howitzers, rockets, plasma cannon/lancer, city_artillery, anti_tank | hit a city or a gathering force without retaliation |
| recon_team, drone_recon, armoured_recon, scout_boat | learn what an alien city holds (contents) and where strikes gather; sabotage |
| engineers | improvements, sea bridges, sabotage |
| survey_team, medical_team, nanorepair_crew | **weak**: niche; review after M14 |
| destroyer, railgun_cruiser, attack_submarine | aliens never cross water: **weak** until sea threats exist |
| trade_convoy | moving goods to a threatened city |

## Follow-ups
- Sensor buildings should reveal strike sources and contents at range.
- The armoury should make better gear (M14).
- Navy needs a sea pressure (later).
