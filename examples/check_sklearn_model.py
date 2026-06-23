#!/usr/bin/env python3
"""Example: Run fairness + interpretability checks on a scikit-learn classifier."""

import numpy as np
from sklearn.datasets import make_classification
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split

from aisafety.checkers.tree.fairness import FairnessChecker
from aisafety.checkers.tree.interpretability import InterpretabilityChecker
from aisafety.core.report import ReportBuilder


def main():
    # Generate synthetic data with a sensitive attribute
    X, y = make_classification(n_samples=1000, n_features=10, n_informative=5, random_state=42)
    sensitive = np.random.default_rng(42).choice(["group_a", "group_b"], size=len(y))

    X_train, X_test, y_train, y_test, sens_train, sens_test = train_test_split(
        X, y, sensitive, test_size=0.3, random_state=42,
    )

    # Train a model
    model = RandomForestClassifier(n_estimators=50, random_state=42)
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)

    # Initialize report builder
    builder = ReportBuilder(target_description="RandomForest on synthetic data")

    # Run fairness checks
    fairness = FairnessChecker()
    if fairness.is_available():
        result = fairness._timed_check(y_true=y_test, y_pred=y_pred, sensitive_features=sens_test)
        builder.add_result(result)
        print(f"Fairness: {len(result.findings)} findings")
        for f in result.findings:
            print(f"  [{f.status.value}] {f.title}: {f.description}")
    else:
        print("Fairness checker not available (install fairlearn)")

    # Run interpretability checks
    interp = InterpretabilityChecker()
    if interp.is_available():
        feature_names = [f"feature_{i}" for i in range(X_train.shape[1])]
        result = interp._timed_check(
            model=model, X_train=X_train, X_explain=X_test[:20], feature_names=feature_names,
        )
        builder.add_result(result)
        print(f"\nInterpretability: {len(result.findings)} findings")
        for f in result.findings:
            print(f"  [{f.status.value}] {f.title}: {f.description}")
    else:
        print("Interpretability checker not available (install shap)")

    # Generate report
    report_json = builder.to_json("sklearn_safety_report.json")
    report = builder.build()
    print(f"\n--- Summary ---")
    print(f"Total checks: {report.summary.total_checks}")
    print(f"Passed: {report.summary.passed}")
    print(f"Failed: {report.summary.failed}")
    print(f"Overall: {report.summary.overall_status.value}")
    print(f"Report saved to sklearn_safety_report.json")


if __name__ == "__main__":
    main()
