#!/usr/bin/env python3
"""Post-hoc sensitivity analysis for an adversary with exact database metadata."""

from __future__ import annotations

import argparse
import gzip
import json
import math
import sys
import time
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
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


def finite_or_none(value: Any) -> float | int | str | None:
    if isinstance(value, (np.integer, int)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return float(value) if np.isfinite(value) else None
    return value


def numeric_stats(series: pd.Series) -> dict[str, Any]:
    values = pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)
    finite = values[np.isfinite(values)]
    missing = int(len(values) - len(finite))
    if not len(finite):
        return {
            "dtype": str(series.dtype),
            "non_missing_count": 0,
            "missing_count": missing,
            "missing_rate": missing / len(values),
            "unique_count": 0,
            "minimum": None,
            "maximum": None,
            "range": None,
            "mean": None,
            "median": None,
            "standard_deviation": None,
            "variance": None,
            "first_quartile": None,
            "third_quartile": None,
            "interquartile_range": None,
            "median_absolute_deviation": None,
        }
    q1, median, q3 = np.quantile(finite, [0.25, 0.5, 0.75])
    minimum, maximum = np.min(finite), np.max(finite)
    mean = np.mean(finite)
    variance = np.var(finite)
    return {
        "dtype": str(series.dtype),
        "non_missing_count": int(len(finite)),
        "missing_count": missing,
        "missing_rate": missing / len(values),
        "unique_count": int(len(np.unique(finite))),
        "minimum": finite_or_none(minimum),
        "maximum": finite_or_none(maximum),
        "range": finite_or_none(maximum - minimum),
        "mean": finite_or_none(mean),
        "median": finite_or_none(median),
        "standard_deviation": finite_or_none(np.sqrt(variance)),
        "variance": finite_or_none(variance),
        "first_quartile": finite_or_none(q1),
        "third_quartile": finite_or_none(q3),
        "interquartile_range": finite_or_none(q3 - q1),
        "median_absolute_deviation": finite_or_none(np.median(np.abs(finite - median))),
    }


def categorical_stats(series: pd.Series) -> dict[str, Any]:
    values = series.astype("string").fillna("<NA>")
    counts = values.value_counts(dropna=False).sort_index()
    total = len(values)
    return {
        "dtype": str(series.dtype),
        "non_missing_count": int((values != "<NA>").sum()),
        "missing_count": int((values == "<NA>").sum()),
        "missing_rate": float((values == "<NA>").mean()),
        "unique_count": int(len(counts)),
        "category_counts": {str(key): int(value) for key, value in counts.items()},
        "category_frequencies": {str(key): float(value / total) for key, value in counts.items()},
    }


def database_metadata(
    features: pd.DataFrame,
    target_raw: pd.Series,
    target_name: str,
    numeric: list[str],
    categorical: list[str],
) -> dict[str, Any]:
    target_values = target_raw.astype("string").fillna("<NA>")
    target_counts = target_values.value_counts(dropna=False).sort_index()
    return {
        "row_count": len(features),
        "feature_count": features.shape[1],
        "target_name": target_name,
        "feature_order": [str(item) for item in features.columns],
        "feature_dtypes": {str(column): str(features[column].dtype) for column in features.columns},
        "numeric_features": {column: numeric_stats(features[column]) for column in numeric},
        "categorical_features": {
            column: categorical_stats(features[column]) for column in categorical
        },
        "target": {
            "dtype": str(target_raw.dtype),
            "class_count": len(target_counts),
            "class_counts": {str(key): int(value) for key, value in target_counts.items()},
            "class_frequencies": {
                str(key): float(value / len(target_values)) for key, value in target_counts.items()
            },
        },
    }


def write_json_gz(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=9, mtime=0) as stream:
            stream.write(payload)


