"""CDUTdino guide. Run with Blender --background --python this_file.
Editable smooth meshes and named walk pivots; no downloaded model or baked photo.
Blender Z up, forward +X. glTF export uses its standard Y-up conversion.

Modelling brief (2026-10-15, revised against the HD mascot render): a saturated
turquoise chibi sauropod with a massive rounded head, short forward-leaning neck,
broad ivory throat/chest/belly, oversized matte graduation cap, thick ribbed gold
tassel, large raised copper spinal ovals mixed with navy dots, and broad feet with
three prominent copper toe caps each. Colours below are authored as sRGB hex and
converted to linear for Blender so the render matches the brief.
"""

import math
from pathlib import Path

import bpy
from mathutils import Quaternion, Vector

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "backend/src/campuspilot/web_assets/models"
PREVIEW = ROOT / "output/playwright/dino"
OUT.mkdir(parents=True, exist_ok=True)
PREVIEW.mkdir(parents=True, exist_ok=True)
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)


def srgb(hexcode):
    """sRGB hex -> linear floats for Blender's Principled BSDF."""
    h = hexcode.lstrip("#")
    out = []
    for i in (0, 2, 4):
        c = int(h[i : i + 2], 16) / 255
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return tuple(out)


def material(name, hexcode, rough=0.42):
    m = bpy.data.materials.new(name)
    color = srgb(hexcode)
    m.diffuse_color = (*color, 1)
    m.use_nodes = True
    p = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    p.inputs["Base Color"].default_value = (*color, 1)
    p.inputs["Roughness"].default_value = rough
    return m


# Palette sampled from the HD reference render.
teal = material("01 · mascot turquoise", "#4FAEAA")
ivory = material("02 · warm ivory", "#F5E9D2")
ink = material("03 · cap charcoal", "#121417")
gold = material("04 · tassel gold", "#E4B93E", 0.30)
iris = material("05 · iris brown", "#4A2C18", 0.18)
ebony = material("06 · pupil black", "#0D0906", 0.12)
sclera = material("07 · eye white", "#FBF8F0", 0.28)
catchlight = material("08 · eye catchlight", "#FFFFFF", 0.12)
copper = material("09 · copper spot", "#9E5732")
navy = material("10 · navy speck", "#22404E")
groove = material("11 · mouth groove", "#2E5B59", 0.55)
root = bpy.data.objects.new("CDUTdino", None)
bpy.context.collection.objects.link(root)


def empty(name, loc, parent=root):
    o = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(o)
    o.location = loc
    o.parent = parent
    return o


def sphere(name, loc, scale, mat, parent=root):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=14, location=loc)
    o = bpy.context.object
    o.name = name
    o.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    o.data.materials.append(mat)
    for p in o.data.polygons:
        p.use_smooth = True
    o.parent = parent
    return o


def curve(name, pts, radius, mat, parent=root):
    c = bpy.data.curves.new(name, "CURVE")
    c.dimensions = "3D"
    c.resolution_u = 12
    c.bevel_depth = radius
    c.bevel_resolution = 2
    s = c.splines.new("BEZIER")
    s.bezier_points.add(len(pts) - 1)
    for b, p in zip(s.bezier_points, pts, strict=False):
        b.co = p
        b.handle_left_type = b.handle_right_type = "AUTO"
    o = bpy.data.objects.new(name, c)
    bpy.context.collection.objects.link(o)
    o.data.materials.append(mat)
    o.parent = parent
    return o


def fuse(name, parts, voxel=0.065):
    bpy.ops.object.select_all(action="DESELECT")
    for o in parts:
        o.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.object.join()
    o = parts[0]
    o.name = name
    r = o.modifiers.new("Sculpt union", "REMESH")
    r.mode = "VOXEL"
    r.voxel_size = voxel
    bpy.ops.object.modifier_apply(modifier=r.name)
    sm = o.modifiers.new("Sculpt polish", "SMOOTH")
    sm.factor = 1.15
    sm.iterations = 6
    bpy.ops.object.modifier_apply(modifier=sm.name)
    sub = o.modifiers.new("Silhouette finish", "SUBSURF")
    sub.levels = 1
    bpy.ops.object.modifier_apply(modifier=sub.name)
    for p in o.data.polygons:
        p.use_smooth = True
    return o


