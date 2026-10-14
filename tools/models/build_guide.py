"""Original CDUTdino guide. Run with Blender --background --python this_file.
Editable smooth meshes and named walk pivots; no downloaded model or baked photo.
Blender Z up, forward +X. glTF export uses its standard Y-up conversion.
"""
import bpy, math
from pathlib import Path
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'backend/src/campuspilot/web_assets/models'
PREVIEW=ROOT/'output/playwright/dino'
OUT.mkdir(parents=True,exist_ok=True);PREVIEW.mkdir(parents=True,exist_ok=True)
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
def material(name,color,rough=.42):
    m=bpy.data.materials.new(name);m.diffuse_color=(*color,1);m.use_nodes=True
    p=next(n for n in m.node_tree.nodes if n.type=='BSDF_PRINCIPLED');p.inputs['Base Color'].default_value=(*color,1);p.inputs['Roughness'].default_value=rough
    return m
jade=material('01 · lagoon jade',(.10,.34,.29));cream=material('02 · warm ivory',(.86,.73,.46))
ink=material('03 · cap charcoal',(.006,.012,.009));gold=material('04 · tassel ochre',(.92,.43,.035),.32)
pupil=material('05 · espresso eyes',(.032,.022,.017),.22);white=material('06 · eye catchlight',(1,.97,.85),.22)
copper=material('07 · muted copper',(.42,.20,.095));darkjade=material('08 · deep jade',(.085,.26,.235))
root=bpy.data.objects.new('CDUTdino',None);bpy.context.collection.objects.link(root)
def empty(name,loc,parent=root):
    o=bpy.data.objects.new(name,None);bpy.context.collection.objects.link(o);o.location=loc;o.parent=parent;return o
def sphere(name,loc,scale,mat,parent=root):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32,ring_count=20,location=loc)
    o=bpy.context.object;o.name=name;o.scale=scale
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    o.data.materials.append(mat)
    for p in o.data.polygons:p.use_smooth=True
    o.parent=parent;return o
def curve(name,pts,radius,mat,parent=root):
    c=bpy.data.curves.new(name,'CURVE');c.dimensions='3D';c.resolution_u=16;c.bevel_depth=radius;c.bevel_resolution=3
    s=c.splines.new('BEZIER');s.bezier_points.add(len(pts)-1)
    for b,p in zip(s.bezier_points,pts):b.co=p;b.handle_left_type=b.handle_right_type='AUTO'
    o=bpy.data.objects.new(name,c);bpy.context.collection.objects.link(o);o.data.materials.append(mat);o.parent=parent;return o
def fuse(name,parts,voxel=.065):
    bpy.ops.object.select_all(action='DESELECT')
    for o in parts:o.select_set(True)
    bpy.context.view_layer.objects.active=parts[0];bpy.ops.object.join();o=parts[0];o.name=name
    r=o.modifiers.new('Sculpt union','REMESH');r.mode='VOXEL';r.voxel_size=voxel;bpy.ops.object.modifier_apply(modifier=r.name)
    sm=o.modifiers.new('Sculpt polish','SMOOTH');sm.factor=1.15;sm.iterations=6;bpy.ops.object.modifier_apply(modifier=sm.name)
    sub=o.modifiers.new('Silhouette finish','SUBSURF');sub.levels=1;bpy.ops.object.modifier_apply(modifier=sub.name)
    for p in o.data.polygons:p.use_smooth=True
    return o
# A continuous pear-shaped body and gently leaning neck. No visible stack of primitives.
torso=empty('torso',(0,0,0))
body=fuse('body sculpt',[
    sphere('haunch',(-.35,0,1.12),(1.0,.65,.79),jade,torso),
    sphere('chest',(.37,0,1.27),(.59,.55,.78),jade,torso),
    sphere('neck lower',(.51,0,1.83),(.37,.37,.72),jade,torso),
    sphere('neck upper',(.62,0,2.38),(.29,.31,.55),jade,torso)])
head=empty('head',(.62,0,2.65),torso)
fuse('head sculpt',[
    sphere('cranium',(.08,0,.41),(.59,.49,.58),jade,head),
    sphere('muzzle',(.52,0,.22),(.58,.41,.31),jade,head),
    sphere('jaw',(.34,0,.04),(.48,.38,.28),jade,head)],.043)
# Ivory bib follows the anterior neck; it is a shallow fitted surface, not a separate ball.
verts=[];faces=[]
rows=[(.76,0,0,.025),(.85,0,0,.16),(1.10,0,0,.28),(1.36,0,0,.29),(1.60,0,0,.24),(1.90,0,0,.185),(2.17,0,0,.16),(2.42,0,0,.15),(2.64,0,0,.13),(2.77,0,0,.045)]
bpy.context.view_layer.update()
def surface(start,direction):
    inv=body.matrix_world.inverted();hit,pos,normal,_=body.ray_cast(inv@Vector(start),inv.to_3x3()@Vector(direction))
    if not hit:raise RuntimeError('surface projection missed '+str(start))
    n=(body.matrix_world.to_3x3()@normal).normalized();return body.matrix_world@pos,n
