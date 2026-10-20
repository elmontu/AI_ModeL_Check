"""Preregistered four-domain public usefulness benchmark; no release authority.

The store must retain prospective registration before cohort parsing or RNG. All
labels are public. Historical Phase 2/3 runtime and experiments are untouched.
"""
from __future__ import annotations
from fractions import Fraction
import hashlib
import importlib
import json
from math import isfinite, lcm, log, sqrt
from pathlib import Path
import platform
import re
from typing import Any
from .certificates import RRParameters, ResearchContext, build_certificate, rational_string, verify_certificate
from .sampling import ConditionalSampler

SPECIFICATION_SHA256 = "6a7e4c5abb8c7fc75c6bb95ab50363f6449b44c6b11ba1eeb3655353783ff94a"
MAX_JSON_BYTES = 32 * 1024 * 1024
ARTIFACTS = ("evaluation.json", "models.json", "predictions.json", "reference-blocks.json", "simulation-diagnostics.json", "reproducibility.json", "evaluation.txt")
AUTHORITY = {"authorization_effect": "none", "production_execution_qualified": False}
_ROUTES = ("public_only", "independent_rr", "certified_continuation")
_HEX_KEY = re.compile(r"[0-9a-f]{64}\Z")

class BenchmarkError(ValueError):
    """Unbound, changed or malformed public benchmark input."""

def canonical_bytes(value: Any) -> bytes:
    try:
        raw = (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False) + "\n").encode("utf-8")
    except (ValueError, TypeError, RecursionError, OverflowError) as exc:
        raise BenchmarkError("Benchmark JSON must contain bounded finite values") from exc
    if len(raw) > MAX_JSON_BYTES:
        raise BenchmarkError("Benchmark JSON exceeds the 32 MiB bound")
    return raw

def sha_bytes(raw: bytes) -> str:
    if type(raw) is not bytes:
        raise BenchmarkError("A captured byte string is required")
    return hashlib.sha256(raw).hexdigest()

def _pairs(items: Any) -> dict[str, Any]:
    result = {}
    for key, value in items:
        if key in result:
            raise BenchmarkError("Duplicate benchmark JSON key")
        result[key] = value
    return result

def specification() -> dict[str, Any]:
    path = Path(__file__).parent / "static" / "benchmark-specification.json"
    try:
        raw = path.read_bytes()
        if sha_bytes(raw) != SPECIFICATION_SHA256:
            raise BenchmarkError("The preregistered benchmark specification bytes changed")
        result = json.loads(raw, object_pairs_hook=_pairs)
        if canonical_bytes(result) != raw:
            raise BenchmarkError("The preregistered benchmark specification is not canonical")
        return result
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BenchmarkError("The packaged benchmark specification is unavailable") from exc

def dependency_status() -> dict[str, Any]:
    versions, missing = {}, []
    for name in ("numpy", "threadpoolctl"):
        try:
            versions[name] = str(importlib.import_module(name).__version__)
        except ImportError:
            missing.append(name)
    return {"available": not missing, "versions": versions, "missing": missing,
            "reason": None if not missing else "Install the research-benchmark extra to run the public benchmark."}

def _numeric() -> tuple[Any, Any]:
    try:
        import numpy as np
        from threadpoolctl import threadpool_limits
    except ImportError as exc:
        raise BenchmarkError("Install the research-benchmark extra (NumPy and threadpoolctl) before running this benchmark") from exc
    return np, threadpool_limits

def _spec(spec: Any) -> dict[str, Any]:
    # Tests replace specification() with an explicit small fixture. Production
    # always compares against the packaged specification's exact frozen SHA.
    if type(spec) is not dict or canonical_bytes(spec) != canonical_bytes(specification()):
        raise BenchmarkError("Request-time benchmark specification overrides are refused")
    return spec

