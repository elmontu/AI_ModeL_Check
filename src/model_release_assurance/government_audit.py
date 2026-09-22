"""Local, append-only review notes for agency model-release evidence.

These controls translate the paper's assumptions into review questions. Matching
bytes establish an inventory binding, never scientific adequacy or authorization.
"""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from . import workflow


PROTOCOL_VERSION = "government-audit-controls/2026-09-22"
FORMAT_VERSION = "government-audit/1"
STATUSES = ("evidence_recorded", "gap", "not_applicable")


def _control(identifier, title, motivation, question, examples):
    return {"id": identifier, "title": title, "motivation": motivation,
            "review_question": question, "evidence_examples": examples}


CONTROLS = (
    _control("purpose-omission-utility", "Purpose, omission and utility",
             "Avoid using protected attributes when omitting them meets the actual task need.",
             "Is the intended task specified, and is protected-input use justified against an omission baseline with task-specific utility and uncertainty?",
             ["agency-scope", "utility-report", "evaluation-plan"]),
    _control("privacy-adjacency", "Protected units and adjacency",
             "The paper's fixed-roster attribute guarantee does not automatically protect participation, whole records or a citizen's history.",
             "Which people, records, attributes, versions and neighboring changes are protected, and which covariates, labels and memberships remain public or outside the promise?",
             ["agency-scope", "evaluation-plan"]),
    _control("recipient-package-history", "Complete recipient package and history",
             "Recipients can retain weights, preprocessing, metadata, linked scores and earlier releases together.",
             "Does the declared view include the complete delivered package, access route, prior releases, recipient background and unrestricted local queries for exported weights?",
             ["agency-scope", "lineage", "request"]),
    _control("training-scoring-footprints", "Training and scoring dependencies",
             "Counting models or training rosters alone can omit scoring exposure and shared protected inputs.",
             "Are all protected channel/unit dependencies used in preprocessing, training and scoring enumerated with stable unit identities and justified mechanism costs?",
             ["lineage", "evaluation-plan", "request"]),
    _control("cached-reuse-versions", "Identical cache reuse and attribute versions",
             "Free reuse requires the identical sanitized value; fresh noise or changed raw values need a new justified accounting contract.",
             "Do cache identities bind the same sanitized values and attribute version, with new draws and changed raw values distinguished from exact reuse?",
             ["lineage", "security-report", "evaluation-plan"]),
    _control("protected-information-flow", "Protected information flow",
             "Ledger consistency alone does not prove that the entire package is post-processing of charged inputs.",
             "Do training, scoring, preprocessing, metadata, evaluation disclosures, selection and refusal avoid uncharged protected values and upstream private coins, including adaptive decisions?",
             ["security-report", "evaluation-plan", "independent-review"]),
    _control("cumulative-accounting", "Cumulative, nonrefundable accounting",
             "A recipient's retained history survives retraining, renaming, expiry and revocation.",
             "Does the cumulative ledger charge the union of training/scoring channel-unit pairs against the declared cap, preserve prior disclosures and prevent refunds, replay and rollback?",
             ["request", "security-report", "independent-review"]),
    _control("model-lineage", "Fine-tuning, merging and ensemble lineage",
             "A derived model can add protected inputs or expose several parent releases jointly.",
             "Are base models, adapters, fine-tunes, merged components, ensembles and distillation teachers bound to recipes, versions, overlap and previously disclosed artifacts?",
             ["lineage", "candidate", "evaluation-plan"]),
    _control("joint-attacks-uncertainty", "Joint attacks and uncertainty",
             "Failed attacks are lower-bound evidence and do not certify privacy; recipients may combine artifacts and background information.",
             "Are calibrated joint membership, attribute and extraction attacks, controls, query budgets, held-out evaluation and uncertainty recorded for the declared recipient view, with unsupported tests explicit?",
             ["evaluation-plan", "utility-report", "independent-review", "request"]),
    _control("exact-byte-delivery", "Exact-byte commitment and delivery",
             "A review applies to its actual package bytes and current prerequisites, not merely a model name.",
             "Are candidate, evidence, dependency and authority bindings rechecked at commit and delivery, with atomic accounting, stale-context rejection and retained receipts?",
             ["candidate", "security-report", "independent-review"]),
    _control("expiry-revocation-recovery", "Expiry, revocation and recovery",
             "Stopping future downloads cannot recall prior copies or undo privacy expenditure.",
             "Have expiry, revocation, crash/retry, concurrent requests and rollback recovery been tested, while preserving earlier disclosure and distinguishing authorization from acknowledged delivery?",
             ["security-report", "independent-review"]),
    _control("agency-decision-risks", "Agency decision and remaining risks",
             "Technical evidence and local review notes do not provide institutional authority or demonstrate agency deployment readiness.",
             "Are the accountable agency decision, independent review, unresolved risks, justified exceptions and required deployment controls documented outside this educational console?",
             ["agency-scope", "independent-review", "security-report"]),
)
CONTROL_IDS = frozenset(control["id"] for control in CONTROLS)


class ReviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    control_id: str = Field(min_length=1, max_length=80)
    status: Literal["evidence_recorded", "gap", "not_applicable"]
    rationale: str = Field(min_length=20, max_length=2000)
    evidence_slots: list[str] = Field(default_factory=list, max_length=16)
    expected_context_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_review(self):
        if self.control_id not in CONTROL_IDS:
            raise ValueError("unknown government audit control")
        if any(not slot or len(slot) > 200 for slot in self.evidence_slots):
            raise ValueError("invalid evidence slot name")
        if len(set(self.evidence_slots)) != len(self.evidence_slots):
            raise ValueError("duplicate evidence slots are not allowed")
        if self.status == "evidence_recorded" and not self.evidence_slots:
            raise ValueError("evidence_recorded requires a bound evidence slot")
        return self


def catalog() -> dict:
    return {"format_version": FORMAT_VERSION, "protocol_version": PROTOCOL_VERSION,
            "authorization_eligible": False, "scientific_adequacy_verified": False,
            "intro": "Record agency review questions against the current case and bound evidence. These educational notes never authorize release.",
            "limitations": ["Matching bytes do not verify evidence quality, privacy assumptions or agency approval.",
                            "Not applicable records a reviewer rationale, not a scientific pass.",
                            "Reviews become stale when the case configuration or cited evidence changes.",
                            "Evidence files must be readable and at most 10 MiB each; larger packages need a bound manifest.",
                            "The local database has no authenticated reviewer identities or hostile-administrator protection."],
            "statuses": list(STATUSES), "controls": deepcopy(list(CONTROLS))}


def context_sha256(project: workflow.Project) -> str:
    payload = {"protocol_version": PROTOCOL_VERSION, "project": project.model_dump()}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def bindings(project: workflow.Project) -> dict[str, workflow.FileBinding]:
    return {slot: ref for slot, ref in {**project.files, **project.supporting_files}.items() if ref is not None}


def checked_bindings(root: Path, project: workflow.Project, slots: list[str]) -> dict:
    """Resolve only project-bound slot names; clients cannot supply file paths."""
    available = bindings(project)
    result = {}
    for slot in slots:
        if slot not in available:
            raise ValueError("evidence slot is unknown or unbound: " + slot)
        ref = available[slot]
        try:
            workflow.verified_bytes(root, ref)
        except (OSError, ValueError) as exc:
            raise ValueError("bound evidence changed or is unreadable: " + slot) from exc
        result[slot] = ref.model_dump()
    return result


def report(root: Path, case_id: str, project: workflow.Project, records: list[dict]) -> dict:
    """Revalidate current cited bytes on every read without rewriting history."""
    result = catalog()
    context = context_sha256(project)
    current = bindings(project)
    inventory = []
    valid = {}
    for slot, ref in sorted(current.items()):
        try:
            workflow.verified_bytes(root, ref)
            valid[slot] = True
        except (OSError, ValueError):
            valid[slot] = False
        inventory.append({"slot": slot, "sha256": ref.sha256, "bytes_valid": valid[slot],
                          "issue": None if valid[slot] else "evidence_changed"})
    by_control = {}
    for record in records:
        by_control.setdefault(record["control_id"], []).append(record)

    def annotate(record):
        value = deepcopy(record)
        issues = []
        if value["context_sha256"] != context:
            issues.append("context_changed")
        if any(slot not in current or not valid.get(slot) or
               current[slot].model_dump() != value["evidence_bindings"].get(slot)
               for slot in value["evidence_slots"]):
            issues.append("evidence_changed")
        value["stale"] = bool(issues)
        value["issues"] = issues
        value["evidence_sha256"] = {slot: ref["sha256"] for slot, ref in value["evidence_bindings"].items()}
        # Paths are not a review input or necessary in this outward record.
        value.pop("evidence_bindings")
        return value

    counts = {"recorded": 0, "needs_work": 0, "not_started": 0}
    for control in result["controls"]:
        history = by_control.get(control["id"], [])
        latest = annotate(history[-1]) if history else None
        issues = latest["issues"] if latest else []
        state = "not_started"
        if latest:
            state = "needs_work" if issues or latest["status"] == "gap" else "recorded"
        counts[state] += 1
        control.update(state=state, issues=issues, history_count=len(history), latest_review=latest,
                       history=[annotate(item) for item in reversed(history[-20:])], history_truncated=len(history) > 20)
    result.update(case_id=case_id, mode=project.mode, context_sha256=context,
                  history_count=len(records), summary=counts, evidence_slots=inventory)
    return result
