#!/usr/bin/env python3
"""Analyze the Version 0.5 full-corpus proxy release experiment.

The analysis freezes mechanism certification on development seeds, selects complete
three-release portfolios, and evaluates them on untouched seeds.  It reports proxy
benchmark estimands only; no government sampling-frame inference is performed.
"""

from __future__ import annotations

import argparse
import gzip
import itertools
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from run_openml_dp_sgd import compose_epsilon  # noqa: E402
from run_openml_membership import one_sided_clopper_pearson  # noqa: E402
from run_openml_structural import sha256_file, write_json  # noqa: E402


DEFAULT_DESIGN = ROOT / "reproduction/prospective-v05/config.json"
DEFAULT_TRAINING = ROOT / "output/reproduction/v05-prospective-training-summary.json"
DEFAULT_SUMMARY = ROOT / "output/reproduction/v05-prospective-decision-summary.json"
DEFAULT_ANALYSIS = ROOT / "output/reproduction/v05-prospective-decision-analysis.json"
DEFAULT_RAW = ROOT / "output/reproduction/v05-prospective-decision-raw.json.gz"
REFUSE = "refuse"


def action_id(epsilon: float) -> str:
    return f"dp-{str(float(epsilon)).replace('.', 'p')}"


def group_privacy(epsilon: float, delta: float, group_size: int) -> tuple[float, float]:
    """Basic group-privacy lift for add/remove adjacency."""
    if epsilon < 0.0 or not 0.0 <= delta <= 1.0 or group_size < 1:
        raise ValueError("invalid group-privacy arguments")
    if group_size == 1:
        return epsilon, delta
    if epsilon == 0.0:
        multiplier = float(group_size)
    else:
        multiplier = math.expm1(group_size * epsilon) / math.expm1(epsilon)
    return group_size * epsilon, min(1.0, delta * multiplier)


def utility_pass(record: dict[str, Any], design: dict[str, Any]) -> bool:
    dp_value = float(record["utility"]["balanced_accuracy"])
    control_value = float(record["matched_non_private_utility"]["balanced_accuracy"])
    chance = 1.0 / int(record["class_count"])
    floor = max(
        control_value - float(design["utility_max_balanced_accuracy_degradation"]),
        chance + float(design["utility_minimum_margin_above_chance"]),
    )
    return dp_value >= floor


def accountant_valid(record: dict[str, Any]) -> bool:
    target = float(record["epsilon_target"])
    for key in ("target_accountant", "reference_accountant"):
        ledger = record[key]
        if ledger["sampling"] != "independent_poisson":
            return False
        if ledger["adjacency"] != "add_remove_one_training_record":
            return False
        if float(ledger["epsilon_computed"]) > target + 1e-9:
            return False
        if not 0.0 <= float(ledger["delta"]) <= 1.0:
            return False
        replayed, order, by_order = compose_epsilon(
            float(ledger["sample_rate"]),
            float(ledger["noise_multiplier"]),
            int(ledger["steps"]),
            float(ledger["delta"]),
            [int(value) for value in ledger["orders"]],
        )
        if not math.isclose(replayed, float(ledger["epsilon_computed"]), rel_tol=0.0, abs_tol=1e-10):
            return False
        if order != int(ledger["optimal_integer_order"]):
            return False
        if any(
            not math.isclose(
                float(by_order[name]),
                float(ledger["epsilon_by_integer_order"][name]),
                rel_tol=0.0,
                abs_tol=1e-10,
            )
            for name in by_order
        ):
            return False
    return True


def artifact_hashes_valid(record: dict[str, Any]) -> bool:
    for artifact in record["artifacts"].values():
        path = ROOT / artifact["path"]
        if not path.is_file() or sha256_file(path) != artifact["sha256"]:
            return False
    return True


