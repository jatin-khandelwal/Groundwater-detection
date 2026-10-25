"""
build_waterlevel.py

Dataset A (state/district wala) + Dataset B (India Data Portal 'manual' CSV/Excel)
ko jodkar ek saaf Rajasthan water-level table banata hai.

Chalane ka tareeka (project root se):
    python scripts/build_waterlevel.py

Pehle neeche CONFIG mein apne file paths daalo.

Output (data/processed/ mein):
    waterlevel_merged.csv           -> final table (model ke liye)
    station_master.csv              -> har station ek baar (lat/lon, district, well attributes)
    unmatched_B_stations.csv        -> B ke wo stations jo A se match nahi hue (baad mein dekhna)
    gprs_telemetry_linked.csv       -> telemetry (DWLR) readings, Semester 8 ke liye
    amsl_linked.csv                 -> AMSL readings (depth nahi, alag rakho)
    quality_year_round_counts.csv   -> saal x round ke row counts
"""
from pathlib import Path
import re

import numpy as np
import pandas as pd
from sklearn.neighbors import BallTree

# ------------------------- CONFIG -------------------------
PATH_A = Path("data/raw/CGWB - Changes in Depth to Water Level_Filtered_Data.csv")
PATH_B = Path("data/raw/groundwater-level-collected-manually.csv")  # India Data Portal manual file (.csv ya .xlsx)
OUT_DIR = Path("data/processed")

STATE_NAME = "rajasthan"       # A mein is state ke rows rakhte hain
# B ke data_type_description 3 tarah ke hain: MANUAL (depth to water, main table), GPRS (telemetry, alag file),
# AMSL (samudra tal se oopar level, depth nahi hai, alag file). Inhe mix mat karo.
MATCH_KM = 0.2                 # A aur B ke station itne km ke andar hon to 'same station' maante hain
LAT_RANGE = (22.5, 30.5)       # Rajasthan ka lagbhag bounding box (B ko pehle chhota karne ke liye)
LON_RANGE = (69.0, 78.5)
# ----------------------------------------------------------


def read_any(path: Path) -> pd.DataFrame:
    """Excel ho ya CSV, dono padh leta hai."""
    if not path.exists():
        raise SystemExit(f"File nahi mili: {path}")
    if path.suffix.lower() in (".xlsx", ".xls"):
        return pd.read_excel(path)
    return pd.read_csv(path, low_memory=False)


def clean_cols(df: pd.DataFrame) -> pd.DataFrame:
    """Column names ko snake_case bana deta hai.
    'Date (date)' -> 'date', 'Station Name' -> 'station_name'.
    Isse headers thode alag hon tab bhi script chal jati hai."""
    new_cols = []
    for c in df.columns:
        c = str(c).strip()
        m = re.search(r"\(([^)]+)\)\s*$", c)  # bracket ke andar ka naam le lo
        if m:
            c = m.group(1)
        c = re.sub(r"[^0-9a-zA-Z]+", "_", c).strip("_").lower()
        new_cols.append(c)
    df.columns = new_cols
    return df


def need(df: pd.DataFrame, cols: list, name: str) -> None:
    """Zaroori columns na ho to saaf message ke saath ruk jao."""
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise SystemExit(
            f"{name} mein ye columns nahi mile: {missing}\n"
            f"Jo columns mile: {list(df.columns)}"
        )


def nearest(src: pd.DataFrame, dst: pd.DataFrame):
    """src ke har station ke liye dst ka sabse paas wala station (index aur km)."""
    tree = BallTree(np.radians(dst[["latitude", "longitude"]].values), metric="haversine")
    dist, idx = tree.query(np.radians(src[["latitude", "longitude"]].values), k=1)
    return idx[:, 0], dist[:, 0] * 6371.0  # radians -> km


def round_name(month: int) -> str:
    """CGWB ke 4 rounds: Jan, pre-monsoon (May), Aug, Nov."""
    return {1: "Jan", 3: "May", 4: "May", 5: "May", 8: "Aug", 11: "Nov"}.get(month, "Other")


# =========================================================
# 1) Dataset A: state/district wala
# =========================================================
A = clean_cols(read_any(PATH_A))
need(A, ["date", "state_name", "district_name", "station_name",
         "latitude", "longitude", "currentlevel"], "Dataset A")

for col in ["basin", "sub_basin", "level_diff"]:   # optional columns
    if col not in A.columns:
        A[col] = np.nan

A["date"] = pd.to_datetime(A["date"], errors="coerce")
for col in ["latitude", "longitude", "currentlevel", "level_diff"]:
    A[col] = pd.to_numeric(A[col], errors="coerce")

A = A[A["state_name"].astype(str).str.lower().str.contains(STATE_NAME)]
A = A.dropna(subset=["date", "latitude", "longitude", "currentlevel"]).copy()
print(f"[A] Rajasthan rows: {len(A)}, stations: "
      f"{A[['station_name', 'latitude', 'longitude']].drop_duplicates().shape[0]}")

