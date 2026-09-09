"""
OceanGuard — PyTorch Dataset + Augmentation Pipeline
======================================================
SIH PS 26143 | NTRO

Provides:
  - SARSpillDataset  : PyTorch Dataset that loads preprocessed .npy patches
  - get_transforms() : Albumentations augmentation pipeline (SAR-specific)
  - get_dataloaders(): Returns train/val DataLoaders ready for training
  - class_weights()  : Computes BCE pos_weight from dataset stats

RTX 3050 Note:
  batch_size=8 on 256×256 patches uses ~1.8 GB VRAM.
  With mixed precision (FP16): ~0.9 GB → leaves room for model (~1.5 GB).
  Total: ~2.4 GB VRAM — well within 4 GB limit.
"""

import os
import json
import random
import numpy as np
from pathlib import Path
from typing import Optional, Tuple, Callable

import torch
from torch.utils.data import Dataset, DataLoader, random_split

try:
    import albumentations as A
    from albumentations.pytorch import ToTensorV2
    HAS_ALBUMENTATIONS = True
except ImportError:
    HAS_ALBUMENTATIONS = False
    print("⚠️  albumentations not installed. Using basic numpy augmentation.")


# ─── DATASET CLASS ───────────────────────────────────────────────────────────

class SARSpillDataset(Dataset):
    """
    PyTorch Dataset for SAR oil spill segmentation.

    Loads preprocessed .npy patch files created by sar_preprocessor.py.

    Expected directory structure:
        data_dir/
          patches/
            images/  0000_0000.npy  (float32, shape: H×W×C)
            masks/   0000_0000.npy  (uint8,   shape: H×W)

    Args:
        data_dir  : Path to preprocessed dataset split directory
        transform : Albumentations transform (applied to both image & mask)
        split     : 'train' or 'val' (controls augmentation behavior)
    """

    def __init__(self,
                 data_dir: Path,
                 transform: Optional[Callable] = None,
                 split: str = "train"):
        self.data_dir  = Path(data_dir)
        self.transform = transform
        self.split     = split

        img_dir = self.data_dir / "patches" / "images"
        msk_dir = self.data_dir / "patches" / "masks"

        if not img_dir.exists():
            raise FileNotFoundError(
                f"Patches not found at {img_dir}\n"
                f"Run: python scripts/download_dataset.py first,\n"
                f"then: python app/ml/sar_preprocessor.py"
            )

        # Collect matched pairs
        img_files = sorted(img_dir.glob("*.npy"))
        self.pairs = []
        for img_f in img_files:
            msk_f = msk_dir / img_f.name
            if msk_f.exists():
                self.pairs.append((img_f, msk_f))
            else:
                print(f"⚠️  No mask for {img_f.name}, skipping.")

        if len(self.pairs) == 0:
            raise ValueError(f"No valid image-mask pairs found in {data_dir}")

        print(f"📦 [{split.upper()}] Loaded {len(self.pairs)} patches from {data_dir.name}")

    def __len__(self) -> int:
        return len(self.pairs)

    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, torch.Tensor]:
        img_path, msk_path = self.pairs[idx]

        # Load .npy files (fast, no TIFF decoding overhead)
        image = np.load(img_path).astype(np.float32)   # (H, W, C)
        mask  = np.load(msk_path).astype(np.float32)   # (H, W)

        # Handle single-band images: duplicate band for 2-channel input
        if image.ndim == 2:
            image = np.stack([image, image], axis=-1)
        elif image.shape[2] == 1:
            image = np.concatenate([image, image], axis=-1)

        # Ensure correct value ranges
        image = np.clip(image, 0.0, 1.0)
        mask  = np.clip(mask,  0.0, 1.0)

        # Apply augmentation transforms
        if self.transform is not None:
            augmented = self.transform(image=image, mask=mask)
            image = augmented["image"]   # tensor after ToTensorV2
            mask  = augmented["mask"]
        else:
            # Manual conversion to tensor
            image = torch.from_numpy(image.transpose(2, 0, 1))   # (C, H, W)
            mask  = torch.from_numpy(mask)

        # Ensure mask is (1, H, W) float for BCEWithLogitsLoss
        if mask.ndim == 2:
            mask = mask.unsqueeze(0)

        return image, mask

    def get_stats(self) -> dict:
        """Returns basic dataset statistics."""
        spill_pixels = 0
        total_pixels = 0
        for _, msk_path in self.pairs:
            msk = np.load(msk_path)
            spill_pixels += int(msk.sum())
            total_pixels += msk.size
        spill_ratio = spill_pixels / max(total_pixels, 1)
        return {
            "total_patches": len(self.pairs),
            "spill_ratio": round(spill_ratio, 4),
            "background_ratio": round(1 - spill_ratio, 4),
            "pos_weight": round((1 - spill_ratio) / max(spill_ratio, 1e-6), 2)
        }


