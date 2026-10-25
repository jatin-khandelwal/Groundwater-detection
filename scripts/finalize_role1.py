"""
finalize_role1.py   (Role 1: Data ka aakhri kaam, ek hi baar mein)

Chalane ka tareeka (C:\\Ground water se):
    python finalize_role1.py

Ye script:
  1. dataset_v2_neighbors.csv par saare data checks chalati hai ([OK] / [WARN])
  2. train / val / test ka SPLIT column lagati hai
  3. data/processed/dataset_v2.csv save karti hai
  4. data/processed/feature_groups.json (Model wale ke liye feature list) banati hai
  5. data/processed/data_dictionary_v2.csv banati hai
  6. handoff/ folder mein Backend aur Frontend ki files rakhti hai
  7. LIMITATIONS.md (report ke liye) likhti hai

Koi original file badalti nahi, sirf nayi files banati hai.
"""
from pathlib import Path
import json
import shutil

import numpy as np
import pandas as pd

# ------------------------- CONFIG -------------------------
PROC = Path("data/processed")
SRC = PROC / "dataset_v2_neighbors.csv"
HANDOFF = Path("handoff")

Y_MIN, Y_MAX = 2005, 2023        # modeling ka saal range (2024 adhoora hai)
TRAIN_END, VAL_YEAR = 2020, 2021  # train 2005-2020, val 2021, test 2022-2023
LAT_RANGE = (23.0, 30.5)         # Rajasthan ka lagbhag bounding box
LON_RANGE = (69.0, 78.5)
# ----------------------------------------------------------

results = []   # (status, message)


def check(ok: bool, msg: str, warn_only: bool = True) -> None:
    status = "OK" if ok else "WARN"
    results.append((status, msg))
    print(f"[{status}] {msg}")


# =========================================================
# 1) Load
# =========================================================
if not SRC.exists():
    raise SystemExit(f"File nahi mili: {SRC}  (C:\\Ground water se chalao)")

d = pd.read_csv(SRC, dtype={"SITE_ID": str}, low_memory=False)
d["DATE"] = pd.to_datetime(d["DATE"], errors="coerce")
d["OUTLIER"] = d["OUTLIER"].astype(str).str.lower().eq("true")
print(f"Loaded: {len(d)} rows, {d.shape[1]} columns, {d['SITE_ID'].nunique()} stations\n")

# =========================================================
# 2) Data checks
# =========================================================
print("---- DATA CHECKS ----")
check(d["DATE"].notna().all(), "DATE sab valid hain")
check(d.duplicated(["SITE_ID", "DATE"]).sum() == 0,
      f"SITE_ID + DATE duplicates: {int(d.duplicated(['SITE_ID', 'DATE']).sum())} (0 hone chahiye)")
check(d["WLS_WTR_LEVEL"].notna().all(),
      f"Target (WLS_WTR_LEVEL) missing: {int(d['WLS_WTR_LEVEL'].isna().sum())} (0 hone chahiye)")
inb = d["LAT"].between(*LAT_RANGE) & d["LON"].between(*LON_RANGE)
check(inb.all(), f"Rajasthan bounding box ke bahar ke rows: {int((~inb).sum())}")

x = d[d["YEAR"].between(Y_MIN, Y_MAX)]
rain_miss = x["rainfall_mm"].isna().mean() * 100
check(rain_miss < 1.0, f"rainfall_mm missing ({Y_MIN}-{Y_MAX}): {rain_miss:.2f}%")
if rain_miss >= 1.0:
    print("   saal ke hisaab se rainfall missing rows:")
    print(x[x["rainfall_mm"].isna()].groupby("YEAR").size().to_string())

