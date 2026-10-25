"""
build_climate2_monthly.py
Reads the daily JSON files from download_climate2.py and writes
data\\processed\\climate2_monthly.csv  (expected: 144 cells x 252 months = 36,288 rows)

Columns: lat_grid, lon_grid, YEAR, MONTH, pet_mm, gwetroot, gwettop, evland_mm_day,
         tmax_mean_c, tmin_mean_c, valid_days
PET = Hargreaves: 0.0023 * Ra * (Tmean + 17.8) * sqrt(max(Tmax - Tmin, 0))   [Ra in mm/day]
Monthly PET = mean daily PET * days in month (NaN if fewer than 20 valid days).

Run from C:\\Ground water (venv active):  python build_climate2_monthly.py
Does not touch any existing file.
"""
from pathlib import Path
import json
import numpy as np
import pandas as pd

ROOT = Path(r"C:\Ground water")
RAW = ROOT / "data" / "raw" / "nasa_power_climate2_json"
OUT = ROOT / "data" / "processed" / "climate2_monthly.csv"
MIN_VALID = 20


def extraterrestrial_mm_day(lat_deg, doy):
    """FAO-56 eq. 21: Ra in MJ/m2/day, converted to mm/day (x 0.408)."""
    phi = np.radians(lat_deg)
    dr = 1 + 0.033 * np.cos(2 * np.pi * doy / 365)
    delta = 0.409 * np.sin(2 * np.pi * doy / 365 - 1.39)
    ws = np.arccos(np.clip(-np.tan(phi) * np.tan(delta), -1, 1))
    ra = (24 * 60 / np.pi) * 0.0820 * dr * (
        ws * np.sin(phi) * np.sin(delta) + np.cos(phi) * np.cos(delta) * np.sin(ws))
    return 0.408 * ra


def one_cell(f):
    lat, lon = (float(x) for x in f.stem.split("_"))
    par = json.loads(f.read_text(encoding="utf-8"))
    d = pd.DataFrame({k: pd.Series(v, dtype=float) for k, v in par.items()})
    d.index = pd.to_datetime(d.index, format="%Y%m%d")
    d = d.mask(d <= -900)                      # NASA fill value -999 -> NaN

    ra = extraterrestrial_mm_day(lat, d.index.dayofyear.values)
    tmean = (d["T2M_MAX"] + d["T2M_MIN"]) / 2
    rng = (d["T2M_MAX"] - d["T2M_MIN"]).clip(lower=0)
    d["pet"] = 0.0023 * ra * (tmean + 17.8) * np.sqrt(rng)

    g = d.groupby([d.index.year, d.index.month])
    m = pd.DataFrame({
        "pet_mean_day": g["pet"].mean(),
        "pet_days": g["pet"].count(),
        "gwetroot": g["GWETROOT"].mean(), "gwetroot_days": g["GWETROOT"].count(),
        "gwettop": g["GWETTOP"].mean(), "gwettop_days": g["GWETTOP"].count(),
        "evland_mm_day": g["EVLAND"].mean(), "evland_days": g["EVLAND"].count(),
        "tmax_mean_c": g["T2M_MAX"].mean(), "tmin_mean_c": g["T2M_MIN"].mean(),
    })
    m.index.names = ["YEAR", "MONTH"]
    m = m.reset_index()
    dim = pd.to_datetime(dict(year=m.YEAR, month=m.MONTH, day=1)).dt.days_in_month
    m["pet_mm"] = m["pet_mean_day"] * dim
    for v, n in [("pet_mm", "pet_days"), ("gwetroot", "gwetroot_days"),
                 ("gwettop", "gwettop_days"), ("evland_mm_day", "evland_days")]:
        m.loc[m[n] < MIN_VALID, v] = np.nan
    m["valid_days"] = m["pet_days"]
    m.insert(0, "lon_grid", lon)
    m.insert(0, "lat_grid", lat)
    return m[["lat_grid", "lon_grid", "YEAR", "MONTH", "pet_mm", "gwetroot", "gwettop",
              "evland_mm_day", "tmax_mean_c", "tmin_mean_c", "valid_days"]]


files = sorted(RAW.glob("*.json"))
print("json files:", len(files), "(144 aana chahiye)")
out = pd.concat([one_cell(f) for f in files], ignore_index=True)
out = out.sort_values(["lat_grid", "lon_grid", "YEAR", "MONTH"]).reset_index(drop=True)

print("rows:", len(out), "(36288 aana chahiye)")
per = out.groupby(["lat_grid", "lon_grid"]).size()
print("rows per cell min/max:", per.min(), per.max(), "(252 / 252 aana chahiye)")
print("\nmissing % per column:")
print((out.isna().mean() * 100).round(2).to_string())

print("\ndescribe:")
print(out[["pet_mm", "gwetroot", "gwettop", "evland_mm_day", "tmax_mean_c", "tmin_mean_c"]]
      .describe().round(2).T.to_string())

# plausibility: annual PET per cell, average over complete years 2005-2020
ann = (out[out.YEAR.between(2005, 2020)].groupby(["lat_grid", "lon_grid", "YEAR"])["pet_mm"]
       .agg(["sum", "count"]).reset_index())
ann = ann[ann["count"] == 12]
print("\nannual PET mm (cells x years):")
print(ann["sum"].describe().round(0).to_string(), "\n(Rajasthan ke liye ~1500-2500 plausible lagta hai)")

print("\nmonthly mean PET (all cells, 2005-2020):")
print(out[out.YEAR.between(2005, 2020)].groupby("MONTH")["pet_mm"].mean().round(0).to_string())

out.to_csv(OUT, index=False)
print("\nsaved", OUT)
