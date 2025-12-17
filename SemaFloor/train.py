"""
SemafloorNet Training Script

Features:
- Mixed precision training (AMP)
- Combined loss: Focal + Dice + Boundary-weighted BCE
- Deep supervision
- IoU metric tracking
- Learning rate scheduling
- Best model checkpointing
- Real-time loss/metric plotting
"""

import os
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader
from torch import optim
from tqdm import tqdm
import matplotlib.pyplot as plt
import numpy as np

from net import SemafloorNet
from data import RoomDataset


# ==================== LOSS FUNCTIONS ====================

class FocalLoss(nn.Module):
    """
    Focal Loss for addressing class imbalance
    Focuses training on hard examples
    """
    def __init__(self, alpha=0.25, gamma=2.0):
        super().__init__()
        self.alpha = alpha
        self.gamma = gamma
    
    def forward(self, inputs, targets):
        """
        Args:
            inputs: logits (B, 1, H, W)
            targets: binary masks (B, 1, H, W)
        """
        bce_loss = F.binary_cross_entropy_with_logits(
            inputs, targets, reduction='none'
        )
        
        pt = torch.exp(-bce_loss)
        focal_loss = self.alpha * (1 - pt) ** self.gamma * bce_loss
        
        return focal_loss.mean()


class DiceLoss(nn.Module):
    """
    Dice Loss for segmentation
    Handles class imbalance geometrically
    """
    def __init__(self, smooth=1e-6):
        super().__init__()
        self.smooth = smooth
    
    def forward(self, inputs, targets):
        """
        Args:
            inputs: logits (B, 1, H, W)
            targets: binary masks (B, 1, H, W)
        """
        inputs = torch.sigmoid(inputs)
        
        # Flatten
        inputs = inputs.view(-1)
        targets = targets.view(-1)
        
        intersection = (inputs * targets).sum()
        union = inputs.sum() + targets.sum()
        
        dice = (2.0 * intersection + self.smooth) / (union + self.smooth)
        
        return 1 - dice


class BoundaryWeightedBCE(nn.Module):
    """
    BCE loss with higher weights on boundary pixels
    Encourages precise edge segmentation
    """
    def __init__(self, boundary_weight=10.0):
        super().__init__()
        self.boundary_weight = boundary_weight
    
    def forward(self, inputs, targets, boundary_mask):
        """
        Args:
            inputs: logits (B, 1, H, W)
            targets: binary masks (B, 1, H, W)
            boundary_mask: boundary weights (B, 1, H, W)
        """
        bce_loss = F.binary_cross_entropy_with_logits(
            inputs, targets, reduction='none'
        )
        
        # Weight boundary regions more heavily
        weights = boundary_mask * self.boundary_weight + 1.0
        weighted_loss = (weights * bce_loss).mean()
        
        return weighted_loss


class CombinedLoss(nn.Module):
    """
    Combined loss for floor plan segmentation
    - Focal loss for class imbalance
    - Dice loss for overlap
    - Boundary-weighted BCE for edge precision
    """
    def __init__(
        self, 
        focal_weight=1.0,
        dice_weight=1.0,
        boundary_weight=0.5,
        boundary_bce_weight=10.0
    ):
        super().__init__()
        
        self.focal_weight = focal_weight
        self.dice_weight = dice_weight
        self.boundary_weight = boundary_weight
        
        self.focal_loss = FocalLoss()
        self.dice_loss = DiceLoss()
        self.boundary_bce = BoundaryWeightedBCE(boundary_bce_weight)
    
    def forward(self, outputs, targets):
        """
        Args:
            outputs: dict with 'room', 'boundary', optionally 'aux3', 'aux2'
            targets: dict with 'room_mask', 'boundary_mask'
        """
        room_pred = outputs['room']
        room_target = targets['room_mask']
        boundary_target = targets['boundary_mask']
        
        # Main losses
        focal = self.focal_loss(room_pred, room_target)
        dice = self.dice_loss(room_pred, room_target)
        boundary_bce = self.boundary_bce(room_pred, room_target, boundary_target)
        
        total_loss = (
            self.focal_weight * focal +
            self.dice_weight * dice +
            self.boundary_weight * boundary_bce
        )
        
        # Deep supervision losses
        if 'aux3' in outputs:
            aux3_loss = F.binary_cross_entropy_with_logits(
                outputs['aux3'], room_target
            )
            total_loss += 0.4 * aux3_loss
        
        if 'aux2' in outputs:
            aux2_loss = F.binary_cross_entropy_with_logits(
                outputs['aux2'], room_target
            )
            total_loss += 0.4 * aux2_loss
        
        return total_loss, {
            'focal': focal.item(),
            'dice': dice.item(),
            'boundary_bce': boundary_bce.item()
        }