# ─── AUGMENTATION PIPELINE ───────────────────────────────────────────────────

def get_transforms(split: str = "train",
                   patch_size: int = 256) -> Optional[Callable]:
    """
    Build SAR-specific augmentation pipeline using Albumentations.

    SAR-specific choices:
      - NO color jitter (SAR data is not optical)
      - NO random brightness/contrast on dB values
      - YES to geometric augmentations (flips, rotations)
      - YES to elastic deform (simulates spill shape variation)
      - YES to Gaussian noise (simulates thermal noise)
      - YES to coarse dropout (simulates missing data / ship shadows)

    Returns:
        Albumentations Compose transform, or None if not installed.
    """
    if not HAS_ALBUMENTATIONS:
        return None

    if split == "train":
        transform = A.Compose([
            # ── Geometric ──────────────────────────────────────────────
            A.HorizontalFlip(p=0.5),
            A.VerticalFlip(p=0.5),
            A.RandomRotate90(p=0.5),
            A.ShiftScaleRotate(
                shift_limit=0.05,
                scale_limit=0.1,
                rotate_limit=15,
                border_mode=0,   # constant border (black)
                p=0.4
            ),

            # ── SAR-specific noise ──────────────────────────────────────
            A.GaussNoise(
                var_limit=(0.001, 0.005),  # Small — SAR noise is subtle
                p=0.3
            ),

            # ── Occlusion / robustness ──────────────────────────────────
            A.CoarseDropout(
                max_holes=4,
                min_holes=1,
                max_height=48,
                min_height=16,
                max_width=48,
                min_width=16,
                fill_value=0.0,   # dark = low SAR backscatter (water)
                p=0.25
            ),

            # ── Convert to tensor ───────────────────────────────────────
            ToTensorV2()
        ])

    else:  # val / test — no augmentation, just convert
        transform = A.Compose([
            ToTensorV2()
        ])

    return transform


# ─── DATALOADERS ─────────────────────────────────────────────────────────────

