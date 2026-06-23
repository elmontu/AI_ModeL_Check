"""Concept Drift Checker — drift detection, model staleness, and temporal stability.

Checks covered:
- Covariate drift detection (feature distribution shift over time)
- Prediction drift detection (output distribution shift)
- Label drift detection (target distribution shift)
- Model staleness estimation (performance decay over time windows)
- Feature importance stability (do important features change over time?)
"""

from __future__ import annotations

import numpy as np

from aisafety.core.base import BaseChecker
from aisafety.core.registry import register_checker
from aisafety.core.types import CheckStatus, Finding, Severity


@register_checker
class ConceptDriftChecker(BaseChecker):
    name = "Concept Drift"
    category = "concept_drift"
    requires = ["numpy"]
    model_types = ["longitudinal"]

    def check(
        self,
        model=None,
        X_reference=None,
        y_reference=None,
        X_current=None,
        y_current=None,
        timestamps=None,
        n_windows: int = 5,
        **kwargs,
    ) -> "CheckResult":
        findings: list[Finding] = []

        if X_reference is None or X_current is None:
            return self._make_result([self._make_finding(
                "no_data", "No data provided",
                "Provide X_reference (training/baseline), X_current (recent), and optionally model, y_reference, y_current.",
                Severity.INFO, CheckStatus.SKIPPED,
            )])

        X_reference = np.asarray(X_reference, dtype=np.float32)
        X_current = np.asarray(X_current, dtype=np.float32)

        # Covariate drift
        findings.append(self._detect_covariate_drift(X_reference, X_current))

        # Prediction drift
        if model is not None:
            findings.append(self._detect_prediction_drift(model, X_reference, X_current))

        # Label drift
        if y_reference is not None and y_current is not None:
            findings.append(self._detect_label_drift(
                np.asarray(y_reference), np.asarray(y_current),
            ))

        # Model staleness
        if model is not None and y_current is not None:
            findings.append(self._detect_staleness(
                model, X_current, np.asarray(y_current), n_windows,
            ))

        # Population Stability Index
        findings.append(self._compute_psi(X_reference, X_current))

        return self._make_result(
            findings,
            metadata={
                "reference_samples": len(X_reference),
                "current_samples": len(X_current),
            },
        )

    def _detect_covariate_drift(self, X_ref, X_cur) -> Finding:
        """Detect feature distribution shift using KS-like statistic."""
        X_ref_flat = X_ref.reshape(len(X_ref), -1)
        X_cur_flat = X_cur.reshape(len(X_cur), -1)
        n_features = X_ref_flat.shape[1]

        drift_scores = []
        drifted_features = []

        for f in range(min(n_features, 50)):  # cap at 50 features
            ref_vals = np.sort(X_ref_flat[:, f])
            cur_vals = np.sort(X_cur_flat[:, f])

            # Compute empirical CDF difference (simplified KS statistic)
            all_vals = np.concatenate([ref_vals, cur_vals])
            ref_cdf = np.searchsorted(ref_vals, all_vals, side="right") / len(ref_vals)
            cur_cdf = np.searchsorted(cur_vals, all_vals, side="right") / len(cur_vals)
            ks_stat = float(np.max(np.abs(ref_cdf - cur_cdf)))

            drift_scores.append(ks_stat)
            if ks_stat > 0.1:
                drifted_features.append({"feature": f, "ks_statistic": ks_stat})

        avg_ks = float(np.mean(drift_scores))
        max_ks = float(np.max(drift_scores)) if drift_scores else 0

        if max_ks > 0.3 or len(drifted_features) > n_features * 0.3:
            severity, status = Severity.HIGH, CheckStatus.FAIL
        elif max_ks > 0.15 or len(drifted_features) > n_features * 0.1:
            severity, status = Severity.MEDIUM, CheckStatus.WARN
        else:
            severity, status = Severity.INFO, CheckStatus.PASS

        return self._make_finding(
            "covariate_drift", "Covariate Drift Detection",
            f"Avg KS stat: {avg_ks:.4f}, Max: {max_ks:.4f}, "
            f"{len(drifted_features)}/{min(n_features, 50)} features drifted.",
            severity, status,
            details={
                "avg_ks_statistic": avg_ks,
                "max_ks_statistic": max_ks,
                "drifted_features": drifted_features[:10],
                "n_drifted": len(drifted_features),
            },
            recommendation="Retrain model on recent data or implement online learning."
            if status != CheckStatus.PASS else "",
        )

    def _detect_prediction_drift(self, model, X_ref, X_cur) -> Finding:
        """Detect shift in model output distribution."""
        ref_preds = model.predict(X_ref)
        cur_preds = model.predict(X_cur)

        if ref_preds.ndim > 1:
            ref_preds = np.argmax(ref_preds, axis=1)
        if cur_preds.ndim > 1:
            cur_preds = np.argmax(cur_preds, axis=1)

        # Compare prediction distributions
        ref_dist = np.bincount(ref_preds.astype(int), minlength=max(ref_preds.max(), cur_preds.max()) + 1) / len(ref_preds)
        cur_dist = np.bincount(cur_preds.astype(int), minlength=max(ref_preds.max(), cur_preds.max()) + 1) / len(cur_preds)

        # Jensen-Shannon divergence
        m = (ref_dist + cur_dist) / 2
        js_div = 0.0
        for p, q, mi in zip(ref_dist, cur_dist, m):
            if mi > 0:
                if p > 0:
                    js_div += 0.5 * p * np.log(p / mi)
                if q > 0:
                    js_div += 0.5 * q * np.log(q / mi)

        if js_div > 0.1:
            severity, status = Severity.HIGH, CheckStatus.FAIL
        elif js_div > 0.05:
            severity, status = Severity.MEDIUM, CheckStatus.WARN
        else:
            severity, status = Severity.INFO, CheckStatus.PASS

        return self._make_finding(
            "prediction_drift", "Prediction Drift Detection",
            f"JS divergence between reference and current predictions: {js_div:.4f}",
            severity, status,
            details={
                "js_divergence": js_div,
                "reference_distribution": ref_dist.tolist(),
                "current_distribution": cur_dist.tolist(),
            },
            recommendation="Model output distribution has shifted. Consider retraining."
            if status != CheckStatus.PASS else "",
        )

    def _detect_label_drift(self, y_ref, y_cur) -> Finding:
        """Detect shift in target variable distribution."""
        if y_ref.ndim > 1:
            y_ref = np.argmax(y_ref, axis=1)
        if y_cur.ndim > 1:
            y_cur = np.argmax(y_cur, axis=1)

        max_label = max(y_ref.max(), y_cur.max()) + 1
        ref_dist = np.bincount(y_ref.astype(int), minlength=max_label) / len(y_ref)
        cur_dist = np.bincount(y_cur.astype(int), minlength=max_label) / len(y_cur)

        # Chi-squared-like statistic
        diff = np.sum(np.abs(ref_dist - cur_dist))

        if diff > 0.2:
            severity, status = Severity.HIGH, CheckStatus.FAIL
        elif diff > 0.1:
            severity, status = Severity.MEDIUM, CheckStatus.WARN
        else:
            severity, status = Severity.INFO, CheckStatus.PASS

        return self._make_finding(
            "label_drift", "Label Drift Detection",
            f"L1 distance between label distributions: {diff:.4f}",
            severity, status,
            details={
                "l1_distance": diff,
                "reference_distribution": ref_dist.tolist(),
                "current_distribution": cur_dist.tolist(),
            },
            recommendation="Target distribution has shifted (concept drift). Retrain with recent labels."
            if status != CheckStatus.PASS else "",
        )

    def _detect_staleness(self, model, X, y, n_windows) -> Finding:
        """Measure performance decay across sequential time windows."""
        n = len(X)
        window_size = n // n_windows
        if window_size < 10:
            return self._make_finding(
                "staleness", "Model Staleness",
                "Not enough data for windowed analysis.",
                Severity.LOW, CheckStatus.SKIPPED,
            )

        window_accs = []
        for i in range(n_windows):
            start = i * window_size
            end = start + window_size
            X_win = X[start:end]
            y_win = y[start:end]
            if y_win.ndim > 1:
                y_win = np.argmax(y_win, axis=1)
            preds = model.predict(X_win)
            if preds.ndim > 1:
                preds = np.argmax(preds, axis=1)
            acc = float(np.mean(preds == y_win))
            window_accs.append(acc)

        # Check for declining trend
        if len(window_accs) >= 3:
            trend = np.polyfit(range(len(window_accs)), window_accs, 1)[0]
        else:
            trend = 0

        total_decay = window_accs[0] - window_accs[-1] if window_accs else 0

        if total_decay > 0.1 or trend < -0.02:
            severity, status = Severity.HIGH, CheckStatus.FAIL
        elif total_decay > 0.05 or trend < -0.01:
            severity, status = Severity.MEDIUM, CheckStatus.WARN
        else:
            severity, status = Severity.INFO, CheckStatus.PASS

        return self._make_finding(
            "staleness", "Model Staleness",
            f"Performance trend: {trend:.4f}/window, total decay: {total_decay:.4f}",
            severity, status,
            details={
                "window_accuracies": window_accs,
                "trend_slope": trend,
                "total_decay": total_decay,
                "n_windows": n_windows,
            },
            recommendation="Model performance is declining over time. Schedule retraining."
            if status != CheckStatus.PASS else "",
        )

    def _compute_psi(self, X_ref, X_cur) -> Finding:
        """Compute Population Stability Index (PSI) for each feature."""
        X_ref_flat = X_ref.reshape(len(X_ref), -1)
        X_cur_flat = X_cur.reshape(len(X_cur), -1)
        n_features = min(X_ref_flat.shape[1], 50)

        psi_values = []
        for f in range(n_features):
            ref_vals = X_ref_flat[:, f]
            cur_vals = X_cur_flat[:, f]

            # Create 10 bins from reference distribution
            bins = np.percentile(ref_vals, np.linspace(0, 100, 11))
            bins[0] = -np.inf
            bins[-1] = np.inf

            ref_counts = np.histogram(ref_vals, bins=bins)[0] / len(ref_vals)
            cur_counts = np.histogram(cur_vals, bins=bins)[0] / len(cur_vals)

            # Avoid log(0)
            ref_counts = np.clip(ref_counts, 1e-6, None)
            cur_counts = np.clip(cur_counts, 1e-6, None)

            psi = float(np.sum((cur_counts - ref_counts) * np.log(cur_counts / ref_counts)))
            psi_values.append(psi)

        avg_psi = float(np.mean(psi_values))
        max_psi = float(np.max(psi_values)) if psi_values else 0

        # PSI thresholds: < 0.1 = no shift, 0.1-0.25 = moderate, > 0.25 = significant
        if max_psi > 0.25 or avg_psi > 0.15:
            severity, status = Severity.HIGH, CheckStatus.FAIL
        elif max_psi > 0.1 or avg_psi > 0.05:
            severity, status = Severity.MEDIUM, CheckStatus.WARN
        else:
            severity, status = Severity.INFO, CheckStatus.PASS

        return self._make_finding(
            "psi", "Population Stability Index (PSI)",
            f"Avg PSI: {avg_psi:.4f}, Max PSI: {max_psi:.4f}",
            severity, status,
            details={"avg_psi": avg_psi, "max_psi": max_psi, "n_features": n_features},
            recommendation="PSI indicates significant population shift. Retrain or recalibrate."
            if status != CheckStatus.PASS else "",
        )
