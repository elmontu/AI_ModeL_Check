"""Frozen finite public-synthetic usefulness benchmark; no release authority.

Exact integration is conditional on the saved public retained history. It is
neither a population confidence interval nor the manuscript's unclipped,
complete-law affine-loss theorem. No source sampler is invoked in this module.
"""
from __future__ import annotations

from fractions import Fraction
from functools import lru_cache
from itertools import product
from math import lcm
import hashlib
import json
import platform
from typing import Any

from .certificates import RRParameters, ResearchContext, rational_string, verify_certificate
from .cli import BLOCK_SCHEMA

SPEC_SCHEMA = "mra-rr-public-usefulness-specification/1.0"
DATA_SCHEMA = "mra-rr-public-usefulness-dataset/1.0"
EVALUATION_SCHEMA = "mra-rr-public-usefulness-evaluation/1.0"
SEED_SCHEDULE = "mra-public-usefulness-v1:20261012"
MARGIN = Fraction(1, 100)
REPETITIONS = 128
TASK_IDS = ("fresh-coordinate-1", "fresh-coordinate-2")
TRAIN_INDICES = (0, 2, 5, 7)
TEST_INDICES = (1, 3, 4, 6)
OUTCOMES = ((0, 0), (0, 1), (1, 0), (1, 1))
AUTHORITY = {"authorization_effect": "none", "production_execution_qualified": False}
LIMITATIONS = (
    "Fixed public synthetic records and retained history only; no population inference.",
    "Mechanism-level decoding can be biased conditional on the saved retained history.",
    "Clipped ridge predictions do not invoke the manuscript affine expected-loss theorem.",
    "The illustrative margin has no supplied agency-owner justification.",
    "Authoritative cross-system disclosure history and production qualification remain pending.",
)

# Explicit covariates precede generator targets. Fits never derive them from labels.
_FEATURE_TABLE = (
    ("public-synthetic-000", -1, -1), ("public-synthetic-001", -1, 1),
    ("public-synthetic-002", 1, -1), ("public-synthetic-003", 1, 1),
    ("public-synthetic-004", -1, -1), ("public-synthetic-005", -1, 1),
    ("public-synthetic-006", 1, -1), ("public-synthetic-007", 1, 1),
)
_AUXILIARY_TABLE = (
    ("aux-00", -1, -1), ("aux-10", 1, -1),
    ("aux-01", -1, 1), ("aux-11", 1, 1),
)


class UsefulnessError(ValueError):
    """Unbound, corrupt, unsupported or incomplete public benchmark inputs."""


def canonical_bytes(value: Any) -> bytes:
    try:
        return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=True, allow_nan=False) + "\n").encode("utf-8")
    except (ValueError, TypeError, RecursionError) as exc:
        raise UsefulnessError("Invalid usefulness JSON value") from exc


