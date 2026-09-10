"""Locally freeze and run a new synthetic independent-model study.

Only numpy and the standard library are required. No downloads, historical
evidence writes, library assurance/authorization claims, or hidden retries.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from fractions import Fraction as F
import hashlib
import json
from math import factorial
from pathlib import Path
import platform
import traceback

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
REGISTRATION = ROOT / "reproduction/independent-models-synthetic-v1/registration.json"
VERIFIER = ROOT / "academic/scripts/verify_independent_model_study.py"
GRID_INTEGERS = np.array([(a, b) for a in (-3, -2, -1, 1, 2, 3)
                          for b in (-3, -2, -1, 1, 2, 3)], dtype=np.int64)
GRID = GRID_INTEGERS / 3
BASE_LABELS = (10 * GRID_INTEGERS[:, 0] + 7 * GRID_INTEGERS[:, 1] > 0).astype(np.uint8)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def rational(value):
    value = F(value)
    return {"numerator": value.numerator, "denominator": value.denominator, "display": float(value)}


def from_rational(value):
    return F(value["numerator"], value["denominator"])


def taylor_exp_lower(value, degree=32):
    return sum((F(value) ** k / factorial(k) for k in range(degree + 1)), F(0))


def allocated_failure_bound(reg):
    m = len(reg["families"]) * reg["models_per_family"]
    channels = m * len(reg["regimes"]) * len(reg["controls"])
    utilities = m * len(reg["controls"])
    e = F(reg["radius"])
    return (4 * channels / taylor_exp_lower(2 * reg["channel_samples_per_state"] * e * e)
            + utilities / taylor_exp_lower(2 * reg["utility_samples"] * e * e))


def fit_logistic(x, y, spec):
    design = np.column_stack((np.ones(len(x)), x))
    weights = np.zeros(design.shape[1])
    for _ in range(spec["iterations"]):
        scores = np.clip(design @ weights, -40, 40)
        probability = 1 / (1 + np.exp(-scores))
        regularizer = weights.copy()
        regularizer[0] = 0
        weights -= spec["learning_rate"] * (design.T @ (probability - y) / len(y)
                                           + spec["ridge"] * regularizer)
    predictions = (np.column_stack((np.ones(len(GRID)), GRID)) @ weights >= 0).astype(np.uint8)
    return {"weights": weights.tolist()}, predictions


def fit_cart(x, y, spec):
    def node(indices, depth):
        outcomes = y[indices]
        ones = int(outcomes.sum())
        result = {"label": int(ones * 2 > len(indices)), "samples": len(indices)}
        if depth == spec["max_depth"] or ones in (0, len(indices)):
            return result
        best = None
        for feature in range(x.shape[1]):
            values = np.unique(x[indices, feature])
            for threshold in (values[:-1] + values[1:]) / 2:
                mask = x[indices, feature] <= threshold
                left, right = indices[mask], indices[~mask]
                if min(len(left), len(right)) < spec["minimum_leaf"]:
                    continue
                # Exact impurity ordering; no floating tie ambiguity.
                impurity = sum((F(2 * int(y[part].sum()) * (len(part) - int(y[part].sum())), len(part))
                                for part in (left, right)), F(0))
                key = (impurity, feature, float(threshold))
                if best is None or key < best[0]:
                    best = (key, left, right)
        if best is not None:
            key, left, right = best
            result.update(feature=key[1], threshold=key[2], left=node(left, depth + 1), right=node(right, depth + 1))
        return result

    tree = node(np.arange(len(y)), 0)

    def predict(row):
        current = tree
        while "feature" in current:
            current = current["left" if row[current["feature"]] <= current["threshold"] else "right"]
        return current["label"]

    return tree, np.array([predict(row) for row in GRID], dtype=np.uint8)


def conditional_weights(q, state):
    # Exact P(X|S) expressed with a shared integer denominator.
    weights = []
    for label in BASE_LABELS:
        py = F(9 if label else 1, 10)
        ps1 = q + (1 - 2 * q) * py
        probability = ps1 if state else 1 - ps1
        weight = probability * 20
        assert weight.denominator == 1
        weights.append(int(weight))
    assert sum(weights) == 360
    return np.array(weights, dtype=np.int64)


def oracle(predictions, q, rho):
    rows = []
    for state in (0, 1):
        raw = F(int(conditional_weights(q, state)[predictions == 1].sum()), 360)
        rows.append(rho + (1 - 2 * rho) * raw)
    raw_utility = F(int(np.where(predictions == BASE_LABELS, 9, 1).sum()), 360)
    utility = rho + (1 - 2 * rho) * raw_utility
    risk = F(1, 2) + abs(rows[1] - rows[0]) / 2
    assert risk == F(1, 2) + (1 - 2 * q) * abs(utility - F(1, 2))
    return rows, risk, utility


def risk_interval(counts, n, radius):
    empirical = [F(value, n) for value in counts]
    lower = [max(F(0), value - radius) for value in empirical]
    upper = [min(F(1), value + radius) for value in empirical]
    low = F(1, 2) + max(F(0), lower[0] - upper[1], lower[1] - upper[0]) / 2
    high = F(1, 2) + max(abs(lower[0] - upper[1]), abs(upper[0] - lower[1])) / 2
    point = F(1, 2) + abs(empirical[0] - empirical[1]) / 2
    return low, high, point


def random_stream(seed, *coordinates):
    return np.random.default_rng(np.random.SeedSequence([seed, *coordinates]))


def selected(rows, method, threshold, minimum):
    if method == "always_refuse":
        return None
    risk_key, utility_key = (("risk_upper", "utility_lower") if method == "simultaneous_bounds"
                            else ("risk_point", "utility_point") if method == "point_estimates"
                            else ("oracle_risk", "oracle_utility"))
    feasible = [row for row in rows if from_rational(row[risk_key]) <= threshold
                and from_rational(row[utility_key]) >= minimum]
    return max(feasible, key=lambda row: F(row["rho"]))["rho"] if feasible else None


def evaluate_model(reg, family, family_index, index, directory):
    seed, n, nu = reg["seed"], reg["channel_samples_per_state"], reg["utility_samples"]
    radius, threshold, minimum = F(reg["radius"]), F(reg["risk_threshold"]), F(reg["utility_minimum"])
    train_rng = random_stream(seed, family_index, index, 0)
    train_x = train_rng.integers(0, len(GRID), size=reg["training_samples"], dtype=np.uint8)
    train_noise = (train_rng.integers(0, 10, size=len(train_x)) == 0).astype(np.uint8)
    train_y = BASE_LABELS[train_x] ^ train_noise
    np.savez_compressed(directory / "training.npz", x_index=train_x, y=train_y)
    fit = fit_logistic if family == "logistic" else fit_cart
    artifact, predictions = fit(GRID[train_x], train_y, reg["training"][family])
    arrays = {"training_x_index": train_x, "training_y": train_y}
    write_json(directory / "model.json", {"family": family, "model_index": index, "artifact": artifact,
                                         "prediction_vector": predictions.tolist()})
    utility = {}
    for control_index, control in enumerate(reg["controls"]):
        rho = F(control)
        rng = random_stream(seed, family_index, index, 1, control_index)
        x = rng.integers(0, len(GRID), size=nu, dtype=np.uint8)
        y = BASE_LABELS[x] ^ (rng.integers(0, 10, size=nu) == 0).astype(np.uint8)
        flip = (rng.integers(0, 10, size=nu) < int(rho * 10)).astype(np.uint8)
        successes = int(((predictions[x] ^ flip) == y).sum())
        point = F(successes, nu)
        utility[control] = (successes, point, max(F(0), point - radius))
        arrays.update({f"u{control_index}_x": x, f"u{control_index}_y": y, f"u{control_index}_flip": flip})
    rows, selections = [], []
    for regime_index, (regime, qtext) in enumerate(reg["regimes"].items()):
        q = F(qtext)
        group = []
        for control_index, control in enumerate(reg["controls"]):
            rho, counts = F(control), []
            oracle_rows, true_risk, true_utility = oracle(predictions, q, F(control))
            for state in (0, 1):
                rng = random_stream(seed, family_index, index, 2, regime_index, control_index, state)
                cumulative = conditional_weights(q, state).cumsum()
                x = np.searchsorted(cumulative, rng.integers(0, 360, size=n), side="right").astype(np.uint8)
                flip = (rng.integers(0, 10, size=n) < int(rho * 10)).astype(np.uint8)
                counts.append(int((predictions[x] ^ flip).sum()))
                prefix = f"r{regime_index}_c{control_index}_s{state}"
                arrays.update({prefix + "_x": x, prefix + "_flip": flip})
            low, high, point = risk_interval(counts, n, radius)
            us, upoint, ulow = utility[control]
            row = {"family": family, "model_index": index, "regime": regime, "q": qtext, "rho": control,
                   "state_output_one_counts": counts, "trials_per_state": n, "utility_successes": us,
                   "utility_trials": nu, "oracle_channel_one": [rational(p) for p in oracle_rows],
                   "oracle_risk": rational(true_risk), "oracle_utility": rational(true_utility),
                   "risk_lower": rational(low), "risk_upper": rational(high), "risk_point": rational(point),
                   "utility_lower": rational(ulow), "utility_point": rational(upoint),
                   "risk_covered": low <= true_risk <= high, "utility_lower_valid": ulow <= true_utility,
                   "channel_cells_covered": all(abs(F(c, n) - p) <= radius for c, p in zip(counts, oracle_rows)),
                   "decision": "BLOCK" if low > threshold else "CLEAR" if high <= threshold else "HOLD"}
            group.append(row)
        oracle_choice = selected(group, "oracle", threshold, minimum)
        for method in reg["comparators"]:
            choice = selected(group, method, threshold, minimum)
            chosen = next((row for row in group if row["rho"] == choice), None)
            privacy_violation = bool(chosen and from_rational(chosen["oracle_risk"]) > threshold)
            utility_violation = bool(chosen and from_rational(chosen["oracle_utility"]) < minimum)
            selections.append({"family": family, "model_index": index, "regime": regime, "method": method,
                "chosen_rho": choice, "oracle_chosen_rho": oracle_choice, "oracle_feasible": oracle_choice is not None,
                "privacy_violation": privacy_violation, "utility_violation": utility_violation,
                "unsafe_selection": privacy_violation or utility_violation,
                "missed_oracle_opportunity": oracle_choice is not None and choice is None,
                "useful_selection": chosen is not None and not (privacy_violation or utility_violation),
                "correct_redesign": oracle_choice is None and choice is None,
                "oracle_selector_agreement": choice == oracle_choice})
        rows.extend(group)
    np.savez_compressed(directory / "draws.npz", **arrays)
    record = {"family": family, "model_index": index, "status": "completed", "rows": rows, "selections": selections,
              "artifact_sha256": sha(directory / "model.json"), "draws_sha256": sha(directory / "draws.npz"),
              "training_sha256": sha(directory / "training.npz")}
    write_json(directory / "record.json", record)
    return record


def summarize(reg, records):
    groups = []
    planned = len(reg["families"]) * reg["models_per_family"]
    complete = len(records) == planned and all(r["status"] == "completed" for r in records)
    for family in reg["families"]:
        for regime in reg["regimes"]:
            for method in reg["comparators"]:
                selections = [s for r in records for s in r.get("selections", [])
                              if (s["family"], s["regime"], s["method"]) == (family, regime, method)]
                metrics = {key: sum(s[key] for s in selections) for key in
                           ("oracle_feasible", "privacy_violation", "utility_violation", "unsafe_selection",
                            "missed_oracle_opportunity", "useful_selection", "correct_redesign", "oracle_selector_agreement")}
                intervals = {}
                if complete and method == "simultaneous_bounds":
                    for endpoint in ("unsafe_selection", "missed_oracle_opportunity"):
                        rate = F(metrics[endpoint], len(selections))
                        intervals[endpoint] = {"count": metrics[endpoint], "denominator": len(selections),
                            "estimate": rational(rate), "lower": rational(max(F(0), rate - F(1, 5))),
                            "upper": rational(min(F(1), rate + F(1, 5)))}
                groups.append({"family": family, "regime": regime, "method": method,
                    "planned_models": reg["models_per_family"],
                    "attempted_models": sum(r["family"] == family for r in records),
                    "evaluated_models": len(selections), **metrics, "primary_intervals": intervals,
                    "useful_given_oracle_feasible": rational(F(metrics["useful_selection"], metrics["oracle_feasible"]))
                        if metrics["oracle_feasible"] else None})
    rows = [row for record in records for row in record.get("rows", [])]
    utilities = {(row["family"], row["model_index"], row["rho"]): row["utility_lower_valid"] for row in rows}
    return {"planned_fits": planned, "confirmatory_complete": complete,
            "attempted_fits": len(records), "completed_fits": sum(r["status"] == "completed" for r in records),
            "failed_fits": [r for r in records if r["status"] != "completed"], "candidate_rows": len(rows),
            "channel_undercoverage": sum(not row["channel_cells_covered"] for row in rows),
            "risk_undercoverage": sum(not row["risk_covered"] for row in rows),
            "invalid_utility_lower_bounds": sum(not valid for valid in utilities.values()),
            "simultaneous_evaluation_failure_upper": rational(allocated_failure_bound(reg)),
            "primary_model_mean_failure_upper": rational(32 / taylor_exp_lower(F(2 * reg["models_per_family"], 25))) if complete else None,
            "groups": groups, "scope_limits": reg["scope_limits"]}


def freeze(output):
    output.mkdir(parents=True, exist_ok=False)
    reg = json.loads(REGISTRATION.read_text(encoding="utf-8"))
    assert allocated_failure_bound(reg) < F(1, 20)
    assert 32 / taylor_exp_lower(F(2 * reg["models_per_family"], 25)) < F(1, 20)
    write_json(output / "registration.json", reg)
    # Source bytes retained for independent replay of this exact study version.
    (output / "runner.py").write_bytes(Path(__file__).read_bytes())
    (output / "verifier.py").write_bytes(VERIFIER.read_bytes())
    write_json(output / "FROZEN.json", {"study_id": reg["study_id"], "frozen_at": datetime.now(timezone.utc).isoformat(),
        "registration_sha256": sha(output / "registration.json"), "runner_sha256": sha(output / "runner.py"),
        "verifier_sha256": sha(output / "verifier.py"),
        "python": platform.python_version(), "numpy": np.__version__,
        "external_timestamp_verified": False, "confirmatory_fits_started": False})
    print("Design frozen; no confirmatory model fitted:", output, flush=True)


def run(output):
    frozen = json.loads((output / "FROZEN.json").read_text(encoding="utf-8"))
    if sha(output / "registration.json") != frozen["registration_sha256"] or sha(Path(__file__)) != frozen["runner_sha256"]:
        raise ValueError("frozen registration/runner mismatch; create a new registered run")
    if sha(VERIFIER) != frozen["verifier_sha256"]:
        raise ValueError("verifier differs from frozen source")
    if (output / "STARTED.json").exists():
        raise ValueError("run already started; never overwrite or silently resume historical attempts")
    if (platform.python_version(), np.__version__) != (frozen["python"], frozen["numpy"]):
        raise ValueError("runtime differs from frozen Python/NumPy versions")
    reg = json.loads((output / "registration.json").read_text(encoding="utf-8"))
    write_json(output / "STARTED.json", {"started_at": datetime.now(timezone.utc).isoformat(), "frozen_sha256": sha(output / "FROZEN.json"),
        "python": platform.python_version(), "numpy": np.__version__})
    records = []
    for family_index, family in enumerate(reg["families"]):
        for index in range(reg["models_per_family"]):
            directory = output / family / f"model-{index:03d}"
            directory.mkdir(parents=True, exist_ok=False)
            try:
                record = evaluate_model(reg, family, family_index, index, directory)
            except Exception:
                record = {"family": family, "model_index": index, "status": "failed", "traceback": traceback.format_exc()}
                write_json(directory / "FAILED.json", record)
                records.append(record)
                write_json(output / "PARTIAL.json", summarize(reg, records))
                raise  # Retain evidence and stop; never replace a failed fit.
            records.append(record)
            if (index + 1) % 12 == 0:
                print(f"Completed {family}: {index + 1}/{reg['models_per_family']} independent fits", flush=True)
    summary = summarize(reg, records)
    write_json(output / "summary.json", summary)
    write_json(output / "COMPLETE.json", {"completed_at": datetime.now(timezone.utc).isoformat(), "frozen_sha256": sha(output / "FROZEN.json"),
        "started_sha256": sha(output / "STARTED.json"), "summary_sha256": sha(output / "summary.json"),
        "record_sha256s": {str(path.relative_to(output)): sha(path) for path in sorted(output.glob("*/model-*/record.json"))}})
    print(json.dumps({key: summary[key] for key in ("attempted_fits", "completed_fits", "candidate_rows", "risk_undercoverage")}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("freeze", "run"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    (freeze if args.operation == "freeze" else run)(args.output.resolve())


if __name__ == "__main__":
    main()