def get_dataloaders(data_dirs: dict,
                    batch_size: int = 8,
                    val_split: float = 0.15,
                    num_workers: int = 2,
                    pin_memory: bool = True) -> Tuple[DataLoader, DataLoader]:
    """
    Create train and validation DataLoaders from multiple dataset splits.

    Args:
        data_dirs  : Dict with keys like 'spills', 'lookalikes'
                     pointing to preprocessed split directories
        batch_size : Training batch size (8 recommended for RTX 3050)
        val_split  : Fraction of data reserved for validation
        num_workers: Parallel data loading workers. Default=2 (safe on Windows)
                     Increase to 4 on Linux for faster loading.
        pin_memory : Speeds up GPU transfer (True if using CUDA)

    Returns:
        (train_loader, val_loader)
    """
    train_transform = get_transforms("train")
    val_transform   = get_transforms("val")

    # Load all splits and concatenate
    all_datasets = []
    for split_name, dir_path in data_dirs.items():
        dir_path = Path(dir_path)
        if not dir_path.exists():
            print(f"⚠️  Skipping {split_name}: {dir_path} does not exist")
            continue
        try:
            ds = SARSpillDataset(dir_path, transform=None, split=split_name)
            all_datasets.append(ds)
        except (FileNotFoundError, ValueError) as e:
            print(f"⚠️  Could not load {split_name}: {e}")

    if not all_datasets:
        raise ValueError("No valid dataset splits found. Run download + preprocess first.")

    from torch.utils.data import ConcatDataset
    combined = ConcatDataset(all_datasets)
    total_size = len(combined)

    # Train / val split
    val_size   = max(1, int(total_size * val_split))
    train_size = total_size - val_size
    train_ds, val_ds = random_split(
        combined, [train_size, val_size],
        generator=torch.Generator().manual_seed(42)
    )

    # Apply transforms separately
    # (Wrap with transform adapter since random_split doesn't support per-set transforms)
    train_ds = TransformWrapper(train_ds, train_transform)
    val_ds   = TransformWrapper(val_ds,   val_transform)

    train_loader = DataLoader(
        train_ds,
        batch_size=batch_size,
        shuffle=True,
        num_workers=num_workers,
        pin_memory=pin_memory,
        drop_last=True,          # Keep batch size consistent for batch norm
        persistent_workers=(num_workers > 0)
    )

    val_loader = DataLoader(
        val_ds,
        batch_size=batch_size,
        shuffle=False,
        num_workers=num_workers,
        pin_memory=pin_memory,
        drop_last=False,
        persistent_workers=(num_workers > 0)
    )

    print(f"\n📊 DataLoader Summary:")
    print(f"   Train : {train_size} patches → {len(train_loader)} batches × batch_size {batch_size}")
    print(f"   Val   : {val_size} patches   → {len(val_loader)} batches")
    print(f"   Workers: {num_workers}")

    return train_loader, val_loader


class TransformWrapper(Dataset):
    """Wraps a Subset to apply transforms that require image+mask together."""

    def __init__(self, subset, transform):
        self.subset    = subset
        self.transform = transform

    def __len__(self):
        return len(self.subset)

    def __getitem__(self, idx):
        # Get raw numpy arrays from the underlying dataset
        # Each item is already a (tensor, tensor) from SARSpillDataset
        # We need raw numpy — work around by bypassing transform
        item = self.subset[idx]
        if self.transform is None:
            return item

        image, mask = item
        # Convert back to numpy for albumentations
        if isinstance(image, torch.Tensor):
            image = image.numpy().transpose(1, 2, 0)   # C,H,W → H,W,C
        if isinstance(mask, torch.Tensor):
            mask  = mask.numpy().squeeze(0)             # 1,H,W → H,W

        augmented = self.transform(image=image.astype(np.float32),
                                   mask=mask.astype(np.float32))
        image = augmented["image"]
        mask  = augmented["mask"]

        if mask.ndim == 2:
            mask = mask.unsqueeze(0)

        return image.float(), mask.float()


# ─── CLASS WEIGHT HELPER ─────────────────────────────────────────────────────

def load_pos_weight(stats_json_path: Path) -> float:
    """
    Load the precomputed BCE pos_weight from stats.json.
    This handles severe class imbalance (oil spills are rare in SAR images).

    pos_weight > 1 means the model is penalized more for missing spill pixels.
    Typical value: 8-20 for oil spill datasets.
    """
    stats_path = Path(stats_json_path)
    if stats_path.exists():
        with open(stats_path) as f:
            stats = json.load(f)
        pw = stats.get("pos_weight_for_bce", 10.0)
        print(f"⚖️  BCE pos_weight loaded from stats: {pw}")
        return float(pw)
    else:
        default = 10.0
        print(f"⚠️  stats.json not found. Using default pos_weight={default}")
        return default
