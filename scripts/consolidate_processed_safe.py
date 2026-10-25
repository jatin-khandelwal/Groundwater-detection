from __future__ import annotations

import argparse
import json
from pathlib import Path
import pandas as pd

KEYS = ["SITE_ID", "DATE"]
BASE_CANDIDATES = [
    "dataset_v2_neighbors.csv",
    "dataset_v2_stage_merged.csv",
    "dataset_v2_enriched.csv",
    "dataset_v2.csv",
    "dataset_v1.csv",
    "dataset_v0.csv",
]
# This script NEVER deletes source or intermediate files.
NEVER_TOUCH = {
    "waterlevel_merged.csv", "station_block_map.csv", "station_elevation.csv",
    "rainfall_monthly.csv", "rainfall_normals.csv", "block_stage.csv",
    "data_dictionary.csv", "year_round_counts.csv", "build_dataset.py",
}

def read_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={"SITE_ID": "string"}, low_memory=False)
    if "DATE" in df.columns:
        df["DATE"] = pd.to_datetime(df["DATE"], errors="coerce").dt.strftime("%Y-%m-%d")
    return df

def dup_count(df: pd.DataFrame) -> int:
    if not all(k in df.columns for k in KEYS):
        return -1
    return int(df.duplicated(KEYS).sum())

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Safely consolidate processed dataset versions. No files are deleted."
    )
    ap.add_argument("--input-dir", default="processed",
                    help="Folder with dataset_v*.csv; defaults to ./processed")
    ap.add_argument("--output", default="dataset_final_candidate.csv",
                    help="Output CSV name inside input folder")
    args = ap.parse_args()

    folder = Path(args.input_dir).expanduser()
    if not folder.is_dir():
        # Convenience: if the requested ./processed folder doesn't exist, use the current
        # directory only when it directly contains candidate datasets.
        cwd = Path.cwd()
        if any((cwd / name).is_file() for name in BASE_CANDIDATES):
            print(f"Folder '{folder}' not found; candidate CSVs are in current directory, using: {cwd}")
            folder = cwd
        else:
            raise SystemExit(
                f"Input folder not found: {folder.resolve()}\n"
                "Run `Get-ChildItem` to locate your CSVs, then pass their folder with --input-dir."
            )
    folder = folder.resolve()

    available = [folder / name for name in BASE_CANDIDATES if (folder / name).is_file()]
    if not available:
        raise SystemExit(
            f"No known dataset versions found in {folder}.\n"
            "Expected one of: " + ", ".join(BASE_CANDIDATES)
        )

    base_path = available[0]
    base = read_csv(base_path)
    if not all(k in base.columns for k in KEYS):
        raise SystemExit(f"STOP: {base_path.name} must contain SITE_ID and DATE.")
    if dup_count(base) != 0:
        raise SystemExit(
            f"STOP: {base_path.name} has {dup_count(base)} duplicate SITE_ID+DATE rows. "
            "No output or cleanup attempted."
        )

    audit = []
    conflicts = []
    for source_path in available[1:]:
        source = read_csv(source_path)
        if not all(k in source.columns for k in KEYS):
            audit.append({"source": source_path.name, "status": "skipped_missing_keys"})
            continue
        ndup = dup_count(source)
        if ndup != 0:
            audit.append({"source": source_path.name, "status": "skipped_duplicate_keys",
                          "duplicate_keys": ndup})
            continue

        # Only add genuinely absent columns. Preserve the preferred base's values.
        new_cols = [c for c in source.columns if c not in base.columns and c not in KEYS]
        shared = [c for c in source.columns if c in base.columns and c not in KEYS]
        conflicts_for_source = 0
        matched_rows = len(base.merge(source[KEYS].drop_duplicates(), on=KEYS, how="inner"))
        source_only_keys = len(source.merge(base[KEYS], on=KEYS, how="left", indicator=True)
                                .query("_merge == 'left_only'"))
        base_only_keys = len(base.merge(source[KEYS], on=KEYS, how="left", indicator=True)
                             .query("_merge == 'left_only'"))

        # Compare overlapping values without changing them; disagreements are audit flags.
        for col in shared:
            tmp = base[KEYS + [col]].merge(source[KEYS + [col]], on=KEYS, how="inner",
                                           suffixes=("_base", "_source"))
            a, b = tmp[f"{col}_base"], tmp[f"{col}_source"]
            both = a.notna() & b.notna()
            if both.any():
                unequal = a[both].astype(str).str.strip() != b[both].astype(str).str.strip()
                count = int(unequal.sum())
                if count:
                    conflicts.append({
                        "source": source_path.name, "column": col,
                        "conflicting_matched_rows": count
                    })
                    conflicts_for_source += count

        if new_cols:
            base = base.merge(source[KEYS + new_cols], on=KEYS, how="left", validate="one_to_one")

        audit.append({
            "source": source_path.name,
            "status": "merged_missing_columns" if new_cols else "audited_no_new_columns",
            "new_columns_added": new_cols,
            "matched_keys": int(matched_rows),
            "source_only_keys_not_added": int(source_only_keys),
            "base_only_keys": int(base_only_keys),
            "shared_value_conflicts": int(conflicts_for_source),
        })

    if "WLS_WTR_LEVEL" not in base.columns:
        raise SystemExit("STOP: WLS_WTR_LEVEL target column missing.")

    out_path = folder / args.output
    if out_path.resolve() in [p.resolve() for p in available]:
        raise SystemExit("STOP: output filename must not overwrite an input dataset.")
    base.to_csv(out_path, index=False)
    reread = read_csv(out_path)
    report = {
        "status": "candidate_only_not_model_certified",
        "final_candidate_file": out_path.name,
        "preferred_base": base_path.name,
        "input_folder": str(folder),
        "rows": int(len(reread)),
        "columns": int(len(reread.columns)),
        "unique_SITE_ID": int(reread["SITE_ID"].nunique(dropna=True)),
        "duplicate_SITE_ID_DATE_rows": dup_count(reread),
        "date_min": str(reread["DATE"].min()) if "DATE" in reread.columns else None,
        "date_max": str(reread["DATE"].max()) if "DATE" in reread.columns else None,
        "missing_target_rows": int(reread["WLS_WTR_LEVEL"].isna().sum()),
        "feature_leakage_warning": (
            "Exclude WLS_WTR_LEVEL (target), WELL_DEPTH and LEVEL_DIFF from predictors. "
            "Validate lag features using time-aware, leakage-safe splits."
        ),
        "merge_audit": audit,
        "shared_value_conflicts": conflicts,
        "files_deleted": [],
        "notes": [
            "This script only consolidates columns across dataset version CSVs keyed by SITE_ID+DATE.",
            "It does not merge standalone station/block/rainfall/elevation tables.",
            "It does not add source-only observation rows from lower-priority versions.",
            "Preferred base values win where shared columns disagree; review conflict report.",
            "No input files are deleted."
        ],
    }
    report_path = folder / "consolidation_quality_report.json"
    report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    print(f"Candidate dataset: {out_path}")
    print(f"Quality report:    {report_path}")
    print(f"Rows: {len(reread):,} | Columns: {len(reread.columns)} | Stations: {reread['SITE_ID'].nunique():,}")
    print(f"Duplicate SITE_ID+DATE rows: {dup_count(reread)}")
    print(f"Shared-value conflict entries: {len(conflicts)}")
    print("Safety: no files were deleted. Treat output as a candidate until audit is reviewed.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