# A ke unique stations
stA = (A.drop_duplicates(["station_name", "latitude", "longitude"])
         [["station_name", "latitude", "longitude", "state_name",
           "district_name", "basin", "sub_basin"]]
         .reset_index(drop=True))

# =========================================================
# 2) Dataset B: India Data Portal manual file
# =========================================================
B = clean_cols(read_any(PATH_B))
need(B, ["station_name", "station_code", "latitude", "longitude", "date",
         "data_type_description", "data_value"], "Dataset B")

for col in ["well_type", "well_aquifer_type", "well_depth", "agency_name"]:  # optional
    if col not in B.columns:
        B[col] = np.nan

# Pehle dekho data types kaun kaun se hain (yahan dhyan se dekhna!)
print("\n[B] data_type_description ki values:")
print(B["data_type_description"].value_counts(dropna=False).head(15))

B["date"] = pd.to_datetime(B["date"], errors="coerce")
for col in ["latitude", "longitude", "data_value", "well_depth"]:
    B[col] = pd.to_numeric(B[col], errors="coerce")

dtl = B["data_type_description"].astype(str).str.lower()
B["wl_kind"] = np.select(
    [dtl.str.contains("amsl"), dtl.str.contains("gprs"),
     dtl.str.contains("manual") & dtl.str.contains("level")],
    ["amsl", "gprs", "manual"], default="other")
print("\n[B] type ke hisaab se rows:")
print(B["wl_kind"].value_counts().to_string())
B = B[B["wl_kind"] != "other"].dropna(subset=["date", "latitude", "longitude", "data_value"])
B = B[B["latitude"].between(*LAT_RANGE) & B["longitude"].between(*LON_RANGE)].copy()
print(f"[B] rows (Rajasthan box, teeno type): {len(B)}")

# B ke unique stations
stB = (B.drop_duplicates("station_code")
         [["station_code", "station_name", "latitude", "longitude",
           "well_type", "well_aquifer_type", "well_depth", "agency_name"]]
         .reset_index(drop=True))

# =========================================================
# 3) A aur B ke stations ko lat/lon se jodo
# =========================================================
stB["a_idx"], stB["km"] = nearest(stB, stA)
linked = stB[stB["km"] <= MATCH_KM].copy()
unmatched = stB[stB["km"] > MATCH_KM]
print(f"\n[Link] B stations: {len(stB)}, A se match (<= {MATCH_KM} km): {len(linked)}, "
      f"unmatched: {len(unmatched)}")

print("\n[Link] doori (km) ka summary:")
print(linked["km"].describe(percentiles=[.5, .9, .99]).round(3).to_string())
print("Links jo 0.2 km se door hain:", (linked["km"] > 0.2).sum())

# Ek A station se ek se zyada B station judein to sabse paas wala rakho
best = linked.sort_values("km").drop_duplicates("a_idx").set_index("a_idx")

# A stations ko SITE_ID do: B ka station_code (agar mila), warna lat/lon wala naam
stA["SITE_ID"] = [
    best.loc[i, "station_code"] if i in best.index
    else f"A_{r.latitude:.4f}_{r.longitude:.4f}"
    for i, r in stA.iterrows()
]
for col, newcol in [("well_type", "WELL_TYPE"),
                    ("well_aquifer_type", "AQUIFER_TYPE"),
                    ("well_depth", "WELL_DEPTH"),
                    ("agency_name", "AGENCY")]:
    stA[newcol] = [best.loc[i, col] if i in best.index else np.nan for i in stA.index]

# =========================================================
# 4) Readings ko ek jaisa banao
# =========================================================
common = ["SITE_ID", "DATE", "STATE_NAME", "DISTRICT_NAME", "STATION_NAME", "LAT", "LON",
          "BASIN", "SUB_BASIN", "WELL_TYPE", "AQUIFER_TYPE", "WELL_DEPTH",
          "WLS_WTR_LEVEL", "LEVEL_DIFF", "SOURCE_DS"]

# --- A ki readings
rowsA = A.merge(stA, on=["station_name", "latitude", "longitude"], how="left",
                suffixes=("", "_st"))
rowsA = rowsA.rename(columns={
    "date": "DATE", "state_name": "STATE_NAME", "district_name": "DISTRICT_NAME",
    "station_name": "STATION_NAME", "latitude": "LAT", "longitude": "LON",
    "basin": "BASIN", "sub_basin": "SUB_BASIN",
    "currentlevel": "WLS_WTR_LEVEL", "level_diff": "LEVEL_DIFF"})
rowsA["SOURCE_DS"] = "A"
rowsA = rowsA[common]

# --- B ki readings (sirf wo stations jo A se linked hain)
link_map = linked.set_index("station_code")["a_idx"]