def fingerprint(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def frozen_specification() -> dict[str, Any]:
    """Return a fresh copy of the prospectively frozen specification."""
    return {
        "schema": SPEC_SCHEMA, "specification_id": "public-usefulness-v1-20261012",
        "dataset_id": "public-binary-cube-with-auxiliary-v1", "input_scope": "public_synthetic_only",
        "tasks": [{"task_id": task, "label_coordinate": i + 1, "mandatory": True,
                   "primary_metric": "mean_test_brier"} for i, task in enumerate(TASK_IDS)],
        "partition": {
            "train_record_ids": [_FEATURE_TABLE[i][0] for i in TRAIN_INDICES],
            "test_record_ids": [_FEATURE_TABLE[i][0] for i in TEST_INDICES],
            "auxiliary_record_ids": [row[0] for row in _AUXILIARY_TABLE],
            "selection": "fixed_before_evaluation_no_tuning",
        },
        "learner": {
            "algorithm": "exact_rational_affine_ridge", "features": ["u", "v"], "intercept": True,
            "slope_penalty_lambda": "1/1", "intercept_penalty": "0/1",
            "prediction_clipping": ["0/1", "1/1"], "training_rows_per_route": 4, "tuning": "none",
            "randomized_target_decoder": "T(z)=(z-(1-p))/(2p-1); fixed mechanism-level p",
        },
        "independent_rr": {
            "fresh_joint_ratio": "L/d", "per_pattern_error_masses": "[k,1,1,1]/(k+3); k=L/d",
            "independent_of_retained_response": True, "coordinates_independent": False,
            "realized_block_seed_domain": "independent-realized-v1",
        },
        "acceptance": {
            "metric": "mean_test_brier",
            "gain": "baseline_expected_brier_minus_continuation_expected_brier",
            "margin": "1/100", "comparison_baselines": ["public_only", "independent_rr"],
            "boundary": "lower>=margin passes; upper<margin fails; otherwise inconclusive",
            "all_mandatory_tasks_required": True,
            "margin_justification": "illustrative_frozen_demo_threshold_only",
            "owner_justification": "not_supplied", "operational_usefulness": "not_evaluated",
        },
        "exact_integration": {
            "conditioning": "actual_saved_public_retained_history", "training_block_outcomes": 256,
            "arithmetic": "exact_rational", "predictive_quantile_levels": ["1/40", "39/40"],
            "confidence_interval": False,
        },
        "diagnostics": {
            "repetitions_per_route": REPETITIONS, "seed_schedule": SEED_SCHEDULE,
            "stream": "domain_separated_sha256_integer_tickets", "optional_stopping": False,
            "admission_effect": "none", "persist_replacement_source_blocks": False,
        },
        "limitations": list(LIMITATIONS), **AUTHORITY,
    }


def benchmark_dataset() -> dict[str, Any]:
    """Fixed feature table and separately generated auxiliary public truth."""
    return {
        "schema": DATA_SCHEMA, "dataset_id": "public-binary-cube-with-auxiliary-v1",
        "public_features": [{"record_id": rid, "u": u, "v": v} for rid, u, v in _FEATURE_TABLE],
        "auxiliary_training": [{"record_id": rid, "u": u, "v": v,
                                "targets": [(u + 1) // 2, (v + 1) // 2]}
                               for rid, u, v in _AUXILIARY_TABLE],
        "generator": {
            "ordering": "public_feature_table_precedes_target_assignment",
            "task_1": "X1=(u+1)/2", "task_2": "X2=(v+1)/2",
            "auxiliary_truth_source": "independent_predeclared_synthetic_cohort",
        },
        "evaluation_truth": [{"record_id": rid, "targets": [(u + 1) // 2, (v + 1) // 2]}
                             for rid, u, v in _FEATURE_TABLE],
        "data_classification": "fully_public_synthetic", **AUTHORITY,
    }


def validate_frozen_inputs(specification: Any, dataset: Any) -> None:
    # Encoding distinguishes bool from int and rejects extra/missing fields.
    if canonical_bytes(specification) != canonical_bytes(frozen_specification()):
        raise UsefulnessError("The prospectively frozen evaluation specification differs")
    if canonical_bytes(dataset) != canonical_bytes(benchmark_dataset()):
        raise UsefulnessError("The fixed public synthetic dataset differs")


def _fraction(value: Any) -> Fraction:
    if type(value) is int:
        return Fraction(value)
    if type(value) is Fraction:
        return value
    raise UsefulnessError("Fitting requires exact rational values")


def _feature_rows(rows: Any) -> tuple[tuple[Fraction, Fraction], ...]:
    if not isinstance(rows, (tuple, list)) or len(rows) != 4:
        raise UsefulnessError("The fixed fitting budget is four public feature rows")
    result = []
    for row in rows:
        if not isinstance(row, (tuple, list)) or len(row) != 2:
            raise UsefulnessError("Each fit row contains only two public predictors")
        result.append(tuple(_fraction(value) for value in row))
    return tuple(result)


def _solve(matrix: list[list[Fraction]], rhs: list[Fraction]) -> tuple[Fraction, ...]:
    augmented = [row[:] + [value] for row, value in zip(matrix, rhs)]
    for column in range(3):
        pivot = next((i for i in range(column, 3) if augmented[i][column]), None)
        if pivot is None:
            raise UsefulnessError("Singular fixed ridge system")
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        scale = augmented[column][column]
        augmented[column] = [value / scale for value in augmented[column]]
        for i in range(3):
            if i != column:
                scale = augmented[i][column]
                augmented[i] = [a - scale * b for a, b in zip(augmented[i], augmented[column])]
    return tuple(row[-1] for row in augmented)


def fit_affine_ridge(public_features: Any, fitting_targets: Any) -> tuple[Fraction, ...]:
    """One task; accepts no record IDs, raw truth, test set or retained W."""
    rows = _feature_rows(public_features)
    if not isinstance(fitting_targets, (tuple, list)) or len(fitting_targets) != 4:
        raise UsefulnessError("Exactly four allowed fitting targets are required")
    targets = tuple(_fraction(value) for value in fitting_targets)
    design = [(Fraction(1), *row) for row in rows]
    matrix = [[sum((row[a] * row[b] for row in design), Fraction(0))
               + (Fraction(1) if a == b and a > 0 else 0)
               for b in range(3)] for a in range(3)]
    rhs = [sum((row[a] * target for row, target in zip(design, targets)), Fraction(0))
           for a in range(3)]
    return _solve(matrix, rhs)


def decode_target(bit: Any, accuracy: Any) -> Fraction:
    if type(bit) is not int or bit not in (0, 1):
        raise UsefulnessError("A persisted randomized target must be integer binary")
    p = _fraction(accuracy)
    if not Fraction(1, 2) < p <= 1:
        raise UsefulnessError("The declared finite unbiased decoder requires p>1/2")
    return (Fraction(bit) - (1 - p)) / (2 * p - 1)


def fit_randomized(public_features: Any, randomized_targets: Any,
                   accuracy: Any) -> tuple[tuple[Fraction, ...], ...]:
    """Both tasks from allowed public predictors and randomized bits only."""
    rows = _feature_rows(public_features)
    if not isinstance(randomized_targets, (tuple, list)) or len(randomized_targets) != 4:
        raise UsefulnessError("Exactly four randomized training rows are required")
    targets = []
    for row in randomized_targets:
        if not isinstance(row, (tuple, list)) or len(row) != 2:
            raise UsefulnessError("A randomized row contains the two fixed targets")
        targets.append(tuple(decode_target(bit, accuracy) for bit in row))
    return tuple(fit_affine_ridge(rows, [row[task] for row in targets]) for task in range(2))


def predict(coefficients: Any, public_features: Any) -> Fraction:
    if not isinstance(coefficients, (tuple, list)) or len(coefficients) != 3:
        raise UsefulnessError("A model contains intercept and two slopes")
    if not isinstance(public_features, (tuple, list)) or len(public_features) != 2:
        raise UsefulnessError("A prediction requires two public predictors")
    coefficients = tuple(_fraction(value) for value in coefficients)
    u, v = (_fraction(value) for value in public_features)
    return min(Fraction(1), max(Fraction(0), coefficients[0] + coefficients[1] * u + coefficients[2] * v))


def _test_losses(models: tuple[tuple[Fraction, ...], ...],
                 dataset: dict[str, Any]) -> tuple[Fraction, Fraction]:
    features, truth = dataset["public_features"], dataset["evaluation_truth"]
    return tuple(sum(((predict(models[task], (features[i]["u"], features[i]["v"]))
                       - truth[i]["targets"][task]) ** 2 for i in TEST_INDICES),
                     Fraction(0)) / 4 for task in range(2))


def comparison_outcome(lower: Any, upper: Any, margin: Fraction = MARGIN) -> str:
    """A justified gain interval, including exact endpoint equality."""
    if lower is None or upper is None:
        return "inconclusive"
    lower, upper, margin = _fraction(lower), _fraction(upper), _fraction(margin)
    if lower > upper:
        raise UsefulnessError("A gain interval cannot have reversed endpoints")
    if lower >= margin:
        return "pass"
    if upper < margin:
        return "fail"
    return "inconclusive"


def aggregate_outcomes(outcomes: Any) -> str:
    if not isinstance(outcomes, (tuple, list)) or not outcomes:
        return "not_evaluated"
    if any(outcome not in {"pass", "fail", "inconclusive", "not_evaluated"} for outcome in outcomes):
        raise UsefulnessError("Unsupported evaluation outcome")
    if "fail" in outcomes:
        return "fail"
    if all(outcome == "pass" for outcome in outcomes):
        return "pass"
    if all(outcome == "not_evaluated" for outcome in outcomes):
        return "not_evaluated"
    return "inconclusive"


def independent_error_law(parameters: RRParameters) -> tuple[Fraction, ...]:
    if parameters.r != 2:
        raise UsefulnessError("The fixed public benchmark supports exactly two tasks")
    k = parameters.L / parameters.d
    return (k / (k + 3), Fraction(1) / (k + 3), Fraction(1) / (k + 3), Fraction(1) / (k + 3))



def _validate_records(records: Any) -> list[dict[str, Any]]:
    if type(records) is not list or len(records) != 8:
        raise UsefulnessError("The fixed public source roster requires eight rows")
    for i, record in enumerate(records):
        if (type(record) is not dict or not {"record_id", "labels", "w"} <= set(record)
                or not set(record) <= {"record_id", "labels", "w", "sampled_labels"}
                or record["record_id"] != _FEATURE_TABLE[i][0]):
            raise UsefulnessError("The fixed public source roster differs")
        labels = record["labels"]
        if (type(labels) is not list or len(labels) != 3
                or any(type(bit) is not int or bit not in (0, 1) for bit in labels)
                or labels != [(i >> shift) & 1 for shift in (2, 1, 0)]
                or type(record["w"]) is not int or record["w"] not in (0, 1)):
            raise UsefulnessError("Only the registered public binary cube is supported")
    return records


def _validate_block(block: Any, records: Any, verified: Any) -> dict[str, Any]:
    required = {"schema", "status", "certificate_sha256", "retained_response_sha256",
                "records", "authorization_effect", "production_execution_qualified", "history_reservation"}
    if (type(block) is not dict or set(block) != required
            or block["schema"] != BLOCK_SCHEMA or block["status"] != "completed"
            or block["certificate_sha256"] != verified.digest
            or block["retained_response_sha256"] != verified.context.retained_response_sha256
            or block["authorization_effect"] != "none" or block["production_execution_qualified"] is not False
            or type(block["history_reservation"]) is not str
            or type(block["records"]) is not list or len(block["records"]) != 8):
        raise UsefulnessError("The committed randomized block is unavailable or mismatched")
    for expected, row in zip(records, block["records"]):
        if (type(row) is not dict or set(row) != {"record_id", "labels"}
                or row["record_id"] != expected["record_id"]
                or type(row["labels"]) is not list or len(row["labels"]) != 2
                or any(type(bit) is not int or bit not in (0, 1) for bit in row["labels"])):
            raise UsefulnessError("The committed randomized block roster is invalid")
    return block


def _record_laws(records: list[dict[str, Any]], verified: Any,
                 route: str) -> tuple[tuple[Fraction, ...], ...]:
    laws = []
    error_law = independent_error_law(verified.parameters)
    for index in TRAIN_INDICES:
        record = records[index]
        truth = record["labels"][1:]
        if route == "independent_rr":
            law = tuple(error_law[OUTCOMES.index(tuple(a ^ b for a, b in zip(fresh, truth)))]
                        for fresh in OUTCOMES)
        elif route == "certified_continuation":
            b = record["labels"][0] ^ record["w"]
            row = verified.shells[b]
            pb = verified.parameters.stratum_probabilities[b]
            law = tuple(row[sum(a != x for a, x in zip(fresh, truth))] / pb for fresh in OUTCOMES)
        else:
            raise UsefulnessError("Unsupported randomized route")
        if sum(law, Fraction(0)) != 1 or any(p <= 0 for p in law):
            raise UsefulnessError("The exact training-record law is not normalized")
        laws.append(law)
    return tuple(laws)


def predictive_quantile(distribution: list[tuple[Fraction, Fraction]], level: Fraction) -> Fraction:
    if not 0 < level <= 1:
        raise UsefulnessError("Predictive quantile level must be in (0,1]")
    if sum((mass for _, mass in distribution), Fraction(0)) != 1:
        raise UsefulnessError("A predictive loss distribution must sum exactly to one")
    total = Fraction(0)
    for loss, mass in sorted(distribution):
        total += mass
        if total >= level:
            return loss
    raise UsefulnessError("Incomplete predictive loss distribution")


@lru_cache(maxsize=1024)
def _loss_for_outcome(features: tuple, targets: tuple, accuracy: Fraction,
                      test_cells: tuple) -> tuple[Fraction, Fraction]:
    """Memoize only pure exact calculations keyed by every consumed value.

    Keys contain allowed predictor/target values and the public evaluator cells,
    never artifact paths or a caller's verified flag. Hash validation and
    deterministic artifact reconstruction still run on every store read.
    """
    models = fit_randomized(features, targets, accuracy)
    return tuple(sum(((predict(models[task], row[:2]) - row[task + 2]) ** 2
                      for row in test_cells), Fraction(0)) / len(test_cells)
                 for task in range(2))


def _test_cells(dataset: Any) -> tuple:
    return tuple((dataset["public_features"][i]["u"], dataset["public_features"][i]["v"],
                  *dataset["evaluation_truth"][i]["targets"]) for i in TEST_INDICES)


def _exact_route(laws: tuple[tuple[Fraction, ...], ...], accuracy: Fraction,
                 features: Any, dataset: dict[str, Any]) -> dict[str, Any]:
    features, test_cells = _feature_rows(features), _test_cells(dataset)
    total, expected = Fraction(0), [Fraction(0), Fraction(0)]
    distributions: list[list[tuple[Fraction, Fraction]]] = [[], []]
    outcomes = 0
    for choices in product(range(4), repeat=4):
        mass = Fraction(1)
        for row, choice in zip(laws, choices):
            mass *= row[choice]
        losses = _loss_for_outcome(features, tuple(OUTCOMES[c] for c in choices), accuracy, test_cells)
        total += mass
        for task, loss in enumerate(losses):
            expected[task] += mass * loss
            distributions[task].append((loss, mass))
        outcomes += 1
    if outcomes != 256 or total != 1:
        raise UsefulnessError("Incomplete exact finite-law evaluation")
    return {
        "outcomes": outcomes, "total_probability": total, "expected": tuple(expected),
        "quantiles": tuple({
            "q025": predictive_quantile(distribution, Fraction(1, 40)),
            "q975": predictive_quantile(distribution, Fraction(39, 40)),
        } for distribution in distributions),
    }


class _PublicTickets:
    """Deterministic public diagnostics only; not private-source randomness."""

    def __init__(self, domain: str) -> None:
        self.domain = ("mra-usefulness-public-ticket/1.0\0" + SEED_SCHEDULE + "\0" + domain).encode("utf-8")
        self.counter = 0

    def randbelow(self, bound: int) -> int:
        if type(bound) is not int or not 1 <= bound <= 2 ** 256:
            raise UsefulnessError("Invalid public diagnostic ticket bound")
        if bound == 1:
            return 0
        bits = (bound - 1).bit_length()
        while True:
            digest = hashlib.sha256(self.domain + self.counter.to_bytes(16, "big")).digest()
            self.counter += 1
            ticket = int.from_bytes(digest, "big") & ((1 << bits) - 1)
            if ticket < bound:
                return ticket


def _choose(law: tuple[Fraction, ...], tickets: _PublicTickets) -> tuple[int, int]:
    denominator = lcm(*(p.denominator for p in law))
    weights = [p.numerator * (denominator // p.denominator) for p in law]
    ticket = tickets.randbelow(denominator)
    for outcome, weight in zip(OUTCOMES, weights):
        if ticket < weight:
            return outcome
        ticket -= weight
    raise UsefulnessError("Invalid public diagnostic integer distribution")


def _draw_training(laws: tuple[tuple[Fraction, ...], ...], domain: str) -> list[list[int]]:
    tickets = _PublicTickets(domain)
    return [list(_choose(law, tickets)) for law in laws]


def _diagnostics(laws: Any, accuracy: Fraction, features: Any,
                 dataset: Any, exact: Any, route: str) -> dict[str, Any]:
    features, test_cells = _feature_rows(features), _test_cells(dataset)
    losses = [
        _loss_for_outcome(features,
                          tuple(tuple(row) for row in _draw_training(laws, f"diagnostics/{route}/{i:03}")),
                          accuracy, test_cells)
        for i in range(REPETITIONS)
    ]
    summaries = []
    for task, task_id in enumerate(TASK_IDS):
        values = [pair[task] for pair in losses]
        mean = sum(values, Fraction(0)) / REPETITIONS
        variance = sum(((value - mean) ** 2 for value in values), Fraction(0)) / (REPETITIONS - 1)
        summaries.append({
            "task_id": task_id, "mean_brier": rational_string(mean),
            "sample_variance_brier": rational_string(variance),
            "deviation_from_exact_expected_brier": rational_string(mean - exact["expected"][task]),
        })
    return {
        "route": route, "repetitions": REPETITIONS, "task_summaries": summaries,
        "loss_records": [
            {"repetition": i, "brier": {task: rational_string(loss[j]) for j, task in enumerate(TASK_IDS)}}
            for i, loss in enumerate(losses)
        ],
        "replacement_source_blocks": 0, "admission_effect": "none",
    }


def _model_artifact(models: Any, accuracy: Fraction) -> dict[str, Any]:
    return {
        "decoder_accuracy": rational_string(accuracy),
        "tasks": [{"task_id": task, "coefficients": {
            "intercept": rational_string(models[i][0]),
            "u": rational_string(models[i][1]), "v": rational_string(models[i][2]),
        }} for i, task in enumerate(TASK_IDS)],
    }


def _prediction_artifact(models: Any, dataset: Any) -> list[dict[str, Any]]:
    return [{
        "record_id": dataset["public_features"][index]["record_id"],
        "predictions": {
            task: rational_string(predict(models[j], (
                dataset["public_features"][index]["u"], dataset["public_features"][index]["v"])))
            for j, task in enumerate(TASK_IDS)
        }} for index in TEST_INDICES]


def _base_reproducibility(specification: Any, dataset: Any, records: Any,
                          block: Any, parameters: Any, context: Any,
                          verified: Any, lineage: Any) -> dict[str, Any]:
    return {
        "schema": "mra-rr-public-usefulness-reproducibility/1.0",
        "specification_sha256": fingerprint(specification), "dataset_sha256": fingerprint(dataset),
        "public_roster_sha256": fingerprint(records),
        "committed_block_sha256": None if block is None else fingerprint(block),
        "certificate_sha256": verified.digest, "parameters": parameters.to_dict(),
        "context": context.to_dict(), "algorithm": specification["learner"],
        "partition": specification["partition"], "seed_schedule": SEED_SCHEDULE,
        "software": {"python": platform.python_version(), "implementation": platform.python_implementation(),
                     "kernel_schema": EVALUATION_SCHEMA},
        "lineage": lineage, "operational_usefulness": "not_evaluated", **AUTHORITY,
    }


def _report(evaluation: dict[str, Any]) -> str:
    lines = [
        "Public synthetic usefulness - fixed finite benchmark",
        f"Outcome: {evaluation['status']}",
        "Operational usefulness: not evaluated; no owner-justified agency margin.",
        "Authorization effect: none. Production qualification: false.",
        "Exact means concern mechanism variation on four fixed test records and the saved public history.",
        "Predictive quantiles are not confidence intervals; simulation diagnostics do not decide admission.",
    ]
    if evaluation.get("reason"):
        lines.append("Reason: " + evaluation["reason"])
    for task in evaluation["task_results"]:
        lines.append(f"{task['task_id']}: {task['status']}; margin={task['margin']}")
        expected = task.get("expected_brier", {})
        if expected:
            lines.append("  Expected Brier: " + ", ".join(f"{key}={value}" for key, value in expected.items()))
            for name, comparison in task["comparisons"].items():
                lines.append(f"  Gain versus {name}: {comparison['gain']}; {comparison['status']}")
    lines.extend("Limitation: " + limitation for limitation in LIMITATIONS)
    return "\n".join(lines) + "\n"



def evaluate_bundle(*, specification: Any, dataset: Any, records: Any,
                    block: Any, parameters: Any, context: Any,
                    certificate: Any, lineage: Any) -> dict[str, dict[str, Any] | str]:
    """Build deterministic artifacts from one saved public conditional block.

    The store owns byte snapshots, reservations, provenance and publication.
    This independently replays raw certificate and frozen fixture, never sampling.
    """
    validate_frozen_inputs(specification, dataset)
    if type(parameters) is dict:
        parameters = RRParameters.from_dict(parameters)
    if type(context) is dict:
        context = ResearchContext.from_dict(context)
    if type(parameters) is not RRParameters or type(context) is not ResearchContext:
        raise UsefulnessError("External parameters and context are required")
    if (parameters.r, parameters.d, parameters.L, parameters.tau) not in {
        (2, Fraction(3), Fraction(9), Fraction(2, 3)),
        (2, Fraction(3), Fraction(9), Fraction(3, 4)),
        (2, Fraction(1), Fraction(1), Fraction(1, 2)),
    }:
        raise UsefulnessError("Only the frozen public presets are supported")
    verified = verify_certificate(certificate, expected_parameters=parameters, expected_context=context)
    records = _validate_records(records)
    response_document = {
        "schema": "mra-rr-retained-responses/1.0",
        "records": [{"record_id": row["record_id"], "w": row["w"]} for row in records],
    }
    if fingerprint(response_document) != context.retained_response_sha256:
        raise UsefulnessError("The supplied retained responses differ from the certificate context")
    if type(lineage) is not dict or not lineage:
        raise UsefulnessError("An externally retained nonempty lineage is required")
    canonical_bytes(lineage)
    features = [(dataset["public_features"][i]["u"], dataset["public_features"][i]["v"])
                for i in TRAIN_INDICES]
    auxiliary = dataset["auxiliary_training"]
    public_models = fit_randomized([(row["u"], row["v"]) for row in auxiliary],
                                   [row["targets"] for row in auxiliary], Fraction(1))
    public_loss = _test_losses(public_models, dataset)
    reason = None
    if verified.claim == "infeasible":
        reason = "The verified certificate proves this frozen channel specification infeasible."
    elif verified.marginal_accuracy == Fraction(1, 2):
        reason = "Uniform p=1/2 has no finite unbiased decoder under the frozen specification."
    if reason is not None:
        evaluation = {
            "schema": EVALUATION_SCHEMA, "status": "not_evaluated", "reason": reason,
            "method": "exact_finite_conditional_law",
            "task_results": [{"task_id": task, "label_coordinate": i + 1,
                              "status": "not_evaluated", "margin": "1/100"}
                             for i, task in enumerate(TASK_IDS)],
            "certificate_claim": verified.claim, "operational_usefulness": "not_evaluated",
            "lineage": lineage, **AUTHORITY,
        }
        models = {"public_only": _model_artifact(public_models, Fraction(1)),
                  "independent_rr": None, "certified_continuation": None}
        return {
            "evaluation.json": evaluation,
            "models.json": {"schema": "mra-rr-public-models/1.0", "algorithm": specification["learner"],
                            "models": models, "lineage": lineage, **AUTHORITY},
            "predictions.json": {"schema": "mra-rr-public-predictions/1.0",
                                 "predictions": {"public_only": _prediction_artifact(public_models, dataset)},
                                 "lineage": lineage, **AUTHORITY},
            "independent-block.json": {"schema": "mra-rr-public-independent-block/1.0",
                                       "status": "not_evaluated", "reason": reason,
                                       "records": [], "lineage": lineage, **AUTHORITY},
            "simulation-diagnostics.json": {"schema": "mra-rr-public-simulation-diagnostics/1.0",
                                           "status": "not_evaluated", "routes": {},
                                           "reason": reason, "lineage": lineage, **AUTHORITY},
            "reproducibility.json": _base_reproducibility(specification, dataset, records, block,
                                                         parameters, context, verified, lineage),
            "evaluation.txt": _report(evaluation),
        }
    block = _validate_block(block, records, verified)
    p_continuation = verified.marginal_accuracy
    k = parameters.L / parameters.d
    p_independent = (k + 1) / (k + 3)
    if p_independent < parameters.tau:
        raise UsefulnessError("The independent comparison does not meet the declared floor")
    continuation_laws = _record_laws(records, verified, "certified_continuation")
    independent_laws = _record_laws(records, verified, "independent_rr")
    independent_targets = _draw_training(independent_laws, "independent-realized-v1")
    continuation_targets = [block["records"][i]["labels"] for i in TRAIN_INDICES]
    realized_models = {
        "public_only": public_models,
        "independent_rr": fit_randomized(features, independent_targets, p_independent),
        "certified_continuation": fit_randomized(features, continuation_targets, p_continuation),
    }
    realized_losses = {route: _test_losses(model, dataset) for route, model in realized_models.items()}
    exact = {
        "independent_rr": _exact_route(independent_laws, p_independent, features, dataset),
        "certified_continuation": _exact_route(continuation_laws, p_continuation, features, dataset),
    }
    task_results = []
    for i, task in enumerate(TASK_IDS):
        expected = {"public_only": public_loss[i],
                    **{route: result["expected"][i] for route, result in exact.items()}}
        comparisons = {}
        for baseline in ("public_only", "independent_rr"):
            gain = expected[baseline] - expected["certified_continuation"]
            comparisons[baseline] = {
                "status": comparison_outcome(gain, gain), "gain": rational_string(gain),
                "lower": rational_string(gain), "upper": rational_string(gain), "margin": "1/100",
                "uncertainty": "exact_finite_expectation",
            }
        task_results.append({
            "task_id": task, "label_coordinate": i + 1, "margin": "1/100",
            "status": aggregate_outcomes([entry["status"] for entry in comparisons.values()]),
            "expected_brier": {route: rational_string(value) for route, value in expected.items()},
            "realized_brier": {route: rational_string(losses[i]) for route, losses in realized_losses.items()},
            "comparisons": comparisons,
            "predictive_loss_quantiles": {
                route: {name: rational_string(value) for name, value in result["quantiles"][i].items()}
                for route, result in exact.items()
            },
        })
    evaluation = {
        "schema": EVALUATION_SCHEMA,
        "status": aggregate_outcomes([task["status"] for task in task_results]),
        "method": "exact_finite_conditional_law", "task_results": task_results,
        "certificate_claim": verified.claim,
        "exact_integration": {
            "outcomes_per_randomized_route": 256,
            "total_probability": {route: rational_string(result["total_probability"])
                                  for route, result in exact.items()},
            "monte_carlo_error": "0/1",
        },
        "uncertainty_scope": "Exact predictive mechanism variation on fixed records/history; no confidence interval.",
        "limitations": list(LIMITATIONS), "operational_usefulness": "not_evaluated",
        "lineage": lineage, **AUTHORITY,
    }
    models = {
        route: _model_artifact(model, {"public_only": Fraction(1), "independent_rr": p_independent,
                                      "certified_continuation": p_continuation}[route])
        for route, model in realized_models.items()
    }
    repro = _base_reproducibility(specification, dataset, records, block,
                                 parameters, context, verified, lineage)
    repro["fitting_target_sha256"] = {
        "public_only": fingerprint([row["targets"] for row in auxiliary]),
        "independent_rr": fingerprint(independent_targets),
        "certified_continuation": fingerprint(continuation_targets),
    }
    repro["exact_evaluation"] = evaluation["exact_integration"]
    return {
        "evaluation.json": evaluation,
        "models.json": {"schema": "mra-rr-public-models/1.0", "algorithm": specification["learner"],
                        "models": models, "lineage": lineage, **AUTHORITY},
        "predictions.json": {"schema": "mra-rr-public-predictions/1.0",
                             "predictions": {route: _prediction_artifact(model, dataset)
                                             for route, model in realized_models.items()},
                             "evaluation_truth_scope": "heldout_public_synthetic_only",
                             "lineage": lineage, **AUTHORITY},
        "independent-block.json": {
            "schema": "mra-rr-public-independent-block/1.0", "status": "completed",
            "seed_schedule": SEED_SCHEDULE, "seed_domain": "independent-realized-v1",
            "fresh_joint_ratio": rational_string(k), "coordinate_correctness": rational_string(p_independent),
            "per_pattern_error_masses": [rational_string(p) for p in independent_error_law(parameters)],
            "records": [{"record_id": _FEATURE_TABLE[index][0], "labels": targets}
                        for index, targets in zip(TRAIN_INDICES, independent_targets)],
            "source_conditional_draw": False, "lineage": lineage, **AUTHORITY,
        },
        "simulation-diagnostics.json": {
            "schema": "mra-rr-public-simulation-diagnostics/1.0", "status": "completed",
            "seed_schedule": SEED_SCHEDULE, "admission_effect": "none",
            "uncertainty_scope": "Descriptive fixed-record mechanism simulations; no confidence interval.",
            "routes": {
                "independent_rr": _diagnostics(independent_laws, p_independent, features,
                                                dataset, exact["independent_rr"], "independent_rr"),
                "certified_continuation": _diagnostics(continuation_laws, p_continuation, features,
                                                       dataset, exact["certified_continuation"], "certified_continuation"),
            },
            "lineage": lineage, **AUTHORITY,
        },
        "reproducibility.json": repro, "evaluation.txt": _report(evaluation),
    }

