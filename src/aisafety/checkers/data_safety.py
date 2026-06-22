"""Data Safety Checker — PII scanning, bias detection, poisoning detection."""

from __future__ import annotations

from aisafety.core.base import BaseChecker
from aisafety.core.registry import register_checker
from aisafety.core.types import CheckStatus, Finding, Severity


@register_checker
class DataSafetyChecker(BaseChecker):
    name = "Data Safety"
    category = "data_safety"
    requires = ["pandas", "presidio_analyzer"]

    def check(
        self,
        dataset=None,
        text_columns: list[str] | None = None,
        sensitive_columns: list[str] | None = None,
        label_column: str | None = None,
        **kwargs,
    ) -> "CheckResult":
        import pandas as pd

        findings: list[Finding] = []

        if dataset is None:
            return self._make_result([self._make_finding(
                "no_data", "No dataset provided", "Provide a DataFrame or CSV path to check.",
                Severity.INFO, CheckStatus.SKIPPED,
            )])

        if isinstance(dataset, (str,)):
            dataset = pd.read_csv(dataset)

        # --- PII Scan ---
        if text_columns:
            pii_findings = self._scan_pii(dataset, text_columns)
            findings.extend(pii_findings)

        # --- Class Imbalance ---
        if label_column and label_column in dataset.columns:
            findings.append(self._check_class_imbalance(dataset, label_column))

        # --- Bias Detection ---
        if sensitive_columns and label_column:
            for col in sensitive_columns:
                if col in dataset.columns:
                    findings.append(self._check_bias(dataset, col, label_column))

        # --- Poisoning Detection (outlier-based) ---
        numeric_cols = dataset.select_dtypes(include=["number"]).columns.tolist()
        if numeric_cols:
            findings.append(self._check_poisoning(dataset, numeric_cols))

        return self._make_result(
            findings,
            metadata={"rows": len(dataset), "columns": list(dataset.columns)},
        )

    def _scan_pii(self, df, text_columns: list[str]) -> list[Finding]:
        from presidio_analyzer import AnalyzerEngine

        analyzer = AnalyzerEngine()
        findings = []
        total_pii = 0
        pii_types: dict[str, int] = {}

        for col in text_columns:
            if col not in df.columns:
                continue
            sample = df[col].dropna().head(500).astype(str)
            for text in sample:
                results = analyzer.analyze(text=text, language="en")
                for r in results:
                    if r.score >= 0.7:
                        total_pii += 1
                        pii_types[r.entity_type] = pii_types.get(r.entity_type, 0) + 1

        if total_pii > 0:
            findings.append(self._make_finding(
                "pii_detected",
                "PII Detected in Dataset",
                f"Found {total_pii} PII instances across {len(text_columns)} columns.",
                Severity.HIGH,
                CheckStatus.FAIL,
                details={"total_pii": total_pii, "entity_types": pii_types},
                recommendation="Remove or anonymize PII before training. Use presidio-anonymizer.",
            ))
        else:
            findings.append(self._make_finding(
                "pii_clean",
                "No PII Detected",
                "No personally identifiable information found in sampled text.",
                Severity.INFO,
                CheckStatus.PASS,
            ))

        return findings

    def _check_class_imbalance(self, df, label_column: str) -> Finding:
        counts = df[label_column].value_counts(normalize=True)
        min_ratio = counts.min()
        max_ratio = counts.max()
        imbalance_ratio = max_ratio / min_ratio if min_ratio > 0 else float("inf")

        if imbalance_ratio > 10:
            severity, status = Severity.HIGH, CheckStatus.FAIL
        elif imbalance_ratio > 3:
            severity, status = Severity.MEDIUM, CheckStatus.WARN
        else:
            severity, status = Severity.INFO, CheckStatus.PASS

        return self._make_finding(
            "class_imbalance",
            "Class Imbalance Check",
            f"Imbalance ratio: {imbalance_ratio:.1f}:1",
            severity,
            status,
            details={"distribution": counts.to_dict(), "imbalance_ratio": imbalance_ratio},
            recommendation="Consider resampling, SMOTE, or class-weighted loss." if status != CheckStatus.PASS else "",
        )

    def _check_bias(self, df, sensitive_col: str, label_col: str) -> Finding:
        from scipy.stats import chi2_contingency

        contingency = pd.crosstab(df[sensitive_col], df[label_col])  # noqa: F821
        try:
            import pandas as pd  # noqa: F811

            contingency = pd.crosstab(df[sensitive_col], df[label_col])
            chi2, p_value, dof, _ = chi2_contingency(contingency)
        except Exception:
            return self._make_finding(
                f"bias_{sensitive_col}",
                f"Bias Check: {sensitive_col}",
                "Could not compute chi-squared test.",
                Severity.LOW,
                CheckStatus.ERROR,
            )

        if p_value < 0.01:
            severity, status = Severity.HIGH, CheckStatus.FAIL
            desc = f"Strong statistical association between {sensitive_col} and {label_col} (p={p_value:.4f})"
        elif p_value < 0.05:
            severity, status = Severity.MEDIUM, CheckStatus.WARN
            desc = f"Moderate association between {sensitive_col} and {label_col} (p={p_value:.4f})"
        else:
            severity, status = Severity.INFO, CheckStatus.PASS
            desc = f"No significant association between {sensitive_col} and {label_col} (p={p_value:.4f})"

        return self._make_finding(
            f"bias_{sensitive_col}",
            f"Bias Check: {sensitive_col}",
            desc,
            severity,
            status,
            details={"chi2": chi2, "p_value": p_value, "dof": dof},
            recommendation="Investigate and mitigate bias in training data." if status != CheckStatus.PASS else "",
        )

    def _check_poisoning(self, df, numeric_cols: list[str]) -> Finding:
        import numpy as np

        outlier_count = 0
        total_points = 0

        for col in numeric_cols[:20]:  # limit to first 20 numeric columns
            values = df[col].dropna().values
            if len(values) < 10:
                continue
            total_points += len(values)
            mean, std = np.mean(values), np.std(values)
            if std > 0:
                z_scores = np.abs((values - mean) / std)
                outlier_count += int(np.sum(z_scores > 4))

        outlier_rate = outlier_count / total_points if total_points > 0 else 0

        if outlier_rate > 0.05:
            severity, status = Severity.HIGH, CheckStatus.FAIL
        elif outlier_rate > 0.01:
            severity, status = Severity.MEDIUM, CheckStatus.WARN
        else:
            severity, status = Severity.INFO, CheckStatus.PASS

        return self._make_finding(
            "poisoning_outliers",
            "Data Poisoning Check (Outlier Detection)",
            f"Outlier rate: {outlier_rate:.2%} ({outlier_count}/{total_points} points with z>4)",
            severity,
            status,
            details={"outlier_count": outlier_count, "total_points": total_points, "outlier_rate": outlier_rate},
            recommendation="Investigate extreme outliers for potential data poisoning." if status != CheckStatus.PASS else "",
        )
