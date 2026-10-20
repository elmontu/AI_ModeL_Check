"""Fixed guided lessons built from the unchanged fictional comparison evaluator.

Navigation selects finite teaching metadata only. No files, clocks, network
requests, science, real decision state, progress records or grades are accessed.
"""
from copy import deepcopy
from urllib.parse import urlencode

from .interactive_tutorial import CONTROL_KEYS
from .tutorial_comparison import evaluate_comparison

SCHEMA = "local-fictional-guided-comparison/1"
DEFAULT_STEP_ID = "orientation"

_STEPS = (
    {
        "id": "orientation",
        "title": "Read the reasons behind the labels",
        "left_preset": "starting-point",
        "right_preset": "worked-example",
        "focus_gap_ids": ("G05", "G06"),
        "goal": "Learn how two configurations can share a teaching label while their checkpoint conditions differ.",
        "action": "Read the paired G05 and G06 checklists below. Configuration A has unanswered starting conditions; configuration B has the complete worked fictional assumptions. Follow the checkpoint reasons on both sides.",
        "observe": (
            "Both G05 and G06 keep the label Lesson assumptions unresolved on both sides.",
            "The surrounding purpose, definition and source conditions differ even though those broad labels match.",
            "The empirical checkpoint remains unresolved and authentic receipts remain not supplied in both configurations.",
        ),
        "explanation": "A broad label summarizes the teaching conditions. It does not describe every reason behind them. The worked fictional account can make its invented purpose, category meanings and issue ordering internally coherent while supplying no empirical performance or target-setting validation. The paired rows therefore show meaningful changes without turning a plausible account into a scientific result.",
        "reflection_question": "Why can G05 and G06 retain the same unresolved label even though the selected assumptions differ?",
        "reflection_answer": "Their empirical checkpoint remains unresolved under every configuration. The selected surrounding conditions can change while that missing condition keeps the broad label unresolved. The shared label therefore does not mean the paired conditions are identical, and neither configuration supplies authentic scientific evidence.",
        "takeaway": "Read the complete checkpoint reasons before interpreting a shared teaching label.",
    },
    {
        "id": "equal-baseline",
        "title": "Establish the same starting assumptions",
        "left_preset": "worked-example",
        "right_preset": "worked-example",
        "focus_gap_ids": ("G03", "G05", "G06"),
        "goal": "Use identical resolved assumptions as a reference before comparing a specific change.",
        "action": "Inspect the two worked-example configurations. Check that their selected assumptions and paired G03 conditions match, then read the shared empirical limits in G05 and G06.",
        "observe": (
            "Both sides have the same effective assumptions, so every gap has the comparison finding Same checklist.",
            "G03's invented definitions, narrow teaching terms and separate source note align within the same fictional boundary on both sides.",
            "G05 and G06 still have unresolved empirical conditions, and every gap still requires authentic real receipts.",
        ),
        "explanation": "A common starting point makes a later change easier to explain. Equality means the same selected teaching conditions and reasons are displayed. It supplies no evidence about a real project. The worked example also preserves its held operational boundary: teaching handover is not a pilot, and an invented exact-revision index is not an agency receipt.",
        "reflection_question": "If the two configurations match, has either one met the actual readiness requirements?",
        "reflection_answer": "No. Matching configurations establish only that the finite lesson rules produce the same conditions and reasons. Authentic receipts remain absent, G05 and G06 empirical evidence remains unresolved, and all twelve real gaps remain open.",
        "takeaway": "An equal baseline isolates later assumption changes without conferring evidence or authority.",
    },
    {
        "id": "decision-review",
        "title": "Change the fictional review arrangement",
        "left_preset": "worked-example",
        "right_preset": "worked-example",
        "right_values": {"decision_review": "overlap"},
        "focus_gap_ids": ("G01",),
        "goal": "Trace how a changed review arrangement affects the scope and accountable-remit checklist.",
        "action": "Compare G01. Configuration A keeps the separate fictional Review Circle note. Configuration B selects drafting self-review without recusal. Read the review checkpoint and then inspect the effects across the other gaps.",
        "observe": (
            "Only the decision-review choice differs between the selected configurations.",
            "G01 changes from aligned teaching assumptions on A to a conflict on B because the review arrangement overlaps drafting without recusal.",
            "The other effect summaries retain their actual dependency outcomes; authentic appointments and accepted remits remain absent on both sides.",
        ),
        "explanation": "A reviewer label is useful only when its remit, competence assumptions, exact revision and relationship to drafting and delivery are understood. The lesson's separate-review choice describes those conditions within the invented case. The overlapping choice exposes a conflict that a title alone cannot cure. This illustrates a reason to reconsider review arrangements; it appoints nobody and establishes no actual independence.",
        "reflection_question": "Would authentic source definitions alone resolve B's overlapping-review conflict in G01?",
        "reflection_answer": "No. Source definitions address a different prerequisite. They cannot establish an accountable remit, supply an authenticated appointment or resolve a drafting and review conflict. The review arrangement needs its own appropriate decision and attributable evidence.",
        "takeaway": "Follow the review arrangement and its remit; a source ledger cannot substitute for accountable review.",
    },
    {
        "id": "source-chronology",
        "title": "Keep the later correction out of the earlier origin",
        "left_preset": "worked-example",
        "right_preset": "worked-example",
        "right_values": {"vintage": "correction-backfill"},
        "focus_gap_ids": ("G04",),
        "goal": "Distinguish the invented first-issue account from a contradictory later-information assumption.",
        "action": "Read G04 with A's first issue before the cutoff and B's later correction backfilled at that earlier cutoff. Both sides retain the separate fictional source note. Inspect the conditional source-note checkpoint that appears on B.",
        "observe": (
            "A keeps the invented first issue before the cutoff and excludes the later correction there.",
            "B's selected correction contradicts the invented release order and the exact source account described by its selected review note.",
            "The extra dependency checkpoint on B is not triggered on A; its absence on A supplies no authentic historical bytes or real eligibility receipt.",
        ),
        "explanation": "An earlier-origin account depends on what was actually available at that origin. A later correction must remain separate rather than silently replacing the earlier view. The selected fictional source note describes the first-issue ordering, so B's backfill also conflicts with that note's exact account. The lesson illustrates both a direct condition and a dependency; it supplies no authentic release evidence.",
        "reflection_question": "Does A's lack of the additional source-note conflict prove that its original issue was genuinely available?",
        "reflection_answer": "No. It means only that A's selected fictional assumptions do not trigger that particular contradiction. Authentic original bytes, actual release evidence with adequate precision, traceable revisions and independent qualification are still required for a real earlier-origin claim.",
        "takeaway": "A conditional conflict disappearing is not evidence arriving; original availability still needs authentic support.",
    },
    {
        "id": "different-conflicts",
        "title": "Compare two different source conflicts",
        "left_preset": "worked-example",
        "right_preset": "worked-example",
        "left_values": {"definitions": "mismatch"},
        "right_values": {"rights": "outside-scope"},
        "focus_gap_ids": ("G03",),
        "goal": "Read different causes behind the same broad conflict label.",
        "action": "Compare G03's full paired checklist. A merges the broader Guidance label with all three invented categories. B keeps the distinct meanings but assumes that visibility permits unrestricted reuse. Read the definition, terms and source-note reasons separately.",
        "observe": (
            "Both sides have the teaching label Lesson assumptions conflict.",
            "A's conflict concerns incompatible category meanings, while B's concerns exceeding the narrow invented teaching terms.",
            "Each choice also contradicts the corresponding part of the selected separate fictional source note; the paired reasons preserve those different dependencies.",
        ),
        "explanation": "Definitions and applicable terms are separate source prerequisites. A common name cannot establish comparable meaning, and a visible source cannot establish permission for every recipient or use. A matching broad label therefore does not identify a shared remedy. The lesson keeps each reason visible without ranking the configurations or claiming that either fictional account resolves a real source obligation.",
        "reflection_question": "Could the same evidence automatically resolve both configurations simply because their G03 labels match?",
        "reflection_answer": "No. A's incompatible meanings need a justified definition and comparability account. B's reuse assumption needs applicable artifact-specific terms and a supported intended-use boundary. Each actual source decision would need its own authentic evidence and appropriate review.",
        "takeaway": "A shared conflict label can conceal different questions, evidence needs and accountable decisions.",
    },
    {
        "id": "operations",
        "title": "Separate a stewardship plan from proven operations",
        "left_preset": "worked-example",
        "right_preset": "worked-example",
        "right_values": {"operations": "deployment-assumed"},
        "focus_gap_ids": ("G10", "G04"),
        "goal": "See an affected operational checklist beside an unchanged source-chronology checklist.",
        "action": "Compare G10 after B treats the written plan as proven deployment and recovery. A retains static-session teaching stewardship. Then compare G04, whose selected original-issue conditions remain the same on both sides.",
        "observe": (
            "G10 has different teaching labels and checkpoints because B converts a plan into an unsupported operational claim.",
            "G04 retains the same full checklist because this operations change does not alter its selected issue-ordering conditions under the finite lesson rules.",
            "Other affected dependencies remain visible in the twelve-gap summary; no workload, service objective, recovery exercise or infrastructure qualification is supplied.",
        ),
        "explanation": "A written steward, stop question or retirement plan explains responsibilities and reasons for reconsideration. It is not an exercised service or measured operating capability. The comparison also gives a bounded example of an unchanged row: the lesson's G04 mapping does not use the changed operations choice. That narrow equality is not a claim that actual operational changes have no wider consequences.",
        "reflection_question": "Does the unchanged G04 row establish that a real operational change needs no source or governance reconsideration?",
        "reflection_answer": "No. It reports only that this finite lesson maps the selected operations change to other conditions while keeping G04's displayed source assumptions unchanged. Actual owners must consider the real setting, dependencies, records and obligations. Authentic evidence remains missing on both sides.",
        "takeaway": "Read both changed and unchanged rows, and keep a plan distinct from demonstrated capability.",
    },
    {
        "id": "practice",
        "title": "Continue in the editable comparison",
        "left_preset": "worked-example",
        "right_preset": "worked-example",
        "focus_gap_ids": ("G05", "G06"),
        "goal": "Practice explaining one changed assumption while retaining the real evidence boundary.",
        "action": "Open the editable workbench with these exact equal configurations. Keep A fixed, change one decision or source choice on B, select Update comparison and read the affected checkpoint reasons. Apply edited choices before using preset, swap or reset links.",
        "observe": (
            "This lesson begins with equal worked-example assumptions; the workbench link carries both complete configurations.",
            "The editable workbench can apply a change, load a preset on one side while preserving the other, swap the illustrated configurations and reset both loaded presets.",
            "Returning to a walkthrough step loads its fixed lesson again. Custom edits, learning progress and grades are not saved by the walkthrough.",
        ),
        "explanation": "Use the comparison as a tool for questions and explanations. First identify the changed assumption, then identify the direct or conditional checkpoint it affects, and finally name the authentic evidence and accountable decision that remain required. A coherent lesson, an unchanged row or a successful navigation action cannot meet an actual readiness condition.",
        "reflection_question": "What should an explanation of your practice comparison include before considering any actual use?",
        "reflection_answer": "Name the selected change, the affected checkpoint reasons, any dependency that appears or disappears, and any row that remains unchanged under the lesson rules. Keep the authentic receipts, unresolved empirical evidence and accountable agency decisions explicit. Neither a completed walkthrough nor a coherent configuration authorizes actual use.",
        "takeaway": "Use the lesson to improve the questions and reasoning; all real evidence and agency decisions remain pending.",
    },
)

