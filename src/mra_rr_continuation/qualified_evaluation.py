"""Execute immutable MOH/MAS/MSF public finite-frame usefulness diagnostics.

Caller durably retains the execution contract before deriving outcomes, and
cohorts plus one retained-response input bundle before fresh simulation/fitting.
No agency acceptance, operational usefulness or release authority is established.
"""
from __future__ import annotations
from fractions import Fraction
import hashlib
import json
from math import isfinite, lcm, log, sqrt
from pathlib import Path
import platform
from typing import Any, Callable
from . import benchmark, qualified_encoding as encoding
from .certificates import RRParameters, ResearchContext, build_certificate, rational_string, verify_certificate
from .sampling import ConditionalSampler

SPECIFICATION_SHA256 = "b6fd59634f6ca82224f7febabf0e1c9bd960101a4de6e676df00a49039244295"
PREREGISTRATION_ID = "1f533833767c74bf262c18145c9bbe8c"
AGENCIES = ("moh", "mas", "msf")
ROUTES = ("public_only", "independent_rr", "certified_continuation")
ARTIFACTS = ("evaluation.json", "models.json", "predictions.json", "reference-blocks.json", "simulation-diagnostics.json", "reproducibility.json", "evaluation.txt")
AUTHORITY = {"authorization_effect": "none", "agency_acceptance": "pending", "operational_usefulness": "not_evaluated", "production_execution_qualified": False}
PERIOD_SIZES = {"moh": 53, "mas": 12, "msf": 1}
FIRST_YEARS = {"moh": 2012, "mas": 1991, "msf": 2019}

class EvaluationError(ValueError):
    """Unbound, malformed or changed public benchmark evidence."""

canonical_bytes = benchmark.canonical_bytes
sha_bytes = benchmark.sha_bytes

def specification():
    raw = (Path(__file__).parent / "static" / "qualified-specification.json").read_bytes()
    if sha_bytes(raw) != SPECIFICATION_SHA256:
        raise EvaluationError("The frozen Phase 5 specification bytes changed")
    value = json.loads(raw)
    if canonical_bytes(value) != raw:
        raise EvaluationError("The frozen specification is not canonical")
    return value

def _spec(value):
    if type(value) is not dict or canonical_bytes(value) != canonical_bytes(specification()):
        raise EvaluationError("Frozen benchmark plan overrides are refused")
    return value

def execution_contract():
    """Mechanical choices admitted by, and consistent with, the frozen plan."""
    return {
        "schema": "mra-qualified-evaluation-execution-contract/1.0", "phase": 6,
        "preregistration_id": PREREGISTRATION_ID, "specification_sha256": SPECIFICATION_SHA256,
        "plan_changes": False,
        "seed": {"material": "ASCII seed_domain + ':' + agency + ':' + purpose",
                 "conversion": "SHA256 digest as unsigned big-endian integer",
                 "purposes": ["retained", "fresh"], "generator": "NumPy Generator(PCG64(seed))"},
        "row_order": "Existing qualified-encoding rows, sorted publisher ordinal then exact series then key; cohorts preserve that order",
        "design_columns": "intercept, (target_year-source_first_year)/10, one-hot period1..published maximum, full exact source series vocabulary1..N, lag bins0..14",
        "period_sizes": dict(PERIOD_SIZES), "source_first_years": dict(FIRST_YEARS),
        "one_hot_reference_level": "None dropped; alpha1 slopes and unpenalized intercept give a unique ridge solution",
        "retained_tickets": "PCG64 int64 integers[0,4), training-row order; response=z when ticket<3, else1-z",
        "fresh_tickets": "PCG64 int64 integers[0,20), row-major replicate then training row; exactly256replicates per batch, exactly16384 total",
        "fresh_coupling": "Same integer ticket drives candidate and independent response-one exact rational thresholds",
        "conditional_law": "Verified exact r1 sampler distribution using y,z,savedW; W never refreshed",
        "fitter_boundary": "Only public encoded covariates and mechanism-marginal decoded fresh response bits enter randomized fitting",
        "ridge_algebra": "Fixed (X'X+diag(0,1,...,1)) inverse; sparse exact-column sufficient statistics and test prediction equivalent to dense ridge; float64, BLAS threads1",
        "decoder": "Continuation (bit-3/20)/(7/10); independent (bit-1/4)/(1/2); public-only clean auxiliary bits",
        "quantiles": "Empirical p025,p975 with NumPy method='linear', descriptive only",
        "numerical_guard": "Hoeffding radius plus1e-9, endpoints clipped[-1,1]; strict lower>0 pass, upper<=0 fail",
        "reference": "Replication index0, no favourable score selection",
        "ordering": "Contract fsynced before outcomes; cohorts and seededW/cert inputs fsynced before fresh RNG and fitting; completion last",
        "verification_scope": "Local source/plan/input replay and result consistency; hashes/timestamps do not prove independent custody or agency approval",
        **AUTHORITY}

def _numeric():
    return benchmark._numeric()