def surface(target, start, direction):
    """Cast a world-space ray at a mesh; returns (world point, world normal)."""
    inv = target.matrix_world.inverted()
    hit, pos, normal, _ = target.ray_cast(inv @ Vector(start), inv.to_3x3() @ Vector(direction))
    if not hit:
        raise RuntimeError("surface projection missed " + str(start))
    n = (target.matrix_world.to_3x3() @ normal).normalized()
    return target.matrix_world @ pos, n


def aim(target, parent, local_center, local_direction):
    """Find the surface point hit when looking at `local_center` from `local_direction`."""
    m = parent.matrix_world
    d = (m.to_3x3() @ Vector(local_direction)).normalized()
    p, n = surface(target, (m @ Vector(local_center)) + d * 6, -d)
    inv = m.inverted()
    return inv @ p, (inv.to_3x3() @ n).normalized()


def orient(o, normal, roll=0.0):
    """Rotate a flattened ellipsoid so its local +Y axis follows the surface normal."""
    n = Vector(normal).normalized()
    q = Vector((0, 1, 0)).rotation_difference(n)
    if roll:
        q = Quaternion(n, roll) @ q
    o.rotation_mode = "QUATERNION"
    o.rotation_quaternion = q
    return o


def dome(name, loc, radii, mat, normal, parent, roll=0.0):
    return orient(sphere(name, loc, radii, mat, parent), normal, roll)


def tangent(normal, direction):
    n = Vector(normal).normalized()
    d = Vector(direction)
    return (d - n * d.dot(n)).normalized()


# ---------------------------------------------------------------------------
# Torso and neck: a broad barrel body, high rounded back and short leaning neck.
# ---------------------------------------------------------------------------
torso = empty("torso", (0, 0, 0))
body = fuse(
    "body sculpt",
    [
        sphere("rear barrel", (-0.52, 0, 1.48), (1.04, 0.82, 0.82), teal, torso),
        sphere("belly", (0.02, 0, 1.26), (0.96, 0.80, 0.78), teal, torso),
        sphere("shoulder", (0.62, 0, 1.56), (0.78, 0.72, 0.80), teal, torso),
        sphere("high back", (-0.12, 0, 1.86), (0.84, 0.64, 0.56), teal, torso),
        sphere("neck lower", (0.55, 0, 2.02), (0.47, 0.44, 0.70), teal, torso),
        sphere("neck upper", (0.80, 0, 2.50), (0.35, 0.33, 0.55), teal, torso),
    ],
    0.068,
)

# Massive rounded head: broad cranium, narrower protruding muzzle, full jaw.
head = empty("head", (1.04, 0, 2.94), torso)
head_mesh = fuse(
    "head sculpt",
    [
        sphere("cranium", (-0.04, 0, 0.20), (0.58, 0.56, 0.48), teal, head),
        sphere("muzzle", (0.44, 0, 0.02), (0.46, 0.50, 0.38), teal, head),
        sphere("cheek", (0.00, 0, -0.24), (0.54, 0.54, 0.38), teal, head),
    ],
    0.050,
)
bpy.context.view_layer.update()


def fitted_patch(name, target, parent, rails, lift, mat):
    """Quad-strip patch of surface-projected rows, kept flush with the mesh."""
    verts = []
    faces = []
    cols = 17
    for z, half in rails:
        for j in range(cols):
            t = (j / (cols - 1) - 0.5) * 2
            p, n = surface(target, (4, half * t, z), (-1, 0, 0))
            verts.append(p + n * (lift - 0.005))
    for i in range(len(rails) - 1):
        for j in range(cols - 1):
            a = i * cols + j
            faces.append((a, a + 1, a + cols + 1, a + cols))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    o = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(o)
    o.parent = parent
    o.data.materials.append(mat)
    sub = o.modifiers.new("Soft edge", "SUBSURF")
    sub.levels = 2
    for p in mesh.polygons:
        p.use_smooth = True
    bpy.ops.object.select_all(action="DESELECT")
    o.select_set(True)
    bpy.context.view_layer.objects.active = o
    bpy.ops.object.modifier_apply(modifier=sub.name)
    for v in o.data.vertices:
        p, n = surface(target, (4, v.co.y, v.co.z), (-1, 0, 0))
        v.co = p + n * lift
    return o


