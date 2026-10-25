"""
add_climate_features.py
climate_monthly.csv se 6 naye features banata hai aur dataset_v2_1.csv mein jodkar
dataset_v2_2.csv banata hai. Purani files nahi badalti.

Chalao (download_climate_extra.py poora chalne ke baad):
    python add_climate_features.py

Rules (leakage nahi):
  - Features reading wale mahine se PEHLE ke mahino se bante hain (current mahina shamil nahi)
  - Normals sirf 2005-2020 se (train years)
"""
import json
from pathlib import Path

import pandas as pd

P = Path("data/processed")
NORM_Y0, NORM_Y1 = 2005, 2020

d = pd.read_csv(P / "dataset_v2_1.csv", dtype={"SITE_ID": str}, low_memory=False)
c = pd.read_csv(P / "climate_monthly.csv")
c = c.sort_values(["lat_grid", "lon_grid", "YEAR", "MONTH"]).reset_index(drop=True)

# Har cell mein mahine continuous hone chahiye (rolling ke liye)
per_cell = c.groupby(["lat_grid", "lon_grid"]).size()
print(f"Cells: {len(per_cell)}, har cell ke rows min/max: {per_cell.min()}/{per_cell.max()}")

# Train-only normals (grid x calendar month)
tr = c[c["YEAR"].between(NORM_Y0, NORM_Y1)]
norm = (tr.groupby(["lat_grid", "lon_grid", "MONTH"])[["t2m_mean_c", "rh2m_mean_pct"]]
          .mean().rename(columns={"t2m_mean_c": "t_norm", "rh2m_mean_pct": "rh_norm"})
          .reset_index())
c = c.merge(norm, on=["lat_grid", "lon_grid", "MONTH"], how="left")
c["t_anom"] = c["t2m_mean_c"] - c["t_norm"]
c["rh_anom"] = c["rh2m_mean_pct"] - c["rh_norm"]

g = c.groupby(["lat_grid", "lon_grid"])


def prev_mean(col, n):
    """Pichhle n mahino ka average (current mahina shamil nahi)."""
    return g[col].transform(lambda s: s.shift(1).rolling(n, min_periods=n).mean())


c["temp_prev3m_mean_c"] = prev_mean("t2m_mean_c", 3)
c["temp_prev12m_mean_c"] = prev_mean("t2m_mean_c", 12)
c["temp_anom_prev3m_c"] = prev_mean("t_anom", 3)
c["temp_anom_prev12m_c"] = prev_mean("t_anom", 12)
c["rh_prev3m_mean_pct"] = prev_mean("rh2m_mean_pct", 3)
c["rh_anom_prev3m_pct"] = prev_mean("rh_anom", 3)
new_cols = ["temp_prev3m_mean_c", "temp_prev12m_mean_c", "temp_anom_prev3m_c",
            "temp_anom_prev12m_c", "rh_prev3m_mean_pct", "rh_anom_prev3m_pct"]

# Dataset se jodo (station ke rainfall grid cell + saal + mahina)
d["_lat"] = d["rainfall_grid_lat"].round(3)
d["_lon"] = d["rainfall_grid_lon"].round(3)
c["lat_grid"] = c["lat_grid"].round(3)
c["lon_grid"] = c["lon_grid"].round(3)
keep = c[["lat_grid", "lon_grid", "YEAR", "MONTH"] + new_cols]
d2 = d.merge(keep, left_on=["_lat", "_lon", "YEAR", "MONTH"],
             right_on=["lat_grid", "lon_grid", "YEAR", "MONTH"], how="left")
d2 = d2.drop(columns=["_lat", "_lon", "lat_grid", "lon_grid"])
assert len(d2) == len(d), "Merge ke baad rows badal gayi, kuch duplicate ho gaya"

print(f"\nRows: {len(d2)} (pehle jitni hi), columns: {d2.shape[1]}")
win = d2[d2["YEAR"].between(2005, 2023)]
print("Missing % (2005-2023):")
print((win[new_cols].isna().mean() * 100).round(2).to_string())

d2.to_csv(P / "dataset_v2_2.csv", index=False)

# feature groups: purane mein ek naya group jodo
fg_path = P / "feature_groups_v2_1.json"
if fg_path.exists():
    fg = json.loads(fg_path.read_text(encoding="utf-8"))
    fg["climate_extra"] = new_cols
    (P / "feature_groups_v2_2.json").write_text(json.dumps(fg, indent=2), encoding="utf-8")
    print("\nSaved feature_groups_v2_2.json (naya group: climate_extra)")
else:
    print("\n[WARN] feature_groups_v2_1.json nahi mili, groups file nahi bani")

desc = {
    "temp_prev3m_mean_c": "Pichhle 3 mahine ka average temperature (C), NASA POWER T2M",
    "temp_prev12m_mean_c": "Pichhle 12 mahine ka average temperature (C)",
    "temp_anom_prev3m_c": "Pichhle 3 mahine ka temperature anomaly (2005-2020 normal se)",
    "temp_anom_prev12m_c": "Pichhle 12 mahine ka temperature anomaly",
    "rh_prev3m_mean_pct": "Pichhle 3 mahine ka average relative humidity (%), NASA POWER RH2M",
    "rh_anom_prev3m_pct": "Pichhle 3 mahine ka humidity anomaly (2005-2020 normal se)",
}
pd.DataFrame({"column": list(desc), "group": "climate_extra", "description": list(desc.values())}) \
  .to_csv(P / "climate_extra_dictionary.csv", index=False, encoding="utf-8-sig")
print("Saved dataset_v2_2.csv, climate_extra_dictionary.csv")
