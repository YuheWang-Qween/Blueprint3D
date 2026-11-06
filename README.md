# Floor Plan to 3D Pipeline

This project is a comprehensive solution for converting 2D floor plan images into interactive 3D models. It utilizes deep learning for semantic understanding and morphological image processing for 3D geometry generation.

## Pipeline Visualization

The following images demonstrate the complete workflow from floor plan input to 3D model output:

<table>
<tr>
<td width="50%">

### Original Floor Plan
![Floor Plan](images/input.png)
*Input floor plan with labeled offices and rooms*

</td>
<td width="50%">

### Semantic Segmentation Output
![Segmentation Map](images/sema.png)
*Colored segmentation map showing detected rooms and structural elements*

</td>
</tr>
<tr>
<td width="50%">

### Overlay Visualization
![Segmentation Overlay](images/split.png)
*Floor plan with color-coded segmentation overlay showing pipeline processing*

</td>
<td width="50%">

### 3D Extruded Model
![3D Model](images/model.png)
*Final 3D model with extruded walls and room structure*

</td>
</tr>
</table>

## Project Structure

The project is organized into three main modules:

1.  **SplitFloor**: A deep learning module responsible for detecting structural elements (Walls, Doors, Windows).
2.  **SemaFloor**: A deep learning module dedicated to detecting room boundaries and habitable areas.
3.  **ForgeFloor**: The core pipeline that orchestrates the neural networks, processes the geometric data, and extrudes the final 3D model.

## Installation

Ensure you have Python 3.10+ installed (the local preview was verified with Python 3.13). Install the required dependencies:

```bash
pip install torch torchvision numpy matplotlib opencv-python pillow pyvista scikit-image tqdm pandas albumentations scipy scikit-learn shapely manifold3d
```

*Note: A CUDA-capable GPU is recommended for training and fast inference.*

## Usage

### Local geometry improvements

The default geometry engine now vectorizes and regularizes room outlines, joins
shared walls, and cuts both door and window openings from closed wall solids.
The original pixel-based engine remains available with `--geometry_mode legacy`.
`--wall_height` controls wall height in vector mode; `--door_height` defaults to
80% of that height. Boolean options can be disabled, for example
`--no-show_interactive` for headless rendering.

To reproduce the included historical sample without neural checkpoints:

```bash
python -m pip install -r requirements-preview-lock.txt
python scripts/optimize_sample.py
python -m unittest discover -s tests -v
```

See [PREVIEW.md](PREVIEW.md) for local outputs, checkpoint provenance, and current
limitations. The historical CSV sample validates geometry generation. Separately,
two images have been tested through CPU neural inference and OBJ export using
locally downloaded checkpoints; this is a smoke test, not an accuracy benchmark.
Weights are not distributed with the code. `requirements-inference-lock.txt`
records the tested Python 3.13 inference environment.

### Reviewed floor-plan model

The [uploaded floor-plan example](examples/user-floorplan-2026-11-06/) includes
the source image, reviewed wall and door coordinates, and downloadable GLB/OBJ
models. Its background grid confused neural segmentation, so the delivered model
uses manually reviewed geometry. Dimensions are illustrative; wall height is
assumed to be 2.8 m.

![Reviewed floor-plan model](examples/user-floorplan-2026-11-06/model/preview.png)

To rebuild it without neural checkpoints:

```bash
python -m pip install -r requirements-model-lock.txt
python scripts/build_traced_plan.py
```

The main entry point for the pipeline is located in the `ForgeFloor` directory.

### Graphical User Interface (GUI)

To launch the interactive application with live preview:

```bash
python ForgeFloor/extruder.py --gui
```

### Command Line Interface (CLI)

To process an image automatically:

```bash
python ForgeFloor/extruder.py --input path/to/floorplan.jpg --auto --output_dir outputs/
```

## Workflow

1.  **Input**: A raw 2D floor plan image (JPG/PNG).
2.  **Inference**: 
    *   `SplitFloor` extracts structural masks (walls, windows, doors).
    *   `SemaFloor` extracts room masks.
3.  **Processing**: `ForgeFloor` cleans the masks using morphological operations.
4.  **Extrusion**: The cleaned 2D data is extruded into 3D meshes.
5.  **Output**: A 3D OBJ model, visualization overlays, and segmentation CSVs.
