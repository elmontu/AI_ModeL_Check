"""Finite ungraded practice using the unchanged fictional comparison evaluator.

The fixed reference and initial editable configuration are worked examples.
Feedback describes current selected assumptions, without inferring edit history,
intent, learning, evidence, acceptance or authority. No external state is read.
"""
from copy import deepcopy
from urllib.parse import urlencode

from .interactive_tutorial import CONTROL_KEYS
from .tutorial_comparison import evaluate_comparison

SCHEMA = "local-fictional-guided-practice/1"
DEFAULT_EXERCISE_ID = "review-arrangement"
_PRESET_ID = "worked-example"

_EXERCISES = (
    {
        "id": "review-arrangement",
        "title": "Review arrangements and accountable remits",
        "focus_gap_ids": ("G01",),
        "goal": "Explain how a selected review arrangement relates to scope, remits and independence.",
        "prompt": "Keep the fixed reference A in view. Choose any review arrangement for B, select Explain my changes and read the current paired checkpoint reasons. You may also explore another allowed assumption.",
        "suggestion": "Try the overlapping drafting self-review choice on B, then compare it with proposed or unanswered review. A separate-review label, an unanswered remit and a conflict pose different questions.",
        "reflection_question": "What would a real review arrangement need beyond a selected reviewer label?",
        "reflection_explanation": "If overlapping drafting self-review is selected, the lesson exposes the unresolved separation and recusal conflict. If separate review is selected, its fictional remit and exact-revision conditions still appoint nobody. Authentic appointments, competence, accepted remits, delegation limits and appropriate independent review remain actual evidence and decision requirements. The feedback below follows whichever choices B currently contains.",
    },
    {
        "id": "source-chronology",
        "title": "Original issues and later corrections",
        "focus_gap_ids": ("G04",),
        "goal": "Explain an earlier-origin source assumption while preserving the first issue and later correction separately.",
        "prompt": "Explore B's original-issue and cutoff choices. Select Explain my changes and inspect G04's direct and conditional reasons, including any dependency on the selected fictional source note.",
        "suggestion": "Try backfilling the later correction, or select unknown original availability while keeping the separate source note. Compare either illustration with the fixed first-issue reference A.",
        "reflection_question": "What does the absence of a source-note conflict establish about authentic original availability?",
        "reflection_explanation": "If backfilling is selected, the hypothetical earlier-origin use contradicts the invented ordering. If original availability is unknown, it remains unresolved and may contradict a simultaneous note that asserts the first-issue account. If those conflicts are not triggered, that absence supplies no authentic original bytes or official release evidence. Actual eligibility still requires traceable records, adequate timing precision and appropriate independent qualification.",
    },
    {
        "id": "definitions-terms",
        "title": "Definitions and artifact-specific terms",
        "focus_gap_ids": ("G03",),
        "goal": "Distinguish a meaning mismatch from an unsupported permission or recipient assumption.",
        "prompt": "Explore B's definition and teaching-term choices separately or together. Select Explain my changes and read the paired G03 conditions rather than relying on the broad lesson label.",
        "suggestion": "Try merging Guidance with all three invented categories. Reset this exercise, then try unrestricted reuse based on visibility. You may combine them to inspect their separate dependencies.",
        "reflection_question": "Why can the same conflict label call for different evidence and decisions?",
        "reflection_explanation": "If incompatible meanings are selected, a common name cannot establish comparability; the definition and reconciliation account needs support. If unrestricted reuse is assumed, source visibility cannot establish applicable artifact-specific terms or permission for a broader recipient and use. These are separate prerequisites. A shared conflict label does not identify a shared cause or a single remedy, and the actual feedback reflects the selected combination.",
    },
    {
        "id": "source-dependencies",
        "title": "Source notes and their dependent assumptions",
        "focus_gap_ids": ("G04", "G09", "G12"),
        "goal": "Trace how an exact fictional source note depends on the definitions, terms and chronology it describes.",
        "prompt": "Explore a source assumption on B while considering the source-review selection beside it. Select Explain my changes and follow the actual dependency reasons through the focused gaps and the complete summary.",
        "suggestion": "Keep the separate source note selected and choose unknown original availability or unresolved definitions. Then compare with an unreviewed source note. Removing a note does not supply the missing source account.",
        "reflection_question": "Can an independent-sounding note fill an unanswered or contradictory source prerequisite?",
        "reflection_explanation": "If the selected separate source note describes distinct meanings, narrow terms and first-issue ordering while another selected assumption contradicts that account, a conditional dependency is exposed. If the note is unreviewed, its independent qualification is missing instead. No reviewer label can silently provide a definition, widen terms or establish release evidence. Which downstream checklists differ depends on the current choices, not on the exercise title.",
    },
    {
        "id": "operations",
        "title": "Stewardship plans and operational evidence",
        "focus_gap_ids": ("G10", "G04"),
        "goal": "Explain an affected operational checklist and the limited meaning of an unchanged source checklist.",
        "prompt": "Explore B's operations choice. Select Explain my changes and read G10 beside G04, then inspect any other affected dependencies. Additional choices remain available if you want to explore a mixed configuration.",
        "suggestion": "Try treating the plan as proven deployment and recovery while leaving every other choice equal to A. Then consider whether an additional source change alters the previously unchanged source row.",
        "reflection_question": "When can G04 stay unchanged, and what does that equality fail to demonstrate?",
        "reflection_explanation": "If only the operations option differs, treating a written plan as proven deployment exposes an unsupported claim in G10 while G04 retains the same selected original-issue conditions under the finite lesson mapping. Additional definition or chronology changes can also alter G04, so that unchanged outcome must not be assumed for every mixture. Equality establishes no authentic evidence or proof that an actual operational change has no wider consequences. A plan supplies no measured workload, accepted service objective, exercised recovery or qualified environment.",
    },
    {
        "id": "free-practice",
        "title": "Open practice with the full evidence boundary",
        "focus_gap_ids": ("G05", "G06"),
        "goal": "Explain a freely chosen comparison while retaining unresolved empirical evidence and pending actual decisions.",
        "prompt": "Choose any finite decision or source assumptions for B. Select Explain my changes, identify the current differences from fixed A and follow their direct, conditional and unchanged checklist reasons.",
        "suggestion": "Begin with one selected difference, then try a mixed configuration. Read a shared broad label carefully and identify a row that remains the same under the lesson rules. Reset returns B to the worked starting assumptions.",
        "reflection_question": "What should an explanation of the current configuration include without claiming readiness or learning completion?",
        "reflection_explanation": "If B matches A, the current lesson has the same conditions and reasons. If B differs, explain the selected values and their actual direct or conditional effects, including any shared label whose reasons differ. Preserve the authentic receipts still required and the empirical checkpoints that remain unresolved in G05 and G06 under every selection. No configuration, navigation action or plausible explanation demonstrates scientific success, actual acceptance or completed learning.",
    },
)

