# Leader art (docs/SPEC_M11.md)

The figures are 3D models made with Meshy (text to 3D, on the designer's own Meshy account,
2026-11-15) and rendered in Blender in this repo. The designer asked for one man and one woman
leader with two outfits each for now: four models.

| file | look | outfit | prompt (short) |
| --- | --- | --- | --- |
| man_1_civilian | man_1 | civilian | man in a navy commander's long coat over a grey suit |
| man_1_field_uniform | man_1 | field_uniform | man in an olive field uniform with belt and boots |
| woman_1_civilian | woman_1 | civilian | woman in a navy commander's long coat over a grey suit |
| woman_1_field_uniform | woman_1 | field_uniform | woman in an olive field uniform with belt and boots |

- Full figures: orthographic camera from the front, 4 degrees above, the figure turned 10 degrees;
  480 x 960 px, transparent background, warm key, cool fill and warm rim lights (AgX).
- `*_portrait`: head and shoulders from the same camera, 256 px, for council cards and banners.
- Each outfit is its own Meshy model, so the face differs a little between outfits of the same
  look. Age shows as a grey tint on the hair in the client, not new models.
- `backdrop_hall.webp`: the "Mirrored Hall" HDRI by Grzegorz Wronkowski from Poly Haven (CC0,
  https://polyhaven.com/a/mirrored_hall), rendered in Blender, then blurred, darkened, warmed
  and vignetted in code.
- Accessories (medal, sash, star pin, family crest) are drawn by the client as overlays.

The Blender scene ("Leaders" in `runs/unit_models.blend`) is git-ignored.
