from __future__ import annotations

import json
import pickle
from pathlib import Path
from typing import Any

import pandas as pd

from ..config import FEATURE_LIST_PATH, INTERVAL_PATH, METRICS_PATH, MODEL_PATH


class ModelService:
    """Load the frozen v2 artifact once; never silently substitute a dummy model."""

    def __init__(self) -> None:
        self.model: Any | None = None
        self.features: list[str] = []
        self.metrics: dict[str, Any] = {}
        self.interval: dict[str, Any] = {}
        self.error: str | None = None

    @property
    def loaded(self) -> bool:
        return self.model is not None

    def load(self) -> None:
        try:
            if not MODEL_PATH.is_file():
                raise FileNotFoundError(f"Frozen model file missing: {MODEL_PATH}")
            self.features = json.loads(FEATURE_LIST_PATH.read_text(encoding="utf-8"))
            if not self.features:
                raise ValueError("feature_list.json is empty")
            try:
                import joblib

                self.model = joblib.load(MODEL_PATH)
            except Exception as joblib_error:
                try:
                    with MODEL_PATH.open("rb") as handle:
                        self.model = pickle.load(handle)
                except Exception:
                    raise RuntimeError(f"Model load failed (joblib: {joblib_error})") from joblib_error
            self.metrics = json.loads(METRICS_PATH.read_text(encoding="utf-8")) if METRICS_PATH.exists() else {}
            self.interval = json.loads(INTERVAL_PATH.read_text(encoding="utf-8")) if INTERVAL_PATH.exists() else {}
            self.error = None
        except Exception as exc:
            self.model = None
            self.error = f"{type(exc).__name__}: {exc}"

    def predict(self, values: dict[str, Any]) -> float:
        if self.model is None:
            raise RuntimeError(self.error or "Frozen model is unavailable")
        missing = [name for name in self.features if name not in values]
        if missing:
            raise ValueError(f"Required model features missing: {missing}")
        frame = pd.DataFrame([{name: values[name] for name in self.features}], columns=self.features)
        result = self.model.predict(frame)
        return float(result[0])

    def prediction_interval(self, prediction_m: float) -> dict[str, float | str | bool]:
        """Apply the saved 80% residual table, clearly marked as historical calibration."""
        edges = self.interval.get("edges", [])
        lows = self.interval.get("res_low", [])
        highs = self.interval.get("res_high", [])
        if not edges or len(lows) != len(edges) + 1 or len(highs) != len(edges) + 1:
            return {"lower_m": prediction_m, "upper_m": prediction_m, "width_m": 0.0,
                    "confidence": "low", "calibration_status": "unavailable"}
        bin_index = sum(prediction_m > edge for edge in edges)
        lower = prediction_m + float(lows[bin_index])
        upper = prediction_m + float(highs[bin_index])
        width = max(0.0, upper - lower)
        confidence = "high" if width < 15 else "medium" if width <= 30 else "low"
        return {"lower_m": round(lower, 2), "upper_m": round(upper, 2),
                "width_m": round(width, 2), "confidence": confidence,
                "calibration_status": "historical_neighbor_inputs; not recalibrated for neighbor_v3"}
