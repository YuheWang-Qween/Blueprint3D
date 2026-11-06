"""Check actual opening volumes, shared walls and courtyard preservation."""

import sys
import unittest
from pathlib import Path

import numpy as np
from shapely.geometry import GeometryCollection, Point, Polygon

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ForgeFloor'))
from vector_geometry import build_scene


def occupied(solid, x, y, z):
    section = GeometryCollection()
    for contour in solid.slice(z).to_polygons():
        section = section.symmetric_difference(Polygon(contour))
    return section.covers(Point(x, y))


class GeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rooms = np.zeros((120, 180), dtype=int)
        rooms[20:100, 20:80] = 1
        rooms[20:100, 90:150] = 2
        structures = np.zeros_like(rooms)
        structures[50:64, 78:93] = 1
        structures[18:24, 30:55] = 3
        cls.rooms, cls.structures = rooms, structures
        cls.scene = build_scene(rooms, structures, wall_height=40, door_height=30,
                               window_base_height=10, window_height=12, tolerance=1)

    def test_shared_wall_has_no_internal_gap(self):
        self.assertTrue(occupied(self.scene.wall_solid, 84, 85, 20))
        self.assertFalse(occupied(self.scene.wall_solid, 55, 85, 20))

    def test_door_is_open_below_lintel_but_closed_above(self):
        for x in (79, 84, 90):
            self.assertFalse(occupied(self.scene.wall_solid, x, 56, 15))
        self.assertTrue(occupied(self.scene.wall_solid, 84, 56, 35))

    def test_window_has_sill_opening_and_header(self):
        self.assertTrue(occupied(self.scene.wall_solid, 42, 18, 5))
        self.assertFalse(occupied(self.scene.wall_solid, 42, 18, 15))
        self.assertTrue(occupied(self.scene.wall_solid, 42, 18, 30))

    def test_solids_are_closed_and_compact(self):
        for mesh in self.scene.walls + self.scene.windows + [self.scene.floor]:
            self.assertEqual(mesh.n_open_edges, 0)
            self.assertGreater(mesh.volume, 0)
        self.assertLess(self.scene.metadata['triangles'], 1500)

    def test_courtyard_is_not_filled(self):
        rooms = np.zeros((140, 140), dtype=int)
        rooms[20:120, 20:120] = 1
        rooms[50:90, 50:90] = 0
        scene = build_scene(rooms, np.zeros_like(rooms), wall_height=40,
                            window_base_height=10, window_height=12)
        self.assertFalse(scene.footprint.covers(Point(70, 70)))

    def test_thin_false_door_does_not_open_wall(self):
        structures = np.zeros_like(self.rooms)
        structures[30:90, 84] = 1
        scene = build_scene(self.rooms, structures, wall_height=40,
                            window_base_height=10, window_height=12)
        self.assertEqual(scene.metadata['door_opening_regions'], 0)
        self.assertTrue(occupied(scene.wall_solid, 84, 60, 10))

    def test_invalid_dimensions_fail_explicitly(self):
        for changes in ({'wall_height':0}, {'door_height':201}, {'window_height':201}):
            with self.assertRaises(ValueError):
                build_scene(self.rooms, self.structures, **changes)
        with self.assertRaises(ValueError):
            build_scene(self.rooms, np.zeros((2, 2)))


if __name__ == '__main__':
    unittest.main()
