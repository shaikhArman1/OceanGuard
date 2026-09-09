"""
OceanGuard — Zenodo SAR Dataset Downloader
===========================================
SIH PS 26143 | NTRO | Oil Spill Detection

Downloads a STRATEGIC SUBSET (~200 image+mask pairs) from the
Zenodo Sentinel-1 SAR Oil Spill Dataset.

Datasets:
  Part I  (Oil Spills)  : https://zenodo.org/records/8346860
  Part II (Lookalikes)  : https://zenodo.org/records/8253899
  Part III (Test Set)   : https://zenodo.org/records/13761290

RTX 3050 Note:
  Full dataset = ~97 GB. We only need ~200 samples = ~4 GB.
  This downloader fetches the FIRST N files via Zenodo REST API.
  Training on 200 samples for 25 epochs ≈ 3-4 hours on RTX 3050.

Usage:
  python download_dataset.py                  # Downloads 200 spill + 100 lookalike
  python download_dataset.py --spills 100     # Custom count
  python download_dataset.py --dry-run        # Preview file list only (no download)
  python download_dataset.py --verify         # Check downloaded files integrity
"""

import os
import sys
import time
import json
import hashlib
import argparse
import requests
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

# ─── CONFIG ────────────────────────────────────────────────────────────────────

# Zenodo Record IDs
RECORD_IDS = {
    "spills":     "8346860",   # Part I  — Oil Spill images + masks
    "lookalikes": "8253899",   # Part II — Lookalike images + masks (same format)
    "test":       "13761290",  # Part III — Test set
}

# Download root
DATA_DIR = Path(__file__).parent.parent / "app" / "data" / "dataset"

SPLIT_DIRS = {
    "spills":     DATA_DIR / "train" / "spills",
    "lookalikes": DATA_DIR / "train" / "lookalikes",
    "test":       DATA_DIR / "test",
}

ZENODO_API = "https://zenodo.org/api/records/{record_id}"

# ─── ZENODO API ────────────────────────────────────────────────────────────────

def get_record_files(record_id: str) -> list[dict]:
    """Fetch file metadata for a Zenodo record via REST API."""
    url = ZENODO_API.format(record_id=record_id)
    print(f"\n🔍 Fetching file list from Zenodo record {record_id}...")

    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"❌ Failed to fetch record metadata: {e}")
        print("   → Check your internet connection and try again.")
        sys.exit(1)

    data = resp.json()
    files = data.get("files", [])

    if not files:
        print(f"❌ No files found in record {record_id}. Record may have moved.")
        sys.exit(1)

    print(f"✅ Found {len(files)} files in record {record_id}")
    for f in files[:5]:
        size_mb = f.get("size", 0) / (1024 * 1024)
        print(f"   • {f.get('key', 'unknown')} ({size_mb:.1f} MB)")
    if len(files) > 5:
        print(f"   ... and {len(files) - 5} more")

    return files


def filter_and_pair_files(files: list[dict], max_pairs: int) -> list[tuple[dict, dict]]:
    """
    Pair image files with their corresponding mask files.
    Zenodo dataset structure:
      images/0001.tiff  →  masks/0001.tiff
      images/0002.tiff  →  masks/0002.tiff
      ...etc
    Returns list of (image_file_info, mask_file_info) tuples.
    """
    image_files = {
        f["key"].split("/")[-1].split(".")[0]: f
        for f in files
        if "/images/" in f.get("key", "") or f.get("key", "").startswith("images/")
    }
    mask_files = {
        f["key"].split("/")[-1].split(".")[0]: f
        for f in files
        if "/masks/" in f.get("key", "") or f.get("key", "").startswith("masks/")
    }

    # If no folder structure found, try even/odd split or name-based pairing
    if not image_files or not mask_files:
        print("⚠️  Couldn't detect image/mask folder structure.")
        print("   → Treating all TIFF files as a flat list and pairing by index.")
        tiff_files = [f for f in files if f.get("key", "").endswith((".tiff", ".tif"))]
        mid = len(tiff_files) // 2
        pairs = list(zip(tiff_files[:mid], tiff_files[mid:]))[:max_pairs]
        return pairs

    # Match by file ID
    common_ids = sorted(set(image_files.keys()) & set(mask_files.keys()))
    print(f"\n📦 Found {len(common_ids)} image-mask pairs.")

    pairs = [
        (image_files[fid], mask_files[fid])
        for fid in common_ids[:max_pairs]
    ]
    return pairs


# ─── DOWNLOAD ENGINE ────────────────────────────────────────────────────────────

