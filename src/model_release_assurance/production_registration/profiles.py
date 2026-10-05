"""Eight pinned local public fixture profiles for prospective registration.

Pins identify the PRD-11 local representations, not authenticated upstream
provenance, licensing, population privacy or complete disclosure history.
Research sources remain read-only and use the existing bounded NPZ loader.
"""
from __future__ import annotations

import copy
import hashlib
import json

import numpy as np

from ..production_adapters.contracts import canonical_bytes
from ..production_adapters.datasets import DatasetError, DatasetUnavailable, load_research_dataset

PROFILE_IDS = ("acs", "bts", "hmda", "tlc", "sklearn-breast-cancer", "sklearn-wine",
               "sklearn-digits", "sklearn-diabetes")
SELECTION_SEED = 20261001
SKLEARN_VERSION = "1.6.1"
# Observed in .local/verification/prd11-adapters-20261001/research-benchmark:
# source hashes: cases/<id>/result.json; manifest hashes: observations/<id>.json.
# Constants keep runtime registration independent of mutable historical receipts.
_PINS = {
    "acs": ("bee2b2bf425028427cc7fb52287f95fb0279bdaf412554a020b8d7af4e3a62e5",
            "5fef5acbd49ff533d521ba7f1889a8b7a46d81103e4fff68828f11e6305b17a1"),
    "bts": ("9f3fc956e2be28919681e211b457676680fdde5b46b5ea72fd6afd341bc6ff7f",
            "2fc482249bc4f98ab8e9aede2c2bedddd3d5698b4ef3bea5faa795428351535b"),
    "hmda": ("01ac8eb0afbe05a087f9331fbb7d33362eef785c8d938242dad65f66af0d8555",
             "21fd76971a566c1d6a99b144d258c2ee26d21094b5bd1ded93a40457315b0a85"),
    "tlc": ("d3313a731d21646706b102fee97177f292c6845783633fad9b5cc69f1896463a",
            "f1a78f647d68bd479be2d799bcae34cb4d59d83ed695f2883d13761c50749d93"),
    "sklearn-breast-cancer": ("66a43647283144ab6cfabf78959cfa0e6ea7102f6b2d025537de77386270842c", None),
    "sklearn-wine": ("5b1c9f5f6fde51958ad523cb464c62486df4f55b89c91aa344767174ba1eb6e9", None),
    "sklearn-digits": ("87fc2c66e80d234871b6583b8e428f65fac66ba625a20f2ef2709204325fda8c", None),
    "sklearn-diabetes": ("cf7c366fa15dbfca5eda6f73aecf9398263ff426c45f429a2090751908f4d990", None),
}


def _digest(value):
    # The PRD-11 benchmark used this same canonical JSON representation. This
    # intentionally allows full bounded fixture arrays, unlike evidence's 64KiB
    # metadata encoder. Source and selected-matrix hashes have different scopes.
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def profile_descriptor(profile_id):
    """Return an owned exact descriptor; catalog-only profiles are unavailable."""
    if type(profile_id) is not str or profile_id not in PROFILE_IDS:
        raise DatasetError("Unknown registered public fixture profile")
    source, manifest = _PINS[profile_id]
    return {"id": profile_id, "task": "regression" if profile_id == "sklearn-diabetes" else "classification",
            "source_kind": "research_prepared" if manifest is not None else "bundled",
            "expected_source_sha256": source, "expected_manifest_sha256": manifest}


