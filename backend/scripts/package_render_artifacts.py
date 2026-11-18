from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

from backend.scripts.export_render_model import OUTPUT as COMPACT_MODEL_DIR, export_model


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "tmp" / "render_artifacts.zip"
FILES = [
    ("tmp/render_compact/preprocessor.joblib", "models/v2/render_compact/preprocessor.joblib"),
    ("tmp/render_compact/tree_offsets.npy", "models/v2/render_compact/tree_offsets.npy"),
    ("tmp/render_compact/children_left.npy", "models/v2/render_compact/children_left.npy"),
    ("tmp/render_compact/children_right.npy", "models/v2/render_compact/children_right.npy"),
    ("tmp/render_compact/feature.npy", "models/v2/render_compact/feature.npy"),
    ("tmp/render_compact/threshold.npy", "models/v2/render_compact/threshold.npy"),
    ("tmp/render_compact/value.npy", "models/v2/render_compact/value.npy"),
    ("tmp/render_compact/manifest.json", "models/v2/render_compact/manifest.json"),
    ("models/v2/feature_list.json", "models/v2/feature_list.json"),
    ("models/v2/metrics.json", "models/v2/metrics.json"),
    ("models/v2/interval_table.json", "models/v2/interval_table.json"),
    ("data/processed/station_master.csv", "data/processed/station_master.csv"),
    ("data/processed/station_block_map.csv", "data/processed/station_block_map.csv"),
    ("data/processed/station_elevation.csv", "data/processed/station_elevation.csv"),
    ("data/processed/waterlevel_merged.csv", "data/processed/waterlevel_merged.csv"),
    ("data/processed/rainfall_monthly.csv", "data/processed/rainfall_monthly.csv"),
    ("data/processed/block_stage.csv", "data/processed/block_stage.csv"),
]


def main() -> None:
    export_model(output=COMPACT_MODEL_DIR)
    missing = [source for source, _ in FILES if not (ROOT / source).is_file()]
    if missing:
        raise SystemExit("Required deployment files are missing:\n" + "\n".join(missing))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(OUTPUT, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for source, archive_name in FILES:
            archive.write(ROOT / source, archive_name)
    digest = hashlib.sha256()
    with OUTPUT.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    print(f"Artifact: {OUTPUT}")
    print(f"Size: {OUTPUT.stat().st_size:,} bytes")
    print(f"SHA-256: {digest.hexdigest()}")
    print("Contains model and clean source CSVs only; no SQLite database or account data.")


if __name__ == "__main__":
    main()
