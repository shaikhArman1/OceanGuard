"""
OceanGuard — RTX 3050 Optimized Training Script
================================================
SIH PS 26143 | NTRO

Trains the U-Net segmentation model on Sentinel-1 SAR data.

RTX 3050 Optimizations applied:
  ✅ Mixed Precision (AMP FP16)       → halves VRAM usage
  ✅ Gradient Accumulation (×4)       → effective batch 32, uses batch 8
  ✅ Gradient Checkpointing           → trades compute for VRAM
  ✅ torch.backends.cudnn.benchmark   → auto-tunes CUDA kernels
  ✅ pin_memory + num_workers=4       → eliminates data bottleneck
  ✅ OneCycleLR scheduler             → fast convergence
  ✅ Early stopping (patience=7)      → no wasted epochs

Expected Training Time on RTX 3050 (4GB):
  ~200 images → ~10,000 patches → 25 epochs ≈ 3–4 hours
  Final IoU target: > 0.70

Usage:
  python train.py                           # Default settings
  python train.py --epochs 30 --batch 8    # Custom
  python train.py --resume checkpoints/best_model.pth   # Resume
  python train.py --dry-run               # Validate setup only
"""

import os
import json
import time
import argparse
import warnings
from pathlib import Path
from datetime import datetime

warnings.filterwarnings("ignore", category=UserWarning)

import numpy as np
import torch
import torch.nn as nn
from torch.cuda.amp import GradScaler, autocast

try:
    from torch.utils.tensorboard import SummaryWriter
    HAS_TB = True
except ImportError:
    HAS_TB = False
    print("ℹ️  TensorBoard not available. Install 'tensorboard' for live loss plots.")

# Local imports — insert backend/ dir so 'from app.ml...' resolves correctly
import sys
sys.path.insert(0, str(Path(__file__).parent))   # backend/

from app.ml.unet_model  import OceanGuardUNet, get_smp_model, CombinedLoss, compute_iou, compute_f1, model_summary
from app.ml.dataset     import get_dataloaders, load_pos_weight


# ─── CONFIG ────────────────────────────────────────────────────────────────────

BASE_DIR   = Path(__file__).parent
DATA_DIR   = BASE_DIR / "app" / "data" / "dataset"
CKPT_DIR   = BASE_DIR / "models"
LOG_DIR    = BASE_DIR / "runs"

SPLIT_DIRS = {
    "spills":     DATA_DIR / "train" / "spills",
    "lookalikes": DATA_DIR / "train" / "lookalikes",
}

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


# ─── GPU DIAGNOSTICS ────────────────────────────────────────────────────────────

def print_gpu_info():
    if not torch.cuda.is_available():
        print("⚠️  CUDA not available! Training on CPU (will be very slow).")
        print("   → Check CUDA/cuDNN installation for RTX 3050.")
        return False

    gpu_name  = torch.cuda.get_device_name(0)
    total_mem = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
    free_mem  = (torch.cuda.get_device_properties(0).total_memory
                 - torch.cuda.memory_allocated(0)) / (1024 ** 3)

    print(f"\n🎮 GPU Detected: {gpu_name}")
    print(f"   Total VRAM : {total_mem:.1f} GB")
    print(f"   Free  VRAM : {free_mem:.1f} GB")

    if "3050" in gpu_name:
        print(f"   Config     : RTX 3050 profile — AMP FP16 enabled")

    return True


# ─── TRAINING LOOP ────────────────────────────────────────────────────────────

