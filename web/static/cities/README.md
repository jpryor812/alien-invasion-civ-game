# City art

These city renders were made in Blender in this repo on 2026-11-15. They are simple house,
mid-rise and tower blocks laid out in street blocks inside the hex, textured with CC0 Poly Haven
materials (https://polyhaven.com):

- roof_09 (Rob Tuytel): terracotta roofs.
- exterior_wall_cladding_03 (Charlotte Baglioni): plastered walls; the window rows are a
  procedural pattern added in Blender.
- concrete_tile_facade (Charlotte Baglioni): towers and flat roofs.
- aerial_asphalt_01 (Rob Tuytel): paving.

The camera is orthographic, 55 degrees above the ground, with an ortho scale of 3.2 hex radii and
the hex centre 62% of the way down the frame. Images are scaled to 360 px.

| files | what |
| --- | --- |
| city_0_*.png | village: houses only, no paving |
| city_1_*.png | town: houses and mid-rises on paving |
| city_2_*.png | city: adds a few towers |
| city_3_*.png | metropolis: a dense tower core |
| suburb_*.png | houses and mid-rises without paving, drawn on neighbouring hexes |

The capitol, the walls and the shield are painted over these in the client (`drawCity`).
