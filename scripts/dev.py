"""Run GigBid locally without Docker: GigSim + API (embedded worker, in-process MCP) + Vite dev server.
    python scripts/dev.py [--demo]     (Ctrl+C stops everything)
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    env = {**os.environ, "PYTHONPATH": str(ROOT), "GIGSIM_AUTOTICK_SECONDS": os.getenv("GIGSIM_AUTOTICK_SECONDS", "30")}
    if "--demo" in sys.argv:
        env.setdefault("REVIEWER_EMAIL", "reviewer@gigbid.local")
        env.setdefault("REVIEWER_PASSWORD", "change-me-locally")
    if not (ROOT / "data/processed/stream_jobs.jsonl").exists():
        subprocess.check_call([sys.executable, "scripts/prepare_data.py"], cwd=ROOT, env=env)
    procs = [
        subprocess.Popen([sys.executable, "-m", "uvicorn", "gigsim.app:app", "--port", "8100"], cwd=ROOT, env=env),
        subprocess.Popen([sys.executable, "-m", "uvicorn", "apps.api.main:app", "--port", "8000"], cwd=ROOT, env=env),
        subprocess.Popen("npm run dev", cwd=ROOT / "apps/web", env=env, shell=True),
    ]
    print("GigSim :8100 | API :8000 | web http://localhost:5173")
    try:
        while all(p.poll() is None for p in procs):
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        for p in procs:
            p.terminate()


if __name__ == "__main__":
    main()
