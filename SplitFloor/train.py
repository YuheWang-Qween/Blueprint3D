import os
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader
import matplotlib.pyplot as plt
from tqdm import tqdm
from sklearn.metrics import jaccard_score

from net import SplitFloor
from data import SplitFloorDataset, get_train_transforms, get_val_transforms, NORM_MEAN, NORM_STD

# ====================================================================
# Loss Definitions
# ====================================================================

def dice_coeff(pred, target, smooth=1e-6):
    """Calculates the Sørensen–Dice coefficient (a.k.a. F1 score)"""
    # Flattens the tensors
    pred = pred.contiguous().view(-1)
    target = target.contiguous().view(-1)
    
    intersection = (pred * target).sum()
    union = pred.sum() + target.sum()
    
    dice = (2. * intersection + smooth) / (union + smooth)
    return dice

class DiceLoss(nn.Module):
    """Dice Loss for segmentation, handles class imbalance."""
    def __init__(self, weight=None, size_average=True):
        super(DiceLoss, self).__init__()

    def forward(self, inputs, targets, smooth=1e-6):
        # Convert targets (long) to one-hot for Dice calculation (C, H, W)
        # Assuming inputs are logits (N, C, H, W) and targets are class indices (N, H, W)
        num_classes = inputs.size(1)
        targets_one_hot = F.one_hot(targets, num_classes=num_classes).permute(0, 3, 1, 2).float()

        # Apply softmax/sigmoid to get probabilities
        inputs = F.softmax(inputs, dim=1)
        
        # Flatten label and prediction tensors
        inputs = inputs.contiguous().view(inputs.shape[0], inputs.shape[1], -1)
        targets_one_hot = targets_one_hot.contiguous().view(targets_one_hot.shape[0], targets_one_hot.shape[1], -1)
        
        # Calculate intersection and union
        intersection = (inputs * targets_one_hot).sum(dim=2)
        union = inputs.sum(dim=2) + targets_one_hot.sum(dim=2)
        
        dice = (2. * intersection + smooth) / (union + smooth)
        
        # Take mean over all classes and batch items
        return (1 - dice).mean()


class CombinedLoss(nn.Module):
    """Combines Cross-Entropy and Dice Loss."""
    def __init__(self):
        super().__init__()
        self.ce_criterion = nn.CrossEntropyLoss()
        self.dice_criterion = DiceLoss()

    def forward(self, pred, target):
        loss_ce = self.ce_criterion(pred, target)
        loss_dice = self.dice_criterion(pred, target)
        
        # Weighted combination (usually 1:1 or slightly favoring one)
        total_loss = loss_ce + loss_dice
        return total_loss

# ====================================================================
# Configuration Class
# ====================================================================

class CFG:
    # --- Data Paths ---
    DATASET_ROOT = "dataset"
    
    # --- Model Settings ---
    MODEL_NAME = "SplitFloor"
    PRETRAINED = True
    NUM_CLASSES = 4
    
    # --- Training Hyperparameters ---
    EPOCHS = 400
    TRAIN_BATCH_SIZE = 4
    VAL_BATCH_SIZE = 8
    LEARNING_RATE = 1e-4
    NUM_WORKERS = 8
    
    # --- Checkpoints & Output ---
    CHECKPOINT_DIR = "checkpoints"
    WEIGHTS_PATH = os.path.join("checkpoints", "splitfloor_best_miou.pth")

# ====================================================================
# Training and Evaluation Functions
# ====================================================================

# We use the native PyTorch Automatic Mixed Precision (AMP) scaler
scaler = torch.cuda.amp.GradScaler() if torch.cuda.is_available() else None

def train_one_epoch(model, loader, optimizer, criterion, device):
    """Handles the training logic for one epoch using Mixed Precision."""
    model.train()
    running_loss = 0.0
    
    for images, masks in tqdm(loader, desc="Training"):
        images = images.to(device)
        masks = masks.to(device)
        
        optimizer.zero_grad()
        
        # AMP context manager for mixed precision training
        with torch.cuda.amp.autocast(enabled=scaler is not None):
            outputs = model(images)
            loss = criterion(outputs, masks)
        
        if scaler is not None:
            # Scaler handles the forward and backward pass for AMP
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
        else:
            loss.backward()
            optimizer.step()
        
        running_loss += loss.item() * images.size(0)
        
    return running_loss / len(loader.dataset)

