"""
OceanGuard — SAR Image Preprocessor
=====================================
SIH PS 26143 | NTRO

Handles the full preprocessing pipeline for Sentinel-1 SAR imagery:
  1. Load GeoTIFF (2048×2048×2 — VV and VH polarization bands)
  2. Apply Lee Speckle Filter (removes SAR multiplicative noise)
  3. Normalize sigma-nought dB values to [0, 1]
  4. Extract 256×256 patches (sliding window with overlap)
  5. Save patches as numpy arrays for fast training loading

RTX 3050 Note:
  Full 2048×2048 image cannot fit in 4GB VRAM.
  This extractor creates 256×256 patches — each image → 64 patches.
  200 images → ~12,800 training patches total.
"""

import os
import json
import numpy as np
from pathlib import Path
from typing import Optional, Tuple, List
from tqdm import tqdm

try:
    import rasterio
    from rasterio.errors import RasterioIOError
    HAS_RASTERIO = True
except ImportError:
    HAS_RASTERIO = False
    print("⚠️  rasterio not installed. Using PIL fallback for non-GeoTIFF images.")

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

from scipy.ndimage import uniform_filter
from scipy.ndimage import variance as ndimage_variance


# ─── LEE SPECKLE FILTER ────────────────────────────────────────────────────────

def lee_speckle_filter(image: np.ndarray, window_size: int = 7) -> np.ndarray:
    """
    Apply Lee adaptive speckle filter to a SAR image band.
    
    SAR images suffer from multiplicative speckle noise (granular texture).
    The Lee filter uses local statistics (mean/variance) to adaptively
    smooth speckle while preserving edges and bright targets.
    
    Args:
        image      : 2D numpy array (single polarization band)
        window_size: Odd integer, size of local filter window (default: 7)
    
    Returns:
        Filtered 2D numpy array, same shape as input
    """
    img = image.astype(np.float64)

    # Local mean via uniform filter
    local_mean = uniform_filter(img, window_size)

    # Local variance: E[X²] - E[X]²
    local_sq_mean = uniform_filter(img ** 2, window_size)
    local_var = local_sq_mean - local_mean ** 2

    # Overall image noise variance (estimated from median local variance)
    noise_var = np.mean(local_var)

    # Lee filter weight
    weight = local_var / (local_var + noise_var + 1e-10)

    # Filtered output
    filtered = local_mean + weight * (img - local_mean)

    return filtered.astype(np.float32)


# ─── NORMALIZATION ────────────────────────────────────────────────────────────

def normalize_sar_band(band: np.ndarray,
                       clip_min: float = -30.0,
                       clip_max: float = 0.0) -> np.ndarray:
    """
    Normalize a SAR sigma-nought dB band to [0, 1].
    
    Sentinel-1 SAR backscatter ranges roughly from -30 dB (water/dark areas)
    to 0 dB (bright targets). Oil spills appear as dark patches (~-20 to -30 dB).
    
    Args:
        band    : 2D numpy array with dB values
        clip_min: Lower clip value in dB (default: -30.0)
        clip_max: Upper clip value in dB (default: 0.0)
    
    Returns:
        Normalized 2D numpy float32 array in [0, 1]
    """
    clipped = np.clip(band, clip_min, clip_max)
    normalized = (clipped - clip_min) / (clip_max - clip_min + 1e-10)
    return normalized.astype(np.float32)


# ─── TIFF LOADING ────────────────────────────────────────────────────────────

def load_sar_image(path: Path) -> Optional[np.ndarray]:
    """
    Load a Sentinel-1 SAR GeoTIFF.
    Returns numpy array of shape (H, W, 2) — [VV, VH] or [VH, VV].
    Returns None on failure.
    """
    path = Path(path)
    if not path.exists():
        print(f"❌ File not found: {path}")
        return None

    # Try rasterio first (preserves geospatial metadata)
    if HAS_RASTERIO:
        try:
            with rasterio.open(path) as src:
                data = src.read()  # shape: (bands, H, W)
                if data.ndim == 3:
                    return np.transpose(data, (1, 2, 0)).astype(np.float32)  # → (H, W, bands)
                elif data.ndim == 2:
                    return data[:, :, np.newaxis].astype(np.float32)
        except RasterioIOError as e:
            print(f"⚠️  rasterio failed ({e}), trying PIL fallback...")

    # Fallback: PIL
    if HAS_PIL:
        try:
            img = Image.open(path)
            arr = np.array(img).astype(np.float32)
            if arr.ndim == 2:
                arr = arr[:, :, np.newaxis]
            return arr
        except Exception as e:
            print(f"❌ PIL also failed: {e}")

    return None