# lag check: water_level_lag_1_obs_m pichhli reading hai ya nahi, aur time order
s = d.sort_values(["SITE_ID", "DATE"]).copy()
s["_prev"] = s.groupby("SITE_ID")["WLS_WTR_LEVEL"].shift(1)
both = s["water_level_lag_1_obs_m"].notna() & s["_prev"].notna()
mism = ((s.loc[both, "water_level_lag_1_obs_m"] - s.loc[both, "_prev"]).abs() > 1e-6).mean() * 100
check(mism < 1.0, f"lag_1 vs 'usi station ki pichhli reading' mismatch: {mism:.2f}% (kam hona chahiye)")
neg = int((d["days_since_previous_observation"] <= 0).sum())
check(neg == 0, f"days_since_previous_observation <= 0 wali rows: {neg} (0 hone chahiye, warna time order galat)")

# neighbor features ki consistency
nb_inconsistent = int(((d["neighbor_prev_level_count_5"] == 0) != d["neighbor_prev_level_mean_5_m"].isna()).sum())
check(nb_inconsistent == 0, f"neighbor count=0 aur mean missing ka mismatch: {nb_inconsistent} rows")
check((d["nearest_neighbor_prev_distance_km"].dropna() >= 0).all(), "neighbor distance negative nahi hai")

# elevation
st = d.drop_duplicates("SITE_ID")
print(f"\nElevation: min {st['elevation_m'].min():.0f} m, max {st['elevation_m'].max():.0f} m, "
      f"median {st['elevation_m'].median():.0f} m")
print("Sabse neeche ke 8 stations (map par ek baar dekh lo):")
print(st.nsmallest(8, "elevation_m")[["SITE_ID", "STATION_NAME", "DISTRICT_NAME", "LAT", "LON", "elevation_m"]]
      .to_string(index=False))

# year x round counts (modeling range)
counts = x.pivot_table(index="YEAR", columns="ROUND", values="SITE_ID", aggfunc="count", fill_value=0)
counts.to_csv(PROC / "quality_year_round_counts_v2.csv")
print("\nYear x round counts (2005-2023) save ho gaye: quality_year_round_counts_v2.csv")

# =========================================================
# 3) SPLIT column
# =========================================================
d["SPLIT"] = "unused"
ok = d["YEAR"].between(Y_MIN, Y_MAX) & ~d["OUTLIER"]
d.loc[ok & (d["YEAR"] <= TRAIN_END), "SPLIT"] = "train"
d.loc[ok & (d["YEAR"] == VAL_YEAR), "SPLIT"] = "val"
d.loc[ok & (d["YEAR"] > VAL_YEAR), "SPLIT"] = "test"

print("\n---- SPLIT ----")
for sp in ["train", "val", "test", "unused"]:
    part = d[d["SPLIT"] == sp]
    print(f"{sp:7s} rows: {len(part):6d}   stations: {part['SITE_ID'].nunique()}")
tr_sites = set(d.loc[d["SPLIT"] == "train", "SITE_ID"])
te_sites = set(d.loc[d["SPLIT"] == "test", "SITE_ID"])
print(f"Test ke stations jo train mein bhi hain: {len(te_sites & tr_sites)} / {len(te_sites)}")

# =========================================================
# 4) Feature groups (Model wale ke liye)
# =========================================================
groups = {
    "target": "WLS_WTR_LEVEL",
    "baseline": ["DISTRICT_NAME", "LAT", "LON", "YEAR", "month_sin", "month_cos"],
    "rainfall": ["rainfall_mm", "rainfall_lag_1m_mm", "rainfall_lag_3m_mm",
                 "rainfall_lag_12m_mm", "rainfall_normal_mm"],
    "elevation": ["elevation_m"],
    "well_aquifer": ["WELL_TYPE", "AQUIFER_TYPE"],
    "lag": ["water_level_lag_1_obs_m", "water_level_lag_2_obs_m",
            "water_level_prev3_obs_mean_m", "water_level_prev5_obs_mean_m",
            "days_since_previous_observation"],
    "neighbor": ["neighbor_prev_level_mean_5_m", "nearest_neighbor_prev_distance_km",
                 "neighbor_prev_level_count_5"],
    "stage_2023_snapshot": ["STAGE_EXTRACTION_PCT", "CATEGORY_CODE"],
    "never_use_as_features": ["WELL_DEPTH", "LEVEL_DIFF", "OUTLIER"],
    "ids_and_bookkeeping": ["SITE_ID", "STATION_NAME", "DATE", "MONTH", "STATE_NAME", "SOURCE_DS", "ROUND",
                            "BLOCK_NAME", "BLOCK_STATUS", "BASIN", "SUB_BASIN",
                            "rainfall_grid_lat", "rainfall_grid_lon", "valid_daily_records",
                            "elevation_source", "elevation_status", "rainfall_normal_grid_cells",
                            "ASSESSMENT_YEAR", "ASSESSMENT_DATE", "CATEGORY_CONFLICT",
                            "STAGE_MATCH_STATUS", "SPLIT"],
}
listed = {groups["target"]}
for k, v in groups.items():
    if isinstance(v, list):
        listed.update(v)