# ==================== METRICS ====================

def compute_iou(pred_logits, target, threshold=0.5, smooth=1e-6):
    """
    Compute Intersection over Union (IoU) metric
    
    Args:
        pred_logits: predicted logits (B, 1, H, W)
        target: ground truth masks (B, 1, H, W)
        threshold: threshold for binarization
        smooth: smoothing constant
    
    Returns:
        IoU score (float)
    """
    pred = torch.sigmoid(pred_logits)
    pred_bin = (pred > threshold).float()
    
    intersection = (pred_bin * target).sum()
    union = pred_bin.sum() + target.sum() - intersection
    
    iou = (intersection + smooth) / (union + smooth)
    
    return iou.item()


# ==================== TRAINING ====================

def train_epoch(model, loader, criterion, optimizer, scaler, device):
    """Train for one epoch"""
    model.train()
    
    total_loss = 0
    total_iou = 0
    loss_components = {'focal': 0, 'dice': 0, 'boundary_bce': 0}
    
    pbar = tqdm(loader, desc="Training")
    for batch in pbar:
        images = batch['image'].to(device)
        room_masks = batch['room_mask'].to(device)
        boundary_masks = batch['boundary_mask'].to(device)
        
        targets = {
            'room_mask': room_masks,
            'boundary_mask': boundary_masks
        }
        
        optimizer.zero_grad()
        
        # Mixed precision forward pass
        with torch.cuda.amp.autocast(enabled=device.type == 'cuda'):
            outputs = model(images)
            loss, loss_dict = criterion(outputs, targets)
        
        # Backward pass
        scaler.scale(loss).backward()
        scaler.step(optimizer)
        scaler.update()
        
        # Metrics
        iou = compute_iou(outputs['room'], room_masks)
        
        # Accumulate
        batch_size = images.size(0)
        total_loss += loss.item() * batch_size
        total_iou += iou * batch_size
        
        for key, val in loss_dict.items():
            loss_components[key] += val * batch_size
        
        pbar.set_postfix({
            'loss': loss.item(),
            'iou': iou
        })
    
    num_samples = len(loader.dataset)
    avg_loss = total_loss / num_samples
    avg_iou = total_iou / num_samples
    
    avg_components = {k: v / num_samples for k, v in loss_components.items()}
    
    return avg_loss, avg_iou, avg_components


def validate_epoch(model, loader, criterion, device):
    """Validate for one epoch"""
    model.eval()
    
    total_loss = 0
    total_iou = 0
    
    with torch.no_grad():
        for batch in tqdm(loader, desc="Validation"):
            images = batch['image'].to(device)
            room_masks = batch['room_mask'].to(device)
            boundary_masks = batch['boundary_mask'].to(device)
            
            targets = {
                'room_mask': room_masks,
                'boundary_mask': boundary_masks
            }
            
            # Forward pass
            with torch.cuda.amp.autocast(enabled=device.type == 'cuda'):
                outputs = model(images)
                loss, _ = criterion(outputs, targets)
            
            # Metrics
            iou = compute_iou(outputs['room'], room_masks)
            
            # Accumulate
            batch_size = images.size(0)
            total_loss += loss.item() * batch_size
            total_iou += iou * batch_size
    
    num_samples = len(loader.dataset)
    avg_loss = total_loss / num_samples
    avg_iou = total_iou / num_samples
    
    return avg_loss, avg_iou