for z,_,x,w in rows:
    for j in range(17):
        t=(j/16-.5)*2;p,n=surface((4,w*t,z),(-1,0,0));verts.append(p+n*.009)
for i in range(len(rows)-1):
    for j in range(16):a=i*17+j;faces.append((a,a+1,a+18,a+17))
mesh=bpy.data.meshes.new('bib');mesh.from_pydata(verts,[],faces);mesh.update()
o=bpy.data.objects.new('ivory throat',mesh);bpy.context.collection.objects.link(o);o.parent=torso;o.data.materials.append(cream)
sub=o.modifiers.new('Soft bib','SUBSURF');sub.levels=2
for p in mesh.polygons:p.use_smooth=True
bpy.ops.object.select_all(action='DESELECT');o.select_set(True);bpy.context.view_layer.objects.active=o;bpy.ops.object.modifier_apply(modifier=sub.name)
for v in o.data.vertices:
    p,n=surface((4,v.co.y,v.co.z),(-1,0,0));v.co=p+n*.014
# Rounded, weight-bearing legs, separate at natural hip folds for a lightweight pivot rig.
legs=[]
for x,label in [(.47,'front'),(-.91,'rear')]:
    for side in [-1,1]:
        leg=empty(f'{label}_{"left" if side<0 else "right"}',(x,side*.45,1.02),torso);legs.append(leg)
        fuse('soft leg',[
            sphere('leg',(.0,0,-.31),(.245,.235,.48),jade,leg),
            sphere('foot',(.065,side*.016,-.78),(.285,.25,.20),jade,leg)],.045)
        for offset in [-.13,0,.13]:sphere('small toe',(.29,offset,-.83),(.06,.048,.063),cream,leg)
tail=empty('tail',(-1.06,0,1.34),torso)
# Tapered curved tail using oriented elliptical rings.
pts=[(0,0,0,.35),(-.30,0,-.03,.30),(-.63,.015,.035,.22),(-.92,.05,.17,.13),(-1.17,.09,.35,.065),(-1.28,.12,.49,.012)]
vs=[];fs=[]
for x,y,z,r in pts:
    for j in range(24):a=2*math.pi*j/24;vs.append((x,y+r*math.cos(a),z+r*math.sin(a)))
for i in range(len(pts)-1):
    for j in range(24):a=i*24+j;b=i*24+(j+1)%24;fs.append((a,b,b+24,a+24))
fs.extend([tuple(range(23,-1,-1)),tuple((len(pts)-1)*24+j for j in range(24))])
m=bpy.data.meshes.new('tail');m.from_pydata(vs,[],fs);m.update();o=bpy.data.objects.new('tapered tail',m);bpy.context.collection.objects.link(o);o.parent=tail;o.data.materials.append(jade)
s=o.modifiers.new('Smooth tail','SUBSURF');s.levels=2
for p in m.polygons:p.use_smooth=True
# Eyes sit on both sides, with a forward glance and one sculpted brow per side.
for side in [-1,1]:
    e=sphere('ivory eye',(.29,side*.409,.55),(.235,.105,.29),cream,head);e.rotation_euler[2]=side*-.25
    sphere('eye pupil',(.36,side*.495,.55),(.14,.06,.205),pupil,head)
    sphere('catchlight',(.398,side*.541,.634),(.049,.016,.056),white,head)
    curve('soft brow',[(.02,side*.413,.78),(.17,side*.48,.88),(.34,side*.458,.85)],.035,ink,head)
    curve('smile',[(.89,side*.25,.14),(.63,side*.375,.06),(.35,side*.388,.065),(.24,side*.375,.13)],.019,darkjade,head)
    sphere('nostril',(.87,side*.20,.37),(.032,.027,.018),darkjade,head)
# Familiar restrained dots, large enough to read from the map's rear camera.
for x,z,r in [(-.97,1.43,.095),(-.66,1.71,.10),(-.29,1.85,.07),(-.48,1.46,.075),(-.12,1.52,.11),(-.78,1.12,.055)]:
    for side in [-1,1]:
        p,n=surface((x,side*3,z),(0,-side,0));spot=sphere('flank spot',p+n*.003,(r,.017,r*.85),copper if r>.085 else darkjade,torso);spot.rotation_mode='QUATERNION';spot.rotation_quaternion=Vector((0,1,0)).rotation_difference(n)
