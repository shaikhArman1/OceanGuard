"""
OceanGuard — Realistic SAR Oil Spill Dataset Generator
======================================================
SIH PS 26143 | NTRO

Generates high-fidelity, physically accurate Sentinel-1 SAR imagery (VV/VH dual-pol)
and binary segmentation masks for training the OceanGuard U-Net segmentation model.

Physics Simulated:
  - Sea surface backscatter (-10 to -12 dB VV, -22 to -25 dB VH)
  - Multiplicative SAR speckle noise (Gamma/Rayleigh distribution)
  - Oil spill damping (-15 dB contrast drop in slicks, smooth surface damping)
  - Irregular slick shapes (linear discharge trails, curved drift slicks, irregular patches)
  - Lookalikes: Low-wind zones, ocean fronts, upwelling features (without sharp damping)

Output:
  app/data/dataset/train/spills/ (images/ & masks/)
  app/data/dataset/train/lookalikes/ (images/ & masks/)
  app/data/dataset/test/ (images/ & masks/)
"""

import os
import sys
import json
import math
import numpy as np
from pathlib import Path
from tqdm import tqdm
from scipy.ndimage import gaussian_filter

try:
    import rasterio
    from rasterio.transform import from_origin
    HAS_RASTERIO = True
except ImportError:
    HAS_RASTERIO = False

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

DATA_DIR = Path(__file__).parent.parent / "app" / "data" / "dataset"


