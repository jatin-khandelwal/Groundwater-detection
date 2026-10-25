
from pathlib import Path
import pandas as pd
import sys

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "processed"
OUTPUT = ROOT / "outputs"
REPORT = OUTPUT / "feature_input_diagnostics.txt"

FILES = [
    "waterlevel_merged.csv",
    "rainfall_monthly.csv",
    "rainfall_normals.csv",
    "block_stage.csv",
    "station_block_map.csv",
    "station_elevation.csv",
    "dataset_v2_neighbors.csv",
]

def section(title, lines):
    lines.append("\n" + "=" * 80)
    lines.append(title)
    lines.append("=" * 80)

def normalize_text(series):
    return (
        series.astype("string")
        .str.strip()
        .str.upper()
        .str.replace(r"\s+", " ", regex=True)
    )

def main():
    lines = []
    tables = {}

    section("PROJECT PATHS", lines)
    lines.append(f"Project: {ROOT}")
    lines.append(f"Processed data: {DATA}")
    lines.append(f"Existing builder: {(ROOT / 'scripts' / 'build_dataset.py').exists()}")

    # 1. Load all required inputs
    section("INPUT FILES AND SCHEMAS", lines)

    for name in FILES:
        path = DATA / name

        if not path.exists():
            lines.append(f"\nMISSING FILE: {name}")
            continue

        try:
            df = pd.read_csv(path, low_memory=False)
            tables[name] = df
            lines.append(f"\nFILE: {name}")
            lines.append(f"Rows: {len(df):,} | Columns: {len(df.columns)}")
            lines.append(f"Columns: {df.columns.tolist()}")
        except Exception as exc:
            lines.append(f"\nREAD ERROR: {name}: {exc}")

    # 2. Groundwater history and target
    section("GROUNDWATER DATA CHECKS", lines)
    water = tables.get("waterlevel_merged.csv")

    if water is not None:
        required = ["SITE_ID", "DATE", "WLS_WTR_LEVEL"]
        missing = [c for c in required if c not in water.columns]
        lines.append(f"Missing required columns: {missing}")

        if not missing:
            water["SITE_ID"] = water["SITE_ID"].astype("string").str.strip()
            water["DATE"] = pd.to_datetime(water["DATE"], errors="coerce")
            water["WLS_WTR_LEVEL"] = pd.to_numeric(
                water["WLS_WTR_LEVEL"], errors="coerce"
            )

            lines.append(f"Date range: {water['DATE'].min()} to {water['DATE'].max()}")
            lines.append(f"Unique stations: {water['SITE_ID'].nunique():,}")
            lines.append(f"Missing station IDs: {water['SITE_ID'].isna().sum():,}")
            lines.append(f"Invalid dates: {water['DATE'].isna().sum():,}")
            lines.append(f"Missing target values: {water['WLS_WTR_LEVEL'].isna().sum():,}")
            lines.append(
                "Duplicate station-date keys: "
                f"{water.duplicated(['SITE_ID', 'DATE']).sum():,}"
            )

            if "ROUND" in water.columns:
                lines.append("Round counts:")
                lines.append(water["ROUND"].value_counts(dropna=False).to_string())

            if "DISTRICT_NAME" in water.columns:
                lines.append("Top districts:")
                lines.append(
                    water["DISTRICT_NAME"].value_counts(dropna=False).head(20).to_string()
                )

    # 3. Rainfall data and rainfall normals
    section("RAINFALL CHECKS", lines)
    rain = tables.get("rainfall_monthly.csv")
    normals = tables.get("rainfall_normals.csv")

    if rain is not None:
        lines.append(f"Rainfall rows: {len(rain):,}")
        if "date" in rain.columns:
            rain["date"] = pd.to_datetime(rain["date"], errors="coerce")
            lines.append(f"Rainfall date range: {rain['date'].min()} to {rain['date'].max()}")

        for col in ["YEAR", "MONTH", "rainfall_mm", "valid_daily_records"]:
            if col in rain.columns:
                lines.append(f"{col} missing: {rain[col].isna().sum():,}")

        grid_keys = ["lat_grid", "lon_grid", "YEAR", "MONTH"]
        if all(c in rain.columns for c in grid_keys):
            lines.append(
                "Duplicate rainfall grid-month keys: "
                f"{rain.duplicated(grid_keys).sum():,}"
            )

    if normals is not None:
        lines.append(f"\nRainfall-normal rows: {len(normals):,}")
        if "district_name" in normals.columns:
            lines.append("Normal district names (first 30):")
            lines.append(
                str(normals["district_name"].dropna().astype(str).drop_duplicates().head(30).tolist())
            )
        if "MONTH" in normals.columns:
            lines.append("Normal month values:")
            lines.append(str(sorted(normals["MONTH"].dropna().unique().tolist())))
        if {"district_name", "MONTH"}.issubset(normals.columns):
            lines.append(
                "Duplicate district-month normal keys: "
                f"{normals.duplicated(['district_name', 'MONTH']).sum():,}"
            )

    # 4. Stage categories and join keys
    section("GROUNDWATER STAGE CHECKS", lines)
    stage = tables.get("block_stage.csv")
    mapping = tables.get("station_block_map.csv")

    if stage is not None:
        lines.append(f"Stage rows: {len(stage):,}")
        for col in ["DISTRICT_NAME", "BLOCK_NAME", "CATEGORY_CODE", "ASSESSMENT_YEAR"]:
            if col in stage.columns:
                lines.append(f"\n{col} values:")
                lines.append(stage[col].value_counts(dropna=False).head(40).to_string())

        if {"DISTRICT_NAME", "BLOCK_NAME"}.issubset(stage.columns):
            lines.append(
                "\nDuplicate stage district-block keys: "
                f"{stage.duplicated(['DISTRICT_NAME', 'BLOCK_NAME']).sum():,}"
            )

    if mapping is not None:
        lines.append(f"\nStation-block mapping rows: {len(mapping):,}")
        for col in ["BLOCK_STATUS", "BLOCK_NAME"]:
            if col in mapping.columns:
                lines.append(f"\nMapping {col} counts:")
                lines.append(mapping[col].value_counts(dropna=False).head(30).to_string())

        if "SITE_ID" in mapping.columns:
            lines.append(
                "Duplicate station IDs in mapping: "
                f"{mapping['SITE_ID'].duplicated().sum():,}"
            )

    # 5. Compare normalized district names without changing source files
    section("DISTRICT NAME MATCH CHECK", lines)

    if (
        water is not None
        and normals is not None
        and "DISTRICT_NAME" in water.columns
        and "district_name" in normals.columns
    ):
        water_districts = set(
            normalize_text(water["DISTRICT_NAME"]).dropna().unique()
        )
        normal_districts = set(
            normalize_text(normals["district_name"]).dropna().unique()
        )

        lines.append(f"Water-level districts: {len(water_districts)}")
        lines.append(f"Normal districts: {len(normal_districts)}")
        lines.append(f"Matching normalized district names: {len(water_districts & normal_districts)}")
        lines.append(f"Water districts without normal match: {len(water_districts - normal_districts)}")
        lines.append("Unmatched water-level district names:")
        lines.append(str(sorted(water_districts - normal_districts)[:100]))
        lines.append("Unmatched rainfall-normal district names:")
        lines.append(str(sorted(normal_districts - water_districts)[:100]))

    # 6. Existing engineered dataset
    section("EXISTING DATASET V2 FEATURES", lines)
    v2 = tables.get("dataset_v2_neighbors.csv")

    if v2 is not None:
        lines.append(f"Rows: {len(v2):,}")
        lines.append(f"Columns: {len(v2.columns)}")
        lines.append("Existing feature columns:")
        lines.append(str([
            c for c in v2.columns
            if any(term in c.lower() for term in [
                "rain", "lag", "prev", "neighbor", "stage",
                "category", "elevation", "month_sin", "month_cos"
            ])
        ]))

        for col in [
            "neighbor_prev_level_mean_5_m",
            "water_level_lag_1_obs_m",
            "water_level_lag_2_obs_m",
            "water_level_prev3_obs_mean_m",
            "water_level_prev5_obs_mean_m",
            "rainfall_lag_1m_mm",
            "rainfall_lag_3m_mm",
            "rainfall_lag_12m_mm",
            "STAGE_EXTRACTION_PCT",
            "CATEGORY_CODE",
        ]:
            if col in v2.columns:
                lines.append(
                    f"{col}: missing={v2[col].isna().sum():,} "
                    f"({v2[col].isna().mean() * 100:.2f}%)"
                )

        if {"SITE_ID", "DATE"}.issubset(v2.columns):
            lines.append(
                "Duplicate V2 station-date keys: "
                f"{v2.duplicated(['SITE_ID', 'DATE']).sum():,}"
            )

    # 7. Save report; do not modify datasets
    OUTPUT.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines), encoding="utf-8")

    print("\n".join(lines))
    print(f"\n\nREPORT SAVED: {REPORT}")
    print("\nDiagnostic complete. No source dataset was modified.")

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\nDIAGNOSTIC FAILED: {exc}")
        sys.exit(1)
