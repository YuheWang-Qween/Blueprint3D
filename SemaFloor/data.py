"""
RoomDataset: Binary segmentation dataset for architectural floor plans.

Features:
- Binary room masks (room=1, background=0)
- Optional boundary mask generation for wall detection
- Floor-plan-appropriate augmentation (rotations, flips)
"""

import os
import random
from typing import Optional, Tuple, Dict, List

import cv2
import numpy as np
import torch
from torch.utils.data import Dataset
import torchvision.transforms.functional as TF
from PIL import Image


class RoomDataset(Dataset):
    """
    Dataset for floor plan room segmentation
    
    Expected structure:
        root_dir/
            train/
                image1.png
                image1_rooms.png
            test/
                ...
    """
    
    def __init__(
        self, 
        root_dir: str, 
        split: str = "train", 
        img_size: int = 512, 
        augment: bool = True,
        generate_boundaries: bool = True
    ):
        """
        Args:
            root_dir: Path to dataset folder
            split: "train" or "test"
            img_size: Resize images to this size
            augment: Whether to apply data augmentation
            generate_boundaries: Whether to generate boundary masks for walls
        """
        self.root_dir = os.path.join(root_dir, split)
        self.img_size = img_size
        self.augment = augment and (split == "train")
        self.generate_boundaries = generate_boundaries
        
        # Collect image and mask pairs
        self.files = []
        for f in os.listdir(self.root_dir):
            if f.endswith(".png") and not f.endswith("_rooms.png"):
                mask_name = f.replace(".png", "_rooms.png")
                mask_path = os.path.join(self.root_dir, mask_name)
                img_path = os.path.join(self.root_dir, f)
                
                if os.path.exists(mask_path):
                    self.files.append((img_path, mask_path))
        
        if len(self.files) == 0:
            raise ValueError(f"No image-mask pairs found in {self.root_dir}")
        
        print(f"[{split.upper()}] Loaded {len(self.files)} image-mask pairs")
    
    def __len__(self) -> int:
        return len(self.files)
    
    def __getitem__(self, idx: int) -> Dict[str, torch.Tensor]:
        img_path, mask_path = self.files[idx]
        
        # ==================== LOAD IMAGE & MASK ====================
        img = Image.open(img_path).convert("RGB")
        mask = Image.open(mask_path).convert("RGB")
        
        # ==================== RESIZE ====================
        img = img.resize((self.img_size, self.img_size), Image.BILINEAR)
        mask = mask.resize((self.img_size, self.img_size), Image.NEAREST)
        
        # ==================== CREATE BINARY MASK ====================
        # Any non-black pixel is considered "room"
        mask_np = np.array(mask)
        room_mask = np.any(mask_np != [0, 0, 0], axis=-1).astype(np.float32)
        
        # ==================== GENERATE BOUNDARY MASK ====================
        boundary_mask = None
        if self.generate_boundaries:
            boundary_mask = self._extract_boundaries(room_mask)
        
        # ==================== DATA AUGMENTATION ====================
        if self.augment:
            img, room_mask, boundary_mask = self._augment(
                img, room_mask, boundary_mask
            )
        
        # ==================== CONVERT TO TENSORS ====================
        # Image: Simple normalization (0-1 range, no ImageNet stats)
        img_tensor = TF.to_tensor(img)
        
        # Normalize to [-1, 1] for better training stability
        img_tensor = (img_tensor - 0.5) / 0.5
        
        # Masks
        room_mask_tensor = torch.from_numpy(room_mask).unsqueeze(0).float()
        
        output = {
            'image': img_tensor,
            'room_mask': room_mask_tensor
        }
        
        if boundary_mask is not None:
            boundary_mask_tensor = torch.from_numpy(boundary_mask).unsqueeze(0).float()
            output['boundary_mask'] = boundary_mask_tensor
        
        return output
    
    def _extract_boundaries(self, room_mask: np.ndarray) -> np.ndarray:
        """
        Extract wall boundaries from room mask using morphological operations.
        
        Args:
            room_mask: Binary mask (H, W) with room=1, background=0
        
        Returns:
            boundary_mask: Binary mask (H, W) with boundaries=1
        """
        # Convert to uint8 for OpenCV
        mask_uint8 = (room_mask * 255).astype(np.uint8)
        
        # Morphological gradient to find edges
        kernel = np.ones((3, 3), np.uint8)
        gradient = cv2.morphologyEx(mask_uint8, cv2.MORPH_GRADIENT, kernel)
        
        # Threshold and normalize
        boundary_mask = (gradient > 0).astype(np.float32)
        
        return boundary_mask
    
    def _augment(
        self, 
        img: Image.Image, 
        room_mask: np.ndarray, 
        boundary_mask: Optional[np.ndarray] = None
    ) -> Tuple[Image.Image, np.ndarray, Optional[np.ndarray]]:
        """
        Apply floor-plan-appropriate augmentations.
        
        Args:
            img: PIL Image
            room_mask: numpy array (H, W)
            boundary_mask: numpy array (H, W) or None
        
        Returns:
            Augmented img, room_mask, boundary_mask
        """
        # Random horizontal flip
        if random.random() > 0.5:
            img = TF.hflip(img)
            room_mask = np.fliplr(room_mask).copy()
            if boundary_mask is not None:
                boundary_mask = np.fliplr(boundary_mask).copy()
        
        # Random vertical flip
        if random.random() > 0.5:
            img = TF.vflip(img)
            room_mask = np.flipud(room_mask).copy()
            if boundary_mask is not None:
                boundary_mask = np.flipud(boundary_mask).copy()
        
        # Random 90-degree rotation
        angle = random.choice([0, 90, 180, 270])
        if angle != 0:
            img = TF.rotate(img, angle)
            k = angle // 90
            room_mask = np.rot90(room_mask, k).copy()
            if boundary_mask is not None:
                boundary_mask = np.rot90(boundary_mask, k).copy()
        
        return img, room_mask, boundary_mask


# ==================== TEST ====================
if __name__ == "__main__":
    import matplotlib.pyplot as plt
    
    dataset = RoomDataset(
        root_dir="dataset", 
        split="train", 
        img_size=512,
        augment=True,
        generate_boundaries=True
    )
    
    print(f"Dataset size: {len(dataset)}")
    
    # Visualize a sample
    sample = dataset[0]
    
    img = sample['image']
    room_mask = sample['room_mask'].squeeze()
    boundary_mask = sample['boundary_mask'].squeeze()
    
    # Denormalize image for display
    img_display = (img * 0.5 + 0.5).permute(1, 2, 0).numpy()
    img_display = np.clip(img_display, 0, 1)
    
    fig, axes = plt.subplots(1, 4, figsize=(16, 4))
    
    axes[0].imshow(img_display)
    axes[0].set_title("Image")
    axes[0].axis('off')
    
    axes[1].imshow(room_mask, cmap='gray')
    axes[1].set_title("Room Mask")
    axes[1].axis('off')
    
    axes[2].imshow(boundary_mask, cmap='gray')
    axes[2].set_title("Boundary Mask")
    axes[2].axis('off')
    
    axes[3].imshow(img_display)
    axes[3].imshow(room_mask, cmap='jet', alpha=0.4)
    axes[3].set_title("Overlay")
    axes[3].axis('off')
    
    plt.tight_layout()
    plt.show()