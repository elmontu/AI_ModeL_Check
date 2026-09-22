"""Pure planning for the fixed two-stage DP export protocol.

A plan consumes an already validated public ``ExportStore.status()`` snapshot.
It checks that snapshot defensively but neither reads private state nor proves
its provenance. A ready plan is not a release authorization: the producer must
recheck live history and construct/commit the exact artifact transactionally.
"""

from __future__ import annotations

import math
import re

from .store import ExportDenied


SCOPE = "fixed-synthetic-fixture-only"
ROUTES = frozenset({"first", "reuse", "retained-state", "independent", "central-count"})
SECOND_ROUTES = ROUTES - {"first", "reuse"}
_HISTORY_KEYS = {"revision", "privacy_ratio", "history_ratio", "delta", "candidates", "releases",
                 "scope", "agency_deployed", "mechanism_source_sha256"}
_CANDIDATE_KEYS = {"request_id", "stage", "route", "base_revision", "status", "stale"}
_RELEASE_KEYS = {"request_id", "release_id", "stage", "route", "revision", "artifact_sha256",
                 "parent_artifact_sha256", "privacy_ratio", "history_ratio", "delta", "status", "scope", "revoked"}


def _valid(condition: bool) -> None:
    if not condition:
        raise ExportDenied("invalid_history", "Expected an internally consistent public export-status snapshot; private fields and arbitrary history claims are unsupported.")


def _integer(value: object, choices: tuple[int, ...]) -> bool:
    return type(value) is int and value in choices


def _token(value: object, expression: str) -> bool:
    return type(value) is str and re.fullmatch(expression, value) is not None


def _validate_public_history(history: dict) -> None:
    # Exact allowlists keep a planner/tool from echoing raw state or staged
    # artifact hashes accidentally added to a request. No supplied field is
    # interpreted as a cryptographic or mathematical privacy attestation.
    _valid(type(history) is dict and set(history) == _HISTORY_KEYS)
    _valid(history["scope"] == SCOPE and history["agency_deployed"] is False
           and _integer(history["delta"], (0,))
           and _integer(history["revision"], (0, 1, 2, 3, 4))
           and _token(history["mechanism_source_sha256"], r"[0-9a-f]{64}"))
    candidates, releases = history["candidates"], history["releases"]
    _valid(type(candidates) is list and len(candidates) <= 128
           and type(releases) is list and len(releases) <= 2)
    _valid(all(type(item) is dict and set(item) == _CANDIDATE_KEYS for item in candidates))
    _valid(all(type(item) is dict and set(item) == _RELEASE_KEYS for item in releases))
    _valid(all(type(item["revoked"]) is bool for item in releases))
    ratio = (1, 2, 4)[len(releases)]
    _valid(_integer(history["privacy_ratio"], (ratio,)) and _integer(history["history_ratio"], (ratio,))
           and history["revision"] == len(releases) + sum(item["revoked"] for item in releases))
    released = {}
    release_ids = set()
    for index, item in enumerate(releases, start=1):
        _valid(_token(item["request_id"], r"[A-Za-z0-9_-]{1,128}")
               and _token(item["release_id"], r"[0-9a-f]{32}")
               and item["request_id"] not in released and item["release_id"] not in release_ids
               and _integer(item["stage"], (index,))
               and ((index == 1 and item["route"] == "first")
                    or (index == 2 and type(item["route"]) is str and item["route"] in SECOND_ROUTES))
               and _integer(item["privacy_ratio"], (2 ** index,))
               and _integer(item["history_ratio"], (2 ** index,))
               and _integer(item["delta"], (0,)) and item["status"] == "committed" and item["scope"] == SCOPE
               and _token(item["artifact_sha256"], r"[0-9a-f]{64}"))
        _valid((index == 1 and item["parent_artifact_sha256"] is None and _integer(item["revision"], (1,)))
               or (index == 2 and item["parent_artifact_sha256"] == releases[0]["artifact_sha256"]
                   and _integer(item["revision"], (2, 3))
                   and (item["revision"] != 3 or releases[0]["revoked"])))
        released[item["request_id"]] = item
        release_ids.add(item["release_id"])
    seen = set()
    committed = set()
    for item in candidates:
        _valid(_token(item["request_id"], r"[A-Za-z0-9_-]{1,128}") and item["request_id"] not in seen
               and type(item["stale"]) is bool and type(item["status"]) is str
               and item["status"] in {"prepared", "committed"}
               and _integer(item["stage"], (1, 2)))
        _valid((item["stage"] == 1 and item["route"] == "first" and _integer(item["base_revision"], (0,)))
               or (item["stage"] == 2 and type(item["route"]) is str and item["route"] in SECOND_ROUTES
                   and bool(releases) and _integer(item["base_revision"], (1, 2))
                   and (item["base_revision"] != 2 or releases[0]["revoked"])))
        _valid(item["base_revision"] <= history["revision"])
        if item["status"] == "committed":
            receipt = released.get(item["request_id"])
            _valid(receipt is not None and not item["stale"]
                   and (item["stage"], item["route"], item["base_revision"] + 1)
                   == (receipt["stage"], receipt["route"], receipt["revision"]))
            committed.add(item["request_id"])
        else:
            _valid(item["stale"] == (item["base_revision"] != history["revision"]))
        seen.add(item["request_id"])
    _valid(committed == set(released))


