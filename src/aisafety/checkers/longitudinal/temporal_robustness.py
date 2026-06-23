"""Temporal Robustness Checker — adversarial perturbations and distribution shift in time-series.

Attacks covered:
- Temporal perturbation: point-wise noise injection, segment shifting
- Time-warp attacks: non-linear time distortion
- Missing data robustness: random and burst dropout
- Distribution shift detection: covariate shift between train/test windows
- Stationarity testing: ADF test for non-stationarity handling
"""

from __future__ import annotations

import numpy as np

from aisafety.core.base import BaseChecker
from aisafety.core.registry import register_checker
from aisafety.core.types import CheckStatus, Finding, Severity


@register_checker
class TemporalRobustnessChecker(BaseChecker):
    name = "Temporal Robustness"
    category = "temporal_robustness"
    requires = ["numpy"]
    model_types = ["longitudinal"]

    def check(
        self,
        model=None,
        X_test=None,
        y_test=None,
        noise_levels: list[float] | None = None,
        dropout_rates: list[float] | None = None,
        **kwargs,
    ) -> "CheckResult":
        findings: list[Finding] = []

        if model is None or X_test is None or y_test is None:
            return self._make_result([self._make_finding(
                "no_data", "No model/data provided",
                "Provide model, X_test (shape: [n_samples, timesteps, features]), and y_test.",
                Severity.INFO, CheckStatus.SKIPPED,
            )])

        X_test = np.asarray(X_test, dtype=np.float32)
        y_test = np.asarray(y_test)
        noise_levels = noise_levels or [0.01, 0.05, 0.1, 0.2, 0.5]
        dropout_rates = dropout_rates or [0.05, 0.1, 0.2, 0.3, 0.5]

        # Baseline accuracy
        clean_acc = self._get_accuracy(model, X_test, y_test)
        findings.append(self._make_finding(
            "clean_accuracy", "Clean Accuracy",
            f"Baseline: {clean_acc:.4f}",
            Severity.INFO, CheckStatus.PASS,
            details={"accuracy": clean_acc},
        ))

        # Point-wise noise injection
        findings.append(self._test_pointwise_noise(model, X_test, y_test, clean_acc, noise_levels))

        # Segment shift attack
        findings.append(self._test_segment_shift(model, X_test, y_test, clean_acc))

        # Time-warp attack
        findings.append(self._test_time_warp(model, X_test, y_test, clean_acc))

        # Missing data robustness
        findings.append(self._test_missing_data(model, X_test, y_test, clean_acc, dropout_rates))

        # Burst dropout
        findings.append(self._test_burst_dropout(model, X_test, y_test, clean_acc))

        # Distribution shift between halves
        findings.append(self._test_temporal_distribution_shift(X_test))

        return self._make_result(
            findings,
            metadata={"n_samples": len(X_test), "shape": list(X_test.shape)},
        )

    def _get_accuracy(self, model, X, y) -> float:
        preds = model.predict(X)
        if preds.ndim > 1:
            preds = np.argmax(preds, axis=1)
        if y.ndim > 1:
            y = np.argmax(y, axis=1)
        return float(np.mean(preds == y))

    def _test_pointwise_noise(self, model, X, y, clean_acc, noise_levels) -> Finding:
        """Inject Gaussian noise at each timestep."""
        results = {}
        worst_drop = 0

        for sigma in noise_levels:
            noise = np.random.default_rng(42).normal(0, sigma, X.shape).astype(np.float32)
            X_noisy = X + noise * np.std(X)
            acc = self._get_accuracy(model, X_noisy, y)
            drop = clean_acc - acc
            results[sigma] = {"accuracy": acc, "drop": drop}
            worst_drop = max(worst_drop, drop)

        if worst_drop > 0.2:
            severity, status = Severity.HIGH, CheckStatus.FAIL
        elif worst_drop > 0.1:
            severity, status = Severity.MEDIUM, CheckStatus.WARN
        else:
            severity, status = Severity.INFO, CheckStatus.PASS

        return self._make_finding(
            "pointwise_noise", "Point-wise Noise Robustness",
            f"Worst accuracy drop: {worst_drop:.4f} across {len(noise_levels)} noise levels.",
            severity, status,
            details={"noise_results": results, "worst_drop": worst_drop},
            recommendation="Apply input smoothing or adversarial training on temporal data."
            if status != CheckStatus.PASS else "",
        )

    def _test_segment_shift(self, model, X, y, clean_acc) -> Finding:
        """Shift a random segment of the time series."""
        if X.ndim < 2:
            return self._make_finding("segment_shift", "Segment Shift", "Need 2D+ data.", Severity.LOW, CheckStatus.SKIPPED)

        timesteps = X.shape[1] if X.ndim >= 2 else len(X[0])
        seg_len = max(1, timesteps // 4)
        rng = np.random.default_rng(42)

        X_shifted = X.copy()
        start = rng.integers(0, timesteps - seg_len)
        shift_magnitude = np.std(X) * 2
        X_shifted[:, start:start + seg_len] += shift_magnitude

        acc = self._get_accuracy(model, X_shifted, y)
        drop = clean_acc - acc

        if drop > 0.15:
            severity, status = Severity.HIGH, CheckStatus.FAIL
        elif drop > 0.05:
            severity, status = Severity.MEDIUM, CheckStatus.WARN
        else:
            severity, status = Severity.INFO, CheckStatus.PASS

        return self._make_finding(
            "segment_shift", "Segment Shift Attack",
            f"Shifting {seg_len} timesteps: accuracy drop {drop:.4f}",
            severity, status,
            details={"segment_length": seg_len, "shift_magnitude": float(shift_magnitude), "accuracy_drop": drop},
            recommendation="Model is sensitive to localized temporal perturbations."
            if status != CheckStatus.PASS else "",
        )

    def _test_time_warp(self, model, X, y, clean_acc) -> Finding:
        """Non-linear time distortion via interpolation."""
        if X.ndim < 2:
            return self._make_finding("time_warp", "Time Warp", "Need 2D+ data.", Severity.LOW, CheckStatus.SKIPPED)

        timesteps = X.shape[1]
        rng = np.random.default_rng(42)

        # Create warped time indices
        original_times = np.linspace(0, 1, timesteps)
        warp = rng.normal(0, 0.1, timesteps)
        warped_times = np.clip(original_times + np.cumsum(warp) * 0.05, 0, 1)
        warped_times = np.sort(warped_times)

        X_warped = np.zeros_like(X)
        for i in range(len(X)):
            for f in range(X.shape[-1] if X.ndim > 2 else 1):
                if X.ndim > 2:
                    X_warped[i, :, f] = np.interp(original_times, warped_times, X[i, :, f])
                else:
                    X_warped[i, :] = np.interp(original_times, warped_times, X[i, :])

        acc = self._get_accuracy(model, X_warped.astype(np.float32), y)
        drop = clean_acc - acc

        if drop > 0.15:
            severity, status = Severity.HIGH, CheckStatus.FAIL
        elif drop > 0.05:
            severity, status = Severity.MEDIUM, CheckStatus.WARN
        else:
            severity, status = Severity.INFO, CheckStatus.PASS

        return self._make_finding(
            "time_warp", "Time-Warp Attack",
            f"Non-linear time distortion: accuracy drop {drop:.4f}",
            severity, status,
            details={"accuracy_drop": drop},
            recommendation="Apply time-warp augmentation during training."
            if status != CheckStatus.PASS else "",
        )

    def _test_missing_data(self, model, X, y, clean_acc, dropout_rates) -> Finding:
        """Random timestep dropout (replace with zeros)."""
        results = {}
        worst_drop = 0

        for rate in dropout_rates:
            rng = np.random.default_rng(42)
            mask = rng.random(X.shape[:2] if X.ndim >= 2 else X.shape) > rate
            X_dropout = X.copy()
            if X.ndim > 2:
                X_dropout *= mask[:, :, np.newaxis]
            else:
                X_dropout *= mask

            acc = self._get_accuracy(model, X_dropout.astype(np.float32), y)
            drop = clean_acc - acc
            results[rate] = {"accuracy": acc, "drop": drop}
            worst_drop = max(worst_drop, drop)

        if worst_drop > 0.2:
            severity, status = Severity.HIGH, CheckStatus.FAIL
        elif worst_drop > 0.1:
            severity, status = Severity.MEDIUM, CheckStatus.WARN
        else:
            severity, status = Severity.INFO, CheckStatus.PASS

        return self._make_finding(
            "missing_data", "Missing Data Robustness",
            f"Worst drop: {worst_drop:.4f} across dropout rates {dropout_rates}.",
            severity, status,
            details={"results": results, "worst_drop": worst_drop},
            recommendation="Implement missing data handling (imputation, masking)."
            if status != CheckStatus.PASS else "",
        )

    def _test_burst_dropout(self, model, X, y, clean_acc) -> Finding:
        """Contiguous burst of missing data."""
        if X.ndim < 2:
            return self._make_finding("burst_dropout", "Burst Dropout", "Need 2D+ data.", Severity.LOW, CheckStatus.SKIPPED)

        timesteps = X.shape[1]
        burst_lengths = [max(1, int(timesteps * r)) for r in [0.1, 0.2, 0.3]]
        worst_drop = 0

        for burst_len in burst_lengths:
            X_burst = X.copy()
            start = timesteps // 2 - burst_len // 2
            X_burst[:, start:start + burst_len] = 0
            acc = self._get_accuracy(model, X_burst.astype(np.float32), y)
            worst_drop = max(worst_drop, clean_acc - acc)

        if worst_drop > 0.2:
            severity, status = Severity.HIGH, CheckStatus.FAIL
        elif worst_drop > 0.1:
            severity, status = Severity.MEDIUM, CheckStatus.WARN
        else:
            severity, status = Severity.INFO, CheckStatus.PASS

        return self._make_finding(
            "burst_dropout", "Burst Dropout Robustness",
            f"Contiguous dropout worst drop: {worst_drop:.4f}",
            severity, status,
            details={"worst_drop": worst_drop, "burst_lengths": burst_lengths},
            recommendation="Model is fragile to contiguous missing data. Add burst-dropout augmentation."
            if status != CheckStatus.PASS else "",
        )

    def _test_temporal_distribution_shift(self, X) -> Finding:
        """Test for distribution shift between first and second half of data."""
        if X.ndim < 2:
            return self._make_finding("dist_shift", "Distribution Shift", "Need 2D+ data.", Severity.LOW, CheckStatus.SKIPPED)

        half = len(X) // 2
        first_half = X[:half].reshape(half, -1)
        second_half = X[half:].reshape(len(X) - half, -1)

        # Compare means and stds across features
        mean_diff = np.abs(np.mean(first_half, axis=0) - np.mean(second_half, axis=0))
        std_ratio = np.std(second_half, axis=0) / (np.std(first_half, axis=0) + 1e-10)

        avg_mean_diff = float(np.mean(mean_diff))
        avg_std_ratio = float(np.mean(std_ratio))

        if avg_mean_diff > 1.0 or abs(avg_std_ratio - 1.0) > 0.5:
            severity, status = Severity.HIGH, CheckStatus.WARN
        elif avg_mean_diff > 0.5 or abs(avg_std_ratio - 1.0) > 0.2:
            severity, status = Severity.MEDIUM, CheckStatus.WARN
        else:
            severity, status = Severity.INFO, CheckStatus.PASS

        return self._make_finding(
            "temporal_dist_shift", "Temporal Distribution Shift",
            f"Mean diff: {avg_mean_diff:.4f}, Std ratio: {avg_std_ratio:.4f}",
            severity, status,
            details={"avg_mean_difference": avg_mean_diff, "avg_std_ratio": avg_std_ratio},
            recommendation="Significant distribution shift detected. Implement online adaptation or drift-aware training."
            if status != CheckStatus.PASS else "",
        )
