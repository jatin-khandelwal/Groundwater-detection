"""One-time scoring of the pre-registered 2024 January/May holdout.

Reads target rows from dataset_v2_neighbors.csv and builds neighbor inputs using
only source readings from dataset_v2_3.csv through 2023-12-31. It never fits or
changes the frozen model and does not write to the demo database.
"""
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

ROOT = Path(__file__).resolve().parents[1]
TARGET_PATH = ROOT / "data/processed/dataset_v2_neighbors.csv"
SOURCE_PATH = ROOT / "data/processed/dataset_v2_3.csv"
MODEL_PATH = ROOT / "models/v2/model.pkl"
FEATURES_PATH = ROOT / "models/v2/feature_list.json"
OUTPUT_PATH = ROOT / "docs/results/holdout_2024_jan_may_v3.json"
RADIUS_KM = 40.0
K = 5
SOURCE_CUTOFF = pd.Timestamp("2023-12-31")


def haversine_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371.0088 * np.arcsin(np.sqrt(a))


def score(y, pred):
    if len(y) == 0:
        return {"n": 0, "MAE_m": None, "RMSE_m": None, "R2": None}
    return {
        "n": int(len(y)),
        "MAE_m": round(float(mean_absolute_error(y, pred)), 3),
        "RMSE_m": round(float(np.sqrt(mean_squared_error(y, pred))), 3),
        "R2": round(float(r2_score(y, pred)), 4) if len(y) > 1 else None,
    }


def main():
    target = pd.read_csv(TARGET_PATH, dtype={"SITE_ID": str}, low_memory=False)
    target["DATE"] = pd.to_datetime(target["DATE"])
    target = target[target["DATE"].dt.year.eq(2024) & target["DATE"].dt.month.isin([1, 5])].copy()
    counts = target["DATE"].dt.month.value_counts().to_dict()
    if len(target) != 742 or counts != {1: 668, 5: 74}:
        raise ValueError(f"Registered holdout rows do not match expected 742 (668 Jan, 74 May): n={len(target)}, months={counts}")

    source = pd.read_csv(
        SOURCE_PATH,
        usecols=["SITE_ID", "DATE", "LAT", "LON", "WLS_WTR_LEVEL"],
        dtype={"SITE_ID": str}, low_memory=False,
    )
    source["DATE"] = pd.to_datetime(source["DATE"])
    source = source[source["DATE"].le(SOURCE_CUTOFF)].dropna(
        subset=["SITE_ID", "LAT", "LON", "WLS_WTR_LEVEL"]
    ).copy()
    station = source.groupby("SITE_ID", sort=False).agg(LAT=("LAT", "first"), LON=("LON", "first"))
    station_ids = station.index.to_numpy()
    station_lat = station["LAT"].to_numpy(float)
    station_lon = station["LON"].to_numpy(float)
    readings = {
        site_id: (group["DATE"].to_numpy(dtype="datetime64[ns]"), group["WLS_WTR_LEVEL"].to_numpy(float))
        for site_id, group in source.sort_values("DATE").groupby("SITE_ID", sort=False)
    }

    means = np.full(len(target), np.nan)
    counts_used = np.zeros(len(target), dtype=int)
    nearest = np.full(len(target), np.nan)
    target_lats = target["LAT"].to_numpy(float)
    target_lons = target["LON"].to_numpy(float)
    target_dates = target["DATE"].to_numpy(dtype="datetime64[ns]")
    target_ids = target["SITE_ID"].astype(str).to_numpy()

    for i in range(len(target)):
        distance = haversine_km(target_lats[i], target_lons[i], station_lat, station_lon)
        eligible = np.isfinite(distance) & (distance <= RADIUS_KM) & (station_ids != target_ids[i])
        candidates = np.flatnonzero(eligible)
        if not len(candidates):
            continue
        candidates = candidates[np.argsort(distance[candidates], kind="stable")[:K]]
        values, distances = [], []
        for j in candidates:
            dates, levels = readings[station_ids[j]]
            pos = np.searchsorted(dates, target_dates[i], side="left") - 1
            if pos >= 0:
                values.append(levels[pos])
                distances.append(distance[j])
        if values:
            means[i] = float(np.mean(values))
            counts_used[i] = len(values)
            nearest[i] = float(np.min(distances))

    feature_names = json.loads(FEATURES_PATH.read_text(encoding="utf-8"))
    required = ["DISTRICT_NAME", "LAT", "LON", "YEAR", "MONTH", "elevation_m", "WLS_WTR_LEVEL"]
    missing = [name for name in required if name not in target.columns]
    if missing:
        raise ValueError(f"Holdout is missing required columns: {missing}")
    target["month_sin"] = np.sin(2 * np.pi * target["MONTH"].to_numpy(float) / 12)
    target["month_cos"] = np.cos(2 * np.pi * target["MONTH"].to_numpy(float) / 12)
    target["neighbor_prev_level_mean_5_m"] = means
    target["neighbor_prev_level_count_5"] = counts_used
    target["nearest_neighbor_prev_distance_km"] = nearest
    X = target[feature_names]
    y = target["WLS_WTR_LEVEL"].to_numpy(float)
    model = joblib.load(MODEL_PATH)
    prediction = model.predict(X)

    training = pd.read_csv(SOURCE_PATH, usecols=["SITE_ID", "YEAR", "SPLIT"], dtype={"SITE_ID": str})
    seen_sites = set(training.loc[training["SPLIT"].isin(["train", "val"]), "SITE_ID"].astype(str))
    seen = target["SITE_ID"].astype(str).isin(seen_sites).to_numpy()
    result = {
        "evaluation_date": pd.Timestamp.now().date().isoformat(),
        "protocol": "Pre-registered 2024 Jan/May single evaluation; frozen v2, no fitting/tuning; v3 K=5 nearest other stations within inclusive 40 km, latest reading strictly before exact target date; source readings capped 2023-12-31.",
        "holdout_rows": {"total": int(len(target)), "january": int(counts[1]), "may": int(counts[5])},
        "source_rows": {"through": SOURCE_CUTOFF.date().isoformat(), "stations": int(len(station_ids))},
        "neighbor_features": {
            "zero_count_rows": int(np.sum(counts_used == 0)),
            "mean_count": round(float(np.mean(counts_used)), 3),
            "count_distribution": {str(int(k)): int(v) for k, v in zip(*np.unique(counts_used, return_counts=True))},
        },
        "all_holdout": score(y, prediction),
        "seen_training_stations": score(y[seen], prediction[seen]),
        "unseen_stations": score(y[~seen], prediction[~seen]),
        "monthly": {
            str(month): score(y[target["MONTH"].to_numpy() == month], prediction[target["MONTH"].to_numpy() == month])
            for month in (1, 5)
        },
        "features": feature_names,
        "holdout_used_for_tuning_or_model_changes": False,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    print(f"Saved: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
