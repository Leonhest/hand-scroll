"""Renders the illustrated hand for each pose in poses.json with Blender.

    blender -b -P render_hands.py -- [pose ...]

For every pose it writes <pose>.png (transparent) and <pose>.json holding the
image size and each landmark's projected position, both in illustration units,
so the screenshot generator can overlay tracking dots exactly on the render.

The hand is a hybrid: fingers are tapered tubes swept along smooth splines
through their joints (no sausage bulges), while palm, thumb pad, thumb web and
thumb-pad metaballs blend organically. A voxel remesh fuses it all into one
surface, a light smooth softens the seams, and a crease map (palm lines and
finger joint creases, drawn from the landmarks) is displaced into the palm side.
"""
import json
import math
import os
import subprocess
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


SKIN = srgb("#d49776")
SKIN_FLUSH = srgb("#cf7c63")   # knuckles, fingertips: where skin reads redder
NAIL = srgb("#dea08e")
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
    """Skin: subsurface, redder on convex areas, darker in creases, fine bump."""
    mat = bpy.data.materials.new("skin")
    mat.use_nodes = True
    nt = mat.node_tree
    N, L = nt.nodes, nt.links
    bsdf = N["Principled BSDF"]

    geo = N.new("ShaderNodeNewGeometry")
    flush_ramp = N.new("ShaderNodeValToRGB")          # pointiness → redness
    flush_ramp.color_ramp.elements[0].position = 0.49
    flush_ramp.color_ramp.elements[1].position = 0.54
    L.new(geo.outputs["Pointiness"], flush_ramp.inputs["Fac"])
    flush = N.new("ShaderNodeMix")
    flush.data_type = "RGBA"
    flush.inputs["A"].default_value = (*SKIN, 1)
    flush.inputs["B"].default_value = (*SKIN_FLUSH, 1)
    L.new(flush_ramp.outputs["Color"], flush.inputs["Factor"])

    ao = N.new("ShaderNodeAmbientOcclusion")          # creases a touch darker
    ao.inputs["Distance"].default_value = 0.05
    ao_ramp = N.new("ShaderNodeMapRange")
    ao_ramp.inputs["To Min"].default_value = 0.72
    L.new(ao.outputs["AO"], ao_ramp.inputs["Value"])
    shade = N.new("ShaderNodeMix")
    shade.data_type = "RGBA"
    shade.blend_type = "MULTIPLY"
    shade.inputs["Factor"].default_value = 1.0
    L.new(flush.outputs["Result"], shade.inputs["A"])
    L.new(ao_ramp.outputs["Result"], shade.inputs["B"])
    L.new(shade.outputs["Result"], bsdf.inputs["Base Color"])

    coord = N.new("ShaderNodeTexCoord")               # skin micro-texture
    noise = N.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 220
    noise.inputs["Detail"].default_value = 6
    L.new(coord.outputs["Object"], noise.inputs["Vector"])
    bump = N.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.08
    bump.inputs["Distance"].default_value = 0.002
    L.new(noise.outputs["Fac"], bump.inputs["Height"])
    L.new(bump.outputs["Normal"], bsdf.inputs["Normal"])

    bsdf.inputs["Roughness"].default_value = 0.5
    bsdf.inputs["Subsurface Weight"].default_value = 0.5
    bsdf.inputs["Subsurface Radius"].default_value = (1.0, 0.38, 0.22)
    bsdf.inputs["Subsurface Scale"].default_value = 0.025
    return mat


def nail_material():
    mat = bpy.data.materials.new("nail")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*NAIL, 1)
    bsdf.inputs["Roughness"].default_value = 0.32
    bsdf.inputs["Subsurface Weight"].default_value = 0.3
    bsdf.inputs["Subsurface Scale"].default_value = 0.01
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
    return obj


def tube(path, rads, cap_sphere=None, bevel_res=8):
    """Tapered tube along a smooth spline; optional sphere (centre, radius) cap."""
    cu = bpy.data.curves.new("tube", "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = U
    cu.bevel_resolution = bevel_res
    cu.resolution_u = 16
    cu.use_fill_caps = True
    sp = cu.splines.new("BEZIER")
    sp.bezier_points.add(len(path) - 1)
    for bp, p, r in zip(sp.bezier_points, path, rads):
        bp.co = to_world(p)
        bp.handle_left_type = bp.handle_right_type = "AUTO"
        bp.radius = r
    obj = bpy.data.objects.new("tube", cu)
    bpy.context.collection.objects.link(obj)
    out = [obj]
    if cap_sphere:
        c, r = cap_sphere
        bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24, radius=r * U, location=to_world(c))
        out.append(bpy.context.active_object)
    return out