def summary_features(
    candidates: pd.DataFrame,
    labels: pd.Series,
    source_meta: dict[str, Any],
    target_meta: dict[str, Any],
    numeric: list[str],
    categorical: list[str],
) -> pd.DataFrame:
    row_count = int(target_meta["row_count"])
    count = len(candidates)
    mean_llr = np.zeros(count)
    extreme_fraction = np.zeros(count)
    median_fraction = np.zeros(count)
    in_range_fraction = np.zeros(count)
    robust_conformity = np.zeros(count)
    missing_pattern_score = np.zeros(count)
    usable = 0
    for column in numeric:
        source = source_meta["numeric_features"][column]
        target = target_meta["numeric_features"][column]
        if source["mean"] is None or source["variance"] in (None, 0) or target["mean"] is None:
            continue
        values = pd.to_numeric(candidates[column], errors="coerce").to_numpy(dtype=float)
        present = np.isfinite(values)
        population_mean = float(source["mean"])
        population_variance = max(float(source["variance"]), 1e-12)
        observed_mean = float(target["mean"])
        variance_h0 = max(population_variance / row_count, 1e-15)
        variance_h1 = max(population_variance * (row_count - 1) / (row_count * row_count), 1e-15)
        mean_h1 = population_mean + (np.where(present, values, population_mean) - population_mean) / row_count
        llr = (
            -0.5 * np.log(variance_h1 / variance_h0)
            -0.5 * ((observed_mean - mean_h1) ** 2 / variance_h1)
            +0.5 * ((observed_mean - population_mean) ** 2 / variance_h0)
        )
        mean_llr += np.where(present, np.clip(llr, -50, 50), 0)
        minimum = float(target["minimum"])
        maximum = float(target["maximum"])
        median = float(target["median"])
        iqr = max(float(target["interquartile_range"] or 0), 1e-12)
        tolerance = np.finfo(float).eps * max(1.0, abs(minimum), abs(maximum), abs(median)) * 8
        extreme_fraction += present & (
            np.isclose(values, minimum, rtol=0, atol=tolerance)
            | np.isclose(values, maximum, rtol=0, atol=tolerance)
        )
        median_fraction += present & np.isclose(values, median, rtol=0, atol=tolerance)
        in_range_fraction += present & (values >= minimum) & (values <= maximum)
        robust_conformity += np.where(present, -np.minimum(np.abs(values - median) / iqr, 50), 0)
        target_missing = max(float(target["missing_rate"]), 1e-12)
        source_missing = max(float(source["missing_rate"]), 1e-12)
        missing_pattern_score += np.where(present, 0, math.log(target_missing / source_missing))
        usable += 1
    denominator = max(usable, 1)
    categorical_log_frequency = np.zeros(count)
    for column in categorical:
        values = candidates[column].astype("string").fillna("<NA>")
        stats = target_meta["categorical_features"][column]
        category_count = max(int(stats["unique_count"]), 1)
        denom = row_count + 0.5 * category_count
        categorical_log_frequency += np.asarray([
            math.log((stats["category_counts"].get(str(item), 0) + 0.5) / denom)
            for item in values
        ])
    target_stats = target_meta["target"]
    class_count = max(int(target_stats["class_count"]), 1)
    class_denom = row_count + 0.5 * class_count
    target_class_log_frequency = np.asarray([
        math.log((target_stats["class_counts"].get(str(item), 0) + 0.5) / class_denom)
        for item in labels.astype("string").fillna("<NA>")
    ])
    return pd.DataFrame({
        "metadata_mean_gaussian_llr": mean_llr / math.sqrt(denominator),
        "metadata_extreme_match_fraction": extreme_fraction / denominator,
        "metadata_median_match_fraction": median_fraction / denominator,
        "metadata_in_training_range_fraction": in_range_fraction / denominator,
        "metadata_robust_conformity": robust_conformity / denominator,
        "metadata_missing_pattern_score": missing_pattern_score / denominator,
        "metadata_categorical_log_frequency": categorical_log_frequency,
        "metadata_target_class_log_frequency": target_class_log_frequency,
    })


