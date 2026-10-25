"""
model_utils.py   (Role 2 ke liye common functions, notebooks se import karo)

Notebook ke pehle cell mein:
    import os, sys
    os.chdir(r"C:\\Ground water")
    sys.path.append(r"C:\\Ground water\\scripts")
    import model_utils as mu

Kya milta hai:
    mu.load_data(exclude_qc=False)        dataset_v2_3 + QC flags
    mu.split(d)                           train, val, test
    mu.cols_for(groups, ["baseline", ...])   feature columns ki list
    mu.make_pipeline(model, X_cols, d)    missing + categorical ek hi pipeline mein
    mu.scores(y, pred)                    n, R2, MAE, MedAE
    mu.persistence_scores(part)           lag_1 ko hi prediction maano
    mu.eval_same_rows(pipe, part, X_cols) model ko 'all rows' aur 'persistence wali rows' par
    mu.fit_final(make_model, X_cols, d)   train + val par final fit (test ko chhoo mat)
"""
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, median_absolute_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

P = Path("data/processed")
DATA = P / "dataset_v2_3.csv"
GROUPS = P / "feature_groups_v2_3.json"
QC = P / "qc_flags_v2_3.csv"
TARGET = "WLS_WTR_LEVEL"
LAG = "water_level_lag_1_obs_m"
NEVER = {"WELL_DEPTH", "LEVEL_DIFF", "OUTLIER", TARGET}   # kabhi feature nahi


def load_data(exclude_qc: bool = False) -> pd.DataFrame:
    d = pd.read_csv(DATA, dtype={"SITE_ID": str}, low_memory=False)
    d["DATE"] = d["DATE"].astype(str)
    if QC.exists():
        q = pd.read_csv(QC, dtype={"SITE_ID": str})
        q["DATE"] = q["DATE"].astype(str)
        d = d.merge(q, on=["SITE_ID", "DATE"], how="left")
        for c in [c for c in q.columns if c.startswith("QC_")]:
            d[c] = d[c].fillna(False).astype(bool)
    else:
        warnings.warn("qc_flags_v2_3.csv nahi mili. Pehle qc_flags.py chalao. Abhi QC_ANY = False maana ja raha hai.")
        d["QC_ANY"] = False
    if "SPLIT" not in d.columns:
        d["SPLIT"] = "unused"
        ok = d["YEAR"].between(2005, 2023)
        d.loc[ok & (d["YEAR"] <= 2020), "SPLIT"] = "train"
        d.loc[ok & (d["YEAR"] == 2021), "SPLIT"] = "val"
        d.loc[ok & (d["YEAR"] > 2021), "SPLIT"] = "test"
    if exclude_qc:
        d = d[~d["QC_ANY"]].copy()
    return d


def split(d: pd.DataFrame):
    return (d[d["SPLIT"] == "train"].copy(), d[d["SPLIT"] == "val"].copy(),
            d[d["SPLIT"] == "test"].copy())


def load_groups() -> dict:
    return json.loads(GROUPS.read_text(encoding="utf-8"))


def cols_for(groups: dict, names: list) -> list:
    """Group ke naam do, columns ki list milti hai (duplicate hata ke)."""
    out = []
    for n in names:
        if n not in groups:
            raise KeyError(f"Group '{n}' nahi mila. Available: {list(groups.keys())}")
        v = groups[n]
        if not isinstance(v, list):
            raise TypeError(f"Group '{n}' list nahi hai (type {type(v).__name__})")
        for c in v:
            if c in NEVER:
                raise ValueError(f"'{c}' kabhi feature nahi ho sakta (group '{n}' mein hai)")
            if c not in out:
                out.append(c)
    return out


def make_pipeline(model, X_cols: list, d: pd.DataFrame) -> Pipeline:
    """Numeric: median fill + 'missing tha' indicator. Text: 'Unknown' + one-hot (naye category ignore)."""
    cat = [c for c in X_cols if not pd.api.types.is_numeric_dtype(d[c])]   # text columns
    num = [c for c in X_cols if c not in cat]
    parts = []
    if num:
        parts.append(("num", SimpleImputer(strategy="median", add_indicator=True), num))
    if cat:
        parts.append(("cat", Pipeline([
            ("imp", SimpleImputer(strategy="constant", fill_value="Unknown")),
            ("oh", OneHotEncoder(handle_unknown="ignore", min_frequency=20, sparse_output=False)),
        ]), cat))
    return Pipeline([("pre", ColumnTransformer(parts, remainder="drop")), ("model", model)])


def scores(y, pred) -> dict:
    y, pred = np.asarray(y, float), np.asarray(pred, float)
    return {"n": int(len(y)), "R2": round(float(r2_score(y, pred)), 4),
            "MAE": round(float(mean_absolute_error(y, pred)), 3),
            "MedAE": round(float(median_absolute_error(y, pred)), 3)}


def persistence_scores(part: pd.DataFrame) -> dict:
    """lag_1 ko hi prediction maano. NaN lag wali rows gir jaati hain, unka % bhi batata hai."""
    ok = part[LAG].notna()
    res = scores(part.loc[ok, TARGET], part.loc[ok, LAG])
    res["rows_dropped_lag_nan"] = int((~ok).sum())
    res["dropped_pct"] = round(float((~ok).mean() * 100), 2)
    return res


def eval_same_rows(pipe: Pipeline, part: pd.DataFrame, X_cols: list) -> dict:
    """Model ka score: (a) saari rows par, (b) sirf unhi rows par jahan persistence chal sakta hai.
    Persistence se compare hamesha (b) par karo."""
    pred = pipe.predict(part[X_cols])
    ok = part[LAG].notna().values
    return {"all_rows": scores(part[TARGET], pred),
            "persistence_rows": scores(part.loc[ok, TARGET], pred[ok])}


def fit_final(make_model, X_cols: list, d: pd.DataFrame) -> Pipeline:
    """Hyperparameters tay hone ke BAAD: train + val (2005-2021) par fit. Test ko chhoo mat."""
    fit_part = d[d["SPLIT"].isin(["train", "val"])]
    pipe = make_pipeline(make_model(), X_cols, d)
    pipe.fit(fit_part[X_cols], fit_part[TARGET])
    return pipe