def build_finger(P, chain, radii):
    """From inside the palm to the tip. Joints are pinched in slightly and each
    segment swells a little between them, like the pads of a real finger."""
    pts = [P[i] for i in chain]
    tip_dir = (pts[-1] - pts[-2]).normalized()
    r_tip = radii[-1]
    base = pts[0] + (pts[0] - pts[1]).normalized() * 10
    end = pts[-1] - tip_dir * r_tip
    joints = pts[:-1] + [end]
    jr = radii[:-1] + [r_tip]
    path, rads = [base], [radii[0]]
    for k in range(len(joints) - 1):
        a, b, ra, rb = joints[k], joints[k + 1], jr[k], jr[k + 1]
        path += [a, (a + b) / 2]
        rads += [ra * (0.97 if k else 1.0), (ra + rb) / 2 * 1.05]
    path.append(end)
    rads.append(r_tip)
    return tube(path, rads, cap_sphere=(end, r_tip))


def build_forearm(P):
    """Narrows at the wrist, then widens into the forearm off the frame."""
    knuckles = (P[5] + P[9] + P[13] + P[17]) / 4
    down = (P[0] - knuckles).normalized()
    # starts inside the palm heel, capped round, so no flat end shows
    start = P[0] - down * 34
    path = [start, P[0] - down * 8, P[0] + down * 22, P[0] + down * 90, P[0] + down * 175]
    rads = [17, 26, 26, 30, 32]
    parts = tube(path, rads, cap_sphere=(start, 17), bevel_res=16)
    # wrists are wider than deep: flatten toward the palm plane (z = 0)
    for o in parts:
        if o.type == "CURVE":
            o.scale.z = 0.55
        else:
            o.scale = (1, 1, 0.55)
            o.location.z *= 0.55
    return parts


def build_hand(pts):
    P = [Vector(p) for p in pts]
    parts = [build_palm(P)] + build_forearm(P)
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
    remesh.voxel_size = 0.55 * U
    smooth = hand.modifiers.new("soften", "SMOOTH")
    smooth.factor = 0.6
    smooth.iterations = 12
    bpy.ops.object.modifier_apply(modifier="fuse")
    bpy.ops.object.modifier_apply(modifier="soften")
    add_creases(hand, pts)
    bpy.ops.object.shade_smooth()
    hand.data.materials.clear()
    hand.data.materials.append(skin_material())
    return hand


# ---------------- creases
# The crease map is drawn in illustration units over this square, then
# projected straight down the view axis onto the hand.
CREASE_BOX = (-45, 0, 360)          # x0, y0, size
CREASE_PX = 1800


