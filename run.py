"""
IntelliSales -- Full Stack Local Launcher
Runs both the FastAPI backend and Vite frontend concurrently.
"""

import subprocess
import sys
import os
import signal
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

def main():
    print("=" * 60)
    print("  IntelliSales -- Privacy-First Retail Intelligence Platform")
    print("  Smart India Hackathon (SIH26179) • Qualcomm QCS6490 Ready")
    print("=" * 60)

    backend_cmd = [sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
    frontend_cmd = ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "3000"]
    frontend_dir = str(PROJECT_ROOT / "frontend")

    print("\n[1/2] Starting FastAPI Backend on http://localhost:8000 ...")
    backend_proc = subprocess.Popen(backend_cmd, cwd=str(PROJECT_ROOT))

    print("[2/2] Starting Vite Frontend Dashboard on http://localhost:3000 ...")
    frontend_proc = subprocess.Popen(frontend_cmd, cwd=frontend_dir, shell=True)

    print("\n✓ Both services started!")
    print("  • Dashboard: http://localhost:3000")
    print("  • REST API & Docs: http://localhost:8000/docs")
    print("  • WebSocket Live Hub: ws://localhost:8000/ws")
    print("\nPress Ctrl+C to terminate all services...\n")

    try:
        backend_proc.wait()
        frontend_proc.wait()
    except KeyboardInterrupt:
        print("\nStopping services...")
        backend_proc.terminate()
        frontend_proc.terminate()
        print("Done. Goodbye!")

if __name__ == "__main__":
    main()
