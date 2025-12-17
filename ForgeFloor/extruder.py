"""
FORGEPLAN - 2D to 3D Floor Plan Pipeline
=========================================
Main orchestrator with CLI and GUI interfaces.

Usage:
    CLI: python extruder.py --smooth 2 --wall_height 200
    GUI: python extruder.py --gui

Author: Floor Plan CV Backend
"""

import os
import sys
import argparse
from pathlib import Path
from typing import Optional, Dict, Any

# Core pipeline imports
try:
    from Shape import ShapeProcessor
    from morpho import MorphoExtruder
except ImportError as e:
    print(f"Error importing modules: {e}")
    print("Make sure Shape.py and morpho.py are in the same directory.")
    sys.exit(1)


class ForgePlanPipeline:
    """Core pipeline class that orchestrates Shape → Morpho workflow."""
    
    def __init__(self, output_dir='outputs'):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.shape_processor = ShapeProcessor()
        self.morpho_extruder = MorphoExtruder()
        
    def run(
        self,
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
        room_height: int = 200,
        wall_thickness: int = 4,
        contour_squareness: int = 1,
        window_base_height: int = 50,
        window_vertical_size: int = 100,
        show_windows: bool = False,
        window_opening_clearance: int = 2,
        floor_opacity: float = 0.7,
        flip_y: bool = True,
        flip_x: bool = True,
        rotation: int = 180,
        show_input_image: bool = False,
        show_segmentation: bool = True,
        input_image_opacity: float = 0.6,
        segmentation_opacity: float = 0.4,
        export_obj: bool = True,
        show_interactive: bool = True,
        callback=None
    ) -> Dict[str, Any]:
        """
        Run the complete pipeline.
        
        Args:
            callback: Optional function to call with progress updates (message, progress_percent)
        
        Returns:
            Dictionary with paths to generated files and status
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
        
        # Check input files
        files_exist = {
            'sema': os.path.exists(sema_path) if sema_path else False,
            'split': os.path.exists(split_path) if split_path else False,
            'underlay': os.path.exists(underlay_path) if underlay_path else False
        }
        
        if not any(files_exist.values()):
            error = "No input files found. Please provide at least one of: sema.csv, split.csv, input.jpeg"
            log(f"❌ {error}")
            result['errors'].append(error)
            return result
        
        log("🚀 Starting Forgeplan Pipeline", 0)
        log(f"📂 Output directory: {self.output_dir}/", 5)
        
        # STEP 1: Shape Processing
        log("\n🏗️  STEP 1: Shape Processing", 10)
        
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
            log("✅ Shape processing complete", 40)
            
        except Exception as e:
            error = f"Shape processing failed: {e}"
            log(f"❌ {error}")
            result['errors'].append(error)
            return result
        
        # STEP 2: 3D Extrusion
        log("\n🏛️  STEP 2: 3D Extrusion", 50)
        
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
                show_interactive=show_interactive
            )
            
            if not morpho_result['success']:
                result['errors'].extend(morpho_result['errors'])
                return result
            
            result['files'].update(morpho_result['files'])
            log("✅ 3D extrusion complete", 90)
            
        except Exception as e:
            error = f"3D extrusion failed: {e}"
            log(f"❌ {error}")
            result['errors'].append(error)
            return result
        
        # Success
        result['success'] = True
        log("\n🎉 Pipeline Complete!", 100)
        log(f"📂 Generated files:")
        for name, path in result['files'].items():
            log(f"   ├── {os.path.basename(path)}")
        
        return result


def create_gui():
    """Create and launch the GUI interface."""
    try:
        import tkinter as tk
        from tkinter import ttk, messagebox, filedialog
    except ImportError:
        print("❌ tkinter not available. Install it or use CLI mode.")
        sys.exit(1)
    
    class ForgePlanGUI:
        def __init__(self, root):
            self.root = root
            self.root.title("Forgeplan - 2D to 3D Floor Plan Pipeline")
            self.root.geometry("800x900")
            
            self.pipeline = ForgePlanPipeline()
            self.params = {}
            
            self.create_widgets()
        
        def create_widgets(self):
            # Main container with scrollbar
            main_frame = ttk.Frame(self.root, padding="10")
            main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
            
            # Title
            title = ttk.Label(main_frame, text="🏗️ Forgeplan Pipeline", 
                            font=('Helvetica', 16, 'bold'))
            title.grid(row=0, column=0, columnspan=3, pady=10)
            
            row = 1
            
            # Input Files Section
            ttk.Separator(main_frame, orient='horizontal').grid(
                row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
            row += 1
            
            ttk.Label(main_frame, text="Input Files", 
                     font=('Helvetica', 12, 'bold')).grid(row=row, column=0, sticky=tk.W)
            row += 1
            
            self.file_vars = {
                'sema': tk.StringVar(value='sema.csv'),
                'split': tk.StringVar(value='split.csv'),
                'underlay': tk.StringVar(value='input.jpeg')
            }
            
            for name, var in self.file_vars.items():
                ttk.Label(main_frame, text=f"{name}.csv/jpeg:").grid(
                    row=row, column=0, sticky=tk.W, padx=(0, 5))
                ttk.Entry(main_frame, textvariable=var, width=30).grid(
                    row=row, column=1, padx=5)
                ttk.Button(main_frame, text="Browse", 
                          command=lambda v=var: self.browse_file(v)).grid(
                    row=row, column=2)
                row += 1
            
            # Shape Parameters Section
            ttk.Separator(main_frame, orient='horizontal').grid(
                row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
            row += 1
            
            ttk.Label(main_frame, text="Shape Parameters", 
                     font=('Helvetica', 12, 'bold')).grid(row=row, column=0, sticky=tk.W)
            row += 1
            
            shape_params = [
                ('smooth', 1, 0, 10, 1),
                ('square', 1, 0, 10, 1),
                ('struct_thickness', 10, 1, 20, 1),
                ('alpha_underlay', 1.0, 0.0, 1.0, 0.1),
                ('alpha_struct', 0.8, 0.0, 1.0, 0.1),
                ('alpha_rooms', 0.5, 0.0, 1.0, 0.1)
            ]
            
            for name, default, min_val, max_val, resolution in shape_params:
                row = self.create_slider(main_frame, row, name, default, 
                                        min_val, max_val, resolution)
            
            # Morpho Parameters Section
            ttk.Separator(main_frame, orient='horizontal').grid(
                row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
            row += 1
            
            ttk.Label(main_frame, text="3D Extrusion Parameters", 
                     font=('Helvetica', 12, 'bold')).grid(row=row, column=0, sticky=tk.W)
            row += 1
            
            morpho_params = [
                ('wall_height', 200, 50, 500, 10),
                ('room_height', 200, 50, 500, 10),
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
                row = self.create_slider(main_frame, row, name, default, 
                                        min_val, max_val, resolution)
            
            # Boolean Parameters
            ttk.Separator(main_frame, orient='horizontal').grid(
                row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
            row += 1
            
            ttk.Label(main_frame, text="Options", 
                     font=('Helvetica', 12, 'bold')).grid(row=row, column=0, sticky=tk.W)
            row += 1
            
            bool_params = [
                ('show_windows', False),
                ('flip_y', True),
                ('flip_x', True),
                ('show_input_image', False),
                ('show_segmentation', True),
                ('export_obj', True),
                ('show_interactive', True)
            ]
            
            for name, default in bool_params:
                var = tk.BooleanVar(value=default)
                self.params[name] = var
                ttk.Checkbutton(main_frame, text=name.replace('_', ' ').title(), 
                              variable=var).grid(row=row, column=0, columnspan=2, 
                                               sticky=tk.W)
                row += 1
            
            # Progress Section
            ttk.Separator(main_frame, orient='horizontal').grid(
                row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
            row += 1
            
            self.status_label = ttk.Label(main_frame, text="Ready", 
                                         font=('Helvetica', 10))
            self.status_label.grid(row=row, column=0, columnspan=3, pady=5)
            row += 1
            
            self.progress = ttk.Progressbar(main_frame, mode='determinate', 
                                           length=400)
            self.progress.grid(row=row, column=0, columnspan=3, pady=5)
            row += 1
            
            # Buttons
            button_frame = ttk.Frame(main_frame)
            button_frame.grid(row=row, column=0, columnspan=3, pady=20)
            
            ttk.Button(button_frame, text="🚀 Render 3D", 
                      command=self.run_pipeline, 
                      style='Accent.TButton').pack(side=tk.LEFT, padx=5)
            ttk.Button(button_frame, text="Exit", 
                      command=self.root.quit).pack(side=tk.LEFT, padx=5)
            
            # Configure grid weights
            self.root.columnconfigure(0, weight=1)
            self.root.rowconfigure(0, weight=1)
            main_frame.columnconfigure(1, weight=1)
        
        def create_slider(self, parent, row, name, default, min_val, max_val, resolution):
            """Create a labeled slider widget."""
            var = tk.DoubleVar(value=default) if isinstance(default, float) else tk.IntVar(value=default)
            self.params[name] = var
            
            label_text = name.replace('_', ' ').title()
            ttk.Label(parent, text=f"{label_text}:").grid(
                row=row, column=0, sticky=tk.W, padx=(0, 5))
            
            slider = ttk.Scale(parent, from_=min_val, to=max_val, 
                              variable=var, orient=tk.HORIZONTAL, 
                              command=lambda v, n=name, var=var: self.update_label(n, var))
            slider.grid(row=row, column=1, sticky=(tk.W, tk.E), padx=5)
            
            value_label = ttk.Label(parent, text=str(default), width=8)
            value_label.grid(row=row, column=2, sticky=tk.W)
            
            # Store reference to update later
            slider.value_label = value_label
            
            return row + 1
        
        def update_label(self, name, var):
            """Update the value label next to slider."""
            # Find the slider widget
            for widget in self.root.winfo_children()[0].winfo_children():
                if isinstance(widget, ttk.Scale) and widget.cget('variable') == str(var):
                    if hasattr(widget, 'value_label'):
                        val = var.get()
                        widget.value_label.config(text=f"{val:.1f}" if isinstance(val, float) else str(int(val)))
        
        def browse_file(self, var):
            """Open file browser dialog."""
            filename = filedialog.askopenfilename()
            if filename:
                var.set(filename)
        
        def update_progress(self, message, progress):
            """Update progress bar and status."""
            self.status_label.config(text=message)
            if progress is not None:
                self.progress['value'] = progress
            self.root.update_idletasks()
        
        def run_pipeline(self):
            """Execute the pipeline with current parameters."""
            # Disable button during execution
            self.status_label.config(text="🔄 Processing...")
            self.progress['value'] = 0
            self.root.update_idletasks()
            
            try:
                # Collect all parameters
                kwargs = {name: var.get() for name, var in self.params.items()}
                kwargs.update({
                    'sema_path': self.file_vars['sema'].get(),
                    'split_path': self.file_vars['split'].get(),
                    'underlay_path': self.file_vars['underlay'].get(),
                    'callback': self.update_progress
                })
                
                # Run pipeline
                result = self.pipeline.run(**kwargs)
                
                if result['success']:
                    messagebox.showinfo("Success", 
                        f"Pipeline completed!\n\nGenerated files:\n" + 
                        "\n".join(f"• {os.path.basename(p)}" for p in result['files'].values()))
                else:
                    messagebox.showerror("Error", 
                        "Pipeline failed:\n" + "\n".join(result['errors']))
                
            except Exception as e:
                messagebox.showerror("Error", f"Unexpected error: {e}")
            
            finally:
                self.status_label.config(text="Ready")
    
    # Launch GUI
    root = tk.Tk()
    app = ForgePlanGUI(root)
    root.mainloop()


def cli_mode(args):
    """Run in CLI mode with command-line arguments."""
    pipeline = ForgePlanPipeline(output_dir=args.output_dir)
    
    result = pipeline.run(
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
        show_interactive=args.show_interactive
    )
    
    if not result['success']:
        print("\n❌ Pipeline failed:")
        for error in result['errors']:
            print(f"  • {error}")
        sys.exit(1)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Forgeplan - 2D to 3D Floor Plan Pipeline',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    # Mode selection
    parser.add_argument('--gui', action='store_true', 
                       help='Launch GUI interface')
    
    # Input files
    parser.add_argument('--sema', default='sema.csv',
                       help='Path to semantic segmentation CSV')
    parser.add_argument('--split', default='split.csv',
                       help='Path to structural split CSV')
    parser.add_argument('--underlay', default='input.jpeg',
                       help='Path to floor plan image')
    parser.add_argument('--output_dir', default='outputs',
                       help='Output directory')
    
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
                       help='Height of rooms')
    parser.add_argument('--wall_thickness', type=int, default=4,
                       help='Thickness of walls in pixels')
    parser.add_argument('--flip_y', action='store_true', default=True,
                       help='Flip vertically')
    parser.add_argument('--flip_x', action='store_true', default=True,
                       help='Flip horizontally')
    parser.add_argument('--rotation', type=int, default=180,
                       help='Rotation angle (multiples of 90)')
    parser.add_argument('--show_segmentation', action='store_true', default=True,
                       help='Show room colors in 3D')
    parser.add_argument('--export_obj', action='store_true', default=True,
                       help='Export 3D model as OBJ')
    parser.add_argument('--show_interactive', action='store_true', default=True,
                       help='Show interactive 3D viewer')
    
    args = parser.parse_args()
    
    # Launch appropriate mode
    if args.gui:
        create_gui()
    else:
        cli_mode(args)


if __name__ == "__main__":
    main()