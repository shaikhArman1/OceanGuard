# OceanGuard — Windows ML Environment Setup
# ==========================================
# Run this ONCE from the /backend directory in PowerShell:
#   cd backend
#   .\setup_env.ps1
#
# Creates a Python virtual environment and installs all training dependencies.

Write-Host "`n============================================================" -ForegroundColor Cyan
Write-Host "  OceanGuard — ML Environment Setup (RTX 3050 / CUDA 12.1)" -ForegroundColor Cyan
Write-Host "  SIH PS 26143 | NTRO" -ForegroundColor Cyan
Write-Host "============================================================`n" -ForegroundColor Cyan

$BackendDir = $PSScriptRoot
$VenvDir    = Join-Path $BackendDir "venv"

# ── Step 1: Create virtual environment ─────────────────────────────────────────
Write-Host "Step 1/4: Creating virtual environment at .\venv ..." -ForegroundColor Yellow
if (Test-Path $VenvDir) {
    Write-Host "  ✅ venv already exists, skipping creation." -ForegroundColor Green
} else {
    python -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  ❌ Failed to create venv. Is Python 3.11 installed?" -ForegroundColor Red
        exit 1
    }
    Write-Host "  ✅ Virtual environment created." -ForegroundColor Green
}

$PipExe     = Join-Path $VenvDir "Scripts\pip.exe"
$PythonExe  = Join-Path $VenvDir "Scripts\python.exe"

# ── Step 2: Install PyTorch with CUDA 12.1 ─────────────────────────────────────
Write-Host "`nStep 2/4: Installing PyTorch 2.4 (CUDA 12.1) for RTX 3050 ..." -ForegroundColor Yellow
Write-Host "  This downloads ~2.4 GB. May take 5-15 minutes depending on your connection." -ForegroundColor Gray

& $PipExe install torch==2.4.0 torchvision==0.19.0 torchaudio==2.4.0 `
    --index-url https://download.pytorch.org/whl/cu121 `
    --quiet

if ($LASTEXITCODE -ne 0) {
    Write-Host "  ❌ PyTorch install failed." -ForegroundColor Red
    Write-Host "  → Try manually: .\venv\Scripts\pip install torch --index-url https://download.pytorch.org/whl/cu121" -ForegroundColor Red
    exit 1
}
Write-Host "  ✅ PyTorch + CUDA installed." -ForegroundColor Green

# ── Step 3: Install remaining requirements ─────────────────────────────────────
Write-Host "`nStep 3/4: Installing ML + API requirements from requirements.txt ..." -ForegroundColor Yellow
Write-Host "  This downloads ~500 MB of packages." -ForegroundColor Gray

& $PipExe install -r "$BackendDir\requirements.txt" --quiet

if ($LASTEXITCODE -ne 0) {
    Write-Host "  ❌ Requirements install failed. Check requirements.txt." -ForegroundColor Red
    exit 1
}
Write-Host "  ✅ All requirements installed." -ForegroundColor Green

# ── Step 4: Verify GPU detection ───────────────────────────────────────────────
Write-Host "`nStep 4/4: Verifying GPU detection ..." -ForegroundColor Yellow

$gpuCheck = & $PythonExe -c @"
import torch
print(f'PyTorch: {torch.__version__}')
print(f'CUDA available: {torch.cuda.is_available()}')
if torch.cuda.is_available():
    print(f'GPU: {torch.cuda.get_device_name(0)}')
    total = torch.cuda.get_device_properties(0).total_memory / 1024**3
    print(f'VRAM: {total:.1f} GB')
else:
    print('WARNING: CUDA not detected. Training will run on CPU (slow).')
    print('Ensure your NVIDIA drivers are up to date.')
"@

Write-Host $gpuCheck -ForegroundColor Cyan

Write-Host "`n============================================================" -ForegroundColor Green
Write-Host "  ✅ Environment setup complete!" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host "`n  NEXT STEPS (run all from the /backend directory):" -ForegroundColor White
Write-Host "`n  1. Activate environment:" -ForegroundColor White
Write-Host "     .\venv\Scripts\Activate.ps1" -ForegroundColor Yellow
Write-Host "`n  2. Download dataset (~3-4 GB):" -ForegroundColor White
Write-Host "     python scripts\download_dataset.py" -ForegroundColor Yellow
Write-Host "`n  3. Preprocess SAR images into patches:" -ForegroundColor White
Write-Host "     python preprocess.py" -ForegroundColor Yellow
Write-Host "`n  4. Verify training setup (no GPU needed):" -ForegroundColor White
Write-Host "     python train.py --dry-run" -ForegroundColor Yellow
Write-Host "`n  5. START TRAINING (~3-4 hours on RTX 3050):" -ForegroundColor White
Write-Host "     python train.py" -ForegroundColor Yellow
Write-Host "`n  6. Monitor live training curves:" -ForegroundColor White
Write-Host "     tensorboard --logdir runs" -ForegroundColor Yellow
Write-Host ""
