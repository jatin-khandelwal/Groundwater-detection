"""
make_normals.py
District x month ka rainfall normal (2005-2020), saare 12 mahine ke liye.
Backend ko future month ke rainfall ke liye ye chahiye.

Chalao (C:\\Ground water se):
    python make_normals.py
"""
import pandas as pd

P = "data/processed/"
Y0, Y1 = 2005, 2020   # sirf training years (leakage nahi)

# 1) Kaun sa district kaun se rainfall grid cells use karta hai (stations se)
d = pd.read_csv(P + "dataset_v2_1.csv", dtype={"SITE_ID": str}, low_memory=False,
                usecols=["DISTRICT_NAME", "rainfall_grid_lat", "rainfall_grid_lon"])
d = d.drop_duplicates().rename(columns={"rainfall_grid_lat": "lat_grid",
                                        "rainfall_grid_lon": "lon_grid"})

# 2) Monthly rainfall (saare mahine), sirf 2005-2020
r = pd.read_csv(P + "rainfall_monthly.csv")
r = r[r["YEAR"].between(Y0, Y1)]
for df in (d, r):   # float match ke liye round
    df["lat_grid"] = df["lat_grid"].round(3)
    df["lon_grid"] = df["lon_grid"].round(3)

m = d.merge(r, on=["lat_grid", "lon_grid"], how="inner")

# 3) Pehle har grid cell ka month-wise average, phir district ke cells ka average
cell = (m.groupby(["DISTRICT_NAME", "lat_grid", "lon_grid", "MONTH"])["rainfall_mm"]
          .mean().reset_index())
out = (cell.groupby(["DISTRICT_NAME", "MONTH"])
           .agg(normal_mm=("rainfall_mm", "mean"), n_grid_cells=("lat_grid", "size"))
           .reset_index())
out["normal_mm"] = out["normal_mm"].round(2)
out["period"] = f"{Y0}-{Y1}"

# 4) Checks
print("Rows:", len(out), "(33 districts x 12 mahine = 396 hone chahiye)")
print("Districts:", out["DISTRICT_NAME"].nunique(), " Months:", out["MONTH"].nunique())
print("Missing normal_mm:", int(out["normal_mm"].isna().sum()))
print("Districts jinke grid cells nahi mile:",
      sorted(set(d["DISTRICT_NAME"]) - set(out["DISTRICT_NAME"])))
print("\nSabse zyada barish wale 3 (August):")
print(out[out["MONTH"] == 8].nlargest(3, "normal_mm")[["DISTRICT_NAME", "normal_mm"]].to_string(index=False))
print("Sabse kam barish wale 3 (August):")
print(out[out["MONTH"] == 8].nsmallest(3, "normal_mm")[["DISTRICT_NAME", "normal_mm"]].to_string(index=False))

out.to_csv(P + "rainfall_normals_v2_1.csv", index=False)
print("\nSaved: data/processed/rainfall_normals_v2_1.csv")
