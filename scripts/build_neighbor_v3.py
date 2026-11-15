"""build_neighbor_v3.py

Neighbor features ko EK SAAF, LIKHE HUE rule se dobara banata hai
(training aur Backend inference dono mein yahi rule lagega).

RULE (find_neighbor_rule.py ke log se mila, result dekhke nahi badlega):
  - K = 5 sabse paas ke DOOSRE stations (station khud exclude), R_KM = 40 km ke andar (nearest_first).
    Stored distance ka max 37.39 km hai, isliye 40 km.
  - Har neighbor ki wo reading jo row ki DATE se STRICTLY pehle ki sabse nayi ho. Koi age limit nahi.
  - Jis neighbor ki aisi reading nahi, wo count nahi hota (use chhod ke agla station NAHI liya jaata).
  - Output:
      nb3_prev_level_mean_5_m    = in readings ka average (count 0 ho to NaN)
      nb3_prev_level_count_5     = kitne neighbors ki pichhli reading mili (0 se 5)
      nb3_nearest_dist_km        = unme se sabse paas wale ki doori (count 0 ho to NaN)

Ye script kuch overwrite nahi karti. Sirf data/processed/neighbor_v3.csv banati hai.
Chalao (project root se):  python scripts\\build_neighbor_v3.py
"""
import os
import sys
import time

import numpy as np
import pandas as pd

ROOT = os.environ.get("GW_ROOT", r"C:\Ground water")
os.chdir(ROOT)
sys.path.append(os.path.join(ROOT, "scripts"))
import model_utils as mu

K, R_KM, MAX_AGE_DAYS = 5, 40.0, None  # MAX_AGE_DAYS None = koi limit nahi
OUT = os.path.join("data", "processed", "neighbor_v3.csv")

t0 = time.time()
d = mu.load_data().reset_index(drop=True)
T = mu.TARGET
need = ["SITE_ID", "DATE", "LAT", "LON", T, "SPLIT"]
miss = [c for c in need if c not in d.columns]
assert not miss, f"Ye columns nahi mile: {miss}"
d["SITE_ID"] = d["SITE_ID"].astype(str)
d["_day"] = pd.to_datetime(d["DATE"]).values.astype("datetime64[D]").astype("int64")
print("rows:", len(d), "| stations:", d["SITE_ID"].nunique())

# ---- station coordinates aur pairwise doori (haversine, km) ----
st = d.groupby("SITE_ID")[["LAT", "LON"]].first()
ids = st.index.values
idx_of = {s: i for i, s in enumerate(ids)}
lat = np.radians(st["LAT"].values.astype(float))
lon = np.radians(st["LON"].values.astype(float))
with np.errstate(invalid="ignore"):
    a = (np.sin((lat[:, None] - lat[None, :]) / 2) ** 2
         + np.cos(lat)[:, None] * np.cos(lat)[None, :] * np.sin((lon[:, None] - lon[None, :]) / 2) ** 2)
    D = 2 * 6371.0088 * np.arcsin(np.sqrt(a))
np.fill_diagonal(D, np.inf)
print("stations jinke coordinates missing hain:", int(np.isnan(lat).sum()))

cand = []
for i in range(len(ids)):
    with np.errstate(invalid="ignore"):
        j = np.where(D[i] <= R_KM)[0]
    cand.append(j[np.argsort(D[i, j])])

# ---- har station ki sorted readings ----
obs = {}
for s, g in d.dropna(subset=[T]).groupby("SITE_ID"):
    g = g.sort_values("_day")
    obs[s] = (g["_day"].values, g[T].values.astype(float))

# ---- har row ke liye neighbor features ----
n = len(d)
sid = d["SITE_ID"].values
day = d["_day"].values
mean_ = np.full(n, np.nan)
count_ = np.zeros(n, dtype=int)
near_ = np.full(n, np.nan)
worst = -10 ** 9  # (source reading ki date) minus (row ki date): hamesha negative hona chahiye

for r in range(n):
    i = idx_of[sid[r]]
    vals, dist = [], []
    for j in cand[i][:K]:  # nearest_first: pehle K sabse paas ke stations, chahe reading ho ya na ho
        o = obs.get(ids[j])
        if o is None:
            continue
        days, lv = o
        p = np.searchsorted(days, day[r], side="left") - 1  # strictly pehle
        if p < 0:
            continue
        if MAX_AGE_DAYS is not None and day[r] - days[p] > MAX_AGE_DAYS:
            continue
        worst = max(worst, int(days[p] - day[r]))
        vals.append(lv[p])
        dist.append(D[i, j])
    if vals:
        mean_[r] = float(np.mean(vals))
        count_[r] = len(vals)
        near_[r] = float(min(dist))
    if (r + 1) % 20000 == 0:
        print(f"  {r + 1}/{n} rows ho gayi ({time.time() - t0:.0f} sec)", flush=True)

assert worst < 0, f"LEAKAGE: koi neighbor reading row ki date ya uske baad ki mili (worst={worst})"
print("Leakage check PASS: sabhi source readings row ki date se pehle ki hain (sabse paas ka farak:", worst, "din)")

res = pd.DataFrame({
    "SITE_ID": d["SITE_ID"], "DATE": d["DATE"].astype(str),
    "nb3_prev_level_mean_5_m": mean_,
    "nb3_prev_level_count_5": count_,
    "nb3_nearest_dist_km": near_,
})
res.to_csv(OUT, index=False)
print("saved:", OUT)

# ---- summary ----
d["_c"] = count_
print("\ncount ka distribution (SPLIT ke hisaab se, %):")
print((pd.crosstab(d["SPLIT"], d["_c"], normalize="index") * 100).round(1).to_string())
print("\nnearest_dist_km percentiles (count > 0 wali rows):")
print(pd.Series(near_[count_ > 0]).describe(percentiles=[.5, .9, .95, .99]).round(2).to_string())

old = [c for c in ["neighbor_prev_level_mean_5_m", "neighbor_prev_level_count_5",
                   "nearest_neighbor_prev_distance_km"] if c in d.columns]
if len(old) == 3:
    print("\nPurane stored features se tulna (sirf jaankari ke liye, match karna zaroori nahi):")
    ok = (~np.isnan(mean_)) & d["neighbor_prev_level_mean_5_m"].notna().values
    diff = np.abs(mean_[ok] - d.loc[ok, "neighbor_prev_level_mean_5_m"].values)
    print("  dono jagah mean maujood:", int(ok.sum()), "rows | mean ka median farak (m):", round(float(np.median(diff)), 3),
          "| 90th percentile farak (m):", round(float(np.percentile(diff, 90)), 3))
    print("  count barabar:", round(float((count_ == d["neighbor_prev_level_count_5"].fillna(0).values).mean() * 100), 1), "% rows")
print(f"\nDone ({time.time() - t0:.0f} sec)")
