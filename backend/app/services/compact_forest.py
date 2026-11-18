from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np


class CompactForest:
    """Run the frozen forest from memory-mapped tree arrays."""

    def __init__(self, preprocessor: Any, directory: Path) -> None:
        self.preprocessor = preprocessor
        self.offsets = np.load(directory / "tree_offsets.npy", mmap_mode="r")
        self.left = np.load(directory / "children_left.npy", mmap_mode="r")
        self.right = np.load(directory / "children_right.npy", mmap_mode="r")
        self.feature = np.load(directory / "feature.npy", mmap_mode="r")
        self.threshold = np.load(directory / "threshold.npy", mmap_mode="r")
        self.value = np.load(directory / "value.npy", mmap_mode="r")

    def predict(self, frame: Any) -> np.ndarray:
        matrix = np.asarray(self.preprocessor.transform(frame), dtype=np.float64)
        if matrix.ndim != 2:
            raise ValueError("Preprocessor must return a two-dimensional matrix")

        row_ids = np.arange(matrix.shape[0])
        predictions = np.zeros(matrix.shape[0], dtype=np.float64)
        tree_count = len(self.offsets) - 1

        for tree_index in range(tree_count):
            start = int(self.offsets[tree_index])
            end = int(self.offsets[tree_index + 1])
            nodes = np.zeros(matrix.shape[0], dtype=np.int64)
            active = np.ones(matrix.shape[0], dtype=bool)

            while active.any():
                active_rows = row_ids[active]
                global_nodes = start + nodes[active]
                left_nodes = self.left[global_nodes]
                leaf = left_nodes < 0

                if leaf.any():
                    leaf_rows = active_rows[leaf]
                    predictions[leaf_rows] += self.value[global_nodes[leaf]]
                    active[leaf_rows] = False

                branch = ~leaf
                if branch.any():
                    branch_rows = active_rows[branch]
                    branch_nodes = global_nodes[branch]
                    feature_ids = self.feature[branch_nodes]
                    go_left = matrix[branch_rows, feature_ids] <= self.threshold[branch_nodes]
                    next_nodes = np.where(go_left, left_nodes[branch], self.right[branch_nodes])
                    nodes[branch_rows] = next_nodes

            if end <= start:
                raise ValueError("Compact forest contains an empty tree")

        return predictions / tree_count
