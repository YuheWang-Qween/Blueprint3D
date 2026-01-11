"""
SemafloorNet Inference / Deployment Script

Features:
- Load trained checkpoint
- Predict room masks for new floor plan images
- Visualization with overlay
- Export masks as PNG or CSV
- Batch processing support
"""

import os
import torch
import torch.nn.functional as F
from PIL import Image
import numpy as np
import matplotlib.pyplot as plt
from torchvision import transforms
import cv2

from net import SemafloorNet


class SemafloorPredictor:
    """
    Predictor class for floor plan room segmentation
    """
    
    def __init__(self, checkpoint_path, device=None, img_size=512):
        """
        Args:
            checkpoint_path: Path to trained model checkpoint
            device: Device to run inference on (cpu/cuda)
            img_size: Input image size (will be resized to this)
        """
        self.device = device or torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.img_size = img_size
        
        print(f"Loading model on {self.device}...")
        
        # Load model
        self.model = SemafloorNet(pretrained=False, deep_supervision=True).to(self.device)
        
        # Load checkpoint
        checkpoint = torch.load(checkpoint_path, map_location=self.device)
        
        if 'model_state_dict' in checkpoint:
            self.model.load_state_dict(checkpoint['model_state_dict'])
            print(f"Loaded checkpoint from epoch {checkpoint.get('epoch', 'unknown')}")
            print(f"  Val Loss: {checkpoint.get('val_loss', 'N/A')}")
            print(f"  Val IoU: {checkpoint.get('val_iou', 'N/A')}")
        else:
            self.model.load_state_dict(checkpoint)
        
        self.model.eval()
        print("Model loaded successfully!\n")
        
        # Image preprocessing
        self.transform = transforms.Compose([
            transforms.Resize((img_size, img_size)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.5, 0.5, 0.5], std=[0.5, 0.5, 0.5])
        ])
    
    def predict(
        self, 
        image_path, 
        threshold=0.5, 
        return_boundary=False,
        visualize=True,
        save_mask=False,
        save_overlay=False,
        output_dir=None
    ):
        """
        Predict room mask for a single image
        
        Args:
            image_path: Path to input image
            threshold: Probability threshold for binary mask
            return_boundary: Whether to also return boundary prediction
            visualize: Whether to display results
            save_mask: Whether to save mask as PNG
            save_overlay: Whether to save overlay as PNG
            output_dir: Directory to save outputs (if None, uses image directory)
        
        Returns:
            Dictionary with predictions and metadata
        """
        # Load and preprocess image
        img = Image.open(image_path).convert("RGB")
        orig_size = img.size  # (width, height)
        
        img_tensor = self.transform(img).unsqueeze(0).to(self.device)
        
        # Inference
        with torch.no_grad():
            outputs = self.model(img_tensor)
            
            room_logits = outputs['room']
            room_probs = torch.sigmoid(room_logits)[0, 0].cpu().numpy()
            room_mask = (room_probs > threshold).astype(np.uint8)
            
            if return_boundary:
                boundary_logits = outputs['boundary']
                boundary_probs = torch.sigmoid(boundary_logits)[0, 0].cpu().numpy()
                boundary_mask = (boundary_probs > threshold).astype(np.uint8)
        
        # Resize to original size
        room_mask_resized = cv2.resize(
            room_mask, 
            orig_size, 
            interpolation=cv2.INTER_NEAREST
        )
        
        if return_boundary:
            boundary_mask_resized = cv2.resize(
                boundary_mask,
                orig_size,
                interpolation=cv2.INTER_NEAREST
            )
        
        # Prepare output directory
        if output_dir is None:
            output_dir = os.path.dirname(image_path)
        os.makedirs(output_dir, exist_ok=True)
        
        base_name = os.path.splitext(os.path.basename(image_path))[0]
        
        # Save mask
        if save_mask:
            mask_path = os.path.join(output_dir, f"{base_name}_predicted_mask.png")
            mask_img = Image.fromarray(room_mask_resized * 255)
            mask_img.save(mask_path)
            print(f"[INFO] Saved mask: {mask_path}")
        
        # Save overlay
        if save_overlay:
            overlay_path = os.path.join(output_dir, f"{base_name}_overlay.png")
            self._save_overlay(img, room_mask_resized, overlay_path)
            print(f"[INFO] Saved overlay: {overlay_path}")
        
        # Visualize
        if visualize:
            if return_boundary:
                self._visualize_with_boundary(img, room_mask_resized, boundary_mask_resized)
            else:
                self._visualize(img, room_mask_resized)
        
        # Prepare results
        results = {
            'room_mask': room_mask_resized,
            'room_probs': cv2.resize(room_probs, orig_size, interpolation=cv2.INTER_LINEAR),
            'image_path': image_path,
            'original_size': orig_size
        }
        
        if return_boundary:
            results['boundary_mask'] = boundary_mask_resized
            results['boundary_probs'] = cv2.resize(boundary_probs, orig_size, interpolation=cv2.INTER_LINEAR)
        
        return results
    
    def predict_batch(
        self,
        image_dir,
        output_dir=None,
        threshold=0.5,
        file_extension=".png"
    ):
        """
        Predict masks for all images in a directory
        
        Args:
            image_dir: Directory containing input images
            output_dir: Directory to save outputs
            threshold: Probability threshold
            file_extension: File extension to filter images
        
        Returns:
            List of result dictionaries
        """
        if output_dir is None:
            output_dir = os.path.join(image_dir, "predictions")
        os.makedirs(output_dir, exist_ok=True)
        
        # Find all images
        image_files = [
            f for f in os.listdir(image_dir) 
            if f.endswith(file_extension) and not f.endswith("_rooms.png")
        ]
        
        print(f"Found {len(image_files)} images to process")
        
        results = []
        for img_file in image_files:
            img_path = os.path.join(image_dir, img_file)
            print(f"\nProcessing: {img_file}")
            
            result = self.predict(
                img_path,
                threshold=threshold,
                visualize=False,
                save_mask=True,
                save_overlay=True,
                output_dir=output_dir
            )
            
            results.append(result)
        
        print(f"\n[INFO] Batch processing complete! Results saved to {output_dir}")
        return results
    
    def _visualize(self, img, mask):
        """Visualize image and mask"""
        fig, axes = plt.subplots(1, 3, figsize=(15, 5))
        
        axes[0].imshow(img)
        axes[0].set_title("Original Image")
        axes[0].axis('off')
        
        axes[1].imshow(mask, cmap='gray')
        axes[1].set_title("Predicted Room Mask")
        axes[1].axis('off')
        
        axes[2].imshow(img)
        axes[2].imshow(mask, cmap='jet', alpha=0.5)
        axes[2].set_title("Overlay")
        axes[2].axis('off')
        
        plt.tight_layout()
        plt.show()
    
    def _visualize_with_boundary(self, img, room_mask, boundary_mask):
        """Visualize image, room mask, and boundary mask"""
        fig, axes = plt.subplots(2, 2, figsize=(12, 12))
        
        axes[0, 0].imshow(img)
        axes[0, 0].set_title("Original Image")
        axes[0, 0].axis('off')
        
        axes[0, 1].imshow(room_mask, cmap='gray')
        axes[0, 1].set_title("Room Mask")
        axes[0, 1].axis('off')
        
        axes[1, 0].imshow(boundary_mask, cmap='gray')
        axes[1, 0].set_title("Boundary Mask")
        axes[1, 0].axis('off')
        
        axes[1, 1].imshow(img)
        axes[1, 1].imshow(room_mask, cmap='Reds', alpha=0.4)
        axes[1, 1].imshow(boundary_mask, cmap='Blues', alpha=0.4)
        axes[1, 1].set_title("Combined Overlay")
        axes[1, 1].axis('off')
        
        plt.tight_layout()
        plt.show()
    
    def _save_overlay(self, img, mask, save_path):
        """Save overlay image"""
        img_np = np.array(img)
        
        # Create colored mask
        mask_colored = np.zeros_like(img_np)
        mask_colored[:, :, 0] = mask * 255  # Red channel
        
        # Blend
        overlay = cv2.addWeighted(img_np, 0.7, mask_colored, 0.3, 0)
        
        overlay_img = Image.fromarray(overlay)
        overlay_img.save(save_path)
    
    def export_to_csv(self, mask, csv_path):
        """
        Export binary mask to CSV
        
        Args:
            mask: Binary mask (H, W)
            csv_path: Path to save CSV
        """
        np.savetxt(csv_path, mask, fmt='%d', delimiter=',')
        print(f"[INFO] Exported mask to CSV: {csv_path}")


# ==================== DEMO USAGE ====================
def demo():
    """
    Demonstration of predictor usage
    """
    # Initialize predictor
    predictor = SemafloorPredictor(
        checkpoint_path="checkpoints/best_semafloor_model.pth",
        img_size=512
    )
    
    # Single image prediction
    print("="*60)
    print("DEMO: Single Image Prediction")
    print("="*60)
    
    result = predictor.predict(
        image_path="demo2.jpg",
        threshold=0.5,
        return_boundary=True,
        visualize=True,
        save_mask=True,
        save_overlay=True,
        output_dir="outputs"
    )
    
    # Export to CSV
    csv_path = "outputs/sample_mask.csv"
    predictor.export_to_csv(result['room_mask'], csv_path)
    
    # Batch prediction (commented out - uncomment to use)
    # print("\n" + "="*60)
    # print("DEMO: Batch Prediction")
    # print("="*60)
    # 
    # results = predictor.predict_batch(
    #     image_dir="dataset/test",
    #     output_dir="outputs/batch",
    #     threshold=0.5
    # )
    # 
    # print(f"\nProcessed {len(results)} images")


if __name__ == "__main__":
    demo()