def _bundled(profile_id, max_rows):
    import sklearn
    from sklearn.datasets import load_breast_cancer, load_wine, load_digits, load_diabetes
    if sklearn.__version__ != SKLEARN_VERSION:
        raise DatasetError("Bundled fixture runtime differs from its pinned representation")
    loaders = {"sklearn-breast-cancer": load_breast_cancer, "sklearn-wine": load_wine,
               "sklearn-digits": load_digits, "sklearn-diabetes": load_diabetes}
    # All loaders are fixed bundled-data functions; none fetch data or import a
    # model named by a caller. Diabetes preserves the historical scaled=True.
    data = loaders[profile_id]()
    x, y = np.array(data.data, dtype=np.float64, copy=True), np.array(data.target, copy=True)
    names = [str(name) for name in data.feature_names]
    if (x.ndim != 2 or y.ndim != 1 or len(x) != len(y) or not 128 <= len(y) <= 4096
            or not 1 <= x.shape[1] <= 128 or len(names) != x.shape[1]
            or y.dtype.kind not in "iuf" or not np.isfinite(x).all() or not np.isfinite(y).all()):
        raise DatasetError("Bundled fixture numeric shape rejected")
    full_digest = _digest({"loader": profile_id, "sklearn": sklearn.__version__,
                           "x": x.tolist(), "y": y.tolist(), "feature_names": names})
    if full_digest != _PINS[profile_id][0]:
        raise DatasetError("Bundled fixture differs from its pinned public representation")
    indices = np.random.default_rng(SELECTION_SEED).permutation(len(y))[:max_rows]
    x, y = x[indices], y[indices]
    return {"x": x, "y": y, "feature_names": names, "dataset_id": profile_id,
            "source_sha256": full_digest,
            "metadata": {"schema": "bundled-dataset-observation/v1", "source": "scikit-learn bundled fixture",
                         "loader": profile_id, "sklearn_version": sklearn.__version__,
                         "available_rows": len(data.target), "selected_rows": len(y),
                         "selection": "fixed20261001 permutation before label inspection",
                         "selection_indices_sha256": _digest(indices.tolist()), "full_fixture_sha256": full_digest,
                         "selected_matrix_sha256": _digest({"x": x.tolist(), "y": y.tolist()}),
                         "features": len(names), "private_data": False,
                         "historically_untouched_data_claim": False, "production_license_approval": False}}


def load_profile(profile_id, *, data_root=None, max_rows=4096):
    """Load only one pinned profile, with owned arrays and explicit lineage.

    An explicit ordinary absolute source root is required for research profiles.
    Bundled profiles never access data_root. No arbitrary model, private intake,
    source URL or caller-selected loader is accepted. A changed source/manifest
    is rejected even when its own local receipt has been consistently restamped.
    """
    descriptor = profile_descriptor(profile_id)
    if type(max_rows) is not int or not 128 <= max_rows <= 4096:
        raise DatasetError("Registered sample bound must be from 128 to 4096 rows")
    try:
        if descriptor["source_kind"] == "research_prepared":
            if data_root is None:
                raise DatasetUnavailable("An explicit research source root is required")
            data = load_research_dataset(data_root, profile_id, max_rows=max_rows)
            if (data["source_sha256"] != descriptor["expected_source_sha256"]
                    or data["metadata"]["manifest_sha256"] != descriptor["expected_manifest_sha256"]):
                raise DatasetError("Research source or manifest differs from its pinned public representation")
            upstream = "Historical prepared covariates; upstream transformations are not independently reconstructed."
        else:
            data = _bundled(profile_id, max_rows)
            upstream = ("Diabetes bundled scaled=True uses full-cohort centering and scaling before this benchmark split."
                        if profile_id == "sklearn-diabetes" else
                        "Fixed scikit-learn bundled representation; upstream source preparation is not independently audited.")
        metadata = copy.deepcopy(data["metadata"])
        metadata.update({"profile_id": profile_id, "profile_source_kind": descriptor["source_kind"],
            "local_public_fixture_pin_verified": True, "pin_observation": "prd11-adapters-20261001",
            "authenticated_upstream_provenance": False, "current_license_approval": False,
            "historical_training_data_reused": True, "fresh_audit_evidence": False,
            "person_level_disjointness_established": False, "disclosure_history_complete": False,
            "private_data_admitted": False, "authorization_eligible": False, "production_authorized": False,
            "model_delivery": False, "upstream_preprocessing": upstream})
        encoded = canonical_bytes(metadata)
        if len(encoded) > 65536:
            raise DatasetError("Registered profile metadata exceeds its bound")
        # No arrays or nested metadata are shared with loader results or another
        # caller. Read-only flags catch accidental downstream preprocessing.
        x, y = np.array(data["x"], copy=True, order="C"), np.array(data["y"], copy=True, order="C")
        x.setflags(write=False)
        y.setflags(write=False)
        return {"x": x, "y": y, "feature_names": list(data["feature_names"]),
                "dataset_id": data["dataset_id"], "source_sha256": data["source_sha256"],
                "metadata": json.loads(encoded), "profile_id": profile_id, "task": descriptor["task"]}
    except (DatasetError, DatasetUnavailable):
        raise
    except (OSError, ValueError, TypeError, KeyError, OverflowError, UnicodeError, RecursionError):
        raise DatasetError("Registered public fixture validation failed") from None
