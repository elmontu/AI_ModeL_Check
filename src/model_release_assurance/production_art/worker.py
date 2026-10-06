"""Trusted ART child entry point with fixed loss-oracle learner parameters.

ART is imported only after the parent-declared runtime and source bindings are
verified. The oracle refuses target fitting, prediction and feature queries.
All inputs are bounded JSON numbers; no pickles, caller code or signing keys.
"""
from __future__ import annotations
import hashlib
from pathlib import Path
import sys
import warnings
from . import protocol
from .runtime import ATTACK_PARAMETERS, LOCKED_VERSIONS, ArtRuntimeUnavailable, probe_runtime
from .execution import MAX_INPUT, MAX_OUTPUT, source_snapshot
from ..production_adapters import native
from ..production_adapters.contracts import canonical_bytes, strict_json

WORKER_FLAGS = {"fixture_only": True, "can_clear": False, "assessment_eligible": False,
                "authorization_eligible": False, "production_authorized": False}


def validate_request(request):
    if (type(request) is not dict or set(request) != {"schema", "prepared", "versions", "source_sha256", "lock_sha256"}
            or request["schema"] != "mra-art-worker-request/v1"):
        raise ValueError("ART worker request rejected")
    prepared = protocol.validate_input(request["prepared"])
    if canonical_bytes(request["versions"]) != canonical_bytes(LOCKED_VERSIONS):
        raise ValueError("ART runtime version roster rejected")
    for key in ("source_sha256", "lock_sha256"):
        value = request[key]
        if type(value) is not str or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            raise ValueError("ART digest rejected")
    return prepared


def _create_attack():
    # Optional imports belong here, after run_request verifies the exact runtime.
    import numpy as np
    from art.attacks.inference.membership_inference import MembershipInferenceBlackBox
    from art.estimators.estimator import BaseEstimator
    from art.estimators.regression import RegressorMixin
    from sklearn.linear_model import LogisticRegression

    class RetainedGroupLossRegressor(BaseEstimator, RegressorMixin):
        """A precomputed loss oracle, deliberately not a fitted target regressor."""
        def __init__(self):
            super().__init__(model=None, clip_values=None, preprocessing=None)

        @property
        def input_shape(self):
            return (1,)

        def fit(self, x, y, **kwargs):
            raise NotImplementedError("Retained loss oracle does not fit targets")

        def predict(self, x, **kwargs):
            raise NotImplementedError("Retained loss oracle has no prediction endpoint")

        def compute_loss(self, x, y, **kwargs):
            raise NotImplementedError("Retained loss oracle has no feature query endpoint")

        def compute_loss_from_predictions(self, pred, y, **kwargs):
            values = np.asarray(pred)
            labels = np.asarray(y)
            if (values.dtype.kind not in "fiu" or values.ndim != 2 or values.shape[1] != 1
                    or not 1 <= len(values) <= protocol.MAX_GROUPS or labels.shape != (len(values),)
                    or labels.dtype.kind not in "fiu" or not np.isfinite(labels).all() or np.any(labels != 0)
                    or not np.isfinite(values).all() or np.any(values < 0) or np.any(values > protocol.MAX_LOSS)):
                raise ValueError("Retained loss oracle input rejected")
            cast = values.astype(np.float32)
            if not np.isfinite(cast).all():
                raise ValueError("ART loss float32 overflow")
            return values[:, 0].copy()

    attack = MembershipInferenceBlackBox(RetainedGroupLossRegressor(), input_type="loss",
                                        attack_model_type="lr", scaler_type="standard")
    if type(attack.attack_model) is not LogisticRegression or attack.default_model is not True:
        raise ValueError("ART learner differs from the fixed default")
    params = {key: ATTACK_PARAMETERS[key] for key in ("C", "solver", "max_iter", "random_state")}
    attack.attack_model.set_params(**params)
    if any(attack.attack_model.get_params()[key] != value for key, value in params.items()):
        raise ValueError("ART learner parameter drift")
    return attack