missing_cols = [c for c in listed if c not in d.columns]
unlisted = [c for c in d.columns if c not in listed]
check(not missing_cols, f"feature_groups ke columns jo dataset mein nahi hain: {missing_cols}")
if unlisted:
    print(f"   [INFO] Ye columns kisi group mein nahi hain: {unlisted}")
with open(PROC / "feature_groups.json", "w", encoding="utf-8") as f:
    json.dump(groups, f, indent=2)

# =========================================================
# 5) dataset_v2.csv aur data dictionary
# =========================================================
d_out = d.copy()
d_out["DATE"] = d_out["DATE"].dt.strftime("%Y-%m-%d")
d_out.to_csv(PROC / "dataset_v2.csv", index=False)

desc = {
    "SITE_ID": "Station ID (CGWB station code, ya A_<lat>_<lon> agar code nahi mila)",
    "DATE": "Reading ki date",
    "STATE_NAME": "State (sab Rajasthan)",
    "DISTRICT_NAME": "District",
    "STATION_NAME": "Station ka naam",
    "LAT": "Latitude (degrees)", "LON": "Longitude (degrees)",
    "BASIN": "River basin", "SUB_BASIN": "Sub basin",
    "WELL_TYPE": "Well ka type (e.g. dug well, tube well)",
    "AQUIFER_TYPE": "Aquifer ka type",
    "WELL_DEPTH": "Well ki gehrai (m). MODEL INPUT NAHI, sirf advisory ke liye",
    "WLS_WTR_LEVEL": "TARGET. Depth to water level (m below ground). Zyada = paani neeche",
    "LEVEL_DIFF": "Level mein badlav (A dataset). MODEL INPUT NAHI (target se bana hai)",
    "SOURCE_DS": "Data source (A ya B)",
    "YEAR": "Saal", "MONTH": "Mahina", "ROUND": "CGWB round (Jan/May/Aug/Nov/Other)",
    "OUTLIER": "True agar level <0 ya >300. Train/test se hataya gaya",
    "BLOCK_NAME": "Block (sirf verified mapping wale stations ka)",
    "BLOCK_STATUS": "Block mapping ka status",
    "rainfall_grid_lat": "Rainfall grid cell ka lat", "rainfall_grid_lon": "Rainfall grid cell ka lon",
    "rainfall_mm": "Us mahine ka rainfall (mm), NASA POWER",
    "valid_daily_records": "Us mahine mein kitne daily rainfall records valid the",
    "rainfall_lag_1m_mm": "Pichhle 1 mahine ka rainfall",
    "rainfall_lag_3m_mm": "Pichhle 3 mahine ka rainfall",
    "rainfall_lag_12m_mm": "Pichhle 12 mahine ka rainfall",
    "water_level_lag_1_obs_m": "Usi station ki pichhli reading ka level",
    "water_level_lag_2_obs_m": "Usi station ki us se pehli wali reading",
    "water_level_prev3_obs_mean_m": "Pichhli 3 readings ka average",
    "water_level_prev5_obs_mean_m": "Pichhli 5 readings ka average",
    "days_since_previous_observation": "Pichhli reading se kitne din ho gaye",
    "month_sin": "Mahine ka sin encoding", "month_cos": "Mahine ka cos encoding",
    "elevation_m": "Station ki elevation (m), SRTM30 (OpenTopoData)",
    "elevation_source": "Elevation ka source", "elevation_status": "Elevation lookup status",
    "rainfall_normal_mm": "District-month ka long-term normal rainfall",
    "rainfall_normal_grid_cells": "Normal nikalne mein kitne grid cells lage",
    "STAGE_EXTRACTION_PCT": "Block ka Stage of Extraction % (2023 snapshot)",
    "CATEGORY_CODE": "Block category (SA / SC / CR / OE ...)",
    "ASSESSMENT_YEAR": "Stage ka assessment year", "ASSESSMENT_DATE": "Stage ki assessment date",
    "CATEGORY_CONFLICT": "Category conflict ka flag",
    "STAGE_MATCH_STATUS": "Block-stage match ka status",
    "neighbor_prev_level_mean_5_m": "Aas-paas ke (5 tak) stations ka pichhla average level",
    "neighbor_prev_level_count_5": "Kitne neighbors us average mein aaye",
    "nearest_neighbor_prev_distance_km": "Sabse paas ke neighbor ki doori (km)",
    "SPLIT": "train (2005-2020) / val (2021) / test (2022-2023) / unused",
}
role_of = {}
for k, v in groups.items():
    if k == "target":
        role_of[v] = "target"
    elif isinstance(v, list):
        for c in v:
            role_of[c] = k
