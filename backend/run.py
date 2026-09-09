"""
OceanGuard — Backend Entry Point
==================================
SIH PS 26143 | NTRO

Run this file from the /backend directory:
    python run.py

Or equivalently using uvicorn directly:
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
"""
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
