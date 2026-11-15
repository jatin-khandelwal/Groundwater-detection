"""Read-only sensitivity check: frozen v2 predictions under two neighbor cutoffs.

Uses a deterministic 3,000-row 2005-2023 sample. Source observations are capped
at 2023-12-31 so the preregistered 2024 Jan/May holdout is not loaded into the
neighbor-reading arrays. This does not score accuracy, tune, or retrain a model.
"""
import json
import joblib
import numpy as np
import pandas as pd
from pathlib import Path

DATA = Path("data/processed/dataset_v2_3.csv")
MODEL_PATH = Path("models/v2/model.pkl")
FEATURES_PATH = Path("models/v2/feature_list.json")
N, SEED, K, RADIUS_KM = 3000, 0, 5, 40.0
cols = ["SITE_ID", "DATE", "DISTRICT_NAME", "LAT", "LON", "WLS_WTR_LEVEL",
        "YEAR", "MONTH", "ROUND", "elevation_m"]
d = pd.read_csv(DATA, usecols=cols, dtype={"SITE_ID": str})
d["DATE"] = pd.to_datetime(d["DATE"])
d = d[d["DATE"] <= pd.Timestamp("2023-12-31")].copy()
d["t"] = (d["DATE"] - pd.Timestamp("1970-01-01")).dt.days.astype(int)
d["tm"] = (d["DATE"].dt.to_period("M").dt.to_timestamp() - pd.Timestamp("1970-01-01")).dt.days.astype(int)
d = d.sort_values(["SITE_ID", "t"]).reset_index(drop=True)
sites = d["SITE_ID"].unique()
d["si"] = d["SITE_ID"].map({s: i for i, s in enumerate(sites)})
n_st = len(sites)
coords = d.groupby("si")[["LAT", "LON"]].first().values
times = [g["t"].values for _, g in d.groupby("si")]
levels = [g["WLS_WTR_LEVEL"].values for _, g in d.groupby("si")]
rows = d[d["YEAR"].between(2005, 2023)].sample(n=min(N, len(d)), random_state=SEED)
n = len(rows)

lat, lon = np.radians(coords[:, 0]), np.radians(coords[:, 1])
la, lo = lat[rows["si"].values][:, None], lon[rows["si"].values][:, None]
a = np.sin((lat[None, :] - la) / 2) ** 2 + np.cos(la) * np.cos(lat[None, :]) * np.sin((lon[None, :] - lo) / 2) ** 2
distances = 2 * 6371.0088 * np.arcsin(np.sqrt(a))
distances[np.arange(n), rows["si"].values] = np.inf
distances = np.where(distances <= RADIUS_KM, distances, np.inf)
idx = np.argpartition(distances, K - 1, axis=1)[:, :K]
selected_distances = np.take_along_axis(distances, idx, axis=1)
within_radius = np.isfinite(selected_distances)


def neighbor_features(cutoffs):
    available = np.full((n, n_st), np.nan)
    for j in range(n_st):
        ix = np.searchsorted(times[j], cutoffs, side="left") - 1
        valid = ix >= 0
        available[valid, j] = levels[j][ix[valid]]
    selected = np.take_along_axis(available, idx, axis=1)
    contributes = within_radius & ~np.isnan(selected)
    count = contributes.sum(axis=1)
    mean = np.where(count > 0, np.where(contributes, selected, 0).sum(axis=1) / np.maximum(count, 1), np.nan)
    nearest = np.where(count > 0, np.where(contributes, selected_distances, np.inf).min(axis=1), np.nan)
    return mean, nearest, count


mean_exact, distance_exact, count_exact = neighbor_features(rows["t"].values)
mean_month, distance_month, count_month = neighbor_features(rows["tm"].values)
months = rows["MONTH"].astype(float).values
base = {
    "DISTRICT_NAME": rows["DISTRICT_NAME"].values,
    "LAT": rows["LAT"].values,
    "LON": rows["LON"].values,
    "YEAR": rows["YEAR"].values,
    "month_sin": np.sin(2 * np.pi * months / 12),
    "month_cos": np.cos(2 * np.pi * months / 12),
    "elevation_m": rows["elevation_m"].values,
}
features_exact = pd.DataFrame({**base,
    "neighbor_prev_level_mean_5_m": mean_exact,
    "nearest_neighbor_prev_distance_km": distance_exact,
    "neighbor_prev_level_count_5": count_exact,
})
features_month = pd.DataFrame({**base,
    "neighbor_prev_level_mean_5_m": mean_month,
    "nearest_neighbor_prev_distance_km": distance_month,
    "neighbor_prev_level_count_5": count_month,
})
feature_names = json.loads(FEATURES_PATH.read_text(encoding="utf-8"))
features_exact = features_exact[feature_names]
features_month = features_month[feature_names]
model = joblib.load(MODEL_PATH)
pred_exact = model.predict(features_exact)
pred_month = model.predict(features_month)
delta = np.abs(pred_exact - pred_month)
print(f"Rows compared: {n} (random 2005-2023 sample; source capped at 2023-12-31)")
print("Frozen model only; this is paired prediction sensitivity, not an accuracy evaluation.")
print(f"|delta prediction| median {np.median(delta):.3f} m | p90 {np.percentile(delta,90):.3f} | p95 {np.percentile(delta,95):.3f} | p99 {np.percentile(delta,99):.3f} | max {np.max(delta):.3f}")
for threshold in (0.1, 1.0, 3.7):
    print(f"Rows with |delta prediction| > {threshold:g} m: {np.mean(delta > threshold) * 100:.1f}%")
print(f"Mean signed prediction change (month-start minus exact-date): {np.mean(pred_month - pred_exact):.3f} m")
print(f"Rows with no contributing neighbors under either cutoff: {np.mean((count_exact == 0) & (count_month == 0)) * 100:.1f}%")