def _seed(spec, agency, purpose):
    material = spec["uncertainty_plan"]["seed_domain"] + ":" + agency + ":" + purpose
    return int.from_bytes(hashlib.sha256(material.encode("ascii")).digest(), "big")

def design_contract(agency):
    if agency not in AGENCIES:
        raise EvaluationError("Unknown mandatory agency")
    names = ["intercept", "centered_calendar_year"] + [
        f"target_period={part}" for part in range(1, PERIOD_SIZES[agency] + 1)] + [
        f"series_code={code}:{series}" for code, series in enumerate(encoding.VOCABULARIES[agency], 1)] + [
        f"previous_level_bin={code}" for code in range(15)]
    return {"first_year": FIRST_YEARS[agency], "period_size": PERIOD_SIZES[agency],
            "series_size": len(encoding.VOCABULARIES[agency]), "level_bin_size": 15, "coefficient_names": names}

def prepare_cohorts(spec, source_bytes):
    """Derive exact public bits after caller persists the execution contract."""
    spec = _spec(spec)
    if type(source_bytes) is not dict or set(source_bytes) != set(AGENCIES):
        raise EvaluationError("Exactly the three frozen public sources are required")
    for agency in AGENCIES:
        if type(source_bytes[agency]) is not bytes or sha_bytes(source_bytes[agency]) != spec["sources"][agency]["csv_sha256"]:
            raise EvaluationError("Public source differs from frozen byte pin")
    audit = encoding.qualify_sources(source_bytes)
    tasks = {}
    for agency in AGENCIES:
        domain = audit["agencies"][agency]
        if domain["raw_observations"] != spec["sources"][agency]["expected_observations"]:
            raise EvaluationError("Public source observation count changed")
        observations = encoding._observations(agency, source_bytes[agency])
        by_ref = {(o["series"], o["line"], o["column"], o["period"]): o for o in observations}
        task = {split: {"keys": [], "B": [], "y": [], **({"z": []} if split == "train" else {})}
                for split in ("train", "auxiliary", "test")}
        for row in domain["rows"]:
            earlier, previous, current = [by_ref[(row["series"], ref["line"], ref["column"], ref["period"])]
                                          for ref in row["label_recipe_references"]]
            if not (earlier["ordinal"] + 1 == previous["ordinal"] and previous["ordinal"] + 1 == current["ordinal"]):
                raise EvaluationError("Nonconsecutive public target lineage")
            group = task[row["split"]]
            group["keys"].append(row["key"]); group["B"].append(row["features"])
            group["y"].append(int(current["value"] > previous["value"]))
            if row["split"] == "train":
                group["z"].append(int(previous["value"] > earlier["value"]))
        task.update({"feature_names": list(encoding.FEATURES), "design_contract": design_contract(agency),
                     "source_sha256": domain["source_sha256"], "split_counts": domain["split_counts"],
                     "coverage": {k: domain[k] for k in ("raw_observations", "eligible_observations", "exclusions",
                         "legitimate_zero_lag_features", "unknown_or_missing_encodings", "calendar_method", "limitations")},
                     "target_frame": domain["target_frame"]})
        tasks[agency] = task
    value = {"schema": "mra-qualified-evaluation-cohorts/1.0", "specification_sha256": sha_bytes(canonical_bytes(spec)),
             "execution_contract_sha256": sha_bytes(canonical_bytes(execution_contract())), "tasks": tasks, **AUTHORITY}
    _cohorts(spec, value)
    return value

def _cohorts(spec, value):
    if (type(value) is not dict or value.get("schema") != "mra-qualified-evaluation-cohorts/1.0"
            or value.get("specification_sha256") != sha_bytes(canonical_bytes(spec))
            or value.get("execution_contract_sha256") != sha_bytes(canonical_bytes(execution_contract()))
            or type(value.get("tasks")) is not dict or set(value["tasks"]) != set(AGENCIES)
            or any(type(value.get(k)) is not type(v) or value.get(k) != v for k, v in AUTHORITY.items())):
        raise EvaluationError("Invalid bound public cohorts")
    for agency in AGENCIES:
        task = value["tasks"][agency]
        if (type(task) is not dict or task.get("feature_names") != list(encoding.FEATURES)
                or task.get("design_contract") != design_contract(agency)
                or task.get("source_sha256") != spec["sources"][agency]["csv_sha256"]):
            raise EvaluationError("Public covariates differ from fixed learner")
        seen = set()
        for split in ("train", "auxiliary", "test"):
            group = task.get(split)
            fields = {"keys", "B", "y", "z"} if split == "train" else {"keys", "B", "y"}
            if type(group) is not dict or set(group) != fields:
                raise EvaluationError("Invalid public cohort fields")
            count = len(group["keys"]) if type(group.get("keys")) is list else 0
            if (not 1 <= count <= 65536 or task.get("split_counts", {}).get(split) != count
                    or any(type(group[f]) is not list or len(group[f]) != count for f in fields)):
                raise EvaluationError("Invalid aligned public cohort counts")
            keys = group["keys"]
            if any(type(k) is not str or len(k) != 64 or any(c not in "0123456789abcdef" for c in k) for k in keys):
                raise EvaluationError("Invalid public row key")
            if len(set(keys)) != count or seen.intersection(keys):
                raise EvaluationError("Public cohorts require disjoint unique rows")
            seen.update(keys)
            for field in fields & {"y", "z"}:
                if any(type(bit) is not int or bit not in (0, 1) for bit in group[field]):
                    raise EvaluationError("Exact integer bits required")
            _design_parts(group["B"], agency)
    canonical_bytes(value)
    return value

