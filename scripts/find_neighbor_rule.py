"""
find_neighbor_rule.py
Ye script dhoondhti hai ki dataset ke 3 neighbor features:
    neighbor_prev_level_mean_5_m, neighbor_prev_level_count_5, nearest_neighbor_prev_distance_km
kis rule se bane the. Alag-alag rules (kitne neighbors, kitni door tak, kitni purani reading,
pehle nearest ya pehle valid) 1,200 random rows par aazmati hai aur dekhti hai ki kaun sa rule
stored values ko sabse zyada rows par reproduce karta hai.

Kuch badalti nahi, sirf padhti hai. Project root se chalao:
    python scripts\\find_neighbor_rule.py

Mode 'nearest_time_any' ek LEAKAGE TEST hai: ye pichhli ya agli, jo bhi reading date ke
sabse paas ho wo leti hai. Agar yahi rule sabse upar aaye, to feature mein future ka level
ghus raha hai.
"""
import itertools
from pathlib import Path

import numpy as np
import pandas as pd

P = Path("data/processed/dataset_v2_3.csv")
N = 1200
SEED = 0
cols = ["SITE_ID", "DATE", "LAT", "LON", "WLS_WTR_LEVEL", "YEAR",
        "neighbor_prev_level_mean_5_m", "neighbor_prev_level_count_5",
        "nearest_neighbor_prev_distance_km"]
d = pd.read_csv(P, usecols=cols, dtype={"SITE_ID": str})
d["DATE"] = pd.to_datetime(d["DATE"])
d["t"] = (d["DATE"] - pd.Timestamp("1970-01-01")).dt.days.astype(int)
d = d.sort_values(["SITE_ID", "t"]).reset_index(drop=True)
sites = d["SITE_ID"].unique()
d["si"] = d["SITE_ID"].map({s: i for i, s in enumerate(sites)})
n_st = len(sites)
coords = d.groupby("si")[["LAT", "LON"]].first().values
T = [g["t"].values for _, g in d.groupby("si")]
L = [g["WLS_WTR_LEVEL"].values for _, g in d.groupby("si")]
print(f"Rows {len(d)}, stations {n_st}")
print("Stored count ka distribution:", d["neighbor_prev_level_count_5"].value_counts().sort_index().to_dict())
print("Stored distance (km) describe:", d["nearest_neighbor_prev_distance_km"].describe().round(2).to_dict())

rows = d[d["YEAR"].between(2005, 2023)].sample(n=min(N, len(d)), random_state=SEED)
n = len(rows)
tr, si_r = rows["t"].values, rows["si"].values
s_mean = rows["neighbor_prev_level_mean_5_m"].values
s_cnt = rows["neighbor_prev_level_count_5"].values
s_dist = rows["nearest_neighbor_prev_distance_km"].values

# Doori matrix (rows x stations), self (SITE_ID) bahar. Same jagah ke doosre ID rahenge (doori 0).
lat, lon = np.radians(coords[:, 0]), np.radians(coords[:, 1])
la_r, lo_r = lat[si_r][:, None], lon[si_r][:, None]
a = np.sin((lat[None, :] - la_r) / 2) ** 2 + np.cos(la_r) * np.cos(lat[None, :]) * np.sin((lon[None, :] - lo_r) / 2) ** 2
D = 2 * 6371.0088 * np.arcsin(np.sqrt(a))
D[np.arange(n), si_r] = np.inf

modes = ["strict", "le", "nearest_time_any"]
AGE = {m: np.full((n, n_st), np.nan) for m in modes}
LV = {m: np.full((n, n_st), np.nan) for m in modes}
for j in range(n_st):
    tj, lj = T[j], L[j]
    kl = np.searchsorted(tj, tr, side="left") - 1          # strictly before
    ok = kl >= 0
    AGE["strict"][ok, j] = tr[ok] - tj[kl[ok]]
    LV["strict"][ok, j] = lj[kl[ok]]
    kr = np.searchsorted(tj, tr, side="right") - 1         # on or before
    ok = kr >= 0
    AGE["le"][ok, j] = tr[ok] - tj[kr[ok]]
    LV["le"][ok, j] = lj[kr[ok]]
    kf = np.searchsorted(tj, tr, side="left")              # first on/after (future)
    before = np.where(kl >= 0, np.abs(tr - tj[np.clip(kl, 0, len(tj) - 1)]), np.inf)
    after = np.where(kf < len(tj), np.abs(tj[np.clip(kf, 0, len(tj) - 1)] - tr), np.inf)
    use_before = before <= after
    k_use = np.where(use_before, kl, kf)
    okk = np.isfinite(np.minimum(before, after))
    AGE["nearest_time_any"][okk, j] = np.minimum(before, after)[okk]
    LV["nearest_time_any"][okk, j] = lj[np.clip(k_use, 0, len(lj) - 1)][okk]

dstat = D.min(axis=1)    # sabse paas ka station (data ho ya na ho)


