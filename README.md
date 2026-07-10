# Paint2Blend

A tiny Blender addon for stylized terrain: blend **two tiled textures through a
painted 1024x1024 bitmask**, brushed directly on the mesh in the viewport.
Grass with painted dirt patches, sand with rock, snow with mud - one brush.

Tested on Blender 5.0 (works from 4.4+).

## How it works

The addon builds a three-layer UV setup on the active mesh:

| UV layer | Purpose |
|----------|---------|
| **UV1** | Base texture tiling (adopts the mesh's existing UVs) |
| **UV2** | Overlay texture tiling (copy of UV1 - retile it independently) |
| **Bitmask** | A one-island unwrap the 1024x1024 mask image maps through |

and wires `Base Color = Mix(base @ UV1, overlay @ UV2, factor = mask @ Bitmask)`.

## Usage

1. Install `paint2blend.py` (Preferences > Add-ons > Install) - a **Bitmask**
   tab appears in the 3D View sidebar.
2. Select your terrain mesh, assign the **Base** (UV1) and **Overlay** (UV2)
   textures in the panel.
3. Press **Paint Bitmap** - the UV layers, node graph and mask image are
   created (once) and you land straight in Texture Paint with the viewport in
   Material Preview. **Paint white = overlay shows, black = base.**
4. **Save Bitmap** writes the mask PNG next to your .blend.
5. The **Edit UV** row (`UV1 | UV2 | Bitmask`) hops into Edit Mode on that
   layer to retile or fix the unwrap - press the lit button again to hop out.

## Notes

- Idempotent: pressing Paint Bitmap on an already-set-up mesh just re-enters
  paint mode; the graph is never duplicated.
- The mask is named `<Object>_Bitmask` and saved beside the .blend, so each
  object gets its own mask.
- For game engines without runtime texture blending, bake the mixed Base Color
  down to a single texture when the painting is done.
