"""Run the upstream geometry pipeline on the author's recovered sample data.

The neural checkpoints are absent. This does not perform image inference.
Input CSVs and image are from upstream commit 5df980e.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ForgeFloor"))

from extruder import ForgePlanPipeline
from morpho import MorphoExtruder
import pyvista as pv


class CapturingExtruder(MorphoExtruder):
    """Keep the original generated geometry for a separate presentation render."""

    def _generate_windows(self, *args, **kwargs):
        self.windows = super()._generate_windows(*args, **kwargs)
        return self.windows

    def _generate_walls(self, *args, **kwargs):
        self.walls = super()._generate_walls(*args, **kwargs)
        return self.walls

    def _generate_floor(self, *args, **kwargs):
        self.floor = super()._generate_floor(*args, **kwargs)
        return self.floor


def main():
    sample = ROOT / "examples" / "historical-sample"
    out = ROOT / "outputs" / "historical-sample"
    out.mkdir(parents=True, exist_ok=True)
    pv.global_theme.window_size = [1600, 1200]
    pipeline = ForgePlanPipeline(output_dir=str(out), project_root=str(ROOT))
    capture = CapturingExtruder()
    pipeline.morpho_extruder = capture
    result = pipeline.run(
        geometry_mode='legacy',
        sema_path=str(sample / "sema.csv"),
        split_path=str(sample / "split.csv"),
        underlay_path=str(sample / "input.jpeg"),
        auto_neural=False,
        wall_height=200,
        room_height=200,
        wall_thickness=4,
        contour_squareness=1,
        flip_y=True,
        flip_x=False,
        rotation=0,
        floor_opacity=1,
        show_segmentation=False,
        show_interactive=False,
    )
    result["provenance"] = {
        "repository": "https://github.com/ashnomad/Blueprint3D",
        "code_commit": "bb4a4fd",
        "sample_commit": "5df980e2b845285d0e72199a7a7e01ef3b3fb572",
        "neural_inference_run": False,
        "units": "image pixels; no metric scale supplied",
        "wall_height": 200,
        "window_sill": 50,
        "window_height": 100,
        "orientation": "flip_y=True, flip_x=False, rotation=0",
    }
    if not result["success"]:
        (out / "result.json").write_text(json.dumps(result, indent=2))
        raise RuntimeError(result["errors"])
    blocks = pv.MultiBlock()
    for i, mesh in enumerate(capture.walls):
        blocks[f"wall_{i:02d}"] = mesh
    for i, mesh in enumerate(capture.windows):
        blocks[f"window_{i:02d}"] = mesh
    blocks["floor"] = capture.floor
    blocks.save(out / "scene.vtm")
    result["mesh_count"] = len(blocks)
    result["points"] = sum(m.n_points for m in blocks)
    result["cells"] = sum(m.n_cells for m in blocks)
    (out / "result.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
