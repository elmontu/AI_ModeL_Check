"""Fairness & Bias Checker — demographic parity, equalized odds, disparate impact."""

from __future__ import annotations

import numpy as np

from aisafety.core.base import BaseChecker
from aisafety.core.registry import register_checker
from aisafety.core.types import CheckStatus, Finding, Severity


@register_checker
class FairnessChecker(BaseChecker):
    name = "Fairness & Bias"
    category = "fairness"
    requires = ["fairlearn", "numpy"]
    model_types = ["tree"]

    def check(
        self,
        y_true=None,
        y_pred=None,
        sensitive_features=None,
        threshold: float = 0.1,
        **kwargs,
    ) -> "CheckResult":
        findings: list[Finding] = []

        if y_true is None or y_pred is None or sensitive_features is None:
            return self._make_result([self._make_finding(
                "no_data", "No prediction data provided",
                "Provide y_true, y_pred, and sensitive_features.",
                Severity.INFO, CheckStatus.SKIPPED,
            )])

        from fairlearn.metrics import (
            demographic_parity_difference,
            equalized_odds_difference,
        )

        y_true = np.asarray(y_true)
        y_pred = np.asarray(y_pred)
        sensitive_features = np.asarray(sensitive_features)

        # --- Demographic Parity ---
        dp_diff = demographic_parity_difference(y_true, y_pred, sensitive_features=sensitive_features)
        findings.append(self._evaluate_metric(
            "demographic_parity", "Demographic Parity",
            abs(dp_diff), threshold,
            "Selection rate difference between groups",
        ))

        # --- Equalized Odds ---
        eo_diff = equalized_odds_difference(y_true, y_pred, sensitive_features=sensitive_features)
        findings.append(self._evaluate_metric(
            "equalized_odds", "Equalized Odds",
            abs(eo_diff), threshold,
            "Max difference in TPR/FPR between groups",
        ))

        # --- Disparate Impact (4/5ths rule) ---
        findings.append(self._check_disparate_impact(y_pred, sensitive_features))

        # --- Subgroup Performance ---
        findings.append(self._check_subgroup_performance(y_true, y_pred, sensitive_features))

        return self._make_result(
            findings,
            metadata={"n_samples": len(y_true), "threshold": threshold},
        )

    def _evaluate_metric(
        self, check_id: str, title: str, value: float, threshold: float, desc_prefix: str,
    ) -> Finding:
        if value > threshold * 2:
            severity, status = Severity.HIGH, CheckStatus.FAIL
        elif value > threshold:
            severity, status = Severity.MEDIUM, CheckStatus.WARN
        else:
            severity, status = Severity.INFO, CheckStatus.PASS

        return self._make_finding(
            check_id, title,
            f"{desc_prefix}: {value:.4f} (threshold: {threshold})",
            severity, status,
            details={"value": value, "threshold": threshold},
            recommendation=f"Apply fairlearn mitigation (ExponentiatedGradient or ThresholdOptimizer)."
            if status != CheckStatus.PASS else "",
        )

    def _check_disparate_impact(self, y_pred, sensitive_features) -> Finding:
        groups = np.unique(sensitive_features)
        if len(groups) < 2:
            return self._make_finding(
                "disparate_impact", "Disparate Impact",
                "Need at least 2 groups.", Severity.LOW, CheckStatus.SKIPPED,
            )

        rates = {}
        for g in groups:
            mask = sensitive_features == g
            rates[str(g)] = float(np.mean(y_pred[mask])) if mask.sum() > 0 else 0.0

        rate_values = [r for r in rates.values() if r > 0]
        if len(rate_values) < 2:
            return self._make_finding(
                "disparate_impact", "Disparate Impact",
                "Cannot compute — at least one group has zero selection rate.",
                Severity.MEDIUM, CheckStatus.WARN,
                details={"selection_rates": rates},
            )

        di_ratio = min(rate_values) / max(rate_values)

        if di_ratio < 0.8:
            severity, status = Severity.HIGH, CheckStatus.FAIL
            desc = f"Disparate impact ratio: {di_ratio:.3f} (below 4/5ths rule threshold of 0.8)"
        else:
            severity, status = Severity.INFO, CheckStatus.PASS
            desc = f"Disparate impact ratio: {di_ratio:.3f} (meets 4/5ths rule)"

        return self._make_finding(
            "disparate_impact", "Disparate Impact (4/5ths Rule)",
            desc, severity, status,
            details={"ratio": di_ratio, "selection_rates": rates},
            recommendation="Review selection criteria for adverse impact." if status != CheckStatus.PASS else "",
        )

    def _check_subgroup_performance(self, y_true, y_pred, sensitive_features) -> Finding:
        groups = np.unique(sensitive_features)
        accuracies = {}
        for g in groups:
            mask = sensitive_features == g
            if mask.sum() > 0:
                accuracies[str(g)] = float(np.mean(y_true[mask] == y_pred[mask]))

        if not accuracies:
            return self._make_finding(
                "subgroup_perf", "Subgroup Performance",
                "No subgroups found.", Severity.LOW, CheckStatus.SKIPPED,
            )

        max_gap = max(accuracies.values()) - min(accuracies.values())

        if max_gap > 0.15:
            severity, status = Severity.HIGH, CheckStatus.FAIL
        elif max_gap > 0.05:
            severity, status = Severity.MEDIUM, CheckStatus.WARN
        else:
            severity, status = Severity.INFO, CheckStatus.PASS

        return self._make_finding(
            "subgroup_performance", "Subgroup Performance Gap",
            f"Max accuracy gap between groups: {max_gap:.4f}",
            severity, status,
            details={"accuracies": accuracies, "max_gap": max_gap},
            recommendation="Investigate underperforming subgroups and consider targeted improvements."
            if status != CheckStatus.PASS else "",
        )
