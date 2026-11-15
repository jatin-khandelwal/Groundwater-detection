from __future__ import annotations

import csv
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .config import CSV_PATHS, DATABASE_PATH


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS stations (
    site_id TEXT PRIMARY KEY,
    station_name TEXT,
    district_name TEXT NOT NULL,
    block_name TEXT,
    latitude REAL,
    longitude REAL,
    elevation_m REAL,
    well_depth_m REAL
);
CREATE INDEX IF NOT EXISTS idx_stations_district ON stations(district_name);
CREATE INDEX IF NOT EXISTS idx_stations_block ON stations(district_name, block_name);
CREATE TABLE IF NOT EXISTS readings (
    site_id TEXT NOT NULL,
    date TEXT NOT NULL,
    level_m REAL,
    year INTEGER,
    month INTEGER,
    PRIMARY KEY(site_id, date)
);
CREATE INDEX IF NOT EXISTS idx_readings_date ON readings(date);
CREATE TABLE IF NOT EXISTS rainfall_monthly (
    lat_grid REAL NOT NULL,
    lon_grid REAL NOT NULL,
    date TEXT NOT NULL,
    rainfall_mm REAL,
    PRIMARY KEY(lat_grid, lon_grid, date)
);
CREATE TABLE IF NOT EXISTS block_stats (
    district_name TEXT NOT NULL,
    block_name TEXT NOT NULL,
    stage_pct REAL,
    category_code TEXT,
    assessment_year INTEGER,
    assessment_date TEXT
);
CREATE INDEX IF NOT EXISTS idx_block_stats ON block_stats(district_name, block_name, assessment_year);
CREATE TABLE IF NOT EXISTS prediction_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    endpoint TEXT NOT NULL,
    request_json TEXT NOT NULL,
    response_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS geocode_cache (
    query TEXT PRIMARY KEY,
    results_json TEXT NOT NULL,
    cached_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS geocoder_state (
    key TEXT PRIMARY KEY,
    last_request_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS auth_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('user','admin')),
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS auth_sessions (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES auth_users(id) ON DELETE CASCADE,
    expires_at INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_user ON auth_sessions(user_id);
CREATE TABLE IF NOT EXISTS auth_login_attempts (
    email TEXT PRIMARY KEY COLLATE NOCASE,
    failed_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until INTEGER NOT NULL DEFAULT 0
);
"""


@contextmanager
def connect(db_path: Path = DATABASE_PATH) -> Iterator[sqlite3.Connection]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


def _rows(path: Path):
    if not path.is_file():
        raise FileNotFoundError(f"Required project data file not found: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        yield from csv.DictReader(handle)


def _float(value: str | None) -> float | None:
    if value is None or value.strip() in {"", "nan", "NaN", "None"}:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _int(value: str | None) -> int | None:
    number = _float(value)
    return int(number) if number is not None else None


def initialize_database(db_path: Path = DATABASE_PATH, csv_paths: dict[str, Path] | None = None) -> dict[str, int]:
    """Create/refresh the demo SQLite database from the repository's processed CSVs."""
    paths = csv_paths or CSV_PATHS
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=30)
    counts: dict[str, int] = {}
    try:
        conn.executescript(SCHEMA)
        conn.execute("BEGIN")
        for table in ("stations", "readings", "rainfall_monthly", "block_stats"):
            conn.execute(f"DELETE FROM {table}")

        # Merge station identity, block map, and elevation by SITE_ID.
        master = {}
        for row in _rows(paths["stations"]):
            sid = (row.get("SITE_ID") or "").strip()
            if sid:
                master[sid] = {
                    "site_id": sid,
                    "station_name": row.get("station_name") or None,
                    "district_name": (row.get("district_name") or "").strip(),
                    "block_name": None,
                    "latitude": _float(row.get("latitude")),
                    "longitude": _float(row.get("longitude")),
                    "elevation_m": None,
                    "well_depth_m": _float(row.get("WELL_DEPTH")),
                }
        for row in _rows(paths["station_blocks"]):
            sid = (row.get("SITE_ID") or "").strip()
            item = master.get(sid)
            block = (row.get("BLOCK_NAME") or "").strip()
            if item and block and (row.get("BLOCK_STATUS") or "").upper() != "UNMATCHED":
                item["block_name"] = block
        for row in _rows(paths["elevations"]):
            item = master.get((row.get("SITE_ID") or "").strip())
            if item:
                item["elevation_m"] = _float(row.get("elevation_m"))
                # Prefer the coordinates from the station elevation match when present.
                item["latitude"] = _float(row.get("latitude")) or item["latitude"]
                item["longitude"] = _float(row.get("longitude")) or item["longitude"]

        conn.executemany(
            "INSERT INTO stations VALUES (:site_id,:station_name,:district_name,:block_name,:latitude,:longitude,:elevation_m,:well_depth_m)",
            [row for row in master.values() if row["district_name"]],
        )
        counts["stations"] = conn.execute("SELECT COUNT(*) FROM stations").fetchone()[0]

        reading_rows = []
        for row in _rows(paths["readings"]):
            sid = (row.get("SITE_ID") or "").strip()
            date = (row.get("DATE") or "").strip()
            if not sid or not date:
                continue
            reading_rows.append((sid, date, _float(row.get("WLS_WTR_LEVEL")), _int(row.get("YEAR")), _int(row.get("MONTH"))))
            if len(reading_rows) >= 10000:
                conn.executemany("INSERT OR REPLACE INTO readings VALUES (?,?,?,?,?)", reading_rows)
                reading_rows.clear()
        if reading_rows:
            conn.executemany("INSERT OR REPLACE INTO readings VALUES (?,?,?,?,?)", reading_rows)
        counts["readings"] = conn.execute("SELECT COUNT(*) FROM readings").fetchone()[0]

        rainfall_rows = []
        for row in _rows(paths["rainfall"]):
            rainfall_rows.append((_float(row.get("lat_grid")), _float(row.get("lon_grid")), row.get("date"), _float(row.get("rainfall_mm"))))
            if len(rainfall_rows) >= 10000:
                conn.executemany("INSERT OR REPLACE INTO rainfall_monthly VALUES (?,?,?,?)", rainfall_rows)
                rainfall_rows.clear()
        if rainfall_rows:
            conn.executemany("INSERT OR REPLACE INTO rainfall_monthly VALUES (?,?,?,?)", rainfall_rows)
        counts["rainfall_monthly"] = conn.execute("SELECT COUNT(*) FROM rainfall_monthly").fetchone()[0]

        stage_rows = []
        for row in _rows(paths["block_stats"]):
            stage_rows.append((
                (row.get("DISTRICT_NAME") or "").strip(), (row.get("BLOCK_NAME") or "").strip(),
                _float(row.get("STAGE_EXTRACTION_PCT")), row.get("CATEGORY_CODE"),
                _int(row.get("ASSESSMENT_YEAR")), row.get("ASSESSMENT_DATE"),
            ))
        conn.executemany("INSERT INTO block_stats VALUES (?,?,?,?,?,?)", stage_rows)
        counts["block_stats"] = conn.execute("SELECT COUNT(*) FROM block_stats").fetchone()[0]
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return counts


def database_exists(db_path: Path = DATABASE_PATH) -> bool:
    if not db_path.is_file():
        return False
    try:
        with connect(db_path) as conn:
            return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='stations'").fetchone() is not None
    except sqlite3.Error:
        return False


def ensure_runtime_schema(db_path: Path = DATABASE_PATH) -> None:
    """Apply additive runtime tables without reloading or clearing project data."""
    with connect(db_path) as conn:
        conn.executescript(
            "CREATE TABLE IF NOT EXISTS geocode_cache ("
            "query TEXT PRIMARY KEY, results_json TEXT NOT NULL, "
            "cached_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);"
            "CREATE TABLE IF NOT EXISTS geocoder_state ("
            "key TEXT PRIMARY KEY, last_request_at REAL NOT NULL);"
            "CREATE TABLE IF NOT EXISTS auth_users ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT NOT NULL UNIQUE COLLATE NOCASE, "
            "password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('user','admin')), "
            "is_active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);"
            "CREATE TABLE IF NOT EXISTS auth_sessions ("
            "token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES auth_users(id) ON DELETE CASCADE, "
            "expires_at INTEGER NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);"
            "CREATE INDEX IF NOT EXISTS idx_auth_sessions_user ON auth_sessions(user_id);"
            "CREATE TABLE IF NOT EXISTS auth_login_attempts ("
            "email TEXT PRIMARY KEY COLLATE NOCASE, failed_attempts INTEGER NOT NULL DEFAULT 0, "
            "locked_until INTEGER NOT NULL DEFAULT 0);"
        )
