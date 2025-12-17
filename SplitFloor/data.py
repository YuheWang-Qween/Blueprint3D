import os
import numpy as np
import torch
import torch.utils.data
from PIL import Image
import torchvision.transforms as T
import albumentations as A
from albumentations.pytorch import ToTensorV2

# =================================================
# Configuration Constants
# =================================================

# Same normalization as training
NORM_MEAN = [0.485, 0.456, 0.406]
NORM_STD = [0.229, 0.224, 0.225]

# =================================================
# Dataset Definition
# =================================================

class SplitFloorDataset(torch.utils.data.Dataset):
    def __init__(self, images_dir, masks_dir, transforms=None):
        self.images = sorted([os.path.join(images_dir, f) for f in os.listdir(images_dir) if f.endswith(".png")])
        self.masks = sorted([os.path.join(masks_dir, f) for f in os.listdir(masks_dir) if f.endswith(".png")])
        assert len(self.images) == len(self.masks), "Images and masks count mismatch"
        self.transforms = transforms

    def __len__(self):
        return len(self.images)

    def __getitem__(self, idx):
        # Image.open is mandatory for Albumentations to work
        image = np.array(Image.open(self.images[idx]).convert("RGB"))
        mask = np.array(Image.open(self.masks[idx]))
        
        if self.transforms:
            # Albumentations handles image and mask transformation together
            augmented = self.transforms(image=image, mask=mask)
            image = augmented['image']
            mask = augmented['mask'].long() # Masks must be type torch.long for CrossEntropyLoss
        else:
            image = T.ToTensor()(Image.fromarray(image))
            mask = torch.as_tensor(mask, dtype=torch.long)
            
        return image, mask

# =================================================
# Transform Functions
# =================================================

def get_train_transforms():
    """Returns training augmentation pipeline."""
    return A.Compose([
        A.Resize(512, 512), # Ensure input size matches your ResNet/U-Net
        A.HorizontalFlip(p=0.5),
        A.ShiftScaleRotate(shift_limit=0.05, scale_limit=0.05, rotate_limit=15, p=0.5),
        A.HueSaturationValue(hue_shift_limit=20, sat_shift_limit=30, val_shift_limit=20, p=0.5),
        A.RandomBrightnessContrast(p=0.5),
        A.Normalize(mean=NORM_MEAN, std=NORM_STD),
        ToTensorV2(),
    ])

def get_val_transforms():
    """Returns validation transform pipeline (only resizing and normalization)."""
    return A.Compose([
        A.Resize(512, 512),
        A.Normalize(mean=NORM_MEAN, std=NORM_STD),
        ToTensorV2(),
    ])

# =================================================
# Image Preprocessing for Inference
# =================================================

def preprocess_image(image_path):
    """
    Preprocess a single image for inference.
    Returns: (tensor, original_size)
    """
    image = np.array(Image.open(image_path).convert("RGB"))
    orig_h, orig_w = image.shape[:2]  # store original size

    tf = A.Compose([
        A.Resize(512, 512),
        A.Normalize(mean=NORM_MEAN, std=NORM_STD),
        ToTensorV2(),
    ])

    sample = tf(image=image)
    return sample["image"].unsqueeze(0), (orig_h, orig_w)  # (1, C, H, W), original size

# =================================================
# Size Restoration Utility
# =================================================

def restore_size(mask, orig_size):
    """Restore mask to original image size."""
    orig_h, orig_w = orig_size
    mask_img = Image.fromarray(mask.astype(np.uint8))
    mask_resized = mask_img.resize((orig_w, orig_h), resample=Image.NEAREST)
    return np.array(mask_resized, dtype=np.uint8)  # ensure integer class values