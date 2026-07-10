bl_info = {
    "name": "Paint2Blend",
    "author": "myuu-151",
    "version": (1, 0),
    "blender": (4, 4, 0),
    "location": "3D View sidebar > Paint2Blend",
    "description": "Two-texture terrain blending through a painted 1024x1024 "
                   "bitmask: assign a base texture (UV1) and an overlay texture "
                   "(UV2), press Paint Bitmap and brush the overlay in directly.",
    "category": "Paint",
}

import bpy, os


MASK_SIZE = 1024


# ------------------------------------------------------------------ helpers
def ensure_uv_layers(ob):
    """UV1 = base tiling (adopts the object's existing first UV), UV2 = overlay
    tiling (copy of UV1, retile it as you like), Bitmask = one-island unwrap
    the mask image maps through."""
    me = ob.data
    if "UV1" not in me.uv_layers:
        if len(me.uv_layers):
            # adopt the current render layer as the base tiling layer
            (me.uv_layers.active or me.uv_layers[0]).name = "UV1"
        else:
            me.uv_layers.new(name="UV1")
    if "UV2" not in me.uv_layers:
        me.uv_layers.active = me.uv_layers["UV1"]   # .new() copies the active layer
        me.uv_layers.new(name="UV2")
    made_bitmask = False
    if "Bitmask" not in me.uv_layers:
        me.uv_layers.new(name="Bitmask")
        made_bitmask = True
    me.uv_layers["UV1"].active_render = True
    return made_bitmask


def unwrap_bitmask(ob):
    """Smart-project the Bitmask layer as one seamless island (angle limit above
    typical terrain slopes)."""
    me = ob.data
    me.uv_layers.active = me.uv_layers["Bitmask"]
    prev_mode = ob.mode
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=1.55, island_margin=0.01)
    bpy.ops.object.mode_set(mode=prev_mode if prev_mode != 'EDIT' else 'OBJECT')


def ensure_mask_image(ob):
    name = ob.name + "_Bitmask"
    img = bpy.data.images.get(name)
    if img is None:
        img = bpy.data.images.new(name, MASK_SIZE, MASK_SIZE, alpha=False)
        img.generated_color = (0, 0, 0, 1)
        base = os.path.dirname(bpy.data.filepath) if bpy.data.filepath else ""
        if base:
            img.filepath_raw = os.path.join(base, name + ".png")
            img.file_format = 'PNG'
            img.save()
    return img