def to_rows(Bsub: pd.DataFrame) -> pd.DataFrame:
    r = Bsub[Bsub["station_code"].isin(link_map.index)].copy()
    r["a_idx"] = r["station_code"].map(link_map)
    r = r.join(stA[["SITE_ID", "state_name", "district_name", "station_name",
                    "latitude", "longitude", "basin", "sub_basin",
                    "WELL_TYPE", "AQUIFER_TYPE", "WELL_DEPTH"]],
               on="a_idx", rsuffix="_A")
    r = r.rename(columns={
        "date": "DATE", "state_name": "STATE_NAME", "district_name": "DISTRICT_NAME",
        "station_name_A": "STATION_NAME", "latitude_A": "LAT", "longitude_A": "LON",
        "basin": "BASIN", "sub_basin": "SUB_BASIN", "data_value": "WLS_WTR_LEVEL"})
    r["LEVEL_DIFF"] = np.nan
    r["SOURCE_DS"] = "B"
    return r[common]


rowsB = to_rows(B[B["wl_kind"] == "manual"])      # main table
rowsGPRS = to_rows(B[B["wl_kind"] == "gprs"])     # telemetry (Semester 8)
rowsAMSL = to_rows(B[B["wl_kind"] == "amsl"])     # samudra tal se oopar level
print(f"[B] linked manual rows: {len(rowsB)}, gprs: {len(rowsGPRS)}, amsl: {len(rowsAMSL)}")

# =========================================================
# 5) Overlap check: dono mein same station + date ho to values milti hain?
# =========================================================
# Ek round mahine mein hota hai, par date alag ho sakti hai, isliye station + mahina (YM) se match karte hain
rowsA["YM"] = rowsA["DATE"].dt.to_period("M")
rowsB["YM"] = rowsB["DATE"].dt.to_period("M")
ov = rowsA.merge(rowsB, on=["SITE_ID", "YM"], suffixes=("_A", "_B"))
print(f"\n[Overlap] A aur B mein same station + same mahine wali rows: {len(ov)}")
if len(ov) > 0:
    diff = (ov["WLS_WTR_LEVEL_A"] - ov["WLS_WTR_LEVEL_B"]).abs()
    print("  |A - B| ka summary (0 ke paas hona chahiye):")
    print(diff.describe().round(3).to_string())

# =========================================================
# 6) Merge, duplicates hatao (A ko priority), features
# =========================================================
df = pd.concat([rowsA, rowsB], ignore_index=True)
df = df.sort_values(["SITE_ID", "DATE", "SOURCE_DS"])        # 'A' pehle aata hai
df = df.drop_duplicates(["SITE_ID", "YM"], keep="first")     # ek station ka ek mahine mein ek hi reading
df = df.drop(columns="YM")
df["YEAR"] = df["DATE"].dt.year
df["MONTH"] = df["DATE"].dt.month
df["ROUND"] = df["MONTH"].map(round_name)
df["OUTLIER"] = (df["WLS_WTR_LEVEL"] < 0) | (df["WLS_WTR_LEVEL"] > 300)  # flag, delete nahi kiya

# =========================================================
# 7) Quality report
# =========================================================
print(f"\n[Final] rows: {len(df)}, stations: {df['SITE_ID'].nunique()}, "
      f"districts: {df['DISTRICT_NAME'].nunique()}")
print(f"[Final] date range: {df['DATE'].min().date()} se {df['DATE'].max().date()}")
print(f"[Final] OUTLIER flag (level <0 ya >300): {int(df['OUTLIER'].sum())} rows (check karo)")
print("\n[Unmatched B stations] agency_name ki values:")
print(unmatched["agency_name"].value_counts(dropna=False).head(8).to_string())

counts = df.pivot_table(index="YEAR", columns="ROUND", values="SITE_ID",
                        aggfunc="count", fill_value=0)
print("\n[Quality] Saal x round ke row counts:")
print(counts.to_string())

yrs = df.groupby("SITE_ID")["YEAR"].nunique()
print(f"\n[Quality] Kitne stations 3+ saal ke data wale: {(yrs >= 3).sum()} / {len(yrs)}")

# =========================================================
# 8) Save
# =========================================================
OUT_DIR.mkdir(parents=True, exist_ok=True)
df.to_csv(OUT_DIR / "waterlevel_merged.csv", index=False)
stA.to_csv(OUT_DIR / "station_master.csv", index=False)
unmatched.to_csv(OUT_DIR / "unmatched_B_stations.csv", index=False)
counts.to_csv(OUT_DIR / "quality_year_round_counts.csv")
rowsGPRS.to_csv(OUT_DIR / "gprs_telemetry_linked.csv", index=False)
rowsAMSL.to_csv(OUT_DIR / "amsl_linked.csv", index=False)
print(f"\nSaved: {OUT_DIR}/waterlevel_merged.csv (+ station_master, unmatched, counts)")