def calculate_miou(outputs, targets, num_classes):
    """Calculates Mean Intersection over Union (mIoU)."""
    # outputs: N, C, H, W -> N, H, W (class indices)
    preds = outputs.argmax(1).cpu().numpy()
    # targets: N, H, W
    targets = targets.cpu().numpy()
    
    miou = 0.0
    for pred, target in zip(preds, targets):
        # Flatten
        pred_flat = pred.flatten()
        target_flat = target.flatten()
        
        # Calculate Jaccard score (IoU) per image
        miou += jaccard_score(target_flat, pred_flat, average='macro', labels=np.arange(num_classes))
        
    return miou / len(preds)

def validate(model, loader, criterion, device, num_classes):
    """Handles the validation logic, calculating both Loss and mIoU."""
    model.eval()
    running_loss = 0.0
    running_miou = 0.0
    
    with torch.no_grad():
        for images, masks in tqdm(loader, desc="Validation"):
            images = images.to(device)
            masks = masks.to(device)
            
            with torch.cuda.amp.autocast(enabled=scaler is not None):
                outputs = model(images)
                loss = criterion(outputs, masks)
            
            running_loss += loss.item() * images.size(0)
            
            # Calculate mIoU
            miou_batch = calculate_miou(outputs, masks, num_classes)
            running_miou += miou_batch * images.size(0)

    val_loss = running_loss / len(loader.dataset)
    val_miou = running_miou / len(loader.dataset)
    
    return val_loss, val_miou

# ====================================================================
# Visualization Functions
# ====================================================================

def visualize_predictions(model, dataset, device, n=5):
    """Plots original image, ground truth mask, and model prediction."""
    model.eval()
    print("\n[INFO] Visualizing Predictions...")
    
    # Define inverse transform for visualization
    mean = np.array(NORM_MEAN)
    std = np.array(NORM_STD)
    
    for i in range(min(n, len(dataset))):
        image_tensor, mask_tensor = dataset[i]
        
        with torch.no_grad():
            output = model(image_tensor.unsqueeze(0).to(device))
            pred = output.argmax(1).squeeze(0).cpu().numpy() 
            
        # Un-normalize the image for visualization
        image_np = image_tensor.permute(1,2,0).cpu().numpy() 
        image_np = image_np * std + mean
        image_np = np.clip(image_np, 0, 1)

        # Plotting
        fig, axes = plt.subplots(1, 3, figsize=(15, 5))
        axes[0].imshow(image_np); axes[0].set_title("Input Image")
        axes[1].imshow(mask_tensor.numpy(), cmap='gray'); axes[1].set_title("Ground Truth Mask")
        axes[2].imshow(pred, cmap='viridis'); axes[2].set_title(f"Model Prediction (Classes 0 to {CFG.NUM_CLASSES - 1})")
        
        for ax in axes:
            ax.axis('off')
            
        plt.tight_layout()
        plt.show()

def plot_metrics(history, cfg):
    """Plots training and validation loss and mIoU over epochs."""
    
    # Enable interactive plotting (important for real-time updates)
    plt.ion()
    
    epochs = range(1, len(history['train_loss']) + 1)
    
    # --- Plot Loss ---
    fig_loss, ax_loss = plt.subplots(figsize=(10, 5))
    ax_loss.plot(epochs, history['train_loss'], 'r-o', label='Train Loss')
    ax_loss.plot(epochs, history['val_loss'], 'b-o', label='Validation Loss')
    ax_loss.set_title(f'{cfg.MODEL_NAME} Loss per Epoch')
    ax_loss.set_xlabel('Epoch')
    ax_loss.set_ylabel('Loss')
    ax_loss.legend()
    ax_loss.grid(True)
    
    # --- Plot mIoU ---
    fig_miou, ax_miou = plt.subplots(figsize=(10, 5))
    ax_miou.plot(epochs, history['val_miou'], 'g-o', label='Validation mIoU')
    ax_miou.set_title(f'{cfg.MODEL_NAME} mIoU per Epoch')
    ax_miou.set_xlabel('Epoch')
    ax_miou.set_ylabel('mIoU')
    ax_miou.legend()
    ax_miou.grid(True)

    # Redraw the canvas for an update
    plt.pause(0.1)
    plt.draw()
    
    # Save the final plots
    fig_loss.savefig(os.path.join(cfg.CHECKPOINT_DIR, 'loss_history.png'))
    fig_miou.savefig(os.path.join(cfg.CHECKPOINT_DIR, 'miou_history.png'))
    # Close figures to prevent memory leaks if running in a loop
    plt.close(fig_loss)
    plt.close(fig_miou)

