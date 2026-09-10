"""Independent recount/oracle verifier; never imports the training runner.

Reconstructs predictions from saved artifacts, recounts retained observations,
enumerates the joint finite world, and replays selection and primary intervals.
It verifies one logical transcript, not a production interface or its timing.
"""
import argparse
from datetime import datetime, timezone
from fractions import Fraction as F
import hashlib
import json
from math import factorial
from pathlib import Path

import numpy as np


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def frac(value):
    return F(value["numerator"], value["denominator"])


def require(condition, message):
    if not condition:
        raise ValueError(message)


def prediction_vector(artifact, grid):
    if artifact["family"] == "logistic":
        weights = artifact["artifact"]["weights"]
        return (np.column_stack((np.ones(len(grid)), grid)) @ weights >= 0).astype(np.uint8)
    values = []
    for x in grid:
        node = artifact["artifact"]
        while "feature" in node:
            node = node["left" if x[node["feature"]] <= node["threshold"] else "right"]
        values.append(node["label"])
    return np.array(values, dtype=np.uint8)


def enumerated_oracle(predictions, base, q, rho):
    joint = [[F(0), F(0)], [F(0), F(0)]]
    utility = F(0)
    for i in range(len(base)):
        for task in (0, 1):
            py = F(9 if task == base[i] else 1, 10) / len(base)
            for output in (0, 1):
                prob = py * (1 - rho if output == predictions[i] else rho)
                if output == task:
                    utility += prob
                for secret in (0, 1):
                    joint[secret][output] += prob * (1 - q if secret == task else q)
    require(all(sum(row) == F(1, 2) for row in joint), "secret prior differs from one half")
    risk = sum(max(joint[0][y], joint[1][y]) for y in (0, 1))
    return risk, utility, [2 * joint[state][1] for state in (0, 1)]


