"""Renders the illustrated hand for each pose in poses.json with Blender.

    blender -b -P render_hands.py -- [pose ...]

For every pose it writes <pose>.png (transparent) and <pose>.json holding the
image size and each landmark's projected position, both in illustration units,
so the screenshot generator can overlay tracking dots exactly on the render.

The hand is a hybrid: fingers are tapered tubes swept along smooth splines
through their joints (no sausage bulges), while palm, thumb pad, thumb web and
forearm are metaballs so they blend organically. A voxel remesh fuses it all
into one surface, and a light smooth softens the seams.
"""
import json
import math
import os
import sys

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
U = 0.01                      # illustration unit → Blender unit
FRAME_W, FRAME_H = 270, 360   # render frame in illustration units
PX_PER_UNIT = 3               # output resolution multiplier

def srgb(hex_):
    """sRGB hex → linear RGB, since material colours are linear."""
    c = [int(hex_[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    return tuple(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in c)


SKIN = srgb("#d9a07c")
NAIL = srgb("#f0c9bb")
RIM = srgb("#6ae7c2")         # brand mint rim light

THRESHOLD = 0.6
STIFF = 4.0
# Distance (as a fraction of radius) at which one element's field hits the threshold.
SURF = math.sqrt(1 - (THRESHOLD / STIFF) ** (1 / 3))

FINGERS_BASE = {5: 11.8, 9: 12.2, 13: 11.3, 17: 10.0}
FINGERS = {  # landmark chain, surface radius at each landmark
    "thumb": ([1, 2, 3, 4], [14.5, 13, 11.8, 10.6]),
    "index": ([5, 6, 7, 8], [11.8, 10.7, 9.8, 9.0]),
    "middle": ([9, 10, 11, 12], [12.2, 11.1, 10.1, 9.3]),
    "ring": ([13, 14, 15, 16], [11.3, 10.3, 9.5, 8.8]),
    "pinky": ([17, 18, 19, 20], [10.0, 9.1, 8.4, 7.8]),
}


def to_world(p):
    x, y, z = p
    return Vector((x * U, -y * U, z * U))


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 96
    scene.cycles.use_denoising = True
    scene.render.film_transparent = True
    scene.render.resolution_x = FRAME_W * PX_PER_UNIT
    scene.render.resolution_y = FRAME_H * PX_PER_UNIT
    scene.render.resolution_percentage = 100
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


def skin_material():
    mat = bpy.data.materials.new("skin")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*SKIN, 1)
    bsdf.inputs["Roughness"].default_value = 0.55
    for name, val in (("Subsurface Weight", 0.35), ("Subsurface Scale", 0.04)):
        if name in bsdf.inputs:
            bsdf.inputs[name].default_value = val
    if "Subsurface Radius" in bsdf.inputs:
        bsdf.inputs["Subsurface Radius"].default_value = (1.0, 0.45, 0.3)
    return mat


def nail_material():
    mat = bpy.data.materials.new("nail")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*NAIL, 1)
    bsdf.inputs["Roughness"].default_value = 0.25
    return mat


def add_capsule(mb, a, b, r):
    a, b = to_world(a), to_world(b)
    d = b - a
    el = mb.elements.new(type="CAPSULE")
    el.co = (a + b) / 2
    el.size_x = d.length / 2
    el.radius = r * U / SURF
    el.stiffness = STIFF
    el.rotation = Vector((1, 0, 0)).rotation_difference(d.normalized())
    return el


def add_ellipsoid(mb, center, axis_dir, semi):
    """semi = (along axis_dir, across, depth) surface semi-axes, illustration units."""
    el = mb.elements.new(type="ELLIPSOID")
    el.co = to_world(center)
    el.radius = max(semi) * U / SURF
    el.size_x, el.size_y, el.size_z = (s / max(semi) for s in semi)
    el.stiffness = STIFF
    el.rotation = Vector((1, 0, 0)).rotation_difference(axis_dir.normalized())
    return el


def build_palm(P):
    """Metaball volumes for everything that should blend softly."""
    mb = bpy.data.metaballs.new("palm")
    mb.resolution = mb.render_resolution = 0.008
    mb.threshold = THRESHOLD
    obj = bpy.data.objects.new("palm", mb)
    bpy.context.collection.objects.link(obj)

    knuckles = (P[5] + P[9] + P[13] + P[17]) / 4
    up = to_world(knuckles) - to_world(P[0])
    palm_c = P[0] * 0.42 + knuckles * 0.58
    add_ellipsoid(mb, palm_c, up, (64, 47, 13))
    # finger bases, so each finger roots into a soft mound
    for i in (5, 9, 13, 17):
        add_capsule(mb, P[i] + (P[0] - P[i]).normalized() * 18, P[i], FINGERS_BASE[i] + 1.5)
    # thumb: metacarpal, pad (thenar) and the web to the index finger
    add_capsule(mb, P[1], P[2], 13.5)
    thenar_c = P[1] * 0.55 + P[0] * 0.2 + P[5] * 0.25
    add_ellipsoid(mb, thenar_c, to_world(P[2]) - to_world(P[1]), (32, 21, 14))
    web_c = P[2] * 0.5 + P[5] * 0.5
    add_ellipsoid(mb, web_c, to_world(P[5]) - to_world(P[2]), (22, 9, 6))
    hypo_c = P[0] * 0.45 + P[17] * 0.55 + Vector((2, 0, -1))
    add_ellipsoid(mb, hypo_c, up, (38, 15, 11))
    # wrist and forearm, running off the bottom of the frame
    down = (P[0] - knuckles).normalized()
    add_capsule(mb, P[0] - down * 10, P[0] + down * 170, 27)
    return obj


def build_finger(P, chain, radii):
    """Tapered tube along a smooth spline from inside the palm to the tip."""
    pts = [P[i] for i in chain]
    tip_dir = (pts[-1] - pts[-2]).normalized()
    r_tip = radii[-1]
    base = pts[0] + (pts[0] - pts[1]).normalized() * 10       # start inside the palm
    end = pts[-1] - tip_dir * r_tip                           # fingertip sphere centre
    path = [base] + pts[:-1] + [end]
    rads = [radii[0]] + radii[:-1] + [r_tip]

    cu = bpy.data.curves.new("finger", "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = U
    cu.bevel_resolution = 8
    cu.resolution_u = 16
    cu.use_fill_caps = True
    sp = cu.splines.new("BEZIER")
    sp.bezier_points.add(len(path) - 1)
    for bp, p, r in zip(sp.bezier_points, path, rads):
        bp.co = to_world(p)
        bp.handle_left_type = bp.handle_right_type = "AUTO"
        bp.radius = r
    obj = bpy.data.objects.new("finger", cu)
    bpy.context.collection.objects.link(obj)

    bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24, radius=r_tip * U,
                                         location=to_world(end))
    return [obj, bpy.context.active_object]


def build_hand(pts):
    P = [Vector(p) for p in pts]
    parts = [build_palm(P)]
    for name, (chain, radii) in FINGERS.items():
        if name == "thumb":
            parts += build_finger(P, chain[1:], radii[1:])     # metacarpal is in the palm
        else:
            parts += build_finger(P, chain, radii)

    # convert everything to mesh and fuse
    bpy.ops.object.select_all(action="DESELECT")
    for o in parts:
        o.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.object.convert(target="MESH")
    bpy.ops.object.join()
    hand = bpy.context.active_object
    hand.name = "hand"

    remesh = hand.modifiers.new("fuse", "REMESH")
    remesh.mode = "VOXEL"
    remesh.voxel_size = 0.7 * U
    smooth = hand.modifiers.new("soften", "SMOOTH")
    smooth.factor = 0.6
    smooth.iterations = 12
    bpy.ops.object.modifier_apply(modifier="fuse")
    bpy.ops.object.modifier_apply(modifier="soften")
    bpy.ops.object.shade_smooth()
    hand.data.materials.clear()
    hand.data.materials.append(skin_material())
    return hand


def add_nails(pts, view_dir):
    """Flattened ellipsoids on the back of each distal segment that faces the
    camera; on a palm-facing hand the others would only peek out as slivers."""
    mat = nail_material()
    P = [to_world(p) for p in pts]
    lateral = (P[17] - P[5]).normalized()
    for name, (chain, radii) in FINGERS.items():
        if name == "thumb":
            continue
        a, b = P[chain[2]], P[chain[3]]
        bone = (b - a).normalized()
        dorsal = bone.cross(lateral).normalized()
        if dorsal.dot(view_dir) < 0.25:
            continue
        r = radii[3] * U
        bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=1)
        nail = bpy.context.active_object
        nail.scale = ((b - a).length * 0.42, r * 0.72, r * 0.22)
        # orient: local X along the bone, local Z along dorsal
        y_axis = dorsal.cross(bone).normalized()
        from mathutils import Matrix
        rot = Matrix((bone, y_axis, dorsal)).transposed().to_4x4()
        nail.rotation_euler = rot.to_euler()
        nail.location = a + (b - a) * 0.62 + dorsal * r * 0.82
        nail.data.materials.append(mat)
        bpy.ops.object.shade_smooth()