# Ivory bib: a broad fitted surface from the throat, across the chest and belly.
fitted_patch(
    "ivory front",
    body,
    torso,
    [
        (2.72, 0.11),
        (2.55, 0.21),
        (2.35, 0.29),
        (2.12, 0.36),
        (1.88, 0.44),
        (1.64, 0.50),
        (1.40, 0.54),
        (1.18, 0.50),
        (1.02, 0.36),
        (0.93, 0.15),
    ],
    0.018,
    ivory,
)

# Massive column legs and broad feet, separated only at the hip folds for the walk rig.
legs = []
for x, label in [(0.62, "front"), (-0.52, "rear")]:
    for side in [-1, 1]:
        leg = empty(f"{label}_{'left' if side < 0 else 'right'}", (x, side * 0.53, 1.42), torso)
        legs.append(leg)
        fuse(
            "soft leg",
            [
                sphere("thigh", (0.00, 0, -0.42), (0.43, 0.41, 0.72), teal, leg),
                sphere("foot", (0.10, side * 0.02, -1.23), (0.50, 0.45, 0.33), teal, leg),
            ],
            0.050,
        )
        for offset in (-0.23, 0.0, 0.23):
            nail = sphere("copper toe", (0.47, offset, -1.20), (0.165, 0.125, 0.125), copper, leg)
            nail.rotation_euler[1] = -0.34

# Thick tail: broad at the body, sweeping back and gently downward like the reference.
tail = empty("tail", (-1.28, 0, 1.58), torso)
TAIL = [
    (-0.05, -0.02, 0.00, 0.56),
    (-0.45, -0.02, -0.02, 0.48),
    (-0.82, -0.05, -0.03, 0.39),
    (-1.12, -0.08, -0.02, 0.29),
    (-1.33, -0.10, -0.10, 0.19),
    (-1.50, -0.10, -0.26, 0.115),
    (-1.62, -0.10, -0.42, 0.075),
    (-1.70, -0.10, -0.50, 0.058),
]
pts = [(x, y, z, r) for x, y, z, r in TAIL]
vs = []
fs = []
for x, y, z, r in pts:
    for j in range(28):
        a = 2 * math.pi * j / 28
        vs.append((x, y + r * math.cos(a) * 1.06, z + r * math.sin(a) * 0.94))
for i in range(len(pts) - 1):
    for j in range(28):
        a = i * 28 + j
        b = i * 28 + (j + 1) % 28
        fs.append((a, b, b + 28, a + 28))
tip = sphere("tail tip", TAIL[-1][:3], (0.075, 0.075, 0.075), teal, tail)
tip.rotation_euler[0] = 0.5
fs.extend([tuple(range(27, -1, -1)), tuple((len(pts) - 1) * 28 + j for j in range(28))])
m = bpy.data.meshes.new("tail")
m.from_pydata(vs, [], fs)
m.update()
o = bpy.data.objects.new("tapered tail", m)
bpy.context.collection.objects.link(o)
o.parent = tail
o.data.materials.append(teal)
s = o.modifiers.new("Smooth tail", "SUBSURF")
s.levels = 1
for p in m.polygons:
    p.use_smooth = True
tail_mesh = o

# ---------------------------------------------------------------------------
# Face: close-set glossy cartoon eyes, dark upper rims, brown irises, nostrils,
# and a broad smiling groove around the lower muzzle.
# ---------------------------------------------------------------------------
eye_centers = []
for side in [-1, 1]:
    p, n = aim(head_mesh, head, (0.20, side * 0.14, 0.34), (0.78, side * 0.42, 0.34))
    eye_centers.append((p, n, side))
    dome("eye white", p, (0.200, 0.032, 0.270), sclera, n, head, side * 0.12)
    dome("eye rim", p - n * 0.018, (0.240, 0.026, 0.310), ink, n, head, side * 0.12)
    front = tangent(n, (1, 0, 0))
    up = tangent(n, (0, 0, 1))
    dome(
        "eye iris", p + front * 0.055 + n * 0.022,
        (0.145, 0.030, 0.190), iris, n, head, side * 0.12,
    )
    dome(
        "eye pupil", p + front * 0.075 + n * 0.036,
        (0.088, 0.028, 0.115), ebony, n, head, side * 0.12,
    )
    dome(
        "catchlight major",
        p + front * 0.082 + up * 0.082 + n * 0.055,
        (0.050, 0.020, 0.056),
        catchlight,
        n,
        head,
    )
    dome(
        "catchlight minor",
        p + front * 0.025 - up * 0.020 + n * 0.055,
        (0.028, 0.018, 0.030),
        catchlight,
        n,
        head,
    )
    np_, nn = aim(head_mesh, head, (0.54, side * 0.09, 0.06), (0.82, side * 0.24, 0.52))
    dome("nostril", np_, (0.032, 0.026, 0.016), groove, nn, head)
    brow_center = p + up * 0.335 - front * 0.030
    curve(
        "upper lid",
        [
            brow_center - front * 0.170 + up * 0.015,
            brow_center + up * 0.065,
            brow_center + front * 0.170 - up * 0.030,
        ],
        0.028,
        ink,
        head,
    )

