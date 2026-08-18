#!/usr/bin/env python3
"""Execute the frozen Version 0.5 proxy release-training design.

This runner deliberately writes a new summary instead of replacing any frozen
OpenML experiment summary. Model artifacts are stored in seed-specific directories
and can be deterministically regenerated from the retained configuration and data.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from run_openml_dp_sgd import run_one  # noqa: E402
from run_openml_structural import sha256_file, write_json  # noqa: E402


DEFAULT_DESIGN = ROOT / "reproduction/prospective-v05/config.json"
DEFAULT_OUTPUT = ROOT / "output/reproduction/v05-prospective-training-summary.json"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_datasets(design: dict[str, Any], dp_config: dict[str, Any]) -> tuple[Path, list[dict[str, Any]]]:
    if "dataset_manifest" in design:
        manifest_path = ROOT / design["dataset_manifest"]
        manifest = _load(manifest_path)
        datasets = [item for item in manifest["datasets"] if item.get("status") == "active"]
    else:
        manifest_path = ROOT / design["subset_manifest"]
        manifest = _load(manifest_path)
        datasets = manifest[dp_config["subset_key"]]
    expected = int(design.get("expected_dataset_count", len(datasets)))
    if len(datasets) != expected:
        raise ValueError(f"dataset manifest contains {len(datasets)} eligible datasets; expected {expected}")
    identifiers = [int(item["dataset_id"]) for item in datasets]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("dataset manifest contains duplicate dataset identifiers")
    return manifest_path, datasets


def _run_cell(
    dataset: dict[str, Any],
    base: dict[str, Any],
    dp_config: dict[str, Any],
    seed: int,
    epsilon: float,
    force: bool,
) -> dict[str, Any]:
    return run_one(dataset, base, dp_config, seed, epsilon, force)


def run_study(
    design_path: Path,
    output_path: Path,
    *,
    force: bool = False,
    workers: int = 1,
) -> int:
    if workers < 1:
        raise ValueError("workers must be at least one")
    design = _load(design_path)
    base_path = ROOT / design["base_config"]
    dp_path = ROOT / design["dp_config"]
    base = _load(base_path)
    dp_config = _load(dp_path)
    dataset_manifest_path, datasets = _load_datasets(design, dp_config)
    seeds = [*design["development_seeds"], *design["evaluation_seeds"]]
    epsilons = [float(value) for value in design["candidate_epsilon_targets"]]
    expected = len(datasets) * len(seeds) * len(epsilons)
    records: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    cells = [
        (dataset, int(seed), epsilon)
        for dataset in datasets
        for seed in seeds
        for epsilon in epsilons
    ]

    def collect(position: int, dataset: dict[str, Any], seed: int, epsilon: float, future: Any) -> None:
        print(
            f"[{position}/{expected}] {dataset['name']} "
            f"seed={seed} epsilon={epsilon}",
            flush=True,
        )
        try:
            records.append(future.result())
        except Exception as exc:  # preserve every failed cell
            failure = {
                "dataset_id": int(dataset["dataset_id"]),
                "dataset_name": dataset["name"],
                "seed": int(seed),
                "epsilon_target": epsilon,
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
            failures.append(failure)
            print(f"  failed: {failure}", flush=True)

    if workers == 1:
        for position, (dataset, seed, epsilon) in enumerate(cells, start=1):
            immediate: concurrent.futures.Future[dict[str, Any]] = concurrent.futures.Future()
            try:
                immediate.set_result(_run_cell(dataset, base, dp_config, seed, epsilon, force))
            except Exception as exc:
                immediate.set_exception(exc)
            collect(position, dataset, seed, epsilon, immediate)
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            submitted = [
                (
                    dataset,
                    seed,
                    epsilon,
                    executor.submit(_run_cell, dataset, base, dp_config, seed, epsilon, force),
                )
                for dataset, seed, epsilon in cells
            ]
            for position, (dataset, seed, epsilon, future) in enumerate(submitted, start=1):
                collect(position, dataset, seed, epsilon, future)
    records.sort(key=lambda item: (int(item["dataset_id"]), int(item["seed"]), float(item["epsilon_target"])))
    failures.sort(key=lambda item: (int(item["dataset_id"]), int(item["seed"]), float(item["epsilon_target"])))
    summary = {
        "study_id": design["study_id"],
        "design_version": design["design_version"],
        "design_status": design["design_status"],
        "claim_boundary": design["claim_boundary"],
        "design_path": str(design_path.relative_to(ROOT)),
        "design_sha256": sha256_file(design_path),
        "base_config_sha256": sha256_file(base_path),
        "dp_config_sha256": sha256_file(dp_path),
        "dataset_manifest_path": str(dataset_manifest_path.relative_to(ROOT)),
        "dataset_manifest_sha256": sha256_file(dataset_manifest_path),
        "datasets": len(datasets),
        "dataset_ids": [int(item["dataset_id"]) for item in datasets],
        "development_seeds": list(design["development_seeds"]),
        "evaluation_seeds": list(design["evaluation_seeds"]),
        "candidate_epsilon_targets": epsilons,
        "expected_runs": expected,
        "completed_runs": len(records),
        "failed_runs": len(failures),
        "records": records,
        "failures": failures,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(output_path, summary)
    print(
        json.dumps(
            {
                "output": str(output_path),
                "expected_runs": expected,
                "completed_runs": len(records),
                "failed_runs": len(failures),
            },
            indent=2,
        )
    )
    return 0 if not failures and len(records) == expected else 2


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--design", type=Path, default=DEFAULT_DESIGN)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()
    return run_study(args.design, args.output, force=args.force, workers=args.workers)


if __name__ == "__main__":
    raise SystemExit(main())