def attack_counts_valid(record: dict[str, Any]) -> bool:
    attack = record["attack"]
    groups = record["group_counts"]
    return (
        int(attack["true_positives"]) + int(attack["false_negatives"])
        == int(groups["member_audit"])
        and int(attack["false_positives"]) + int(attack["true_negatives"])
        == int(groups["nonmember_audit"])
        and 0 <= int(attack["calibration_false_positives"])
        <= int(groups["nonmember_calibration"])
    )


def attack_blocks(record: dict[str, Any], tolerance: float) -> bool:
    floor = record["attack"].get("certified_attack_floor")
    return floor is not None and float(floor) > tolerance


def _allocation_cost(
    allocation: tuple[str, ...],
    costs: dict[str, tuple[float, float]],
) -> tuple[float, float]:
    return (
        sum(costs[action][0] for action in allocation if action != REFUSE),
        sum(costs[action][1] for action in allocation if action != REFUSE),
    )


def choose_joint_allocation(
    *,
    actions: tuple[str, ...],
    eligible: dict[str, bool],
    values: dict[str, float],
    costs: dict[str, tuple[float, float]],
    weights: tuple[float, ...],
    epsilon_budget: float,
    delta_budget: float,
) -> tuple[str, ...]:
    best: tuple[str, ...] | None = None
    best_key: tuple[float, int, float, float] | None = None
    for allocation in itertools.product((*actions, REFUSE), repeat=len(weights)):
        if any(action != REFUSE and not eligible[action] for action in allocation):
            continue
        epsilon, delta = _allocation_cost(allocation, costs)
        if epsilon > epsilon_budget + 1e-12 or delta > delta_budget + 1e-15:
            continue
        value = sum(
            weight * values[action]
            for weight, action in zip(weights, allocation, strict=True)
            if action != REFUSE
        )
        releases = sum(action != REFUSE for action in allocation)
        key = (value, releases, -epsilon, -delta)
        if best_key is None or key > best_key:
            best, best_key = allocation, key
    if best is None:
        raise RuntimeError("refusal allocation must always be feasible")
    return best


def choose_greedy_allocation(
    *,
    actions: tuple[str, ...],
    eligible: dict[str, bool],
    values: dict[str, float],
    costs: dict[str, tuple[float, float]],
    weights: tuple[float, ...],
    epsilon_budget: float,
    delta_budget: float,
) -> tuple[str, ...]:
    selected: list[str] = []
    used_epsilon = 0.0
    used_delta = 0.0
    for weight in weights:
        feasible = [
            action
            for action in actions
            if eligible[action]
            and used_epsilon + costs[action][0] <= epsilon_budget + 1e-12
            and used_delta + costs[action][1] <= delta_budget + 1e-15
        ]
        if not feasible:
            selected.append(REFUSE)
            continue
        chosen = max(
            feasible,
            key=lambda action: (
                weight * values[action],
                -costs[action][0],
                -costs[action][1],
                action,
            ),
        )
        selected.append(chosen)
        used_epsilon += costs[chosen][0]
        used_delta += costs[chosen][1]
    return tuple(selected)


def _allocation_value(
    allocation: tuple[str, ...], values: dict[str, float], weights: tuple[float, ...]
) -> float:
    return sum(
        weight * values[action]
        for weight, action in zip(weights, allocation, strict=True)
        if action != REFUSE
    )


def _record_map(records: Iterable[dict[str, Any]]) -> dict[tuple[int, int, str], dict[str, Any]]:
    result: dict[tuple[int, int, str], dict[str, Any]] = {}
    for record in records:
        key = (
            int(record["dataset_id"]),
            int(record["seed"]),
            action_id(float(record["epsilon_target"])),
        )
        if key in result:
            raise ValueError(f"duplicate training cell {key}")
        result[key] = record
    return result