def attack_result(
    scores: dict[str, np.ndarray],
    target_fpr: float,
    confidence: float,
) -> dict[str, Any]:
    threshold, calibration_fp = threshold_at_fpr(scores["nonmember_calibration"], target_fpr)
    tp = int(np.sum(scores["member_audit"] >= threshold))
    fn = len(scores["member_audit"]) - tp
    fp = int(np.sum(scores["nonmember_audit"] >= threshold))
    tn = len(scores["nonmember_audit"]) - fp
    tpr_interval = one_sided_clopper_pearson(tp, tp + fn, confidence)
    fpr_interval = one_sided_clopper_pearson(fp, fp + tn, confidence)
    attained = fpr_interval[1] <= target_fpr
    return {
        "threshold": threshold,
        "calibration_false_positives": calibration_fp,
        "true_positives": tp,
        "false_positives": fp,
        "true_negatives": tn,
        "false_negatives": fn,
        "tpr": tp / (tp + fn),
        "fpr": fp / (fp + tn),
        "tpr_clopper_pearson_one_sided": list(tpr_interval),
        "fpr_clopper_pearson_one_sided": list(fpr_interval),
        "confidence": confidence,
        "operating_point_attained": attained,
        "certified_attack_floor": tpr_interval[0] if attained else None,
        "evidence_class": "floor" if attained else "screen",
    }


def fit_attack(X: pd.DataFrame, y: np.ndarray, seed: int) -> Pipeline:
    model = Pipeline([
        ("scale", StandardScaler()),
        ("logistic", LogisticRegression(
            solver="liblinear", class_weight="balanced", random_state=seed, max_iter=1000
        )),
    ])
    model.fit(X, y)
    return model