EXERCISE_IDS = tuple(row["id"] for row in _EXERCISES)
EXERCISE_OPTIONS = tuple((row["id"], row["title"]) for row in _EXERCISES)
_EXERCISE_INDEX = {row["id"]: row for row in _EXERCISES}
_TEXT_KEYS = ("goal", "prompt", "suggestion", "reflection_question", "reflection_explanation")


def _exercise_id(exercise):
    if exercise is None:
        return DEFAULT_EXERCISE_ID
    if type(exercise) is not str or exercise not in _EXERCISE_INDEX:
        raise ValueError("Unknown guided practice exercise")
    return exercise


def _workbench_base(comparison):
    values = [
        ("left_preset", comparison["left"]["preset_id"]),
        ("right_preset", comparison["right"]["preset_id"]),
    ]
    for side in ("left", "right"):
        values.extend((side + "_" + key, comparison[side]["assumptions"][key])
                      for key in CONTROL_KEYS)
    return "/tutorial-compare?" + urlencode(values)


def _learning_explanation(gap, has_changes):
    if not gap["checklists_changed"]:
        if has_changes:
            introduction = (
                "Current B differs from fixed A elsewhere, while this checklist "
                "retains the same checkpoint values and reasons under the finite "
                "lesson rules. "
            )
        else:
            introduction = (
                "Current B matches fixed A. This checklist therefore retains the "
                "same selected conditions and reasons. "
            )
    else:
        selections = [
            row["label"] + ": A uses " + row["left"]["value_label"]
            + "; current B uses " + row["right"]["value_label"]
            for row in gap["changed_controls"]
        ]
        introduction = "Selected conditions referenced here differ. " + ". ".join(selections) + ". "
        if gap["state_changed"]:
            introduction += (
                "A has the lesson label " + gap["left"]["label"]
                + "; current B has " + gap["right"]["label"] + ". "
            )
        else:
            introduction += (
                "Both sides retain the lesson label " + gap["left"]["label"]
                + ", while their checkpoint reasons differ. "
            )
        if any("+" in pair["control_key"] for pair in gap["checkpoint_differences"]):
            introduction += (
                "A conditional dependency also differs or is triggered on only "
                "one side. A condition not triggered supplies no authentic evidence. "
            )
    conclusion = (
        " Authentic receipts remain not supplied and the actual gap remains open "
        "on both sides."
    )
    if gap["id"] in ("G05", "G06"):
        conclusion += " The empirical checkpoint remains unresolved on both sides."
    return introduction + gap["explanation"] + conclusion