rows = []
for c in d.columns:
    ser = d[c]
    nn = ser.dropna()
    rows.append({
        "column": c,
        "role": role_of.get(c, "unlisted"),
        "dtype": str(ser.dtype),
        "missing_pct": round(ser.isna().mean() * 100, 1),
        "n_unique": int(ser.nunique()),
        "example": str(nn.iloc[0]) if len(nn) else "",
        "description": desc.get(c, ""),
    })
pd.DataFrame(rows).to_csv(PROC / "data_dictionary_v2.csv", index=False, encoding="utf-8-sig")

# =========================================================
# 6) Handoff folder (Backend + Frontend)
# =========================================================
be = HANDOFF / "backend"
fe = HANDOFF / "frontend"
be.mkdir(parents=True, exist_ok=True)
fe.mkdir(parents=True, exist_ok=True)

be_files = ["waterlevel_merged.csv", "station_master.csv", "station_block_map.csv",
            "rainfall_monthly.csv", "rainfall_normals.csv", "block_stage.csv",
            "station_elevation.csv", "dataset_v2.csv", "data_dictionary_v2.csv",
            "feature_groups.json"]
copied, not_found = [], []
for fn in be_files:
    p = PROC / fn
    if p.exists():
        shutil.copy2(p, be / fn)
        copied.append(fn)
    else:
        not_found.append(fn)

# Frontend: 20 sample stations + 3 stations ka history (mock data ke liye)
good = d[(d["SPLIT"] != "unused")]
latest = good.sort_values("DATE").groupby("SITE_ID").tail(1)
sample = latest.sample(n=min(20, len(latest)), random_state=7)[
    ["SITE_ID", "STATION_NAME", "DISTRICT_NAME", "BLOCK_NAME", "LAT", "LON",
     "WLS_WTR_LEVEL", "DATE", "CATEGORY_CODE"]].rename(columns={
        "WLS_WTR_LEVEL": "latest_level", "DATE": "latest_date", "CATEGORY_CODE": "stage_category_code"})
sample["latest_date"] = sample["latest_date"].dt.strftime("%Y-%m-%d")
sample.to_csv(fe / "sample_stations_20.csv", index=False)
hist_ids = sample["SITE_ID"].head(3).tolist()
hist = good[good["SITE_ID"].isin(hist_ids)].sort_values(["SITE_ID", "DATE"])[
    ["SITE_ID", "DATE", "WLS_WTR_LEVEL"]].copy()
hist["DATE"] = hist["DATE"].dt.strftime("%Y-%m-%d")
hist.to_csv(fe / "sample_history_3_stations.csv", index=False)