def load_mask(path: Path) -> Optional[np.ndarray]:
    """
    Load a binary segmentation mask.
    Returns numpy array of shape (H, W) with values {0, 1}.
    """
    path = Path(path)
    if not path.exists():
        return None

    if HAS_RASTERIO:
        try:
            with rasterio.open(path) as src:
                mask = src.read(1).astype(np.uint8)
                return np.clip(mask, 0, 1)
        except Exception:
            pass

    if HAS_PIL:
        try:
            img = Image.open(path)
            arr = np.array(img).astype(np.uint8)
            if arr.ndim == 3:
                arr = arr[:, :, 0]
            return np.clip(arr, 0, 1)
        except Exception as e:
            print(f"❌ Mask load failed: {e}")

    return None


# ─── PATCH EXTRACTION ────────────────────────────────────────────────────────

def extract_patches(image: np.ndarray,
                    mask: np.ndarray,
                    patch_size: int = 256,
                    stride: int = 192,
                    min_spill_ratio: float = 0.0) -> Tuple[List[np.ndarray], List[np.ndarray]]:
    """
    Extract overlapping patches from a full SAR image and its mask.
    
    Args:
        image          : (H, W, C) numpy array
        mask           : (H, W) numpy array
        patch_size     : Size of each square patch (default: 256)
        stride         : Step between patches — smaller = more overlap (default: 192)
        min_spill_ratio: Min fraction of spill pixels to include a patch.
                         0.0 = include all patches (background included for class balance).
    
    Returns:
        (image_patches, mask_patches) — lists of numpy arrays
    """
    H, W = image.shape[:2]
    image_patches = []
    mask_patches  = []

    for y in range(0, H - patch_size + 1, stride):
        for x in range(0, W - patch_size + 1, stride):
            img_patch  = image[y:y+patch_size, x:x+patch_size, :]
            mask_patch = mask[y:y+patch_size, x:x+patch_size]

            # Filter by spill content if requested
            spill_ratio = mask_patch.sum() / (patch_size * patch_size)
            if spill_ratio < min_spill_ratio:
                continue

            image_patches.append(img_patch)
            mask_patches.append(mask_patch)

    return image_patches, mask_patches


# ─── FULL PREPROCESSING PIPELINE ─────────────────────────────────────────────

def preprocess_single(image_path: Path,
                      mask_path: Path,
                      patch_size: int = 256,
                      stride: int = 192,
                      apply_speckle_filter: bool = True) -> Tuple[List[np.ndarray], List[np.ndarray]]:
    """
    Full preprocessing pipeline for one image-mask pair.
    
    Returns:
        (image_patches, mask_patches) lists ready for model input
    """
    # 1. Load
    image = load_sar_image(image_path)
    mask  = load_mask(mask_path)

    if image is None or mask is None:
        return [], []

    # 2. Lee Speckle Filter per band
    if apply_speckle_filter:
        for c in range(image.shape[2]):
            image[:, :, c] = lee_speckle_filter(image[:, :, c], window_size=7)

    # 3. Normalize each band to [0, 1]
    for c in range(image.shape[2]):
        image[:, :, c] = normalize_sar_band(image[:, :, c])

    # 4. Extract patches
    img_patches, msk_patches = extract_patches(
        image, mask,
        patch_size=patch_size,
        stride=stride
    )

    return img_patches, msk_patches