def train_one_epoch(model, loader, optimizer, criterion, scaler,
                    scheduler, accum_steps: int, epoch: int) -> dict:
    """
    Single training epoch with:
    - Mixed precision (autocast)
    - Gradient accumulation (accum_steps)
    - OneCycleLR step per batch
    """
    model.train()
    total_loss = 0.0
    total_iou  = 0.0
    total_f1   = 0.0
    n_batches  = len(loader)

    optimizer.zero_grad()

    for batch_idx, (images, masks) in enumerate(loader):
        images = images.to(DEVICE, non_blocking=True)
        masks  = masks.to(DEVICE, non_blocking=True)

        # Forward pass with AMP
        with autocast():
            logits = model(images)
            loss   = criterion(logits, masks)
            loss   = loss / accum_steps   # Scale for gradient accumulation

        # Backward with GradScaler
        scaler.scale(loss).backward()

        # Gradient accumulation: only step optimizer every N batches
        if (batch_idx + 1) % accum_steps == 0 or (batch_idx + 1) == n_batches:
            scaler.unscale_(optimizer)
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            scaler.step(optimizer)
            scaler.update()
            optimizer.zero_grad()

            if scheduler is not None:
                scheduler.step()

        # Metrics (no grad needed)
        with torch.no_grad():
            total_loss += loss.item() * accum_steps   # Undo scaling for logging
            total_iou  += compute_iou(logits.detach(), masks)
            total_f1   += compute_f1(logits.detach(), masks)

    return {
        "loss": total_loss / n_batches,
        "iou":  total_iou  / n_batches,
        "f1":   total_f1   / n_batches
    }


@torch.no_grad()
def validate(model, loader, criterion) -> dict:
    """Validation epoch — no gradient flow."""
    model.eval()
    total_loss = 0.0
    total_iou  = 0.0
    total_f1   = 0.0
    n_batches  = len(loader)

    for images, masks in loader:
        images = images.to(DEVICE, non_blocking=True)
        masks  = masks.to(DEVICE, non_blocking=True)

        with autocast():
            logits = model(images)
            loss   = criterion(logits, masks)

        total_loss += loss.item()
        total_iou  += compute_iou(logits, masks)
        total_f1   += compute_f1(logits, masks)

    return {
        "loss": total_loss / n_batches,
        "iou":  total_iou  / n_batches,
        "f1":   total_f1   / n_batches
    }


# ─── CHECKPOINT ────────────────────────────────────────────────────────────────

def save_checkpoint(model, optimizer, epoch, metrics, path: Path, is_best: bool = False):
    """Save model checkpoint with all state needed for resumption."""
    checkpoint = {
        "epoch":          epoch,
        "model_state":    model.state_dict(),
        "optimizer_state": optimizer.state_dict(),
        "metrics":        metrics,
        "timestamp":      datetime.now().isoformat()
    }
    torch.save(checkpoint, path)
    if is_best:
        best_path = path.parent / "best_model.pth"
        torch.save(checkpoint, best_path)
        print(f"   💾 New best model saved → {best_path} (IoU: {metrics['val_iou']:.4f})")


def load_checkpoint(model, optimizer, path: Path):
    """Load checkpoint and return starting epoch."""
    ckpt = torch.load(path, map_location=DEVICE)
    model.load_state_dict(ckpt["model_state"])
    optimizer.load_state_dict(ckpt["optimizer_state"])
    print(f"✅ Resumed from epoch {ckpt['epoch']} (IoU: {ckpt['metrics'].get('val_iou', 0):.4f})")
    return ckpt["epoch"] + 1


# ─── MAIN TRAINING FUNCTION ────────────────────────────────────────────────────

