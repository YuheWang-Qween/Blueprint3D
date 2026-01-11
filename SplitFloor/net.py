import torch
import torch.nn as nn
import torch.nn.functional as F
import torchvision.models as models

class SplitFloor(nn.Module):
    """
    U-Net-like architecture with a ResNet-50 encoder.
    Uses concatenation for skip connections and bilinear upsampling for stability.
    """
    def __init__(self, num_classes: int = 4, pretrained: bool = True, freeze: bool = True):
        super(SplitFloor, self).__init__()
        
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.num_classes = 4
        
        # Initialize the ResNet-50 Encoder
        self._initialize_resnet_encoder(pretrained, freeze) 
        
        # --- Channel Planning ---
        # ResNet-50 output channels: [2048 (L4), 1024 (L3), 512 (L2), 256 (L1)]
        # dec_channels define the output channels of each refinement block
        dec_channels = [1024, 512, 256, 128] 
        
        # 1. Skip Connection Processing
        # Reduces channels of the encoder skips (L4, L3, L2) to match the decoder steps
        self.skip_convs = nn.ModuleList([
            self._conv_block(1024, 1024, kernel_size=1), # F4 (L3 output) -> 1024 
            self._conv_block(512, 512, kernel_size=1),   # F3 (L2 output) -> 512
            self._conv_block(256, 256, kernel_size=1)    # F2 (L1 output) -> 256
        ])
        
        # 2. Upsampling and Refinement Blocks (Decoder Path)
        self.decoder_blocks = nn.ModuleList([
            # Block 0: Pre-concatenation step: F5 (2048) -> C=1024
            self._conv_block(2048, 1024, 3, 1, 1), 
            
            # Block 1 (Post-concat F4): (1024 + 1024) = 2048 channels input -> 512 output
            self._refinement_block(2048, 512), 
            
            # Block 2 (Post-concat F3): (512 + 512) = 1024 channels input -> 256 output
            self._refinement_block(1024, 256), 
            
            # Block 3 (Post-concat F2): (256 + 256) = 512 channels input -> 128 output
            self._refinement_block(512, 128), 
        ])
        
        # 3. Final Output Head
        self.output_conv = nn.Conv2d(dec_channels[-1], num_classes, kernel_size=1)
        
    def _conv_block(
        self, 
        in_channels: int, 
        out_channels: int, 
        kernel_size: int, 
        stride: int = 1, 
        padding: int = 0
    ) -> nn.Sequential:
        # Determine padding for non-1x1 kernels
        if kernel_size > 1:
            padding = kernel_size // 2
        
        # Use bias=False with BatchNorm
        conv2d = nn.Conv2d(in_channels, out_channels, kernel_size, stride, padding, bias=False) 
        nn.init.kaiming_uniform_(conv2d.weight, nonlinearity='relu')
        
        return nn.Sequential(conv2d, nn.BatchNorm2d(out_channels), nn.ReLU(inplace=True))

    def _refinement_block(self, in_channels: int, out_channels: int) -> nn.Sequential:
        """Standard convolution block used after concatenation (typically 3x3)."""
        return self._conv_block(in_channels, out_channels, kernel_size=3)

    def _initialize_resnet_encoder(self, pretrained: bool, freeze: bool):
        encmodel = models.resnet50(weights=models.ResNet50_Weights.IMAGENET1K_V1 if pretrained else None)
        
        if freeze:
            for param in encmodel.parameters():
                param.requires_grad = False
                
        # Encoder Stages
        self.conv_in = nn.Sequential(encmodel.conv1, encmodel.bn1, encmodel.relu)
        
        self.features = nn.ModuleList([
            encmodel.layer1, # F2 (C=256, H/4) - Skip 3
            encmodel.layer2, # F3 (C=512, H/8) - Skip 2
            encmodel.layer3, # F4 (C=1024, H/16) - Skip 1
            encmodel.layer4  # F5 (C=2048, H/32) - Deepest feature/Decoder start
        ])

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        input_h, input_w = x.shape[2:]
        
        # --- Encoder Pass ---
        x = self.conv_in(x)
        
        # Collect features for skip connections: [F2, F3, F4, F5]
        encoder_skips = [] 
        for model in self.features:
            x = model(x)
            encoder_skips.append(x) 
        
        # Initialize decoder path with F5 features
        x = encoder_skips[-1] # F5: C=2048, H/32

        # --- Decoder Pass ---
        # The loop runs 3 times, combining F4, F3, and F2 skips respectively.
        # i=0: combines F4. Dec path: self.decoder_blocks[0] output (1024)
        # i=1: combines F3. Dec path: self.decoder_blocks[1] output (512)
        # i=2: combines F2. Dec path: self.decoder_blocks[2] output (256)
        
        # Start the decoder by running the first refinement block (Block 0: 2048 -> 1024)
        x = self.decoder_blocks[0](x) # x is now 1024 channels
        
        # Loop over the remaining skip features in reverse (F4, F3, F2)
        # Corresponding indices in encoder_skips are [2, 1, 0]
        for i, skip_idx in enumerate([2, 1, 0]):
            
            # Upsample the current decoder feature map (x) by 2x
            x = F.interpolate(x, scale_factor=2, mode='bilinear', align_corners=True)

            # Process the skip feature (F4, F3, or F2)
            skip_feature = self.skip_convs[i](encoder_skips[skip_idx])
            
            # Match sizes (handles potential non-standard input sizes)
            target_h, target_w = x.shape[2:]
            if skip_feature.shape[2] != target_h or skip_feature.shape[3] != target_w:
                skip_feature = F.interpolate(skip_feature, size=(target_h, target_w), mode='bilinear', align_corners=True)
            
            # Concatenation (Standard U-Net skip)
            x = torch.cat([x, skip_feature], dim=1)
            
            # Refinement Convolution (Block 1, 2, or 3)
            # i=0 -> Block 1; i=1 -> Block 2; i=2 -> Block 3
            x = self.decoder_blocks[i + 1](x) 

        # --- Final Output Head ---
        
        # Upsample to the original input resolution
        final_size = (input_h, input_w)
        
        x = F.interpolate(x, size=final_size, mode='bilinear', align_corners=True)
        
        # Final classification (128 channels -> num_classes)
        logits = self.output_conv(x)
        
        return logits