def run(mode, W, K, R, pre):
    age, lv = AGE[mode], LV[mode]
    valid = ~np.isnan(age)
    if W is not None:
        valid = valid & (age <= W)
    Dr = D if R is None else np.where(D <= R, D, np.inf)
    if pre == "valid_first":
        Dm = np.where(valid, Dr, np.inf)
        idx = np.argpartition(Dm, K - 1, axis=1)[:, :K]
        dsel = np.take_along_axis(Dm, idx, 1)
        fin = np.isfinite(dsel)
    else:  # nearest_first: pehle K sabse paas ke stations, phir jinki reading valid ho
        idx = np.argpartition(Dr, K - 1, axis=1)[:, :K]
        dsel = np.take_along_axis(Dr, idx, 1)
        fin = np.isfinite(dsel) & np.take_along_axis(valid, idx, 1)
        dsel = np.where(fin, dsel, np.inf)
    lsel = np.take_along_axis(lv, idx, 1)
    cnt = fin.sum(1)
    mean = np.where(cnt > 0, np.where(fin, lsel, 0).sum(1) / np.maximum(cnt, 1), np.nan)
    dyn = np.where(cnt > 0, dsel.min(1), np.nan)
    return cnt, mean, dyn


def evaluate(mode, W, K, R, pre):
    cnt, mean, dyn = run(mode, W, K, R, pre)
    m_ok = np.isclose(mean, s_mean, atol=5e-6, equal_nan=True)
    c_ok = cnt == s_cnt
    dd_ok = np.isclose(dyn, s_dist, atol=0.01, rtol=1e-3, equal_nan=True)
    ds_ok = np.isclose(dstat, s_dist, atol=0.01, rtol=1e-3, equal_nan=True)
    return {"mode": mode, "W_days": W, "K": K, "R_km": R, "pick": pre,
            "mean_ok": m_ok.mean(), "count_ok": c_ok.mean(),
            "dist_dyn_ok": dd_ok.mean(), "dist_static_ok": ds_ok.mean(),
            "all3": (m_ok & c_ok & (dd_ok | ds_ok)).mean()}


# Hint: radius ka andaza stored values se
pos = s_cnt > 0
print("\nRadius ka hint: max(stored doori | count>0) =", round(float(np.nanmax(s_dist[pos])), 2),
      "| min(stored doori | count==0) =",
      round(float(np.nanmin(s_dist[~pos])), 2) if (~pos).any() else "koi count==0 row nahi")

# Stage 1: mota grid
results = []
for mode, W, K, R, pre in itertools.product(
        modes, [None, 100, 130, 200, 400], [3, 5, 8, 10],
        [None, 15, 25, 40, 60, 100], ["valid_first", "nearest_first"]):
    results.append(evaluate(mode, W, K, R, pre))
res1 = pd.DataFrame(results).sort_values(["all3", "mean_ok"], ascending=False).reset_index(drop=True)
b1 = res1.iloc[0]
print("Stage 1 sabse achha:", dict(b1[["mode", "W_days", "K", "R_km", "pick"]]), "| all3 =", round(b1["all3"], 3))

# Stage 2: bareek grid (R har 1 km, W ke bahut se maan) usi mode aur K ke aas-paas
results2 = []
Ws = [None, 60, 80, 92, 100, 110, 120, 130, 140, 150, 160, 180, 200, 250, 300, 365, 400]
Rs = [None] + list(range(5, 151))
for W, R, pre in itertools.product(Ws, Rs, ["valid_first", "nearest_first"]):
    results2.append(evaluate(b1["mode"], W, int(b1["K"]), R, pre))
res = pd.concat([res1, pd.DataFrame(results2)]).drop_duplicates(
    subset=["mode", "W_days", "K", "R_km", "pick"]).sort_values(
    ["all3", "mean_ok"], ascending=False).reset_index(drop=True)
pd.set_option("display.width", 200)
print("\nTop 12 rules (rows ka fraction jahan stored values reproduce hue):")
print(res.head(12).round(3).to_string(index=False))
best = res.iloc[0]
print("\nSabse achha rule:", dict(best[["mode", "W_days", "K", "R_km", "pick"]]), "| all3 =", round(best["all3"], 3))
if best["all3"] >= 0.98:
    print(">>> RULE MIL GAYA (98% se zyada rows reproduce). Ye result mujhe bhejo.")
elif best["all3"] >= 0.6:
    print(">>> Kaafi paas hai par poora nahi. Top rules aur mismatch examples mujhe bhejo.")
else:
    print(">>> Koi rule match nahi hua. Generator ko reconstruct karna padega.")
if best["mode"] == "nearest_time_any" and best["all3"] > 0.5:
    print("!!! WARNING: sabse achha rule future readings bhi leta hai (leakage ka shak).")

cnt, mean, dyn = run(best["mode"], None if pd.isna(best["W_days"]) else int(best["W_days"]), int(best["K"]),
                     None if pd.isna(best["R_km"]) else float(best["R_km"]), best["pick"])
bad = np.where(~np.isclose(mean, s_mean, atol=5e-6, equal_nan=True) | (cnt != s_cnt))[0][:6]
print("\nMismatch ke examples (stored vs hamara):")
for b in bad:
    print(f"  {sites[si_r[b]]} {rows['DATE'].iloc[b].date()}: stored mean {s_mean[b]:.4f} cnt {s_cnt[b]} dist {s_dist[b]:.3f} | "
          f"hamara mean {mean[b]:.4f} cnt {cnt[b]} dyn {dyn[b]:.3f} static {dstat[b]:.3f}")
res.to_csv("data/processed/neighbor_rule_search.csv", index=False)
print("\nSaved: data/processed/neighbor_rule_search.csv")
