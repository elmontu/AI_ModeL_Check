#!/usr/bin/env python3
"""Train shallow MLPs with record-level DP-SGD and retain an accountant ledger.

The implementation uses independent Poisson sampling, per-example gradient
clipping, and Gaussian noise on the summed gradient. Preprocessing is fixed from
the declared public OpenML benchmark population. It is therefore outside the DP
mechanism; a deployment must use public/fixed or separately private
preprocessing to inherit the same guarantee.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.special import logsumexp
from sklearn.metrics import accuracy_score, balanced_accuracy_score, log_loss, roc_auc_score
from sklearn.preprocessing import LabelEncoder, StandardScaler


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from run_openml_membership import (  # noqa: E402
    equalized_target,
    member_halves,
    one_sided_clopper_pearson,
    threshold_at_fpr,
)
from run_openml_structural import (  # noqa: E402
    build_preprocessor,
    canonical_json,
    capped_indices,
    make_splits,
    row_ids,
    sha256_bytes,
    sha256_file,
    write_json,
)


def sampled_gaussian_rdp_integer(order: int, sample_rate: float, noise_multiplier: float) -> float:
    """Exact integer-order RDP log moment for Poisson-sampled Gaussian noise."""
    if order < 2 or order != int(order):
        raise ValueError("order must be an integer >= 2")
    if not 0.0 < sample_rate <= 1.0 or noise_multiplier <= 0:
        raise ValueError("invalid sample rate or noise multiplier")
    terms = []
    for i in range(order + 1):
        log_choose = math.lgamma(order + 1) - math.lgamma(i + 1) - math.lgamma(order - i + 1)
        log_probability = 0.0
        if i:
            log_probability += i * math.log(sample_rate)
        if order - i:
            if sample_rate == 1.0:
                continue
            log_probability += (order - i) * math.log1p(-sample_rate)
        terms.append(
            log_choose
            + log_probability
            + (i * i - i) / (2.0 * noise_multiplier * noise_multiplier)
        )
    return float(logsumexp(terms) / (order - 1))


def compose_epsilon(
    sample_rate: float,
    noise_multiplier: float,
    steps: int,
    delta: float,
    orders: list[int],
) -> tuple[float, int, dict[str, float]]:
    by_order: dict[str, float] = {}
    best = (math.inf, -1)
    for order in orders:
        rdp = steps * sampled_gaussian_rdp_integer(order, sample_rate, noise_multiplier)
        epsilon = rdp + math.log(1.0 / delta) / (order - 1)
        by_order[str(order)] = epsilon
        if epsilon < best[0]:
            best = (epsilon, order)
    return float(best[0]), int(best[1]), by_order


def solve_noise_multiplier(
    epsilon_target: float,
    sample_rate: float,
    steps: int,
    delta: float,
    orders: list[int],
) -> tuple[float, float, int, dict[str, float]]:
    low, high = 0.05, 2.0
    while compose_epsilon(sample_rate, high, steps, delta, orders)[0] > epsilon_target:
        high *= 2.0
        if high > 1e4:
            raise RuntimeError("could not bracket a noise multiplier")
    for _ in range(70):
        middle = (low + high) / 2.0
        if compose_epsilon(sample_rate, middle, steps, delta, orders)[0] <= epsilon_target:
            high = middle
        else:
            low = middle
    epsilon, order, by_order = compose_epsilon(sample_rate, high, steps, delta, orders)
    return float(high), epsilon, order, by_order


class NumpyMLP:
    def __init__(self, n_features: int, n_classes: int, hidden: int, seed: int):
        rng = np.random.default_rng(seed)
        self.W1 = rng.normal(0.0, math.sqrt(2.0 / max(1, n_features)), (n_features, hidden)).astype(np.float32)
        self.b1 = np.zeros(hidden, dtype=np.float32)
        self.W2 = rng.normal(0.0, math.sqrt(2.0 / max(1, hidden)), (hidden, n_classes)).astype(np.float32)
        self.b2 = np.zeros(n_classes, dtype=np.float32)

    def probabilities(self, X: np.ndarray) -> np.ndarray:
        hidden = np.maximum(X @ self.W1 + self.b1, 0.0)
        logits = hidden @ self.W2 + self.b2
        logits -= logits.max(axis=1, keepdims=True)
        exp = np.exp(logits)
        return exp / exp.sum(axis=1, keepdims=True)

    def save(self, path: Path) -> None:
        np.savez_compressed(path, W1=self.W1, b1=self.b1, W2=self.W2, b2=self.b2)


def clipped_gradient_sums(model: NumpyMLP, X: np.ndarray, y: np.ndarray, clip: float) -> tuple[list[np.ndarray], float]:
    hidden_pre = X @ model.W1 + model.b1
    hidden = np.maximum(hidden_pre, 0.0)
    probabilities = model.probabilities(X)
    delta2 = probabilities.copy()
    delta2[np.arange(len(y)), y] -= 1.0
    delta1 = (delta2 @ model.W2.T) * (hidden_pre > 0.0)

    # Frobenius norms of per-example outer products factor into vector norms.
    grad_norm_sq = (
        np.sum(X * X, axis=1) * np.sum(delta1 * delta1, axis=1)
        + np.sum(delta1 * delta1, axis=1)
        + np.sum(hidden * hidden, axis=1) * np.sum(delta2 * delta2, axis=1)
        + np.sum(delta2 * delta2, axis=1)
    )
    weights = np.minimum(1.0, clip / np.sqrt(np.maximum(grad_norm_sq, 1e-30))).astype(np.float32)
    weighted1 = delta1 * weights[:, None]
    weighted2 = delta2 * weights[:, None]
    sums = [X.T @ weighted1, weighted1.sum(axis=0), hidden.T @ weighted2, weighted2.sum(axis=0)]
    clipping_fraction = float(np.mean(weights < 1.0))
    return [np.asarray(item, dtype=np.float32) for item in sums], clipping_fraction


def train_dp(
    X: np.ndarray,
    y: np.ndarray,
    n_classes: int,
    config: dict[str, Any],
    epsilon_target: float,
    seed: int,
) -> tuple[NumpyMLP, dict[str, Any]]:
    n = len(X)
    expected_batch = min(int(config["expected_batch_size"]), n)
    q = expected_batch / n
    steps_per_epoch = math.ceil(1.0 / q)
    steps = int(config["epochs"]) * steps_per_epoch
    delta = 1.0 / (n * n)
    orders = [int(item) for item in config["rdp_integer_orders"]]
    sigma, epsilon, best_order, by_order = solve_noise_multiplier(
        epsilon_target, q, steps, delta, orders
    )
    clip = float(config["gradient_clip_norm"])
    learning_rate = float(config["learning_rate"])
    model = NumpyMLP(X.shape[1], n_classes, int(config["hidden_units"]), seed)
    params = [model.W1, model.b1, model.W2, model.b2]
    first = [np.zeros_like(item) for item in params]
    second = [np.zeros_like(item) for item in params]
    rng = np.random.default_rng(seed + 71_000)
    clipping = []
    realised_batch_sizes = []
    beta1, beta2 = 0.9, 0.999
    denominator = q * n
    for step in range(1, steps + 1):
        selected = np.flatnonzero(rng.random(n) < q)
        realised_batch_sizes.append(int(len(selected)))
        if len(selected):
            sums, fraction = clipped_gradient_sums(model, X[selected], y[selected], clip)
            clipping.append(fraction)
        else:
            sums = [np.zeros_like(item) for item in params]
            clipping.append(0.0)
        gradients = [
            (item + rng.normal(0.0, sigma * clip, size=item.shape).astype(np.float32)) / denominator
            for item in sums
        ]
        for index, (parameter, gradient) in enumerate(zip(params, gradients, strict=True)):
            first[index] = beta1 * first[index] + (1.0 - beta1) * gradient
            second[index] = beta2 * second[index] + (1.0 - beta2) * (gradient * gradient)
            m_hat = first[index] / (1.0 - beta1**step)
            v_hat = second[index] / (1.0 - beta2**step)
            parameter -= learning_rate * m_hat / (np.sqrt(v_hat) + 1e-8)
    ledger = {
        "accountant_version": 1,
        "adjacency": config["adjacency"],
        "sampling": config["sampling"],
        "training_size": n,
        "expected_batch_size": expected_batch,
        "sample_rate": q,
        "steps_per_epoch": steps_per_epoch,
        "epochs": int(config["epochs"]),
        "steps": steps,
        "gradient_clip_norm": clip,
        "noise_multiplier": sigma,
        "delta": delta,
        "epsilon_target": epsilon_target,
        "epsilon_computed": epsilon,
        "optimal_integer_order": best_order,
        "epsilon_by_integer_order": by_order,
        "orders": orders,
        "mean_realised_batch_size": float(np.mean(realised_batch_sizes)),
        "minimum_realised_batch_size": int(min(realised_batch_sizes)),
        "maximum_realised_batch_size": int(max(realised_batch_sizes)),
        "mean_clipping_fraction": float(np.mean(clipping)),
    }
    return model, ledger


def train_non_private_control(
    X: np.ndarray,
    y: np.ndarray,
    n_classes: int,
    config: dict[str, Any],
    seed: int,
) -> NumpyMLP:
    """Matched control: same architecture, batches, Adam schedule, and steps."""
    n = len(X)
    expected_batch = min(int(config["expected_batch_size"]), n)
    q = expected_batch / n
    steps = int(config["epochs"]) * math.ceil(1.0 / q)
    learning_rate = float(config["learning_rate"])
    model = NumpyMLP(X.shape[1], n_classes, int(config["hidden_units"]), seed)
    params = [model.W1, model.b1, model.W2, model.b2]
    first = [np.zeros_like(item) for item in params]
    second = [np.zeros_like(item) for item in params]
    rng = np.random.default_rng(seed + 71_000)
    beta1, beta2 = 0.9, 0.999
    denominator = q * n
    for step in range(1, steps + 1):
        selected = np.flatnonzero(rng.random(n) < q)
        if len(selected):
            sums, _ = clipped_gradient_sums(model, X[selected], y[selected], float("inf"))
        else:
            sums = [np.zeros_like(item) for item in params]
        gradients = [item / denominator for item in sums]
        for index, (parameter, gradient) in enumerate(zip(params, gradients, strict=True)):
            first[index] = beta1 * first[index] + (1.0 - beta1) * gradient
            second[index] = beta2 * second[index] + (1.0 - beta2) * (gradient * gradient)
            m_hat = first[index] / (1.0 - beta1**step)
            v_hat = second[index] / (1.0 - beta2**step)
            parameter -= learning_rate * m_hat / (np.sqrt(v_hat) + 1e-8)
    return model


def per_record_loss(model: NumpyMLP, X: np.ndarray, y: np.ndarray) -> np.ndarray:
    p = model.probabilities(X)
    return -np.log(np.clip(p[np.arange(len(y)), y], 1e-30, 1.0))


def utility(model: NumpyMLP, X: np.ndarray, y: np.ndarray) -> dict[str, float | None]:
    probability = model.probabilities(X)
    prediction = probability.argmax(axis=1)
    result: dict[str, float | None] = {
        "accuracy": float(accuracy_score(y, prediction)),
        "balanced_accuracy": float(balanced_accuracy_score(y, prediction)),
        "log_loss": float(log_loss(y, probability, labels=np.arange(probability.shape[1]))),
        "roc_auc": None,
    }
    try:
        if probability.shape[1] == 2:
            result["roc_auc"] = float(roc_auc_score(y, probability[:, 1]))
        else:
            result["roc_auc"] = float(roc_auc_score(y, probability, multi_class="ovr", average="weighted"))
    except ValueError:
        pass
    return result


def run_one(dataset: dict[str, Any], base: dict[str, Any], config: dict[str, Any], seed: int, epsilon_target: float, force: bool) -> dict[str, Any]:
    dataset_id = int(dataset["dataset_id"])
    label = str(epsilon_target).replace(".", "p")
    run_dir = ROOT / "reproduction/openml/runs/dp-sgd" / f"openml-{dataset_id}" / f"seed-{seed}" / f"epsilon-{label}"
    manifest_path = run_dir / "run-manifest.json"
    config_hash = sha256_bytes(canonical_json({"base": base, "dp": config}))
    if manifest_path.is_file() and not force:
        old = json.loads(manifest_path.read_text())
        if old.get("status") == "complete" and old.get("config_sha256") == config_hash:
            return old
    started = time.monotonic()
    snapshot = ROOT / dataset["snapshot_path"]
    if sha256_file(snapshot) != dataset["snapshot_sha256"]:
        raise ValueError("dataset snapshot hash mismatch")
    frame = pd.read_parquet(snapshot)
    features = frame.drop(columns=[dataset["target"]])
    encoder = LabelEncoder().fit(frame[dataset["target"]].astype("string").fillna("<NA>"))
    target_all = encoder.transform(frame[dataset["target"]].astype("string").fillna("<NA>"))
    selected = capped_indices(target_all, int(config["dp_row_cap"]), int(base["master_seed"]))
    features = features.iloc[selected].reset_index(drop=True)
    target = target_all[selected]
    identities = row_ids(dataset_id, dataset["snapshot_sha256"], len(frame))[selected]
    splits = make_splits(target, seed, base["split_fractions"])
    target_indices = equalized_target(splits["target_train"], target, len(splits["reference_train"]), seed + 100)
    reference_indices = splits["reference_train"]
    member_calibration, member_audit = member_halves(target_indices, target, seed + 200)

    # This fit is explicitly public/fixed in the benchmark threat contract.
    preprocessor, numeric, categorical = build_preprocessor(features)
    public_unscaled = np.asarray(preprocessor.fit_transform(features), dtype=np.float32)
    scaler = StandardScaler().fit(public_unscaled)
    public_X = np.asarray(scaler.transform(public_unscaled), dtype=np.float32)
    target_model, target_ledger = train_dp(public_X[target_indices], target[target_indices], len(encoder.classes_), config, epsilon_target, seed)
    reference_model, reference_ledger = train_dp(public_X[reference_indices], target[reference_indices], len(encoder.classes_), config, epsilon_target, seed + 10_000)
    non_private_control = train_non_private_control(
        public_X[target_indices], target[target_indices], len(encoder.classes_), config, seed
    )

    groups = {
        "member_calibration": member_calibration,
        "member_audit": member_audit,
        "nonmember_calibration": splits["attack_calibration"],
        "nonmember_audit": splits["attack_audit_nonmember"],
    }
    raw_rows = []
    scores: dict[str, np.ndarray] = {}
    for group, indices in groups.items():
        target_loss = per_record_loss(target_model, public_X[indices], target[indices])
        reference_loss = per_record_loss(reference_model, public_X[indices], target[indices])
        score = reference_loss - target_loss
        scores[group] = score
        raw_rows.extend({
            "row_id": identities[index],
            "group": group,
            "is_member": group.startswith("member_"),
            "true_class": int(target[index]),
            "target_loss": float(t),
            "reference_loss": float(r),
            "membership_score": float(s),
        } for index, t, r, s in zip(indices, target_loss, reference_loss, score, strict=True))
    threshold, calibration_fp = threshold_at_fpr(scores["nonmember_calibration"], float(base["target_fpr"]))
    tp = int(np.sum(scores["member_audit"] >= threshold))
    fp = int(np.sum(scores["nonmember_audit"] >= threshold))
    fn = len(groups["member_audit"]) - tp
    tn = len(groups["nonmember_audit"]) - fp
    tpr_ci = one_sided_clopper_pearson(tp, tp + fn, float(base["confidence"]))
    fpr_ci = one_sided_clopper_pearson(fp, fp + tn, float(base["confidence"]))
    attained = fpr_ci[1] <= float(base["target_fpr"])

    run_dir.mkdir(parents=True, exist_ok=True)
    scores_path = run_dir / "raw-scores.parquet"
    pd.DataFrame(raw_rows).to_parquet(scores_path, index=False, compression="zstd")
    target_path, reference_path = run_dir / "target-model.npz", run_dir / "reference-model.npz"
    non_private_path = run_dir / "matched-non-private-control.npz"
    target_model.save(target_path)
    reference_model.save(reference_path)
    non_private_control.save(non_private_path)
    target_ledger_path, reference_ledger_path = run_dir / "target-accountant-ledger.json", run_dir / "reference-accountant-ledger.json"
    write_json(target_ledger_path, target_ledger)
    write_json(reference_ledger_path, reference_ledger)
    preprocessing_path = run_dir / "public-preprocessing.npz"
    np.savez_compressed(preprocessing_path, mean=scaler.mean_, scale=scaler.scale_)
    utility_indices = splits["utility_test"]
    target_fpr = float(base["target_fpr"])
    epsilon_computed = float(target_ledger["epsilon_computed"])
    delta_computed = float(target_ledger["delta"])
    dp_roc_ceiling = min(
        1.0,
        math.exp(epsilon_computed) * target_fpr + delta_computed,
        1.0 - math.exp(-epsilon_computed) * (1.0 - target_fpr - delta_computed),
    )
    manifest = {
        "status": "complete",
        "implementation_version": int(config["implementation_version"]),
        "experiment": config["experiment"],
        "dataset_id": dataset_id,
        "dataset_name": dataset["name"],
        "dataset_version": dataset["version"],
        "dataset_snapshot_sha256": dataset["snapshot_sha256"],
        "seed": seed,
        "epsilon_target": epsilon_target,
        "protected_unit": "record",
        "selected_rows": len(selected),
        "target_and_reference_training_size": len(target_indices),
        "group_counts": {name: len(value) for name, value in groups.items()},
        "numeric_features": numeric,
        "categorical_features": categorical,
        "transformed_feature_count": int(public_X.shape[1]),
        "class_count": len(encoder.classes_),
        "model_family": "one-hidden-layer ReLU MLP",
        "public_preprocessing_contract": config["public_preprocessing"],
        "target_accountant": target_ledger,
        "reference_accountant": reference_ledger,
        "utility": utility(target_model, public_X[utility_indices], target[utility_indices]),
        "matched_non_private_utility": utility(
            non_private_control, public_X[utility_indices], target[utility_indices]
        ),
        "matched_non_private_contract": config["non_private_control"],
        "dp_membership_roc_ceiling_at_target_fpr": dp_roc_ceiling,
        "attack": {
            "score": "DP reference loss minus DP target loss",
            "target_fpr": float(base["target_fpr"]),
            "threshold": threshold,
            "calibration_false_positives": calibration_fp,
            "true_positives": tp,
            "false_positives": fp,
            "true_negatives": tn,
            "false_negatives": fn,
            "tpr": tp / (tp + fn),
            "fpr": fp / (fp + tn),
            "tpr_clopper_pearson_one_sided": list(tpr_ci),
            "fpr_clopper_pearson_one_sided": list(fpr_ci),
            "confidence": float(base["confidence"]),
            "operating_point_attained": attained,
            "certified_attack_floor": tpr_ci[0] if attained else None,
        },
        "artifacts": {},
        "config_sha256": config_hash,
        "elapsed_seconds": time.monotonic() - started,
    }
    for name, path in {
        "raw_scores": scores_path,
        "target_model": target_path,
        "reference_model": reference_path,
        "matched_non_private_control": non_private_path,
        "target_accountant_ledger": target_ledger_path,
        "reference_accountant_ledger": reference_ledger_path,
        "public_scaler": preprocessing_path,
    }.items():
        manifest["artifacts"][name] = {"path": str(path.relative_to(ROOT)), "sha256": sha256_file(path)}
    write_json(manifest_path, manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--dp-config", type=Path, required=True)
    parser.add_argument("--subset-manifest", type=Path, required=True)
    parser.add_argument("--dataset-id", type=int, action="append")
    parser.add_argument("--seed", type=int, action="append")
    parser.add_argument("--epsilon", type=float, action="append")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    base, config, subset = json.loads(args.config.read_text()), json.loads(args.dp_config.read_text()), json.loads(args.subset_manifest.read_text())
    datasets = subset[config["subset_key"]]
    if args.dataset_id:
        allowed = set(args.dataset_id)
        datasets = [item for item in datasets if int(item["dataset_id"]) in allowed]
    seeds = args.seed or [int(item) for item in config["replicate_seeds"]]
    epsilons = args.epsilon or [float(item) for item in config["epsilon_targets"]]
    total = len(datasets) * len(seeds) * len(epsilons)
    records, failures = [], []
    position = 0
    for dataset in datasets:
        for seed in seeds:
            for epsilon in epsilons:
                position += 1
                print(f"[{position}/{total}] {dataset['name']} seed={seed} epsilon={epsilon}", flush=True)
                try:
                    records.append(run_one(dataset, base, config, seed, epsilon, args.force))
                except Exception as exc:
                    failures.append({"dataset_id": dataset["dataset_id"], "seed": seed, "epsilon": epsilon, "error_type": type(exc).__name__, "error": str(exc)})
                    print(f"  failed: {failures[-1]}", flush=True)
    output = ROOT / "output/reproduction"
    summary = {
        "experiment": config["experiment"],
        "expected_runs": total,
        "completed_runs": len(records),
        "failed_runs": len(failures),
        "records": records,
        "failures": failures,
        "base_config_sha256": sha256_file(args.config),
        "dp_config_sha256": sha256_file(args.dp_config),
        "subset_manifest_sha256": sha256_file(args.subset_manifest),
    }
    write_json(output / "openml-dp-sgd-summary.json", summary)
    output.mkdir(parents=True, exist_ok=True)
    pd.json_normalize(records, sep=".").to_csv(output / "openml-dp-sgd-summary.csv", index=False)
    print(json.dumps({"expected_runs": total, "completed_runs": len(records), "failed_runs": len(failures)}, indent=2))
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