def download_file(url: str, dest_path: Path, file_size: int, retries: int = 3) -> bool:
    """
    Download a single file with progress bar, resume support, and retry logic.
    """
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    # Resume: check if partially downloaded
    headers = {}
    existing_size = 0
    if dest_path.exists():
        existing_size = dest_path.stat().st_size
        if existing_size == file_size:
            return True  # Already complete
        elif existing_size > 0:
            headers["Range"] = f"bytes={existing_size}-"

    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=headers, stream=True, timeout=60)
            resp.raise_for_status()

            mode = "ab" if existing_size > 0 else "wb"
            total = file_size - existing_size if existing_size > 0 else file_size

            with open(dest_path, mode) as f:
                with tqdm(
                    total=total,
                    unit="B",
                    unit_scale=True,
                    desc=f"  {dest_path.name}",
                    leave=False,
                    dynamic_ncols=True
                ) as pbar:
                    for chunk in resp.iter_content(chunk_size=65536):
                        if chunk:
                            f.write(chunk)
                            pbar.update(len(chunk))
            return True

        except (requests.RequestException, IOError) as e:
            if attempt < retries - 1:
                wait = 2 ** attempt
                print(f"   ⚠️  Attempt {attempt + 1} failed: {e}. Retrying in {wait}s...")
                time.sleep(wait)
            else:
                print(f"   ❌ All {retries} attempts failed for {dest_path.name}")
                return False

    return False


def download_pair(pair: tuple, dest_dir: Path, pair_idx: int) -> dict:
    """Download a single (image, mask) pair."""
    img_info, mask_info = pair
    results = {"success": True, "image": None, "mask": None}

    for file_info, subfolder in [(img_info, "images"), (mask_info, "masks")]:
        filename = file_info.get("key", "").split("/")[-1]
        if not filename.endswith((".tiff", ".tif")):
            filename = f"{pair_idx:04d}.tiff"

        dest_path = dest_dir / subfolder / filename
        download_url = file_info.get("links", {}).get("self", "")

        if not download_url:
            # Fallback: construct download URL
            record_id = file_info.get("record_id", "")
            download_url = f"https://zenodo.org/records/{record_id}/files/{file_info.get('key', '')}"

        success = download_file(download_url, dest_path, file_info.get("size", 0))
        results["success"] = results["success"] and success

        if subfolder == "images":
            results["image"] = str(dest_path) if success else None
        else:
            results["mask"] = str(dest_path) if success else None

    return results


# ─── VERIFY ────────────────────────────────────────────────────────────────────

def verify_dataset(data_dir: Path):
    """Verify downloaded dataset: check file count, sizes, and basic TIFF validity."""
    print("\n🔍 Verifying downloaded dataset...\n")

    total_ok = 0
    total_bad = 0

    for split_name, split_dir in SPLIT_DIRS.items():
        img_dir = split_dir / "images"
        msk_dir = split_dir / "masks"

        if not img_dir.exists():
            continue

        images = sorted(img_dir.glob("*.tiff")) + sorted(img_dir.glob("*.tif"))
        masks  = sorted(msk_dir.glob("*.tiff")) + sorted(msk_dir.glob("*.tif"))

        print(f"  [{split_name}]")
        print(f"    Images: {len(images)}")
        print(f"    Masks:  {len(masks)}")

        # Check pairing
        img_stems = {p.stem for p in images}
        msk_stems = {p.stem for p in masks}
        missing_masks  = img_stems - msk_stems
        missing_images = msk_stems - img_stems

        if missing_masks:
            print(f"    ⚠️  {len(missing_masks)} images have no mask: {list(missing_masks)[:5]}")
            total_bad += len(missing_masks)
        if missing_images:
            print(f"    ⚠️  {len(missing_images)} masks have no image")
            total_bad += len(missing_images)

        # Check file sizes (a valid TIFF should be > 1 MB)
        tiny = [p.name for p in images if p.stat().st_size < 1024 * 1024]
        if tiny:
            print(f"    ⚠️  {len(tiny)} suspiciously small image files: {tiny[:3]}")
            total_bad += len(tiny)
        else:
            total_ok += len(images)

        # Total size
        total_mb = sum(p.stat().st_size for p in images + masks) / (1024 * 1024)
        print(f"    Total: {total_mb:.0f} MB\n")

    print(f"✅ Verified: {total_ok} OK, {total_bad} issues")


# ─── DOWNLOAD MANIFEST ────────────────────────────────────────────────────────

def save_manifest(results: list, dest_dir: Path):
    """Save download manifest JSON for reproducibility."""
    manifest = {
        "download_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_pairs": len(results),
        "successful": sum(1 for r in results if r.get("success")),
        "files": results
    }
    manifest_path = dest_dir / "download_manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"\n📋 Manifest saved: {manifest_path}")


