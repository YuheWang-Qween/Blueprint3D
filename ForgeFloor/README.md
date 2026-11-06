# ForgeFloor

ForgeFloor is the orchestration and 3D generation engine of the pipeline. It combines the outputs from the neural networks to build a clean 3D representation of the floor plan.

## Key Components

### `extruder.py`
The main application script.
- **Orchestrator**: Manages the execution of `SplitFloor` and `SemaFloor` inference.
- **GUI**: Provides a Tkinter-based interface with live 2D preview and parameter tuning.
- **Pipeline**: Connects raw inputs to the final 3D output.

### `Shape.py`
Handles 2D geometric processing.
- Cleans up segmentation masks using morphological operations (smoothing, squaring).
- Separates connected components into distinct rooms.
- Refines structural elements to ensure clean wall geometry.

### `morpho.py`
The 3D extrusion engine.
- Uses `pyvista` to convert processed 2D masks into 3D meshes.
- Generates walls, windows (with cutouts), and floors.
- Exports the final scene to `.obj` format.

### `auth.py`
Local authentication for the desktop GUI.
- Stores accounts in `users.json` next to this file (PBKDF2-hashed passwords).
- Shows the blueprint-styled login window (sign in / register) before the main GUI opens.

## Usage

Run the extruder script from this directory:

```bash
# Launch GUI
python extruder.py --gui

# Run in automatic mode via CLI
python extruder.py --input ../input.jpg --auto --output_dir ../outputs
```

*Note: Ensure `SplitFloor` and `SemaFloor` directories are accessible relative to the project root.*