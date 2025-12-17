"""
morpho.py - 3D Floor Plan Extruder
===================================
Generates 3D models from processed architectural data.

Part of the Forgeplan pipeline.
"""

import numpy as np
import pyvista as pv
from skimage import measure, morphology
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
from PIL import Image
import os
from typing import Optional, Dict, Any


def apply_transformations(data, flip_y=False, flip_x=False, rotation=0):
    """Apply consistent transformations to 2D arrays."""
    result = data.copy()
    if flip_y:
        result = np.flipud(result)
    if flip_x:
        result = np.fliplr(result)
    if rotation != 0:
        k = (rotation // 90) % 4
        result = np.rot90(result, k=k)
    return result


def apply_transformations_to_image(img_array, flip_y=False, flip_x=False, rotation=0):
    """Apply consistent transformations to image arrays (H, W, C)."""
    result = img_array.copy()
    if flip_y:
        result = np.flipud(result)
    if flip_x:
        result = np.fliplr(result)
    if rotation != 0:
        k = (rotation // 90) % 4
        result = np.rot90(result, k=k)
    return result


def create_debug_visualization(rooms_data, struct_data, img_array,
                               contour_squareness, wall_thickness,
                               flip_y, flip_x, rotation, output_dir):
    """Create comprehensive 2D preview showing all transformations."""
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
    transform_info = f"Transforms: flip_y={flip_y}, flip_x={flip_x}, rotation={rotation}°"
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
    
    print(f"✅ Saved 2D preview: {os.path.basename(preview_path)}")
    
    return preview_room_boundaries, preview_path


class MorphoExtruder:
    """3D floor plan extruder."""
    
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
        show_interactive: bool = True
    ) -> Dict[str, Any]:
        """
        Extrude 3D floor plan from processed data.
        
        Returns:
            Dictionary with success status, file paths, and errors
        """
        result = {
            'success': False,
            'files': {},
            'errors': []
        }
        
        try:
            # Load data
            rooms_data_raw = np.loadtxt(rooms_csv, delimiter=',')
            struct_data_raw = np.loadtxt(struct_csv, delimiter=',')
            
            # Load image if provided
            img_array_raw = None
            if underlay_path and os.path.exists(underlay_path):
                try:
                    img = Image.open(underlay_path).convert('RGB')
                    img_array_raw = np.array(img)
                except Exception as e:
                    result['errors'].append(f"Could not load image: {e}")
            
            # Apply transformations
            rooms_data = apply_transformations(rooms_data_raw, flip_y, flip_x, rotation)
            struct_data = apply_transformations(struct_data_raw, flip_y, flip_x, rotation)
            
            img_array = None
            if img_array_raw is not None:
                # Resize image to match data if needed
                if img_array_raw.shape[:2] != rooms_data.shape:
                    img_resized = Image.fromarray(img_array_raw).resize(
                        (rooms_data.shape[1], rooms_data.shape[0]),
                        Image.Resampling.LANCZOS
                    )
                    img_array_raw = np.array(img_resized)
                
                img_array = apply_transformations_to_image(img_array_raw, flip_y, flip_x, rotation)
            
            # Create debug visualization
            _, preview_path = create_debug_visualization(
                rooms_data, struct_data, img_array,
                contour_squareness, wall_thickness,
                flip_y, flip_x, rotation, output_dir
            )
            result['files']['preview_png'] = preview_path
            
            # Build 3D model
            plotter = pv.Plotter(off_screen=not show_interactive)
            plotter.set_background("white")
            n_y, n_x = struct_data.shape
            
            unique_rooms = np.unique(rooms_data)
            unique_rooms = unique_rooms[unique_rooms > 0]
            
            # Window processing
            window_mask = (struct_data == 3)
            window_clearance = morphology.dilation(
                window_mask,
                morphology.square(int(wall_thickness + window_opening_clearance))
            )
            
            window_volumes = []
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
            
            # Room extrusion
            cmap = plt.get_cmap('Pastel1')
            all_meshes = []
            
            for i, room_id in enumerate(unique_rooms):
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
                
                color = cmap(i % 9)[:3]
                
                # Full height walls
                no_window_mask = full_wall_mask & ~window_clearance
                if np.any(no_window_mask):
                    grid = pv.ImageData(dimensions=(n_x, n_y, 1))
                    grid.origin = (0, 0, base_height)
                    grid.point_data["values"] = no_window_mask.flatten(order="C")
                    mesh = grid.threshold(0.5).extract_surface()
                    if mesh.n_points > 0:
                        wall_mesh = mesh.extrude((0, 0, room_height), capping=True)
                        all_meshes.append(wall_mesh)
                        plotter.add_mesh(wall_mesh, color=color, opacity=1.0,
                                       edge_color="black", show_edges=True)
                
                # Window-segmented walls
                window_overlap_mask = full_wall_mask & window_clearance
                if np.any(window_overlap_mask):
                    # Sill
                    grid_u = pv.ImageData(dimensions=(n_x, n_y, 1))
                    grid_u.origin = (0, 0, base_height)
                    grid_u.point_data["values"] = window_overlap_mask.flatten(order="C")
                    mesh_u = grid_u.threshold(0.5).extract_surface()
                    if mesh_u.n_points > 0:
                        sill_mesh = mesh_u.extrude((0, 0, window_base_height), capping=True)
                        all_meshes.append(sill_mesh)
                        plotter.add_mesh(sill_mesh, color=color, opacity=1.0,
                                       edge_color="black", show_edges=True)
                    
                    # Header
                    header_start = base_height + window_base_height + window_vertical_size
                    header_height = room_height - (window_base_height + window_vertical_size)
                    if header_height > 0:
                        grid_o = pv.ImageData(dimensions=(n_x, n_y, 1))
                        grid_o.origin = (0, 0, header_start)
                        grid_o.point_data["values"] = window_overlap_mask.flatten(order="C")
                        mesh_o = grid_o.threshold(0.5).extract_surface()
                        if mesh_o.n_points > 0:
                            header_mesh = mesh_o.extrude((0, 0, header_height), capping=True)
                            all_meshes.append(header_mesh)
                            plotter.add_mesh(header_mesh, color=color, opacity=1.0,
                                           edge_color="black", show_edges=True)
            
            # Add windows
            if show_windows:
                for win_mesh in window_volumes:
                    all_meshes.append(win_mesh)
                    plotter.add_mesh(win_mesh, color="#0000FF", opacity=0.6)
            
            # Add floor
            building_mask = rooms_data > 0
            
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
            
            room_colors = {}
            for i, room_id in enumerate(unique_rooms):
                c = cmap(i % 9)
                room_colors[room_id] = np.array(c[:3])
            
            for y in range(n_y):
                for x in range(n_x):
                    if building_mask[y, x]:
                        v0 = [x, y, base_height]
                        v1 = [x + 1, y, base_height]
                        v2 = [x + 1, y + 1, base_height]
                        v3 = [x, y + 1, base_height]
                        
                        vertices.extend([v0, v1, v2, v3])
                        faces.append([3, vertex_count, vertex_count + 1, vertex_count + 2])
                        faces.append([3, vertex_count, vertex_count + 2, vertex_count + 3])
                        
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
                        
                        for _ in range(4):
                            colors.append(final_color)
                        
                        vertex_count += 4
            
            if len(vertices) > 0:
                vertices = np.array(vertices)
                faces_array = np.array(faces).flatten()
                colors = np.array(colors)
                
                floor_mesh = pv.PolyData(vertices, faces_array)
                floor_mesh.point_data['colors'] = (colors * 255).astype(np.uint8)
                all_meshes.append(floor_mesh)
                
                plotter.add_mesh(floor_mesh, scalars='colors', rgb=True,
                               opacity=floor_opacity, show_edges=False)
            
            plotter.show_axes()
            
            # Export to OBJ
            if export_obj and len(all_meshes) > 0:
                combined_mesh = all_meshes[0]
                for mesh in all_meshes[1:]:
                    combined_mesh = combined_mesh.merge(mesh)
                
                obj_path = os.path.join(output_dir, 'floorplan_3d.obj')
                combined_mesh.save(obj_path)
                result['files']['obj_model'] = obj_path
                print(f"✅ Exported 3D model: {os.path.basename(obj_path)}")
            
            # Show or save screenshot
            if show_interactive:
                print("🎨 Opening interactive 3D viewer...")
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
        print("3D extrusion failed:")
        for error in result['errors']:
            print(f"  • {error}")