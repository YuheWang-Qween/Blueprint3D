import os
import numpy as np
import torch
from PIL import Image
import pandas as pd

from net import SplitFloor
from data import preprocess_image, restore_size

# =================================================
# Configuration
# =================================================

MODEL_WEIGHTS = "checkpoints/splitfloor_best_miou.pth"
NUM_CLASSES = 4

OUTPUT_MASK_RAW = "output_mask_raw.png"      # uses class indices
OUTPUT_MASK_COLOR = "output_mask_colored.png"
OUTPUT_CSV = "output_mask.csv"

# =================================================
# Color Map (Editable)
# =================================================
COLOR_MAP = {
    0: (0,   0,   0),        # Background – black
    1: (255, 0,   0),        # Class 1 – red
    2: (0,   255, 0),        # Class 2 – green
    3: (0,   0,   255),      # Class 3 – blue
}

# =================================================
# Save class-index mask (raw)
# =================================================

def save_raw_mask(pred_mask, save_path):
    Image.fromarray(pred_mask.astype(np.uint8)).save(save_path)
    print(f"Saved raw mask → {save_path}")

# =================================================
# Create & save colorized mask
# =================================================

def save_color_mask(pred_mask, save_path):
    h, w = pred_mask.shape
    color_img = np.zeros((h, w, 3), dtype=np.uint8)

    for cls, color in COLOR_MAP.items():
        color_img[pred_mask == cls] = color

    Image.fromarray(color_img).save(save_path)
    print(f"Saved colored mask → {save_path}")

# =================================================
# Save CSV containing only class indices (0-3)
# =================================================

def save_csv(pred_mask, save_path):
    # Ensure values are integers and in 0..NUM_CLASSES-1
    pred_mask = pred_mask.astype(np.uint8)
    pred_mask[pred_mask >= NUM_CLASSES] = 0  # safety check
    # Save without index or header
    pd.DataFrame(pred_mask).to_csv(save_path, index=False, header=False)
    print(f"Saved CSV → {save_path}")

# =================================================
# Inference
# =================================================

def infer(image_path):
    device = "cuda" if torch.cuda.is_available() else "cpu"

    # Load model
    model = SplitFloor(num_classes=NUM_CLASSES).to(device)
    model.load_state_dict(torch.load(MODEL_WEIGHTS, map_location=device))
    model.eval()

    img_tensor, orig_size = preprocess_image(image_path)
    img_tensor = img_tensor.to(device)

    with torch.no_grad():
        pred = model(img_tensor).argmax(1).squeeze(0).cpu().numpy()

    # Restore mask to original image size
    pred = restore_size(pred, orig_size)

    # Outputs
    save_raw_mask(pred, OUTPUT_MASK_RAW)
    save_color_mask(pred, OUTPUT_MASK_COLOR)
    save_csv(pred, OUTPUT_CSV)

    print("\n✓ Inference complete.")
    print(f"Files generated:\n - {OUTPUT_MASK_RAW}\n - {OUTPUT_MASK_COLOR}\n - {OUTPUT_CSV}")

# =================================================
# Main
# =================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--image", type=str, required=True,
                        help="Path to input image")

    args = parser.parse_args()
    infer(args.image)