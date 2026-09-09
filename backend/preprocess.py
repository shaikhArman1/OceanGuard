"""
OceanGuard — Preprocessing Runner
===================================
Run this AFTER download_dataset.py to prepare the dataset for training.

Usage:
  python preprocess.py                    # Process all downloaded splits
  python preprocess.py --split spills     # Only process spills
  python preprocess.py --patch 256 --stride 192  # Custom patch config
"""
import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent))

from app.ml.sar_preprocessor import preprocess_dataset

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "app" / "data" / "dataset"

SPLITS = {
    "spills":     (DATA_DIR / "train" / "spills",     DATA_DIR / "train" / "spills"),
    "lookalikes": (DATA_DIR / "train" / "lookalikes",  DATA_DIR / "train" / "lookalikes"),
    "test":       (DATA_DIR / "test",                  DATA_DIR / "test"),
}


def main():
    parser = argparse.ArgumentParser(description="OceanGuard SAR Preprocessor Runner")
    parser.add_argument("--split",  type=str, default="all",
                        choices=["all", "spills", "lookalikes", "test"])
    parser.add_argument("--patch",  type=int, default=256, help="Patch size (default: 256)")
    parser.add_argument("--stride", type=int, default=192, help="Stride (default: 192)")
    parser.add_argument("--max",    type=int, default=None, help="Max images per split")
    args = parser.parse_args()

    print("\n" + "=" * 55)
    print("  OceanGuard — SAR Dataset Preprocessing")
    print("  SIH PS 26143 | NTRO")
    print("=" * 55)
    print(f"  Patch size : {args.patch}×{args.patch}")
    print(f"  Stride     : {args.stride}")
    print(f"  Overlap    : {args.patch - args.stride} px")
    print(f"  Per image  : ~{int((2048 / args.stride) ** 2)} patches")

    target_splits = SPLITS if args.split == "all" else {args.split: SPLITS[args.split]}

    for name, (src, out) in target_splits.items():
        if not src.exists():
            print(f"\n⚠️  [{name}] Source not found: {src}")
            print(f"   → Run: python scripts/download_dataset.py first")
            continue

        print(f"\n{'─'*50}")
        print(f"  Processing: {name.upper()}")
        print(f"  Source : {src}")
        print(f"  Output : {out}")
        print(f"{'─'*50}")

        preprocess_dataset(
            dataset_dir=src,
            output_dir=out,
            patch_size=args.patch,
            stride=args.stride,
            max_images=args.max
        )

    print("\n✅ Preprocessing complete. Ready for training.")
    print("   Next: python train.py --dry-run  (verify setup)")
    print("         python train.py            (start training)")


if __name__ == "__main__":
    main()
