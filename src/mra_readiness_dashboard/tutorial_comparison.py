"""Pure paired explanations for two finite fictional tutorial configurations.

Both sides reuse the existing lesson evaluator. No filesystem, network, clocks,
scientific procedures or real decision state are read or changed.
"""
from copy import deepcopy
import json

from .interactive_tutorial import CONTROL_KEYS, evaluate_assumptions

SCHEMA = "local-fictional-tutorial-comparison/1"
DEFAULT_LEFT_PRESET_ID = "starting-point"
DEFAULT_RIGHT_PRESET_ID = "worked-example"


def _changed_controls(left, right):
    left_rows = {row["key"]: row for row in left["selected_controls"]}
    right_rows = {row["key"]: row for row in right["selected_controls"]}
    return [
        {
            "key": key,
            "label": left_rows[key]["label"],
            "left": deepcopy(left_rows[key]),
            "right": deepcopy(right_rows[key]),
        }
        for key in CONTROL_KEYS
        if left["assumptions"][key] != right["assumptions"][key]
    ]


def _checkpoint_index(gap):
    # Factor and control key identify the explanatory checkpoint together.
    # Several terms dependencies may have the same factor and different keys.
    return {
        (row["control_key"], row["factor"]): row
        for row in gap["checklist"]
    }


def _checkpoint_pairs(left, right):
    left_rows = _checkpoint_index(left)
    right_rows = _checkpoint_index(right)
    ordered_keys = list(left_rows)
    ordered_keys.extend(key for key in right_rows if key not in left_rows)
    pairs = []
    for key in ordered_keys:
        left_row = left_rows.get(key)
        right_row = right_rows.get(key)
        if left_row is None:
            change = "right_only"
            explanation = (
                "This conditional checkpoint is triggered only by the right-hand "
                "selections. On the left it is not triggered; that absence supplies "
                "no authentic evidence and closes no real requirement."
            )
        elif right_row is None:
            change = "left_only"
            explanation = (
                "This conditional checkpoint is triggered only by the left-hand "
                "selections. On the right it is not triggered; that absence supplies "
                "no authentic evidence and closes no real requirement."
            )
        elif left_row != right_row:
            change = "different"
            explanation = (
                "The selected value, teaching condition or explanation differs. "
                "Read both checkpoint reasons even if their teaching-state labels "
                "are the same. Neither side supplies an authentic receipt."
            )
        else:
            change = "same"
            explanation = (
                "Both configurations retain the same checkpoint value, teaching "
                "condition and explanation. Any stated missing authentic evidence "
                "or empirical condition remains missing on both sides."
            )
        pairs.append({
            "factor": key[1],
            "control_key": key[0],
            "left": deepcopy(left_row),
            "right": deepcopy(right_row),
            "left_applicable": left_row is not None,
            "right_applicable": right_row is not None,
            "different": left_row != right_row,
            "change": change,
            "explanation": explanation,
        })
    return pairs


def _referenced_controls(left, right):
    referenced = set()
    for gap in (left, right):
        for checkpoint in gap["checklist"]:
            referenced.update(checkpoint["control_key"].split("+"))
    return referenced


def _gap_comparison(left, right, changed):
    pairs = _checkpoint_pairs(left, right)
    checkpoint_differences = [deepcopy(row) for row in pairs if row["different"]]
    state_changed = left["state"] != right["state"]
    checklists_changed = left["checklist"] != right["checklist"]
    referenced = _referenced_controls(left, right)
    affected = [deepcopy(row) for row in changed if row["key"] in referenced]
    if state_changed:
        kind = "state_and_checkpoint_differences"
        explanation = (
            "The configurations have different teaching-state labels and different "
            "checkpoint conditions. Each side explains its own assumptions and "
            "dependencies. The comparison assigns no rank and makes no real "
            "readiness or acceptance decision."
        )
    elif checklists_changed:
        kind = "checkpoint_differences"
        explanation = (
            "The teaching-state label is unchanged, but the selected checkpoint "
            "conditions or their reasons differ. The shared label can conceal "
            "different unresolved or conflicting assumptions; read the paired "
            "checkpoints. It does not mean that the selections have no effect."
        )
    else:
        kind = "same_checklist"
        if changed:
            explanation = (
                "The changed selections do not alter any checkpoint in this "
                "checklist under the finite lesson rules. Both sides retain the "
                "same teaching conditions and missing authentic receipts. This "
                "unchanged lesson row establishes no real evidence or closure."
            )
        else:
            explanation = (
                "Both sides resolve to the same teaching assumptions and "
                "checklist. Preset provenance or side placement alone does not "
                "create an assumption difference. Missing authentic receipts "
                "and any unresolved empirical checkpoint remain unchanged."
            )
    return {
        "id": left["id"],
        "title": left["title"],
        "left": deepcopy(left),
        "right": deepcopy(right),
        "state_changed": state_changed,
        "checklists_changed": checklists_changed,
        "changed_controls": affected,
        "checkpoint_pairs": pairs,
        "checkpoint_differences": checkpoint_differences,
        "difference_kind": kind,
        "explanation": explanation,
        "real_gap_status": "open",
        "real_receipt_status": "not_supplied",
        "authentic_receipt_supplied": False,
        "demonstrated_result": False,
    }