def _input_task(spec, agency, cohorts, responses):
    parameters = RRParameters(1, 3, 9, Fraction(2, 3))
    cohort_hash = sha_bytes(canonical_bytes(cohorts)); spec_hash = sha_bytes(canonical_bytes(spec))
    contract_hash = sha_bytes(canonical_bytes(execution_contract()))
    keys = cohorts["tasks"][agency]["train"]["keys"]
    law = {"schema": "mra-qualified-public-retained-law/1.0", "d": "3/1", "task_id": agency,
           "specification_sha256": spec_hash, "cohorts_sha256": cohort_hash,
           "execution_contract_sha256": contract_hash, "randomness": "fixed seeded public PCG64 simulation"}
    response_document = {"schema": "mra-qualified-public-retained-responses/1.0", "task_id": agency,
                         "records": [{"record_id": k, "w": w} for k, w in zip(keys, responses)]}
    history = {"schema": "mra-qualified-public-history/1.0", "task_id": agency,
               "retained_law_sha256": sha_bytes(canonical_bytes(law)),
               "retained_response_sha256": sha_bytes(canonical_bytes(response_document)),
               "additional_protected_outputs": False, "scope": "public simulation only"}
    request = {"schema": "mra-qualified-public-request/1.0", "task_id": agency,
               "parameters": parameters.to_dict(), "train_record_ids": keys,
               "specification_sha256": spec_hash, "cohorts_sha256": cohort_hash,
               "execution_contract_sha256": contract_hash, "candidate": "optimal_r1", "visible_decisions": "frozen_public_fixed"}
    context = ResearchContext(sha_bytes(canonical_bytes(law)), sha_bytes(canonical_bytes(response_document)),
                              sha_bytes(canonical_bytes(history)), sha_bytes(canonical_bytes(request)))
    certificate = build_certificate(parameters, context)
    verified = verify_certificate(certificate, expected_parameters=parameters, expected_context=context)
    if (verified.claim != "optimal" or verified.marginal_accuracy != Fraction(17, 20)
            or verified.conditional_accuracies != (Fraction(9, 10), Fraction(7, 10))):
        raise EvaluationError("Exact frozen continuation certificate failed")
    return {"parameters": parameters.to_dict(), "context": context.to_dict(), "certificate": certificate,
            "certificate_sha256": verified.digest, "retained_responses": responses, "retained_law": law,
            "retained_response_document": response_document, "history": history, "request_plan": request,
            "certificate_verification": {"status": "verified", "claim": "optimal", "marginal_accuracy": "17/20",
                                         "conditional_accuracies": ["9/10", "7/10"], "authorization_effect": "none"}}

def _retained_responses(spec, agency, train):
    np, _ = _numeric()
    rng = np.random.Generator(np.random.PCG64(_seed(spec, agency, "retained")))
    tickets = rng.integers(0, 4, size=len(train["z"]), dtype=np.int64)
    z = np.asarray(train["z"], dtype=np.int64)
    return np.where(tickets < 3, z, 1 - z).tolist()

def prepare_inputs(spec, cohorts):
    """Return one seeded W and exact bound certificates; caller fsyncs it."""
    spec = _spec(spec); cohorts = _cohorts(spec, cohorts)
    return {"schema": "mra-qualified-evaluation-inputs/1.0",
            "specification_sha256": sha_bytes(canonical_bytes(spec)), "cohorts_sha256": sha_bytes(canonical_bytes(cohorts)),
            "execution_contract_sha256": sha_bytes(canonical_bytes(execution_contract())),
            "tasks": {a: _input_task(spec, a, cohorts, _retained_responses(spec, a, cohorts["tasks"][a]["train"])) for a in AGENCIES},
            **AUTHORITY}

def verify_inputs(spec, cohorts, inputs):
    spec = _spec(spec); cohorts = _cohorts(spec, cohorts)
    if canonical_bytes(inputs) != canonical_bytes(prepare_inputs(spec, cohorts)):
        raise EvaluationError("Saved retained history or certificate differs from frozen public input replay")
    for agency in AGENCIES:
        item = inputs["tasks"][agency]
        verify_certificate(item["certificate"], expected_parameters=RRParameters.from_dict(item["parameters"]),
                           expected_context=ResearchContext.from_dict(item["context"]), expected_certificate_sha256=item["certificate_sha256"])
    return True


