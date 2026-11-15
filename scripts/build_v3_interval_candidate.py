"""Build a non-deployed interval-calibration candidate from train-only OOF data."""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import GroupKFold

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import model_utils as mu

FEATURES_PATH = ROOT / "models/v2/feature_list.json"
NEIGHBOR_PATH = ROOT / "data/processed/neighbor_v3.csv"
OUTPUT_PATH = ROOT / "docs/results/interval_v3_candidate.json"


def make_table(pred, residual):
    edges = np.quantile(pred, [0.2, 0.4, 0.6, 0.8]).tolist()
    bins = np.searchsorted(edges, pred, side="left")
    low, high = [], []
    for index in range(5):
        values = residual[bins == index]
        if not len(values):
            raise ValueError(f"Calibration bin {index} is empty")
        low.append(float(np.quantile(values, 0.1)))
        high.append(float(np.quantile(values, 0.9)))
    return edges, low, high


def intervals(pred, edges, low, high):
    bins = np.searchsorted(edges, pred, side="left")
    return pred + np.asarray(low)[bins], pred + np.asarray(high)[bins]


def main():
    features = json.loads(FEATURES_PATH.read_text(encoding="utf-8"))
    d = mu.load_data().reset_index(drop=True)
    nb = pd.read_csv(NEIGHBOR_PATH, dtype={"SITE_ID": str}, low_memory=False)
    d["SITE_ID"] = d["SITE_ID"].astype(str)
    d["DATE"] = d["DATE"].astype(str)
    nb["SITE_ID"] = nb["SITE_ID"].astype(str)
    nb["DATE"] = nb["DATE"].astype(str)
    if nb.duplicated(["SITE_ID", "DATE"]).any():
        raise ValueError("neighbor_v3 has duplicate station/date keys")
    d = d.merge(nb, on=["SITE_ID", "DATE"], how="left", validate="one_to_one")
    d["neighbor_prev_level_mean_5_m"] = d["nb3_prev_level_mean_5_m"]
    d["neighbor_prev_level_count_5"] = d["nb3_prev_level_count_5"]
    d["nearest_neighbor_prev_distance_km"] = d["nb3_nearest_dist_km"]
    train = d[d["SPLIT"].eq("train")].copy().reset_index(drop=True)
    if train.empty or train["YEAR"].max() > 2020:
        raise ValueError("Expected only pre-validation train rows through 2020")
    X, y = train[features], train[mu.TARGET].to_numpy(float)
    groups = train["SITE_ID"].astype(str).to_numpy()
    cv = GroupKFold(n_splits=5)
    oof = np.full(len(train), np.nan)
    fold_ids = np.full(len(train), -1, dtype=int)
    fold_coverages, fold_widths, fold_sizes = [], [], []
    params = {"n_estimators": 100, "min_samples_leaf": 1, "max_features": 0.4,
              "max_depth": 20, "random_state": 42, "n_jobs": -1}

    for fold, (fit_idx, hold_idx) in enumerate(cv.split(X, y, groups), start=1):
        pipe = mu.make_pipeline(RandomForestRegressor(**params), features, train)
        pipe.fit(X.iloc[fit_idx], y[fit_idx])
        oof[hold_idx] = pipe.predict(X.iloc[hold_idx])
        fold_ids[hold_idx] = fold
        print(f"Fold {fold}/5 OOF predictions complete", flush=True)

    if np.isnan(oof).any() or np.any(fold_ids < 0):
        raise ValueError("OOF predictions incomplete")
    for fold in range(1, 6):
        hold_idx = np.flatnonzero(fold_ids == fold)
        cal_idx = np.flatnonzero(fold_ids != fold)
        edges, low, high = make_table(oof[cal_idx], y[cal_idx] - oof[cal_idx])
        lower, upper = intervals(oof[hold_idx], edges, low, high)
        fold_coverages.append(float(np.mean((y[hold_idx] >= lower) & (y[hold_idx] <= upper))))
        fold_widths.append(float(np.mean(upper - lower)))
        fold_sizes.append(len(hold_idx))
        print(f"Fold {fold}/5 calibration cross-check complete; coverage={fold_coverages[-1]:.3f}", flush=True)
    edges, low, high = make_table(oof, y - oof)
    output = {
        "status": "candidate_only_not_deployed",
        "method": "Five-bin predicted-level residual calibration; 10th/90th residual quantiles; GroupKFold(5) by SITE_ID on SPLIT=train rows only; v3 neighbor inputs.",
        "train_rows": int(len(train)),
        "train_years": [int(train["YEAR"].min()), int(train["YEAR"].max())],
        "unique_sites": int(train["SITE_ID"].nunique()),
        "model_params": params,
        "scikit_learn_version": sklearn.__version__,
        "features": features,
        "edges": [float(x) for x in edges],
        "res_low": low,
        "res_high": high,
        "oof_mae_m": round(float(np.mean(np.abs(y - oof))), 3),
        "crossfit_coverage_mean": round(float(np.mean(fold_coverages)), 4),
        "crossfit_coverage_pooled": round(float(np.average(fold_coverages, weights=fold_sizes)), 4),
        "crossfit_coverage_by_fold": [round(value, 4) for value in fold_coverages],
        "crossfit_mean_width_m_by_fold": [round(value, 3) for value in fold_widths],
        "warning": "This candidate was built after the frozen model was packaged and under the current environment version. It has not been independently checked against the deployed artifact version or calibrated on an untouched interval-calibration set. Do not replace models/v2/interval_table.json until reviewed.",
        "holdout_2024_used": False,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2))
    print(f"Saved candidate only: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
