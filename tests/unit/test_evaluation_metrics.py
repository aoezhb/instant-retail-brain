from __future__ import annotations

import unittest

from ird.evaluation import mae, quantile_coverage, rmse, summarize_forecast_metrics, wape


class EvaluationMetricTests(unittest.TestCase):
    def test_forecast_metrics(self) -> None:
        self.assertEqual(mae([1, 3], [2, 1]), 1.5)
        self.assertEqual(rmse([1, 3], [2, 1]), 1.5811)
        self.assertEqual(wape([1, 3], [2, 1]), 0.75)
        self.assertEqual(quantile_coverage([1, 3], [2, 4]), 1.0)
        self.assertEqual(summarize_forecast_metrics([1], [2], [2], [3])["p50_coverage"], 1.0)

    def test_forecast_metrics_reject_misaligned_inputs(self) -> None:
        with self.assertRaisesRegex(ValueError, "same length"):
            mae([1, 2], [1])
        with self.assertRaisesRegex(ValueError, "same length"):
            quantile_coverage([1], [1, 2])


if __name__ == "__main__":
    unittest.main()