def crease_svg(pts):
    """Palm lines and finger joint creases, positioned from the landmarks."""
    P = [Vector(p[:2]) for p in pts]
    lines = []

    def q(a, c, b, w):
        """Palm line that thins toward both ends (three nested dash spans)."""
        d = f"M{a.x:.1f} {a.y:.1f} Q{c.x:.1f} {c.y:.1f} {b.x:.1f} {b.y:.1f}"
        for frac, width in ((1.0, w * 0.45), (0.75, w * 0.75), (0.45, w)):
            gap = (1 - frac) / 2 * 100
            lines.append(f'<path d="{d}" pathLength="100" stroke-width="{width:.2f}" '
                         f'stroke-dasharray="0 {gap:.1f} {frac*100:.1f} 100"/>')

    V = lambda x, y: Vector((x, y))
    # heart line: from under the pinky knuckle, curving up between index and middle
    q(P[17] + V(12, 22), P[13] + V(-4, 40), (P[5] + P[9]) / 2 + V(2, 12), 3.2)
    # head line: from the thumb-index web, drifting down across the palm
    q(P[5] + V(-10, 30), (P[9] + P[13]) / 2 + V(-10, 52), P[17] + V(-2, 62), 3.0)
    # life line: arcs around the thumb pad down to the wrist
    q(P[5] + V(-8, 32), P[1] + V(40, -34), P[0] + V(-14, -14), 3.2)
    # wrist crease
    q(P[0] + V(-24, -4), P[0] + V(0, 2), P[0] + V(24, -4), 2.2)

    def cross(center, bone, half, w):
        n = Vector((-bone.y, bone.x)).normalized() * half
        a, b = center - n, center + n
        lines.append(f'<line x1="{a.x:.1f}" y1="{a.y:.1f}" x2="{b.x:.1f}" y2="{b.y:.1f}" stroke-width="{w}"/>')

    for name, (chain, radii) in FINGERS.items():
        mcp, pip, dip, tip = (P[i] for i in chain)
        if name == "thumb":
            cross(pip, (dip - pip).normalized(), radii[1] * 0.55, 1.8)       # thumb MCP
            cross(dip, (tip - dip).normalized(), radii[2] * 0.55, 1.8)       # thumb IP
            continue
        bone = (pip - mcp).normalized()
        cross(mcp + (pip - mcp) * 0.3, bone, radii[0] * 0.6, 2.0)           # finger base
        for off in (-1.6, 1.6):                                              # PIP: double crease
            cross(pip + bone * off, bone, radii[1] * 0.55, 1.4)
        cross(dip, (tip - dip).normalized(), radii[2] * 0.5, 1.4)           # DIP

    x0, y0, size = CREASE_BOX
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x0} {y0} {size} {size}" '
            f'width="{CREASE_PX}" height="{CREASE_PX}">'
            f'<defs><filter id="b"><feGaussianBlur stdDeviation="1.3"/></filter></defs>'
            f'<rect x="{x0}" y="{y0}" width="{size}" height="{size}" fill="#000"/>'
            f'<g fill="none" stroke="#fff" stroke-linecap="round" filter="url(#b)">{"".join(lines)}</g></svg>')


def add_creases(hand, pts):
    cache = os.path.join(HERE, ".cache")
    os.makedirs(cache, exist_ok=True)
    svg, png = os.path.join(cache, "creases.svg"), os.path.join(cache, "creases.png")
    with open(svg, "w") as f:
        f.write(crease_svg(pts))
    subprocess.run(["rsvg-convert", svg, "-o", png], check=True)

    tex = bpy.data.textures.new("creases", "IMAGE")
    tex.image = bpy.data.images.load(png, check_existing=False)
    tex.extension = "EXTEND"
    x0, y0, size = CREASE_BOX
    proj = bpy.data.objects.new("crease_projector", None)
    proj.location = ((x0 + size / 2) * U, -(y0 + size / 2) * U, 0)
    proj.scale = (size / 2 * U, size / 2 * U, 1)
    bpy.context.collection.objects.link(proj)

    # Only the palm-side layer: fingers curled toward the camera (thumb, a
    # pinching index) sit above the palm in depth and must not pick up its lines.
    vg = hand.vertex_groups.new(name="creasable")
    buckets = {}
    for v in hand.data.vertices:
        depth_w = max(0.0, min(1.0, (34 - v.co.z / U) / 10))
        facing_w = max(0.0, min(1.0, (v.normal.z - 0.4) / 0.4))
        w = round(depth_w * facing_w, 1)
        if w:
            buckets.setdefault(w, []).append(v.index)
    for w, idx in buckets.items():
        vg.add(idx, w, "REPLACE")

    disp = hand.modifiers.new("creases", "DISPLACE")
    disp.texture = tex
    disp.texture_coords = "OBJECT"
    disp.texture_coords_object = proj
    disp.mid_level = 0.0
    disp.strength = -0.9 * U
    disp.vertex_group = vg.name
    soften = hand.modifiers.new("crease_soften", "SMOOTH")
    soften.factor = 0.5
    soften.iterations = 2
    bpy.ops.object.modifier_apply(modifier="creases")
    bpy.ops.object.modifier_apply(modifier="crease_soften")


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
        nail.scale = ((b - a).length * 0.36, r * 0.68, r * 0.2)
        # orient: local X along the bone, local Z along dorsal
        y_axis = dorsal.cross(bone).normalized()
        from mathutils import Matrix
        rot = Matrix((bone, y_axis, dorsal)).transposed().to_4x4()
        nail.rotation_euler = rot.to_euler()
        nail.location = a + (b - a) * 0.55 + dorsal * r * 0.86
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

    add_light("key", center + Vector((-3.0, 3.0, 5.0)), center, 470, 2.5, (1.0, 0.96, 0.9))
    add_light("fill", center + Vector((4.0, -0.5, 3.0)), center, 80, 4.0, (0.85, 0.92, 1.0))
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
