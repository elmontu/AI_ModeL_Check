"""Sequence Safety Checker — data integrity and leakage checks for time-series models.

Checks covered:
- Look-ahead bias / temporal leakage detection
- Anomaly injection robustness
- Label leakage between train/test splits
- Temporal ordering validation
- Autocorrelation-based memorization detection
"""

from __future__ import annotations

import numpy as np

from aisafety.core.base import BaseChecker
from aisafety.core.registry import register_checker
from aisafety.core.types import CheckStatus, Finding, Severity


@register_checker
class SequenceSafetyChecker(BaseChecker):
    name = "Sequence Safety"
    category = "sequence_safety"
    requires = ["numpy"]
    model_types = ["longitudinal"]

    def check(
        self,
        model=None,
        X_train=None,
        y_train=None,
        X_test=None,
        y_test=None,
        timestamps_train=None,
        timestamps_test=None,
        **kwargs,
    ) -> "CheckResult":
        findings: list[Finding] = []

        if X_train is None and X_test is None:
            return self._make_result([self._make_finding(
                "no_data", "No data provided",
                "Provide X_train/X_test with optional timestamps.",
                Severity.INFO, CheckStatus.SKIPPED,
            )])

        if X_train is not None:
            X_train = np.asarray(X_train, dtype=np.float32)
        if X_test is not None:
            X_test = np.asarray(X_test, dtype=np.float32)
        if y_train is not None:
            y_train = np.asarray(y_train)
        if y_test is not None:
            y_test = np.asarray(y_test)

        # Look-ahead bias
        if timestamps_train is not None and timestamps_test is not None:
            findings.append(self._check_lookahead_bias(
                np.asarray(timestamps_train), np.asarray(timestamps_test),
            ))

        # Temporal ordering
        if timestamps_train is not None:
            findings.append(self._check_temporal_ordering(np.asarray(timestamps_train), "train"))
        if timestamps_test is not None:
            findings.append(self._check_temporal_ordering(np.asarray(timestamps_test), "test"))

        # Train-test leakage
        if X_train is not None and X_test is not None:
            findings.append(self._check_data_leakage(X_train, X_test))

        # Anomaly injection robustness
        if model is not None and X_test is not None and y_test is not None:
            findings.append(self._test_anomaly_injection(model, X_test, y_test))

        # Autocorrelation memorization
        if model is not None and X_train is not None and y_train is not None:
            findings.append(self._check_autocorrelation_memorization(model, X_train, y_train))

        # Label distribution temporal consistency
        if y_train is not None and y_test is not None:
            findings.append(self._check_label_temporal_consistency(y_train, y_test))

        return self._make_result(
            findings,
            metadata={
                "train_samples": len(X_train) if X_train is not None else 0,
                "test_samples": len(X_test) if X_test is not None else 0,
            },
        )

    def _check_lookahead_bias(self, ts_train, ts_test) -> Finding:
        """Check if any test timestamps precede training timestamps (data leakage)."""
        train_max = np.max(ts_train)
        test_min = np.min(ts_test)

        # Check for overlap
        overlap_count = int(np.sum(ts_test < train_max))
        overlap_rate = overlap_count / len(ts_test) if len(ts_test) > 0 else 0

        if overlap_count > 0:
            severity, status = Severity.CRITICAL, CheckStatus.FAIL
            desc = (f"Look-ahead bias: {overlap_count} test samples ({overlap_rate:.0%}) "
                    f"have timestamps before training end.")
        else:
            severity, status = Severity.INFO, CheckStatus.PASS
            desc = "No look-ahead bias detected. Test data is strictly after training data."

        return self._make_finding(
            "lookahead_bias", "Look-Ahead Bias Detection",
            desc, severity, status,
            details={
                "train_max_timestamp": float(train_max),
                "test_min_timestamp": float(test_min),
                "overlap_count": overlap_count,
                "overlap_rate": overlap_rate,
            },
            recommendation="Remove test samples that overlap with training period. Use strict temporal splits."
            if status != CheckStatus.PASS else "",
        )

    def _check_temporal_ordering(self, timestamps, split_name: str) -> Finding:
        """Verify timestamps are monotonically increasing."""
        is_sorted = bool(np.all(timestamps[:-1] <= timestamps[1:]))
        n_violations = int(np.sum(timestamps[:-1] > timestamps[1:]))

        if not is_sorted:
            severity, status = Severity.HIGH, CheckStatus.FAIL
            desc = f"{split_name}: {n_violations} temporal ordering violations."
        else:
            severity, status = Severity.INFO, CheckStatus.PASS
            desc = f"{split_name}: timestamps are monotonically ordered."

        return self._make_finding(
            f"temporal_order_{split_name}", f"Temporal Ordering ({split_name})",
            desc, severity, status,
            details={"is_sorted": is_sorted, "violations": n_violations},
            recommendation="Sort data by timestamp before training. Violations can cause leakage."
            if status != CheckStatus.PASS else "",
        )

    def _check_data_leakage(self, X_train, X_test) -> Finding:
        """Check for duplicate/near-duplicate samples between train and test."""
        X_train_flat = X_train.reshape(len(X_train), -1)
        X_test_flat = X_test.reshape(len(X_test), -1)

        # Sample for efficiency
        n_train = min(500, len(X_train_flat))
        n_test = min(200, len(X_test_flat))

        duplicates = 0
        near_duplicates = 0

        for i in range(n_test):
            dists = np.sqrt(np.sum((X_train_flat[:n_train] - X_test_flat[i]) ** 2, axis=1))
            min_dist = float(np.min(dists))
            if min_dist == 0:
                duplicates += 1
            elif min_dist < 1e-4 * np.mean(np.std(X_train_flat[:n_train], axis=0)):
                near_duplicates += 1

        total_leakage = duplicates + near_duplicates
        leak_rate = total_leakage / n_test if n_test > 0 else 0

        if duplicates > 0:
            severity, status = Severity.CRITICAL, CheckStatus.FAIL
        elif near_duplicates > n_test * 0.1:
            severity, status = Severity.HIGH, CheckStatus.WARN
        elif near_duplicates > 0:
            severity, status = Severity.MEDIUM, CheckStatus.WARN
        else:
            severity, status = Severity.INFO, CheckStatus.PASS

        return self._make_finding(
            "data_leakage", "Train-Test Data Leakage",
            f"Exact duplicates: {duplicates}, near-duplicates: {near_duplicates} "
            f"(checked {n_test} test vs {n_train} train samples).",
            severity, status,
            details={
                "exact_duplicates": duplicates,
                "near_duplicates": near_duplicates,
                "leak_rate": leak_rate,
            },
            recommendation="Remove duplicate samples. Use temporal splitting, not random splitting."
            if status != CheckStatus.PASS else "",
        )

    def _test_anomaly_injection(self, model, X_test, y_test) -> Finding:
        """Test model behavior when anomalous points are injected into sequences."""
        if X_test.ndim < 2:
            return self._make_finding("anomaly_injection", "Anomaly Injection", "Need 2D+ data.",
                                     Severity.LOW, CheckStatus.SKIPPED)

        clean_acc = self._get_accuracy(model, X_test, y_test)

        rng = np.random.default_rng(42)
        n = min(200, len(X_test))
        X_anom = X_test[:n].copy()

        # Inject spike anomalies at random timesteps
        for i in range(n):
            t = rng.integers(0, X_anom.shape[1])
            X_anom[i, t] = X_anom[i, t] + 10 * np.std(X_test)

        anom_acc = self._get_accuracy(model, X_anom, y_test[:n])
        drop = clean_acc - anom_acc

        if drop > 0.2:
            severity, status = Severity.HIGH, CheckStatus.FAIL
        elif drop > 0.1:
            severity, status = Severity.MEDIUM, CheckStatus.WARN
        else:
            severity, status = Severity.INFO, CheckStatus.PASS

        return self._make_finding(
            "anomaly_injection", "Anomaly Injection Robustness",
            f"Single-point spike injection: accuracy drop {drop:.4f}",
            severity, status,
            details={"clean_accuracy": clean_acc, "anomaly_accuracy": anom_acc, "accuracy_drop": drop},
            recommendation="Model is sensitive to anomalous data points. Add anomaly detection preprocessing."
            if status != CheckStatus.PASS else "",
        )

    def _check_autocorrelation_memorization(self, model, X_train, y_train) -> Finding:
        """Check if model memorizes autocorrelation patterns instead of learning features."""
        if X_train.ndim < 2:
            return self._make_finding("autocorr_memo", "Autocorrelation Memorization",
                                     "Need 2D+ data.", Severity.LOW, CheckStatus.SKIPPED)

        n = min(200, len(X_train))
        clean_acc = self._get_accuracy(model, X_train[:n], y_train[:n])

        # Shuffle timesteps within each sample (breaks temporal structure)
        rng = np.random.default_rng(42)
        X_shuffled = X_train[:n].copy()
        for i in range(n):
            perm = rng.permutation(X_shuffled.shape[1])
            X_shuffled[i] = X_shuffled[i, perm]

        shuffled_acc = self._get_accuracy(model, X_shuffled, y_train[:n])

        # If shuffled accuracy ≈ clean accuracy, model doesn't use temporal structure
        temporal_dependence = clean_acc - shuffled_acc

        if temporal_dependence < 0.02:
            severity, status = Severity.MEDIUM, CheckStatus.WARN
            desc = f"Model barely uses temporal structure (drop when shuffled: {temporal_dependence:.4f})."
        else:
            severity, status = Severity.INFO, CheckStatus.PASS
            desc = f"Model uses temporal structure (drop when shuffled: {temporal_dependence:.4f})."

        return self._make_finding(
            "autocorrelation_memorization", "Temporal Structure Usage",
            desc, severity, status,
            details={
                "clean_accuracy": clean_acc,
                "shuffled_accuracy": shuffled_acc,
                "temporal_dependence": temporal_dependence,
            },
            recommendation="Model may be ignoring temporal patterns. Verify feature engineering."
            if status != CheckStatus.PASS else "",
        )

    def _check_label_temporal_consistency(self, y_train, y_test) -> Finding:
        """Check if label distribution is consistent between train and test periods."""
        if y_train.ndim > 1:
            y_train = np.argmax(y_train, axis=1)
        if y_test.ndim > 1:
            y_test = np.argmax(y_test, axis=1)

        max_label = max(y_train.max(), y_test.max()) + 1
        train_dist = np.bincount(y_train.astype(int), minlength=max_label) / len(y_train)
        test_dist = np.bincount(y_test.astype(int), minlength=max_label) / len(y_test)

        l1_diff = float(np.sum(np.abs(train_dist - test_dist)))

        if l1_diff > 0.3:
            severity, status = Severity.HIGH, CheckStatus.WARN
        elif l1_diff > 0.1:
            severity, status = Severity.MEDIUM, CheckStatus.WARN
        else:
            severity, status = Severity.INFO, CheckStatus.PASS

        return self._make_finding(
            "label_consistency", "Label Distribution Consistency",
            f"L1 distance between train/test label distributions: {l1_diff:.4f}",
            severity, status,
            details={
                "l1_distance": l1_diff,
                "train_distribution": train_dist.tolist(),
                "test_distribution": test_dist.tolist(),
            },
            recommendation="Label distribution differs significantly between periods. "
            "This may indicate concept drift or improper splitting."
            if status != CheckStatus.PASS else "",
        )

    def _get_accuracy(self, model, X, y) -> float:
        preds = model.predict(X)
        if preds.ndim > 1:
            preds = np.argmax(preds, axis=1)
        if y.ndim > 1:
            y = np.argmax(y, axis=1)
        return float(np.mean(preds == y))
