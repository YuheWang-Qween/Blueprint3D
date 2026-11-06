"""
morpho.py - 3D Floor Plan Extruder
===================================
Generates 3D models from processed architectural data.

Part of the Forgeplan pipeline.
"""

import os
from typing import Any, Dict, List, Optional, Tuple

import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
import numpy as np
import pyvista as pv
from PIL import Image
from skimage import measure, morphology


def apply_transformations(data: np.ndarray, flip_y: bool = False, flip_x: bool = False, rotation: int = 0) -> np.ndarray:
    """
    Apply consistent geometric transformations (flip/rotate) to an array.
    
    Args:
        data: Input array (2D or 3D).
        flip_y: Whether to flip vertically.
        flip_x: Whether to flip horizontally.
        rotation: Rotation angle in degrees (0, 90, 180, 270).
        
    Returns:
        Transformed numpy array.
    """
    result = data.copy()
    if flip_y:
        result = np.flipud(result)
    if flip_x:
        result = np.fliplr(result)
    if rotation != 0:
        k = (rotation // 90) % 4
        result = np.rot90(result, k=k)
    return result


def create_debug_visualization(
    rooms_data: np.ndarray,
    struct_data: np.ndarray,
    img_array: Optional[np.ndarray],
    contour_squareness: int,
    wall_thickness: float,
    flip_y: bool,
    flip_x: bool,
    rotation: int,
    output_dir: str
) -> Tuple[np.ndarray, str]:
    """
    Create and save a comprehensive 2D preview showing all transformations.
    
    Returns:
        Tuple containing the room boundary mask and the path to the saved preview image.
    """
    unique_rooms = np.unique(rooms_data)
    unique_rooms = unique_rooms[unique_rooms > 0]
    
    # Create room boundary masks
    preview_room_boundaries = np.zeros_like(rooms_data)
    for room_id in unique_rooms:
        room_mask = (rooms_data == room_id)
        inner = morphology.binary_erosion(room_mask)
        boundary = room_mask ^ inner
        
        if contour_squareness > 0:
            boundary = morphology.binary_closing(boundary, morphology.square(contour_squareness))
            boundary = morphology.binary_opening(boundary, morphology.square(contour_squareness))
            
        if wall_thickness > 1:
            boundary = morphology.dilation(boundary, morphology.square(int(wall_thickness)))
            
        preview_room_boundaries[boundary] = room_id
    
    # Create window mask
    window_mask = (struct_data == 3)
    
    # Create figure with 4 subplots
    fig, axes = plt.subplots(2, 2, figsize=(16, 14))
    
    # Transform info for title
    transform_info = f"Transforms: flip_y={flip_y}, flip_x={flip_x}, rotation={rotation} deg"
    fig.suptitle(f'2D Preview - {transform_info}', fontsize=14, fontweight='bold')
    
    # Plot 1: Original floor plan image
    if img_array is not None:
        axes[0, 0].imshow(img_array, origin='lower')
        axes[0, 0].set_title("Floor Plan Image (Transformed)")
    else:
        axes[0, 0].text(0.5, 0.5, 'No Image', ha='center', va='center')
        axes[0, 0].set_title("Floor Plan Image (Not Available)")
    axes[0, 0].axis('off')
    
    # Plot 2: Room boundaries
    axes[0, 1].imshow(preview_room_boundaries, cmap='tab20', origin='lower')
    axes[0, 1].set_title("Room Boundary Masks")
    axes[0, 1].axis('off')
    
    # Plot 3: Window data
    axes[1, 0].imshow(window_mask, cmap='Blues', origin='lower')
    axes[1, 0].set_title("Window Data (Class 3)")
    axes[1, 0].axis('off')
    
    # Plot 4: Composite overlay
    if img_array is not None:
        axes[1, 1].imshow(img_array, origin='lower', alpha=0.7)
    
    # Overlay room boundaries
    boundary_overlay = np.ma.masked_where(preview_room_boundaries == 0, preview_room_boundaries)
    axes[1, 1].imshow(boundary_overlay, cmap='tab20', origin='lower', alpha=0.5)
    
    # Overlay windows
    window_overlay = np.ma.masked_where(~window_mask, window_mask)
    axes[1, 1].imshow(window_overlay, cmap='cool', origin='lower', alpha=0.6)
    
    axes[1, 1].set_title("Composite: Image + Boundaries + Windows")
    axes[1, 1].axis('off')
    
    plt.tight_layout()
    
    # Save preview
    preview_path = os.path.join(output_dir, '2d_preview.png')
    plt.savefig(preview_path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    
    print(f"[INFO] Saved 2D preview: {os.path.basename(preview_path)}")
    
    return preview_room_boundaries, preview_path


class MorphoExtruder:
    """
    Handles the extrusion of 2D floor plan data into 3D models.
    """
    
    def __init__(self):
        self.last_result = None
    
    def extrude(
        self,
        rooms_csv: str,
        struct_csv: str,
        underlay_path: Optional[str] = None,
        output_dir: str = 'outputs',
        wall_height: int = 50,
        room_height: int = 45,
        wall_thickness: float = 2.0,
        contour_squareness: int = 2,
        base_height: float = 0.0,
        window_base_height: float = 10.0,
        window_vertical_size: float = 15.0,
        show_windows: bool = True,
        window_opening_clearance: float = 1.0,
        floor_opacity: float = 0.5,
        flip_y: bool = False,
        flip_x: bool = False,
        rotation: int = 0,
        show_input_image: bool = True,
        show_segmentation: bool = True,
        input_image_opacity: float = 0.7,
        segmentation_opacity: float = 0.3,
        export_obj: bool = True,
        show_interactive: bool = True,
        geometry_mode: str = 'vector',
        door_height: Optional[float] = None,
        opening_struct_csv: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate a 3D model from processed floor plan data.
        
        Args:
            rooms_csv: Path to the CSV file containing room segmentation data.
            struct_csv: Path to the CSV file containing structural element data.
            underlay_path: Path to the original floor plan image (optional).
            output_dir: Directory to save output files.
            wall_height: Height of the walls in 3D units.
            room_height: Height of the room volumes.
            wall_thickness: Thickness of the walls in pixels.
            contour_squareness: Kernel size for morphological squaring of contours.
            base_height: Base elevation for the model.
            window_base_height: Height of the window sill from the floor.
            window_vertical_size: Height of the window opening.
            show_windows: Whether to generate window geometries.
            window_opening_clearance: Clearance around window openings.
            floor_opacity: Opacity of the floor mesh.
            flip_y: Flip data vertically.
            flip_x: Flip data horizontally.
            rotation: Rotate data (0, 90, 180, 270 degrees).
            show_input_image: Project the input image onto the floor.
            show_segmentation: Overlay room segmentation colors on the floor.
            input_image_opacity: Opacity of the projected image.
            segmentation_opacity: Opacity of the segmentation overlay.
            export_obj: Whether to export the model as an OBJ file.
            show_interactive: Whether to open an interactive 3D viewer.
            geometry_mode: 'vector' for unified solids, 'legacy' for pixel extrusion.
            door_height: Door opening height; defaults to 80% of wall_height.
            opening_struct_csv: Raw structural mask used to avoid expanded noise.
        
        Returns:
            Dictionary containing success status, generated file paths, and any errors.
        """
        result = {
            'success': False,
            'files': {},
            'errors': []
        }
        
        try:
            os.makedirs(output_dir, exist_ok=True)
            if geometry_mode not in ('vector', 'legacy'):
                raise ValueError("geometry_mode must be 'vector' or 'legacy'")
            # 1. Load Data
            rooms_data, struct_data, img_array = self._load_and_transform_data(
                rooms_csv, struct_csv, underlay_path, flip_y, flip_x, rotation, result
            )
            
            # 2. Create Debug Visualization
            _, preview_path = create_debug_visualization(
                rooms_data, struct_data, img_array,
                contour_squareness, wall_thickness,
                flip_y, flip_x, rotation, output_dir
            )
            result['files']['preview_png'] = preview_path

            if geometry_mode == 'vector':
                opening_data = struct_data
                if opening_struct_csv is not None:
                    opening_data = apply_transformations(
                        np.loadtxt(opening_struct_csv, delimiter=','), flip_y, flip_x, rotation
                    )
                self._extrude_vector(
                    rooms_data, struct_data, opening_data, img_array, output_dir,
                    wall_height, wall_thickness, contour_squareness, base_height,
                    window_base_height, window_vertical_size, door_height,
                    window_opening_clearance, show_windows, floor_opacity,
                    show_input_image, show_segmentation, input_image_opacity,
                    segmentation_opacity, export_obj, show_interactive, result,
                )
                result['success'] = True
                self.last_result = result
                return result
            
            # 3. Initialize 3D Plotter
            plotter = pv.Plotter(off_screen=not show_interactive)
            plotter.set_background("white")
            
            all_meshes = []
            
            # 4. Generate Windows
            window_volumes = []
            if show_windows:
                window_volumes = self._generate_windows(
                    struct_data, base_height, window_base_height, window_vertical_size
                )
                for win_mesh in window_volumes:
                    all_meshes.append(win_mesh)
                    plotter.add_mesh(win_mesh, color="#0000FF", opacity=0.6)
            
            # 5. Generate Walls
            # Note: Passing room_height as the wall height to match original behavior
            wall_meshes = self._generate_walls(
                rooms_data, struct_data, wall_thickness, contour_squareness,
                room_height, base_height, window_base_height, window_vertical_size,
                window_opening_clearance
            )
            
            cmap = plt.get_cmap('Pastel1')
            for i, mesh in enumerate(wall_meshes):
                all_meshes.append(mesh)
                color = cmap(i % 9)[:3]
                plotter.add_mesh(mesh, color=color, opacity=1.0, edge_color="black", show_edges=True)
            
            # 6. Generate Floor
            floor_mesh = self._generate_floor(
                rooms_data, img_array, base_height, floor_opacity,
                show_input_image, show_segmentation,
                input_image_opacity, segmentation_opacity, cmap
            )
            
            if floor_mesh:
                all_meshes.append(floor_mesh)
                plotter.add_mesh(floor_mesh, scalars='colors', rgb=True, opacity=floor_opacity, show_edges=False)
            
            plotter.show_axes()
            
            # 7. Export and Finalize
            if export_obj and all_meshes:
                self._export_obj(all_meshes, output_dir, result)
            
            if show_interactive:
                print("[INFO] Opening interactive 3D viewer...")
                plotter.show()
            else:
                screenshot_path = os.path.join(output_dir, '3d_render.png')
                plotter.screenshot(screenshot_path)
                result['files']['render_png'] = screenshot_path
                plotter.close()
            
            result['success'] = True
            
        except Exception as e:
            result['errors'].append(f"3D extrusion error: {e}")
            import traceback
            traceback.print_exc()
        
        self.last_result = result
        return result

    def _extrude_vector(
        self, rooms_data, struct_data, opening_data, img_array, output_dir,
        wall_height, wall_thickness, contour_squareness, base_height,
        window_base_height, window_vertical_size, door_height, clearance,
        show_windows, floor_opacity, show_input_image, show_segmentation,
        image_opacity, segmentation_opacity, export_obj, show_interactive, result,
    ):
        from vector_geometry import build_scene

        scene = build_scene(
            rooms_data, struct_data, opening_data=opening_data,
            wall_height=wall_height, wall_thickness=wall_thickness,
            tolerance=max(1., float(contour_squareness), wall_thickness/2),
            base_height=base_height, window_base_height=window_base_height,
            window_height=window_vertical_size, door_height=door_height,
            opening_clearance=clearance,
        )
        self.last_scene = scene
        self.walls, self.windows, self.floor = scene.walls, scene.windows, scene.floor
        result['geometry'] = scene.metadata
        all_meshes = list(scene.walls) + (scene.windows if show_windows else []) + [scene.floor]
        blocks = pv.MultiBlock()
        for i, mesh in enumerate(scene.walls):
            blocks[f'wall_{i:02d}'] = mesh
        if show_windows:
            for i, mesh in enumerate(scene.windows):
                blocks[f'window_{i:02d}'] = mesh
        blocks['floor'] = scene.floor
        scene_path = os.path.join(output_dir, 'scene.vtm')
        blocks.save(scene_path)
        result['files']['scene_vtm'] = scene_path
        if export_obj:
            self._export_obj(all_meshes, output_dir, result)
        plotter = pv.Plotter(off_screen=not show_interactive, window_size=(1600, 1280))
        try:
            plotter.set_background('#f4f3ef')
            for mesh in scene.walls:
                plotter.add_mesh(mesh, color='#e6e2da', show_edges=False,
                                 ambient=.35, diffuse=.65, smooth_shading=False)
            if show_windows:
                for mesh in scene.windows:
                    plotter.add_mesh(mesh, color='#88b8c7', opacity=.3, show_edges=False)
            floor_texture = None
            if (show_input_image and img_array is not None) or show_segmentation:
                blended = np.zeros((*rooms_data.shape, 3), dtype=float)
                weight = 0.
                if show_input_image and img_array is not None and image_opacity > 0:
                    blended += img_array[..., :3] * image_opacity
                    weight += image_opacity
                if show_segmentation and segmentation_opacity > 0:
                    colors = plt.get_cmap('Pastel1')
                    segmentation = np.full_like(blended, 235)
                    for i, rid in enumerate(np.unique(rooms_data[rooms_data > 0])):
                        segmentation[rooms_data == rid] = np.asarray(colors(i % 9)[:3]) * 255
                    blended += segmentation * segmentation_opacity
                    weight += segmentation_opacity
                if weight > 0:
                    tex = np.clip(blended / weight, 0, 255).astype(np.uint8)
                    self.floor.active_texture_coordinates = self.floor.points[:, :2] / np.array([rooms_data.shape[1]-1, rooms_data.shape[0]-1])
                    floor_texture = pv.numpy_to_texture(np.flipud(tex))
            plotter.add_mesh(self.floor, color='#d8c9b2', texture=floor_texture,
                             opacity=floor_opacity, show_edges=False, ambient=.35)
            center = np.asarray(blocks.center)
            span = max(blocks.bounds[1]-blocks.bounds[0], blocks.bounds[3]-blocks.bounds[2])
            plotter.camera_position = [center+span*np.array([1.3, -1.8, 2.1]), center, (0, 0, 1)]
            plotter.enable_parallel_projection()
            plotter.reset_camera()
            plotter.camera.zoom(1.05)
            plotter.enable_anti_aliasing('ssaa')
            if show_interactive:
                plotter.show()
            else:
                render_path = os.path.join(output_dir, '3d_render.png')
                plotter.screenshot(render_path)
                result['files']['render_png'] = render_path
        finally:
            plotter.close()

    def _load_and_transform_data(
        self, rooms_csv, struct_csv, underlay_path, flip_y, flip_x, rotation, result
    ):
        """Load CSVs and image, and apply transformations."""
        rooms_data_raw = np.loadtxt(rooms_csv, delimiter=',')
        struct_data_raw = np.loadtxt(struct_csv, delimiter=',')
        
        img_array_raw = None
        if underlay_path and os.path.exists(underlay_path):
            try:
                img = Image.open(underlay_path).convert('RGB')
                img_array_raw = np.array(img)
            except Exception as e:
                result['errors'].append(f"Could not load image: {e}")
        
        rooms_data = apply_transformations(rooms_data_raw, flip_y, flip_x, rotation)
        struct_data = apply_transformations(struct_data_raw, flip_y, flip_x, rotation)
        
        img_array = None
        if img_array_raw is not None:
            # Resize image to match data dimensions if needed
            if img_array_raw.shape[:2] != rooms_data.shape:
                img_resized = Image.fromarray(img_array_raw).resize(
                    (rooms_data.shape[1], rooms_data.shape[0]),
                    Image.Resampling.LANCZOS
                )
                img_array_raw = np.array(img_resized)
            
            img_array = apply_transformations(img_array_raw, flip_y, flip_x, rotation)
            
        return rooms_data, struct_data, img_array

    def _generate_windows(self, struct_data, base_height, window_base_height, window_vertical_size):
        """Generate 3D volumes for windows."""
        window_mask = (struct_data == 3)
        window_volumes = []
        n_y, n_x = struct_data.shape
        
        if np.any(window_mask):
            labeled_windows, n_windows = measure.label(window_mask, return_num=True)
            for w_id in range(1, n_windows + 1):
                mask = (labeled_windows == w_id)
                grid = pv.ImageData(dimensions=(n_x, n_y, 1))
                grid.origin = (0, 0, base_height + window_base_height)
                grid.point_data["values"] = mask.flatten(order="C")
                
                mesh = grid.threshold(0.5).extract_surface()
                if mesh.n_points > 0:
                    extruded = mesh.extrude((0, 0, window_vertical_size), capping=True)
                    window_volumes.append(extruded)
        return window_volumes

    def _generate_walls(
        self, rooms_data, struct_data, wall_thickness, contour_squareness,
        wall_height, base_height, window_base_height, window_vertical_size,
        window_opening_clearance
    ):
        """Generate 3D meshes for walls, handling window cutouts."""
        unique_rooms = np.unique(rooms_data)
        unique_rooms = unique_rooms[unique_rooms > 0]
        n_y, n_x = rooms_data.shape
        
        window_mask = (struct_data == 3)
        window_clearance = morphology.dilation(
            window_mask,
            morphology.square(int(wall_thickness + window_opening_clearance))
        )
        
        wall_meshes = []
        
        for room_id in unique_rooms:
            room_mask = (rooms_data == room_id)
            inner = morphology.binary_erosion(room_mask)
            boundary_mask = room_mask ^ inner
            
            if contour_squareness > 0:
                boundary_mask = morphology.binary_closing(
                    boundary_mask, morphology.square(contour_squareness)
                )
                boundary_mask = morphology.binary_opening(
                    boundary_mask, morphology.square(contour_squareness)
                )
            
            if wall_thickness > 1:
                full_wall_mask = morphology.dilation(
                    boundary_mask, morphology.square(int(wall_thickness))
                )
            else:
                full_wall_mask = boundary_mask
            
            # 1. Full height walls (where no windows exist)
            no_window_mask = full_wall_mask & ~window_clearance
            if np.any(no_window_mask):
                grid = pv.ImageData(dimensions=(n_x, n_y, 1))
                grid.origin = (0, 0, base_height)
                grid.point_data["values"] = no_window_mask.flatten(order="C")
                mesh = grid.threshold(0.5).extract_surface()
                if mesh.n_points > 0:
                    wall_mesh = mesh.extrude((0, 0, wall_height), capping=True)
                    wall_meshes.append(wall_mesh)
            
            # 2. Window-segmented walls (Sill and Header)
            window_overlap_mask = full_wall_mask & window_clearance
            if np.any(window_overlap_mask):
                # Sill (below window)
                grid_u = pv.ImageData(dimensions=(n_x, n_y, 1))
                grid_u.origin = (0, 0, base_height)
                grid_u.point_data["values"] = window_overlap_mask.flatten(order="C")
                mesh_u = grid_u.threshold(0.5).extract_surface()
                if mesh_u.n_points > 0:
                    sill_mesh = mesh_u.extrude((0, 0, window_base_height), capping=True)
                    wall_meshes.append(sill_mesh)
                
                # Header (above window)
                header_start = base_height + window_base_height + window_vertical_size
                header_height = wall_height - (window_base_height + window_vertical_size)
                
                if header_height > 0:
                    grid_o = pv.ImageData(dimensions=(n_x, n_y, 1))
                    grid_o.origin = (0, 0, header_start)
                    grid_o.point_data["values"] = window_overlap_mask.flatten(order="C")
                    mesh_o = grid_o.threshold(0.5).extract_surface()
                    if mesh_o.n_points > 0:
                        header_mesh = mesh_o.extrude((0, 0, header_height), capping=True)
                        wall_meshes.append(header_mesh)
                        
        return wall_meshes

    def _generate_floor(
        self, rooms_data, img_array, base_height, floor_opacity,
        show_input_image, show_segmentation, input_image_opacity,
        segmentation_opacity, cmap
    ):
        """Generate the floor mesh with vertex colors."""
        building_mask = rooms_data > 0
        n_y, n_x = rooms_data.shape
        
        # Validate display options
        if not show_input_image and not show_segmentation:
            show_segmentation = True
        if show_input_image and img_array is None:
            show_input_image = False
            show_segmentation = True
        
        vertices = []
        faces = []
        colors = []
        vertex_count = 0
        
        unique_rooms = np.unique(rooms_data)
        unique_rooms = unique_rooms[unique_rooms > 0]
        room_colors = {rid: np.array(cmap(i % 9)[:3]) for i, rid in enumerate(unique_rooms)}
        
        # Note: This loop is kept explicit for readability and custom blending logic.
        # Vectorization is possible but complex due to the blending requirements.
        for y in range(n_y):
            for x in range(n_x):
                if building_mask[y, x]:
                    # Create a quad for this pixel
                    v0 = [x, y, base_height]
                    v1 = [x + 1, y, base_height]
                    v2 = [x + 1, y + 1, base_height]
                    v3 = [x, y + 1, base_height]
                    
                    vertices.extend([v0, v1, v2, v3])
                    faces.append([3, vertex_count, vertex_count + 1, vertex_count + 2])
                    faces.append([3, vertex_count, vertex_count + 2, vertex_count + 3])
                    
                    # Calculate color
                    final_color = np.array([0.0, 0.0, 0.0])
                    total_weight = 0.0
                    
                    if show_input_image and img_array is not None:
                        img_color = img_array[y, x, :3] / 255.0
                        final_color += img_color * input_image_opacity
                        total_weight += input_image_opacity
                    
                    if show_segmentation:
                        room_id = rooms_data[y, x]
                        if room_id in room_colors:
                            room_color = room_colors[room_id]
                            final_color += room_color * segmentation_opacity
                            total_weight += segmentation_opacity
                    
                    if total_weight > 0:
                        final_color = final_color / total_weight
                    
                    final_color = np.clip(final_color, 0.0, 1.0)
                    
                    # Assign color to all 4 vertices of the quad
                    for _ in range(4):
                        colors.append(final_color)
                    
                    vertex_count += 4
        
        if not vertices:
            return None
            
        vertices = np.array(vertices)
        faces_array = np.array(faces).flatten()
        colors = np.array(colors)
        
        floor_mesh = pv.PolyData(vertices, faces_array)
        floor_mesh.point_data['colors'] = (colors * 255).astype(np.uint8)
        return floor_mesh

    def _export_obj(self, all_meshes, output_dir, result):
        """Combine and export meshes to OBJ."""
        combined_mesh = all_meshes[0]
        for mesh in all_meshes[1:]:
            combined_mesh = combined_mesh.merge(mesh)
        
        obj_path = os.path.join(output_dir, 'floorplan_3d.obj')
        combined_mesh.save(obj_path)
        result['files']['obj_model'] = obj_path
        print(f"[INFO] Exported 3D model: {os.path.basename(obj_path)}")


# Standalone execution for testing
if __name__ == "__main__":
    extruder = MorphoExtruder()
    result = extruder.extrude(
        rooms_csv='outputs/room_segmentation.csv',
        struct_csv='outputs/structural_elements.csv',
        underlay_path='input.jpeg',
        output_dir='outputs',
        wall_height=200,
        room_height=200,
        wall_thickness=4,
        flip_y=True,
        flip_x=True,
        rotation=180,
        show_segmentation=True,
        export_obj=True,
        show_interactive=True
    )
    
    if result['success']:
        print("3D extrusion successful!")
        for name, path in result['files'].items():
            print(f"  {name}: {path}")
    else:
        print("[ERROR] 3D extrusion failed:")
        for error in result['errors']:
            print(f"  - {error}")