def analyze(
    design_path: Path,
    training_path: Path,
    summary_path: Path,
    analysis_path: Path,
    raw_path: Path,
) -> dict[str, Any]:
    design = json.loads(design_path.read_text(encoding="utf-8"))
    training = json.loads(training_path.read_text(encoding="utf-8"))
    if training["design_sha256"] != sha256_file(design_path):
        raise ValueError("training summary is bound to a different design")
    if training["failed_runs"] or training["completed_runs"] != training["expected_runs"]:
        raise ValueError("full-corpus training grid is incomplete")

    development_seeds = tuple(int(value) for value in design["development_seeds"])
    evaluation_seeds = tuple(int(value) for value in design["evaluation_seeds"])
    epsilons = tuple(float(value) for value in design["candidate_epsilon_targets"])
    actions = tuple(action_id(value) for value in epsilons)
    weights = tuple(float(value) for value in design["release_position_value_weights"])
    if len(weights) != int(design["release_horizon"]):
        raise ValueError("release weights must match the release horizon")
    record_map = _record_map(training["records"])
    dataset_ids = sorted({key[0] for key in record_map})
    expected_keys = {
        (dataset_id, seed, action)
        for dataset_id in dataset_ids
        for seed in (*development_seeds, *evaluation_seeds)
        for action in actions
    }
    if set(record_map) != expected_keys:
        missing = sorted(expected_keys - set(record_map))[:5]
        extra = sorted(set(record_map) - expected_keys)[:5]
        raise ValueError(f"training grid mismatch; missing={missing}, extra={extra}")
    all_artifact_hashes_valid = all(
        artifact_hashes_valid(record) for record in training["records"]
    )
    all_attack_counts_valid = all(
        attack_counts_valid(record) for record in training["records"]
    )
    all_training_accountants_valid = all(
        accountant_valid(record) for record in training["records"]
    )
    if not all_artifact_hashes_valid:
        raise ValueError("a full-corpus artifact is missing or has a mismatched hash")
    if not all_attack_counts_valid:
        raise ValueError("a full-corpus attack confusion table is inconsistent")
    if not all_training_accountants_valid:
        raise ValueError("a full-corpus accountant ledger failed independent replay")

    family_confidence = float(design["familywise_confidence"])
    per_action_confidence = 1.0 - (1.0 - family_confidence) / len(actions)
    reliability_floor = float(design["utility_reliability_floor"])
    attack_tolerance = float(design["membership_floor_tolerance_at_target_fpr"])
    action_statistics: list[dict[str, Any]] = []
    dataset_stats: dict[int, dict[str, dict[str, Any]]] = defaultdict(dict)
    for dataset_id in dataset_ids:
        for action in actions:
            dev = [record_map[(dataset_id, seed, action)] for seed in development_seeds]
            evaluation = [record_map[(dataset_id, seed, action)] for seed in evaluation_seeds]
            dev_passes = [utility_pass(record, design) for record in dev]
            eval_passes = [utility_pass(record, design) for record in evaluation]
            lower, upper = one_sided_clopper_pearson(
                sum(dev_passes), len(dev_passes), per_action_confidence
            )
            eval_lower, eval_upper = one_sided_clopper_pearson(
                sum(eval_passes), len(eval_passes), 0.95
            )
            all_accountants_valid = all(accountant_valid(record) for record in dev)
            any_attack_block = any(attack_blocks(record, attack_tolerance) for record in dev)
            transcript_counts = Counter(
                (
                    "utility-pass" if utility_pass(record, design) else "utility-fail",
                    "accountant-valid" if accountant_valid(record) else "accountant-invalid",
                    "attack-block" if attack_blocks(record, attack_tolerance) else "no-attack-block",
                )
                for record in dev
            )
            stat = {
                "dataset_id": dataset_id,
                "dataset_name": dev[0]["dataset_name"],
                "action": action,
                "epsilon_target": float(dev[0]["epsilon_target"]),
                "development_runs": len(dev),
                "development_utility_passes": sum(dev_passes),
                "development_utility_pass_rate": sum(dev_passes) / len(dev_passes),
                "development_simultaneous_lower": lower,
                "development_one_sided_upper": upper,
                "development_mean_balanced_accuracy": sum(
                    float(record["utility"]["balanced_accuracy"]) for record in dev
                )
                / len(dev),
                "evaluation_runs": len(evaluation),
                "evaluation_utility_passes": sum(eval_passes),
                "evaluation_utility_pass_rate": sum(eval_passes) / len(eval_passes),
                "evaluation_lower_95": eval_lower,
                "evaluation_upper_95": eval_upper,
                "evaluation_mean_balanced_accuracy": sum(
                    float(record["utility"]["balanced_accuracy"]) for record in evaluation
                )
                / len(evaluation),
                "all_development_accountants_valid": all_accountants_valid,
                "development_attack_block": any_attack_block,
                "utility_certified": (
                    all_accountants_valid and not any_attack_block and lower >= reliability_floor
                ),
                "evaluation_oracle_acceptable": (
                    all(accountant_valid(record) for record in evaluation)
                    and not any(attack_blocks(record, attack_tolerance) for record in evaluation)
                    and sum(eval_passes) / len(eval_passes) >= reliability_floor
                ),
                "worst_development_delta": max(
                    float(record["target_accountant"]["delta"]) for record in dev
                ),
                "development_membership_counts": {
                    name: sum(int(record["attack"][name]) for record in dev)
                    for name in ("true_positives", "false_positives", "true_negatives", "false_negatives")
                },
                "evaluation_membership_counts": {
                    name: sum(int(record["attack"][name]) for record in evaluation)
                    for name in ("true_positives", "false_positives", "true_negatives", "false_negatives")
                },
                "development_evidence_law": [
                    {
                        "transcript": list(transcript),
                        "count": count,
                        "probability": count / len(dev),
                    }
                    for transcript, count in sorted(transcript_counts.items())
                ],
            }
            action_statistics.append(stat)
            dataset_stats[dataset_id][action] = stat

    scenarios: list[dict[str, Any]] = []
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_temp = raw_path.with_name(f"{raw_path.name}.tmp")
    raw_handle = gzip.open(raw_temp, "wt", encoding="utf-8")
    raw_handle.write(
        json.dumps(
            {
                "study_id": design["study_id"],
                "design_sha256": sha256_file(design_path),
            },
            sort_keys=True,
            separators=(",", ":"),
        )[:-1]
        + ',"rows":['
    )
    raw_count = 0
    method_totals: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for dataset_id in dataset_ids:
        stats = dataset_stats[dataset_id]
        dev_values = {action: stats[action]["development_mean_balanced_accuracy"] for action in actions}
        eval_values = {action: stats[action]["evaluation_mean_balanced_accuracy"] for action in actions}
        primary_eligible = {action: bool(stats[action]["utility_certified"]) for action in actions}
        point_eligible = {
            action: (
                stats[action]["all_development_accountants_valid"]
                and not stats[action]["development_attack_block"]
                and stats[action]["development_utility_pass_rate"] >= reliability_floor
            )
            for action in actions
        }
        oracle_eligible = {
            action: bool(stats[action]["evaluation_oracle_acceptable"]) for action in actions
        }
        for profile in design["profiles"]:
            group_size = int(profile["group_size_bound"])
            costs = {
                action: group_privacy(
                    float(stats[action]["epsilon_target"]),
                    float(stats[action]["worst_development_delta"]),
                    group_size,
                )
                for action in actions
            }
            epsilon_budget = float(profile["portfolio_epsilon_budget"])
            delta_budget = float(profile["portfolio_delta_budget"])
            primary = choose_joint_allocation(
                actions=actions,
                eligible=primary_eligible,
                values=dev_values,
                costs=costs,
                weights=weights,
                epsilon_budget=epsilon_budget,
                delta_budget=delta_budget,
            )
            point = choose_joint_allocation(
                actions=actions,
                eligible=point_eligible,
                values=dev_values,
                costs=costs,
                weights=weights,
                epsilon_budget=epsilon_budget,
                delta_budget=delta_budget,
            )
            greedy = choose_greedy_allocation(
                actions=actions,
                eligible=primary_eligible,
                values=dev_values,
                costs=costs,
                weights=weights,
                epsilon_budget=epsilon_budget,
                delta_budget=delta_budget,
            )
            oracle = choose_joint_allocation(
                actions=actions,
                eligible=oracle_eligible,
                values=eval_values,
                costs=costs,
                weights=weights,
                epsilon_budget=epsilon_budget,
                delta_budget=delta_budget,
            )
            methods = {
                "simultaneous-joint": primary,
                "point-estimate-joint": point,
                "simultaneous-greedy": greedy,
                "fail-closed-refusal": tuple(REFUSE for _ in weights),
            }
            oracle_value = _allocation_value(oracle, eval_values, weights)
            oracle_releases = sum(action != REFUSE for action in oracle)
            for method, allocation in methods.items():
                epsilon_used, delta_used = _allocation_cost(allocation, costs)
                releases = sum(action != REFUSE for action in allocation)
                proxy_false_clears = sum(
                    action != REFUSE and not oracle_eligible[action] for action in allocation
                )
                evaluation_value = _allocation_value(allocation, eval_values, weights)
                realised_failures = 0
                realised_action_checks = 0
                portfolio_successes = 0
                combinations = 0
                for seed_tuple in itertools.product(evaluation_seeds, repeat=len(weights)):
                    combinations += 1
                    failures = 0
                    for position, (action, seed) in enumerate(
                        zip(allocation, seed_tuple, strict=True)
                    ):
                        if action == REFUSE:
                            continue
                        realised_action_checks += 1
                        passed = utility_pass(record_map[(dataset_id, seed, action)], design)
                        if not passed:
                            failures += 1
                    realised_failures += failures
                    portfolio_successes += int(failures == 0)
                    raw_row = {
                        "dataset_id": dataset_id,
                        "profile_id": profile["profile_id"],
                        "method": method,
                        "evaluation_seeds": list(seed_tuple),
                        "allocation": list(allocation),
                        "released_positions": releases,
                        "utility_failure_count": failures,
                        "all_released_positions_pass": failures == 0,
                    }
                    if raw_count:
                        raw_handle.write(",")
                    raw_handle.write(
                        json.dumps(raw_row, sort_keys=True, separators=(",", ":"))
                    )
                    raw_count += 1
                scenario = {
                    "dataset_id": dataset_id,
                    "dataset_name": stats[actions[0]]["dataset_name"],
                    "profile_id": profile["profile_id"],
                    "method": method,
                    "allocation": list(allocation),
                    "release_count": releases,
                    "release_yield": releases / len(weights),
                    "composed_epsilon": epsilon_used,
                    "composed_delta": delta_used,
                    "privacy_budget_valid": (
                        epsilon_used <= epsilon_budget + 1e-12
                        and delta_used <= delta_budget + 1e-15
                    ),
                    "proxy_false_clear_actions": proxy_false_clears,
                    "proxy_false_clear_rate": (
                        proxy_false_clears / releases if releases else None
                    ),
                    "realised_utility_failures": realised_failures,
                    "realised_action_checks": realised_action_checks,
                    "realised_utility_failure_rate": (
                        realised_failures / realised_action_checks
                        if realised_action_checks
                        else None
                    ),
                    "evaluation_portfolios": combinations,
                    "portfolio_successes": portfolio_successes,
                    "portfolio_success_rate": portfolio_successes / combinations,
                    "evaluation_weighted_utility": evaluation_value,
                    "oracle_allocation": list(oracle),
                    "oracle_release_count": oracle_releases,
                    "oracle_weighted_utility": oracle_value,
                    "release_count_shortfall": max(0, oracle_releases - releases),
                    "utility_regret": max(0.0, oracle_value - evaluation_value),
                }
                scenarios.append(scenario)
                totals = method_totals[method]
                totals["scenarios"] += 1
                totals["requested_positions"] += len(weights)
                totals["released_positions"] += releases
                totals["proxy_false_clear_actions"] += proxy_false_clears
                totals["realised_utility_failures"] += realised_failures
                totals["realised_action_checks"] += realised_action_checks
                totals["evaluation_portfolios"] += combinations
                totals["portfolio_successes"] += portfolio_successes
                totals["utility_regret"] += max(0.0, oracle_value - evaluation_value)
                totals["privacy_budget_violations"] += int(
                    not scenario["privacy_budget_valid"]
                )

    aggregate_methods: list[dict[str, Any]] = []
    for method, totals in sorted(method_totals.items()):
        released = int(totals["released_positions"])
        false_clears = int(totals["proxy_false_clear_actions"])
        method_scenarios = [row for row in scenarios if row["method"] == method]
        released_dataset_ids = {
            row["dataset_id"] for row in method_scenarios if row["release_count"]
        }
        false_clear_dataset_ids = {
            row["dataset_id"]
            for row in method_scenarios
            if row["proxy_false_clear_actions"]
        }
        action_checks = int(totals["realised_action_checks"])
        aggregate_methods.append(
            {
                "method": method,
                "scenarios": int(totals["scenarios"]),
                "requested_positions": int(totals["requested_positions"]),
                "released_positions": released,
                "release_yield": released / totals["requested_positions"],
                "proxy_false_clear_actions": false_clears,
                "proxy_false_clear_rate": false_clears / released if released else None,
                "datasets_with_releases": len(released_dataset_ids),
                "datasets_with_proxy_false_clear": len(false_clear_dataset_ids),
                "aggregate_inference": (
                    "descriptive only: release positions and profiles are clustered "
                    f"within {len(dataset_ids)} fixed OpenML-CC18 datasets"
                ),
                "realised_utility_failures": int(totals["realised_utility_failures"]),
                "realised_action_checks": action_checks,
                "realised_utility_failure_rate": (
                    totals["realised_utility_failures"] / action_checks
                    if action_checks
                    else None
                ),
                "portfolio_success_rate": (
                    totals["portfolio_successes"] / totals["evaluation_portfolios"]
                ),
                "mean_utility_regret": totals["utility_regret"] / totals["scenarios"],
                "privacy_budget_violations": int(totals["privacy_budget_violations"]),
            }
        )

    original_dataset_ids = {
        int(value) for value in design.get("original_eight_dataset_ids", [])
    }
    extension_strata = {
        "original-observed-subset": original_dataset_ids & set(dataset_ids),
        "added-full-corpus-extension": set(dataset_ids) - original_dataset_ids,
    }
    stratified_aggregate_methods: list[dict[str, Any]] = []
    for stratum, stratum_ids in extension_strata.items():
        for method in sorted(method_totals):
            rows = [
                row
                for row in scenarios
                if row["method"] == method and row["dataset_id"] in stratum_ids
            ]
            requested = len(rows) * len(weights)
            released = sum(int(row["release_count"]) for row in rows)
            action_checks = sum(int(row["realised_action_checks"]) for row in rows)
            evaluation_portfolios = sum(int(row["evaluation_portfolios"]) for row in rows)
            stratified_aggregate_methods.append(
                {
                    "stratum": stratum,
                    "method": method,
                    "datasets": len(stratum_ids),
                    "scenarios": len(rows),
                    "requested_positions": requested,
                    "released_positions": released,
                    "release_yield": released / requested if requested else None,
                    "proxy_false_clear_actions": sum(
                        int(row["proxy_false_clear_actions"]) for row in rows
                    ),
                    "realised_utility_failures": sum(
                        int(row["realised_utility_failures"]) for row in rows
                    ),
                    "realised_action_checks": action_checks,
                    "realised_utility_failure_rate": (
                        sum(int(row["realised_utility_failures"]) for row in rows)
                        / action_checks
                        if action_checks
                        else None
                    ),
                    "portfolio_success_rate": (
                        sum(int(row["portfolio_successes"]) for row in rows)
                        / evaluation_portfolios
                        if evaluation_portfolios
                        else None
                    ),
                    "mean_utility_regret": (
                        sum(float(row["utility_regret"]) for row in rows) / len(rows)
                        if rows
                        else None
                    ),
                    "privacy_budget_violations": sum(
                        int(not row["privacy_budget_valid"]) for row in rows
                    ),
                }
            )

    all_accountants_valid = all(
        stat["all_development_accountants_valid"] for stat in action_statistics
    )
    primary_rows = [row for row in scenarios if row["method"] == "simultaneous-joint"]
    summary = {
        "study_id": design["study_id"],
        "design_status": design["design_status"],
        "extension_disclosure": design.get("extension_disclosure"),
        "design_sha256": sha256_file(design_path),
        "training_summary_sha256": sha256_file(training_path),
        "claim_boundary": design["claim_boundary"],
        "datasets": len(dataset_ids),
        "candidate_mechanisms": len(actions),
        "development_runs": len(dataset_ids) * len(actions) * len(development_seeds),
        "evaluation_runs": len(dataset_ids) * len(actions) * len(evaluation_seeds),
        "trained_model_cells": training["completed_runs"],
        "trained_ml_artifacts": training["completed_runs"] * 3,
        "profiles": len(design["profiles"]),
        "release_horizon": len(weights),
        "exact_evaluation_portfolios_per_scenario": len(evaluation_seeds) ** len(weights),
        "raw_decision_rows": raw_count,
        "action_statistics": action_statistics,
        "scenario_results": scenarios,
        "aggregate_methods": aggregate_methods,
        "stratified_aggregate_methods": stratified_aggregate_methods,
        "validation": {
            "training_grid_complete": True,
            "all_development_accountants_valid": all_accountants_valid,
            "all_training_accountants_valid": all_training_accountants_valid,
            "all_training_artifact_hashes_valid": all_artifact_hashes_valid,
            "all_training_attack_counts_valid": all_attack_counts_valid,
            "all_selected_privacy_budgets_valid": all(
                row["privacy_budget_valid"] for row in scenarios
            ),
            "primary_proxy_false_clear_actions": sum(
                row["proxy_false_clear_actions"] for row in primary_rows
            ),
            "primary_release_positions": sum(row["release_count"] for row in primary_rows),
            "representative_government_release_yield_identified": False,
        },
    }
    analysis = {
        "study_id": design["study_id"],
        "design_status": design["design_status"],
        "claim_boundary": design["claim_boundary"],
        "estimands": {
            row["method"]: {
                key: value
                for key, value in row.items()
                if key
                not in {
                    "method",
                    "scenarios",
                    "requested_positions",
                    "realised_action_checks",
                    "evaluation_portfolios",
                }
            }
            for row in aggregate_methods
        },
        "stratified_estimands": stratified_aggregate_methods,
        "interpretation_rules": {
            "privacy_failure": "any invalid accountant or composed epsilon/delta budget",
            "proxy_false_clear": "a selected mechanism has held-out pass probability below the fixed reliability floor",
            "realised_utility_failure": "a selected mechanism instance fails the two-part utility contract",
            "external_validity": (
                f"descriptive for the fixed {len(dataset_ids)}-dataset OpenML-CC18 "
                "benchmark frame only; not representative of government release requests"
            ),
        },
        "validation": summary["validation"],
    }
    raw_handle.write("]}\n")
    raw_handle.close()
    raw_temp.replace(raw_path)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(summary_path, summary)
    write_json(analysis_path, analysis)
    print(
        json.dumps(
            {
                "summary": str(summary_path),
                "analysis": str(analysis_path),
                "raw": str(raw_path),
                "trained_model_cells": summary["trained_model_cells"],
                "raw_decision_rows": summary["raw_decision_rows"],
                "aggregate_methods": aggregate_methods,
            },
            indent=2,
        )
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--design", type=Path, default=DEFAULT_DESIGN)
    parser.add_argument("--training", type=Path, default=DEFAULT_TRAINING)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--analysis", type=Path, default=DEFAULT_ANALYSIS)
    parser.add_argument("--raw", type=Path, default=DEFAULT_RAW)
    args = parser.parse_args()
    analyze(args.design, args.training, args.summary, args.analysis, args.raw)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
