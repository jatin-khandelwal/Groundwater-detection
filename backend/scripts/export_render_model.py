from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np

from backend.app.config import MODEL_PATH


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "tmp" / "render_compact"


def export_model(model_path: Path = MODEL_PATH, output: Path = OUTPUT):
    pipeline = joblib.load(model_path)
    preprocessor = pipeline.named_steps["pre"]
    forest = pipeline.named_steps["model"]
    if not hasattr(forest, "estimators_") or not forest.estimators_:
        raise ValueError("Expected a fitted RandomForestRegressor in the frozen pipeline")

    output.mkdir(parents=True, exist_ok=True)
    joblib.dump(preprocessor, output / "preprocessor.joblib", compress=3)

    trees = [estimator.tree_ for estimator in forest.estimators_]
    offsets = np.zeros(len(trees) + 1, dtype=np.int64)
    for index, tree in enumerate(trees):
        offsets[index + 1] = offsets[index] + tree.node_count

    total = int(offsets[-1])
    left = np.empty(total, dtype=np.int32)
    right = np.empty(total, dtype=np.int32)
    feature = np.empty(total, dtype=np.int32)
    threshold = np.empty(total, dtype=np.float64)
    value = np.empty(total, dtype=np.float64)

    for index, tree in enumerate(trees):
        start, end = int(offsets[index]), int(offsets[index + 1])
        left[start:end] = tree.children_left
        right[start:end] = tree.children_right
        feature[start:end] = tree.feature
        threshold[start:end] = tree.threshold
        value[start:end] = tree.value[:, 0, 0]

    np.save(output / "tree_offsets.npy", offsets)
    np.save(output / "children_left.npy", left)
    np.save(output / "children_right.npy", right)
    np.save(output / "feature.npy", feature)
    np.save(output / "threshold.npy", threshold)
    np.save(output / "value.npy", value)
    (output / "manifest.json").write_text(
        json.dumps({"trees": len(trees), "nodes": total}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Exported {len(trees)} trees and {total:,} nodes to {output}")
    return pipeline


if __name__ == "__main__":
    export_model()