# A clean front smile: a shallow upward arc across the lower muzzle, projected
# straight back onto the face so it never climbs the cheeks.
mouth_pts = []
mouth_normals = []
mouth_half = []
for i in range(19):
    t = i / 18 * 2 - 1
    y = t * 0.30
    z = -0.16 + 0.16 * t * t
    p, n = surface(head_mesh, (2.54, y, 2.94 + z), (-1, 0, 0))
    mouth_pts.append(head.matrix_world.inverted() @ (p + n * 0.008))
    mouth_normals.append(n)
    mouth_half.append(0.019 - 0.005 * abs(t))
mouth_verts = []
mouth_faces = []
for i, p in enumerate(mouth_pts):
    if i == 0:
        d = mouth_pts[1] - mouth_pts[0]
    elif i == len(mouth_pts) - 1:
        d = mouth_pts[-1] - mouth_pts[-2]
    else:
        d = mouth_pts[i + 1] - mouth_pts[i - 1]
    # Ribbon width runs inside the surface plane, across the path direction.
    b = d.normalized().cross(mouth_normals[i]).normalized()
    mouth_verts += [p - b * mouth_half[i], p + b * mouth_half[i]]
for i in range(len(mouth_pts) - 1):
    a = i * 2
    mouth_faces.append((a, a + 1, a + 3, a + 2))
mm = bpy.data.meshes.new("mouth")
mm.from_pydata(mouth_verts, [], mouth_faces)
mm.update()
mo = bpy.data.objects.new("smiling groove", mm)
bpy.context.collection.objects.link(mo)
mo.parent = head
mo.data.materials.append(groove)
for p in mm.polygons:
    p.use_smooth = True

# ---------------------------------------------------------------------------
# Skin markings: one spaced row of triangular copper dorsal plates from the neck
# down the spine and onto the tail, plus round copper dots and navy dots spread
# loosely across the flanks (never clustered).
# ---------------------------------------------------------------------------
def plate(name, loc, length, height, mat, parent):
    bpy.ops.mesh.primitive_cone_add(vertices=3, radius1=1, radius2=0, depth=1, location=loc)
    o = bpy.context.object
    o.name = name
    o.scale = (length, length * 0.32, height)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    o.rotation_euler[2] = math.pi
    o.data.materials.append(mat)
    o.parent = parent
    return o


for x, size in [
    (0.28, 0.16),
    (-0.02, 0.19),
    (-0.32, 0.19),
    (-0.62, 0.18),
    (-0.90, 0.16),
    (-1.14, 0.13),
]:
    p, n = surface(body, (x, 0, 7), (0, 0, -1))
    plate("dorsal plate", (p.x, 0, p.z + size * 0.18), size * 1.5, size * 1.6, copper, torso)
for lx, lz, r, size in [
    (-0.45, -0.02, 0.48, 0.115),
    (-0.85, -0.05, 0.39, 0.100),
    (-1.15, -0.02, 0.29, 0.085),
    (-1.36, -0.14, 0.19, 0.070),
]:
    plate(
        "tail plate",
        (lx, 0, lz + r * 0.90 + size * 0.10),
        size * 1.5,
        size * 1.6,
        copper,
        tail,
    )
flank_copper = [
    (0.78, 2.52, 0.070),
    (0.35, 2.15, 0.080),
    (0.42, 1.80, 0.105),
    (0.10, 1.15, 0.095),
    (-0.02, 1.62, 0.115),
    (-0.50, 1.86, 0.100),
    (-0.88, 1.56, 0.110),
    (-1.16, 1.72, 0.090),
    (-1.28, 1.42, 0.085),
]
for x, z, r in flank_copper + [(0.35, 2.15, 0.080)]:
    for side in [-1, 1]:
        p, n = surface(body, (x, side * 4, z), (0, -side, 0))
        if abs(p.y) > abs(side) * 1.2:
            raise RuntimeError("flank dot missed the body " + str((x, z)))
        dome("flank dot", p + n * (r * 0.05), (r, r * 0.45, r), copper, n, torso)