def look_at(loc, target, world_up=Vector((0, 1, 0))):
    """Rotation pointing local -Z at target with local Y as close to world_up as possible."""
    from mathutils import Matrix
    fwd = (target - Vector(loc)).normalized()
    right = fwd.cross(world_up).normalized()
    up = right.cross(fwd)
    return Matrix((right, up, -fwd)).transposed().to_euler()


def add_light(name, loc, target, energy, size, color=(1, 1, 1)):
    data = bpy.data.lights.new(name, type="AREA")
    data.energy = energy
    data.size = size
    data.color = color
    obj = bpy.data.objects.new(name, data)
    obj.location = loc
    bpy.context.collection.objects.link(obj)
    obj.rotation_euler = look_at(loc, target)


def setup_camera_and_lights(pts, yaw_deg, pitch_deg):
    P = [to_world(p) for p in pts]
    center = Vector((FRAME_W / 2 * U, -FRAME_H / 2 * U, 0.2))
    # frame centred on the hand's bounding box, not the whole frame
    xs = [p.x for p in P]; ys = [p.y for p in P]
    center = Vector(((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2 - 0.06, 0.2))

    cam_data = bpy.data.cameras.new("cam")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = FRAME_H * U
    cam = bpy.data.objects.new("cam", cam_data)
    bpy.context.collection.objects.link(cam)
    yaw, pitch, dist = math.radians(yaw_deg), math.radians(pitch_deg), 10
    cam.location = center + Vector((math.sin(yaw) * math.cos(pitch) * dist,
                                    math.sin(pitch) * dist,
                                    math.cos(yaw) * math.cos(pitch) * dist))
    cam.rotation_euler = look_at(cam.location, center)
    bpy.context.scene.camera = cam

    add_light("key", center + Vector((-3.0, 3.0, 5.0)), center, 400, 3.0, (1.0, 0.96, 0.9))
    add_light("fill", center + Vector((4.0, -0.5, 3.0)), center, 110, 4.0, (0.85, 0.92, 1.0))
    add_light("rim", center + Vector((1.5, 2.5, -4.0)), center, 500, 2.5, RIM)
    return cam


def render_pose(name, pts, yaw=-16, pitch=6):
    scene = reset_scene()
    build_hand(pts)
    cam = setup_camera_and_lights(pts, yaw, pitch)
    view_dir = (cam.location - Vector((0, 0, 0))).normalized()
    add_nails(pts, view_dir)
    scene.render.filepath = os.path.join(HERE, f"{name}.png")
    bpy.ops.render.render(write_still=True)

    projected = []
    for p in pts:
        u, v, _ = world_to_camera_view(scene, cam, to_world(p))
        projected.append([round(u * FRAME_W, 2), round((1 - v) * FRAME_H, 2)])
    with open(os.path.join(HERE, f"{name}.json"), "w") as f:
        json.dump({"w": FRAME_W, "h": FRAME_H, "points": projected}, f)
    print(f"rendered {name}")


if __name__ == "__main__":
    with open(os.path.join(HERE, "poses.json")) as f:
        poses = {k: v for k, v in json.load(f).items() if not k.startswith("_")}
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    for name in argv or poses:
        render_pose(name, poses[name])
