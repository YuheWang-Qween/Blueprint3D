"""Selectable finish skins in the original GLB frame; structural meshes stay intact."""
import hashlib
import json
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

import manifold3d as mf
import numpy as np
from shapely import make_valid
from shapely.geometry import Polygon
from shapely.geometry.polygon import orient
from shapely.ops import unary_union


def polygons(shape):
    if isinstance(shape, Polygon):
        if shape.area > 1e-7:
            yield shape
    elif hasattr(shape, 'geoms'):
        for part in shape.geoms:
            yield from polygons(part)


def surface(kind, polygon, normal, offset):
    polygon = orient(polygon, sign=1)
    rings = [np.asarray(r.coords[:-1], dtype=float) for r in [polygon.exterior, *polygon.interiors]]
    uv = np.concatenate(rings)
    indices = np.asarray(mf.triangulate(rings), dtype=int)
    normal = np.asarray(normal, dtype=float)
    if kind == 'floor':
        # CCW in X/-Z has an upward normal.
        positions = np.column_stack((uv[:, 0], np.full(len(uv), offset + .003), -uv[:, 1]))
    else:
        tangent = np.array([normal[2], 0, -normal[0]])
        positions = uv[:, :1] * tangent + uv[:, 1:] * [0, 1, 0] + normal * (offset + .002)
    digest = hashlib.sha256(np.round(positions, 5).tobytes() + normal.tobytes()).hexdigest()[:16]
    return {'id': f'{kind}-{digest}', 'kind': kind, 'area': round(polygon.area, 3),
            'positions': np.round(positions, 5).ravel().tolist(), 'indices': indices.ravel().tolist(),
            'normal': normal.tolist(), 'uvs': np.round(uv, 5).ravel().tolist(),
            'color': '#becacf' if kind == 'floor' else '#e2e8ec'}


def get_surfaces(directory):
    path = directory / 'mesh.json'
    stat = path.stat()
    return _surfaces(str(path.resolve()), stat.st_mtime_ns, stat.st_size)


@lru_cache(maxsize=32)
def _surfaces(path, modified, size):
    meshes = json.loads(Path(path).read_text())
    floors = defaultdict(list)
    wall_planes = defaultdict(list)
    wall_footprints = []
    for mesh in meshes:
        kind = mesh['kind']
        if kind not in ('wall', 'floor'):
            continue
        points = np.asarray(mesh['positions']).reshape(-1, 3)
        points = points[:, [0, 2, 1]] * [1, 1, -1]
        faces = np.asarray(mesh['indices']).reshape(-1, 3)
        for triangle in points[faces]:
            normal = np.cross(triangle[1] - triangle[0], triangle[2] - triangle[0])
            length = np.linalg.norm(normal)
            if length < 1e-9:
                continue
            normal /= length
            if kind == 'floor' and normal[1] > .99:
                floors[round(float(triangle[:, 1].mean()), 4)].append(Polygon(triangle[:, [0, 2]] * [1, -1]))
            if kind != 'wall':
                continue
            footprint = Polygon(triangle[:, [0, 2]] * [1, -1])
            if footprint.area > 1e-8:
                wall_footprints.append(footprint)
            if abs(normal[1]) > .01:
                continue
            normal = np.round(normal, 5)
            distance = round(float(triangle[0] @ normal), 5)
            tangent = np.array([normal[2], 0, -normal[0]])
            projected = Polygon(np.column_stack((triangle @ tangent, triangle[:, 1])))
            wall_planes[(*normal, distance)].append(projected)
    result = []
    walls = unary_union(wall_footprints)
    for height, triangles in floors.items():
        footprint = make_valid(unary_union(triangles))
        rooms = make_valid(footprint.difference(walls))
        # Without closed interior walls, the connected floor remains one editable area.
        for polygon in polygons(rooms):
            if polygon.area >= .05:
                result.append(surface('floor', polygon, [0., 1., 0.], height))
    for plane, triangles in wall_planes.items():
        for polygon in polygons(make_valid(unary_union(triangles))):
            result.append(surface('wall', polygon, plane[:3], plane[3]))
    result.sort(key=lambda s: (s['kind'], tuple(np.asarray(s['positions']).reshape(-1, 3).mean(axis=0).round(5)), s['id']))
    counts = defaultdict(int)
    for item in result:
        counts[item['kind']] += 1
        item['name'] = ('地面区域 ' if item['kind'] == 'floor' else '墙面 ') + str(counts[item['kind']])
    return {'version': 1, 'surfaces': result}