navy_specks = [
    (0.60, 2.28, 0.055),
    (0.05, 2.02, 0.058),
    (0.55, 1.66, 0.060),
    (0.10, 1.94, 0.055),
    (-0.28, 1.52, 0.062),
    (-0.52, 1.18, 0.058),
    (-0.70, 1.92, 0.055),
    (-1.00, 1.44, 0.058),
    (-1.24, 1.62, 0.050),
]
for x, z, r in navy_specks:
    for side in [-1, 1]:
        p, n = surface(body, (x, side * 4, z), (0, -side, 0))
        dome("navy dot", p + n * (r * 0.05), (r, r * 0.42, r), navy, n, torso)
for lx, _cy, _ry, lz, r, mat, name in [
    (-0.82, -0.05, 0.413, -0.03, 0.070, copper, "tail dot"),
    (-1.15, -0.08, 0.307, -0.02, 0.052, navy, "tail speck"),
]:
    bpy.context.view_layer.update()
    for side in [-1, 1]:
        start = tail.matrix_world @ Vector((lx, side * 4, lz))
        p, n = surface(tail_mesh, start, (0, -side, 0))
        inv = tail.matrix_world.inverted()
        dome(name, inv @ (p + n * (r * 0.05)), (r, r * 0.45, r), mat, inv.to_3x3() @ n, tail)

# ---------------------------------------------------------------------------
# Graduation cap: a tall matte crown, oversized beveled square board, raised gold
# cords to a knot and a thick ribbed tassel skirt hanging beside the cheek.
# ---------------------------------------------------------------------------
hat = empty("mortarboard", (-0.14, 0, 0.72), head)
hat.rotation_euler[1] = 0.12
bpy.ops.mesh.primitive_cylinder_add(vertices=40, radius=0.42, depth=0.36, location=(0, 0, 0.05))
band = bpy.context.object
band.name = "cap crown"
band.parent = hat
band.data.materials.append(ink)
bev = band.modifiers.new("Rounded crown", "BEVEL")
bev.width = 0.06
bev.segments = 4
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0.27))
board = bpy.context.object
board.name = "square academic cap"
board.scale = (1.58, 1.50, 0.145)
bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
board.parent = hat
board.data.materials.append(ink)
bev = board.modifiers.new("Bound cap edge", "BEVEL")
bev.width = 0.06
bev.segments = 4
board.rotation_euler[2] = 0.10
sphere("cap button", (0, 0, 0.375), (0.085, 0.085, 0.030), gold, hat)
curve(
    "gold cord",
    [
        (0.00, 0.00, 0.375),
        (0.20, -0.42, 0.365),
        (0.48, -0.80, 0.300),
        (0.62, -0.90, 0.060),
        (0.64, -0.90, -0.320),
    ],
    0.028,
    gold,
    hat,
)
curve(
    "tassel knot",
    [
        (0.640, -0.900, -0.300),
        (0.655, -0.905, -0.345),
        (0.640, -0.900, -0.390),
    ],
    0.055,
    gold,
    hat,
)
curve(
    "tassel skirt",
    [
        (0.585, -0.875, -0.400),
        (0.640, -0.900, -0.470),
        (0.685, -0.920, -0.575),
        (0.705, -0.925, -0.700),
        (0.665, -0.915, -0.820),
        (0.600, -0.895, -0.895),
    ],
    0.098,
    gold,
    hat,
)

# ---------------------------------------------------------------------------
# Export an actual loop; pivots stay editable in the .blend and as glTF channels.
# ---------------------------------------------------------------------------
scene = bpy.context.scene
scene.render.fps = 30
scene.frame_start = 1
scene.frame_end = 31
for frame in range(1, 32):
    a = (frame - 1) / 30 * 2 * math.pi
    for i, leg in enumerate(legs):
        leg.rotation_euler[1] = math.sin(a + (0 if i in [0, 3] else math.pi)) * 0.24
        leg.keyframe_insert("rotation_euler", frame=frame)
    torso.location.z = 0.035 * (1 - math.cos(a * 2))
    torso.keyframe_insert("location", frame=frame)
    head.rotation_euler[1] = math.cos(a) * 0.035
    head.keyframe_insert("rotation_euler", frame=frame)
    tail.rotation_euler[2] = math.sin(a) * 0.10
    tail.keyframe_insert("rotation_euler", frame=frame)
    hat.rotation_euler[0] = 0.05 + math.sin(a - 0.7) * 0.10
    hat.keyframe_insert("rotation_euler", frame=frame)