def plan_export(history: dict, route: str) -> dict:
    """Describe one supported next action without state access or execution.

    ``ready`` means only that the snapshot's stage permits the route. It does
    not assert retained state availability, current authority, model utility,
    or correctness of a caller-supplied snapshot. Blocked plans never propose
    a lower history ratio. Reuse means retrieving identical committed bytes,
    not running a new training job or drawing fresh mechanism randomness.
    """
    if not _token(route, r"[a-z][a-z0-9-]{0,63}"):
        raise ExportDenied("invalid_request", "Route must be a short public construction identifier.")
    _validate_public_history(history)
    count = len(history["releases"])
    current_ratio = history["history_ratio"]
    details = {
        "first": (
            "initial-protected-training", "randomized-response-then-postprocessing",
            "The fixed synthetic first-bit records are perturbed; the coordinator initializes and retains the fixed two-period fixture state.",
            "The first protected channel is log(2)-DP; fitting the model from it is post-processing.",
        ),
        "reuse": (
            "protected-output-reuse", "identical-artifact-postprocessing",
            "No new raw records or mechanism randomness; retrieve the already committed artifact after live history and revocation checks.",
            "Delivering identical previously committed bytes adds no new privacy cost. Earlier exposure remains counted; this route does not retrain.",
        ),
        "retained-state": (
            "jointly-certified-extension", "complete-history-joint-certificate",
            "New second-bit values and the retained first-response flip E=X xor A; E together with A reconstructs X. The current coordinator retains and validates full first-stage state.",
            "The joint first-and-second channel has ratio 4. This complete-history certificate does not assign an independent log(2) privacy cost to the retained-state step.",
        ),
        "independent": (
            "independent-protected-training", "sequential-composition",
            "Second-bit values for fresh independent randomized response. The current coordinator also retains and validates first-stage state; reduced-access isolation is not implemented.",
            "First-stage log(2)-DP plus independent second-stage log(2)-DP gives the sufficient complete-history bound log(4).",
        ),
        "central-count": (
            "direct-private-training", "sensitivity-one-counts-and-sequential-composition",
            "Trusted access to second-bit counts within fixed public groups. The current coordinator also retains and validates first-stage state.",
            "One citizen changes one group's count by at most one. Ratio-2 geometric count noise and model post-processing give log(2)-DP for this stage; composition gives log(4) for history. This is a fixed sufficient-statistic trainer, not a general DP-SGD adapter.",
        ),
    }
    supported = route in ROUTES
    block_reason = None
    block_message = None
    if not supported:
        block_reason, block_message = "unsupported_route", "This bounded protocol does not implement that construction."
    elif route == "first" and count:
        block_reason, block_message = "history_not_empty", "Earlier disclosures remain counted; a first-stage restart is not permitted."
    elif route == "reuse" and not count:
        block_reason, block_message = "no_committed_release", "Reuse requires an existing committed artifact."
    elif route == "reuse" and history["releases"][-1]["revoked"]:
        block_reason, block_message = "latest_release_revoked", "The latest artifact is revoked; this route does not fall back to an earlier release."
    elif route in SECOND_ROUTES and count == 0:
        block_reason, block_message = "first_release_required", "Commit the first protected model before extending its history."
    elif route in SECOND_ROUTES and count == 2:
        block_reason, block_message = "history_complete", "The two-stage privacy certificate is exhausted; revocation does not permit another branch or reset."
    ready = supported and block_reason is None
    proposed_ratio = (current_ratio if route == "reuse" else 2 if route == "first" else 4) if ready else None
    family, accounting, access, interpretation = details.get(route, ("unsupported", "unsupported", "unsupported", "No privacy claim is available."))
    return {
        "schema": "mra-export-poc-plan-v1", "scope": SCOPE, "route": route,
        "supported": supported, "ready": ready, "block_reason": block_reason, "block_message": block_message,
        "history_revision": history["revision"], "current_history_ratio": current_ratio,
        "current_epsilon": math.log(current_ratio), "proposed_history_ratio": proposed_ratio,
        "proposed_epsilon": math.log(proposed_ratio) if proposed_ratio is not None else None,
        "delta": 0, "stage": 1 if route == "first" else 2 if route in SECOND_ROUTES else None,
        "protocol_family": family, "accounting_method": accounting,
        "required_private_access": access, "privacy_cost_interpretation": interpretation,
        "model_bytes_change": supported and route != "reuse",
        "model_bytes_change_meaning": "Whether the route constructs a new artifact, not a guarantee that its bytes differ; reuse returns identical bytes.",
        "reuse_release_id": history["releases"][-1]["release_id"] if ready and route == "reuse" else None,
        "can_authorize": False,
        "limits": "Snapshot-only plan for a fixed synthetic fixture. Live commit/delivery checks remain mandatory. No general accountant, new dataset, utility certification, or privacy-budget reset is supported.",
    }