def _run_case(prepared, name):
    import numpy as np
    from sklearn.exceptions import ConvergenceWarning
    labels = prepared["membership_labels"]
    losses = protocol.loss_features_float32(prepared["cases"][name]["loss_values"])
    values = np.asarray(losses, dtype=np.float64).reshape(-1, 1)
    result = []
    for split in protocol.frozen_splits(prepared):
        members = [index for index in split["train_indices"] if labels[index] == 1]
        nonmembers = [index for index in split["train_indices"] if labels[index] == 0]
        attack = _create_attack()
        with warnings.catch_warnings():
            warnings.simplefilter("error", ConvergenceWarning)
            attack.fit(pred=values[members], y=np.zeros(len(members), dtype=np.float32),
                       test_pred=values[nonmembers], test_y=np.zeros(len(nonmembers), dtype=np.float32))
            test = split["test_indices"]
            probabilities = np.asarray(attack.infer(None, y=np.zeros(len(test), dtype=np.float32),
                                                    pred=values[test], probabilities=True))
        model, scaler = attack.attack_model, attack.scaler
        if (probabilities.shape != (len(test), 1) or not np.isfinite(probabilities).all()
                or np.any(probabilities < 0) or np.any(probabilities > 1)
                or not np.array_equal(model.classes_, np.asarray([0, 1]))
                or model.coef_.shape != (1, 2) or model.intercept_.shape != (1,)
                or scaler.mean_.shape != (2,) or scaler.scale_.shape != (2,)
                or model.n_iter_.shape != (1,) or not 0 <= model.n_iter_[0] < 500):
            raise ValueError("ART learner output rejected")
        learned = {"classes": [0, 1], "coef": model.coef_[0].tolist(), "intercept": float(model.intercept_[0]),
            "scaler_mean": scaler.mean_.tolist(), "scaler_scale": scaler.scale_.tolist(), "n_iter": int(model.n_iter_[0])}
        result.append({**split, "member_probabilities": probabilities[:, 0].tolist(),
                       "learned": learned, "loss_features_float32": list(losses)})
    protocol.compare_repetitions(prepared, name, result)
    return result


def run_request(request):
    prepared = validate_request(request)
    request = protocol.owned(request)
    # Own all bindings before caller-visible or external work.
    versions = dict(request["versions"])
    source = source_snapshot()
    source_digest = hashlib.sha256(canonical_bytes(source)).hexdigest()
    if source_digest != request["source_sha256"]:
        raise ValueError("ART implementation source changed")
    before = probe_runtime(versions)
    cases = {name: _run_case(prepared, name) for name in protocol.CASES}
    if probe_runtime(versions) != before or source_snapshot() != source:
        raise ValueError("ART execution binding changed")
    return {"schema": "mra-art-worker-output/v1", "status": "completed",
        "prepared_sha256": hashlib.sha256(canonical_bytes(prepared)).hexdigest(), "runtime": before,
        "versions": versions, "source_sha256": source_digest, "lock_sha256": request["lock_sha256"],
        "cases": cases, **WORKER_FLAGS}


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 3:
        return 2
    path, expected, destination = args
    output = Path(destination)
    try:
        native._real_directory(output)
        raw = native._read(Path(path), MAX_INPUT)
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError("ART worker input changed")
        request = strict_json(raw, maximum=MAX_INPUT)
        result = run_request(request)
        encoded = canonical_bytes(result)
        if len(encoded) > MAX_OUTPUT:
            raise ValueError("ART worker output too large")
        with (output / "worker.json").open("xb") as stream:
            stream.write(encoded + b"\n")
        return 0
    except Exception as error:
        unavailable = isinstance(error, (ArtRuntimeUnavailable, ModuleNotFoundError))
        try:
            native._real_directory(output)
            with (output / "failure.json").open("xb") as stream:
                stream.write(canonical_bytes({"status": "unavailable" if unavailable else "failed",
                    "error_type": type(error).__name__, **WORKER_FLAGS}) + b"\n")
        except Exception:
            return 1
        return 3 if unavailable else 1


if __name__ == "__main__":
    raise SystemExit(main())