# ====================================================================
# Main Training Function
# ====================================================================

def main(cfg: CFG):
    """Main training and validation loop."""
    
    # 1. Setup Device, Checkpoint Directory
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")
    os.makedirs(cfg.CHECKPOINT_DIR, exist_ok=True)
    
    # 2. Load Data
    print("\n[INFO] Loading Data...")
    train_dataset = SplitFloorDataset(
        images_dir=os.path.join(cfg.DATASET_ROOT, "train/images"),
        masks_dir=os.path.join(cfg.DATASET_ROOT, "train/masks"),
        transforms=get_train_transforms()
    )
    val_dataset = SplitFloorDataset(
        images_dir=os.path.join(cfg.DATASET_ROOT, "valid/images"),
        masks_dir=os.path.join(cfg.DATASET_ROOT, "valid/masks"),
        transforms=get_val_transforms()
    )

    train_loader = DataLoader(train_dataset, batch_size=cfg.TRAIN_BATCH_SIZE, 
                              shuffle=True, num_workers=cfg.NUM_WORKERS, pin_memory=True)
    val_loader = DataLoader(val_dataset, batch_size=cfg.VAL_BATCH_SIZE, 
                            shuffle=False, num_workers=cfg.NUM_WORKERS, pin_memory=True)
    
    print(f"Train samples: {len(train_dataset)}, Validation samples: {len(val_dataset)}")

    # 3. Initialize Model, Loss, Optimizer, and Scheduler
    print("\n[INFO] Initializing Model and Training components...")
    model = SplitFloor(num_classes=cfg.NUM_CLASSES, pretrained=cfg.PRETRAINED).to(device) 
    criterion = CombinedLoss()
    optimizer = torch.optim.AdamW(model.parameters(), lr=cfg.LEARNING_RATE)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=cfg.EPOCHS, eta_min=1e-6)
    
    best_val_miou = 0.0
    
    # History Dictionary for Plotting
    history = {
        'train_loss': [],
        'val_loss': [],
        'val_miou': []
    }
    
    # 4. Training Loop
    print("\n[INFO] Starting Training...")
    
    # Enable interactive mode for live plotting
    plt.ion() 
    
    for epoch in range(cfg.EPOCHS):
        
        train_loss = train_one_epoch(model, train_loader, optimizer, criterion, device)
        val_loss, val_miou = validate(model, val_loader, criterion, device, cfg.NUM_CLASSES)
        
        # Step the scheduler
        scheduler.step()
        
        # Record Metrics
        history['train_loss'].append(train_loss)
        history['val_loss'].append(val_loss)
        history['val_miou'].append(val_miou)
        
        # Plot Metrics after Every Epoch
        plot_metrics(history, cfg)
        
        print(f"\n[Epoch {epoch+1}/{cfg.EPOCHS}] | LR: {optimizer.param_groups[0]['lr']:.6f} | Train Loss: {train_loss:.4f} | Val Loss: {val_loss:.4f} | Val mIoU: {val_miou:.4f}")

        # Save Best Model Checkpoint based on mIoU
        if val_miou > best_val_miou:
            print(f"[INFO] Validation mIoU improved ({best_val_miou:.4f} -> {val_miou:.4f}). Saving model...")
            best_val_miou = val_miou
            torch.save(model.state_dict(), cfg.WEIGHTS_PATH)
            
    # Disable interactive mode after training is complete
    plt.ioff()
    
    # 5. Final Visualization
    print("\n[INFO] Training Finished")
    
    if os.path.exists(cfg.WEIGHTS_PATH):
        model.load_state_dict(torch.load(cfg.WEIGHTS_PATH, map_location=device))
        print(f"[INFO] Loaded best model from {cfg.WEIGHTS_PATH}")
    
    visualize_predictions(model, val_dataset, device, n=5)


if __name__ == "__main__":
    
    try:
        main(CFG)
    except FileNotFoundError as e:
        print(f"\n[ERROR] A required file or directory was not found. Please check the path: {e}")
        print("[ERROR] Ensure 'net.py' (containing the SplitFloor class) and the 'splitfloor_dataset' directory structure exist.")
    except Exception as e:
        print(f"\n[ERROR] An unexpected error occurred during execution: {e}")