def preprocess_dataset(dataset_dir: Path,
                       output_dir: Path,
                       patch_size: int = 256,
                       stride: int = 192,
                       max_images: Optional[int] = None):
    """
    Preprocess an entire dataset split (spills/ or lookalikes/).
    Saves patches as .npy files for fast DataLoader access.
    
    Directory structure expected:
        dataset_dir/
          images/  *.tiff
          masks/   *.tiff
    
    Output structure:
        output_dir/
          patches/
            images/  0000_00.npy, 0000_01.npy, ...
            masks/   0000_00.npy, 0000_01.npy, ...
          stats.json
    """
    img_dir = dataset_dir / "images"
    msk_dir = dataset_dir / "masks"

    if not img_dir.exists():
        print(f"❌ Image directory not found: {img_dir}")
        return

    image_paths = sorted(list(img_dir.glob("*.tiff")) + list(img_dir.glob("*.tif")))
    if max_images:
        image_paths = image_paths[:max_images]

    # Output directories
    out_img_dir = output_dir / "patches" / "images"
    out_msk_dir = output_dir / "patches" / "masks"
    out_img_dir.mkdir(parents=True, exist_ok=True)
    out_msk_dir.mkdir(parents=True, exist_ok=True)

    total_patches  = 0
    total_spill_px = 0
    total_px       = 0
    stats_records  = []

    print(f"\n🔧 Preprocessing {len(image_paths)} images from {dataset_dir.name}...")
    print(f"   Patch size: {patch_size}×{patch_size}, Stride: {stride}")

    for img_idx, img_path in enumerate(tqdm(image_paths, desc="  Preprocessing")):
        msk_path = msk_dir / img_path.name

        if not msk_path.exists():
            # Try common name mismatches
            stem = img_path.stem
            for ext in [".tiff", ".tif"]:
                candidate = msk_dir / (stem + ext)
                if candidate.exists():
                    msk_path = candidate
                    break
            else:
                tqdm.write(f"⚠️  No mask for {img_path.name}, skipping.")
                continue

        img_patches, msk_patches = preprocess_single(
            img_path, msk_path,
            patch_size=patch_size,
            stride=stride
        )

        for patch_idx, (img_p, msk_p) in enumerate(zip(img_patches, msk_patches)):
            name = f"{img_idx:04d}_{patch_idx:04d}.npy"
            np.save(out_img_dir / name, img_p.astype(np.float32))
            np.save(out_msk_dir / name, msk_p.astype(np.uint8))

            total_spill_px += int(msk_p.sum())
            total_px       += patch_size * patch_size

        total_patches += len(img_patches)
        stats_records.append({
            "image": img_path.name,
            "patches": len(img_patches),
            "spill_ratio": float(sum(mp.mean() for mp in msk_patches) / max(len(msk_patches), 1))
        })

    # Class balance stats
    spill_ratio = total_spill_px / max(total_px, 1)
    stats = {
        "total_source_images": len(image_paths),
        "total_patches": total_patches,
        "patch_size": patch_size,
        "stride": stride,
        "class_imbalance_ratio": round(spill_ratio, 4),
        "pos_weight_for_bce": round((1 - spill_ratio) / max(spill_ratio, 1e-5), 2),
        "per_image": stats_records
    }

    stats_path = output_dir / "stats.json"
    with open(stats_path, "w") as f:
        json.dump(stats, f, indent=2)

    print(f"\n✅ Preprocessing complete:")
    print(f"   Total patches   : {total_patches}")
    print(f"   Spill pixel %   : {spill_ratio*100:.2f}%")
    print(f"   BCE pos_weight  : {stats['pos_weight_for_bce']}  (use in training)")
    print(f"   Stats saved     : {stats_path}")


# ─── STANDALONE USAGE ────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="OceanGuard SAR Preprocessor")
    parser.add_argument("--input",      required=True, help="Dataset directory (with images/ and masks/)")
    parser.add_argument("--output",     required=True, help="Output directory for patches")
    parser.add_argument("--patch-size", type=int, default=256)
    parser.add_argument("--stride",     type=int, default=192)
    parser.add_argument("--max",        type=int, default=None, help="Max images to process")
    args = parser.parse_args()

    preprocess_dataset(
        dataset_dir=Path(args.input),
        output_dir=Path(args.output),
        patch_size=args.patch_size,
        stride=args.stride,
        max_images=args.max
    )
