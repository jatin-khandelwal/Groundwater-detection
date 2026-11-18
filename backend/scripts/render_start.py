from __future__ import annotations

import hashlib
import os
import sys
import tempfile
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

from backend.app.config import DATABASE_PATH, PROJECT_ROOT
from backend.app.db import connect, database_exists, ensure_runtime_schema, initialize_database
from backend.app.services.auth_service import create_user


REQUIRED_FILES = {
    "models/v2/render_compact/preprocessor.joblib",
    "models/v2/render_compact/tree_offsets.npy",
    "models/v2/render_compact/children_left.npy",
    "models/v2/render_compact/children_right.npy",
    "models/v2/render_compact/feature.npy",
    "models/v2/render_compact/threshold.npy",
    "models/v2/render_compact/value.npy",
    "models/v2/render_compact/manifest.json",
    "models/v2/feature_list.json",
    "models/v2/metrics.json",
    "models/v2/interval_table.json",
    "data/processed/station_master.csv",
    "data/processed/station_block_map.csv",
    "data/processed/station_elevation.csv",
    "data/processed/waterlevel_merged.csv",
    "data/processed/rainfall_monthly.csv",
    "data/processed/block_stage.csv",
}


def download_artifact() -> None:
    url = os.environ.get("GW_ARTIFACT_URL", "").strip()
    expected = os.environ.get("GW_ARTIFACT_SHA256", "").strip().lower()
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc or not expected:
        raise SystemExit("Set HTTPS GW_ARTIFACT_URL and GW_ARTIFACT_SHA256 in Render environment variables.")

    digest = hashlib.sha256()
    with tempfile.NamedTemporaryFile(prefix="gw-artifacts-", suffix=".zip", delete=False) as handle:
        archive_path = Path(handle.name)
        try:
            with urllib.request.urlopen(url, timeout=90) as response:
                while chunk := response.read(1024 * 1024):
                    handle.write(chunk)
                    digest.update(chunk)
        except Exception:
            archive_path.unlink(missing_ok=True)
            raise
    try:
        if digest.hexdigest() != expected:
            raise SystemExit("Downloaded artifact SHA-256 does not match GW_ARTIFACT_SHA256.")
        with zipfile.ZipFile(archive_path) as archive:
            names = set(archive.namelist())
            if names != REQUIRED_FILES:
                raise SystemExit("Deployment archive file list does not match the required manifest.")
            if sum(info.file_size for info in archive.infolist()) > 600_000_000:
                raise SystemExit("Deployment archive expands beyond the allowed size.")
            for name in names:
                target = (PROJECT_ROOT / name).resolve()
                if not target.is_relative_to(PROJECT_ROOT):
                    raise SystemExit("Deployment archive contains an unsafe path.")
            archive.extractall(PROJECT_ROOT)
    finally:
        archive_path.unlink(missing_ok=True)


def bootstrap_admin() -> None:
    email = os.environ.get("GW_BOOTSTRAP_ADMIN_EMAIL", "").strip()
    password = os.environ.get("GW_BOOTSTRAP_ADMIN_PASSWORD", "")
    if not email or not password:
        raise SystemExit("Set GW_BOOTSTRAP_ADMIN_EMAIL and GW_BOOTSTRAP_ADMIN_PASSWORD in Render environment variables.")
    with connect(DATABASE_PATH) as conn:
        users = conn.execute("SELECT COUNT(*) FROM auth_users").fetchone()[0]
    if users == 0:
        create_user(DATABASE_PATH, email, password, "admin")


def main() -> None:
    download_artifact()
    if not database_exists(DATABASE_PATH):
        initialize_database(DATABASE_PATH)
    ensure_runtime_schema(DATABASE_PATH)
    bootstrap_admin()
    port = os.environ.get("PORT", "10000")
    os.execv(sys.executable, [sys.executable, "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", port])


if __name__ == "__main__":
    main()
