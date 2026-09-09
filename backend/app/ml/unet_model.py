"""
OceanGuard — U-Net Segmentation Model
=======================================
SIH PS 26143 | NTRO

Architecture: U-Net with EfficientNet-B0 encoder (pre-trained on ImageNet)
  - Encoder: EfficientNet-B0  (~4M params, very lightweight)
  - Decoder: 4 upsampling blocks with skip connections
  - Head   : 1×1 conv → sigmoid binary mask

Why EfficientNet-B0 over ResNet-34 for RTX 3050:
  - EfficientNet-B0 : ~4M params,  ~1.1 GB VRAM @ batch 8
  - ResNet-34        : ~21M params, ~1.9 GB VRAM @ batch 8
  - EfficientNet-B0 trains faster, comparable accuracy on SAR data

Loss Function: Combined Dice + BCE
  - Dice Loss    : Handles class imbalance by maximizing overlap
  - BCE w/ weight: Penalizes false negatives (missing spill pixels)
  - Combined     : 0.5 * Dice + 0.5 * BCE (empirically best for SAR)

Input  : (B, 2, 256, 256)  — 2-channel SAR (VV + VH)
Output : (B, 1, 256, 256)  — binary spill mask (logits, pre-sigmoid)
"""

import torch
import torch.nn as nn
import torch.nn.functional as F


# ─── LOSS FUNCTIONS ──────────────────────────────────────────────────────────

