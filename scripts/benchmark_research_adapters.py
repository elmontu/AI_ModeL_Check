#!/usr/bin/env python3
"""Run sector-neutral public-data adapter checks; no downloads or release authority."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).absolute().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
_SPEC = importlib.util.spec_from_file_location("mra_adapter_baseline", ROOT / "scripts/verify_build_baseline.py")
_BASELINE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_BASELINE)
from model_release_assurance.production_adapters.catalog import catalog_entries
from model_release_assurance.production_adapters.datasets import load_research_dataset, DatasetUnavailable
from model_release_assurance.production_adapters.native import run_native

FLAGS = {"public_benchmark_only": True, "production_authorized": False,
         "authorization_eligible": False, "can_clear": False, "deployable": False,
         "private_data_admitted": False, "research_reproduction": False}
CATALOG_MANIFEST = "reproduction/openml/manifests/suite-99-datasets.json"
MAX_REPORT_BYTES = 4 * 1024 * 1024


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _digest(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _new_json(path, value):
    content = json.dumps(value, sort_keys=True, indent=2, allow_nan=False).encode("utf-8") + b"\n"
    if len(content) > MAX_REPORT_BYTES:
        raise ValueError("Benchmark report exceeds its bound")
    with path.open("xb") as stream:
        stream.write(content)


def source_snapshot(root):
    names = {"pyproject.toml", "requirements.lock", "requirements-build.lock", CATALOG_MANIFEST,
             "scripts/benchmark_research_adapters.py", "scripts/replay_native_adapter.py",
             "scripts/verify_build_baseline.py", "src/model_release_assurance/__init__.py"}
    for folder in (root / "src/model_release_assurance", root / "tests"):
        names.update(path.relative_to(root).as_posix() for path in folder.rglob("*.py"))
    files = []
    for name in sorted(names):
        content = _BASELINE._read_file(root, name)
        if len(content) > 8 * 1024 * 1024:
            raise ValueError("Benchmark source input exceeds its bound")
        files.append({"path": name, "sha256": hashlib.sha256(content).hexdigest()})
    return {"scope": "package Python sources, tests/helpers, CLI/build helper, runtime declarations and OpenML registry",
            "files": files, "sha256": _digest(files)}


def load_bundled(loader_id, max_rows):
    import numpy as np
    import sklearn
    from sklearn.datasets import load_breast_cancer, load_wine, load_digits, load_diabetes
    loaders = {"sklearn-breast-cancer": load_breast_cancer, "sklearn-wine": load_wine,
               "sklearn-digits": load_digits, "sklearn-diabetes": load_diabetes}
    if loader_id not in loaders:
        raise ValueError("Unknown bundled dataset")
    data = loaders[loader_id]()
    x, y = np.array(data.data, dtype=np.float64, copy=True), np.array(data.target, copy=True)
    names = [str(name) for name in data.feature_names]
    full_digest = _digest({"loader": loader_id, "sklearn": sklearn.__version__,
                           "x": x.tolist(), "y": y.tolist(), "feature_names": names})
    indices = np.random.default_rng(20261001).permutation(len(y))[:max_rows]
    x, y = x[indices], y[indices]
    return {"x": x, "y": y, "feature_names": names, "dataset_id": loader_id,
            "source_sha256": full_digest,
            "metadata": {"schema": "bundled-dataset-observation/v1", "source": "scikit-learn bundled fixture",
                         "loader": loader_id, "sklearn_version": sklearn.__version__, "available_rows": len(data.target),
                         "selected_rows": len(y), "selection": "fixed20261001 permutation before label inspection",
                         "selection_indices_sha256": _digest(indices.tolist()), "full_fixture_sha256": full_digest,
                         "selected_matrix_sha256": _digest({"x": x.tolist(), "y": y.tolist()}),
                         "features": len(names), "private_data": False,
                         "historically_untouched_data_claim": False, "production_license_approval": False}}


def _validate_limits(max_rows, seed):
    if type(max_rows) is not int or not 128 <= max_rows <= 4096:
        raise ValueError("max_rows must be an integer from128 through4096")
    if type(seed) is not int or not 0 <= seed <= 2**32 - 1:
        raise ValueError("seed must be a bounded integer")


def run_benchmark(*, root, data_root, output, max_rows=4096, seed=20261001):
    _validate_limits(max_rows, seed)
    data_root = Path(data_root)
    if not data_root.is_absolute() or ".." in data_root.parts:
        raise ValueError("Use an explicit absolute research data root without traversal")
    destination = _BASELINE.prepare_output(Path(root).absolute(), output)
    report = {"schema": "mra-research-adapter-benchmark/v1", "status": "failed", **FLAGS,
              "data_root": str(data_root), "max_rows_per_profile": max_rows, "seed": seed,
              "entries": [], "errors": [], "coverage_complete": False,
              "all_research_datasets_tested": False, "limitations": [
                  "Only available allowlisted prepared data and bundled fixtures are model-tested; unavailable profiles are explicit.",
                  "Catalog entries are source profiles, not independent datasets or proof every registered OpenML input was historically trained.",
                  "Bounded historical samples are engineering benchmarks, not full-corpus training, fresh audits or representative privacy evidence.",
                  "Large upstream raw sources are not rehashed or rescanned by this run; prepared NPZ bytes are verified against their retained manifests.",
                  "These are trusted local adapter checks, separate from PRD-10's fixed-count worker; no cloud isolation or image admission is established.",
                  "Current licensing, scientific acceptance and production qualification remain pending for every profile."]}
    baseline = None
    started = time.monotonic()
    try:
        baseline = source_snapshot(Path(root).absolute())
        report["source"] = baseline
        entries = catalog_entries(Path(root).absolute())
        ids = [entry["id"] for entry in entries]
        if not entries or len(entries) > 128 or len(set(ids)) != len(ids):
            raise ValueError("Invalid or duplicate catalog entries")
        report["catalog_sha256"] = _digest(entries)
        report["catalog_entries"] = len(entries)
        _new_json(destination / "plan.json", {"schema": "mra-research-adapter-batch-plan/v1",
                  "catalog": entries, "max_rows": max_rows, "seed": seed,
                  "selection_seed": 20261001, "source_sha256": baseline["sha256"],
                  "stopping_rule": "one fixed native adapter per supported profile; no selection on outcomes", **FLAGS})
        (destination / "cases").mkdir()
        (destination / "observations").mkdir()
        for entry in entries:
            item = {"id": entry["id"], "label": entry["label"], "kind": entry["kind"],
                    "task": entry["task"], "status": "not_run", **FLAGS}
            report["entries"].append(item)
            if entry["kind"] in {"historical_unavailable", "openml_registered"}:
                item.update(status="unavailable", reason="No eligible local dataset loader or source snapshot in this D-drive profile",
                            model_tested=False, historical_usage_verified_by_this_run=False)
                continue
            try:
                if entry["kind"] == "research_prepared":
                    data = load_research_dataset(data_root, entry["corpus"], max_rows=max_rows)
                elif entry["kind"] == "bundled":
                    data = load_bundled(entry["loader_id"], max_rows)
                else:
                    raise ValueError("Unrecognized catalog kind")
                case = destination / "cases" / entry["id"]
                observation = destination / "observations" / (entry["id"] + ".json")
                _new_json(observation, data["metadata"])
                receipt = run_native(data["x"], data["y"], dataset_id=data["dataset_id"],
                          source_sha256=data["source_sha256"], feature_names=data["feature_names"],
                          task=entry["task"], output=case, seed=seed)
                if not case.is_dir():
                    raise ValueError("Adapter did not retain its result directory")
                status = receipt.get("status")
                if status not in {"passed", "completed", "unsupported", "failed"}:
                    raise ValueError("Adapter returned an unknown outcome")
                item.update(status="passed" if status in {"passed", "completed"} else status,
                            model_tested=status in {"passed", "completed"}, source_sha256=data["source_sha256"],
                            selected_rows=len(data["y"]), features=len(data["feature_names"]),
                            source_observation=data["metadata"],
                            source_observation_path=observation.relative_to(destination).as_posix(),
                            receipt_sha256=_digest(receipt),
                            result_directory=case.relative_to(destination).as_posix())
                item["adapter_result"] = receipt
            except DatasetUnavailable:
                item.update(status="unavailable", reason="The fixed prepared source is absent", model_tested=False)
            except Exception as error:
                # A failed source/adapter is never relabeled missing or a clean screen.
                item.update(status="failed", reason=type(error).__name__, model_tested=False)
        counts = dict(Counter(item["status"] for item in report["entries"]))
        report["counts"] = counts
        report["coverage_complete"] = counts.get("passed", 0) == len(entries)
        report["all_research_datasets_tested"] = False  # This catalog cannot establish universal research coverage.
        report["status"] = "failed" if counts.get("failed", 0) or counts.get("not_run", 0) else (
            "passed" if report["coverage_complete"] else "completed_with_gaps")
    except Exception as error:
        report["errors"].append(type(error).__name__)
        report["status"] = "failed"
    finally:
        if baseline is not None:
            try:
                stable = source_snapshot(Path(root).absolute()) == baseline
            except Exception:
                stable = False
            report["source_stable"] = stable
            if not stable:
                report["status"] = "failed"
                report["errors"].append("source_changed")
        report["elapsed_seconds"] = round(time.monotonic() - started, 3)
        _new_json(destination / "result.json", report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", required=True, type=Path, help="Existing public research root, read-only")
    parser.add_argument("--output", required=True, type=Path, help="Fresh ignored government .local child")
    parser.add_argument("--max-rows", type=int, default=4096)
    parser.add_argument("--seed", type=int, default=20261001)
    parser.add_argument("--require-complete", action="store_true", help="Return nonzero if any catalog profile is unavailable/unsupported")
    args = parser.parse_args(argv)
    try:
        report = run_benchmark(root=ROOT, data_root=args.data_root, output=args.output,
                               max_rows=args.max_rows, seed=args.seed)
    except (ValueError, OSError, _BASELINE.BaselineError) as error:
        print(json.dumps({"status": "refused", "reason": type(error).__name__, **FLAGS}))
        return 2
    print(json.dumps({"status": report["status"], "counts": report.get("counts", {}),
                      "coverage_complete": report["coverage_complete"],
                      "all_research_datasets_tested": False, "errors": report["errors"], **FLAGS}))
    if report["status"] == "failed":
        return 1
    return 3 if args.require_complete and not report["coverage_complete"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
