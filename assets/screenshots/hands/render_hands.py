"""Renders the illustrated hand for each pose with Blender, using a rigged
human from MPFB (MakeHuman's Blender extension; generated content is CC0).

    blender -b -P render_hands.py -- [open] [pinch]

Requires the MPFB extension (extensions.blender.org/add-ons/mpfb). For every
pose it writes <pose>.png (transparent) and <pose>.json holding the frame size
and the 21 MediaPipe-style landmarks projected into it, both in illustration
units, so the screenshot generator can overlay tracking dots on the fingertips.

The left hand is used: seen palm-on, its thumb is on the left, which matches
the mirrored preview of a user's right hand. The arm stays in its rest pose and
the camera is aimed at the palm instead; everything but hand and forearm is
masked away. The pinch is solved with IK: index and thumb tips reach for a
shared point in front of the palm.
"""
import json
import math
import os
import sys

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Matrix, Vector

from bl_ext.user_default.mpfb.services.humanservice import HumanService

HERE = os.path.dirname(os.path.abspath(__file__))
MPFB_TEXTURES = os.path.join(os.path.dirname(sys.modules[HumanService.__module__].__file__), "..", "data", "textures")

FRAME_W, FRAME_H = 270, 360   # render frame in illustration units
HAND_UNITS = 232              # wrist-to-middle-fingertip length in illustration units
PX_PER_UNIT = 3
SIDE = ".L"


