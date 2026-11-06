"""Create a dimension-assumed model from reviewed image-space wall centerlines."""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pyvista as pv
import trimesh
from shapely.geometry import GeometryCollection, LineString, Point, Polygon, box
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'ForgeFloor'))
from vector_geometry import cross_section, solid_mesh

COLORS = {
    'wall': '#e9e7e1', 'floor': '#d6c9b5', 'door': '#b98d62',
    'glass': '#a3c7d1', 'frame': '#70858c',
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, default=ROOT / 'examples/user-floorplan-2026-11-06/traced-plan.json')
    parser.add_argument('--output', type=Path, default=ROOT / 'outputs/user-floorplan-2026-11-06/reviewed')
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    scale = plan['scale_m_per_pixel']
    origin = np.asarray(plan['origin_px'])
    height = plan['wall_height_m']
    door_height = plan['door_height_m']

    def xy(coords):
        return (np.asarray(coords, dtype=float) - origin) * [scale, -scale]

    def stroke(coords, width):
        return LineString(xy(coords)).buffer(width / 2, cap_style='square', join_style='mitre')

    footprint = Polygon(xy(plan['footprint_px']))
    external = footprint.boundary.buffer(plan['external_wall_thickness_m']/2, join_style='mitre')
    wall_plan = unary_union([external] + [stroke(line, plan['internal_wall_thickness_m'])
                                         for line in plan['internal_walls_px']])
    blocks = []
    for x1, y1, x2, y2 in plan['square_features_px']:
        a, b = xy([[x1, y1], [x2, y2]])
        blocks.append(box(min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])))
    wall_plan = unary_union([wall_plan, *blocks])
    wall_solid = cross_section(wall_plan).extrude(height)
    opening_lines = [[d['hinge_px'], d['closed_tip_px']] for d in plan['doors']]
    opening_lines.append(plan['sliding_opening_px'])
    # Flat ends retain the narrow central pier between the two north doors.
    opening_shapes = [LineString(xy(line)).buffer(.30, cap_style='flat') for line in opening_lines]
    for opening in opening_shapes:
        wall_solid -= cross_section(opening).extrude(door_height + .02).translate((0, 0, -.01))

    meshes = {'wall_shell': solid_mesh(wall_solid)}
    meshes['floor_slab'] = solid_mesh(cross_section(footprint.buffer(.09, join_style='mitre')).extrude(.14).translate((0, 0, -.14)))

    for door in plan['doors']:
        hinge_px = np.asarray(door['hinge_px'], dtype=float)
        vector = np.asarray(door['closed_tip_px']) - hinge_px
        theta = np.deg2rad(door['open_degrees'])
        rotation = np.array([[np.cos(theta), -np.sin(theta)], [np.sin(theta), np.cos(theta)]])
        tip_px = hinge_px + rotation @ vector
        panel = stroke([hinge_px, tip_px], .035)
        meshes[f"door_{door['id']}"] = solid_mesh(cross_section(panel).extrude(door_height-.035).translate((0, 0, .015)))

    for i, line in enumerate(plan['sliding_panels_px']):
        panel = stroke(line, .025)
        meshes[f'glass_sliding_{i}'] = solid_mesh(cross_section(panel).extrude(door_height-.09).translate((0, 0, .045)))
        for end, point in enumerate(line):
            x, y = xy(point)
            frame = box(x-.022, y-.022, x+.022, y+.022)
            meshes[f'frame_post_{i}_{end}'] = solid_mesh(cross_section(frame).extrude(door_height))
        for label, z in [('top', door_height-.04), ('bottom', 0)]:
            meshes[f'frame_{label}_{i}'] = solid_mesh(cross_section(stroke(line, .045)).extrude(.04).translate((0, 0, z)))

    def occupied(x, y, z):
        section = GeometryCollection()
        for contour in wall_solid.slice(z).to_polygons():
            section = section.symmetric_difference(Polygon(contour))
        return section.covers(Point(x, y))

    checks = []
    for name, opening in zip([d['id'] for d in plan['doors']] + ['sliding_partition'], opening_lines):
        midpoint = xy(np.mean(opening, axis=0))
        clear = not occupied(*midpoint, 1.0)
        header = occupied(*midpoint, 2.5)
        assert clear and header, f'Opening failed: {name}'
        checks.append({'opening': name, 'clear_below_header': clear, 'header_preserved': header})

    scene = pv.MultiBlock(meshes)
    scene.save(out / 'scene.vtm')
    payload = []
    gltf_scene = trimesh.Scene()
    obj_lines = ['# Assumed metric scale; see model-info.json', 'mtllib floorplan.mtl']
    offset = 1
    # glTF uses Y up: x,y,z -> x,z,-y. OBJ and scene.vtm retain Z up.
    gltf_transform = np.array([[1,0,0,0],[0,0,1,0],[0,-1,0,0],[0,0,0,1]], dtype=float)
    for name, mesh in meshes.items():
        mesh = mesh.triangulate().clean()
        assert mesh.n_open_edges == 0 and mesh.volume > 0 and np.isfinite(mesh.points).all(), name
        kind = name.split('_')[0]
        faces = mesh.faces.reshape(-1, 4)[:, 1:]
        payload.append({'name':name, 'kind':kind,
                        'positions':np.round(mesh.points, 5).ravel().tolist(),
                        'indices':faces.ravel().tolist()})
        obj_lines.extend([f'o {name}', f'usemtl {kind}'])
        obj_lines.extend('v ' + ' '.join(f'{v:.6f}' for v in p) for p in mesh.points)
        obj_lines.extend('f ' + ' '.join(str(int(v)+offset) for v in face) for face in faces)
        offset += mesh.n_points
        rgb = [int(COLORS[kind][i:i+2], 16) for i in (1,3,5)]
        material = trimesh.visual.material.PBRMaterial(name=kind, baseColorFactor=rgb+[85 if kind=='glass' else 255],
                    metallicFactor=0, roughnessFactor=.8, alphaMode='BLEND' if kind=='glass' else 'OPAQUE', doubleSided=True)
        tm = trimesh.Trimesh(vertices=mesh.points.copy(), faces=faces.copy(), process=False)
        tm.visual = trimesh.visual.TextureVisuals(material=material)
        tm.apply_transform(gltf_transform)
        gltf_scene.add_geometry(tm, node_name=name, geom_name=name)
    (out/'floorplan.obj').write_text('\n'.join(obj_lines)+'\n')
    materials = []
    for name, color in COLORS.items():
        rgb = [int(color[i:i+2], 16)/255 for i in (1,3,5)]
        materials.extend([f'newmtl {name}', 'Kd '+' '.join(f'{v:.5f}' for v in rgb),
                          f'd {0.33 if name=="glass" else 1.0}', 'illum 2', ''])
    (out/'floorplan.mtl').write_text('\n'.join(materials))
    gltf_scene.export(str(out/'floorplan.glb'))
    (out/'preview-mesh.json').write_text(json.dumps(payload, separators=(',', ':')))

    plotter = pv.Plotter(off_screen=True, window_size=(1700, 1450))
    plotter.set_background('#f5f3ee')
    for name, mesh in meshes.items():
        kind = name.split('_')[0]
        plotter.add_mesh(mesh, color=COLORS[kind], opacity=.33 if kind=='glass' else 1,
                         show_edges=False, ambient=.30, diffuse=.72, smooth_shading=False)
    plotter.enable_parallel_projection()
    center = np.asarray(scene.center)
    plotter.camera_position = [center+np.array([10, -14, 20]), center, (0,0,1)]
    plotter.reset_camera()
    plotter.camera.zoom(1.10)
    plotter.enable_anti_aliasing('ssaa')
    plotter.screenshot(out/'preview.png')
    plotter.view_xy()
    plotter.reset_camera()
    plotter.camera.zoom(1.05)
    plotter.screenshot(out/'top-view.png')
    plotter.close()

    loaded = trimesh.load(out/'floorplan.glb', force='scene')
    assert len(loaded.geometry)==len(meshes)
    assert sum(len(m.faces) for m in loaded.geometry.values()) == sum(m.n_cells for m in meshes.values())
    try:
        source = str(args.plan.resolve().relative_to(ROOT))
    except ValueError:
        source = args.plan.name
    report = {'source':source, 'method':plan['method'],
              'units':'meters; illustrative, unmeasured scale', 'scale_m_per_pixel':scale,
              'scale_note':plan['scale_note'], 'wall_height_m':height, 'door_height_m':door_height,
              'hinged_doors':len(plan['doors']), 'sliding_partitions':1, 'windows':0,
              'triangles':sum(m.n_cells for m in meshes.values()), 'mesh_parts':len(meshes),
              'all_meshes_closed':True, 'opening_checks':checks, 'glb_roundtrip_passed':True,
              'notes':[plan['square_feature_note'],plan['sliding_note'],plan['window_note']],
              'formats':{'glb':'Y up','obj':'Z up','vtm':'Z up'}}
    (out/'model-info.json').write_text(json.dumps(report, indent=2, ensure_ascii=False)+'\n')
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
