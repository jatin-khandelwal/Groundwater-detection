from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROCESSED = PROJECT_ROOT / "data" / "processed"
MODEL_DIR = PROJECT_ROOT / "models" / "v2"
BACKEND_DIR = PROJECT_ROOT / "backend"


def env_path(name: str, default: Path) -> Path:
    raw = os.getenv(name)
    return Path(raw).expanduser().resolve() if raw else default


DATABASE_PATH = env_path("GW_DATABASE_PATH", BACKEND_DIR / "data" / "groundwater.sqlite3")
MODEL_PATH = env_path("GW_MODEL_PATH", MODEL_DIR / "model.pkl")
FEATURE_LIST_PATH = env_path("GW_FEATURE_LIST_PATH", MODEL_DIR / "feature_list.json")
METRICS_PATH = env_path("GW_METRICS_PATH", MODEL_DIR / "metrics.json")
INTERVAL_PATH = env_path("GW_INTERVAL_PATH", MODEL_DIR / "interval_table.json")

CSV_PATHS = {
    "stations": PROCESSED / "station_master.csv",
    "station_blocks": PROCESSED / "station_block_map.csv",
    "elevations": PROCESSED / "station_elevation.csv",
    "readings": PROCESSED / "waterlevel_merged.csv",
    "rainfall": PROCESSED / "rainfall_monthly.csv",
    "block_stats": PROCESSED / "block_stage.csv",
}

ADVISORY_BUFFER_M = (
    float(os.environ["GW_ADVISORY_BUFFER_M"])
    if os.getenv("GW_ADVISORY_BUFFER_M")
    else None
)
AUTO_INIT_DB = os.getenv("GW_AUTO_INIT_DB", "1").strip().lower() not in {"0", "false", "no"}

CORS_ORIGINS = [
    value.strip()
    for value in os.getenv(
        "GW_CORS_ORIGINS",
        "http://localhost:8501,http://127.0.0.1:8501,http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if value.strip()
]

GEOCODER_URL = os.getenv("GW_GEOCODER_URL", "https://nominatim.openstreetmap.org/search")
GEOCODER_USER_AGENT = os.getenv(
    "GW_GEOCODER_USER_AGENT", "GroundwaterIntelligenceDemo/1.0 (academic local demo)"
)
