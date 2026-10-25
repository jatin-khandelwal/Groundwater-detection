"""
add_climate2_features.py
Reads dataset_v2_2.csv + climate2_monthly.csv and writes
  data\\processed\\dataset_v2_3.csv
  data\\processed\\feature_groups_v2_3.json   (v2_2 groups + new group "evap_soil_extra")
  data\\processed\\climate2_extra_dictionary.csv
No existing file is overwritten.

Leakage rules:
  - every feature uses only months BEFORE the reading's month (shift(1), then rolling)
  - anomalies use normals from 2005-2020 only (per grid cell x calendar month)

Run from C:\\Ground water (venv active):  python add_climate2_features.py
"""
from pathlib import Path
import json
import pandas as pd

P = Path(r"C:\Ground water\data\processed")
NORM_Y0, NORM_Y1 = 2005, 2020

d = pd.read_csv(P / "dataset_v2_2.csv", dtype={"SITE_ID": str}, low_memory=False)
c = pd.read_csv(P / "climate2_monthly.csv")
c = c.sort_values(["lat_grid", "lon_grid", "YEAR", "MONTH"]).reset_index(drop=True)

# train-only normal for root-zone soil wetness (grid cell x calendar month)
nrm = (c[c.YEAR.between(NORM_Y0, NORM_Y1)]
       .groupby(["lat_grid", "lon_grid", "MONTH"])["gwetroot"].mean()
       .rename("gwetroot_norm").reset_index())
c = c.merge(nrm, on=["lat_grid", "lon_grid", "MONTH"], how="left")
c["gwetroot_anom"] = c["gwetroot"] - c["gwetroot_norm"]

g = c.groupby(["lat_grid", "lon_grid"])


def prev(col, n, how):
    """Previous n months (current month excluded). how = 'sum' or 'mean'."""
    def f(s):
        r = s.shift(1).rolling(n, min_periods=n)
        return r.sum() if how == "sum" else r.mean()
    return g[col].transform(f)


c["pet_prev3m_sum_mm"] = prev("pet_mm", 3, "sum")
c["pet_prev12m_sum_mm"] = prev("pet_mm", 12, "sum")
c["soil_wet_root_prev3m_mean"] = prev("gwetroot", 3, "mean")
c["soil_wet_root_anom_prev3m"] = prev("gwetroot_anom", 3, "mean")
c["soil_wet_top_prev1m"] = g["gwettop"].shift(1)
c["evland_prev3m_mean"] = prev("evland_mm_day", 3, "mean")

new_cols = ["pet_prev3m_sum_mm", "pet_prev12m_sum_mm", "water_balance_prev12m_mm",
            "soil_wet_root_prev3m_mean", "soil_wet_root_anom_prev3m",
            "soil_wet_top_prev1m", "evland_prev3m_mean"]

# join on station's rainfall grid cell + year + month
d["_lat"] = d["rainfall_grid_lat"].round(3)
d["_lon"] = d["rainfall_grid_lon"].round(3)
c["lat_grid"] = c["lat_grid"].round(3)
c["lon_grid"] = c["lon_grid"].round(3)
keep = c[["lat_grid", "lon_grid", "YEAR", "MONTH", "pet_prev3m_sum_mm", "pet_prev12m_sum_mm",
          "soil_wet_root_prev3m_mean", "soil_wet_root_anom_prev3m",
          "soil_wet_top_prev1m", "evland_prev3m_mean"]]
d3 = d.merge(keep, left_on=["_lat", "_lon", "YEAR", "MONTH"],
             right_on=["lat_grid", "lon_grid", "YEAR", "MONTH"], how="left")
d3 = d3.drop(columns=["_lat", "_lon", "lat_grid", "lon_grid"])
assert len(d3) == len(d), "row count changed after merge"

# water balance: rain_cum_12m_mm (previous 12 months, existing column) minus PET of the same window
d3["water_balance_prev12m_mm"] = d3["rain_cum_12m_mm"] - d3["pet_prev12m_sum_mm"]

print("Rows:", len(d3), "(92452 aana chahiye) | columns:", d3.shape[1], "(77 aana chahiye)")
win = d3[d3.YEAR.between(2005, 2023)]
print("\nMissing % (2005-2023):")
print((win[new_cols].isna().mean() * 100).round(2).to_string())
print("\ndescribe (2005-2023):")
print(win[new_cols].describe().round(2).T.to_string())
print("\nmean by SPLIT:")
print(d3.groupby("SPLIT")[new_cols].mean().round(1).T.to_string())

d3.to_csv(P / "dataset_v2_3.csv", index=False)

fg = json.loads((P / "feature_groups_v2_2.json").read_text(encoding="utf-8"))
fg["evap_soil_extra"] = new_cols
(P / "feature_groups_v2_3.json").write_text(json.dumps(fg, indent=2), encoding="utf-8")

desc = {
    "pet_prev3m_sum_mm": "Pichhle 3 mahine ka PET (Hargreaves estimate, mm), current mahina shamil nahi",
    "pet_prev12m_sum_mm": "Pichhle 12 mahine ka PET (Hargreaves estimate, mm)",
    "water_balance_prev12m_mm": "rain_cum_12m_mm minus pet_prev12m_sum_mm (mm); negative = PET rainfall se zyada",
    "soil_wet_root_prev3m_mean": "Pichhle 3 mahine ka root-zone soil wetness (NASA POWER GWETROOT, relative index 0-1)",
    "soil_wet_root_anom_prev3m": "Pichhle 3 mahine ka root-zone wetness anomaly (2005-2020 normal se)",
    "soil_wet_top_prev1m": "Pichhle mahine ka surface soil wetness (GWETTOP, index 0-1)",
    "evland_prev3m_mean": "Pichhle 3 mahine ka average evaporation land (EVLAND, mm/day)",
}
pd.DataFrame({"column": list(desc), "group": "evap_soil_extra", "description": list(desc.values())}) \
  .to_csv(P / "climate2_extra_dictionary.csv", index=False, encoding="utf-8-sig")
print("\nSaved dataset_v2_3.csv, feature_groups_v2_3.json, climate2_extra_dictionary.csv")