def verify(output):
    output = Path(output)
    frozen, started, complete = (read(output / name) for name in ("FROZEN.json", "STARTED.json", "COMPLETE.json"))
    require(sha(output / "registration.json") == frozen["registration_sha256"], "registration hash mismatch")
    require(sha(output / "runner.py") == frozen["runner_sha256"], "frozen runner hash mismatch")
    require(sha(output / "verifier.py") == frozen["verifier_sha256"], "frozen verifier hash mismatch")
    require(sha(Path(__file__)) == frozen["verifier_sha256"], "executing verifier differs from frozen verifier")
    require(sha(output / "FROZEN.json") == started["frozen_sha256"] == complete["frozen_sha256"], "freeze link mismatch")
    require(sha(output / "STARTED.json") == complete["started_sha256"], "start link mismatch")
    require(sha(output / "summary.json") == complete["summary_sha256"], "summary hash mismatch")
    require(datetime.fromisoformat(frozen["frozen_at"]) <= datetime.fromisoformat(started["started_at"])
            <= datetime.fromisoformat(complete["completed_at"]), "local timestamps out of order")
    require((frozen["python"], frozen["numpy"]) == (started["python"], started["numpy"]), "runtime changed")
    reg, summary = read(output / "registration.json"), read(output / "summary.json")
    grid_i = np.array([(a, b) for a in (-3, -2, -1, 1, 2, 3) for b in (-3, -2, -1, 1, 2, 3)])
    grid, base = grid_i / 3, (10 * grid_i[:, 0] + 7 * grid_i[:, 1] > 0).astype(np.uint8)
    n, nu, radius = reg["channel_samples_per_state"], reg["utility_samples"], F(reg["radius"])
    threshold, minimum = F(reg["risk_threshold"]), F(reg["utility_minimum"])
    all_selections, checks, interval_failures, cell_failures, utility_failures = [], 0, 0, 0, set()
    record_paths = []
    for fi, family in enumerate(reg["families"]):
        for index in range(reg["models_per_family"]):
            directory = output / family / f"model-{index:03d}"
            record_path = directory / "record.json"
            record_paths.append(str(record_path.relative_to(output)))
            require(sha(record_path) == complete["record_sha256s"][record_paths[-1]], "record hash mismatch")
            record, artifact = read(record_path), read(directory / "model.json")
            require(record["status"] == "completed", "incomplete fit cannot claim confirmatory results")
            require(sha(directory / "model.json") == record["artifact_sha256"], "model hash mismatch")
            require(sha(directory / "draws.npz") == record["draws_sha256"], "draw hash mismatch")
            require(sha(directory / "training.npz") == record["training_sha256"], "training hash mismatch")
            prediction = prediction_vector(artifact, grid)
            require(prediction.tolist() == artifact["prediction_vector"], "artifact predictions differ")
            with np.load(directory / "draws.npz", allow_pickle=False) as draws, np.load(directory / "training.npz", allow_pickle=False) as training:
                require(np.array_equal(training["x_index"], draws["training_x_index"])
                        and np.array_equal(training["y"], draws["training_y"]), "training draw copies differ")
                require(len(training["x_index"]) == reg["training_samples"], "training sample count differs")
                rng = np.random.default_rng(np.random.SeedSequence([reg["seed"], fi, index, 0]))
                tx = rng.integers(0, 36, size=reg["training_samples"], dtype=np.uint8)
                ty = base[tx] ^ (rng.integers(0, 10, size=len(tx)) == 0).astype(np.uint8)
                require(np.array_equal(tx, training["x_index"]) and np.array_equal(ty, training["y"]), "training stream differs")
                require(len(record["rows"]) == len(reg["regimes"]) * len(reg["controls"])
                        and len(record["selections"]) == len(reg["regimes"]) * len(reg["comparators"]), "candidate/selector inventory differs")
                for ri, (regime, qtext) in enumerate(reg["regimes"].items()):
                    group = [r for r in record["rows"] if r["regime"] == regime]
                    require(len(group) == len(reg["controls"]), "missing or duplicate candidate rows")
                    require({r["rho"] for r in group} == set(reg["controls"]), "control inventory differs")
                    for ci, control in enumerate(reg["controls"]):
                        row = next(r for r in group if r["rho"] == control)
                        counts = []
                        for state in (0, 1):
                            prefix = f"r{ri}_c{ci}_s{state}"
                            x, flips = draws[prefix + "_x"], draws[prefix + "_flip"]
                            require(len(x) == len(flips) == n and np.all(x < 36) and np.all(flips <= 1), "invalid channel draws")
                            q, weights = F(qtext), []
                            for b in base:
                                ps = sum(F(9 if task == b else 1, 10) * (1-q if task == state else q) for task in (0, 1))
                                weights.append(int(ps * 20))
                            rng = np.random.default_rng(np.random.SeedSequence([reg["seed"], fi, index, 2, ri, ci, state]))
                            expected_x = np.searchsorted(np.cumsum(weights), rng.integers(0, 360, size=n), side="right").astype(np.uint8)
                            expected_f = (rng.integers(0, 10, size=n) < int(F(control) * 10)).astype(np.uint8)
                            require(np.array_equal(x, expected_x) and np.array_equal(flips, expected_f), "conditional sampling stream differs")
                            counts.append(int((prediction[x] ^ flips).sum()))
                        require(counts == row["state_output_one_counts"], "recounted channel samples differ")
                        ux, uy, uf = (draws[f"u{ci}_" + suffix] for suffix in ("x", "y", "flip"))
                        require(len(ux) == len(uy) == len(uf) == nu, "utility draw count differs")
                        rng = np.random.default_rng(np.random.SeedSequence([reg["seed"], fi, index, 1, ci]))
                        ex = rng.integers(0, 36, size=nu, dtype=np.uint8)
                        ey = base[ex] ^ (rng.integers(0, 10, size=nu) == 0).astype(np.uint8)
                        ef = (rng.integers(0, 10, size=nu) < int(F(control) * 10)).astype(np.uint8)
                        require(np.array_equal(ux, ex) and np.array_equal(uy, ey) and np.array_equal(uf, ef), "utility sampling stream differs")
                        require(row["trials_per_state"] == n and row["utility_trials"] == nu, "reported trial denominator differs")
                        successes = int(((prediction[ux] ^ uf) == uy).sum())
                        require(successes == row["utility_successes"], "utility recount differs")
                        risk, utility, probabilities = enumerated_oracle(prediction, base, F(qtext), F(control))
                        require(risk == frac(row["oracle_risk"]) and utility == frac(row["oracle_utility"]), "oracle differs")
                        require(probabilities == [frac(p) for p in row["oracle_channel_one"]], "oracle rows differ")
                        ps = [F(c, n) for c in counts]
                        limits = [(max(F(0), p - radius), min(F(1), p + radius)) for p in ps]
                        # Enumerate vertices plus any interval intersection;
                        # |p0-p1| is convex and its minimum is zero on overlap.
                        compatible = [(a, b) for a in limits[0] for b in limits[1]]
                        overlap = max(limits[0][0], limits[1][0])
                        if overlap <= min(limits[0][1], limits[1][1]):
                            compatible.append((overlap, overlap))
                        values = [max(1-a, 1-b)/2 + max(a, b)/2 for a, b in compatible]
                        lower, upper = min(values), max(values)
                        point = max(1-ps[0], 1-ps[1])/2 + max(ps[0], ps[1])/2
                        require((lower, upper, point) == tuple(frac(row[key]) for key in ("risk_lower", "risk_upper", "risk_point")), "interval differs")
                        ulow, upoint = max(F(0), F(successes, nu) - radius), F(successes, nu)
                        require((ulow, upoint) == (frac(row["utility_lower"]), frac(row["utility_point"])), "utility bound differs")
                        require(row["decision"] == ("BLOCK" if lower > threshold else "CLEAR" if upper <= threshold else "HOLD"), "decision differs")
                        covered, cells, uvalid = lower <= risk <= upper, all(abs(p-v) <= radius for p, v in zip(ps, probabilities)), ulow <= utility
                        require((covered, cells, uvalid) == (row["risk_covered"], row["channel_cells_covered"], row["utility_lower_valid"]), "coverage flag differs")
                        interval_failures += not covered
                        cell_failures += not cells
                        if not uvalid:
                            utility_failures.add((family, index, control))
                        checks += 1
                    feasible = lambda riskkey, utilitykey: [r for r in group if frac(r[riskkey]) <= threshold and frac(r[utilitykey]) >= minimum]
                    choose = lambda rows: max((F(r["rho"]) for r in rows), default=None)
                    oracle_choice = choose(feasible("oracle_risk", "oracle_utility"))
                    for selection in [s for s in record["selections"] if s["regime"] == regime]:
                        method = selection["method"]
                        choice = None if method == "always_refuse" else choose(feasible(
                            "risk_upper" if method == "simultaneous_bounds" else "risk_point",
                            "utility_lower" if method == "simultaneous_bounds" else "utility_point"))
                        require(choice == (F(selection["chosen_rho"]) if selection["chosen_rho"] is not None else None), "selection differs")
                        require(oracle_choice == (F(selection["oracle_chosen_rho"]) if selection["oracle_chosen_rho"] is not None else None), "oracle selector differs")
                        chosen = next((r for r in group if F(r["rho"]) == choice), None)
                        pv = bool(chosen and frac(chosen["oracle_risk"]) > threshold)
                        uv = bool(chosen and frac(chosen["oracle_utility"]) < minimum)
                        expected = {"oracle_feasible": oracle_choice is not None, "privacy_violation": pv,
                            "utility_violation": uv, "unsafe_selection": pv or uv,
                            "missed_oracle_opportunity": oracle_choice is not None and choice is None,
                            "useful_selection": chosen is not None and not (pv or uv),
                            "correct_redesign": oracle_choice is None and choice is None,
                            "oracle_selector_agreement": choice == oracle_choice}
                        require(all(selection[k] == v for k, v in expected.items()), "selector endpoint differs")
                        all_selections.append(selection)
    require(set(record_paths) == set(complete["record_sha256s"]), "extra or missing model records")
    expected_models = len(reg["families"]) * reg["models_per_family"]
    require(summary["confirmatory_complete"] and summary["attempted_fits"] == summary["completed_fits"] == expected_models, "wrong fit denominator")
    require(summary["candidate_rows"] == checks, "wrong candidate denominator")
    require((summary["risk_undercoverage"], summary["channel_undercoverage"], summary["invalid_utility_lower_bounds"])
            == (interval_failures, cell_failures, len(utility_failures)), "summary coverage differs")
    intervals_checked = 0
    require(len(summary["groups"]) == len(reg["families"]) * len(reg["regimes"]) * len(reg["comparators"]), "group inventory differs")
    require(len({(g["family"], g["regime"], g["method"]) for g in summary["groups"]}) == len(summary["groups"]), "duplicate summary groups")
    for group in summary["groups"]:
        rows = [s for s in all_selections if all(s[k] == group[k] for k in ("family", "regime", "method"))]
        require(len(rows) == reg["models_per_family"], "wrong group denominator")
        for key in ("oracle_feasible", "privacy_violation", "utility_violation", "unsafe_selection", "missed_oracle_opportunity",
                    "useful_selection", "correct_redesign", "oracle_selector_agreement"):
            require(group[key] == sum(r[key] for r in rows), "aggregate endpoint differs: " + key)
        for endpoint, interval in group["primary_intervals"].items():
            p = F(sum(r[endpoint] for r in rows), len(rows))
            require(interval["denominator"] == len(rows) and interval["count"] == sum(r[endpoint] for r in rows), "primary count differs")
            require((frac(interval["estimate"]), frac(interval["lower"]), frac(interval["upper"]))
                    == (p, max(F(0), p-F(1, 5)), min(F(1), p+F(1, 5))), "primary interval differs")
            intervals_checked += 1
    require(intervals_checked == 16, "wrong number of primary simultaneous intervals")
    exp_lower = lambda x: sum((F(x)**k / factorial(k) for k in range(33)), F(0))
    failure = (4 * checks + expected_models * len(reg["controls"])) / exp_lower(2 * n * radius * radius)
    require(frac(summary["simultaneous_evaluation_failure_upper"]) == failure < F(1, 20), "family allocation differs")
    require(frac(summary["primary_model_mean_failure_upper"]) == 32 / exp_lower(F(2 * reg["models_per_family"], 25)) < F(1, 20), "model mean allocation differs")
    return {"verified_at": datetime.now(timezone.utc).isoformat(), "verifier_sha256": sha(Path(__file__)),
        "complete_sha256": sha(output / "COMPLETE.json"), "models_recounted": expected_models,
        "candidate_rows_recounted": checks, "primary_intervals_recomputed": intervals_checked,
        "risk_undercoverage": interval_failures, "passed": True,
        "boundary": "Independent artifact/count/oracle replay; no refitting, production enforcement or external attestation."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_directory", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.run_directory.resolve())
    with args.receipt.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2)
        handle.write("\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