hat=empty('mortarboard',(.02,0,.90),head)
sphere('cap crown',(0,0,.015),(.44,.40,.18),ink,hat)
bpy.ops.mesh.primitive_cube_add(size=1,location=(0,0,.16));board=bpy.context.object;board.name='square academic cap';board.scale=(1.35,1.24,.095);bpy.ops.object.transform_apply(location=False,rotation=False,scale=True);board.parent=hat;board.data.materials.append(ink)
bev=board.modifiers.new('Bound cap edge','BEVEL');bev.width=.055;bev.segments=3
board.rotation_euler[2]=.12
sphere('cap button',(0,0,.234),(.07,.07,.025),ink,hat)
tassel=empty('tassel',(-.43,-.49,.22),hat)
curve('gold cord',[(.43,.49,.015),(-.05,.04,.012),(.05,-.07,-.16),(.07,-.08,-.50)],.024,gold,tassel)
sphere('tassel knot',(.07,-.08,-.52),(.065,.065,.085),gold,tassel)
bpy.ops.mesh.primitive_cone_add(vertices=24,radius1=.095,radius2=.045,depth=.28,location=(.07,-.08,-.73));o=bpy.context.object;o.name='gold tassel';o.parent=tassel;o.data.materials.append(gold)
bev=o.modifiers.new('Soft tassel','BEVEL');bev.width=.02;bev.segments=3
for p in o.data.polygons:p.use_smooth=True
# Export an actual loop; pivots are editable in the .blend as well as glTF animation channels.
scene=bpy.context.scene;scene.render.fps=30;scene.frame_start=1;scene.frame_end=31
for frame in range(1,32):
    a=(frame-1)/30*2*math.pi
    for i,l in enumerate(legs):
        l.rotation_euler[1]=math.sin(a+(0 if i in [0,3] else math.pi))*.24;l.keyframe_insert('rotation_euler',frame=frame)
    torso.location.z=.035*(1-math.cos(a*2));torso.keyframe_insert('location',frame=frame)
    head.rotation_euler[1]=math.cos(a)*.035;head.keyframe_insert('rotation_euler',frame=frame)
    tail.rotation_euler[2]=math.sin(a)*.10;tail.keyframe_insert('rotation_euler',frame=frame)
    tassel.rotation_euler[0]=math.sin(a-.7)*.12;tassel.keyframe_insert('rotation_euler',frame=frame)
scene.frame_set(1)
# The sculpture reads at 50–90 px on a map. Keep its silhouette, reduce hidden topology.
for o in list(root.children_recursive):
    if o.type=='MESH' and len(o.data.polygons)>600:
        dec=o.modifiers.new('Web mesh budget','DECIMATE');dec.ratio=.15 if len(o.data.polygons)>2000 else .45
bpy.ops.object.select_all(action='DESELECT')
for o in bpy.data.objects:
    if o==root or o in root.children_recursive:o.select_set(True)
bpy.ops.export_scene.gltf(filepath=str(OUT/'cdutdino-guide.glb'),export_format='GLB',use_selection=True,export_animations=True,export_animation_mode='SCENE',export_frame_range=True,export_force_sampling=True,export_apply=True)
# Studio is excluded from the exported model, included in editable Blender source.
floor=material('studio chalk',(.79,.84,.82),.8)
bpy.ops.mesh.primitive_plane_add(size=200);bpy.context.object.name='Studio floor';bpy.context.object.data.materials.append(floor)
world=scene.world or bpy.data.worlds.new('World');scene.world=world;world.use_nodes=True;bg=next(n for n in world.node_tree.nodes if n.type=='BACKGROUND');bg.inputs[0].default_value=(.68,.76,.74,1);bg.inputs[1].default_value=.45
def area(name,loc,power,size):
    bpy.ops.object.light_add(type='AREA',location=loc);o=bpy.context.object;o.name=name;o.data.energy=power;o.data.shape='DISK';o.data.size=size;o.rotation_euler=(Vector((0,0,2))-o.location).to_track_quat('-Z','Y').to_euler()
area('Key',(4,-6,8),850,5);area('Fill',(-4,-2,4),500,4);area('Rim',(1,5,7),1000,4)
bpy.ops.object.camera_add(location=(7,-10,6));cam=bpy.context.object;scene.camera=cam;cam.data.type='ORTHO';cam.data.ortho_scale=5.9
scene.render.engine='CYCLES';scene.cycles.samples=40;scene.cycles.use_denoising=True
scene.render.resolution_x=1000;scene.render.resolution_y=1000;scene.render.resolution_percentage=100
scene.view_settings.view_transform='AgX';scene.render.image_settings.file_format='PNG'
cam.rotation_euler=(Vector((-.25,0,1.9))-cam.location).to_track_quat('-Z','Y').to_euler()
bpy.context.preferences.filepaths.save_version=0
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'tools/models/cdutdino-guide.blend'))
for name,loc in [('three-quarter',(7,-10,6)),('rear',(-7,-10,6)),('front',(10,-.1,4.8))]:
    cam.location=loc;cam.rotation_euler=(Vector((-.25,0,1.9))-cam.location).to_track_quat('-Z','Y').to_euler();scene.render.filepath=str(PREVIEW/(name+'.png'));bpy.ops.render.render(write_still=True)
print('MODEL_COMPLETE',OUT)