def run_dataset(
    dataset: dict[str, Any],
    base_config: dict[str, Any],
    attack_config: dict[str, Any],
    seed: int,
    force: bool,
) -> list[dict[str, Any]]:
    dataset_id = int(dataset["dataset_id"])
    base_dir = ROOT / "reproduction/openml/runs/metadata-adversary" / f"openml-{dataset_id}" / f"seed-{seed}"
    snapshot = ROOT / dataset["snapshot_path"]
    if sha256_file(snapshot) != dataset["snapshot_sha256"]:
        raise ValueError("dataset snapshot hash mismatch")
    frame = pd.read_parquet(snapshot)
    target_name = dataset["target"]
    full_features = frame.drop(columns=[target_name])
    full_target = frame[target_name].astype("string").fillna("<NA>")
    label_encoder = LabelEncoder()
    full_encoded_target = label_encoder.fit_transform(full_target)
    identities = row_ids(dataset_id, dataset["snapshot_sha256"], len(frame))
    selected = capped_indices(
        full_encoded_target,
        max(int(base_config["row_cap"]) * 2, 500),
        int(base_config["master_seed"]),
    )
    features = full_features.iloc[selected].reset_index(drop=True)
    target_raw = full_target.iloc[selected].reset_index(drop=True)
    target = full_encoded_target[selected]
    identities = identities[selected]
    splits = make_splits(target, seed, base_config["split_fractions"])
    target_indices = equalized_target(
        splits["target_train"], target, len(splits["reference_train"]), seed + 100
    )
    member_calibration, member_audit = member_halves(target_indices, target, seed + 200)
    groups = {
        "member_calibration": member_calibration,
        "member_audit": member_audit,
        "nonmember_calibration": splits["attack_calibration"],
        "nonmember_audit": splits["attack_audit_nonmember"],
    }
    _, numeric, categorical = build_preprocessor(features)
    source_meta = database_metadata(full_features, full_target, target_name, numeric, categorical)
    target_meta = database_metadata(
        features.iloc[target_indices].reset_index(drop=True),
        target_raw.iloc[target_indices].reset_index(drop=True),
        target_name,
        numeric,
        categorical,
    )
    base_dir.mkdir(parents=True, exist_ok=True)
    source_meta_path = base_dir / "full-source-database-metadata.json.gz"
    target_meta_path = base_dir / "target-training-database-metadata.json.gz"
    write_json_gz(source_meta_path, source_meta)
    write_json_gz(target_meta_path, target_meta)
    metadata_artifacts = {
        "full_source_metadata": {
            "path": str(source_meta_path.relative_to(ROOT)),
            "sha256": sha256_file(source_meta_path),
        },
        "target_training_metadata": {
            "path": str(target_meta_path.relative_to(ROOT)),
            "sha256": sha256_file(target_meta_path),
        },
    }

    records: list[dict[str, Any]] = []
    target_fpr = float(base_config["target_fpr"])
    family_confidence = float(attack_config["confidence_family"])
    attack_family_size = int(attack_config["new_attack_family_size"])
    simultaneous_confidence = 1.0 - (1.0 - family_confidence) / attack_family_size
    metadata_columns = [
        "metadata_mean_gaussian_llr",
        "metadata_extreme_match_fraction",
        "metadata_median_match_fraction",
        "metadata_in_training_range_fraction",
        "metadata_robust_conformity",
        "metadata_missing_pattern_score",
        "metadata_categorical_log_frequency",
        "metadata_target_class_log_frequency",
    ]
    for capacity in base_config["attack_capacities"]:
        capacity_name = f"trees-{capacity['n_estimators']}-depth-{capacity['max_depth']}"
        output_dir = base_dir / capacity_name
        manifest_path = output_dir / "run-manifest.json"
        config_hash = sha256_bytes(canonical_json({"base": base_config, "metadata": attack_config}))
        if manifest_path.is_file() and not force:
            previous = json.loads(manifest_path.read_text())
            if (
                previous.get("status") == "complete"
                and previous.get("config_sha256") == config_hash
                and previous.get("implementation_version") == attack_config["implementation_version"]
            ):
                records.append(previous)
                continue
        started = time.monotonic()
        source_run_path = (
            ROOT
            / "reproduction/openml/runs/membership"
            / f"openml-{dataset_id}"
            / f"seed-{seed}"
            / capacity_name
            / "run-manifest.json"
        )
        source_run = json.loads(source_run_path.read_text())
        raw_path = ROOT / source_run["artifacts"]["raw_scores"]["path"]
        if sha256_file(raw_path) != source_run["artifacts"]["raw_scores"]["sha256"]:
            raise ValueError("source model-attack raw score hash mismatch")
        existing = pd.read_parquet(raw_path).set_index("row_id")
        raw_groups: list[pd.DataFrame] = []
        for group, indices in groups.items():
            meta_features = summary_features(
                features.iloc[indices].reset_index(drop=True),
                target_raw.iloc[indices].reset_index(drop=True),
                source_meta,
                target_meta,
                numeric,
                categorical,
            )
            meta_features.insert(0, "row_id", identities[indices])
            meta_features.insert(1, "group", group)
            meta_features.insert(2, "is_member", group.startswith("member_"))
            meta_features["model_membership_score"] = existing.loc[
                meta_features.row_id, "membership_score"
            ].to_numpy()
            raw_groups.append(meta_features)
        raw = pd.concat(raw_groups, ignore_index=True)
        calibration = raw.group.str.endswith("calibration")
        y_calibration = raw.loc[calibration, "is_member"].astype(int).to_numpy()
        metadata_model = fit_attack(raw.loc[calibration, metadata_columns], y_calibration, seed)
        combined_columns = ["model_membership_score", *metadata_columns]
        combined_model = fit_attack(raw.loc[calibration, combined_columns], y_calibration, seed + 1)
        raw["metadata_only_score"] = metadata_model.predict_proba(raw[metadata_columns])[:, 1]
        raw["combined_model_metadata_score"] = combined_model.predict_proba(raw[combined_columns])[:, 1]

        attacks: dict[str, dict[str, Any]] = {}
        for name, score_column in {
            "metadata_only": "metadata_only_score",
            "combined_model_metadata": "combined_model_metadata_score",
        }.items():
            scores = {
                group: raw.loc[raw.group == group, score_column].to_numpy()
                for group in groups
            }
            attacks[name] = attack_result(scores, target_fpr, simultaneous_confidence)
            attacks[name].update({
                "score_column": score_column,
                "target_fpr": target_fpr,
                "familywise_confidence": family_confidence,
                "bonferroni_attack_family_size": attack_family_size,
                "analysis_status": "post_hoc_sensitivity",
            })
        output_dir.mkdir(parents=True, exist_ok=True)
        scores_path = output_dir / "raw-metadata-adversary-scores.parquet"
        metadata_model_path = output_dir / "metadata-only-attack.joblib"
        combined_model_path = output_dir / "combined-model-metadata-attack.joblib"
        raw.to_parquet(scores_path, index=False, compression="zstd")
        joblib.dump(metadata_model, metadata_model_path, compress=3)
        joblib.dump(combined_model, combined_model_path, compress=3)
        manifest = {
            "status": "complete",
            "implementation_version": int(attack_config["implementation_version"]),
            "experiment": "summary_informed_membership_sensitivity",
            "post_hoc_sensitivity_analysis": True,
            "dataset_id": dataset_id,
            "dataset_name": dataset["name"],
            "dataset_version": dataset["version"],
            "dataset_snapshot_sha256": dataset["snapshot_sha256"],
            "seed": seed,
            "capacity": capacity,
            "protected_unit": "record",
            "adversary_knowledge": attack_config["assumption"],
            "candidate_features_known": True,
            "candidate_label_known": True,
            "metadata_fields": {
                "continuous": attack_config["continuous_metadata"],
                "categorical": attack_config["categorical_metadata"],
                "target": attack_config["target_metadata"],
            },
            "group_counts": {name: len(indices) for name, indices in groups.items()},
            "attacks": attacks,
            "artifacts": {
                **metadata_artifacts,
                "raw_scores": {
                    "path": str(scores_path.relative_to(ROOT)),
                    "sha256": sha256_file(scores_path),
                },
                "metadata_only_attack": {
                    "path": str(metadata_model_path.relative_to(ROOT)),
                    "sha256": sha256_file(metadata_model_path),
                },
                "combined_model_metadata_attack": {
                    "path": str(combined_model_path.relative_to(ROOT)),
                    "sha256": sha256_file(combined_model_path),
                },
                "source_membership_run_manifest": {
                    "path": str(source_run_path.relative_to(ROOT)),
                    "sha256": sha256_file(source_run_path),
                },
            },
            "limitations": [
                "The logistic attackers were developed after the baseline tree results and are post-hoc sensitivity analyses.",
                "The diagonal-Gaussian mean feature ignores feature covariance and finite-population dependence.",
                "Exact summaries do not imply that the adversary knows the record roster.",
                "Metadata-only is the no-model baseline; release-enabled incremental risk requires a paired comparison, not subtraction of separate confidence bounds.",
            ],
            "config_sha256": config_hash,
            "elapsed_seconds": time.monotonic() - started,
        }
        write_json(manifest_path, manifest)
        records.append(manifest)
    return records


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--metadata-config", type=Path, required=True)
    parser.add_argument("--subset-manifest", type=Path, required=True)
    parser.add_argument("--dataset-id", type=int, action="append")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    base_config = json.loads(args.config.read_text())
    attack_config = json.loads(args.metadata_config.read_text())
    subset = json.loads(args.subset_manifest.read_text())
    datasets = subset["expensive_subset"]
    if args.dataset_id:
        allowed = set(args.dataset_id)
        datasets = [item for item in datasets if int(item["dataset_id"]) in allowed]
    seed = int(base_config["replicate_seeds"][0])
    records: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for position, dataset in enumerate(datasets, start=1):
        print(f"[{position}/{len(datasets)}] {dataset['name']} OpenML {dataset['dataset_id']}", flush=True)
        try:
            records.extend(run_dataset(dataset, base_config, attack_config, seed, args.force))
        except Exception as exc:
            failures.append({
                "dataset_id": dataset["dataset_id"],
                "dataset_name": dataset["name"],
                "error_type": type(exc).__name__,
                "error": str(exc),
            })
            print(f"  failed: {failures[-1]}", flush=True)
    expected = len(datasets) * len(base_config["attack_capacities"])
    summary = {
        "experiment": "openml_cc18_summary_informed_membership_sensitivity",
        "post_hoc_sensitivity_analysis": True,
        "subset_manifest_sha256": sha256_file(args.subset_manifest),
        "base_config_sha256": sha256_file(args.config),
        "metadata_config_sha256": sha256_file(args.metadata_config),
        "expected_runs": expected,
        "completed_runs": len(records),
        "failed_runs": len(failures),
        "records": records,
        "failures": failures,
    }
    output = ROOT / "output/reproduction"
    write_json(output / "openml-metadata-adversary-summary.json", summary)
    flat = []
    for record in records:
        for attack_name, attack in record["attacks"].items():
            flat.append({
                "dataset_id": record["dataset_id"],
                "dataset_name": record["dataset_name"],
                "seed": record["seed"],
                **record["capacity"],
                "attack_name": attack_name,
                **attack,
            })
    pd.DataFrame(flat).to_csv(output / "openml-metadata-adversary-summary.csv", index=False)
    print(json.dumps({"expected_runs": expected, "completed_runs": len(records), "failed_runs": len(failures)}, indent=2))
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
