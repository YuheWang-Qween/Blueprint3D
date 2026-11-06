"""Vectorize segmentation masks and build compact, closed architectural solids.

Coordinates and dimensions remain in image units. No metric scale is inferred.
Rooms are regularized individually, shared wall gaps are filled once, and door
and window volumes are subtracted from the resulting unified wall solid.
"""

from dataclasses import dataclass
from typing import Dict, List

import manifold3d as mf
import numpy as np
import pyvista as pv
from scipy import ndimage
from shapely import make_valid
from shapely.geometry import GeometryCollection, LineString, Polygon
from shapely.ops import unary_union
from skimage import measure, morphology


def polygons(geometry):
    if isinstance(geometry, Polygon):
        yield geometry
    elif hasattr(geometry, "geoms"):
        for part in geometry.geoms:
            yield from polygons(part)


def _snap_ring(coords, tolerance):
    """Straighten nearly axis-aligned edges; preserve intentional diagonals."""
    points = np.asarray(coords[:-1], dtype=float).copy()
    count = len(points)
    original = points.copy()
    for axis in (0, 1):
        parent = list(range(count))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        for i in range(count):
            j = (i + 1) % count
            delta = original[j] - original[i]
            length = np.linalg.norm(delta)
            if (length >= 4 * tolerance and abs(delta[axis]) <= 2 * tolerance
                    and abs(delta[axis]) / length < np.sin(np.deg2rad(6))):
                parent[find(j)] = find(i)
        for group in {find(i) for i in range(count)}:
            ids = [i for i in range(count) if find(i) == group]
            points[ids, axis] = np.median(original[ids, axis])
    return points


def regularize(geometry, tolerance):
    if tolerance <= 0:
        return make_valid(geometry)
    parts = []
    for poly in polygons(make_valid(geometry.simplify(tolerance, preserve_topology=True))):
        candidate = make_valid(Polygon(
            _snap_ring(list(poly.exterior.coords), tolerance),
            [_snap_ring(list(r.coords), tolerance) for r in poly.interiors],
        ))
        # Never accept a large room-area change caused by snapping short edges.
        parts.append(candidate if abs(candidate.area - poly.area) <= max(1, poly.area * .025) else poly)
    return make_valid(unary_union(parts))


def mask_geometry(mask, tolerance=1.5, min_area=4):
    result = GeometryCollection()
    for contour in measure.find_contours(np.pad(mask.astype(float), 1), .5):
        xy = contour[:, ::-1] - 1
        poly = make_valid(Polygon(xy))
        if poly.area >= min_area:
            # Even/odd fill retains holes, including courtyards and shafts.
            result = result.symmetric_difference(poly)
    return regularize(result, tolerance)


def cross_section(geometry):
    contours = []
    for poly in polygons(make_valid(geometry)):
        contours.append(np.asarray(poly.exterior.coords[:-1], dtype=np.float64))
        contours.extend(np.asarray(r.coords[:-1], dtype=np.float64) for r in poly.interiors)
    return mf.CrossSection(contours, mf.FillRule.EvenOdd)


def solid_mesh(solid):
    if solid.status() != mf.Error.NoError:
        raise ValueError(f"Invalid solid: {solid.status()}")
    mesh = solid.to_mesh()
    triangles = np.asarray(mesh.tri_verts, dtype=np.int64)
    if not len(triangles):
        return pv.PolyData()
    faces = np.c_[np.full(len(triangles), 3, dtype=np.int64), triangles].ravel()
    # Copy the nanobind-owned buffer so VTK does not retain a foreign Mesh.
    return pv.PolyData(np.asarray(mesh.vert_properties)[:, :3].copy(), faces)


def opening_geometry(data, class_id, tolerance, clearance):
    mask = data == class_id
    # Remove one-pixel false positives before expansion creates fake openings.
    mask = morphology.binary_opening(mask, morphology.disk(1))
    labels, count = ndimage.label(mask)
    pieces = []
    for label_id, slices in enumerate(ndimage.find_objects(labels), 1):
        if slices is None:
            continue
        region = labels[slices] == label_id
        if region.sum() < 12 or min(region.shape) < 3:
            continue
        geometry = mask_geometry(labels == label_id, tolerance, min_area=12)
        if class_id == 3:
            geometry = geometry.minimum_rotated_rectangle
        pieces.append(geometry.buffer(clearance, join_style="mitre"))
    return unary_union(pieces)


@dataclass
class VectorScene:
    walls: List[pv.PolyData]
    windows: List[pv.PolyData]
    floor: pv.PolyData
    metadata: Dict
    wall_solid: object
    footprint: object
    wall_footprint: object
    door_openings: object
    window_openings: object