def srgb(hex_):
    """sRGB hex → linear RGB, since material colours are linear."""
    c = [int(hex_[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    return tuple(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in c)


SKIN = srgb("#d49776")
SKIN_FLUSH = srgb("#cf7c63")   # knuckles, fingertips: where skin reads redder
NAIL = srgb("#e2aa9a")
RIM = srgb("#6ae7c2")          # brand mint rim light

# MediaPipe landmark order → (bone, end). 0 wrist; thumb 1-4; index 5-8; ... pinky 17-20.
LANDMARKS = [("wrist", "head")]
for f in range(1, 6):
    LANDMARKS += [(f"finger{f}-1", "head"), (f"finger{f}-2", "head"), (f"finger{f}-3", "head"), (f"finger{f}-3", "tip")]


# ---------------------------------------------------------------- scene
def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 128
    scene.cycles.use_denoising = True
    scene.render.film_transparent = True
    scene.render.resolution_x = FRAME_W * PX_PER_UNIT
    scene.render.resolution_y = FRAME_H * PX_PER_UNIT
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.view_settings.view_transform = "Standard"
    world = bpy.data.worlds.new("world")
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.05, 0.16, 0.12, 1)
    bg.inputs["Strength"].default_value = 0.35
    scene.world = world
    return scene


def build_human():
    body = HumanService.create_human()
    rig = HumanService.add_builtin_rig(body, "default")

    # keep only the forearm and hand
    bones = ["lowerarm01", "lowerarm02", "wrist"] + [f"metacarpal{i}" for i in range(1, 5)] \
        + [f"finger{f}-{j}" for f in range(1, 6) for j in range(1, 4)]
    wanted = {body.vertex_groups[b + SIDE].index for b in bones if b + SIDE in body.vertex_groups}
    keep = body.vertex_groups.new(name="keep")
    keep.add([v.index for v in body.data.vertices
              if any(g.group in wanted and g.weight > 0.05 for g in v.groups)], 1.0, "REPLACE")
    mask = body.modifiers.new("keep hand", "MASK")
    mask.vertex_group = keep.name
    sub = body.modifiers.new("smooth", "SUBSURF")
    sub.levels, sub.render_levels = 2, 3
    for poly in body.data.polygons:
        poly.use_smooth = True
    return body, rig


class HandFrame:
    """Rest-pose hand axes: up (wrist → knuckles), lat (index → pinky), n (palm normal)."""

    def __init__(self, rig):
        self.rig = rig
        self.wrist = self.head("wrist")
        self.up = (self.head("finger3-1") - self.wrist).normalized()
        self.lat = (self.head("finger5-1") - self.head("finger2-1")).normalized()
        n = self.up.cross(self.lat).normalized()
        curl = self.tail("finger3-3") - self.head("finger3-1")
        curl -= self.up * curl.dot(self.up)
        self.n = n if n.dot(curl) > 0 else -n
        self.length = (self.tail("finger3-3") - self.wrist).length   # metres

    def head(self, b):
        return self.rig.matrix_world @ self.rig.data.bones[b + SIDE].head_local

    def tail(self, b):
        return self.rig.matrix_world @ self.rig.data.bones[b + SIDE].tail_local


# ---------------------------------------------------------------- poses
def bend(rig, bone, x=0.0, z=0.0):
    """Local rotation in degrees: +x curls toward the palm, z spreads sideways."""
    pb = rig.pose.bones[bone + SIDE]
    pb.rotation_mode = "XYZ"
    pb.rotation_euler = (math.radians(x), 0, math.radians(z))


def pose_open(rig, hf):
    # relaxed: a slight natural curl and spread
    for f, spread in ((2, 5), (3, 0), (4, -4), (5, -9)):
        bend(rig, f"finger{f}-1", 4, spread)
        bend(rig, f"finger{f}-2", 5)
        bend(rig, f"finger{f}-3", 4)


def ik_to(rig, bone, target, chain):
    c = rig.pose.bones[bone + SIDE].constraints.new("IK")
    c.target = target
    c.chain_count = chain
    c.use_tail = True
    c.iterations = 800


def pose_pinch(rig, hf):
    # middle, ring and pinky stay up, relaxing slightly more toward the pinky
    for f, curl, spread in ((3, 4, 1), (4, 6, -1), (5, 9, -4)):
        bend(rig, f"finger{f}-1", curl, spread)
        bend(rig, f"finger{f}-2", curl + 2)
        bend(rig, f"finger{f}-3", curl)
    index_len = (hf.tail("finger2-3") - hf.head("finger2-1")).length
    meet = hf.head("finger2-1") + hf.n * (0.5 * index_len) - hf.lat * (0.2 * index_len) - hf.up * (0.1 * index_len)
    # both tips reach for the same point: bone tails sit at the fingertips, so
    # this presses the pads together
    for name in ("index", "thumb"):
        e = bpy.data.objects.new(f"target_{name}", None)
        e.location = meet
        bpy.context.collection.objects.link(e)
        ik_to(rig, "finger2-3" if name == "index" else "finger1-3", e, 3)


POSES = {"open": pose_open, "pinch": pose_pinch}


# ---------------------------------------------------------------- materials
def skin_material(k):
    """Skin: subsurface, redder on convex areas, darker in creases, fine bump,
    nails from MPFB's UV nail mask. k scales distances to the model's size."""
    mat = bpy.data.materials.new("skin")
    mat.use_nodes = True
    nt = mat.node_tree
    N, L = nt.nodes, nt.links
    bsdf = N["Principled BSDF"]

    geo = N.new("ShaderNodeNewGeometry")
    flush_ramp = N.new("ShaderNodeValToRGB")
    flush_ramp.color_ramp.elements[0].position = 0.49
    flush_ramp.color_ramp.elements[1].position = 0.55
    L.new(geo.outputs["Pointiness"], flush_ramp.inputs["Fac"])
    flush = N.new("ShaderNodeMix")
    flush.data_type = "RGBA"
    flush.inputs["A"].default_value = (*SKIN, 1)
    flush.inputs["B"].default_value = (*SKIN_FLUSH, 1)
    L.new(flush_ramp.outputs["Color"], flush.inputs["Factor"])

    nails_img = N.new("ShaderNodeTexImage")
    nails_img.image = bpy.data.images.load(os.path.join(MPFB_TEXTURES, "mpfb_fingernails.jpg"))
    nails_img.image.colorspace_settings.name = "Non-Color"
    uv = N.new("ShaderNodeUVMap")
    L.new(uv.outputs["UV"], nails_img.inputs["Vector"])
    nails = N.new("ShaderNodeMix")
    nails.data_type = "RGBA"
    nails.inputs["B"].default_value = (*NAIL, 1)
    L.new(flush.outputs["Result"], nails.inputs["A"])
    L.new(nails_img.outputs["Color"], nails.inputs["Factor"])
    rough = N.new("ShaderNodeMapRange")                 # nails glossier than skin
    rough.inputs["To Min"].default_value = 0.5
    rough.inputs["To Max"].default_value = 0.28
    L.new(nails_img.outputs["Color"], rough.inputs["Value"])
    L.new(rough.outputs["Result"], bsdf.inputs["Roughness"])

    ao = N.new("ShaderNodeAmbientOcclusion")
    ao.inputs["Distance"].default_value = 0.05 * k
    ao_ramp = N.new("ShaderNodeMapRange")
    ao_ramp.inputs["To Min"].default_value = 0.72
    L.new(ao.outputs["AO"], ao_ramp.inputs["Value"])
    shade = N.new("ShaderNodeMix")
    shade.data_type = "RGBA"
    shade.blend_type = "MULTIPLY"
    shade.inputs["Factor"].default_value = 1.0
    L.new(nails.outputs["Result"], shade.inputs["A"])
    L.new(ao_ramp.outputs["Result"], shade.inputs["B"])
    L.new(shade.outputs["Result"], bsdf.inputs["Base Color"])

    coord = N.new("ShaderNodeTexCoord")
    noise = N.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 220 / k
    noise.inputs["Detail"].default_value = 6
    L.new(coord.outputs["Object"], noise.inputs["Vector"])
    bump = N.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.08
    bump.inputs["Distance"].default_value = 0.002 * k
    L.new(noise.outputs["Fac"], bump.inputs["Height"])
    L.new(bump.outputs["Normal"], bsdf.inputs["Normal"])

    bsdf.inputs["Subsurface Weight"].default_value = 0.5
    bsdf.inputs["Subsurface Radius"].default_value = (1.0, 0.38, 0.22)
    bsdf.inputs["Subsurface Scale"].default_value = 0.025 * k
    return mat


# ---------------------------------------------------------------- camera, lights
def look_at(loc, target, world_up):
    fwd = (target - loc).normalized()
    right = fwd.cross(world_up).normalized()
    up = right.cross(fwd)
    return Matrix((right, up, -fwd)).transposed().to_euler(), right, up, fwd


def add_light(name, loc, target, up, energy, size, color):
    data = bpy.data.lights.new(name, type="AREA")
    data.energy, data.size, data.color = energy, size, color
    obj = bpy.data.objects.new(name, data)
    obj.location = loc
    obj.rotation_euler = look_at(loc, target, up)[0]
    bpy.context.collection.objects.link(obj)


def setup_camera_and_lights(hf, yaw_deg, pitch_deg):
    k = hf.length / 2.32            # the old scene's hand was ~2.32 units long
    tip_top = hf.wrist + hf.up * hf.length
    center = (hf.wrist + tip_top) / 2 - hf.up * (hf.length * 0.02)

    yaw, pitch = math.radians(yaw_deg), math.radians(pitch_deg)
    side = hf.up.cross(hf.n).normalized()          # image-right when facing the palm
    view = (hf.n * math.cos(yaw) * math.cos(pitch) + side * math.sin(yaw) * math.cos(pitch)
            + hf.up * math.sin(pitch)).normalized()
    cam_data = bpy.data.cameras.new("cam")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = hf.length * FRAME_H / HAND_UNITS
    cam = bpy.data.objects.new("cam", cam_data)
    cam.location = center + view * 10 * k
    rot, right, up, fwd = look_at(cam.location, center, hf.up)
    cam.rotation_euler = rot
    bpy.context.collection.objects.link(cam)
    bpy.context.scene.camera = cam

    # same rig as before, expressed in the camera's frame and scaled to the model
    def at(x, y, z):
        return center + (right * x + up * y - fwd * z) * k
    add_light("key", at(-3.0, 3.0, 5.0), center, up, 470 * k * k, 2.5 * k, (1.0, 0.96, 0.9))
    add_light("fill", at(4.0, -0.5, 3.0), center, up, 80 * k * k, 4.0 * k, (0.85, 0.92, 1.0))
    add_light("rim", at(1.5, 2.5, -4.0), center, up, 300 * k * k, 3.0 * k, RIM)
    return cam, k


# ---------------------------------------------------------------- output
def landmark_positions(rig):
    """World positions of the 21 landmarks from the posed rig. Fingertip
    landmarks sit a little past the last bone's tail, at the tip surface."""
    out = []
    for bone, end in LANDMARKS:
        pb = rig.pose.bones[bone + SIDE]
        head, tail = rig.matrix_world @ pb.head, rig.matrix_world @ pb.tail
        out.append(head if end == "head" else tail + (tail - head) * 0.3)
    return out


def render_pose(name, yaw=-16, pitch=6):
    scene = reset_scene()
    body, rig = build_human()
    hf = HandFrame(rig)
    POSES[name](rig, hf)
    bpy.context.view_layer.update()
    cam, k = setup_camera_and_lights(hf, yaw, pitch)
    body.data.materials.clear()
    body.data.materials.append(skin_material(k))
    for poly in body.data.polygons:
        poly.material_index = 0

    scene.render.filepath = os.path.join(HERE, f"{name}.png")
    bpy.ops.render.render(write_still=True)

    bpy.context.view_layer.update()
    projected = []
    for p in landmark_positions(rig):
        u, v, _ = world_to_camera_view(scene, cam, p)
        projected.append([round(u * FRAME_W, 2), round((1 - v) * FRAME_H, 2)])
    with open(os.path.join(HERE, f"{name}.json"), "w") as f:
        json.dump({"w": FRAME_W, "h": FRAME_H, "points": projected}, f)
    print(f"rendered {name}")


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    for pose in argv or POSES:
        render_pose(pose)