def _design_parts(B, agency):
    np, _ = _numeric()
    values = np.asarray(B)
    if (values.ndim != 2 or values.shape[1] != 4 or not 1 <= len(values) <= 65536
            or values.dtype.kind not in "iu" or agency not in AGENCIES):
        raise EvaluationError("Ridge requires only aligned legal public covariates")
    years, periods, series, bins = (values[:, i] for i in range(4))
    if (np.any(years < FIRST_YEARS[agency]) or np.any(years > 2024)
            or np.any(periods < 1) or np.any(periods > PERIOD_SIZES[agency])
            or np.any(series < 1) or np.any(series > len(encoding.VOCABULARIES[agency]))
            or np.any(bins < 0) or np.any(bins > 14)):
        raise EvaluationError("Public covariates exceed semantic bounds")
    return (years.astype(np.float64) - FIRST_YEARS[agency]) / 10.0, (
        periods.astype(np.int64) - 1, series.astype(np.int64) - 1, bins.astype(np.int64))

def encode_design(B, agency):
    np, _ = _numeric()
    year, codes = _design_parts(B, agency)
    widths = (PERIOD_SIZES[agency], len(encoding.VOCABULARIES[agency]), 15)
    design = np.zeros((len(year), 2 + sum(widths)), dtype=np.float64)
    design[:, 0] = 1.0; design[:, 1] = year
    offset = 2
    for code, width in zip(codes, widths):
        design[np.arange(len(year)), offset + code] = 1.0
        offset += width
    return design

def _ridge_inverse(B, agency):
    np, _ = _numeric()
    X = encode_design(B, agency)
    penalty = np.eye(X.shape[1], dtype=np.float64); penalty[0, 0] = 0.0
    gram = X.T @ X + penalty
    inverse = np.linalg.solve(gram, np.eye(gram.shape[0], dtype=np.float64))
    if not np.isfinite(inverse).all():
        raise EvaluationError("Nonfinite fixed ridge factorization")
    return inverse

def fit_decoded(B, decoded, agency, *, inverse=None):
    """Only public covariates and decoded fresh responses enter the fit."""
    np, _ = _numeric()
    year, codes = _design_parts(B, agency)
    targets = np.asarray(decoded, dtype=np.float64)
    one = targets.ndim == 1
    if one:
        targets = targets[None, :]
    if (targets.ndim != 2 or targets.shape[1] != len(year)
            or not 1 <= len(targets) <= 256 or not np.isfinite(targets).all()):
        raise EvaluationError("Invalid bounded decoded responses")
    widths = (PERIOD_SIZES[agency], len(encoding.VOCABULARIES[agency]), 15)
    rhs = np.zeros((2 + sum(widths), len(targets)), dtype=np.float64)
    rhs[0] = np.sum(targets, axis=1); rhs[1] = targets @ year
    offset = 2
    for code, width in zip(codes, widths):
        for rep, response in enumerate(targets):
            rhs[offset:offset + width, rep] = np.bincount(code, weights=response, minlength=width)
        offset += width
    coefficients = ((inverse if inverse is not None else _ridge_inverse(B, agency)) @ rhs).T
    if not np.isfinite(coefficients).all():
        raise EvaluationError("Nonfinite ridge coefficients")
    return coefficients[0] if one else coefficients

def predict(B, coefficients, agency):
    np, _ = _numeric()
    year, codes = _design_parts(B, agency)
    coefficients = np.asarray(coefficients, dtype=np.float64)
    one = coefficients.ndim == 1
    if one:
        coefficients = coefficients[None, :]
    widths = (PERIOD_SIZES[agency], len(encoding.VOCABULARIES[agency]), 15)
    if (coefficients.ndim != 2 or coefficients.shape[1] != 2 + sum(widths)
            or not 1 <= len(coefficients) <= 256 or not np.isfinite(coefficients).all()):
        raise EvaluationError("Invalid fixed affine ridge coefficients")
    values = coefficients[:, :1] + coefficients[:, 1:2] * year[None, :]
    offset = 2
    for code, width in zip(codes, widths):
        values += coefficients[:, offset + code]; offset += width
    values = np.clip(values, 0.0, 1.0)
    return values[0] if one else values

def research_decision(lower, upper):
    if any(type(v) not in (int, float) or not isfinite(v) for v in (lower, upper)) or lower > upper:
        raise EvaluationError("Invalid finite research endpoints")
    return "pass" if lower > 0 else "fail" if upper <= 0 else "inconclusive"

def comparison_interval(gains):
    np, _ = _numeric()
    values = np.asarray(gains, dtype=np.float64)
    if (values.ndim != 1 or not 1 <= len(values) <= 16384 or not np.isfinite(values).all()
            or np.any(values < -1) or np.any(values > 1)):
        raise EvaluationError("Invalid bounded paired Brier gains")
    radius = sqrt(2 * log(2 * 6 / .05) / len(values)) + 1e-9
    gain = float(np.mean(values)); lower, upper = max(-1., gain - radius), min(1., gain + radius)
    return {"status": research_decision(lower, upper), "gain": gain, "lower": lower, "upper": upper,
            "margin": 0.0, "radius": radius, "repetitions": len(values), "family_size": 6, "family_alpha": .05}

