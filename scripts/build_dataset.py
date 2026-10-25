"""Reproducible dataset builder for Demo 2 groundwater project.

Inputs (CSV files):
  waterlevel_merged.csv
  station_block_map.csv
  rainfall_monthly.csv

Outputs:
  dataset_v0.csv, dataset_v1.csv, dataset_v2.csv
  data_quality_report_v0.txt, dataset_v1_quality_report.txt,
  dataset_v2_quality_report.json, year_round_counts.csv, feature_spec_v2.md

Usage:
  python build_dataset.py --input-dir data/raw --processed-dir data/processed
or put all three input files in one directory and pass that directory to --input-dir.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import pandas as pd
import numpy as np

TARGET = "WLS_WTR_LEVEL"
KEYS = ["SITE_ID", "DATE"]


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Required input not found: {path}")
    return pd.read_csv(path, low_memory=False)


def normalize_site_id(s: pd.Series) -> pd.Series:
    # Preserve station identifiers as strings and remove accidental trailing .0.
    return s.astype("string").str.replace(r"\.0$", "", regex=True).str.strip()


def build(input_dir: Path, processed_dir: Path) -> None:
    processed_dir.mkdir(parents=True, exist_ok=True)
    raw = read_csv(input_dir / "waterlevel_merged.csv")
    block = read_csv(input_dir / "station_block_map.csv")
    rain = read_csv(input_dir / "rainfall_monthly.csv")

    required = {"SITE_ID", "DATE", "WLS_WTR_LEVEL", "LAT", "LON", "YEAR", "MONTH"}
    missing = required - set(raw.columns)
    if missing:
        raise ValueError(f"waterlevel_merged.csv missing columns: {sorted(missing)}")

    raw["SITE_ID"] = normalize_site_id(raw["SITE_ID"])
    raw["DATE"] = pd.to_datetime(raw["DATE"], errors="coerce")
    raw["YEAR"] = pd.to_numeric(raw["YEAR"], errors="coerce").astype("Int64")
    raw["MONTH"] = pd.to_numeric(raw["MONTH"], errors="coerce").astype("Int64")
    raw = raw.sort_values(["SITE_ID", "DATE", "ROUND"], kind="stable")

    # Dataset v0: standardized base, retain all source rows; never silently deduplicate.
    v0 = raw.copy()
    if v0.duplicated(KEYS, keep=False).any():
        dup_n = int(v0.duplicated(KEYS, keep=False).sum())
        raise ValueError(f"Found {dup_n} rows in repeated SITE_ID + DATE keys; resolve explicitly before build.")
    v0["DATE"] = v0["DATE"].dt.strftime("%Y-%m-%d")
    v0.to_csv(processed_dir / "dataset_v0.csv", index=False)

    # Attach station-to-block metadata. Mapping is one row per SITE_ID; unresolved stays missing.
    block["SITE_ID"] = normalize_site_id(block["SITE_ID"])
    block_cols = [c for c in ["SITE_ID", "BLOCK_NAME", "BLOCK_STATUS"] if c in block.columns]
    block_map = block[block_cols].drop_duplicates("SITE_ID", keep="first")
    v1 = raw.copy()
    v1 = v1.drop(columns=[c for c in ["BLOCK_NAME", "BLOCK_STATUS"] if c in v1.columns], errors="ignore")
    v1 = v1.merge(block_map, on="SITE_ID", how="left", validate="many_to_one")
    v1["BLOCK_STATUS"] = v1["BLOCK_STATUS"].fillna("UNMATCHED")

    # Match each station to its nearest 0.5-degree rainfall grid, then join by calendar month.
    rain_required = {"lat_grid", "lon_grid", "YEAR", "MONTH", "rainfall_mm"}
    missing = rain_required - set(rain.columns)
    if missing:
        raise ValueError(f"rainfall_monthly.csv missing columns: {sorted(missing)}")
    rain["YEAR"] = pd.to_numeric(rain["YEAR"], errors="coerce").astype("Int64")
    rain["MONTH"] = pd.to_numeric(rain["MONTH"], errors="coerce").astype("Int64")
    rain_key = ["lat_grid", "lon_grid", "YEAR", "MONTH"]
    if rain.duplicated(rain_key).any():
        raise ValueError("rainfall_monthly.csv has duplicate grid-month keys")
    v1["rainfall_grid_lat"] = (pd.to_numeric(v1["LAT"], errors="coerce") * 2).round() / 2
    v1["rainfall_grid_lon"] = (pd.to_numeric(v1["LON"], errors="coerce") * 2).round() / 2
    rain_join = rain.rename(columns={"lat_grid": "rainfall_grid_lat", "lon_grid": "rainfall_grid_lon"})
    keep = ["rainfall_grid_lat", "rainfall_grid_lon", "YEAR", "MONTH", "rainfall_mm"]
    if "valid_daily_records" in rain_join.columns:
        keep.append("valid_daily_records")
    v1 = v1.merge(rain_join[keep], on=["rainfall_grid_lat", "rainfall_grid_lon", "YEAR", "MONTH"], how="left", validate="many_to_one")
    v1["DATE"] = v1["DATE"].dt.strftime("%Y-%m-%d")
    v1.to_csv(processed_dir / "dataset_v1.csv", index=False)

    # Dataset v2: leakage-safe calendar rainfall lags and prior observations within station.
    v2 = v1.copy()
    v2["DATE"] = pd.to_datetime(v2["DATE"], errors="coerce")
    v2 = v2.sort_values(["SITE_ID", "DATE", "ROUND"], kind="stable")
    # For rainfall lags, derive from the station's grid-cell monthly series, not from observation rows.
    grid_month = rain.rename(columns={"lat_grid": "rainfall_grid_lat", "lon_grid": "rainfall_grid_lon"}).copy()
    grid_month = grid_month.sort_values(["rainfall_grid_lat", "rainfall_grid_lon", "YEAR", "MONTH"])
    grid_month["month_index"] = grid_month["YEAR"].astype(int) * 12 + grid_month["MONTH"].astype(int)
    lag_frames = []
    for lag in (1, 3, 12):
        part = grid_month[["rainfall_grid_lat", "rainfall_grid_lon", "month_index", "rainfall_mm"]].copy()
        part["month_index"] = part["month_index"] + lag
        part = part.rename(columns={"rainfall_mm": f"rainfall_lag_{lag}m_mm"})
        lag_frames.append(part)
    v2["month_index"] = pd.to_numeric(v2["YEAR"], errors="coerce") * 12 + pd.to_numeric(v2["MONTH"], errors="coerce")
    for lag, part in zip((1, 3, 12), lag_frames):
        v2 = v2.merge(part, on=["rainfall_grid_lat", "rainfall_grid_lon", "month_index"], how="left", validate="many_to_one")
    # Historical target features are shifted so the current row's target is never used.
    grouped = v2.groupby("SITE_ID", sort=False)[TARGET]
    v2["water_level_lag_1_obs_m"] = grouped.shift(1)
    v2["water_level_lag_2_obs_m"] = grouped.shift(2)
    v2["water_level_prev3_obs_mean_m"] = grouped.transform(lambda s: s.shift(1).rolling(3, min_periods=1).mean())
    v2["water_level_prev5_obs_mean_m"] = grouped.transform(lambda s: s.shift(1).rolling(5, min_periods=1).mean())
    prev_date = v2.groupby("SITE_ID", sort=False)["DATE"].shift(1)
    v2["days_since_previous_observation"] = (v2["DATE"] - prev_date).dt.days
    month = pd.to_numeric(v2["MONTH"], errors="coerce")
    v2["month_sin"] = np.sin(2 * np.pi * month / 12)
    v2["month_cos"] = np.cos(2 * np.pi * month / 12)
    v2["DATE"] = v2["DATE"].dt.strftime("%Y-%m-%d")
    v2 = v2.drop(columns=["month_index"], errors="ignore")
    v2.to_csv(processed_dir / "dataset_v2.csv", index=False)

    # Audits and reproducibility outputs.
    counts = v0.copy()
    counts["YEAR"] = pd.to_numeric(counts["YEAR"], errors="coerce")
    round_counts = counts.groupby(["YEAR", "ROUND"], dropna=False).size().rename("row_count").reset_index()
    round_counts.to_csv(processed_dir / "year_round_counts.csv", index=False)

    q0 = {
        "dataset": "dataset_v0.csv", "rows": int(len(v0)), "columns": int(len(v0.columns)),
        "unique_sites": int(v0["SITE_ID"].nunique()),
        "date_min": str(pd.to_datetime(v0["DATE"], errors="coerce").min().date()),
        "date_max": str(pd.to_datetime(v0["DATE"], errors="coerce").max().date()),
        "duplicate_site_date": int(v0.duplicated(KEYS).sum()),
        "missing_counts": {k: int(v0[k].isna().sum()) for k in v0.columns if v0[k].isna().any()}
    }
    (processed_dir / "data_quality_report_v0.txt").write_text(json.dumps(q0, indent=2), encoding="utf-8")
    q2 = {
        "dataset": "dataset_v2.csv", "rows": int(len(v2)), "columns": int(len(v2.columns)),
        "unique_sites": int(v2["SITE_ID"].nunique()),
        "date_min": str(pd.to_datetime(v2["DATE"], errors="coerce").min().date()),
        "date_max": str(pd.to_datetime(v2["DATE"], errors="coerce").max().date()),
        "duplicate_site_date": int(v2.duplicated(KEYS).sum()),
        "missing_counts": {k: int(v2[k].isna().sum()) for k in v2.columns if v2[k].isna().any()},
        "features_added": ["rainfall_lag_1m_mm", "rainfall_lag_3m_mm", "rainfall_lag_12m_mm", "water_level_lag_1_obs_m", "water_level_lag_2_obs_m", "water_level_prev3_obs_mean_m", "water_level_prev5_obs_mean_m", "days_since_previous_observation", "month_sin", "month_cos"],
        "limitations": ["Elevation, official stage of extraction, neighbor aggregates, and rainfall normals are not included unless their source files are added to this builder."]
    }
    (processed_dir / "dataset_v2_quality_report.json").write_text(json.dumps(q2, indent=2), encoding="utf-8")
    (processed_dir / "feature_spec_v2.md").write_text("""# Dataset v2 — Feature Specification\n\n## Target\n- `WLS_WTR_LEVEL`: groundwater depth-to-water in metres; higher means water is deeper.\n\n## Leakage exclusions\n- Never use current-row `WLS_WTR_LEVEL` as a predictor.\n- Never use `WELL_DEPTH` or `LEVEL_DIFF` as predictors.\n- Exclude `OUTLIER` and `SOURCE_DS` unless explicitly justified.\n\n## Added features\n- Calendar rainfall lags: `rainfall_lag_1m_mm`, `rainfall_lag_3m_mm`, `rainfall_lag_12m_mm`.\n- Prior same-station observations: `water_level_lag_1_obs_m`, `water_level_lag_2_obs_m`, `water_level_prev3_obs_mean_m`, `water_level_prev5_obs_mean_m`, `days_since_previous_observation`.\n- Seasonal encoding: `month_sin`, `month_cos`.\n\n`rainfall_mm` is current-month rainfall and is only appropriate when available at prediction time. Elevation, official stage, neighbor features, and district rainfall normals are not yet included.\n\n## Modeling protocol\nUse GroupKFold grouped by `SITE_ID` for station-generalization checks. Temporal split: train 2005–2020, validation 2021, test 2022–2023. Keep partial 2024 data out of test. Fit preprocessing within each training fold.\n""", encoding="utf-8")
    print(f"Built v0/v1/v2 in {processed_dir}")
    print(f"Rows: {len(v0):,}; sites: {v0['SITE_ID'].nunique():,}; duplicate SITE_ID+DATE: {v2.duplicated(KEYS).sum()}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path, required=True, help="Folder containing the three input CSVs")
    parser.add_argument("--processed-dir", type=Path, required=True, help="Output folder for processed datasets")
    args = parser.parse_args()
    build(args.input_dir, args.processed_dir)