def build_graph(ob, base_img, over_img, mask_img):
    """Base Color = Mix(base@UV1, overlay@UV2, factor = mask@Bitmask)."""
    me = ob.data
    if not me.materials or me.materials[0] is None:
        mat = bpy.data.materials.new(ob.name + "_Bitmask")
        if me.materials: me.materials[0] = mat
        else: me.materials.append(mat)
    mat = me.materials[0]
    mat.use_nodes = True
    nt = mat.node_tree
    nodes, links = nt.nodes, nt.links

    bsdf = next((n for n in nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if bsdf is None:
        bsdf = nodes.new('ShaderNodeBsdfPrincipled')
        out = next((n for n in nodes if n.type == 'OUTPUT_MATERIAL'), None) or nodes.new('ShaderNodeOutputMaterial')
        links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    def named(kind, name, x, y):
        n = nodes.get(name)
        if n is None or n.bl_idname != kind:
            n = nodes.new(kind)
            n.name = name
        n.location = (bsdf.location.x + x, bsdf.location.y + y)
        return n

    uv1  = named('ShaderNodeUVMap',    "BMP_UV1",  -900,  60);  uv1.uv_map = "UV1"
    uv2  = named('ShaderNodeUVMap',    "BMP_UV2",  -900, -260); uv2.uv_map = "UV2"
    uvm  = named('ShaderNodeUVMap',    "BMP_UVM",  -900, -580); uvm.uv_map = "Bitmask"
    tex1 = named('ShaderNodeTexImage', "BMP_Base", -620,  120); tex1.image = base_img; tex1.label = "Base (UV1)"
    tex2 = named('ShaderNodeTexImage', "BMP_Over", -620, -200); tex2.image = over_img; tex2.label = "Overlay (UV2)"
    texm = named('ShaderNodeTexImage', "BMP_Mask", -620, -520); texm.image = mask_img; texm.label = "PAINT ME (bitmask)"
    mix  = named('ShaderNodeMix',      "BMP_Mix",  -240,  -40); mix.data_type = 'RGBA'; mix.label = "Base / Overlay"

    links.new(uv1.outputs["UV"], tex1.inputs["Vector"])
    links.new(uv2.outputs["UV"], tex2.inputs["Vector"])
    links.new(uvm.outputs["UV"], texm.inputs["Vector"])
    links.new(texm.outputs["Color"], mix.inputs["Factor"])
    links.new(tex1.outputs["Color"], mix.inputs["A"])
    links.new(tex2.outputs["Color"], mix.inputs["B"])
    for l in list(nt.links):
        if l.to_node == bsdf and l.to_socket.name == "Base Color":
            nt.links.remove(l)
    links.new(mix.outputs["Result"], bsdf.inputs["Base Color"])

    nodes.active = texm            # texture paint targets the mask
    for n in nodes: n.select = False
    texm.select = True
    return mat


# ---------------------------------------------------------------- operators
class BMP_OT_paint(bpy.types.Operator):
    """Build the UV1/UV2/Bitmask blend setup on the active object (if needed)
    and jump straight into Texture Paint on the 1024x1024 bitmask, with the
    viewport in Material Preview"""
    bl_idname = "paint.bmp_paint_bitmap"
    bl_label = "Paint Bitmap"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.object and context.object.type == 'MESH'

    def execute(self, context):
        scn = context.scene
        ob = context.object
        if scn.bmp_base is None or scn.bmp_over is None:
            self.report({'ERROR'}, "Assign both textures first (Base = UV1, Overlay = UV2)")
            return {'CANCELLED'}

        fresh = ensure_uv_layers(ob)
        if fresh:
            unwrap_bitmask(ob)
        mask = ensure_mask_image(ob)
        build_graph(ob, scn.bmp_base, scn.bmp_over, mask)

        # paint directly on the bitmask through the Bitmask UV
        ob.data.uv_layers.active = ob.data.uv_layers["Bitmask"]
        context.scene.tool_settings.image_paint.mode = 'MATERIAL'
        bpy.ops.object.mode_set(mode='TEXTURE_PAINT')
        for area in context.screen.areas:          # material preview shading
            if area.type == 'VIEW_3D':
                for space in area.spaces:
                    if space.type == 'VIEW_3D':
                        space.shading.type = 'MATERIAL'
        self.report({'INFO'}, "Painting %s (white = overlay)" % mask.name)
        return {'FINISHED'}


class BMP_OT_save(bpy.types.Operator):
    """Save the active object's bitmask image to disk"""
    bl_idname = "paint.bmp_save_bitmap"
    bl_label = "Save Bitmap"

    @classmethod
    def poll(cls, context):
        return (context.object and
                bpy.data.images.get(context.object.name + "_Bitmask") is not None)

    def execute(self, context):
        img = bpy.data.images[context.object.name + "_Bitmask"]
        if not img.filepath_raw:
            base = os.path.dirname(bpy.data.filepath) if bpy.data.filepath else ""
            if not base:
                self.report({'ERROR'}, "Save the .blend first so the mask has a home")
                return {'CANCELLED'}
            img.filepath_raw = os.path.join(base, img.name + ".png")
            img.file_format = 'PNG'
        img.save()
        self.report({'INFO'}, "Saved " + img.filepath_raw)
        return {'FINISHED'}


class BMP_OT_edit_uv(bpy.types.Operator):
    """Switch the active UV layer and hop into Edit Mode to tweak it
    (press the active layer's button again to hop back out)"""
    bl_idname = "paint.bmp_edit_uv"
    bl_label = "Edit UV"
    bl_options = {'REGISTER', 'UNDO'}

    layer: bpy.props.StringProperty()

    @classmethod
    def poll(cls, context):
        return context.object and context.object.type == 'MESH'

    def execute(self, context):
        ob = context.object
        me = ob.data
        lay = me.uv_layers.get(self.layer)
        if lay is None:
            self.report({'ERROR'}, "No '%s' layer yet - press Paint Bitmap first" % self.layer)
            return {'CANCELLED'}
        already = (me.uv_layers.active == lay)
        if already and ob.mode == 'EDIT':      # toggle off: back to object mode
            bpy.ops.object.mode_set(mode='OBJECT')
            return {'FINISHED'}
        me.uv_layers.active = lay
        if ob.mode != 'EDIT':
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.select_all(action='SELECT')
        self.report({'INFO'}, "Editing UV layer: " + self.layer)
        return {'FINISHED'}


# ------------------------------------------------------------------- panel
class BMP_PT_panel(bpy.types.Panel):
    bl_label = "Paint2Blend"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Paint2Blend"

    def draw(self, context):
        scn = context.scene
        col = self.layout.column()
        col.label(text="Base texture (UV1):")
        col.template_ID(scn, "bmp_base", open="image.open")
        col.label(text="Overlay texture (UV2):")
        col.template_ID(scn, "bmp_over", open="image.open")
        col.separator()
        col.operator("paint.bmp_paint_bitmap", icon='BRUSH_DATA')
        col.operator("paint.bmp_save_bitmap", icon='FILE_TICK')
        ob = context.object
        if ob and ob.type == 'MESH' and "Bitmask" in ob.data.uv_layers:
            col.label(text="Mask: %s_Bitmask (%dpx)" % (ob.name, MASK_SIZE), icon='IMAGE_DATA')
        # edit-UV toggles: press to hop into Edit Mode on that layer, press the
        # lit one again to hop back out.
        if ob and ob.type == 'MESH':
            col.separator()
            col.label(text="Edit UV:")
            row = col.row(align=True)
            active = ob.data.uv_layers.active.name if ob.data.uv_layers.active else ""
            for lay in ("UV1", "UV2", "Bitmask"):
                op = row.operator("paint.bmp_edit_uv", text=lay,
                                  depress=(active == lay and ob.mode == 'EDIT'))
                op.layer = lay


classes = (BMP_OT_paint, BMP_OT_save, BMP_OT_edit_uv, BMP_PT_panel)


def register():
    bpy.types.Scene.bmp_base = bpy.props.PointerProperty(
        name="Base", type=bpy.types.Image,
        description="Tiling base texture, sampled through UV1")
    bpy.types.Scene.bmp_over = bpy.props.PointerProperty(
        name="Overlay", type=bpy.types.Image,
        description="Tiling overlay texture, sampled through UV2 - painted in via the bitmask")
    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
    del bpy.types.Scene.bmp_base
    del bpy.types.Scene.bmp_over


if __name__ == "__main__":
    register()
