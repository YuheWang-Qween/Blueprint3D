"""Reproduce the optimized sample using the project's standard pipeline."""

import json
import sys
import time
from pathlib import Path

import numpy as np
import pyvista as pv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'ForgeFloor'))
from extruder import ForgePlanPipeline


def main():
    sample = ROOT / 'examples' / 'historical-sample'
    out = ROOT / 'outputs' / 'optimized-sample'
    pipeline = ForgePlanPipeline(output_dir=str(out), project_root=str(ROOT))
    start = time.perf_counter()
    result = pipeline.run(
        sema_path=str(sample / 'sema.csv'), split_path=str(sample / 'split.csv'),
        underlay_path=str(sample / 'input.jpeg'), geometry_mode='vector',
        wall_height=200, room_height=0, wall_thickness=4, door_height=160,
        flip_y=True, flip_x=False, rotation=0, show_segmentation=False,
        show_input_image=False, floor_opacity=1, show_interactive=False,
    )
    if not result['success']:
        raise RuntimeError(result['errors'])
    result['elapsed_seconds'] = round(time.perf_counter() - start, 3)
    result['provenance'] = {
        'repository': 'https://github.com/ashnomad/Blueprint3D',
        'base_commit': 'bb4a4fd',
        'sample_commit': '5df980e2b845285d0e72199a7a7e01ef3b3fb572',
        'neural_inference_run': False,
        'units': 'image pixels; no metric scale supplied',
    }
    scene = pv.read(out / 'scene.vtm')
    payload = []
    for name, mesh in zip(scene.keys(), scene):
        mesh = mesh.triangulate()
        payload.append({
            'name': name, 'kind': name.split('_')[0],
            'positions': np.round(mesh.points.astype(float), 3).ravel().tolist(),
            'indices': mesh.faces.reshape(-1, 4)[:, 1:].ravel().tolist(),
        })
    (out / 'preview-mesh.json').write_text(json.dumps(payload, separators=(',', ':')))
    (out / 'preview.png').write_bytes((out / '3d_render.png').read_bytes())
    result['obj_bytes'] = (out / 'floorplan_3d.obj').stat().st_size
    legacy = ROOT / 'outputs' / 'historical-sample'
    if (legacy / 'scene.vtm').exists():
        legacy_scene = pv.read(legacy / 'scene.vtm')
        triangles = sum(m.triangulate().n_cells for m in legacy_scene)
        result['comparison'] = {
            'original_triangles': triangles,
            'optimized_triangles': result['geometry']['triangles'],
            'triangle_reduction_percent': round(100 * (1-result['geometry']['triangles']/triangles), 3),
            'original_obj_bytes': (legacy / 'floorplan_3d.obj').stat().st_size,
        }
    (out / 'result.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
