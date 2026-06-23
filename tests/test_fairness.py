"""Tests for the Fairness checker."""

import numpy as np
import pytest


def test_fairness_checker_basic(binary_classification_data):
    from aisafety.checkers.tree.fairness import FairnessChecker

    checker = FairnessChecker()
    if not checker.is_available():
        pytest.skip("fairlearn not installed")

    data = binary_classification_data
    result = checker.check(
        y_true=data["y"],
        y_pred=data["y_pred"],
        sensitive_features=data["sensitive"],
    )

    assert result.category == "fairness"
    assert len(result.findings) >= 3  # demographic parity, equalized odds, disparate impact, subgroup
    check_ids = [f.check_id for f in result.findings]
    assert any("demographic_parity" in cid for cid in check_ids)
    assert any("equalized_odds" in cid for cid in check_ids)
    assert any("disparate_impact" in cid for cid in check_ids)


def test_fairness_checker_no_data():
    from aisafety.checkers.tree.fairness import FairnessChecker

    checker = FairnessChecker()
    result = checker.check()
    assert len(result.findings) == 1
    assert result.findings[0].status.value == "skipped"


def test_fairness_checker_perfect_fairness():
    from aisafety.checkers.tree.fairness import FairnessChecker

    checker = FairnessChecker()
    if not checker.is_available():
        pytest.skip("fairlearn not installed")

    # Same predictions for all groups
    y_true = np.array([0, 1, 0, 1, 0, 1, 0, 1])
    y_pred = np.array([0, 1, 0, 1, 0, 1, 0, 1])
    sensitive = np.array([0, 0, 0, 0, 1, 1, 1, 1])

    result = checker.check(y_true=y_true, y_pred=y_pred, sensitive_features=sensitive)

    dp_finding = next(f for f in result.findings if "demographic_parity" in f.check_id)
    assert dp_finding.status.value == "pass"