def aggregate_outcomes(values):
    if type(values) is not list or not values or any(v not in ("pass", "fail", "inconclusive") for v in values):
        raise EvaluationError("Every mandatory outcome required")
    return "fail" if "fail" in values else "inconclusive" if "inconclusive" in values else "pass"

def _conditional_probabilities(task, inputs):
    parameters = RRParameters.from_dict(inputs["parameters"]); context = ResearchContext.from_dict(inputs["context"])
    verified = verify_certificate(inputs["certificate"], expected_parameters=parameters,
                                  expected_context=context, expected_certificate_sha256=inputs["certificate_sha256"])
    if verified.claim != "optimal" or verified.marginal_accuracy != Fraction(17, 20):
        raise EvaluationError("Exact optimal certificate gate failed")
    sampler = ConditionalSampler(inputs["certificate"], expected_parameters=parameters,
                                 expected_context=context, expected_certificate_sha256=verified.digest)
    lookup = {(z, y, w): dict(sampler.conditional_distribution([z, y], w))[(1,)]
              for z in (0, 1) for y in (0, 1) for w in (0, 1)}
    return [lookup[(z, y, w)] for z, y, w in zip(
        task["train"]["z"], task["train"]["y"], inputs["retained_responses"])], verified

def _fresh_thresholds(task, inputs):
    np, _ = _numeric()
    probabilities, verified = _conditional_probabilities(task, inputs)
    independent = [Fraction(3, 4) if y else Fraction(1, 4) for y in task["train"]["y"]]
    bound = lcm(*(p.denominator for p in probabilities + independent))
    if bound != 20:
        raise EvaluationError("Frozen exact common ticket bound changed")
    return bound, {
        "certified_continuation": np.asarray([p.numerator * (bound // p.denominator) for p in probabilities], dtype=np.int64),
        "independent_rr": np.asarray([p.numerator * (bound // p.denominator) for p in independent], dtype=np.int64)}, verified

def _coverage(task):
    return {**task["coverage"], "counts": task["split_counts"],
            "outcome_prevalence": {s: {"y": sum(task[s]["y"]) / len(task[s]["y"]),
                                      **({"z": sum(task[s]["z"]) / len(task[s]["z"])} if s == "train" else {})}
                                   for s in ("train", "auxiliary", "test")},
            "test_inclusion_probability": "1/1", "population_uncertainty": "not_evaluated"}

def _result(spec, agency, task, inputs, losses, public_loss, reference_losses):
    np, _ = _numeric()
    gains = {"public_only": public_loss - losses["certified_continuation"],
             "independent_rr": losses["independent_rr"] - losses["certified_continuation"]}
    comparisons = {r: comparison_interval(v) for r, v in gains.items()}
    return {"task_id": agency, "title": spec["sources"][agency]["task_title"],
            "status": aggregate_outcomes([v["status"] for v in comparisons.values()]),
            "expected_brier": {"public_only": public_loss, **{r: float(np.mean(v)) for r, v in losses.items()}},
            "reference_brier": reference_losses, "comparisons": comparisons,
            "predictive_loss_quantiles": {r: {"p025": float(np.quantile(v, .025, method="linear")),
                                              "p975": float(np.quantile(v, .975, method="linear"))} for r, v in losses.items()},
            "certificate": inputs["certificate_verification"], "coverage": _coverage(task)}, gains

def _evaluate_task(spec, agency, task, inputs, progress=None):
    np, limits = _numeric()
    repetitions = spec["uncertainty_plan"]["repetitions_per_task"]
    batch_size = spec["uncertainty_plan"]["fixed_batch_size"]
    if (type(repetitions) is not int or not 1 <= repetitions <= 16384
            or type(batch_size) is not int or not 1 <= batch_size <= 256 or repetitions % batch_size):
        raise EvaluationError("Invalid fixed batching contract")
    bound, thresholds, _ = _fresh_thresholds(task, inputs)
    rng = np.random.Generator(np.random.PCG64(_seed(spec, agency, "fresh")))
    truth = np.asarray(task["test"]["y"], dtype=np.float64)
    losses = {r: np.empty(repetitions, dtype=np.float64) for r in ("independent_rr", "certified_continuation")}
    coefficients0, predictions0, bits0 = {}, {}, {}
    ticket_digest = hashlib.sha256()
    with limits(limits=1):
        inverse = _ridge_inverse(task["train"]["B"], agency)
        public_coefficients = fit_decoded(task["auxiliary"]["B"], task["auxiliary"]["y"], agency)
        public_predictions = predict(task["test"]["B"], public_coefficients, agency)
        public_loss = float(np.mean((public_predictions - truth) ** 2))
        coefficients0["public_only"] = public_coefficients.tolist(); predictions0["public_only"] = public_predictions.tolist()
        for start in range(0, repetitions, batch_size):
            tickets = rng.integers(0, bound, size=(batch_size, len(task["train"]["y"])), dtype=np.int64)
            ticket_digest.update(tickets.astype("<i8", copy=False).tobytes(order="C"))
            for route, accuracy in (("independent_rr", Fraction(3, 4)), ("certified_continuation", Fraction(17, 20))):
                bits = (tickets < thresholds[route][None, :]).astype(np.uint8)
                decoded = benchmark.decode_targets(bits, accuracy)
                coefficients = fit_decoded(task["train"]["B"], decoded, agency, inverse=inverse)
                predictions = predict(task["test"]["B"], coefficients, agency)
                loss = np.mean((predictions - truth[None, :]) ** 2, axis=1)
                if not np.isfinite(loss).all() or np.any(loss < 0) or np.any(loss > 1):
                    raise EvaluationError("Invalid bounded Brier loss")
                losses[route][start:start + batch_size] = loss
                if start == 0:
                    coefficients0[route] = coefficients[0].tolist()
                    predictions0[route] = predictions[0].tolist(); bits0[route] = bits[0].tolist()
            if progress is not None:
                progress({"task_id": agency, "completed_repetitions": start + batch_size,
                          "repetitions_per_task": repetitions, "fixed_batch_size": batch_size})
    reference_losses = {"public_only": public_loss, **{r: float(v[0]) for r, v in losses.items()}}
    result, gains = _result(spec, agency, task, inputs, losses, public_loss, reference_losses)
    return {"result": result, "coefficients": coefficients0, "predictions": predictions0, "reference_targets": bits0,
            "loss_vectors": {r: v.tolist() for r, v in losses.items()},
            "paired_gain_vectors": {r: v.tolist() for r, v in gains.items()},
            "integer_ticket_bound": bound, "fresh_ticket_sha256": ticket_digest.hexdigest()}


def evaluate_benchmark(spec, cohorts, inputs, progress=None):
    """Run all fixed repetitions only after store durably retains inputs."""
    spec = _spec(spec); cohorts = _cohorts(spec, cohorts); verify_inputs(spec, cohorts, inputs)
    computed = {a: _evaluate_task(spec, a, cohorts["tasks"][a], inputs["tasks"][a], progress) for a in AGENCIES}
    return _bundle(spec, cohorts, inputs, computed)

def _bundle(spec, cohorts, inputs, computed):
    results = [computed[a]["result"] for a in AGENCIES]
    uncertainty = {**spec["uncertainty_plan"], "numerical_guard": 1e-9,
                   "radius": sqrt(2 * log(2 * 6 / .05) / spec["uncertainty_plan"]["repetitions_per_task"]) + 1e-9}
    evaluation = {"schema": "mra-qualified-public-evaluation/1.0", "phase": 6,
                  "status": aggregate_outcomes([t["status"] for t in results]), "public_usefulness": "evaluated",
                  "preregistration_id": PREREGISTRATION_ID, "specification_sha256": sha_bytes(canonical_bytes(spec)),
                  "task_results": results, "metric": "mean held-out Brier loss",
                  "uncertainty": uncertainty, "scope": spec["scope"], **AUTHORITY}
    models = {"schema": "mra-qualified-public-models/1.0", "learner": spec["learning_plan"],
              "reference_replication_index": 0, "tasks": {}, **AUTHORITY}
    predictions = {"schema": "mra-qualified-public-predictions/1.0", "reference_replication_index": 0, "tasks": {}, **AUTHORITY}
    blocks = {"schema": "mra-qualified-public-reference-blocks/1.0", "reference_replication_index": 0,
              "scope": "First fixed public simulated block only; no protected disclosure", "tasks": {}, **AUTHORITY}
    diagnostics = {"schema": "mra-qualified-public-diagnostics/1.0",
                   "repetitions": spec["uncertainty_plan"]["repetitions_per_task"],
                   "fixed_batch_size": spec["uncertainty_plan"]["fixed_batch_size"], "uncertainty": uncertainty, "tasks": {}, **AUTHORITY}
    for agency in AGENCIES:
        task, calc = cohorts["tasks"][agency], computed[agency]
        models["tasks"][agency] = {"coefficient_names": task["design_contract"]["coefficient_names"],
            "routes": {r: {"coefficients": calc["coefficients"][r],
                          "decoder_accuracy": "1/1" if r == "public_only" else "3/4" if r == "independent_rr" else "17/20"} for r in ROUTES}}
        predictions["tasks"][agency] = {"test_keys": task["test"]["keys"], "test_truth": task["test"]["y"],
            "routes": calc["predictions"], "reference_row_losses": {
                r: [(p - y) ** 2 for p, y in zip(v, task["test"]["y"])] for r, v in calc["predictions"].items()}}
        blocks["tasks"][agency] = {"train_keys": task["train"]["keys"],
            "retained_responses": inputs["tasks"][agency]["retained_responses"], "routes": calc["reference_targets"]}
        diagnostics["tasks"][agency] = {k: calc[k] for k in ("loss_vectors", "paired_gain_vectors", "integer_ticket_bound", "fresh_ticket_sha256")}
    repro = {"schema": "mra-qualified-public-reproducibility/1.0",
             "specification_sha256": sha_bytes(canonical_bytes(spec)),
             "execution_contract_sha256": sha_bytes(canonical_bytes(execution_contract())),
             "cohorts_sha256": sha_bytes(canonical_bytes(cohorts)), "inputs_sha256": sha_bytes(canonical_bytes(inputs)),
             "python": platform.python_version(), "dependencies": benchmark.dependency_status(), "numerical_threads": 1,
             "simulation": spec["uncertainty_plan"], "reference_replication_index": 0, "model_selection": "none",
             "retained_history": "One durably saved public simulated W vector per task, never refreshed during fresh-law integration",
             "population_uncertainty": "not_evaluated", **AUTHORITY}
    lines = ["Phase 6 frozen MOH, MAS and MSF public usefulness benchmark",
             f"Overall research result: {evaluation['status']}",
             "Agency acceptance: pending. Operational usefulness: not_evaluated. Release authority: none.",
             "Finite historical aggregate-frame census, conditional on one saved public simulated retained history per task.",
             "16384 paired repetitions per task, batches256; all6 strict zero-margin comparisons mandatory.",
             "Six-comparison Hoeffding bounds concern conditional MC integration, not people or future periods.",
             "PCG64 approximates ideal independent tickets; source as-of availability is unverified.",
             "Public-only cohort sizes/periods differ; comparison includes data availability and time differences.",
             "Reference models and p025/p975 loss quantiles are descriptive only."]
    for result in results:
        lines.append(f"{result['title']}: {result['status']}")
        for route, comparison in result["comparisons"].items():
            lines.append(f"  {route}: {comparison['status']}; gain {comparison['gain']:.12g}; interval [{comparison['lower']:.12g}, {comparison['upper']:.12g}]; research margin0.")
    lines.append("No agency endorsement, authoritative custody, protected release or production qualification is established.")
    values = {"evaluation.json": evaluation, "models.json": models, "predictions.json": predictions,
              "reference-blocks.json": blocks, "simulation-diagnostics.json": diagnostics,
              "reproducibility.json": repro, "evaluation.txt": "\n".join(lines) + "\n"}
    return {n: v.encode("utf-8") if n.endswith(".txt") else canonical_bytes(v) for n, v in values.items()}

def verify_results(spec, cohorts, inputs, bundle, *, full_replay=False):
    """Semantic consistency; full_replay byte-compares complete execution.

    Cheap checks cannot authenticate coherently rewritten non-reference loss
    vectors against execution. Full replay verifies every deterministic output;
    neither hashes nor local timestamps prove independent custody.
    """
    spec = _spec(spec); cohorts = _cohorts(spec, cohorts); verify_inputs(spec, cohorts, inputs)
    if type(full_replay) is not bool:
        raise EvaluationError("Invalid verification mode")
    if type(bundle) is not dict or set(bundle) != set(ARTIFACTS) or any(type(v) is not bytes for v in bundle.values()):
        raise EvaluationError("All seven exact captured artifact bytes required")
    if full_replay:
        if bundle != evaluate_benchmark(spec, cohorts, inputs):
            raise EvaluationError("Saved results differ from complete deterministic execution replay")
        return True
    np, limits = _numeric()
    decoded = {}
    for name, raw in bundle.items():
        if name.endswith(".json"):
            try:
                decoded[name] = json.loads(raw)
            except (UnicodeError, ValueError) as exc:
                raise EvaluationError("Invalid captured evaluation JSON") from exc
            if canonical_bytes(decoded[name]) != raw:
                raise EvaluationError("Exact canonical evaluation JSON required")
    evaluation, models, predictions, blocks, diagnostics, repro = [decoded[n] for n in ARTIFACTS[:-1]]
    repetitions = spec["uncertainty_plan"]["repetitions_per_task"]
    if (evaluation.get("schema") != "mra-qualified-public-evaluation/1.0"
            or evaluation.get("preregistration_id") != PREREGISTRATION_ID
            or evaluation.get("specification_sha256") != sha_bytes(canonical_bytes(spec))
            or evaluation.get("public_usefulness") != "evaluated"
            or type(evaluation.get("task_results")) is not list or len(evaluation["task_results"]) != 3
            or diagnostics.get("repetitions") != repetitions
            or diagnostics.get("fixed_batch_size") != spec["uncertainty_plan"]["fixed_batch_size"]
            or any(v.get(k) != required for v in decoded.values() for k, required in AUTHORITY.items())):
        raise EvaluationError("Invalid frozen status, authority or repetition fields")
    for field, expected in (("specification_sha256", sha_bytes(canonical_bytes(spec))),
                            ("execution_contract_sha256", sha_bytes(canonical_bytes(execution_contract()))),
                            ("cohorts_sha256", sha_bytes(canonical_bytes(cohorts))),
                            ("inputs_sha256", sha_bytes(canonical_bytes(inputs)))):
        if repro.get(field) != expected:
            raise EvaluationError("Result replay bindings changed")
    rebuilt_results = []; computed = {}
    with limits(limits=1):
        for agency in AGENCIES:
            task, item = cohorts["tasks"][agency], inputs["tasks"][agency]
            if any(type(v.get("tasks")) is not dict or set(v["tasks"]) != set(AGENCIES) for v in (models, predictions, blocks, diagnostics)):
                raise EvaluationError("Mandatory result tasks changed")
            model, forecast, block, diag = [v["tasks"][agency] for v in (models, predictions, blocks, diagnostics)]
            if (forecast["test_keys"] != task["test"]["keys"] or forecast["test_truth"] != task["test"]["y"]
                    or block["train_keys"] != task["train"]["keys"] or block["retained_responses"] != item["retained_responses"]
                    or model["coefficient_names"] != task["design_contract"]["coefficient_names"]
                    or set(diag["loss_vectors"]) != {"independent_rr", "certified_continuation"}
                    or set(diag["paired_gain_vectors"]) != {"public_only", "independent_rr"}):
                raise EvaluationError("Reference rows or vectors changed")
            bound, thresholds, _ = _fresh_thresholds(task, item)
            rng = np.random.Generator(np.random.PCG64(_seed(spec, agency, "fresh")))
            tickets = rng.integers(0, bound, size=len(task["train"]["y"]), dtype=np.int64)
            truth = np.asarray(task["test"]["y"], dtype=np.float64)
            reference_losses = {}
            for route in ROUTES:
                if route == "public_only":
                    coefficients = fit_decoded(task["auxiliary"]["B"], task["auxiliary"]["y"], agency)
                    accuracy = "1/1"
                else:
                    bits = (tickets < thresholds[route]).astype(np.uint8)
                    if block["routes"][route] != bits.tolist():
                        raise EvaluationError("Reference response differs from exact seeded simulation")
                    p = Fraction(3, 4) if route == "independent_rr" else Fraction(17, 20)
                    coefficients = fit_decoded(task["train"]["B"], benchmark.decode_targets(bits, p), agency)
                    accuracy = rational_string(p)
                saved = model["routes"][route]
                if saved["decoder_accuracy"] != accuracy or not np.allclose(coefficients, saved["coefficients"], rtol=0, atol=1e-10):
                    raise EvaluationError("Reference model differs from fixed ridge reconstruction")
                fitted = predict(task["test"]["B"], coefficients, agency)
                if not np.allclose(fitted, forecast["routes"][route], rtol=0, atol=1e-10):
                    raise EvaluationError("Reference prediction differs from fixed ridge reconstruction")
                row_losses = (fitted - truth) ** 2
                if not np.allclose(row_losses, forecast["reference_row_losses"][route], rtol=0, atol=1e-10):
                    raise EvaluationError("Reference row scores changed")
                reference_losses[route] = float(np.mean(row_losses))
            losses = {r: np.asarray(v, dtype=np.float64) for r, v in diag["loss_vectors"].items()}
            if (any(v.shape != (repetitions,) or not np.isfinite(v).all() or np.any(v < 0) or np.any(v > 1) for v in losses.values())
                    or diag["integer_ticket_bound"] != 20
                    or any(abs(float(v[0]) - reference_losses[r]) > 1e-10 for r, v in losses.items())):
                raise EvaluationError("Invalid complete loss-vector bounds/count or reference")
            saved_result = next((r for r in evaluation["task_results"] if r.get("task_id") == agency), None)
            if saved_result is None:
                raise EvaluationError("Missing mandatory agency result")
            public_loss = saved_result["expected_brier"]["public_only"]
            if type(public_loss) not in (int, float) or abs(public_loss - reference_losses["public_only"]) > 1e-10:
                raise EvaluationError("Public-only constant score changed")
            expected_reference = {"public_only": public_loss, **{r: float(v[0]) for r, v in losses.items()}}
            result, gains = _result(spec, agency, task, item, losses, public_loss, expected_reference)
            if any(diag["paired_gain_vectors"][r] != v.tolist() for r, v in gains.items()) or saved_result != result:
                raise EvaluationError("Mandatory gains, intervals or decisions changed")
            ticket_hash = diag.get("fresh_ticket_sha256")
            if (type(ticket_hash) is not str or len(ticket_hash) != 64
                    or any(c not in "0123456789abcdef" for c in ticket_hash)):
                raise EvaluationError("Invalid complete fresh-ticket identity")
            computed[agency] = {
                "result": result,
                "coefficients": {r: model["routes"][r]["coefficients"] for r in ROUTES},
                "predictions": forecast["routes"], "reference_targets": block["routes"],
                "loss_vectors": diag["loss_vectors"], "paired_gain_vectors": diag["paired_gain_vectors"],
                "integer_ticket_bound": 20, "fresh_ticket_sha256": ticket_hash}
            rebuilt_results.append(result)
    if evaluation.get("status") != aggregate_outcomes([r["status"] for r in rebuilt_results]):
        raise EvaluationError("Overall six-comparison decision changed")
    if bundle != _bundle(spec, cohorts, inputs, computed):
        raise EvaluationError("Result schema, rationale, uncertainty or reproducibility differs from exact reconstruction")
    return True