def train(args):
    print("\n" + "=" * 60)
    print("  OceanGuard — SAR Oil Spill Segmentation Training")
    print("  SIH PS 26143 | NTRO")
    print("=" * 60)

    has_gpu = print_gpu_info()

    # ── Model ──────────────────────────────────────────────────────────────────
    print("\n🏗️  Building model...")
    model = get_smp_model(
        encoder_name="efficientnet-b0",
        encoder_weights="imagenet" if not args.no_pretrain else None,
        in_channels=2
    )
    model = model.to(DEVICE)
    model_summary(model)

    # Gradient checkpointing to save VRAM (trade compute for memory)
    if args.grad_checkpoint and hasattr(model, "encoder"):
        try:
            model.encoder.set_grad_checkpointing(enable=True)
            print("   ✅ Gradient checkpointing enabled on encoder")
        except AttributeError:
            pass

    # ── Loss ───────────────────────────────────────────────────────────────────
    stats_path = DATA_DIR / "train" / "spills" / "stats.json"
    pos_weight = load_pos_weight(stats_path)
    criterion  = CombinedLoss(pos_weight=pos_weight, dice_weight=0.5).to(DEVICE)

    # ── Optimizer ──────────────────────────────────────────────────────────────
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=args.lr,
        weight_decay=1e-4
    )

    # ── Data ───────────────────────────────────────────────────────────────────
    print("\n📦 Loading dataset...")
    try:
        train_loader, val_loader = get_dataloaders(
            data_dirs=SPLIT_DIRS,
            batch_size=args.batch,
            num_workers=args.workers,
            pin_memory=has_gpu
        )
    except ValueError as e:
        print(f"\n❌ Dataset error: {e}")
        print("   Run first:")
        print("   1. python scripts/download_dataset.py")
        print("   2. python app/ml/sar_preprocessor.py --input ... --output ...")
        return

    if args.dry_run:
        print("\n✅ Dry run complete — setup is valid.")
        print("   Remove --dry-run to start actual training.")
        return

    # ── Scheduler ──────────────────────────────────────────────────────────────
    total_steps = len(train_loader) * args.epochs // args.grad_accum
    scheduler = torch.optim.lr_scheduler.OneCycleLR(
        optimizer,
        max_lr=args.lr * 10,
        total_steps=total_steps,
        pct_start=0.1,
        anneal_strategy="cos"
    )

    # ── AMP Scaler ─────────────────────────────────────────────────────────────
    scaler = GradScaler(enabled=has_gpu)

    # ── CUDA benchmark ─────────────────────────────────────────────────────────
    if has_gpu:
        torch.backends.cudnn.benchmark = True
        print("   ✅ cudnn.benchmark enabled (auto-tunes CUDA kernels)")

    # ── Dirs & Logging ─────────────────────────────────────────────────────────
    CKPT_DIR.mkdir(parents=True, exist_ok=True)
    run_name = datetime.now().strftime("%Y%m%d_%H%M%S")
    writer = None
    if HAS_TB:
        writer = SummaryWriter(LOG_DIR / run_name)
        print(f"   📊 TensorBoard: tensorboard --logdir {LOG_DIR}")

    # ── Resume ─────────────────────────────────────────────────────────────────
    start_epoch = 1
    if args.resume and Path(args.resume).exists():
        start_epoch = load_checkpoint(model, optimizer, Path(args.resume))

    # ── Training Loop ──────────────────────────────────────────────────────────
    print(f"\n🚀 Starting training: {args.epochs} epochs, batch={args.batch}, "
          f"accum={args.grad_accum} → effective batch={args.batch * args.grad_accum}")
    print(f"   Device  : {DEVICE}")
    print(f"   AMP FP16: {has_gpu}")
    print(f"   LR      : {args.lr}")
    print()

    best_iou       = 0.0
    patience_count = 0
    history        = []

    for epoch in range(start_epoch, args.epochs + 1):
        epoch_start = time.time()

        # Train
        train_metrics = train_one_epoch(
            model, train_loader, optimizer, criterion, scaler,
            scheduler, args.grad_accum, epoch
        )

        # Validate
        val_metrics = validate(model, val_loader, criterion)

        elapsed = time.time() - epoch_start

        # ── Logging ────────────────────────────────────────────────────────────
        combined = {
            "epoch":     epoch,
            "train_loss": round(train_metrics["loss"], 4),
            "train_iou":  round(train_metrics["iou"], 4),
            "train_f1":   round(train_metrics["f1"], 4),
            "val_loss":   round(val_metrics["loss"], 4),
            "val_iou":    round(val_metrics["iou"], 4),
            "val_f1":     round(val_metrics["f1"], 4),
            "lr":         round(optimizer.param_groups[0]["lr"], 7),
            "elapsed_s":  round(elapsed, 1)
        }
        history.append(combined)

        iou_flag = "🏆" if val_metrics["iou"] > best_iou else "  "
        print(
            f"Epoch {epoch:03d}/{args.epochs} | "
            f"Loss: {train_metrics['loss']:.4f}→{val_metrics['loss']:.4f} | "
            f"IoU: {train_metrics['iou']:.4f}→{val_metrics['iou']:.4f} {iou_flag}| "
            f"F1: {val_metrics['f1']:.4f} | "
            f"{elapsed:.0f}s"
        )

        if writer:
            for k, v in combined.items():
                if k not in ("epoch", "elapsed_s"):
                    writer.add_scalar(k, v, epoch)

        # ── Checkpoint ─────────────────────────────────────────────────────────
        is_best = val_metrics["iou"] > best_iou
        if is_best:
            best_iou       = val_metrics["iou"]
            patience_count = 0
        else:
            patience_count += 1

        if epoch % args.save_every == 0 or is_best:
            ckpt_path = CKPT_DIR / f"checkpoint_epoch{epoch:03d}.pth"
            save_checkpoint(model, optimizer, epoch, combined, ckpt_path, is_best)

        # ── Early Stopping ─────────────────────────────────────────────────────
        if patience_count >= args.patience:
            print(f"\n⏹  Early stopping — no IoU improvement for {args.patience} epochs.")
            break

        # ── VRAM Monitor ───────────────────────────────────────────────────────
        if has_gpu and epoch % 5 == 0:
            used  = torch.cuda.max_memory_allocated(0) / (1024 ** 3)
            total = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
            print(f"   🎮 VRAM: {used:.2f}/{total:.1f} GB used")
            torch.cuda.reset_peak_memory_stats()

    # ── Save History ───────────────────────────────────────────────────────────
    history_path = CKPT_DIR / "training_history.json"
    with open(history_path, "w") as f:
        json.dump(history, f, indent=2)

    if writer:
        writer.close()

    print(f"\n{'=' * 60}")
    print(f"  ✅ Training Complete!")
    print(f"  Best Val IoU : {best_iou:.4f}")
    print(f"  Checkpoints  : {CKPT_DIR}")
    print(f"  Best model   : {CKPT_DIR / 'best_model.pth'}")
    print(f"{'=' * 60}")
    print(f"\n  Next step: python app/ml/inference.py --model models/best_model.pth")


