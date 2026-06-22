"""Tests for the Alignment checker."""

import numpy as np
import pytest

from aisafety.checkers.alignment import AlignmentChecker


def test_alignment_no_data():
    checker = AlignmentChecker()
    result = checker.check()
    assert result.findings[0].status.value == "skipped"


def test_alignment_basic(sample_trajectories):
    checker = AlignmentChecker()
    if not checker.is_available():
        pytest.skip("numpy not installed")

    result = checker.check(trajectories=sample_trajectories)
    assert result.category == "alignment"
    assert len(result.findings) >= 2  # reward hacking + shortcuts + action diversity


def test_alignment_with_gt_scores(sample_trajectories):
    checker = AlignmentChecker()
    if not checker.is_available():
        pytest.skip("numpy not installed")

    # Generate correlated ground truth scores
    rng = np.random.default_rng(42)
    gt_scores = [sum(t["rewards"]) / len(t["rewards"]) + rng.random() * 0.1 for t in sample_trajectories]

    result = checker.check(
        trajectories=sample_trajectories,
        ground_truth_scores=gt_scores,
        reward_fn=lambda x: sum(x),
    )

    reward_finding = next(f for f in result.findings if "reward_hacking" in f.check_id)
    assert reward_finding is not None


def test_alignment_degenerate_trajectories():
    checker = AlignmentChecker()
    if not checker.is_available():
        pytest.skip("numpy not installed")

    # All same action → should flag shortcut
    trajectories = [
        {"states": [[0]] * 20, "actions": [1] * 20, "rewards": [1.0] * 20}
        for _ in range(10)
    ]

    result = checker.check(trajectories=trajectories)
    shortcut = next(f for f in result.findings if "shortcut" in f.check_id)
    assert shortcut.status.value in ("fail", "warn")