with open(HANDOFF / "README.txt", "w", encoding="utf-8") as f:
    f.write("Handoff folder (Role 1 se)\n\n")
    f.write("backend/  : Backend wale ko ye poora folder do (DB load ke liye)\n")
    f.write("frontend/ : Frontend wale ko ye folder do (mock data ke liye)\n\n")
    f.write("Units: WLS_WTR_LEVEL meter mein depth to water hai (zyada = paani neeche).\n")
    f.write("Modeling data: 2005-2023. WELL_DEPTH, LEVEL_DIFF model input nahi hain.\n")
    f.write("CATEGORY_CODE ke short codes (SA/SC/CR/OE) ka full naam Backend map karega.\n")
print(f"\nHandoff: backend/ mein {len(copied)} files, frontend/ mein 2 files")
if not_found:
    print(f"   [WARN] Ye files processed mein nahi mili: {not_found}")

# =========================================================
# 7) LIMITATIONS.md
# =========================================================
n_st = d["SITE_ID"].nunique()
block_cov = st["BLOCK_NAME"].notna().mean() * 100
stage_cov = st["STAGE_EXTRACTION_PCT"].notna().mean() * 100
years_present = set(d["YEAR"].unique())
missing_years = sorted(set(range(Y_MIN, Y_MAX + 1)) - years_present)
low = []
for yr in counts.index:
    for rd in ["Jan", "May", "Aug", "Nov"]:
        if rd in counts.columns and counts.loc[yr, rd] < 300:
            low.append(f"{yr} {rd} ({int(counts.loc[yr, rd])} readings)")
stage_years = sorted(d["ASSESSMENT_YEAR"].dropna().unique().astype(int).tolist())

lines = [
    "# Data limitations (auto-generated)\n",
    f"- Dataset: {len(d)} rows, {n_st} stations, {d['DISTRICT_NAME'].nunique()} districts. "
    f"Modeling window: {Y_MIN}-{Y_MAX}; 2024 is partial and not used for testing.",
    "- Measurements are seasonal (4 rounds per year: Jan, May, Aug, Nov), so this is a "
    "seasonal level prediction, not a daily forecast.",
    f"- Block mapping covers only {block_cov:.1f}% of stations; unverified blocks are left missing "
    "(not guessed from the nearest station).",
    f"- Stage of Extraction is available for {stage_cov:.1f}% of stations and comes from a single "
    f"assessment snapshot (assessment year(s): {stage_years}); applying it to earlier years is "
    "a limitation and is reported with and without the feature.",
    f"- Years with no data in the window: {missing_years if missing_years else 'none'}.",
    f"- Rounds with fewer than 300 readings: {', '.join(low) if low else 'none'}.",
    "- Rainfall is NASA POWER gridded data (0.5 degree), not station rainfall. District normals are "
    "simple averages of grid cells, not area-weighted.",
    "- Future rainfall is unknown; predictions use the district normal or a dry/wet scenario.",
    "- Elevation is SRTM30 via a public API at station coordinates; not individually field-verified.",
    "- Direct pumping/abstraction data is not available; Stage of Extraction is only a proxy.",
    "- WELL_DEPTH and LEVEL_DIFF are excluded from model inputs to avoid leakage.",
    "- Data source credit: India Data Portal (CGWB / India-WRIS data), Open Data Commons Attribution License.",
]
(PROC / "LIMITATIONS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

# =========================================================
# 8) Summary
# =========================================================
print("\n---- SUMMARY ----")
warns = [m for s_, m in results if s_ == "WARN"]
print(f"Checks: {len(results) - len(warns)} OK, {len(warns)} WARN")
for m in warns:
    print("  WARN:", m)
print("\nBani hui files:")
for fn in ["dataset_v2.csv", "feature_groups.json", "data_dictionary_v2.csv",
           "quality_year_round_counts_v2.csv", "LIMITATIONS.md"]:
    print("  data/processed/" + fn)
print("  handoff/backend/, handoff/frontend/, handoff/README.txt")
