"""
FORGEPLAN - 2D to 3D Floor Plan Pipeline (Enhanced with Live Preview)
======================================================================
Main orchestrator with automatic neural network inference integration
and real-time 2D preview.

Usage:
    Auto mode: python extruder.py --input floorplan.jpg --auto
    Manual mode: python extruder.py --sema sema.csv --split split.csv
    GUI: python extruder.py --gui

Author: Floor Plan CV Backend - Enhanced Edition with Live Preview
"""

import os
import sys
import argparse
import subprocess
import shutil
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
import threading
import time

# Core pipeline imports
try:
    from Shape import ShapeProcessor
    from morpho import MorphoExtruder
except ImportError as e:
    print(f"Error importing modules: {e}")
    print("Make sure Shape.py and morpho.py are in the same directory.")
    sys.exit(1)


class NeuralInferenceOrchestrator:
    """Manages SplitFloor and SemaFloor neural network inference."""
    
    def __init__(self, project_root: str = '.'):
        """
        Initialize orchestrator.
        
        Args:
            project_root: Root directory containing SplitFloor/ and SemaFloor/
        """
        self.project_root = Path(project_root).expanduser().resolve()
        self.splitfloor_dir = self.project_root / 'SplitFloor'
        self.semafloor_dir = self.project_root / 'SemaFloor'
        
    def check_dependencies(self) -> Dict[str, bool]:
        """Check if neural network modules are available."""
        status = {
            'splitfloor_exists': (self.splitfloor_dir / 'deploy.py').exists(),
            'semafloor_exists': (self.semafloor_dir / 'deploy_sema.py').is_file(),
            'splitfloor_checkpoint': (self.splitfloor_dir / 'checkpoints/splitfloor_best_miou.pth').is_file(),
            'semafloor_checkpoint': (self.semafloor_dir / 'checkpoints/best_semafloor_model.pth').is_file()
        }
        return status
    
    def run_splitfloor(
        self, 
        image_path: str, 
        output_dir: str,
        callback=None
    ) -> Tuple[bool, Dict[str, str], str]:
        """
        Run SplitFloor inference.
        
        Args:
            image_path: Input floor plan image
            output_dir: Directory to store outputs
            callback: Progress callback function
            
        Returns:
            (success, files_dict, error_message)
        """
        if callback:
            callback("[INFO] Running SplitFloor structural extraction...", 15)

        image_path = str(Path(image_path).expanduser().resolve())
        output_dir = str(Path(output_dir).expanduser().resolve())
        
        deploy_script = self.splitfloor_dir / 'deploy.py'
        
        if not deploy_script.exists():
            return False, {}, f"SplitFloor deploy script not found at {deploy_script}"
        
        # Create temporary output directory for SplitFloor
        temp_dir = Path(output_dir) / 'splitfloor_temp'
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            # Run SplitFloor as subprocess
            cmd = [
                sys.executable,
                str(deploy_script),
                '--image', image_path,
                '--output_dir', str(temp_dir),
            ]
            
            # Change to SplitFloor directory to ensure relative paths work
            result = subprocess.run(
                cmd,
                cwd=str(self.splitfloor_dir),
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            if result.returncode != 0:
                error_msg = f"SplitFloor failed:\n{result.stderr}"
                return False, {}, error_msg
            
            # Collect output files (from deploy_split.py)
            expected_files = {
                'split_csv': 'output_mask.csv',
                'split_mask_raw': 'output_mask_raw.png',
                'split_mask_color': 'output_mask_colored.png'
            }
            
            files = {}
            missing_files = []
            
            for key, filename in expected_files.items():
                src_path = temp_dir / filename
                if src_path.exists():
                    # Move to output directory
                    dest_path = Path(output_dir) / f"split_{filename}"
                    shutil.copy(src_path, dest_path)
                    files[key] = str(dest_path)
                    
                    # Also create expected name for pipeline
                    if key == 'split_csv':
                        pipeline_path = Path(output_dir) / 'split.csv'
                        shutil.copy(src_path, pipeline_path)
                        files['split_csv_pipeline'] = str(pipeline_path)
                else:
                    missing_files.append(filename)
            
            if missing_files:
                return False, files, f"Missing SplitFloor outputs: {missing_files}"
            
            if callback:
                callback("[SUCCESS] SplitFloor complete", 25)
            
            return True, files, ""
            
        except subprocess.TimeoutExpired:
            return False, {}, "SplitFloor inference timed out (>5 minutes)"
        except Exception as e:
            return False, {}, f"SplitFloor error: {str(e)}"
    
    def run_semafloor(
        self, 
        image_path: str, 
        output_dir: str,
        callback=None
    ) -> Tuple[bool, Dict[str, str], str]:
        """
        Run SemaFloor inference.
        
        Args:
            image_path: Input floor plan image
            output_dir: Directory to store outputs
            callback: Progress callback function
            
        Returns:
            (success, files_dict, error_message)
        """
        if callback:
            callback("[INFO] Running SemaFloor semantic segmentation...", 30)
        
        deploy_script = self.semafloor_dir / 'deploy_sema.py'
        
        if not deploy_script.exists():
            return False, {}, f"SemaFloor deploy script not found at {deploy_script}"
        
        try:
            image_path = str(Path(image_path).expanduser().resolve())
            output_dir = str(Path(output_dir).expanduser().resolve())
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            # Pass paths as arguments, avoiding generated Python source and
            # allowing spaces, non-ASCII characters and apostrophes in names.
            result = subprocess.run(
                [sys.executable, str(deploy_script), '--image', image_path,
                 '--output_dir', output_dir],
                cwd=str(self.semafloor_dir),
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode != 0:
                error_msg = f"SemaFloor failed:\n{result.stderr}"
                return False, {}, error_msg
            
            # Collect output files
            input_basename = Path(image_path).stem
            expected_files = {
                'sema_csv': 'sema.csv',
                'sema_mask': f'{input_basename}_predicted_mask.png',
                'sema_overlay': f'{input_basename}_overlay.png'
            }
            
            files = {}
            missing_files = []
            
            for key, filename in expected_files.items():
                src_path = Path(output_dir) / filename
                if src_path.exists():
                    files[key] = str(src_path)
                else:
                    missing_files.append(filename)
            
            if missing_files:
                return False, files, f"Missing SemaFloor outputs: {missing_files}"
            
            if callback:
                callback("[SUCCESS] SemaFloor complete", 40)
            
            return True, files, ""
            
        except subprocess.TimeoutExpired:
            return False, {}, "SemaFloor inference timed out (>5 minutes)"
        except Exception as e:
            return False, {}, f"SemaFloor error: {str(e)}"
    
    def run_both(
        self, 
        image_path: str, 
        output_dir: str,
        callback=None
    ) -> Tuple[bool, Dict[str, str], list]:
        """
        Run both SplitFloor and SemaFloor inference.
        
        Returns:
            (success, all_files_dict, errors_list)
        """
        all_files = {}
        errors = []
        
        # Check dependencies
        deps = self.check_dependencies()
        if not all(deps.values()):
            errors.append("Missing neural network dependencies:")
            for key, available in deps.items():
                if not available:
                    errors.append(f"  ✗ {key}")
            return False, {}, errors
        
        # Run SplitFloor
        success_split, files_split, error_split = self.run_splitfloor(
            image_path, output_dir, callback
        )
        
        if not success_split:
            errors.append(error_split)
            return False, all_files, errors
        
        all_files.update(files_split)
        
        # Run SemaFloor
        success_sema, files_sema, error_sema = self.run_semafloor(
            image_path, output_dir, callback
        )
        
        if not success_sema:
            errors.append(error_sema)
            return False, all_files, errors
        
        all_files.update(files_sema)
        
        return True, all_files, errors


class ForgePlanPipeline:
    """Core pipeline class that orchestrates the complete workflow."""
    
    def __init__(self, output_dir='outputs', project_root='.'):
        self.output_dir = Path(output_dir).expanduser().resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.shape_processor = ShapeProcessor()
        self.morpho_extruder = MorphoExtruder()
        self.neural_orchestrator = NeuralInferenceOrchestrator(project_root)
        
    def run(
        self,
        # Input options
        input_image: Optional[str] = None,
        auto_neural: bool = False,
        sema_path: Optional[str] = 'sema.csv',
        split_path: Optional[str] = 'split.csv',
        underlay_path: Optional[str] = 'input.jpeg',
        # Shape parameters
        smooth: int = 1,
        square: int = 1,
        struct_thickness: int = 10,
        alpha_underlay: float = 1.0,
        alpha_struct: float = 0.8,
        alpha_rooms: float = 0.5,
        # Morpho parameters
        wall_height: int = 200,
        room_height: int = 0,
        wall_thickness: int = 4,
        contour_squareness: int = 1,
        window_base_height: int = 50,
        window_vertical_size: int = 100,
        show_windows: bool = True,
        window_opening_clearance: int = 2,
        floor_opacity: float = 0.7,
        flip_y: bool = True,
        flip_x: bool = True,
        rotation: int = 180,
        show_input_image: bool = True,
        show_segmentation: bool = False,
        input_image_opacity: float = 1,
        segmentation_opacity: float = 0.4,
        export_obj: bool = True,
        show_interactive: bool = True,
        callback=None,
        geometry_mode: str = 'vector',
        door_height: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Run the complete pipeline.
        
        NEW: If auto_neural=True and input_image is provided, automatically run
        SplitFloor and SemaFloor inference before Shape processing.
        """
        result = {
            'success': False,
            'files': {},
            'errors': []
        }
        
        def log(message, progress=None):
            print(message)
            if callback:
                callback(message, progress)
        
        log("[START] Starting Forgeplan Pipeline", 0)
        log(f"[INFO] Output directory: {self.output_dir}/", 5)
        
        # STEP 0: Neural Inference (if auto mode)
        if auto_neural and input_image:
            if not os.path.exists(input_image):
                error = f"Input image not found: {input_image}"
                log(f"[ERROR] {error}")
                result['errors'].append(error)
                return result
            
            log("STEP 0: Neural Network Inference", 10)
            log(f"  Input: {os.path.basename(input_image)}")
            
            success, neural_files, neural_errors = self.neural_orchestrator.run_both(
                input_image, str(self.output_dir), callback
            )
            
            if not success:
                result['errors'].extend(neural_errors)
                return result
            
            result['files'].update(neural_files)
            
            # Update paths for downstream processing
            if 'split_csv_pipeline' in neural_files:
                split_path = neural_files['split_csv_pipeline']
            if 'sema_csv' in neural_files:
                sema_path = neural_files['sema_csv']
            if input_image and (underlay_path in (None, 'input.jpeg') or not os.path.isfile(underlay_path)):
                underlay_path = input_image
            
            log("[SUCCESS] Neural inference complete", 45)
        
        # Check input files (manual mode or post-neural)
        files_exist = {
            'sema': os.path.exists(sema_path) if sema_path else False,
            'split': os.path.exists(split_path) if split_path else False,
            'underlay': os.path.exists(underlay_path) if underlay_path else False
        }
        
        if not any(files_exist.values()):
            error = "No input files found. Use --auto with --input, or provide sema.csv/split.csv"
            log(f"[ERROR] {error}")
            result['errors'].append(error)
            return result
        
        # STEP 1: Shape Processing
        log("STEP 1: Shape Processing", 50)
        
        try:
            shape_result = self.shape_processor.process(
                sema_path=sema_path if files_exist['sema'] else None,
                split_path=split_path if files_exist['split'] else None,
                underlay_path=underlay_path if files_exist['underlay'] else None,
                output_dir=str(self.output_dir),
                smooth=smooth,
                square=square,
                struct_thickness=struct_thickness,
                alpha_underlay=alpha_underlay,
                alpha_struct=alpha_struct,
                alpha_rooms=alpha_rooms
            )
            
            if not shape_result['success']:
                result['errors'].extend(shape_result['errors'])
                return result
            
            result['files'].update(shape_result['files'])
            log("[SUCCESS] Shape processing complete", 65)
            
        except Exception as e:
            error = f"Shape processing failed: {e}"
            log(f"[ERROR] {error}")
            result['errors'].append(error)
            return result
        
        # STEP 2: 3D Extrusion
        log("STEP 2: 3D Extrusion", 70)
        
        try:
            morpho_result = self.morpho_extruder.extrude(
                rooms_csv=shape_result['files']['rooms_csv'],
                struct_csv=shape_result['files']['struct_csv'],
                underlay_path=underlay_path if files_exist['underlay'] else None,
                output_dir=str(self.output_dir),
                wall_height=wall_height,
                room_height=room_height,
                wall_thickness=wall_thickness,
                contour_squareness=contour_squareness,
                window_base_height=window_base_height,
                window_vertical_size=window_vertical_size,
                show_windows=show_windows,
                window_opening_clearance=window_opening_clearance,
                floor_opacity=floor_opacity,
                flip_y=flip_y,
                flip_x=flip_x,
                rotation=rotation,
                show_input_image=show_input_image,
                show_segmentation=show_segmentation,
                input_image_opacity=input_image_opacity,
                segmentation_opacity=segmentation_opacity,
                export_obj=export_obj,
                show_interactive=show_interactive,
                geometry_mode=geometry_mode,
                door_height=door_height,
                opening_struct_csv=split_path if files_exist['split'] else None,
            )
            
            if not morpho_result['success']:
                result['errors'].extend(morpho_result['errors'])
                return result
            
            result['files'].update(morpho_result['files'])
            if 'geometry' in morpho_result:
                result['geometry'] = morpho_result['geometry']
            log("[SUCCESS] 3D extrusion complete", 95)
            
        except Exception as e:
            error = f"3D extrusion failed: {e}"
            log(f"[ERROR] {error}")
            result['errors'].append(error)
            return result
        
        # Success
        result['success'] = True
        log("\n[SUCCESS] Pipeline Complete!", 100)
        log(f"[INFO] Generated files:")
        for name, path in result['files'].items():
            log(f"   - {os.path.basename(path)}")
        
        return result


def create_gui(project_root='.'): 
    """Create and launch the GUI interface with auto-neural support and live preview."""
    try:
        import tkinter as tk
        from tkinter import ttk, messagebox, filedialog
        from PIL import Image, ImageTk
        from auth import LoginWindow
    except ImportError as e:
        print(f"[ERROR] Required libraries not available: {e}")
        print("Install with: pip install pillow")
        sys.exit(1)
    
    class ForgePlanGUI:
        def __init__(self, root):
            self.root = root
            self.root.title("Forgeplan - 2D to 3D Floor Plan Pipeline (Enhanced with Live Preview)")
            self.root.geometry("1400x800")
            
            self.pipeline = ForgePlanPipeline(project_root=project_root) 
            self.params = {}
            
            # Cache for neural inference outputs
            self.cached_neural_outputs = {
                'sema_path': None,
                'split_path': None,
                'underlay_path': None,
                'neural_complete': False
            }
            
            # Preview state
            self.preview_image = None
            self.preview_photo = None
            self.update_timer = None
            self.preview_updating = False
            
            self.create_widgets()
        
        def create_widgets(self):
            # Main container with two columns
            main_container = ttk.Frame(self.root)
            main_container.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
            
            # Left column: Preview
            left_frame = ttk.Frame(main_container, width=600)
            left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
            left_frame.pack_propagate(False)
            
            # Right column: Controls (scrollable)
            right_frame = ttk.Frame(main_container)
            right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
            
            self.create_preview_panel(left_frame)
            self.create_control_panel(right_frame)
        
        def create_preview_panel(self, parent):
            """Create the live preview panel."""
            preview_container = ttk.LabelFrame(parent, text="Live 2D Preview", padding=10)
            preview_container.pack(fill=tk.BOTH, expand=True)
            
            # Preview status
            self.preview_status = ttk.Label(
                preview_container, 
                text="Upload an image to see preview",
                font=('Helvetica', 10)
            )
            self.preview_status.pack(pady=5)
            
            # Canvas for preview image
            canvas_frame = ttk.Frame(preview_container)
            canvas_frame.pack(fill=tk.BOTH, expand=True, pady=5)
            
            self.preview_canvas = tk.Canvas(
                canvas_frame, 
                bg='#2b2b2b',
                highlightthickness=1,
                highlightbackground='#555555'
            )
            self.preview_canvas.pack(fill=tk.BOTH, expand=True)
            
            # Info label
            info_text = ("Adjust shape parameters to see real-time updates.\n"
                        "Click 'Render 3D' to generate the full 3D model.")
            ttk.Label(
                preview_container,
                text=info_text,
                font=('Helvetica', 9),
                foreground='#666666',
                justify=tk.CENTER
            ).pack(pady=5)
        
        def create_control_panel(self, parent):
            """Create the control panel with all parameters."""
            canvas = tk.Canvas(parent, highlightthickness=0)
            scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
            scrollable_frame = ttk.Frame(canvas, padding="20")
            
            scrollable_frame.bind(
                "<Configure>",
                lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
            )
            
            canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
            canvas.configure(yscrollcommand=scrollbar.set)
            
            canvas.pack(side="left", fill="both", expand=True)
            scrollbar.pack(side="right", fill="y")
            
            def _on_mousewheel(event):
                canvas.yview_scroll(int(-1*(event.delta/120)), "units")
            
            canvas.bind_all("<MouseWheel>", _on_mousewheel)
            
            self.canvas = canvas
            self.scrollable_frame = scrollable_frame
            
            self.build_ui(scrollable_frame)
        
        def build_ui(self, parent):
            row = 0
            
            # Title
            title = ttk.Label(parent, text="Forgeplan Pipeline", 
                            font=('Helvetica', 16, 'bold'))
            title.grid(row=row, column=0, columnspan=3, pady=(0, 15))
            row += 1
            
            # Mode Selection
            self.create_section_header(parent, row, "Input Mode")
            row += 2
            
            self.mode_var = tk.StringVar(value='auto')
            
            mode_frame = ttk.Frame(parent)
            mode_frame.grid(row=row, column=0, columnspan=3, sticky=tk.W, pady=10)
            
            ttk.Radiobutton(mode_frame, text="Auto (Neural Inference)", 
                          variable=self.mode_var, value='auto',
                          command=self.update_mode).pack(side=tk.LEFT, padx=20)
            ttk.Radiobutton(mode_frame, text="Manual (CSV files)", 
                          variable=self.mode_var, value='manual',
                          command=self.update_mode).pack(side=tk.LEFT, padx=20)
            row += 1
            
            # Auto Mode Inputs
            self.auto_frame = ttk.LabelFrame(parent, text="Auto Mode", padding=10)
            self.auto_frame.grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
            
            self.input_image_var = tk.StringVar(value='')
            ttk.Label(self.auto_frame, text="Floor Plan:").grid(row=0, column=0, sticky=tk.W, pady=5)
            ttk.Entry(self.auto_frame, textvariable=self.input_image_var, width=35).grid(
                row=0, column=1, padx=10, pady=5, sticky=tk.W)
            ttk.Button(self.auto_frame, text="Browse", 
                      command=self.browse_and_process_image).grid(row=0, column=2, pady=5)
            
            row += 1
            
            # Manual Mode Inputs
            self.manual_frame = ttk.LabelFrame(parent, text="Manual Mode", padding=10)
            self.manual_frame.grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
            
            self.file_vars = {
                'sema': tk.StringVar(value='sema.csv'),
                'split': tk.StringVar(value='split.csv'),
                'underlay': tk.StringVar(value='input.jpeg')
            }
            
            for idx, (name, var) in enumerate(self.file_vars.items()):
                ttk.Label(self.manual_frame, text=f"{name}:").grid(
                    row=idx, column=0, sticky=tk.W, pady=5, padx=5)
                ttk.Entry(self.manual_frame, textvariable=var, width=30).grid(
                    row=idx, column=1, padx=10, pady=5, sticky=tk.W)
                ttk.Button(self.manual_frame, text="Browse", 
                          command=lambda v=var: self.browse_file(v)).grid(
                    row=idx, column=2, pady=5)
            
            row += 1
            
            # Shape Parameters (these trigger preview updates)
            self.create_section_header(parent, row, "Shape Parameters (Live Preview)")
            row += 2
            
            shape_params = [
                ('smooth', 1, 0, 10, 1),
                ('square', 1, 0, 10, 1),
                ('struct_thickness', 10, 1, 20, 1),
                ('alpha_underlay', 1.0, 0.0, 1.0, 0.1),
                ('alpha_struct', 0.8, 0.0, 1.0, 0.1),
                ('alpha_rooms', 0.5, 0.0, 1.0, 0.1)
            ]
            
            for name, default, min_val, max_val, resolution in shape_params:
                row = self.create_slider(parent, row, name, default, 
                                        min_val, max_val, resolution, 
                                        preview_trigger=True)
            
            row += 1
            
            # 3D Parameters (no preview updates)
            self.create_section_header(parent, row, "3D Extrusion Parameters")
            row += 2
            
            morpho_params = [
                ('wall_height', 200, 50, 500, 10),
                ('door_height', 160, 20, 500, 10),
                ('wall_thickness', 4, 1, 20, 1),
                ('contour_squareness', 1, 0, 10, 1),
                ('window_base_height', 50, 0, 200, 10),
                ('window_vertical_size', 100, 10, 300, 10),
                ('window_opening_clearance', 2, 0, 10, 1),
                ('floor_opacity', 0.7, 0.0, 1.0, 0.1),
                ('input_image_opacity', 0.6, 0.0, 1.0, 0.1),
                ('segmentation_opacity', 0.4, 0.0, 1.0, 0.1),
                ('rotation', 180, 0, 360, 90)
            ]
            
            for name, default, min_val, max_val, resolution in morpho_params:
                row = self.create_slider(parent, row, name, default, 
                                        min_val, max_val, resolution,
                                        preview_trigger=False)
            
            row += 1
            
            # Boolean Options
            self.create_section_header(parent, row, "Options")
            row += 2
            
            bool_params = [
                ('show_windows', False),
                ('flip_y', True),
                ('flip_x', True),
                ('show_input_image', False),
                ('show_segmentation', True),
                ('export_obj', True),
                ('show_interactive', True)
            ]
            
            checkbox_frame = ttk.Frame(parent)
            checkbox_frame.grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
            
            for idx, (name, default) in enumerate(bool_params):
                var = tk.BooleanVar(value=default)
                self.params[name] = var
                col = idx % 2
                r = idx // 2
                ttk.Checkbutton(checkbox_frame, 
                              text=name.replace('_', ' ').title(), 
                              variable=var).grid(row=r, column=col, sticky=tk.W, padx=20, pady=5)
            
            row += 1
            row += 1
            
            # Progress
            ttk.Separator(parent, orient='horizontal').grid(
                row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=15)
            row += 1
            
            self.status_label = ttk.Label(parent, text="Ready", 
                                         font=('Helvetica', 10))
            self.status_label.grid(row=row, column=0, columnspan=3, pady=5)
            row += 1
            
            self.progress = ttk.Progressbar(parent, mode='determinate', 
                                           length=400)
            self.progress.grid(row=row, column=0, columnspan=3, pady=10)
            row += 1
            
            # Buttons
            button_frame = ttk.Frame(parent)
            button_frame.grid(row=row, column=0, columnspan=3, pady=20)
            
            ttk.Button(button_frame, text="Render 3D", 
                      command=self.run_pipeline).pack(side=tk.LEFT, padx=10, ipadx=20, ipady=10)
            
            ttk.Button(button_frame, text="Exit", 
                      command=self.root.quit).pack(side=tk.LEFT, padx=10, ipadx=20, ipady=10)
            
            parent.columnconfigure(1, weight=1)
            
            # Initialize mode
            self.update_mode()
        
        def create_section_header(self, parent, row, text):
            ttk.Separator(parent, orient='horizontal').grid(
                row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(15, 10))
            ttk.Label(parent, text=text, 
                     font=('Helvetica', 11, 'bold')).grid(
                row=row+1, column=0, columnspan=3, sticky=tk.W, pady=(0, 10))
            return row + 2
        
        def create_slider(self, parent, row, name, default, min_val, max_val, resolution, preview_trigger=False):
            var = tk.DoubleVar(value=default) if isinstance(default, float) else tk.IntVar(value=default)
            self.params[name] = var
            
            label_text = name.replace('_', ' ').title()
            ttk.Label(parent, text=f"{label_text}:", 
                     font=('Helvetica', 9)).grid(
                row=row, column=0, sticky=tk.W, pady=5)
            
            # Create callback that triggers preview update if needed
            def on_slider_change(v):
                self.update_slider_value(var, isinstance(default, float))
                if preview_trigger and self.cached_neural_outputs['neural_complete']:
                    self.schedule_preview_update()
            
            slider = ttk.Scale(parent, from_=min_val, to=max_val, 
                              variable=var, orient=tk.HORIZONTAL, 
                              command=on_slider_change)
            slider.grid(row=row, column=1, sticky=(tk.W, tk.E), padx=10, pady=5)
            
            value_label = ttk.Label(parent, text=str(default), width=8, 
                                   font=('Helvetica', 9))
            value_label.grid(row=row, column=2, sticky=tk.W, pady=5)
            
            self.params[f'{name}_label'] = value_label
            
            return row + 1
        
        def update_slider_value(self, var, is_float):
            val = var.get()
            for param_name, param_var in self.params.items():
                if param_var == var:
                    label_name = param_name + '_label'
                    if label_name in self.params:
                        if is_float:
                            self.params[label_name].config(text=f"{val:.2f}")
                        else:
                            self.params[label_name].config(text=f"{int(val)}")
                    break
        
        def update_mode(self):
            """Toggle between auto and manual mode."""
            mode = self.mode_var.get()
            if mode == 'auto':
                self.auto_frame.grid()
                self.manual_frame.grid_remove()
            else:
                self.auto_frame.grid_remove()
                self.manual_frame.grid()
        
        def browse_file(self, var, filetypes=None):
            if filetypes is None:
                filetypes = [("All files", "*.*")]
            filename = filedialog.askopenfilename(filetypes=filetypes)
            if filename:
                var.set(filename)
        
        def browse_and_process_image(self):
            """Browse for image and run neural inference."""
            filetypes = [("Images", "*.jpg *.jpeg *.png *.bmp")]
            filename = filedialog.askopenfilename(filetypes=filetypes)
            if filename:
                self.input_image_var.set(filename)
                # Run neural inference in background
                self.run_neural_inference(filename)
        
        def run_neural_inference(self, image_path):
            """Run neural inference and cache outputs."""
            self.preview_status.config(text="Running neural network inference...")
            self.progress['value'] = 0
            self.root.update_idletasks()
            
            def inference_thread():
                try:
                    success, neural_files, neural_errors = self.pipeline.neural_orchestrator.run_both(
                        image_path, 
                        str(self.pipeline.output_dir), 
                        callback=self.update_progress
                    )
                    
                    if success:
                        # Cache the outputs
                        self.cached_neural_outputs['sema_path'] = neural_files.get('sema_csv')
                        self.cached_neural_outputs['split_path'] = neural_files.get('split_csv_pipeline')
                        self.cached_neural_outputs['underlay_path'] = image_path
                        self.cached_neural_outputs['neural_complete'] = True
                        
                        # Update preview
                        self.root.after(0, self.update_shape_preview)
                    else:
                        error_msg = "\n".join(neural_errors)
                        self.root.after(0, lambda: messagebox.showerror("Neural Inference Failed", error_msg))
                        self.root.after(0, lambda: self.preview_status.config(text="Inference failed"))
                
                except Exception as e:
                    self.root.after(0, lambda: messagebox.showerror("Error", f"Neural inference error: {e}"))
                    self.root.after(0, lambda: self.preview_status.config(text="Error occurred"))
            
            # Run in background thread
            thread = threading.Thread(target=inference_thread, daemon=True)
            thread.start()
        
        def schedule_preview_update(self):
            """Schedule preview update with debouncing to avoid excessive updates."""
            if self.update_timer:
                self.root.after_cancel(self.update_timer)
            
            # Debounce: wait 300ms after last slider change
            self.update_timer = self.root.after(300, self.update_shape_preview)
        
        def update_shape_preview(self):
            """Update the 2D preview by re-running ShapeProcessor."""
            if not self.cached_neural_outputs['neural_complete']:
                return
            
            if self.preview_updating:
                return
            
            self.preview_updating = True
            self.preview_status.config(text="Updating preview...")
            self.root.update_idletasks()
            
            try:
                # Get current shape parameters
                shape_params = {
                    'smooth': int(self.params['smooth'].get()),
                    'square': int(self.params['square'].get()),
                    'struct_thickness': int(self.params['struct_thickness'].get()),
                    'alpha_underlay': float(self.params['alpha_underlay'].get()),
                    'alpha_struct': float(self.params['alpha_struct'].get()),
                    'alpha_rooms': float(self.params['alpha_rooms'].get())
                }
                
                # Run ShapeProcessor with cached inputs
                shape_result = self.pipeline.shape_processor.process(
                    sema_path=self.cached_neural_outputs['sema_path'],
                    split_path=self.cached_neural_outputs['split_path'],
                    underlay_path=self.cached_neural_outputs['underlay_path'],
                    output_dir=str(self.pipeline.output_dir),
                    **shape_params
                )
                
                if shape_result['success']:
                    # Try different possible output files from ShapeProcessor
                    preview_candidates = [
                        'composite_image',
                        'visualization',
                        'architectural_overlay',
                        'overlay'
                    ]
                    
                    preview_path = None
                    for candidate in preview_candidates:
                        if candidate in shape_result['files']:
                            preview_path = shape_result['files'][candidate]
                            break
                    
                    # Fallback: check output directory for common filenames
                    if not preview_path:
                        output_dir = self.pipeline.output_dir
                        possible_files = [
                            'architectural_overlay.png',
                            'composite_image.png',
                            'visualization.png',
                            'shape_output.png'
                        ]
                        for filename in possible_files:
                            candidate_path = output_dir / filename
                            if candidate_path.exists():
                                preview_path = str(candidate_path)
                                break
                    
                    if preview_path and os.path.exists(preview_path):
                        self.display_preview_image(preview_path)
                        self.preview_status.config(text="Preview ready - Adjust parameters to update")
                    else:
                        available_files = list(shape_result['files'].keys())
                        self.preview_status.config(text=f"No preview image found. Available: {available_files}")
                else:
                    errors = shape_result.get('errors', ['Unknown error'])
                    self.preview_status.config(text=f"Preview failed: {errors[0][:50]}")
            
            except Exception as e:
                print(f"Preview update error: {e}")
                self.preview_status.config(text=f"Preview error: {str(e)[:50]}")
            
            finally:
                self.preview_updating = False
        
        def display_preview_image(self, image_path):
            """Display image in the preview canvas with proper scaling."""
            try:
                # Load image
                img = Image.open(image_path)
                
                # Get canvas size
                canvas_width = self.preview_canvas.winfo_width()
                canvas_height = self.preview_canvas.winfo_height()
                
                # Handle initial size (before canvas is drawn)
                if canvas_width <= 1:
                    canvas_width = 560
                if canvas_height <= 1:
                    canvas_height = 560
                
                # Calculate scaling to fit canvas while maintaining aspect ratio
                img_ratio = img.width / img.height
                canvas_ratio = canvas_width / canvas_height
                
                if img_ratio > canvas_ratio:
                    # Image is wider than canvas
                    new_width = canvas_width - 20
                    new_height = int(new_width / img_ratio)
                else:
                    # Image is taller than canvas
                    new_height = canvas_height - 20
                    new_width = int(new_height * img_ratio)
                
                # Resize image
                img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                
                # Convert to PhotoImage
                self.preview_photo = ImageTk.PhotoImage(img_resized)
                
                # Clear canvas and display image
                self.preview_canvas.delete("all")
                x = canvas_width // 2
                y = canvas_height // 2
                self.preview_canvas.create_image(x, y, image=self.preview_photo)
                
            except Exception as e:
                print(f"Error displaying preview: {e}")
                self.preview_status.config(text="Failed to display preview")
        
        def update_progress(self, message, progress):
            self.status_label.config(text=message)
            if progress is not None:
                self.progress['value'] = progress
            self.root.update_idletasks()
        
        def run_pipeline(self):
            """Run the full 3D pipeline."""
            self.status_label.config(text="Rendering 3D model...")
            self.progress['value'] = 0
            self.root.update_idletasks()
            
            try:
                # Collect parameters
                kwargs = {name: var.get() for name, var in self.params.items() 
                         if not name.endswith('_label')}
                kwargs['callback'] = self.update_progress
                
                # Determine mode
                mode = self.mode_var.get()
                
                if mode == 'auto':
                    if self.cached_neural_outputs['neural_complete']:
                        # Use cached neural outputs
                        kwargs['auto_neural'] = False
                        kwargs['sema_path'] = self.cached_neural_outputs['sema_path']
                        kwargs['split_path'] = self.cached_neural_outputs['split_path']
                        kwargs['underlay_path'] = self.cached_neural_outputs['underlay_path']
                    else:
                        input_img = self.input_image_var.get()
                        if not input_img or not os.path.exists(input_img):
                            messagebox.showerror("Error", "Please select a valid input image")
                            return
                        
                        kwargs['input_image'] = input_img
                        kwargs['auto_neural'] = True
                        kwargs['underlay_path'] = input_img
                else:
                    kwargs['auto_neural'] = False
                    kwargs['sema_path'] = self.file_vars['sema'].get()
                    kwargs['split_path'] = self.file_vars['split'].get()
                    kwargs['underlay_path'] = self.file_vars['underlay'].get()
                
                # Run pipeline
                result = self.pipeline.run(**kwargs)
                
                if result['success']:
                    messagebox.showinfo("Success", 
                        f"Pipeline completed!\n\nGenerated files:\n" + 
                        "\n".join(f"- {os.path.basename(p)}" for p in result['files'].values()))
                else:
                    messagebox.showerror("Error", 
                        "Pipeline failed:\n" + "\n".join(result['errors']))
                
            except Exception as e:
                messagebox.showerror("Error", f"Unexpected error: {e}")
                import traceback
                traceback.print_exc()
            
            finally:
                self.status_label.config(text="Ready")
    
    # Launch GUI: login window first, main workspace after authentication
    root = tk.Tk()

    def on_login_success(username):
        for widget in root.winfo_children():
            widget.destroy()
        app = ForgePlanGUI(root)
        app.current_user = username
        app.root.title(
            "Forgeplan - 2D to 3D Floor Plan Pipeline"
            " (Enhanced with Live Preview) | user: " + username
        )

    LoginWindow(root, on_success=on_login_success)
    root.mainloop()


def cli_mode(args):
    """Run in CLI mode with command-line arguments."""
    pipeline = ForgePlanPipeline(
        output_dir=args.output_dir,
        project_root=args.project_root
    )
    
    result = pipeline.run(
        input_image=args.input,
        auto_neural=args.auto,
        sema_path=args.sema,
        split_path=args.split,
        underlay_path=args.underlay,
        smooth=args.smooth,
        square=args.square,
        struct_thickness=args.struct_thickness,
        wall_height=args.wall_height,
        room_height=args.room_height,
        wall_thickness=args.wall_thickness,
        flip_y=args.flip_y,
        flip_x=args.flip_x,
        rotation=args.rotation,
        show_segmentation=args.show_segmentation,
        export_obj=args.export_obj,
        show_interactive=args.show_interactive,
        geometry_mode=args.geometry_mode,
        door_height=args.door_height,
        window_base_height=args.window_base_height,
        window_vertical_size=args.window_vertical_size,
    )
    
    if not result['success']:
        print("\n[ERROR] Pipeline failed:")
        for error in result['errors']:
            print(f"  - {error}")
        sys.exit(1)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Forgeplan - 2D to 3D Floor Plan Pipeline (Enhanced with Live Preview)',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    # Mode selection
    parser.add_argument('--gui', action='store_true', 
                       help='Launch GUI interface')
    parser.add_argument('--auto', action='store_true',
                       help='Enable automatic neural network inference')
    
    # Input files
    parser.add_argument('--input', type=str,
                       help='Input floor plan image (for auto mode)')
    parser.add_argument('--sema', default='sema.csv',
                       help='Path to semantic segmentation CSV (manual mode)')
    parser.add_argument('--split', default='split.csv',
                       help='Path to structural split CSV (manual mode)')
    parser.add_argument('--underlay', default='input.jpeg',
                       help='Path to floor plan image (manual mode)')
    parser.add_argument('--output_dir', default='outputs',
                       help='Output directory')
    parser.add_argument('--project_root', default='.',
                       help='Project root directory containing SplitFloor/ and SemaFloor/')
    
    # Shape parameters
    parser.add_argument('--smooth', type=int, default=1,
                       help='Morphological smoothing radius')
    parser.add_argument('--square', type=int, default=1,
                       help='Squaring kernel size')
    parser.add_argument('--struct_thickness', type=int, default=10,
                       help='Structural element thickness')
    
    # Morpho parameters
    parser.add_argument('--wall_height', type=int, default=200,
                       help='Height of walls')
    parser.add_argument('--room_height', type=int, default=200,
                       help='Legacy mode wall height; vector mode uses wall_height')
    parser.add_argument('--geometry_mode', choices=['vector', 'legacy'], default='vector',
                       help='Vector solids or original pixel extrusion')
    parser.add_argument('--door_height', type=float, default=None,
                       help='Door opening height; defaults to 80%% of wall height')
    parser.add_argument('--window_base_height', type=float, default=50,
                       help='Window sill height')
    parser.add_argument('--window_vertical_size', type=float, default=100,
                       help='Window opening height')
    parser.add_argument('--wall_thickness', type=int, default=4,
                       help='Thickness of walls in pixels')
    parser.add_argument('--flip_y', action=argparse.BooleanOptionalAction, default=True,
                       help='Flip vertically')
    parser.add_argument('--flip_x', action=argparse.BooleanOptionalAction, default=True,
                       help='Flip horizontally')
    parser.add_argument('--rotation', type=int, default=180,
                       help='Rotation angle (multiples of 90)')
    parser.add_argument('--show_segmentation', action=argparse.BooleanOptionalAction, default=True,
                       help='Show room colors in 3D')
    parser.add_argument('--export_obj', action=argparse.BooleanOptionalAction, default=True,
                       help='Export 3D model as OBJ')
    parser.add_argument('--show_interactive', action=argparse.BooleanOptionalAction, default=True,
                       help='Show interactive 3D viewer')
    
    args = parser.parse_args()
    
    # Launch appropriate mode
    if args.gui:
        create_gui(project_root=args.project_root)
    else:
        cli_mode(args)


if __name__ == "__main__":
    main()
