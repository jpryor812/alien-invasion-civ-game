# City builder art (docs/SPEC_M16.md)

Building sprites for the city builder, one per building id, plus the city hall.

- **Meshy** (text to 3D, on the designer's own Meshy account, 2026-11-16; prompts "low-poly
  stylized game building ... bright colours, mobile strategy game style"): city_hall, library,
  market, military_base (the barracks), workshop, factory, radio_tower, food_depot.
- **Blender kit** (original models built from primitives by script in this repo, 2026-11-16):
  every other building, by archetype - offices, labs with domes, glass domes, towers with dishes,
  power cores, beacon spires (taller with each level), docks, a hospital, alien pods, plants with
  tanks, storehouses, an automated factory.

All are scaled to the same footprint (1.6 units across, height capped at 2.4), set on the
ground at the origin, and rendered with a transparent background from the builder's camera:
orthographic, 35 degrees above the ground, turned 28 degrees, Standard view transform. 512 px
renders saved as 384 px WebP. The ground origin sits 65.4% down each image
(`web/static/builder.js`, drawBuilding). Scene "Settlement" in `runs/unit_models.blend`
(git-ignored).