def train_model(
    root_dir="dataset",
    img_size=512,
    batch_size=4,
    num_epochs=50,
    lr=5e-5,
    checkpoint_dir="checkpoints",
    device=None
):
    """
    Main training loop
    """
    
    # Device setup
    if device is None:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")
    
    # ==================== DATASETS ====================
    train_dataset = RoomDataset(
        root_dir=root_dir,
        split="train",
        img_size=img_size,
        augment=True,
        generate_boundaries=True
    )
    
    val_dataset = RoomDataset(
        root_dir=root_dir,
        split="test",
        img_size=img_size,
        augment=False,
        generate_boundaries=True
    )
    
    train_loader = DataLoader(
        train_dataset,
        batch_size=batch_size,
        shuffle=True,
        num_workers=4,
        pin_memory=True
    )
    
    val_loader = DataLoader(
        val_dataset,
        batch_size=1,
        shuffle=False,
        num_workers=2,
        pin_memory=True
    )
    
    # ==================== MODEL ====================
    model = SemafloorNet(pretrained=True, deep_supervision=True).to(device)
    
    # ==================== OPTIMIZER & SCHEDULER ====================
    optimizer = optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, 
        mode='min', 
        factor=0.5, 
        patience=5,
    )
    
    # ==================== LOSS & SCALER ====================
    criterion = CombinedLoss(
        focal_weight=1.0,
        dice_weight=1.0,
        boundary_weight=0.5,
        boundary_bce_weight=10.0
    )
    
    scaler = torch.cuda.amp.GradScaler(enabled=(device.type == 'cuda'))
    
    # ==================== CHECKPOINTING ====================
    os.makedirs(checkpoint_dir, exist_ok=True)
    best_val_loss = float('inf')
    
    # ==================== TRACKING ====================
    history = {
        'train_loss': [],
        'train_iou': [],
        'val_loss': [],
        'val_iou': [],
        'focal': [],
        'dice': [],
        'boundary_bce': []
    }
    
    # ==================== TRAINING LOOP ====================
    print(f"\nStarting training for {num_epochs} epochs...")
    print(f"Train samples: {len(train_dataset)}")
    print(f"Val samples: {len(val_dataset)}")
    print(f"Batch size: {batch_size}\n")
    
    for epoch in range(1, num_epochs + 1):
        print(f"\n{'='*60}")
        print(f"Epoch {epoch}/{num_epochs}")
        print(f"{'='*60}")
        
        # Train
        train_loss, train_iou, train_components = train_epoch(
            model, train_loader, criterion, optimizer, scaler, device
        )
        
        # Validate
        val_loss, val_iou = validate_epoch(
            model, val_loader, criterion, device
        )
        
        # Learning rate scheduling
        scheduler.step(val_loss)
        current_lr = optimizer.param_groups[0]['lr']
        
        # Log results
        print(f"\nResults:")
        print(f"  Train Loss: {train_loss:.4f} | Train IoU: {train_iou:.4f}")
        print(f"  Val Loss:   {val_loss:.4f} | Val IoU:   {val_iou:.4f}")
        print(f"  LR: {current_lr:.2e}")
        print(f"  Loss Components:")
        print(f"    - Focal: {train_components['focal']:.4f}")
        print(f"    - Dice:  {train_components['dice']:.4f}")
        print(f"    - Boundary BCE: {train_components['boundary_bce']:.4f}")
        
        # Update history
        history['train_loss'].append(train_loss)
        history['train_iou'].append(train_iou)
        history['val_loss'].append(val_loss)
        history['val_iou'].append(val_iou)
        history['focal'].append(train_components['focal'])
        history['dice'].append(train_components['dice'])
        history['boundary_bce'].append(train_components['boundary_bce'])
        
        # Save best model
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            checkpoint_path = os.path.join(checkpoint_dir, "best_semafloor_model.pth")
            torch.save({
                'epoch': epoch,
                'model_state_dict': model.state_dict(),
                'optimizer_state_dict': optimizer.state_dict(),
                'val_loss': val_loss,
                'val_iou': val_iou
            }, checkpoint_path)
            print(f"\n✓ Saved best model (val_loss: {val_loss:.4f})")
        
        # Save checkpoint every 10 epochs
        if epoch % 10 == 0:
            checkpoint_path = os.path.join(checkpoint_dir, f"semafloor_epoch_{epoch}.pth")
            torch.save({
                'epoch': epoch,
                'model_state_dict': model.state_dict(),
                'optimizer_state_dict': optimizer.state_dict(),
                'val_loss': val_loss,
                'val_iou': val_iou
            }, checkpoint_path)
            print(f"✓ Saved checkpoint at epoch {epoch}")
        
        # Plot training curves
        if epoch % 5 == 0 or epoch == 1:
            plot_training_curves(history, checkpoint_dir)
    
    print("\n" + "="*60)
    print("Training completed!")
    print(f"Best validation loss: {best_val_loss:.4f}")
    print("="*60)
    
    return history