STEP_IDS = tuple(row["id"] for row in _STEPS)
STEP_OPTIONS = tuple((row["id"], row["title"]) for row in _STEPS)
_STEP_INDEX = {row["id"]: row for row in _STEPS}
_TEXT_KEYS = ("goal", "action", "explanation", "reflection_question",
              "reflection_answer", "takeaway")


def _step_id(step):
    if step is None:
        return DEFAULT_STEP_ID
    if type(step) is not str or step not in _STEP_INDEX:
        raise ValueError("Unknown guided comparison step")
    return step


def _workbench_base(comparison):
    fields = [
        ("left_preset", comparison["left"]["preset_id"]),
        ("right_preset", comparison["right"]["preset_id"]),
    ]
    for side in ("left", "right"):
        fields.extend((side + "_" + key, comparison[side]["assumptions"][key])
                      for key in CONTROL_KEYS)
    return "/tutorial-compare?" + urlencode(fields)


def evaluate_walkthrough(step=None):
    """Return a fresh fixed lesson and actual unchanged comparison effects.

    The step is the only input. No custom assumptions, assessment, completion
    state or progress record is accepted. Workbench links reproduce all choices.
    """
    identifier = _step_id(step)
    specification = _STEP_INDEX[identifier]
    position = STEP_IDS.index(identifier)
    comparison = evaluate_comparison(
        specification.get("left_values"), specification.get("right_values"),
        specification["left_preset"], specification["right_preset"])
    gaps = comparison["comparison"]["gap_checklists"]
    indexed = {row["id"]: row for row in gaps}
    base = _workbench_base(comparison)
    per_gap_urls = {row["id"]: base + "#compare-" + row["id"] for row in gaps}
    focus = list(specification["focus_gap_ids"])
    summaries = [
        {
            "id": row["id"],
            "title": row["title"],
            "left_state": row["left"]["state"],
            "left_label": row["left"]["label"],
            "right_state": row["right"]["state"],
            "right_label": row["right"]["label"],
            "difference_kind": row["difference_kind"],
            "state_changed": row["state_changed"],
            "checklists_changed": row["checklists_changed"],
            "explanation": row["explanation"],
            "workbench_url": per_gap_urls[row["id"]],
            "real_gap_status": row["real_gap_status"],
            "real_receipt_status": row["real_receipt_status"],
        }
        for row in gaps
    ]
    return {
        "schema": SCHEMA,
        "id": identifier,
        "title": specification["title"],
        "position": position + 1,
        "total": len(STEP_IDS),
        "previous_id": STEP_IDS[position - 1] if position else None,
        "next_id": STEP_IDS[position + 1] if position + 1 < len(STEP_IDS) else None,
        **{key: specification[key] for key in _TEXT_KEYS},
        "observe": list(specification["observe"]),
        "focus_gap_ids": focus,
        "comparison": comparison,
        "gap_summaries": summaries,
        "focused_gap_checklists": [deepcopy(indexed[key]) for key in focus],
        "workbench_url": per_gap_urls[focus[0]],
        "workbench_form_url": base + "#comparison-workbench",
        "per_gap_urls": per_gap_urls,
        "fictional_example": True,
        "public_synthetic_only": True,
        "authentic_source_records_included": False,
        "real_agency_decisions": "pending",
        "original_substantive_gaps_open": 12,
        "original_substantive_gaps_closed": 0,
        "authorization_effect": "none",
        "benchmark_executed": False,
        "progress_saved": False,
        "graded": False,
        "custom_edits_retained": False,
        "navigation_boundary": (
            "Previous, next and restart select fixed lesson configurations. "
            "Open the editable workbench to make your own comparison. Returning "
            "to a walkthrough step loads its fixed illustration again; no custom "
            "edit, learning progress, grade, agency response or approval is saved."
        ),
    }