scene.frame_set(1)
# The sculpture reads at 50-90 px on a map. Convert decorative curves to meshes,
# then keep each silhouette while dropping hidden topology.
bpy.ops.object.select_all(action="DESELECT")
for o in list(root.children_recursive):
    if o.type == "CURVE":
        bpy.context.view_layer.objects.active = o
        o.select_set(True)
        bpy.ops.object.convert(target="MESH")
        o.select_set(False)
bpy.ops.object.select_all(action="DESELECT")
for o in list(root.children_recursive):
    if o.type == "MESH":
        bpy.context.view_layer.objects.active = o
        o.select_set(True)
        for mod in list(o.modifiers):
            if mod.type != "DECIMATE":
                bpy.ops.object.modifier_apply(modifier=mod.name)
        if len(o.data.polygons) > 300:
            dec = o.modifiers.new("Web mesh budget", "DECIMATE")
            dec.ratio = 0.06 if len(o.data.polygons) > 2000 else 0.24
            bpy.ops.object.modifier_apply(modifier=dec.name)
        o.select_set(False)
bpy.ops.object.select_all(action="DESELECT")
for o in bpy.data.objects:
    if o == root or o in root.children_recursive:
        o.select_set(True)
bpy.ops.export_scene.gltf(
    filepath=str(OUT / "cdutdino-guide.glb"),
    export_format="GLB",
    use_selection=True,
    export_animations=True,
    export_animation_mode="SCENE",
    export_frame_range=True,
    export_force_sampling=True,
    export_apply=True,
)
# Studio is excluded from the exported model, included in editable Blender source.
floor = material("studio chalk", "#C9D6D2", 0.8)
bpy.ops.mesh.primitive_plane_add(size=200)
bpy.context.object.name = "Studio floor"
bpy.context.object.data.materials.append(floor)
world = scene.world or bpy.data.worlds.new("World")
scene.world = world
world.use_nodes = True
bg = next(n for n in world.node_tree.nodes if n.type == "BACKGROUND")
bg.inputs[0].default_value = (0.68, 0.76, 0.74, 1)
bg.inputs[1].default_value = 0.45


def area(name, loc, power, size):
    bpy.ops.object.light_add(type="AREA", location=loc)
    o = bpy.context.object
    o.name = name
    o.data.energy = power
    o.data.shape = "DISK"
    o.data.size = size
    o.rotation_euler = (Vector((0, 0, 2)) - o.location).to_track_quat("-Z", "Y").to_euler()


area("Key", (4, -6, 8), 900, 5)
area("Fill", (-4, -2, 4), 520, 4)
area("Rim", (1, 5, 7), 1050, 4)
bpy.ops.object.camera_add(location=(7, -10, 6))
cam = bpy.context.object
scene.camera = cam
cam.data.type = "ORTHO"
cam.data.ortho_scale = 6.1
scene.render.engine = "CYCLES"
scene.cycles.samples = 40
scene.cycles.use_denoising = True
scene.render.resolution_x = 1000
scene.render.resolution_y = 1000
scene.render.resolution_percentage = 100
scene.view_settings.view_transform = "Standard"
scene.render.image_settings.file_format = "PNG"
FOCUS = Vector((0.10, 0, 1.95))
cam.rotation_euler = (FOCUS - cam.location).to_track_quat("-Z", "Y").to_euler()
bpy.context.preferences.filepaths.save_version = 0
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT / "tools/models/cdutdino-guide.blend"))
for name, loc in [
    ("three-quarter", (7, -10, 6)),
    ("rear", (-7, -10, 6)),
    ("front", (10, -0.1, 4.8)),
]:
    cam.location = loc
    cam.rotation_euler = (FOCUS - cam.location).to_track_quat("-Z", "Y").to_euler()
    scene.render.filepath = str(PREVIEW / (name + ".png"))
    bpy.ops.render.render(write_still=True)
