"""Read-only comparison of row-date and request-time month-start cutoffs.

This only reads data/processed/dataset_v2_3.csv and prints diagnostics. It does
not update model files, datasets, or the preregistered 2024 holdout.
"""
import numpy as np
import pandas as pd
from pathlib import Path

P = Path("data/processed/dataset_v2_3.csv")
N, SEED, K, R = 3000, 0, 5, 40.0
cols = ["SITE_ID", "DATE", "LAT", "LON", "WLS_WTR_LEVEL", "YEAR", "ROUND"]
d = pd.read_csv(P, usecols=cols, dtype={"SITE_ID": str})
d["DATE"] = pd.to_datetime(d["DATE"])
# Keep the reserved 2024 Jan/May holdout outside the source arrays entirely.
d = d[d["DATE"] <= pd.Timestamp("2023-12-31")].copy()
d["t"] = (d["DATE"] - pd.Timestamp("1970-01-01")).dt.days.astype(int)
d["tm"] = (d["DATE"].dt.to_period("M").dt.to_timestamp() - pd.Timestamp("1970-01-01")).dt.days.astype(int)
d = d.sort_values(["SITE_ID", "t"]).reset_index(drop=True)
sites = d["SITE_ID"].unique()
d["si"] = d["SITE_ID"].map({s: i for i, s in enumerate(sites)})
n_st = len(sites)
coords = d.groupby("si")[["LAT", "LON"]].first().values
T = [g["t"].values for _, g in d.groupby("si")]
Lv = [g["WLS_WTR_LEVEL"].values for _, g in d.groupby("si")]

rows = d[d["YEAR"].between(2005, 2023)].sample(n=min(N, len(d)), random_state=SEED)
n = len(rows)
si_r = rows["si"].values
lat, lon = np.radians(coords[:, 0]), np.radians(coords[:, 1])
la, lo = lat[si_r][:, None], lon[si_r][:, None]
a = np.sin((lat[None, :] - la) / 2) ** 2 + np.cos(la) * np.cos(lat[None, :]) * np.sin((lon[None, :] - lo) / 2) ** 2
D = 2 * 6371.0088 * np.arcsin(np.sqrt(a))
D[np.arange(n), si_r] = np.inf
Dr = np.where(D <= R, D, np.inf)
idx = np.argpartition(Dr, K - 1, axis=1)[:, :K]
dsel = np.take_along_axis(Dr, idx, 1)
inr = np.isfinite(dsel)


def features(cut):
    """For each row, latest selected-station reading strictly before cutoff."""
    lv = np.full((n, n_st), np.nan)
    for j in range(n_st):
        k = np.searchsorted(T[j], cut, side="left") - 1
        ok = k >= 0
        lv[ok, j] = Lv[j][k[ok]]
    lsel = np.take_along_axis(lv, idx, 1)
    fin = inr & ~np.isnan(lsel)
    cnt = fin.sum(1)
    mean = np.where(cnt > 0, np.where(fin, lsel, 0).sum(1) / np.maximum(cnt, 1), np.nan)
    dist = np.where(cnt > 0, np.where(fin, dsel, np.inf).min(1), np.nan)
    return cnt, mean, dist


cA, mA, dA = features(rows["t"].values)   # exact observation date, reconstructed training rule
cB, mB, dB = features(rows["tm"].values)  # first day of target month, request-time rule
both = ~np.isnan(mA) & ~np.isnan(mB)
diff = np.abs(mA - mB)[both]
print(f"Rows checked: {n} (random sample from 2005-2023; source data capped at 2023-12-31)")
print(f"Count alag: {np.mean(cA != cB) * 100:.1f}% rows")
print(f"Mean alag (> 0.01 m): {np.mean(diff > 0.01) * 100:.1f}% of rows jahan dono ke paas value hai")
print(f"|mean diff| median {np.median(diff):.3f} m | p90 {np.percentile(diff, 90):.3f} | p99 {np.percentile(diff, 99):.3f} | max {diff.max():.3f}")
dd = np.abs(dA - dB)[both]
print(f"|distance diff| median {np.median(dd):.3f} km | p90 {np.percentile(dd, 90):.3f} | max {dd.max():.3f}")
print(f"Request-time (month start) par count 0 hua jabki exact-date par > 0 tha: {np.mean((cB == 0) & (cA > 0)) * 100:.1f}% rows")
print("\nRound ke hisaab se (count alag %):")
print(pd.Series(cA != cB, index=rows.index).groupby(rows["ROUND"]).mean().mul(100).round(1).to_string())
