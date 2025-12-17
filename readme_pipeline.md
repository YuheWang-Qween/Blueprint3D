# Floor Plan Processing Pipeline

A complete, modular pipeline for floor plan analysis and 3D wall generation.

## 📁 Project Structure

```
project/
├── splitfloor/
│   ├── net.py              # SplitFloor model definition
│   ├── deploy.py           # Structure extraction deployment
│   └── checkpoints/
│       └── splitfloor_best_miou.pth
│
├── roomtype/
│   ├── net.py              # RoomSegNet model definition
│   ├── deploy.py           # Room type classification deployment
│   └── checkpoints/
│       └── best_roomseg_model.pth
│
├── extruder.py             # Core processing module
├── main.py                 # Pipeline orchestrator
└── README.md               # This file
```

## 🚀 Quick Start

### 1. Process an Image End-to-End

```bash
# Step 1: Extract structure (walls, windows)
cd splitfloor
python deploy.py --image ../floorplan.jpg --output ../output

# Step 2: Extract room types
cd ../roomtype
python deploy.py --image ../floorplan.jpg --output ../output

# Step 3: Run complete pipeline with 3D generation
cd ..
python main.py --input-dir output/ --3d
```

### 2. Run with Custom Parameters

```bash
python main.py \
    --input-dir output/ \
    --target-rooms 8 \
    --target-windows 10 \
    --wall-thickness 2 \
    --wall-height 80 \
    --3d
```

### 3. Process Specific CSV Files

```bash
python main.py \
    --rooms path/to/rooms.csv \
    --structure path/to/structure.csv \
    --3d
```

## 📦 Installation

### Required Dependencies

```bash
pip install numpy pandas torch torchvision opencv-python
pip install scipy scikit-image matplotlib pillow
pip install albumentations
```

### Optional Dependencies

```bash
# For GPU acceleration (recommended)
pip install cupy-cuda11x  # or cupy-cuda12x depending on CUDA version

# For 3D visualization (required for --3d flag)
pip install pyvista
```

## 📋 Module Documentation

### `splitfloor/deploy.py`

Extracts structural elements from floor plan images.

**Input:** Floor plan image (JPG, PNG)

**Output:**
- `structure.csv` - Class indices (0=background, 1=rooms, 2=walls, 3=windows)
- `structure_colored.png` - Color visualization
- `structure_raw.png` - Raw class indices

**Usage:**
```bash
python deploy.py --image input.jpg --output output_dir/
```

**Options:**
- `--weights`: Path to model weights (default: `checkpoints/splitfloor_best_miou.pth`)
- `--device`: Computation device (`cpu` or `cuda`)

---

### `roomtype/deploy.py`

Classifies room types from floor plan images.

**Input:** Floor plan image (JPG, PNG)

**Output:**
- `rooms.csv` - Room type indices
- `rooms_colored.png` - Color visualization
- `rooms_raw.png` - Raw class indices

**Usage:**
```bash
python deploy.py --image input.jpg --output output_dir/
```

**Options:**
- `--weights`: Path to model weights (default: `checkpoints/best_roomseg_model.pth`)
- `--threshold`: Binary threshold for room detection (default: 0.5)
- `--device`: Computation device (`cpu` or `cuda`)

---

### `main.py`

Orchestrates the complete pipeline from CSV inputs to final output.

**Input:** 
- `rooms.csv` - Room type data
- `structure.csv` - Structure data

**Output:**
- 2D visualization with rooms, walls, and windows
- Optional 3D model viewer

**Usage:**
```bash
# From directory
python main.py --input-dir output_dir/ [options]

# From specific files
python main.py --rooms rooms.csv --structure structure.csv [options]
```

**Processing Options:**
- `--target-rooms N`: Target number of room instances (default: 5)
- `--target-windows N`: Target number of windows (default: 5)
- `--door-width N`: Door width threshold in pixels (default: 30)
- `--wall-thickness N`: Wall thickness in pixels (default: 1)
- `--wall-continuity N`: Wall continuity/closing size (default: 1)

**3D Options:**
- `--3d`: Generate and display 3D model
- `--wall-height N`: 3D wall height (default: 60)
- `--window-sill N`: Window sill height (default: 15)
- `--window-height N`: Window opening height (default: 25)

**Visualization Options:**
- `--no-display`: Skip displaying visualization
- `--debug`: Show debug visualization layers

---

### `extruder.py`

Core processing module (not run directly, imported by `main.py`).

**Main Classes:**
- `FloorPlanProcessor`: Main processing pipeline

**Key Functions:**
- `segment_rooms()`: Room instance segmentation
- `generate_walls()`: Wall mask generation
- `process_windows()`: Window detection and merging
- `generate_3d_model()`: 3D mesh creation
- `visualize_2d()`: 2D visualization
- `display_3d_model()`: 3D visualization

## 🎯 Pipeline Workflow

