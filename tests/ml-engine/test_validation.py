from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from crypto_signal.config import ModelConfig
from crypto_signal.model import walk_forward_validation


class ValidationTests(unittest.TestCase):
    def test_walk_forward_gap_is_respected(self) -> None:
        rng = np.random.default_rng(7)
        X = pd.DataFrame(rng.normal(size=(360, 4)), columns=list("abcd"))
        y = pd.Series(np.resize(np.array([-1, 0, 1]), len(X)))
        config = ModelConfig(
            test_fraction=0.2,
            cv_splits=3,
            probability_threshold=0.5,
            random_state=42,
            max_iter=10,
            learning_rate=0.1,
            max_leaf_nodes=7,
            min_samples_leaf=10,
            l2_regularization=1.0,
        )
        gap = 6
        results = walk_forward_validation(X, y, config, gap=gap)
        for fold in results["folds"]:
            self.assertGreaterEqual(
                fold["validation_start"] - fold["train_end"] - 1,
                gap,
            )


if __name__ == "__main__":
    unittest.main()