# ─── CLI ─────────────────────────────────────────────────────────────────────


def parse_args():
    parser = argparse.ArgumentParser(
        description="OceanGuard SAR Training (RTX 3050 optimized)"
    )
    parser.add_argument("--epochs",          type=int,   default=25,
                        help="Total training epochs (default: 25)")
    parser.add_argument("--batch",           type=int,   default=8,
                        help="Batch size per GPU step (default: 8 for RTX 3050)")
    parser.add_argument("--grad-accum",      type=int,   default=4,
                        help="Gradient accumulation steps (default: 4 → eff. batch 32)")
    parser.add_argument("--lr",              type=float, default=1e-4,
                        help="Base learning rate (default: 1e-4)")
    parser.add_argument("--workers",         type=int,   default=2,
                        help="DataLoader workers (default: 2 for Windows)")
    parser.add_argument("--patience",        type=int,   default=7,
                        help="Early stopping patience (default: 7 epochs)")
    parser.add_argument("--save-every",      type=int,   default=5,
                        help="Save checkpoint every N epochs (default: 5)")
    parser.add_argument("--resume",          type=str,   default=None,
                        help="Path to checkpoint to resume from")
    parser.add_argument("--no-pretrain",     action="store_true",
                        help="Train from scratch (skip ImageNet weights)")
    parser.add_argument("--grad-checkpoint", action="store_true", default=True,
                        help="Enable gradient checkpointing to save VRAM")
    parser.add_argument("--dry-run",         action="store_true",
                        help="Validate setup without training")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    train(args)