```
Input Image
    ↓
┌───────────────────────┐
│  splitfloor/deploy.py │ → structure.csv
└───────────────────────┘
    ↓
┌───────────────────────┐
│  roomtype/deploy.py   │ → rooms.csv
└───────────────────────┘
    ↓
┌───────────────────────┐
│      main.py          │
│   ┌───────────────┐   │
│   │  extruder.py  │   │
│   │  - segment    │   │
│   │  - walls      │   │
│   │  - windows    │   │
│   │  - 3D gen     │   │
│   └───────────────┘   │
└───────────────────────┘
    ↓
2D Visualization + 3D Model
```

## 🔧 Configuration

### CSV Format

**rooms.csv:**
- No header, no index
- Integer values representing room types
- 0 = background, 1+ = room types
- Dimensions should match input image

**structure.csv:**
- No header, no index
- Integer values: 0=background, 1=rooms, 2=walls, 3=windows
- Dimensions should match input image

### Color Maps

Color mappings can be customized in deploy scripts:

```python
# In splitfloor/deploy.py
COLOR_MAP = {
    0: (255, 255, 255),  # Background - white
    1: (200, 200, 200),  # Rooms - light gray
    2: (0, 0, 0),        # Walls - black
    3: (0, 191, 255),    # Windows - blue
}

# In roomtype/deploy.py
ROOM_TYPE_NAMES = {
    0: "Background",
    1: "Living Room",
    2: "Bedroom",
    # ... customize as needed
}
```

## 💡 Examples

### Example 1: Basic Processing

```bash
# Process image with defaults
cd splitfloor
python deploy.py --image ../house.jpg --output ../results
cd ../roomtype
python deploy.py --image ../house.jpg --output ../results
cd ..
python main.py --input-dir results/
```

### Example 2: High-Detail Processing

```bash
# Extract more room instances and windows
python main.py --input-dir results/ \
    --target-rooms 12 \
    --target-windows 20 \
    --wall-thickness 2 \
    --wall-continuity 3
```

### Example 3: 3D Model Generation

```bash
# Generate tall walls with large windows
python main.py --input-dir results/ \
    --3d \
    --wall-height 100 \
    --window-sill 20 \
    --window-height 40
```

### Example 4: Debug Mode

```bash
# Show intermediate processing layers
python main.py --input-dir results/ --debug
```

## 🐛 Troubleshooting

### "Model weights not found"
Ensure checkpoint files are in the correct locations:
- `splitfloor/checkpoints/splitfloor_best_miou.pth`
- `roomtype/checkpoints/best_roomseg_model.pth`

### "Could not import net.py"
Make sure `net.py` files exist in both `splitfloor/` and `roomtype/` directories.

### "PyVista missing" when using --3d
Install PyVista: `pip install pyvista`

### GPU acceleration not working
Install CuPy matching your CUDA version:
```bash
# For CUDA 11.x
pip install cupy-cuda11x

# For CUDA 12.x
pip install cupy-cuda12x
```

### Dimension mismatch errors
Ensure both CSV files have the same dimensions. They should match the original image size.

## 📊 Performance

**CPU Performance:**
- Image processing: ~2-5 seconds per image
- 2D visualization: <1 second
- 3D generation: 1-3 seconds

**GPU Performance (with CuPy):**
- Image processing: ~0.5-1 second per image
- Significant speedup on large images (>1024x1024)

## 🔬 Advanced Usage

### Programmatic Usage

```python
from extruder import FloorPlanProcessor, visualize_2d, generate_and_display_3d
import numpy as np
import pandas as pd

# Load data
rooms = pd.read_csv("rooms.csv", header=None).values
structure = pd.read_csv("structure.csv", header=None).values

# Process
processor = FloorPlanProcessor()
results = processor.process(
    rooms_data=rooms,
    structure_data=structure,
    target_rooms=8,
    target_windows=12
)

# Visualize
visualize_2d(results, show_rooms=True, show_walls=True, show_windows=True)

# Generate 3D
generate_and_display_3d(
    final_walls=results['final_walls'],
    window_mask=results['window_mask'],
    wall_height=80,
    window_sill=20,
    window_height=30
)
```

### Custom Processing Parameters

```python
# Fine-tune room segmentation
results = processor.process(
    rooms_data=rooms,
    structure_data=structure,
    target_rooms=10,
    door_width=25,          # Narrower door detection
    separation_width=5,     # Wider separation between rooms
    wall_thickness=3,       # Thicker walls
    wall_continuity=4,      # More wall continuity
    window_extrusion=7,     # Larger window detection area
    target_windows=15
)
```

## 📝 Citation

If you use this pipeline in your research, please cite:

```bibtex
@software{floorplan_pipeline,
  title={Floor Plan Processing Pipeline},
  author={Your Name},
  year={2025},
  url={https://github.com/yourusername/floorplan-pipeline}
}
```

## 📄 License

MIT License - See LICENSE file for details

## 🤝 Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Submit a pull request

## 📧 Contact

For questions or issues, please open an issue on GitHub or contact [your-email@example.com]