class DiceLoss(nn.Module):
    """
    Soft Dice Loss for binary segmentation.
    Maximizes the overlap between predicted and ground-truth masks.
    More robust to class imbalance than pixel-wise BCE alone.
    """

    def __init__(self, smooth: float = 1.0):
        super().__init__()
        self.smooth = smooth

    def forward(self, logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        preds = torch.sigmoid(logits)

        # Flatten spatial dims
        preds_f   = preds.view(-1)
        targets_f = targets.view(-1)

        intersection = (preds_f * targets_f).sum()
        dice = (2.0 * intersection + self.smooth) / (
            preds_f.sum() + targets_f.sum() + self.smooth
        )
        return 1.0 - dice


class CombinedLoss(nn.Module):
    """
    Combined Dice + BCE loss — empirically best for SAR oil spill segmentation.

    Dice alone: unstable early training
    BCE alone : ignores class imbalance
    Combined  : stable + handles imbalance + good boundary precision
    """

    def __init__(self, pos_weight: float = 10.0, dice_weight: float = 0.5):
        super().__init__()
        self.dice_weight = dice_weight
        self.bce_weight  = 1.0 - dice_weight
        self.dice_loss   = DiceLoss(smooth=1.0)
        self.bce_loss    = nn.BCEWithLogitsLoss(
            pos_weight=torch.tensor([pos_weight])
        )

    def forward(self, logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        dice = self.dice_loss(logits, targets)
        bce  = self.bce_loss(logits, targets)
        return self.dice_weight * dice + self.bce_weight * bce


# ─── BUILDING BLOCKS ────────────────────────────────────────────────────────

class ConvBNReLU(nn.Module):
    """Conv2d → BatchNorm2d → ReLU block"""

    def __init__(self, in_channels: int, out_channels: int,
                 kernel_size: int = 3, padding: int = 1):
        super().__init__()
        self.block = nn.Sequential(
            nn.Conv2d(in_channels, out_channels, kernel_size, padding=padding, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True)
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.block(x)


class DoubleConv(nn.Module):
    """Two consecutive ConvBNReLU blocks (standard U-Net decoder block)"""

    def __init__(self, in_channels: int, out_channels: int):
        super().__init__()
        mid = (in_channels + out_channels) // 2
        self.block = nn.Sequential(
            ConvBNReLU(in_channels, mid),
            ConvBNReLU(mid, out_channels)
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.block(x)


class DecoderBlock(nn.Module):
    """
    U-Net decoder block: upsample + concatenate skip → DoubleConv
    """

    def __init__(self, in_channels: int, skip_channels: int, out_channels: int):
        super().__init__()
        self.upsample = nn.ConvTranspose2d(
            in_channels, in_channels // 2, kernel_size=2, stride=2
        )
        self.conv = DoubleConv(in_channels // 2 + skip_channels, out_channels)

    def forward(self, x: torch.Tensor, skip: torch.Tensor) -> torch.Tensor:
        x = self.upsample(x)

        # Handle size mismatch from rounding
        if x.shape != skip.shape:
            x = F.interpolate(x, size=skip.shape[2:], mode="bilinear", align_corners=False)

        x = torch.cat([x, skip], dim=1)
        return self.conv(x)


# ─── SIMPLE U-NET (no extra dependencies) ────────────────────────────────────

class OceanGuardUNet(nn.Module):
    """
    Lightweight U-Net for SAR oil spill binary segmentation.

    This implementation does NOT require segmentation-models-pytorch,
    so it works with just PyTorch.

    If segmentation-models-pytorch is available, use get_smp_model()
    instead for better pre-trained features.

    Architecture:
        Encoder: 4 downsampling stages (MaxPool)
        Bottleneck: 1024 channels
        Decoder: 4 upsampling stages (ConvTranspose2d)
        Head: 1×1 Conv → logits (no sigmoid — use BCEWithLogitsLoss)

    Input : (B, 2, H, W)   — 2-channel SAR (VV + VH)
    Output: (B, 1, H, W)   — logits
    """

    def __init__(self, in_channels: int = 2, base_filters: int = 32):
        super().__init__()
        f = base_filters  # 32 by default — doubles each encoder stage

        # ── Encoder ────────────────────────────────────────────────────
        self.enc1 = DoubleConv(in_channels, f)         # 32
        self.enc2 = DoubleConv(f,       f * 2)         # 64
        self.enc3 = DoubleConv(f * 2,   f * 4)         # 128
        self.enc4 = DoubleConv(f * 4,   f * 8)         # 256

        self.pool = nn.MaxPool2d(2)

        # ── Bottleneck ─────────────────────────────────────────────────
        self.bottleneck = DoubleConv(f * 8, f * 16)    # 512

        # ── Decoder ────────────────────────────────────────────────────
        self.dec4 = DecoderBlock(f * 16, f * 8,  f * 8)   # 512 → 256
        self.dec3 = DecoderBlock(f * 8,  f * 4,  f * 4)   # 256 → 128
        self.dec2 = DecoderBlock(f * 4,  f * 2,  f * 2)   # 128 → 64
        self.dec1 = DecoderBlock(f * 2,  f,      f)        # 64  → 32

        # ── Output Head ────────────────────────────────────────────────
        self.head = nn.Conv2d(f, 1, kernel_size=1)

        self._init_weights()

    def _init_weights(self):
        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                nn.init.kaiming_normal_(m.weight, mode="fan_out", nonlinearity="relu")
                if m.bias is not None:
                    nn.init.zeros_(m.bias)
            elif isinstance(m, nn.BatchNorm2d):
                nn.init.ones_(m.weight)
                nn.init.zeros_(m.bias)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # Encoder path with skip connections
        e1 = self.enc1(x)
        e2 = self.enc2(self.pool(e1))
        e3 = self.enc3(self.pool(e2))
        e4 = self.enc4(self.pool(e3))

        # Bottleneck
        b  = self.bottleneck(self.pool(e4))

        # Decoder path
        d4 = self.dec4(b,  e4)
        d3 = self.dec3(d4, e3)
        d2 = self.dec2(d3, e2)
        d1 = self.dec1(d2, e1)

        return self.head(d1)   # (B, 1, H, W) — raw logits


# ─── SMP-BACKED MODEL (better accuracy, requires smp package) ────────────────

def get_smp_model(encoder_name: str = "efficientnet-b0",
                  encoder_weights: str = "imagenet",
                  in_channels: int = 2) -> nn.Module:
    """
    Build a U-Net using segmentation-models-pytorch with a pre-trained encoder.

    EfficientNet-B0 on ImageNet is a good starting point even for SAR
    (low-level edge/texture features transfer well across domains).

    Falls back to OceanGuardUNet if smp is not installed.
    """
    try:
        import segmentation_models_pytorch as smp

        model = smp.Unet(
            encoder_name=encoder_name,
            encoder_weights=encoder_weights,
            in_channels=in_channels,
            classes=1,
            activation=None,      # No sigmoid — we use BCEWithLogitsLoss
        )
        print(f"✅ Using smp.Unet with {encoder_name} encoder ({encoder_weights} weights)")
        return model

    except ImportError:
        print("⚠️  segmentation-models-pytorch not available. Using custom U-Net.")
        return OceanGuardUNet(in_channels=in_channels)


# ─── METRICS ────────────────────────────────────────────────────────────────

def compute_iou(logits: torch.Tensor, targets: torch.Tensor,
                threshold: float = 0.5) -> float:
    """
    Compute Intersection over Union (IoU) for binary segmentation.
    This is the primary evaluation metric for oil spill detection.
    Target: IoU > 0.70
    """
    preds = (torch.sigmoid(logits) > threshold).float()
    targets = targets.float()

    intersection = (preds * targets).sum()
    union        = preds.sum() + targets.sum() - intersection

    if union == 0:
        return 1.0 if intersection == 0 else 0.0

    return float(intersection / (union + 1e-8))


def compute_f1(logits: torch.Tensor, targets: torch.Tensor,
               threshold: float = 0.5) -> float:
    """F1 score (Dice coefficient) — same as 2*IoU/(1+IoU)."""
    preds   = (torch.sigmoid(logits) > threshold).float()
    targets = targets.float()

    tp = (preds * targets).sum()
    fp = preds.sum() - tp
    fn = targets.sum() - tp

    f1 = 2 * tp / (2 * tp + fp + fn + 1e-8)
    return float(f1)


def model_summary(model: nn.Module, input_shape: tuple = (1, 2, 256, 256)):
    """Print model parameter count and estimated VRAM usage."""
    total_params     = sum(p.numel() for p in model.parameters())
    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)

    # Rough VRAM estimate: params * 4 bytes (fp32) * 2 (fwd+bwd) + activations
    vram_mb_fp32 = (total_params * 4 * 3) / (1024 ** 2)  # ×3 for optimizer state
    vram_mb_fp16 = vram_mb_fp32 / 2

    print(f"\n📐 Model Summary:")
    print(f"   Total params     : {total_params:,}")
    print(f"   Trainable params : {trainable_params:,}")
    print(f"   Est. VRAM (FP32) : {vram_mb_fp32:.0f} MB")
    print(f"   Est. VRAM (FP16) : {vram_mb_fp16:.0f} MB  ← AMP mode (recommended)")
    print(f"   RTX 3050 (4GB)   : {'✅ OK' if vram_mb_fp16 < 3000 else '⚠️  May be tight'}")