# ─── MAIN ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="OceanGuard — Zenodo SAR Dataset Downloader (SIH PS 26143)"
    )
    parser.add_argument("--spills",     type=int, default=150,
                        help="Number of oil spill image pairs to download (default: 150)")
    parser.add_argument("--lookalikes", type=int, default=80,
                        help="Number of lookalike pairs to download (default: 80)")
    parser.add_argument("--test",       type=int, default=30,
                        help="Number of test pairs to download (default: 30)")
    parser.add_argument("--workers",    type=int, default=2,
                        help="Parallel download workers (default: 2, max: 4)")
    parser.add_argument("--dry-run",    action="store_true",
                        help="List files without downloading")
    parser.add_argument("--verify",     action="store_true",
                        help="Verify already-downloaded dataset integrity")
    parser.add_argument("--output",     type=str, default=None,
                        help="Override output directory")
    args = parser.parse_args()

    if args.output:
        global DATA_DIR, SPLIT_DIRS
        DATA_DIR = Path(args.output)
        SPLIT_DIRS = {
            "spills":     DATA_DIR / "train" / "spills",
            "lookalikes": DATA_DIR / "train" / "lookalikes",
            "test":       DATA_DIR / "test",
        }

    print("=" * 60)
    print("  OceanGuard — SAR Dataset Downloader")
    print("  SIH PS 26143 | NTRO | Oil Spill Intelligence")
    print("=" * 60)

    if args.verify:
        verify_dataset(DATA_DIR)
        return

    # Estimate download size
    # ~16 MB per image TIFF (2048×2048×2 float32) + ~4 MB mask
    total_pairs = args.spills + args.lookalikes + args.test
    estimated_mb = total_pairs * 20
    print(f"\n📊 Download Plan:")
    print(f"   Oil Spill pairs  : {args.spills}")
    print(f"   Lookalike pairs  : {args.lookalikes}")
    print(f"   Test pairs       : {args.test}")
    print(f"   Total pairs      : {total_pairs}")
    print(f"   Estimated size   : ~{estimated_mb / 1024:.1f} GB")
    print(f"   Output directory : {DATA_DIR}")

    if args.dry_run:
        print("\n\n⚠️  DRY RUN — No files will be downloaded.")

    # Download each split
    download_targets = [
        ("spills",     RECORD_IDS["spills"],     args.spills,     SPLIT_DIRS["spills"]),
        ("lookalikes", RECORD_IDS["lookalikes"],  args.lookalikes, SPLIT_DIRS["lookalikes"]),
        ("test",       RECORD_IDS["test"],        args.test,       SPLIT_DIRS["test"]),
    ]

    all_results = []
    for split_name, record_id, max_pairs, dest_dir in download_targets:
        print(f"\n{'─' * 50}")
        print(f"  Downloading: {split_name.upper()} ({max_pairs} pairs)")
        print(f"{'─' * 50}")

        # Get file list
        files = get_record_files(record_id)
        pairs = filter_and_pair_files(files, max_pairs)

        if not pairs:
            print(f"⚠️  No pairs found for {split_name}, skipping.")
            continue

        print(f"📥 Will download {len(pairs)} pairs from {split_name}...")

        if args.dry_run:
            for i, (img, msk) in enumerate(pairs[:5]):
                size_mb = (img.get("size", 0) + msk.get("size", 0)) / (1024 * 1024)
                print(f"   [{i+1:03d}] {img.get('key', 'unknown')} ({size_mb:.1f} MB)")
            if len(pairs) > 5:
                print(f"   ...and {len(pairs) - 5} more pairs")
            continue

        # Create output directories
        dest_dir.mkdir(parents=True, exist_ok=True)
        (dest_dir / "images").mkdir(exist_ok=True)
        (dest_dir / "masks").mkdir(exist_ok=True)

        # Download with thread pool
        workers = min(args.workers, 4)
        split_results = []

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(download_pair, pair, dest_dir, i): i
                for i, pair in enumerate(pairs)
            }

            with tqdm(total=len(pairs), desc=f"  {split_name}", unit="pair") as pbar:
                for future in as_completed(futures):
                    result = future.result()
                    split_results.append(result)
                    pbar.update(1)
                    if not result.get("success"):
                        pbar.set_postfix({"failed": pbar.n})

        successful = sum(1 for r in split_results if r.get("success"))
        print(f"✅ {split_name}: {successful}/{len(pairs)} pairs downloaded successfully")
        all_results.extend(split_results)

    if not args.dry_run and all_results:
        save_manifest(all_results, DATA_DIR)
        verify_dataset(DATA_DIR)
        print(f"\n🎉 Dataset ready at: {DATA_DIR}")
        print(f"   Next: python preprocess.py  (patches + augmentation)")


if __name__ == "__main__":
    main()