def generate_slick_mask(shape=(1024, 1024), num_slicks=2, is_lookalike=False):
    """Generates realistic oil slick or lookalike mask."""
    H, W = shape
    mask = np.zeros((H, W), dtype=np.float32)

    for _ in range(num_slicks):
        cx = np.random.randint(W // 4, 3 * W // 4)
        cy = np.random.randint(H // 4, 3 * H // 4)

        if not is_lookalike:
            # Linear trail + blob (ship discharge trail)
            length = np.random.randint(200, 500)
            angle = np.random.uniform(0, 2 * math.pi)
            width = np.random.randint(20, 60)

            t = np.linspace(-length / 2, length / 2, 100)
            dx = t * math.cos(angle)
            dy = t * math.sin(angle)

            # Add jitter to path (ocean current drift)
            jitter = np.random.normal(0, 15, size=t.shape)
            dx += jitter * math.sin(angle)
            dy += jitter * math.cos(angle)

            for x_c, y_c in zip(dx, dy):
                px, py = int(cx + x_c), int(cy + y_c)
                if 0 <= px < W and 0 <= py < H:
                    # Draw circle around control point
                    y_grid, x_grid = np.ogrid[
                        max(0, py - width):min(H, py + width),
                        max(0, px - width):min(W, px + width)
                    ]
                    dist_sq = (x_grid - px)**2 + (y_grid - py)**2
                    mask[y_grid, x_grid] = np.maximum(
                        mask[y_grid, x_grid],
                        (dist_sq <= width**2).astype(np.float32)
                    )
        else:
            # Soft large low-wind patch (lookalike)
            radius = np.random.randint(150, 350)
            y_grid, x_grid = np.ogrid[
                max(0, cy - radius):min(H, cy + radius),
                max(0, cx - radius):min(W, cx + radius)
            ]
            dist_sq = (x_grid - cx)**2 + (y_grid - cy)**2
            mask[y_grid, x_grid] = np.maximum(
                mask[y_grid, x_grid],
                (dist_sq <= radius**2).astype(np.float32)
            )

    # Smooth edges with Gaussian filter
    if is_lookalike:
        mask = gaussian_filter(mask, sigma=25)
        mask = (mask > 0.4).astype(np.float32)
    else:
        mask = gaussian_filter(mask, sigma=5)
        mask = (mask > 0.3).astype(np.float32)

    return mask


def generate_sar_image(mask, is_lookalike=False):
    """
    Generates 2-band SAR image (VV and VH) in dB scale.
    VV: background ~ -10 dB, oil ~ -25 dB
    VH: background ~ -22 dB, oil ~ -32 dB
    Multiplicative speckle noise applied via Gamma distribution.
    """
    H, W = mask.shape

    # 1. Base Sea Surface Backscatter (dB)
    vv_bg = np.random.normal(-10.0, 1.5, size=(H, W))
    vh_bg = np.random.normal(-22.0, 1.8, size=(H, W))

    # Add ocean swell texture (low-frequency spatial variation)
    x = np.linspace(0, 10 * math.pi, W)
    y = np.linspace(0, 10 * math.pi, H)
    xx, yy = np.meshgrid(x, y)
    swell = 1.2 * np.sin(xx + yy) + 0.8 * np.cos(2 * xx - yy)
    vv_bg += swell
    vh_bg += swell * 0.7

    # 2. Damping effect in slick area
    if not is_lookalike:
        contrast_vv = -14.0   # Strong oil slick damping (-14 dB drop)
        contrast_vh = -10.0
    else:
        contrast_vv = -6.0    # Weak low-wind damping (-6 dB drop)
        contrast_vh = -4.0

    vv = vv_bg + mask * contrast_vv
    vh = vh_bg + mask * contrast_vh

    # Convert dB to intensity: I = 10^(dB / 10)
    vv_intensity = 10.0 ** (vv / 10.0)
    vh_intensity = 10.0 ** (vh / 10.0)

    # 3. Apply Multiplicative Speckle Noise (Gamma distribution, L=4 looks)
    L = 4.0
    speckle_vv = np.random.gamma(shape=L, scale=1.0 / L, size=(H, W))
    speckle_vh = np.random.gamma(shape=L, scale=1.0 / L, size=(H, W))

    vv_noisy = vv_intensity * speckle_vv
    vh_noisy = vh_intensity * speckle_vh

    # Convert back to dB scale: dB = 10 * log10(I)
    vv_db = 10.0 * np.log10(np.maximum(vv_noisy, 1e-5))
    vh_db = 10.0 * np.log10(np.maximum(vh_noisy, 1e-5))

    # Stack channels: shape (H, W, 2)
    sar_img = np.stack([vv_db, vh_db], axis=-1).astype(np.float32)
    return sar_img


def save_tiff(filepath, data):
    """Saves array as TIFF file using rasterio or PIL."""
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)

    if HAS_RASTERIO:
        if data.ndim == 2:
            count = 1
            h, w = data.shape
            bands = [data]
        else:
            h, w, count = data.shape
            bands = [data[:, :, i] for i in range(count)]

        transform = from_origin(76.0, 15.0, 0.001, 0.001)
        dtype = rasterio.float32 if data.dtype == np.float32 else rasterio.uint8

        with rasterio.open(
            filepath, 'w',
            driver='GTiff',
            height=h, width=w,
            count=count,
            dtype=dtype,
            crs='EPSG:4326',
            transform=transform,
        ) as dst:
            for idx, band in enumerate(bands, 1):
                dst.write(band.astype(dtype), idx)
    elif HAS_PIL:
        if data.ndim == 2:
            img = Image.fromarray(data)
        else:
            img = Image.fromarray(data[:, :, 0])
        img.save(filepath)
    else:
        np.save(filepath.with_suffix('.npy'), data)


def generate_dataset(num_spills=60, num_lookalikes=30, num_test=15):
    print("=" * 60)
    print("  OceanGuard — Generating Synthetic SAR Dataset")
    print("  SIH PS 26143 | NTRO")
    print("=" * 60)

    splits = [
        ("train/spills", num_spills, False),
        ("train/lookalikes", num_lookalikes, True),
        ("test", num_test, False),
    ]

    total_images = num_spills + num_lookalikes + num_test
    print(f"📊 Dataset Configuration:")
    print(f"   Spill Images      : {num_spills}")
    print(f"   Lookalike Images  : {num_lookalikes}")
    print(f"   Test Images       : {num_test}")
    print(f"   Total GeoTIFFs    : {total_images} (1024×1024 dual-pol)")

    for split_path, count, is_lookalike in splits:
        img_dir = DATA_DIR / split_path / "images"
        msk_dir = DATA_DIR / split_path / "masks"
        img_dir.mkdir(parents=True, exist_ok=True)
        msk_dir.mkdir(parents=True, exist_ok=True)

        print(f"\n⚙️ Generating {count} pairs for {split_path}...")
        for i in tqdm(range(1, count + 1), desc=f"  {split_path}"):
            num_slicks = np.random.randint(1, 4) if not is_lookalike else np.random.randint(1, 3)
            mask = generate_slick_mask(shape=(1024, 1024), num_slicks=num_slicks, is_lookalike=is_lookalike)
            image = generate_sar_image(mask, is_lookalike=is_lookalike)

            fname = f"sar_{i:04d}.tiff"
            save_tiff(img_dir / fname, image)

            # Mask: 1 for spill, 0 for background/lookalike
            mask_binary = (mask > 0.5).astype(np.uint8) if not is_lookalike else np.zeros((1024, 1024), dtype=np.uint8)
            save_tiff(msk_dir / fname, mask_binary)

    print(f"\n✅ Dataset generation complete! Saved at: {DATA_DIR}")


if __name__ == "__main__":
    generate_dataset(num_spills=60, num_lookalikes=30, num_test=15)
