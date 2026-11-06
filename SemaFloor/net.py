"""
SemafloorNet: Binary room segmentation for architectural floor plans
Features:
- ResNet50 encoder 
- ASPP module for multi-scale context
- Symmetric U-Net decoder with transposed convolutions
- Boundary refinement head for wall detection
- Deep supervision at intermediate stages
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from torchvision import models


class ASPP(nn.Module):
    """
    Atrous Spatial Pyramid Pooling
    Captures multi-scale context using parallel dilated convolutions
    """
    def __init__(self, in_channels, out_channels=256):
        super().__init__()
        
        # Multiple parallel atrous convolutions with different dilation rates
        self.conv1 = nn.Sequential(
            nn.Conv2d(in_channels, out_channels, 1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True)
        )
        
        self.conv2 = nn.Sequential(
            nn.Conv2d(in_channels, out_channels, 3, padding=6, dilation=6, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True)
        )
        
        self.conv3 = nn.Sequential(
            nn.Conv2d(in_channels, out_channels, 3, padding=12, dilation=12, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True)
        )
        
        self.conv4 = nn.Sequential(
            nn.Conv2d(in_channels, out_channels, 3, padding=18, dilation=18, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True)
        )
        
        # Global average pooling branch
        self.global_pool = nn.Sequential(
            nn.AdaptiveAvgPool2d(1),
            nn.Conv2d(in_channels, out_channels, 1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True)
        )
        
        # Projection to reduce concatenated channels
        self.project = nn.Sequential(
            nn.Conv2d(out_channels * 5, out_channels, 1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
            nn.Dropout(0.1)
        )
    
    def forward(self, x):
        size = x.shape[2:]
        
        # Parallel branches
        feat1 = self.conv1(x)
        feat2 = self.conv2(x)
        feat3 = self.conv3(x)
        feat4 = self.conv4(x)
        feat5 = self.global_pool(x)
        feat5 = F.interpolate(feat5, size=size, mode='bilinear', align_corners=False)
        
        # Concatenate and project
        out = torch.cat([feat1, feat2, feat3, feat4, feat5], dim=1)
        out = self.project(out)
        
        return out


class ConvBlock(nn.Module):
    """
    Double convolution block with BatchNorm and ReLU
    """
    def __init__(self, in_channels, out_channels):
        super().__init__()
        self.block = nn.Sequential(
            nn.Conv2d(in_channels, out_channels, 3, padding=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
            nn.Conv2d(out_channels, out_channels, 3, padding=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True)
        )
    
    def forward(self, x):
        return self.block(x)


class UpBlock(nn.Module):
    """
    Upsampling block using transposed convolution + ConvBlock
    Preserves sharp edges better than bilinear interpolation
    """
    def __init__(self, in_channels, skip_channels, out_channels):
        super().__init__()
        
        # Transposed convolution for upsampling
        self.up = nn.ConvTranspose2d(
            in_channels, in_channels, 
            kernel_size=2, stride=2
        )
        
        # Convolution block after concatenation
        self.conv = ConvBlock(in_channels + skip_channels, out_channels)
    
    def forward(self, x, skip):
        x = self.up(x)
        
        # Handle size mismatch
        if x.shape[2:] != skip.shape[2:]:
            x = F.interpolate(x, size=skip.shape[2:], mode='nearest')
        
        x = torch.cat([x, skip], dim=1)
        x = self.conv(x)
        
        return x


class SemafloorNet(nn.Module):
    """
    Binary room segmentation network for architectural floor plans
    
    Features:
    - ResNet50 encoder with preserved resolution
    - ASPP for multi-scale context
    - Symmetric U-Net decoder
    - Boundary refinement head
    - Deep supervision support
    """
    def __init__(self, pretrained=True, deep_supervision=True):
        super().__init__()
        
        self.deep_supervision = deep_supervision
        
        # ==================== ENCODER (ResNet50) ====================
        weights = models.ResNet50_Weights.IMAGENET1K_V1 if pretrained else None
        resnet = models.resnet50(weights=weights)
        
        # Modified stem: replace 7x7 stride-2 conv + maxpool with stride-2 conv only
        # This preserves more spatial information for thin walls
        self.enc0 = nn.Sequential(
            nn.Conv2d(3, 64, kernel_size=3, stride=2, padding=1, bias=False),
            resnet.bn1,
            resnet.relu
        )
        
        # ResNet layers (no maxpool before layer1)
        self.enc1 = resnet.layer1  # 64 channels, 1/2 resolution
        self.enc2 = resnet.layer2  # 256 channels, 1/4 resolution  
        self.enc3 = resnet.layer3  # 512 channels, 1/8 resolution
        self.enc4 = resnet.layer4  # 2048 channels, 1/16 resolution
        
        # ==================== ASPP (Bottleneck) ====================
        self.aspp = ASPP(2048, 512)
        
        # ==================== DECODER (Symmetric U-Net) ====================
        self.dec4 = UpBlock(512, 1024, 256)   # 1/8 resolution
        self.dec3 = UpBlock(256, 512, 128)    # 1/4 resolution
        self.dec2 = UpBlock(128, 256, 64)     # 1/2 resolution
        self.dec1 = UpBlock(64, 64, 64)       # 1/1 resolution (back to input size)
        
        # Additional upsampling to reach full resolution
        self.final_up = nn.Sequential(
            nn.ConvTranspose2d(64, 32, kernel_size=2, stride=2),
            nn.BatchNorm2d(32),
            nn.ReLU(inplace=True)
        )
        
        # ==================== SEGMENTATION HEADS ====================
        # Main room segmentation head
        self.room_head = nn.Conv2d(32, 1, kernel_size=1)
        
        # Boundary refinement head (detects walls/edges)
        self.boundary_head = nn.Sequential(
            nn.Conv2d(32, 16, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(16),
            nn.ReLU(inplace=True),
            nn.Conv2d(16, 1, kernel_size=1)
        )
        
        # ==================== DEEP SUPERVISION ====================
        if self.deep_supervision:
            self.aux3 = nn.Conv2d(128, 1, kernel_size=1)
            self.aux2 = nn.Conv2d(64, 1, kernel_size=1)
    
    def forward(self, x):
        input_size = x.shape[2:]
        
        # ==================== ENCODER ====================
        e0 = self.enc0(x)      # 1/2
        e1 = self.enc1(e0)     # 1/2
        e2 = self.enc2(e1)     # 1/4
        e3 = self.enc3(e2)     # 1/8
        e4 = self.enc4(e3)     # 1/16
        
        # ==================== ASPP ====================
        bottleneck = self.aspp(e4)  # 1/16
        
        # ==================== DECODER ====================
        d4 = self.dec4(bottleneck, e3)  # 1/8
        d3 = self.dec3(d4, e2)          # 1/4
        d2 = self.dec2(d3, e1)          # 1/2
        d1 = self.dec1(d2, e0)          # 1/1
        
        # Final upsampling
        d_final = self.final_up(d1)     # Full resolution
        
        # ==================== OUTPUTS ====================
        room_out = self.room_head(d_final)
        boundary_out = self.boundary_head(d_final)
        
        # Ensure output matches input size exactly
        if room_out.shape[2:] != input_size:
            room_out = F.interpolate(room_out, size=input_size, mode='bilinear', align_corners=False)
            boundary_out = F.interpolate(boundary_out, size=input_size, mode='bilinear', align_corners=False)
        
        # ==================== DEEP SUPERVISION OUTPUTS ====================
        if self.deep_supervision and self.training:
            aux3_out = self.aux3(d3)
            aux2_out = self.aux2(d2)
            
            # Upsample auxiliary outputs to match input size
            aux3_out = F.interpolate(aux3_out, size=input_size, mode='bilinear', align_corners=False)
            aux2_out = F.interpolate(aux2_out, size=input_size, mode='bilinear', align_corners=False)
            
            return {
                'room': room_out,
                'boundary': boundary_out,
                'aux3': aux3_out,
                'aux2': aux2_out
            }
        else:
            return {
                'room': room_out,
                'boundary': boundary_out
            }


# ==================== TEST ====================
if __name__ == "__main__":
    device = "cuda" if torch.cuda.is_available() else "cpu"
    
    model = SemafloorNet(pretrained=False, deep_supervision=True).to(device)
    model.train()
    
    x = torch.randn(2, 3, 512, 512).to(device)
    output = model(x)
    
    print(f"Input shape: {x.shape}")
    print(f"Room output shape: {output['room'].shape}")
    print(f"Boundary output shape: {output['boundary'].shape}")
    
    if 'aux3' in output:
        print(f"Aux3 output shape: {output['aux3'].shape}")
        print(f"Aux2 output shape: {output['aux2'].shape}")
    
    # Test inference mode
    model.eval()
    with torch.no_grad():
        output_eval = model(x)
    print(f"\nInference mode outputs: {list(output_eval.keys())}")
