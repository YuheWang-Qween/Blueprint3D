# SemaFloor

SemaFloor is a deep learning module designed for **Semantic Room Segmentation**. It identifies the habitable areas within a floor plan, distinguishing rooms from the background.

## Architecture

The model (`SemafloorNet`) is built upon a robust segmentation architecture:
- **Encoder**: ResNet-50 (pretrained on ImageNet).
- **Context Module**: ASPP (Atrous Spatial Pyramid Pooling) to capture multi-scale context.
- **Decoder**: Symmetric U-Net style decoder with transposed convolutions.
- **Heads**: 
    - Primary Room Head (Binary Segmentation).
    - Boundary Refinement Head (Edge detection).

## Training

The training script supports mixed precision (AMP), deep supervision, and a combined loss function (Focal + Dice + Boundary-weighted BCE).

```bash
# Train the model
python train.py
```

## Inference

Use `deploy.py` to generate masks for new images.

```bash
python deploy.py --image path/to/image.png
```

## Data Format

The dataset expects images and corresponding binary masks where white pixels represent rooms and black pixels represent the background.