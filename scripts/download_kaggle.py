"""Download the Kaggle datasets listed in docs/DATA_CARD.md into data/raw/<slug>/.

Needs a Kaggle API token at ~/.kaggle/kaggle.json (or ~/.kaggle/access_token).
data/raw/ is git-ignored: we never redistribute the raw files, only derived
aggregate statistics (pricing percentiles) and a sample of titles.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATASETS = [
    "asaniczka/upwork-job-postings-dataset-2024-50k-records",
    "asaniczka/all-jobs-on-upwork-200k-plus",
    "ahmedmyalo/upwork-freelance-jobs-60k",
    "asaniczka/freelance-contracts-dataset-1-3-million-entries",
    "sarveshchhetri/freelancer-success-earnings-and-churn-prediction",
    "adityammantri/trial-1",
]


def main() -> int:
    ok = 0
    for ds in DATASETS:
        out = ROOT / "data" / "raw" / ds.split("/")[1]
        if out.exists() and any(out.iterdir()):
            print(f"[skip] {ds} already present")
            ok += 1
            continue
        out.mkdir(parents=True, exist_ok=True)
        print(f"[download] {ds}")
        r = subprocess.run([sys.executable, "-m", "kaggle", "datasets", "download", "-d", ds, "-p", str(out), "--unzip"])
        ok += r.returncode == 0
    print(f"{ok}/{len(DATASETS)} datasets available")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
