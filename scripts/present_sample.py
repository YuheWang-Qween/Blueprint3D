"""Render captured upstream meshes and prepare a small interactive mesh payload."""

import json
from pathlib import Path

import numpy as np
import pyvista as pv

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "historical-sample"


def main():
    blocks = pv.read(OUT / "scene.vtm")
    payload = []
    plotter = pv.Plotter(off_screen=True, window_size=(1800, 1450))
    plotter.set_background("#f4f3ef")
    for name, mesh in zip(blocks.keys(), blocks):
        kind = name.split("_")[0]
        if kind == "floor":
            plotter.add_mesh(mesh, color="#e3d7c4", show_edges=False, ambient=0.35)
        elif kind == "wall":
            plotter.add_mesh(mesh, color="#f3f0e8", show_edges=False,
                             ambient=0.25, diffuse=0.8, smooth_shading=False)
        else:
            plotter.add_mesh(mesh, color="#88b8c7", opacity=0.30,
                             show_edges=False, ambient=0.4)
        simple = mesh.triangulate().clean()
        before = simple.n_cells
        if before > 1000:
            simple = simple.decimate_pro(
                0.99, preserve_topology=True, feature_angle=25,
                splitting=False, boundary_vertex_deletion=True,
            )
        simple = simple.clean()
        simple.save(OUT / f"preview_{name}.vtp")
        payload.append({
            "name": name,
            "kind": kind,
            "positions": np.round(simple.points, 2).reshape(-1).tolist(),
            "indices": simple.faces.reshape(-1, 4)[:, 1:].reshape(-1).tolist(),
        })
        print(name, before, "->", simple.n_cells, flush=True)
    center = np.array(blocks.center)
    plotter.enable_parallel_projection()
    plotter.camera_position = [center + np.array([950, -1300, 1550]), center, (0, 0, 1)]
    plotter.reset_camera()
    plotter.camera.zoom(1.15)
    plotter.enable_anti_aliasing("ssaa")
    plotter.screenshot(OUT / "preview.png")
    plotter.view_xy()
    plotter.reset_camera()
    plotter.camera.zoom(1.12)
    plotter.screenshot(OUT / "top-view.png")
    plotter.close()
    destination = OUT / "preview-mesh.json"
    destination.write_text(json.dumps(payload, separators=(",", ":")))
    print("Mesh payload bytes:", destination.stat().st_size, flush=True)


if __name__ == "__main__":
    main()
