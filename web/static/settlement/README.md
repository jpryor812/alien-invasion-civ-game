# Settlement sandbox art (docs/SPEC_M15.md)

Each building is a low-poly model built from primitives (boxes, gables, cylinders, cones with a
bevel) by a script in Blender in this repo (2026-11-16), and rendered with a transparent
background: orthographic camera 35 degrees above the ground (matching the sandbox view's tilt)
and turned 28 degrees for a three-quarter look, one sun plus a soft sky, Standard view transform
for saturated colours. 512 px renders, saved as 384 px WebP. The model's ground origin sits 65.4%
down each image; `web/static/sandbox.js` (drawBuilding) anchors there.

Files: city_hall, farm, lumber_camp, quarry, iron_mine, granary, warehouse, house, workshop,
watchtower. Original work; no third-party assets. The scene is "Settlement" in
`runs/unit_models.blend` (git-ignored). Ground textures and the forest sprites are reused from
`web/static/terrain` and `web/static/features` (see their READMEs).