def evaluate_practice(values=None, exercise=None):
    """Explain current finite B selections against a fixed worked reference A.

    Every exercise starts with the same equal pair. Exercise metadata supplies
    questions and suggestions only; it neither forces target choices nor grades
    a response. Input validation is the existing strict comparison validation.
    """
    identifier = _exercise_id(exercise)
    specification = _EXERCISE_INDEX[identifier]
    comparison = evaluate_comparison({}, values, _PRESET_ID, _PRESET_ID)
    has_changes = comparison["left"]["assumptions"] != comparison["right"]["assumptions"]
    if has_changes:
        feedback_intro = (
            "Current configuration B differs from the fixed worked-example "
            "reference A. Read the selected differences and the actual paired "
            "checkpoint reasons below. Feedback describes this current "
            "illustration, with no judgment of readiness, intent or learning."
        )
    else:
        feedback_intro = (
            "Current configuration B matches the fixed worked-example reference "
            "A. The paired conditions and reasons are the same. Authentic receipts "
            "remain absent, empirical evidence remains unresolved and no real "
            "requirement or learning completion is established."
        )
    gaps = comparison["comparison"]["gap_checklists"]
    base = _workbench_base(comparison)
    per_gap_urls = {row["id"]: base + "#compare-" + row["id"] for row in gaps}
    focus = list(specification["focus_gap_ids"])
    exercise_urls = {
        key: "/tutorial-practice?" + urlencode({"exercise": key})
        for key in EXERCISE_IDS
    }
    feedback = [
        {
            "id": row["id"],
            "title": row["title"],
            "difference_kind": row["difference_kind"],
            "has_checkpoint_changes": row["checklists_changed"],
            "state_changed": row["state_changed"],
            "changed_controls": deepcopy(row["changed_controls"]),
            "learning_explanation": _learning_explanation(row, has_changes),
            "checklist": deepcopy(row),
        }
        for row in gaps
    ]
    return {
        "schema": SCHEMA,
        "id": identifier,
        "title": specification["title"],
        **{key: specification[key] for key in _TEXT_KEYS},
        "focus_gap_ids": focus,
        "comparison": comparison,
        "reference_assumptions": deepcopy(comparison["left"]["assumptions"]),
        "starting_assumptions": deepcopy(comparison["left"]["assumptions"]),
        "assumptions": deepcopy(comparison["right"]["assumptions"]),
        "selected_controls": deepcopy(comparison["right"]["selected_controls"]),
        "has_changes": has_changes,
        "changed_controls": deepcopy(comparison["changed_controls"]),
        "feedback_intro": feedback_intro,
        "gap_feedback": feedback,
        "workbench_url": per_gap_urls[focus[0]],
        "workbench_form_url": base + "#comparison-workbench",
        "per_gap_urls": per_gap_urls,
        "reset_url": exercise_urls[identifier],
        "exercise_urls": exercise_urls,
        "fictional_example": True,
        "public_synthetic_only": True,
        "authentic_source_records_included": False,
        "real_agency_decisions": "pending",
        "original_substantive_gaps_open": 12,
        "original_substantive_gaps_closed": 0,
        "authorization_effect": "none",
        "benchmark_executed": False,
        "graded": False,
        "progress_saved": False,
        "navigation_boundary": (
            "Exercise links load the equal worked starting pair and discard the "
            "current illustrated overrides. Reset keeps this exercise and restores "
            "B's worked starting assumptions. Apply choices with Explain my "
            "changes. No learning progress, grade, agency response or approval "
            "is saved."
        ),
    }
