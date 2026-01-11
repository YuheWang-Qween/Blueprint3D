# SplitFloor

SplitFloor is a deep learning module designed for **Structural Element Segmentation**. It classifies pixels into specific structural categories to define the skeleton of the building.

## Classes

The model segments the image into 4 classes:
0.  **Background**
1.  **Door**
2.  **Wall**
3.  **Window**

## Architecture

The model (`SplitFloor`) uses a U-Net-like architecture:
- **Encoder**: ResNet-50.
- **Decoder**: Custom refinement blocks with concatenation for skip connections and bilinear upsampling.

## Training

Training utilizes `albumentations` for data augmentation and tracks Mean IoU (mIoU) for validation.

```bash
# Train the model
python train.py
```

## Inference

```bash
python deploy.py --image path/to/image.png
```