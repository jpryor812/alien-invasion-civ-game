# Unit art

Each PNG is a 3D model generated with Meshy (text to 3D, on the designer's own Meshy account,
2026-11-15) and rendered in Blender in this repo. The camera is orthographic, 40 degrees above the
horizon and turned 30 degrees, matching the map. Renders are 256 px with a transparent background,
lit by a warm key light, a cool fill light and a rim light, using the AgX "Punchy" look.

The client (`web/static/app.js`, `UNIT_ART`) maps every unit type to the nearest model. It crops
each render to its content and draws it on a team-coloured base. If an image is missing, the
client falls back to the drawn badge.

| file | prompt (short) | used for |
| --- | --- | --- |
| infantry | soldier in combat armour with rifle | infantry, militia, marines, home guard, recon, anti-tank, xeno trooper, plasma lancer |
| engineer | engineer in hard hat and hi-vis vest | engineers, survey, medical, nanorepair |
| tank | main battle tank | tank, mech infantry, armoured recon, trade convoy |
| hover_tank | hover tank on anti-gravity pad | hover tank |
| artillery | towed howitzer | artillery, city artillery, railgun, SP howitzer, rockets, plasma cannon |
| walker | military combat mech walker | walker, exo infantry |
| drone | quadcopter recon drone | drone recon, swarm drones |
| destroyer | navy destroyer | every ship |
| alien_small | small insectoid alien | alien drone, hatchling |
| alien_warrior | bipedal alien with blade arms | warrior, pillager, wraith |
| alien_spitter | alien artillery creature | spitter, sporecaster |
| alien_brute | armoured alien brute | hive guard, brute, shieldbearer |
| alien_titan | tentacled alien titan | titan, leviathan |

The Blender scene is saved to `runs/unit_models.blend`, which is git-ignored.