def _keys(value: Any, expected: set[str], label: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != expected:
        raise BenchmarkError(f"Invalid {label} fields")
    return value

def _bounded_count(value: Any, maximum: int, label: str) -> int:
    if type(value) is not int or not 1 <= value <= maximum:
        raise BenchmarkError(f"Invalid bounded {label}")
    return value

def _source_arrays(spec: dict[str, Any], corpus: str, value: Any) -> dict[str, Any]:
    np, _ = _numeric()
    if type(value) is not dict or not {"B", "z", "y", "keys", "source_panel"} <= set(value):
        raise BenchmarkError("Public source lacks required categorical, label or key arrays")
    source = spec["sources"][corpus]
    rows = _bounded_count(source.get("selected_rows", 27000), 27000, "source row count")
    arrays = {name: np.asarray(value[name]) for name in ("B", "z", "y", "keys", "source_panel")}
    sizes = source["category_sizes"]
    if len(sizes) != len(source["features"]) or not 1 <= len(sizes) <= 16 or any(type(size) is not int or not 1 <= size <= 64 for size in sizes):
        raise BenchmarkError("Invalid fixed feature category sizes")
    if arrays["B"].shape != (rows, len(sizes)) or arrays["B"].dtype.kind not in "iu":
        raise BenchmarkError("Source B must have aligned bounded integer categorical columns")
    for column, size in enumerate(sizes):
        if np.any(arrays["B"][:, column] < 0) or np.any(arrays["B"][:, column] >= size):
            raise BenchmarkError("Source category code exceeds its fixed manifest size")
    for name in ("z", "y"):
        array = arrays[name]
        if array.shape != (rows,) or array.dtype.kind not in "iu" or not np.all((array == 0) | (array == 1)):
            raise BenchmarkError("Every source target must be an aligned integer binary array")
    keys, panels = arrays["keys"], arrays["source_panel"]
    if keys.shape != (rows,) or keys.dtype.kind != "U" or panels.shape != (rows,) or panels.dtype.kind != "U":
        raise BenchmarkError("Source keys and panels require aligned primitive Unicode arrays")
    key_list = keys.tolist()
    if any(not _HEX_KEY.fullmatch(key) for key in key_list) or len(set(key_list)) != rows:
        raise BenchmarkError("Source requires unique lowercase 64-hex snapshot keys")
    if not set(panels.tolist()) <= {"train", "final"}:
        raise BenchmarkError("Only the frozen train and final source panels are permitted")
    counts = {panel: int(np.count_nonzero(panels == panel)) for panel in ("train", "final")}
    if rows == 27000 and counts != {"train": 15000, "final": 12000}:
        raise BenchmarkError("Source panel counts differ from the frozen historical metadata")
    if counts["train"] < spec["row_counts"]["train"] + spec["row_counts"]["auxiliary"] or counts["final"] < spec["row_counts"]["test"]:
        raise BenchmarkError("Source panels cannot supply the preregistered disjoint rows")
    return arrays

def prepare_cohorts(spec: Any, datasets: Any) -> dict[str, Any]:
    spec = _spec(spec)
    _keys(datasets, set(spec["tasks_order"]), "public dataset mapping")
    for split, count in spec["row_counts"].items():
        _bounded_count(count, 512, f"{split} row count")
    tasks = {}
    for corpus in spec["tasks_order"]:
        arrays = _source_arrays(spec, corpus, datasets[corpus])
        priorities = []
        for index, key in enumerate(arrays["keys"].tolist()):
            priority = hashlib.sha256((spec["split"]["salt"] + corpus + ":" + key).encode("ascii")).digest()
            priorities.append((priority, key, index))
        ordered = {panel: [index for _, _, index in sorted(priorities) if arrays["source_panel"][index] == panel] for panel in ("train", "final")}
        n, auxiliary, test = (spec["row_counts"][name] for name in ("train", "auxiliary", "test"))
        indices = {"train": ordered["train"][:n], "auxiliary": ordered["train"][n:n + auxiliary], "test": ordered["final"][:test]}
        task = {}
        for split, selected in indices.items():
            fields = ("keys", "B", "y", "z") if split == "train" else ("keys", "B", "y")
            task[split] = {name: arrays[name][selected].tolist() for name in fields}
        task.update({"feature_names": list(spec["sources"][corpus]["features"]), "category_sizes": list(spec["sources"][corpus]["category_sizes"]),
                     "selection": {"priority": spec["split"]["priority"], "salt": spec["split"]["salt"], "source_rows": len(arrays["keys"]),
                                   "source_panel_counts": {panel: len(values) for panel, values in ordered.items()}, "label_dependent": False}})
        tasks[corpus] = task
    result = {"schema": "mra-public-benchmark-cohorts/1.0", "tasks": tasks}
    _cohorts(spec, result)
    return result

def _cohorts(spec: dict[str, Any], cohorts: Any) -> dict[str, Any]:
    _keys(cohorts, {"schema", "tasks"}, "cohort")
    if cohorts["schema"] != "mra-public-benchmark-cohorts/1.0":
        raise BenchmarkError("Unsupported cohort schema")
    _keys(cohorts["tasks"], set(spec["tasks_order"]), "cohort task mapping")
    for corpus in spec["tasks_order"]:
        task = _keys(cohorts["tasks"][corpus], {"train", "auxiliary", "test", "feature_names", "category_sizes", "selection"}, "cohort task")
        source = spec["sources"][corpus]
        if task["feature_names"] != source["features"] or task["category_sizes"] != source["category_sizes"]:
            raise BenchmarkError("Cohort predictors differ from the preregistered public features")
        seen = set()
        for split in ("train", "auxiliary", "test"):
            fields = {"keys", "B", "y", "z"} if split == "train" else {"keys", "B", "y"}
            group = _keys(task[split], fields, f"{split} cohort")
            count = spec["row_counts"][split]
            if any(type(group[name]) is not list or len(group[name]) != count for name in fields):
                raise BenchmarkError("Cohort row counts differ from preregistration")
            if any(type(key) is not str or not _HEX_KEY.fullmatch(key) for key in group["keys"]):
                raise BenchmarkError("Cohort key is invalid")
            if len(set(group["keys"])) != count or seen.intersection(group["keys"]):
                raise BenchmarkError("Training, auxiliary and test keys must be row-disjoint")
            seen.update(group["keys"])
            for name in fields & {"z", "y"}:
                if any(type(bit) is not int or bit not in (0, 1) for bit in group[name]):
                    raise BenchmarkError("Cohort labels require exact integer bits")
            for row in group["B"]:
                if type(row) is not list or len(row) != len(source["category_sizes"]) or any(type(code) is not int or not 0 <= code < size for code, size in zip(row, source["category_sizes"])):
                    raise BenchmarkError("Cohort features exceed frozen categorical bounds")
        selection = _keys(task["selection"], {"priority", "salt", "source_rows", "source_panel_counts", "label_dependent"}, "cohort selection")
        if selection["priority"] != spec["split"]["priority"] or selection["salt"] != spec["split"]["salt"] or selection["label_dependent"] is not False:
            raise BenchmarkError("Cohort selection differs from the frozen key-only rule")
    canonical_bytes(cohorts)
    return cohorts

def _seed(spec: dict[str, Any], corpus: str, purpose: str) -> int:
    material = spec["simulation"]["seed_domain"] + ":" + corpus + ":" + purpose
    return int.from_bytes(hashlib.sha256(material.encode("ascii")).digest(), "big")

def prepare_inputs(spec: Any, cohorts: Any) -> dict[str, Any]:
    spec = _spec(spec)
    cohorts = _cohorts(spec, cohorts)
    np, _ = _numeric()
    specification_hash, cohort_hash = sha_bytes(canonical_bytes(spec)), sha_bytes(canonical_bytes(cohorts))
    parameters = RRParameters.from_dict(spec["parameters"])
    if parameters.r != 1 or parameters.d != 3 or parameters.L != 9 or parameters.tau != Fraction(2, 3):
        raise BenchmarkError("Only the preregistered r=1 channel parameters are supported")
    tasks = {}
    for corpus in spec["tasks_order"]:
        train = cohorts["tasks"][corpus]["train"]
        rng = np.random.Generator(np.random.PCG64(_seed(spec, corpus, "retained")))
        tickets = rng.integers(0, 4, size=len(train["z"]), dtype=np.int64)
        responses = [int(z) if int(ticket) < 3 else 1 - int(z) for z, ticket in zip(train["z"], tickets)]
        law = {"schema": "mra-public-benchmark-retained-law/1.0", "d": "3/1", "task_id": corpus,
               "specification_sha256": specification_hash, "cohorts_sha256": cohort_hash,
               "randomness": "registered public PCG64 simulation"}
        response_document = {"schema": "mra-public-benchmark-retained-responses/1.0", "task_id": corpus,
                             "records": [{"record_id": key, "w": w} for key, w in zip(train["keys"], responses)]}
        history = {"schema": "mra-public-benchmark-history/1.0", "task_id": corpus,
                   "retained_law_sha256": sha_bytes(canonical_bytes(law)), "retained_response_sha256": sha_bytes(canonical_bytes(response_document)),
                   "additional_protected_outputs": False, "scope": "public simulation only"}
        request = {"schema": "mra-public-benchmark-request/1.0", "task_id": corpus, "parameters": parameters.to_dict(),
                   "train_record_ids": train["keys"], "specification_sha256": specification_hash, "cohorts_sha256": cohort_hash,
                   "candidate": "optimal_r1", "visible_decisions": "preregistered_public_fixed"}
        context = ResearchContext(sha_bytes(canonical_bytes(law)), sha_bytes(canonical_bytes(response_document)),
                                  sha_bytes(canonical_bytes(history)), sha_bytes(canonical_bytes(request)))
        certificate = build_certificate(parameters, context)
        verified = verify_certificate(certificate, expected_parameters=parameters, expected_context=context)
        if verified.claim != "optimal" or verified.marginal_accuracy is None or verified.marginal_accuracy <= Fraction(1, 2):
            raise BenchmarkError("The registered candidate has no nonsingular optimal decoder")
        tasks[corpus] = {"parameters": parameters.to_dict(), "context": context.to_dict(), "certificate": certificate,
                         "retained_responses": responses, "retained_law": law, "retained_response_document": response_document,
                         "history": history, "request_plan": request}
    return {"schema": "mra-public-benchmark-inputs/1.0", "specification_sha256": specification_hash,
            "cohorts_sha256": cohort_hash, "tasks": tasks}

def encode_features(B: Any, category_sizes: Any) -> Any:
    """Fixed one-hot basis including every manifest level and an intercept."""
    np, _ = _numeric()
    if type(category_sizes) is not list or not 1 <= len(category_sizes) <= 16 or any(type(size) is not int or not 1 <= size <= 64 for size in category_sizes):
        raise BenchmarkError("Invalid one-hot category sizes")
    values = np.asarray(B)
    if values.ndim != 2 or values.shape[1] != len(category_sizes) or not 1 <= len(values) <= 512 or values.dtype.kind not in "iu":
        raise BenchmarkError("The learner requires bounded integer public covariates only")
    result = np.zeros((len(values), 1 + sum(category_sizes)), dtype=np.float64)
    result[:, 0] = 1.0
    offset = 1
    for column, size in enumerate(category_sizes):
        codes = values[:, column]
        if np.any(codes < 0) or np.any(codes >= size):
            raise BenchmarkError("Public feature level exceeds its fixed vocabulary")
        result[np.arange(len(values)), offset + codes] = 1.0
        offset += size
    return result

def decode_targets(bits: Any, accuracy: Any) -> Any:
    np, _ = _numeric()
    values = np.asarray(bits)
    if values.ndim not in (1, 2) or values.dtype.kind not in "iu" or not np.all((values == 0) | (values == 1)):
        raise BenchmarkError("Randomized fitting targets must be integer binary values")
    p = float(accuracy)
    if not isfinite(p) or not 0.5 < p <= 1:
        raise BenchmarkError("A finite nonsingular mechanism-level decoder is required")
    return (values.astype(np.float64) - (1 - p)) / (2 * p - 1)

def _projection(design: Any) -> Any:
    np, _ = _numeric()
    penalty = np.eye(design.shape[1], dtype=np.float64)
    penalty[0, 0] = 0.0
    return np.linalg.solve(design.T @ design + penalty, design.T)

def fit_coefficients(B: Any, bits: Any, category_sizes: Any, accuracy: Any) -> Any:
    """Only allowed public predictors and supplied fitting targets enter the fit."""
    np, limits = _numeric()
    design = encode_features(B, category_sizes)
    targets = decode_targets(bits, accuracy)
    if targets.shape[-1] != len(design) or (targets.ndim == 2 and not 1 <= targets.shape[0] <= 4096):
        raise BenchmarkError("Fitting targets do not match the permitted training rows")
    with limits(limits=1):
        return (_projection(design) @ targets.T).T

def comparison_interval(gains: Any, *, family_size: int = 8, alpha: float = 0.05, margin: float = 0.01) -> dict[str, Any]:
    np, _ = _numeric()
    values = np.asarray(gains, dtype=np.float64)
    if (values.ndim != 1 or not 1 <= len(values) <= 4096 or not np.isfinite(values).all()
            or np.any(values < -1) or np.any(values > 1) or type(family_size) is not int or not 1 <= family_size <= 8
            or type(alpha) not in (float, int) or not 0 < alpha < 1 or type(margin) not in (float, int) or not isfinite(margin)):
        raise BenchmarkError("Invalid bounded paired-gain interval arguments")
    radius = sqrt(2 * log(2 * family_size / alpha) / len(values)) + 1e-9
    gain = float(np.mean(values))
    lower, upper = max(-1.0, gain - radius), min(1.0, gain + radius)
    return {"status": comparison_outcome(lower, upper, margin), "gain": gain, "lower": lower,
            "upper": upper, "margin": float(margin), "radius": radius}

def comparison_outcome(lower: Any, upper: Any, margin: Any = 0.01) -> str:
    if any(type(value) not in (float, int) or not isfinite(value) for value in (lower, upper, margin)) or lower > upper:
        raise BenchmarkError("Invalid finite comparison endpoints")
    return "pass" if lower >= margin else "fail" if upper < margin else "inconclusive"

def aggregate_outcomes(outcomes: Any) -> str:
    if type(outcomes) is not list or not outcomes or any(value not in ("pass", "fail", "inconclusive") for value in outcomes):
        raise BenchmarkError("All mandatory comparison outcomes are required")
    return "fail" if "fail" in outcomes else "inconclusive" if "inconclusive" in outcomes else "pass"

def _conditional_probabilities(task: dict[str, Any], inputs: dict[str, Any]) -> tuple[Any, Any]:
    parameters, context = RRParameters.from_dict(inputs["parameters"]), ResearchContext.from_dict(inputs["context"])
    verified = verify_certificate(inputs["certificate"], expected_parameters=parameters, expected_context=context)
    sampler = ConditionalSampler(inputs["certificate"], expected_parameters=parameters, expected_context=context,
                                 expected_certificate_sha256=verified.digest)
    lookup = {(z, y, w): dict(sampler.conditional_distribution([z, y], w))[(1,)] for z in (0, 1) for y in (0, 1) for w in (0, 1)}
    probabilities = [lookup[(z, y, w)] for z, y, w in zip(task["train"]["z"], task["train"]["y"], inputs["retained_responses"])]
    return probabilities, verified

def _coverage(task: dict[str, Any]) -> dict[str, Any]:
    counts, prevalence, unknown, sets = {}, {}, {}, {}
    for split in ("train", "auxiliary", "test"):
        group = task[split]
        counts[split] = len(group["keys"])
        sets[split] = set(group["keys"])
        prevalence[split] = {"y": sum(group["y"]) / len(group["y"])}
        if split == "train":
            prevalence[split]["z"] = sum(group["z"]) / len(group["z"])
        unknown[split] = {name: sum(row[index] == 0 for row in group["B"]) / len(group["B"])
                          for index, name in enumerate(task["feature_names"])}
    return {"counts": counts, "outcome_prevalence": prevalence, "unknown_code_frequency": unknown,
            "key_disjointness": {"train_auxiliary": not bool(sets["train"] & sets["auxiliary"]),
                                 "train_test": not bool(sets["train"] & sets["test"]), "auxiliary_test": not bool(sets["auxiliary"] & sets["test"])},
            "meaning": "Descriptive fixed-sample coverage only; code zero uses each historical manifest encoding; no criteria change"}

def _evaluate_task(spec: dict[str, Any], corpus: str, task: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
    np, limits = _numeric()
    repetitions = _bounded_count(spec["repetitions"], 4096, "replication count")
    probabilities, verified = _conditional_probabilities(task, inputs)
    parameters = RRParameters.from_dict(inputs["parameters"])
    independent_ratio = parameters.L / parameters.d
    independent_accuracy = independent_ratio / (1 + independent_ratio)
    independent_probabilities = [independent_accuracy if y else 1 - independent_accuracy for y in task["train"]["y"]]
    bound = lcm(*(p.denominator for p in (*probabilities, *independent_probabilities)))
    if not 1 <= bound < 2 ** 63:
        raise BenchmarkError("Public simulation integer-ticket bound is unsupported")
    rng = np.random.Generator(np.random.PCG64(_seed(spec, corpus, "fresh")))
    tickets = rng.integers(0, bound, size=(repetitions, len(probabilities)), dtype=np.int64)
    targets = {"independent_rr": (tickets < np.array([p.numerator * (bound // p.denominator) for p in independent_probabilities], dtype=np.int64)).astype(np.uint8),
               "certified_continuation": (tickets < np.array([p.numerator * (bound // p.denominator) for p in probabilities], dtype=np.int64)).astype(np.uint8)}
    train_design = encode_features(task["train"]["B"], task["category_sizes"])
    aux_design = encode_features(task["auxiliary"]["B"], task["category_sizes"])
    test_design = encode_features(task["test"]["B"], task["category_sizes"])
    test_truth = np.asarray(task["test"]["y"], dtype=np.float64)
    with limits(limits=1):
        train_projection = _projection(train_design)
        public_coefficients = _projection(aux_design) @ np.asarray(task["auxiliary"]["y"], dtype=np.float64)
        public_predictions = np.clip(test_design @ public_coefficients, 0.0, 1.0)
        public_loss = float(np.mean((public_predictions - test_truth) ** 2))
        reference_coefficients, reference_predictions = {"public_only": public_coefficients.tolist()}, {"public_only": public_predictions.tolist()}
        losses = {}
        for route in ("independent_rr", "certified_continuation"):
            accuracy = independent_accuracy if route == "independent_rr" else verified.marginal_accuracy
            decoded = decode_targets(targets[route], accuracy)
            coefficients = (train_projection @ decoded.T).T
            predictions = np.clip(coefficients @ test_design.T, 0.0, 1.0)
            loss = np.mean((predictions - test_truth[None, :]) ** 2, axis=1)
            if not np.isfinite(loss).all():
                raise BenchmarkError("Nonfinite benchmark loss prevents a result")
            losses[route] = loss
            reference_coefficients[route] = coefficients[0].tolist()
            reference_predictions[route] = predictions[0].tolist()
    gains = {"public_only": public_loss - losses["certified_continuation"],
             "independent_rr": losses["independent_rr"] - losses["certified_continuation"]}
    comparisons = {route: comparison_interval(values, family_size=spec["uncertainty"]["family_size"], alpha=spec["uncertainty"]["alpha"], margin=spec["practical_margin"])
                   for route, values in gains.items()}
    expected = {"public_only": public_loss, **{route: float(np.mean(values)) for route, values in losses.items()}}
    reference = {"public_only": public_loss, **{route: float(values[0]) for route, values in losses.items()}}
    quantiles = {route: {"p025": float(np.quantile(values, .025, method="linear")), "p975": float(np.quantile(values, .975, method="linear"))} for route, values in losses.items()}
    return {"result": {"task_id": corpus, "title": spec["sources"][corpus]["title"],
                       "status": aggregate_outcomes([entry["status"] for entry in comparisons.values()]),
                       "expected_brier": expected, "reference_brier": reference, "comparisons": comparisons,
                       "predictive_loss_quantiles": quantiles,
                       "certificate": {"claim": verified.claim, "marginal_accuracy": rational_string(verified.marginal_accuracy),
                                       "conditional_accuracies": [rational_string(p) for p in verified.conditional_accuracies], "certificate_sha256": verified.digest},
                       "coverage": _coverage(task)},
            "coefficients": reference_coefficients, "predictions": reference_predictions,
            "reference_targets": {route: values[0].tolist() for route, values in targets.items()},
            "loss_vectors": {route: values.tolist() for route, values in losses.items()},
            "paired_gain_vectors": {route: values.tolist() for route, values in gains.items()}, "integer_ticket_bound": bound}

def evaluate_benchmark(spec: Any, cohorts: Any, inputs: Any) -> dict[str, Any]:
    spec = _spec(spec)
    cohorts = _cohorts(spec, cohorts)
    if canonical_bytes(inputs) != canonical_bytes(prepare_inputs(spec, cohorts)):
        raise BenchmarkError("Retained responses, certificate or context differ from the prospectively registered public inputs")
    computed = {corpus: _evaluate_task(spec, corpus, cohorts["tasks"][corpus], inputs["tasks"][corpus]) for corpus in spec["tasks_order"]}
    results = [computed[corpus]["result"] for corpus in spec["tasks_order"]]
    uncertainty = {**spec["uncertainty"], "repetitions": spec["repetitions"], "numerical_guard": 1e-9,
                   "radius": sqrt(2 * log(2 * spec["uncertainty"]["family_size"] / spec["uncertainty"]["alpha"]) / spec["repetitions"]) + 1e-9}
    evaluation = {"schema": "mra-public-benchmark-evaluation/1.0", "status": aggregate_outcomes([task["status"] for task in results]),
                  "task_results": results, "metric": spec["metric"], "uncertainty": uncertainty,
                  "operational_usefulness": "not_evaluated", "scope": spec["scope"], **AUTHORITY}
    models = {"schema": "mra-public-benchmark-models/1.0", "learner": spec["learner"], "tasks": {}, **AUTHORITY}
    predictions = {"schema": "mra-public-benchmark-predictions/1.0", "tasks": {}, **AUTHORITY}
    reference_blocks = {"schema": "mra-public-benchmark-reference-blocks/1.0", "reference_replication_index": 0,
                        "scope": "First preregistered public simulation only; no protected block or score selection", "tasks": {}, **AUTHORITY}
    diagnostics = {"schema": "mra-public-benchmark-diagnostics/1.0", "repetitions": spec["repetitions"], "uncertainty": uncertainty, "tasks": {}, **AUTHORITY}
    for corpus in spec["tasks_order"]:
        task, calculated = cohorts["tasks"][corpus], computed[corpus]
        feature_names = ["intercept"] + [f"{name}={level}" for name, size in zip(task["feature_names"], task["category_sizes"]) for level in range(size)]
        models["tasks"][corpus] = {"coefficient_names": feature_names,
                                   "routes": {route: {"coefficients": calculated["coefficients"][route],
                                                      "decoder_accuracy": "1/1" if route == "public_only" else "3/4" if route == "independent_rr" else calculated["result"]["certificate"]["marginal_accuracy"]} for route in _ROUTES},
                                   "reference_replication_index": 0}
        predictions["tasks"][corpus] = {"test_keys": task["test"]["keys"], "test_truth": task["test"]["y"], "routes": calculated["predictions"],
                                       "reference_row_losses": {route: [(prediction - truth) ** 2 for prediction, truth in zip(values, task["test"]["y"])]
                                                                for route, values in calculated["predictions"].items()},
                                       "reference_replication_index": 0}
        reference_blocks["tasks"][corpus] = {"train_keys": task["train"]["keys"], "retained_responses": inputs["tasks"][corpus]["retained_responses"], "routes": calculated["reference_targets"]}
        diagnostics["tasks"][corpus] = {"loss_vectors": calculated["loss_vectors"], "paired_gain_vectors": calculated["paired_gain_vectors"],
                                        "integer_ticket_bound": calculated["integer_ticket_bound"], "predictive_loss_quantiles": calculated["result"]["predictive_loss_quantiles"]}
    reproducibility = {"schema": "mra-public-benchmark-reproducibility/1.0", "specification_sha256": sha_bytes(canonical_bytes(spec)),
                       "cohorts_sha256": sha_bytes(canonical_bytes(cohorts)), "inputs_sha256": sha_bytes(canonical_bytes(inputs)),
                       "python": platform.python_version(), "dependencies": dependency_status(), "numerical_threads": 1,
                       "simulation": spec["simulation"], "reference_replication_index": 0,
                       "coverage": {corpus: computed[corpus]["result"]["coverage"] for corpus in spec["tasks_order"]},
                       "model_selection": "none", "population_uncertainty": "not_evaluated", **AUTHORITY}
    lines = ["Phase 4 preregistered public usefulness benchmark", f"Overall result: {evaluation['status']}",
             "Operational usefulness: not_evaluated. Authorization effect: none.",
             "Monte Carlo integration concerns fixed historical public rows and saved retained responses.",
             uncertainty["interpretation"], "Reference models use replication zero; their scores are descriptive only."]
    for result in results:
        lines.append(f"{result['title']}: {result['status']}")
        for route, comparison in result["comparisons"].items():
            lines.append(f"  {route}: {comparison['status']}; gain {comparison['gain']:.12g}; simultaneous interval [{comparison['lower']:.12g}, {comparison['upper']:.12g}]; margin {comparison['margin']:.12g}")
    lines.extend(["No favorable seed, cohort replacement, tuning or additional repetitions are permitted.",
                  "Population representativeness, agency custody, operational margins, independent acceptance and release enforcement remain pending."])
    bundle = {"evaluation.json": evaluation, "models.json": models, "predictions.json": predictions, "reference-blocks.json": reference_blocks,
              "simulation-diagnostics.json": diagnostics, "reproducibility.json": reproducibility, "evaluation.txt": "\n".join(lines) + "\n"}
    for name, value in bundle.items():
        raw = value.encode("utf-8") if name.endswith(".txt") else canonical_bytes(value)
        if len(raw) > MAX_JSON_BYTES:
            raise BenchmarkError("Benchmark output exceeds its bounded artifact size")
    return bundle