def evaluate_comparison(left_values=None, right_values=None,
                        left_preset=None, right_preset=None):
    """Return fresh independent lessons and reasoned paired checkpoint effects.

    A missing left preset starts at unanswered conditions. A missing right preset
    starts at the complete fictional worked example. Explicit presets and partial
    choices use the existing evaluator's strict finite validation unchanged.
    Preset provenance is retained but does not itself create a difference.
    """
    left_id = DEFAULT_LEFT_PRESET_ID if left_preset is None else left_preset
    right_id = DEFAULT_RIGHT_PRESET_ID if right_preset is None else right_preset
    left = evaluate_assumptions(left_values, left_id)
    right = evaluate_assumptions(right_values, right_id)
    changed = _changed_controls(left, right)
    left_gaps = left["simulated"]["gap_checklists"]
    right_gaps = right["simulated"]["gap_checklists"]
    return {
        "schema": SCHEMA,
        "title": "Compare fictional decisions and source assumptions",
        "summary": (
            "Read two independently selected teaching configurations side by side. "
            "Each checklist pairs all conditions, explains changed assumptions and "
            "retains shared missing evidence. A shared state label can still have "
            "different reasons. There is no score, preferred configuration, "
            "scientific result or real gap closure."
        ),
        "fictional_example": True,
        "public_synthetic_only": True,
        "authentic_source_records_included": False,
        "real_agency_decisions": "pending",
        "original_substantive_gaps_closed": 0,
        "original_substantive_gaps_open": 12,
        "authorization_effect": "none",
        "benchmark_executed": False,
        "left": left,
        "right": right,
        "changed_controls": changed,
        "comparison": {
            "gap_checklists": [
                _gap_comparison(left_gap, right_gap, changed)
                for left_gap, right_gap in zip(left_gaps, right_gaps)
            ],
            "scientific_result": "not_demonstrated",
            "operational_evidence": "not_supplied",
            "agency_acceptance": "pending",
        },
        "guidance": {
            "do": [
                "Keep one side fixed while changing a decision or source assumption on the other; then read every affected checkpoint reason.",
                "Read paired checkpoint conditions even when the teaching-state label stays the same.",
                "Treat a condition shown on only one side as a dependency triggered by that side, rather than evidence supplied by the other.",
                "Keep authentic receipt requirements and the unresolved empirical checkpoints visible on both sides.",
                "Use the same resolved assumptions on both sides to distinguish an actual assumption difference from preset provenance.",
            ],
            "dont": [
                "Do not turn a different teaching label, aligned assumptions or a shorter-looking checklist into a score, preferred choice or real approval.",
                "Do not treat a missing conditional conflict row as an authentic receipt, scientific success or permission to act.",
                "Do not infer authentic source records, actual appointments, source admission, protected-data authority, operational capability or pilot acceptance from either side.",
                "Do not alter the sealed adverse result or unsupported findings, substitute a synthetic download for real intake, or infer that a benchmark was executed.",
            ],
            "next_questions": [
                "Which changed choice alters the checkpoint, and which dependent teaching note must be reconsidered with it?",
                "If two labels match, are their unresolved conditions and explanations also the same?",
                "What accountable decision and authentic evidence would still be required on either side before actual use could be considered?",
            ],
        },
    }


def comparison_json(left_values=None, right_values=None,
                    left_preset=None, right_preset=None):
    """Return deterministic canonical UTF-8 JSON for the paired teaching schema."""
    return (json.dumps(
        evaluate_comparison(left_values, right_values, left_preset, right_preset),
        ensure_ascii=False, allow_nan=False, sort_keys=True,
        separators=(",", ":")) + "\n").encode("utf-8")