def build_scene(rooms, structures, *, wall_height=200, wall_thickness=4,
                tolerance=2, base_height=0, window_base_height=50,
                window_height=100, door_height=None, opening_clearance=2,
                opening_data=None):
    if rooms.ndim != 2 or structures.shape != rooms.shape:
        raise ValueError("Room and structure masks must have the same 2D shape")
    if wall_height <= 0 or wall_thickness <= 0:
        raise ValueError("Wall height and thickness must be positive")
    if opening_data is None:
        opening_data = structures
    if opening_data.shape != rooms.shape:
        raise ValueError("Opening mask shape must match room mask shape")
    if window_base_height < 0 or window_height < 0 or window_base_height + window_height > wall_height:
        raise ValueError("Window sill and height must fit within the wall")
    if door_height is None:
        door_height = wall_height * .8
    if not 0 < door_height <= wall_height:
        raise ValueError("Door height must be positive and no higher than the wall")
    room_polygons = [mask_geometry(rooms == rid, tolerance, 16)
                     for rid in np.unique(rooms) if rid > 0]
    room_polygons = [p for p in room_polygons if not p.is_empty]
    if not room_polygons:
        raise ValueError("No nonempty rooms available for extrusion")
    interior = unary_union(room_polygons)
    # Closing bridges only nearby room gaps, retaining courtyards wider than
    # the join distance. Subtracting rooms creates one solid shared wall.
    gap = max(2 * wall_thickness, 2 * tolerance)
    support = mask_geometry(np.isin(opening_data, [2, 3]), tolerance, 12)
    nearby = interior.buffer(2 * gap, join_style="mitre")
    support = unary_union([p for p in polygons(support) if p.intersects(nearby)])
    seed = interior.buffer(wall_thickness / 2, join_style="mitre").union(support)
    footprint = seed.buffer(gap, join_style="mitre").buffer(-gap, join_style="mitre")
    footprint = regularize(footprint, tolerance)
    wall_plan = make_valid(footprint.difference(interior))
    # Raw opening masks often stop at the visible wall face. Extend through
    # the entire shared wall rather than leaving a thin blocking membrane.
    clearance = max(opening_clearance, gap)
    door_candidates = opening_geometry(opening_data, 1, tolerance, clearance)
    window_candidates = opening_geometry(opening_data, 3, tolerance, clearance)
    doors = make_valid(wall_plan.intersection(door_candidates))
    windows = make_valid(wall_plan.intersection(window_candidates).difference(door_candidates))
    full = cross_section(wall_plan).extrude(wall_height)
    wall_solid = full
    if not doors.is_empty:
        wall_solid = wall_solid - cross_section(door_candidates).extrude(door_height + 1).translate((0, 0, -1))
    if not windows.is_empty and window_height > 0:
        window_cutter = cross_section(window_candidates.difference(door_candidates)).extrude(window_height)
        wall_solid = wall_solid - window_cutter.translate((0, 0, window_base_height))
    wall_solid = wall_solid.translate((0, 0, base_height))
    wall_mesh = solid_mesh(wall_solid)
    slab_thickness = max(1, wall_thickness)
    floor = solid_mesh(cross_section(footprint).extrude(slab_thickness).translate((0, 0, base_height-slab_thickness)))
    panes = []
    if window_height > 0:
        for poly in polygons(windows):
            if poly.area < 8:
                continue
            rect = np.asarray(poly.minimum_rotated_rectangle.exterior.coords[:-1])
            edges = np.roll(rect, -1, axis=0) - rect
            lengths = np.linalg.norm(edges, axis=1)
            idx = int(np.argmax(lengths))
            length = lengths[idx]
            direction = edges[idx] / length
            center = np.asarray(poly.centroid.coords[0])
            line = LineString([center-direction*length*.5, center+direction*length*.5])
            pane = line.buffer(min(.7, wall_thickness*.15), cap_style="flat").intersection(poly)
            if not pane.is_empty:
                panes.append(solid_mesh(cross_section(pane).extrude(window_height).translate((0, 0, base_height+window_base_height))))
    metadata = {
        "mode": "vector", "rooms": len(room_polygons),
        "door_opening_regions": sum(p.area >= 8 for p in polygons(doors)),
        "window_opening_regions": sum(p.area >= 8 for p in polygons(windows)),
        "wall_height": wall_height, "door_height": door_height,
        "window_sill": window_base_height, "window_height": window_height,
        "simplification_tolerance": tolerance, "units": "image pixels",
        "wall_volume": float(wall_solid.volume()),
        "wall_boundary_edges": wall_mesh.n_open_edges,
        "triangles": int(wall_mesh.n_cells+floor.n_cells+sum(p.n_cells for p in panes)),
    }
    return VectorScene([wall_mesh], panes, floor, metadata, wall_solid,
                       footprint, wall_plan, doors, windows)