def plot_training_curves(history, save_dir):
    """
    Plot and save training curves
    """
    epochs = range(1, len(history['train_loss']) + 1)
    
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    
    # Loss curves
    axes[0, 0].plot(epochs, history['train_loss'], 'b-', label='Train Loss', linewidth=2)
    axes[0, 0].plot(epochs, history['val_loss'], 'r-', label='Val Loss', linewidth=2)
    axes[0, 0].set_xlabel('Epoch')
    axes[0, 0].set_ylabel('Loss')
    axes[0, 0].set_title('Training and Validation Loss')
    axes[0, 0].legend()
    axes[0, 0].grid(True, alpha=0.3)
    
    # IoU curves
    axes[0, 1].plot(epochs, history['train_iou'], 'b-', label='Train IoU', linewidth=2)
    axes[0, 1].plot(epochs, history['val_iou'], 'r-', label='Val IoU', linewidth=2)
    axes[0, 1].set_xlabel('Epoch')
    axes[0, 1].set_ylabel('IoU')
    axes[0, 1].set_title('Training and Validation IoU')
    axes[0, 1].legend()
    axes[0, 1].grid(True, alpha=0.3)
    
    # Loss components
    axes[1, 0].plot(epochs, history['focal'], label='Focal Loss', linewidth=2)
    axes[1, 0].plot(epochs, history['dice'], label='Dice Loss', linewidth=2)
    axes[1, 0].plot(epochs, history['boundary_bce'], label='Boundary BCE', linewidth=2)
    axes[1, 0].set_xlabel('Epoch')
    axes[1, 0].set_ylabel('Loss')
    axes[1, 0].set_title('Loss Components')
    axes[1, 0].legend()
    axes[1, 0].grid(True, alpha=0.3)
    
    # Validation IoU trend
    axes[1, 1].plot(epochs, history['val_iou'], 'g-', linewidth=2)
    axes[1, 1].fill_between(epochs, history['val_iou'], alpha=0.3, color='green')
    axes[1, 1].set_xlabel('Epoch')
    axes[1, 1].set_ylabel('IoU')
    axes[1, 1].set_title('Validation IoU Trend')
    axes[1, 1].grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    # Save plot
    plot_path = os.path.join(save_dir, 'training_curves.png')
    plt.savefig(plot_path, dpi=150, bbox_inches='tight')
    plt.close()
    
    print(f"✓ Training curves saved to {plot_path}")


# ==================== MAIN ====================
if __name__ == "__main__":
    history = train_model(
        root_dir="dataset",
        img_size=512,
        batch_size=4,
        num_epochs=50,
        lr=5e-5,
        checkpoint_dir="checkpoints"
    )