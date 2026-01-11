"""
Shape.py - Architectural Floor Plan Processor
==============================================
Processes semantic segmentation and structural data to generate
clean room segmentation and refined structural elements.

Part of the Forgeplan pipeline.
"""

import numpy as np
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend for CLI mode
import matplotlib.pyplot as plt
from scipy.ndimage import label, center_of_mass
from skimage import morphology, transform
from PIL import Image
import os
from typing import Optional, Dict, Any


class ShapeProcessor:
    """Processes architectural floor plans from semantic data."""
    
    def __init__(self):
        self.last_result = None
    
    def process(
        self,
        sema_path: Optional[str] = None,
        split_path: Optional[str] = None,
        underlay_path: Optional[str] = None,
        output_dir: str = 'outputs',
        smooth: int = 2,
        square: int = 3,
        struct_thickness: int = 5,
        alpha_underlay: float = 0.4,
        alpha_struct: float = 0.9,
        alpha_rooms: float = 0.4
    ) -> Dict[str, Any]:
        """
        Process floor plan data.
        
        Args:
            sema_path: Path to semantic segmentation CSV (optional)
            split_path: Path to structural split CSV (optional)
            underlay_path: Path to floor plan image (optional)
            output_dir: Output directory for results
            smooth: Morphological smoothing radius
            square: Squaring kernel size
            struct_thickness: Structural element thickness
            alpha_underlay: Underlay image opacity
            alpha_struct: Structure overlay opacity
            alpha_rooms: Room overlay opacity
        
        Returns:
            Dictionary with success status, file paths, and errors
        """
        result = {
            'success': False,
            'files': {},
            'errors': []
        }
        
        try:
            # Load data with graceful fallbacks
            sema = None
            split = None
            
            if sema_path and os.path.exists(sema_path):
                try:
                    sema = np.loadtxt(sema_path, delimiter=',')
                except Exception as e:
                    result['errors'].append(f"Failed to load sema.csv: {e}")
            
            if split_path and os.path.exists(split_path):
                try:
                    split = np.loadtxt(split_path, delimiter=',')
                except Exception as e:
                    result['errors'].append(f"Failed to load split.csv: {e}")
            
            # Check if we have enough data to proceed
            if sema is None and split is None:
                result['errors'].append("No valid input data (sema or split)")
                return result
            
            # Use split as base shape if sema is missing
            if sema is None and split is not None:
                sema = split.copy()
            elif split is None and sema is not None:
                split = np.zeros_like(sema)
            
            # Process the data
            rooms, final_struct, n_rooms = self._process_architecture(
                sema, split, smooth, square, struct_thickness
            )
            
            # Save outputs
            output_dir = os.path.abspath(output_dir)
            os.makedirs(output_dir, exist_ok=True)
            
            rooms_path = os.path.join(output_dir, 'room_segmentation.csv')
            struct_path = os.path.join(output_dir, 'structural_elements.csv')
            overlay_path = os.path.join(output_dir, 'architectural_overlay.png')
            
            np.savetxt(rooms_path, rooms, delimiter=',', fmt='%d')
            np.savetxt(struct_path, final_struct, delimiter=',', fmt='%d')
            
            result['files']['rooms_csv'] = rooms_path
            result['files']['struct_csv'] = struct_path
            
            # Create visualization
            self._create_visualization(
                rooms, final_struct, n_rooms,
                underlay_path, overlay_path,
                alpha_underlay, alpha_struct, alpha_rooms
            )
            
            result['files']['overlay_png'] = overlay_path
            result['success'] = True
            
            print(f"[INFO] Shape processing complete: {n_rooms} rooms detected")
            
        except Exception as e:
            result['errors'].append(f"Shape processing error: {e}")
            import traceback
            traceback.print_exc()
        
        self.last_result = result
        return result
    
    def _process_architecture(
        self, 
        sema: np.ndarray, 
        split: np.ndarray, 
        smooth: int, 
        square: int, 
        struct_thickness: int
    ):
        """
        Core processing logic for architectural elements.
        
        Returns:
            Tuple of (rooms, final_struct, n_rooms)
        """
        # Morphological straightening helper
        def refine(mask, sm, sq):
            m = morphology.binary_closing(mask > 0, morphology.disk(sm))
            return morphology.binary_opening(m, morphology.square(sq))
        
        # Clean the room mask (Class 1 in sema)
        clean_sema = refine(sema == 1, smooth, square)
        
        # Room segmentation
        rooms, n_rooms = label(clean_sema, structure=np.ones((3, 3)))
        room_mask = (rooms > 0)
        
        # Structure refinement with multi-class gap filling
        unique_classes = np.unique(split)
        unique_classes = unique_classes[unique_classes > 0]
        
        # Priority: Walls (2) < Doors (1) < Windows (3)
        processing_order = []
        if 2 in unique_classes: processing_order.append(2)  # Walls
        if 1 in unique_classes: processing_order.append(1)  # Doors
        if 3 in unique_classes: processing_order.append(3)  # Windows
        
        # Add any other classes
        for c in unique_classes:
            if c not in processing_order:
                processing_order.insert(0, c)
        
        # Prepare structure buffer
        final_struct = np.zeros_like(split, dtype=int)
        
        # Constrain expansion to structural vicinity
        original_struct_mask = (split > 0)
        constrained_limit = morphology.dilation(
            original_struct_mask, 
            morphology.square(struct_thickness)
        )
        
        for class_id in processing_order:
            class_mask = (split == class_id)
            
            # Special handling for windows
            if class_id == 3:
                refined_class = refine(class_mask, max(1, smooth), max(2, square))
            else:
                refined_class = refine(class_mask, smooth, square)
            
            # Expand to fill gaps
            if struct_thickness > 0:
                expanded_class = morphology.dilation(
                    refined_class, 
                    morphology.square(struct_thickness)
                )
                expanded_class = expanded_class & constrained_limit
            else:
                expanded_class = refined_class
            
            # Sequential overwriting based on priority
            final_struct[expanded_class] = int(class_id)
        
        # Rooms always take precedence over structure
        final_struct = np.where(room_mask, 0, final_struct)
        
        return rooms, final_struct, n_rooms
    
    def _create_visualization(
        self,
        rooms: np.ndarray,
        final_struct: np.ndarray,
        n_rooms: int,
        underlay_path: Optional[str],
        output_path: str,
        alpha_underlay: float,
        alpha_struct: float,
        alpha_rooms: float
    ):
        """Create and save the architectural overlay visualization."""
        fig, ax = plt.subplots(figsize=(14, 10))
        
        # Layer 1: Underlay sketch
        if underlay_path and os.path.exists(underlay_path):
            try:
                img = Image.open(underlay_path).convert('RGB')
                img_rescaled = transform.resize(
                    np.array(img), 
                    final_struct.shape, 
                    anti_aliasing=True
                )
                ax.imshow(img_rescaled, alpha=alpha_underlay)
            except Exception:
                ax.imshow(np.ones_like(final_struct), cmap='gray', 
                         vmin=0, vmax=1, alpha=0.1)
        else:
            ax.imshow(np.ones_like(final_struct), cmap='gray', 
                     vmin=0, vmax=1, alpha=0.1)
        
        # Layer 2: Structure
        struct_rgba = np.zeros((*final_struct.shape, 4))
        colors_map = {
            2: [0.17, 0.24, 0.31, alpha_struct],  # Walls - Dark Navy
            1: [0.60, 0.40, 0.20, alpha_struct],  # Doors - Brown
            3: [0.00, 0.80, 1.00, alpha_struct],  # Windows - Cyan
        }
        
        for val, color in colors_map.items():
            struct_rgba[final_struct == val] = color
        
        ax.imshow(struct_rgba, interpolation='nearest')
        
        # Layer 3: Rooms
        if n_rooms > 0:
            room_mask = (rooms > 0)
            room_rgba = plt.cm.Pastel1(rooms / max(n_rooms, 1))
            room_rgba[..., 3] = room_mask.astype(float) * alpha_rooms
            ax.imshow(room_rgba, interpolation='nearest')
            
            # Layer 4: Annotations
            centers = center_of_mass(room_mask, rooms, range(1, n_rooms + 1))
            for i, (y, x) in enumerate(centers, 1):
                if not np.isnan(y):
                    ax.text(x, y, f"Room {i}", color='black', weight='bold',
                           ha='center', va='center', fontsize=8,
                           bbox=dict(facecolor='white', alpha=0.8, 
                                   edgecolor='none', boxstyle='round,pad=0.2'))
        
        ax.set_title(f"Refined Architecture: {n_rooms} Rooms", 
                    fontsize=14, pad=20)
        ax.axis('off')
        plt.tight_layout()
        
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        plt.close(fig)
        
        print(f"[INFO] Saved visualization: {os.path.basename(output_path)}")


# Standalone execution for testing
if __name__ == "__main__":
    processor = ShapeProcessor()
    result = processor.process(
        sema_path='sema.csv',
        split_path='split.csv',
        underlay_path='input.jpeg',
        output_dir='outputs',
        smooth=1,
        square=1,
        struct_thickness=10,
        alpha_underlay=1.0,
        alpha_struct=0.8,
        alpha_rooms=0.5
    )
    
    if result['success']:
        print("Shape processing successful!")
        for name, path in result['files'].items():
            print(f"  {name}: {path}")
    else:
        print("[ERROR] Shape processing failed:")
        for error in result['errors']:
            print(f"  - {error}")