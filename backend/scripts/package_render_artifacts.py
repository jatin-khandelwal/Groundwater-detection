from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "tmp" / "render_artifacts.zip"
FILES = [
    "models/v2/model.pkl",
    "models/v2/feature_list.json",
    "models/v2/metrics.json",
    "models/v2/interval_table.json",
    "data/processed/station_master.csv",
    "data/processed/station_block_map.csv",
    "data/processed/station_elevation.csv",
    "data/processed/waterlevel_merged.csv",
    "data/processed/rainfall_monthly.csv",
    "data/processed/block_stage.csv",
]


def main() -> None:
    missing = [name for name in FILES if not (ROOT / name).is_file()]
    if missing:
        raise SystemExit("Required deployment files are missing:\n" + "\n".join(missing))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(OUTPUT, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name in FILES:
            archive.write(ROOT / name, name)
    digest = hashlib.sha256()
    with OUTPUT.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    print(f"Artifact: {OUTPUT}")
    print(f"Size: {OUTPUT.stat().st_size:,} bytes")
    print(f"SHA-256: {digest}")
    print("Contains model and clean source CSVs only; no SQLite database or account data.")


if __name__ == "__main__":
    main()
