"""Pure finite fictional assumptions and teaching-checklist effects.

No files, service state, network, scientific procedures, clocks or actual decisions
are accessed. Invented records never supply authentic evidence or authority.
"""
from copy import deepcopy
import json

SCHEMA = "local-fictional-interactive-decision-evidence-tutorial/1"
PRESET_IDS = ("starting-point", "draft-decisions", "reviewed-decisions",
              "traceable-sources", "worked-example")
PRESET_OPTIONS = (
    ("starting-point", "Starting point"),
    ("draft-decisions", "Draft decisions"),
    ("reviewed-decisions", "Reviewed fictional decisions; sources unresolved"),
    ("traceable-sources", "Traceable synthetic sources"),
    ("worked-example", "Complete worked fictional example"),
)
DEFAULT_PRESET_ID = "starting-point"

# Immutable private data drives validation; exported metadata is only a copy.
# Each option is identifier, visible label, teaching condition, explanation.
_CONTROL_DATA = (
    ("purpose", "Purpose and recipient",
     "Whether the fictional Planning Circle discussion stays within the teaching case.",
     (
         ("unanswered", "Purpose and recipient conditions unanswered", "unresolved",
          "The Service Planning Office has not chosen a use or recipient boundary for toy-planning-package-A."),
         ("discussion", "Planning Circle: discussion only; no onward sharing", "illustrated",
          "The fictional Planning Circle discusses invented Directions, Form Guidance and Appointment Information categories in the Information Desk Capacity Review. Individual eligibility, ranking, automated decisions and onward sharing are excluded."),
         ("individual-use", "Assume individual decisions or onward sharing", "conflict",
          "This hypothetical extension contradicts the static discussion-only package and narrow Planning Circle teaching terms. No individual data, authority or delivery evidence is supplied."),
     )),
    ("decision_review", "Role remits and decision review",
     "Whether fictional drafting and review roles have distinct remits at the exact teaching revision.",
     (
         ("unanswered", "Roles and exact-revision review unanswered", "unresolved",
          "No fictional service, data, security or scientific remit or exact-revision review note is selected; all actual appointments remain pending."),
         ("draft", "Drafting Circle remits proposed; review not recorded", "unresolved",
          "The fictional Drafting Circle proposes service, data, security and scientific responsibilities. The separate Review Circle is proposed only; no exact-revision teaching review note is assumed."),
         ("separate", "Separate Review Circle note at teaching-revision-A", "illustrated",
          "A fictional Review Circle note records the discussion scope, qualitative rationale and synthetic-only boundary at teaching-revision-A. Its assumed remit and competence are stated, it has no drafting or delivery role, and overlap requires disclosure, recusal and replacement. This is an invented note, not an authenticated appointment or real acceptance."),
         ("overlap", "Drafting Circle reviews its own work without recusal", "conflict",
          "The hypothetical review role overlaps drafting or delivery and leaves the conflict unresolved. A reviewer label cannot establish independence or competent real review."),
     )),
    ("practical", "Benefit, harm and alternatives",
     "Whether the hoped-for benefit is distinguished from demonstrated usefulness.",
     (
         ("unanswered", "Benefit, harms and alternatives unanswered", "unresolved",
          "The fictional case has no stated benefit, harm, alternative or pause rationale."),
         ("reasoned", "Qualitative rationale; no measured benefit claimed", "illustrated",
          "Clearer category discussion is the hoped-for benefit; definition confusion and staffing overreliance are the harms. Current manual notes and no package are alternatives. Discussion pauses for definition mismatch, missing lineage or a new correction. No numerical threshold, measured improvement or scientific success is asserted."),
         ("benefit-assumed", "Treat the rationale as demonstrated benefit", "conflict",
          "A hoped-for benefit, plausible explanation or locally complete checklist is not evidence of practical improvement. This selection would turn reasoning into an unsupported result."),
     )),
    ("definitions", "Definitions and comparability",
     "Whether the invented category dictionary has compatible meanings or an unresolved splice.",
     (
         ("unresolved", "Guidance label and category meanings unresolved", "unresolved",
          "The broader invented label Guidance is not reconciled with Directions, Form Guidance and Appointment Information. A similar name cannot establish comparability."),
         ("aligned", "Invented dictionary keeps three meanings distinct", "illustrated",
          "Toy-category-dictionary-A defines Directions as wayfinding, Form Guidance as procedural form help and Appointment Information as booking-process information. The broader Guidance label remains separate; no real observation or cross-series splice is introduced."),
         ("mismatch", "Merge Guidance with all three categories", "conflict",
          "The hypothetical merge changes the meaning and scope of the invented categories without a justified reconciliation. Source review or a common label cannot cure this definition mismatch."),
     )),
    ("rights", "Artifact-specific teaching terms",
     "Whether the assumed terms match the recipient and intended use rather than being generalized.",
     (
         ("unresolved", "Artifact-specific terms unanswered", "unresolved",
          "No applicable terms for the fabricated dictionary and issue descriptions are selected. A source being visible or described as public does not supply reuse permission."),
         ("teaching-only", "Invented terms: Planning Circle teaching only", "illustrated",
          "Toy-teaching-terms-A applies only to the invented dictionary and issue descriptions for the Planning Circle discussion, with no onward sharing. It is a fabricated lesson condition that grants no real rights."),
         ("outside-scope", "Assume visibility permits unrestricted reuse", "conflict",
          "The hypothetical reuse exceeds the narrow invented teaching terms and substitutes visibility for applicable permission. No real license, lawful authority or source admission is supplied."),
     )),
    ("vintage", "Original issue and cutoff",
     "Whether the synthetic first issue is retained and the later correction excluded at the earlier origin.",
     (
         ("unknown", "Original availability and issue order unknown", "unresolved",
          "The names toy-first-issue, toy-correction-issue and toy-decision-cutoff do not establish their ordering or original availability."),
         ("first-issue", "First issue before cutoff; later correction excluded", "illustrated",
          "The invented ledger places toy-first-issue before toy-decision-cutoff and toy-correction-issue afterward. Only the first issue is eligible under this fictional origin assumption. The later correction is excluded there and both issues are retained; no authentic historical bytes or official release evidence exist in the lesson."),
         ("correction-backfill", "Backfill the later correction at the earlier cutoff", "conflict",
          "Toy-correction-issue is described as published after toy-decision-cutoff. Selecting it for that earlier origin contradicts the invented availability order, leaks later information and replaces rather than preserves the original view."),
     )),
    ("source_review", "Source-review remit and independence",
     "Whether a fictional source note accounts for the selected definitions, terms and issue lineage.",
     (
         ("unreviewed", "Source dependencies not covered by a review note", "unresolved",
          "No fictional source-review note covers the exact dictionary, teaching terms and original-issue lineage."),
         ("separate", "Separate Review Circle note covers the toy lineage", "illustrated",
          "A fictional separate Review Circle source note at teaching-revision-A records the invented dictionary, narrow teaching terms and first-issue/correction ordering in toy-source-ledger-A. Its assumed remit and competence, no drafting or delivery role, and conflict-recusal conditions are explicit. The note is not authentic source evidence, real admission or executed validation."),
         ("overlap", "Data drafter self-reviews the source claim", "conflict",
          "The hypothetical source reviewer also drafted the claim and has no recusal or replacement. The lesson cannot treat a matching ledger or reviewer label as independent source qualification."),
     )),
    ("protected_scope", "Protected scope and disclosure history",
     "Whether the lesson stays synthetic-only or assumes an unsupported protected-data extension.",
     (
         ("unknown", "Protected scope and disclosure history unanswered", "unresolved",
          "The intended protected scope and prior-disclosure position are not selected. Unknown history cannot be treated as unused permission or allowance."),
         ("synthetic-only", "Invented category descriptions; no privacy guarantee", "illustrated",
          "Only invented category-period descriptions are in scope, with no people, households, protected records or linkage. No privacy guarantee, allowance or protected-data permission is claimed. Unknown history blocks an extension beyond the lesson."),
         ("protected-extension", "Extend the toy record to protected-data use", "conflict",
          "Synthetic descriptions and an invented source chronology establish neither lawful protected-data authority nor authoritative cumulative disclosure history. The extension has no supported protected unit, guarantee or allowance."),
     )),
    ("custody", "Custody and delivery-route scope",
     "Whether a narrow teaching route is distinguished from independent custody and all-route control.",
     (
         ("unmapped", "Custodian and teaching route unanswered", "unresolved",
          "No fictional custody responsibility or recipient route is described; no authoritative current-state account is supplied."),
         ("teaching-route", "Drafting Circle custody; one read-only teaching route", "illustrated",
          "The fictional Drafting Circle data remit keeps the teaching note and ledger; the Planning Circle reads one static discussion copy. This describes a narrow lesson route, not independent administration or actual all-route coverage. Retained or downloaded recipient copies are not promised to be revoked."),
         ("all-routes-assumed", "Treat one local record as control over every copy", "conflict",
          "A local index or one teaching route cannot demonstrate independent custody, authoritative current state or capture and enforcement across every actual delivery route. It cannot revoke copies already retained by recipients."),
     )),
    ("operations", "Operations and reassessment",
     "Whether stewardship and stop questions are distinguished from measured operational performance.",
     (
         ("unplanned", "Stewardship, stop and retirement questions unanswered", "unresolved",
          "No fictional stewardship, correction pause or lesson-retirement boundary is selected."),
         ("teaching-stewardship", "Static session; steward and correction pause described", "illustrated",
          "The Drafting Circle stewards a static internal Planning Circle session. Definition mismatch, missing lineage, toy-correction-issue or a package, purpose or recipient change pauses discussion for renewed review. Lesson-only retirement reasoning never deletes real evidence. No workload, cost, recovery exercise or service commitment is demonstrated."),
         ("deployment-assumed", "Treat the plan as proven deployment and recovery", "conflict",
          "A written stewardship plan is not an exercised service, measured workload, accepted operating objective, proven recovery capability or qualified identity/build/isolation environment."),
     )),
    ("pilot", "Pilot and handover boundary",
     "Whether teaching handover is kept separate from authorized operational admission.",
     (
         ("unplanned", "Handover prerequisites unanswered", "unresolved",
          "No fictional teaching-handover checklist or later-pilot prerequisite boundary is selected."),
         ("teaching-handover", "Teaching handover only; operational gate held", "illustrated",
          "The fictional handover note permits only reading the lesson and lists the authentic prerequisites still absent. There is no operational use, pilot, accepted agency gate or model delivery. Aligned invented choices cannot supply independent real acceptance."),
         ("pilot-assumed", "Treat the toy checklist as permission to start a pilot", "conflict",
          "An illustrated checklist, local configuration or fictional Review Circle note cannot authorize a real pilot, admit a model or supply attributable independent acceptance."),
     )),
    ("governance", "Governance and exact-revision index",
     "Whether an invented index is distinguished from authentic current publication and governance receipts.",
     (
         ("unindexed", "Review and governance receipt categories unanswered", "unresolved",
          "No fictional exact-revision teaching index or list of missing authentic governance receipts is selected."),
         ("teaching-index", "Index teaching-revision-A; authentic receipts absent", "illustrated",
          "The invented index binds the teaching note and toy-source-ledger-A to teaching-revision-A and explicitly lists missing authentic appointments, review, publication and governance receipts. It proves no actual publication, merge, current remote state, signature or agency decision."),
         ("authority-assumed", "Treat an index or download as agency authority", "conflict",
          "A locally consistent index, hash, download or fictional role cannot authenticate an agency decision, current publication event or independent governance acceptance. All actual authority remains pending."),
     )),
)

CONTROL_KEYS = tuple(row[0] for row in _CONTROL_DATA)
CONTROL_OPTIONS = tuple(
    {"key": key, "label": label, "description": description,
     "options": tuple((option[0], option[1]) for option in options)}
    for key, label, description, options in _CONTROL_DATA
)
_CONTROL_INDEX = {row[0]: row for row in _CONTROL_DATA}
_OPTION_INDEX = {row[0]: {option[0]: option for option in row[3]}
                 for row in _CONTROL_DATA}
_START = ("unanswered", "unanswered", "unanswered", "unresolved", "unresolved",
          "unknown", "unreviewed", "unknown", "unmapped", "unplanned",
          "unplanned", "unindexed")
_DRAFT = ("discussion", "draft", "reasoned", "unresolved", "unresolved",
          "unknown", "unreviewed", "synthetic-only", "unmapped", "unplanned",
          "unplanned", "unindexed")
_REVIEWED = ("discussion", "separate", "reasoned", "unresolved", "unresolved",
             "unknown", "unreviewed", "synthetic-only", "unmapped", "unplanned",
             "unplanned", "unindexed")
_TRACEABLE = ("discussion", "separate", "reasoned", "aligned", "teaching-only",
              "first-issue", "separate", "synthetic-only", "unmapped",
              "unplanned", "unplanned", "unindexed")
_WORKED = ("discussion", "separate", "reasoned", "aligned", "teaching-only",
           "first-issue", "separate", "synthetic-only", "teaching-route",
           "teaching-stewardship", "teaching-handover", "teaching-index")
_PRESET_ROWS = tuple(zip(PRESET_IDS, (_START, _DRAFT, _REVIEWED, _TRACEABLE, _WORKED)))
_PRESET_INDEX = dict(_PRESET_ROWS)
_PRESET_TITLES = dict(PRESET_OPTIONS)

_GAPS = (
    ("G01", "Scope, appointments and accountable remits",
     ("purpose", "decision_review", "protected_scope"),
     "A defined discussion purpose, recipient boundary and separated fictional responsibilities explain what could be reviewed. A source ledger cannot appoint people or widen a purpose.",
     "Attributable real scope decisions, authenticated core appointments, accepted remits, delegation limits and exact-revision governance review."),
    ("G02", "Prospective practical criteria",
     ("purpose", "practical", "decision_review"),
     "Benefit, harms, alternatives and pause conditions must fit the intended decision before an outcome is interpreted. Qualitative reasoning remains distinct from demonstrated improvement.",
     "Accountable prospective practical criteria, justified benefit and harm rationale, credible alternatives and independent exact-revision review; any practical acceptance decision remains pending."),
    ("G03", "Definitions, terms and source eligibility",
     ("definitions", "rights", "source_review"),
     "Compatible category meanings, applicable artifact-specific terms and a defensible review remit are separate prerequisites. Agreement in one cannot repair a contradiction in another.",
     "Authentic source definitions and applicable artifact-specific reuse evidence, resolved discrepancies, independent eligibility review and accountable source admission."),
    ("G04", "Original vintages and release lineage",
     ("vintage", "definitions", "source_review"),
     "An earlier-origin claim requires the issue actually available then. A later correction remains separate, and unknown original availability is unresolved rather than silently eligible.",
     "Authentic original bytes, actual release evidence with adequate precision, traceable revisions and independent qualification for each value and origin."),
    ("G05", "Preserved adverse finding and distinct later claim",
     ("purpose", "practical", "definitions", "rights", "vintage", "decision_review"),
     "Toy-planning-package-A is a static teaching note with no empirical performance claim. No configuration can change the real sealed fail result or twelve unsupported null findings; a distinct later scientific proposal would need separate prospective evidence.",
     "Preserved original adverse findings and, for any distinct later claim, a justified separately identified proposal, eligible evidence, prospective criteria and independent review. No replacement result is supplied."),
    ("G06", "Validation and limits of inference",
     ("purpose", "definitions", "vintage", "source_review", "protected_scope"),
     "Invented issue ordering can illustrate eligibility reasoning but is never untouched target-setting validation. Future, population and person-level validity are not demonstrated by any lesson configuration.",
     "Eligible target-setting validation, prior-knowledge and dependence analysis, justified selection and inference assumptions and independent review. No validation result is supplied."),
    ("G07", "Protected scope and disclosure account",
     ("protected_scope", "purpose", "rights", "decision_review"),
     "A synthetic-only teaching boundary illustrates restraint, not a privacy guarantee. An invented source chronology is not an authoritative cumulative disclosure account or lawful protected-data permission.",
     "Defined real protected scope and contributions, lawful authority, recipient conditions, authoritative cumulative disclosure history and accountable review."),
    ("G08", "Identity, build provenance and isolation",
     ("protected_scope", "custody", "operations"),
     "The configured package is a static note, not a qualified executable or environment. Source traceability, role labels and operational plans demonstrate no actual identity, build chain, worker isolation or deployed control.",
     "Accepted actual identity and build provenance, worker isolation and exact-environment evidence with accountable infrastructure decisions."),
    ("G09", "Independent custody and delivery-route coverage",
     ("custody", "rights", "source_review"),
     "One fictional read-only route can be described without claiming independent administration or complete real route coverage. Neither a source ledger nor local consistency supplies authoritative current state or revocation of recipient copies.",
     "Independent actual custody, authoritative current state and demonstrated capture or enforcement across every actual delivery route, with retained-copy limitations."),
    ("G10", "Operations, recovery and retirement",
     ("operations", "purpose", "practical"),
     "Stewardship and correction-triggered reconsideration are reasons to plan, not workload measurements, exercised recovery, accepted service objectives or authority to delete preserved records.",
     "Accepted workload and cost evidence, operating owners, justified service and recovery objectives, actual exercises where required and retirement obligations."),
    ("G11", "Independent acceptance, pilot and handover",
     ("pilot", "operations", "decision_review", "governance"),
     "A teaching handover lists authentic prerequisites and keeps the operational gate held. Even internally aligned invented decisions and source assumptions cannot authorize a pilot, start model delivery or supply independent real acceptance.",
     "Qualified independent real acceptance, authentic prerequisite evidence, an authorized restricted pilot with entry and exit decisions and attributable handover."),
    ("G12", "Current governance and publication receipts",
     ("governance", "decision_review", "source_review"),
     "An invented exact-revision index can expose missing receipts. It demonstrates no actual publication or merge, current remote state, independent external review, signature or agency acceptance.",
     "Current authentic publication and independent review receipts, attributable governance decisions, exact-revision reconciliation and current hosted or remote controls where required."),
)
_STATE_LABELS = {
    "illustration_incomplete": "Lesson assumptions unresolved",
    "illustration_coherent": "Lesson assumptions aligned",
    "illustration_conflict": "Lesson assumptions conflict",
}
_CASE = {
    "office": "Fictional Service Planning Office",
    "purpose": "Information Desk Capacity Review: human discussion of invented information-desk categories only.",
    "package": "toy-planning-package-A at teaching-revision-A; a static read-only planning note and dictionary, with no executable candidate or fitted model.",
    "categories": "Directions means wayfinding; Form Guidance means procedural form help; Appointment Information means booking-process information. Guidance remains a separate broader label.",
    "recipient": "Fictional Planning Circle; read-only teaching discussion, no onward sharing, individual eligibility, ranking or automated decisions.",
    "roles": "Fictional Drafting Circle service, data, security and scientific remits; separate fictional Review Circle with stated remit and assumed competence, no drafting or delivery role, and disclosure, recusal and replacement for overlap.",
    "source_chain": "Invented toy-first-issue precedes toy-decision-cutoff; toy-correction-issue follows and is excluded at that earlier origin. Both remain retained.",
    "evidence_boundary": "No authentic source records, actual agency decisions, performance results, protected-data permission, operational exercises or current governance receipts are included.",
}
_GUIDANCE = {
    "do": [
        "Change one assumption, apply it and read the cited conditions in each affected checklist; then try a mixed configuration to expose dependencies.",
        "Distinguish a concrete fictional choice, a reasoned plan and authentic demonstrated evidence. Read every missing-real-receipt statement even when lesson assumptions align.",
        "Keep the first issue and later correction separate. An issue after the fictional cutoff remains excluded at the earlier origin.",
        "Check definitions, artifact-specific terms, recipient limits and reviewer separation together. A plausible purpose or review note cannot repair a source conflict.",
        "Treat the worked preset as a consistent teaching boundary, including held operational gates and unresolved empirical checkpoints.",
    ],
    "dont": [
        "Do not interpret an aligned lesson, selected option or downloaded configuration as closure, agency approval, scientific acceptance or authority to act.",
        "Do not copy the synthetic configuration into real intake, claim authentic source records, invent appointments or signatures, or imply that a benchmark or validation was run.",
        "Do not infer measured benefit, privacy protection, qualified infrastructure, independent custody, exercised recovery, pilot permission or current publication from a plan or source ledger.",
        "Do not backfill a later correction, silently merge incompatible category meanings, generalize narrow terms or promise to revoke already retained recipient copies.",
    ],
    "next_questions": [
        "Which selected assumption is a decision an accountable real owner must make, and which requires authentic evidence that no local configuration can create?",
        "If purpose, recipient, package or source issue changes, which earlier rationale and review remit must be reconsidered?",
        "What independent exact-revision review, source provenance and actual operational or governance receipt would be needed before real use could be considered?",
    ],
}


def _preset_id(preset_id):
    if preset_id is None:
        return DEFAULT_PRESET_ID
    if type(preset_id) is not str or preset_id not in _PRESET_INDEX:
        raise ValueError("Unknown fictional tutorial preset")
    return preset_id


def preset_assumptions(id=None):
    """Return a fresh finite assumption map for a fixed teaching preset."""
    chosen = _preset_id(id)
    return dict(zip(CONTROL_KEYS, _PRESET_INDEX[chosen]))


DEFAULT_ASSUMPTIONS = preset_assumptions()


def normalize_assumptions(values=None, preset_id=None):
    """Validate a partial strict-dict selection and overlay a finite preset.

    Free text, unknown keys, non-string values, subclasses and unknown options
    are refused rather than reflected or silently interpreted.
    """
    selected = preset_assumptions(preset_id)
    if values is None:
        return selected
    if type(values) is not dict:
        raise ValueError("Fictional assumptions must be a finite object")
    for key, value in values.items():
        if type(key) is not str or key not in _OPTION_INDEX:
            raise ValueError("Unknown fictional assumption")
        if type(value) is not str or value not in _OPTION_INDEX[key]:
            raise ValueError("Unknown fictional assumption choice")
        selected[key] = value
    return selected


def _control_row(key, values):
    option = _OPTION_INDEX[key][values[key]]
    return {
        "factor": _CONTROL_INDEX[key][1],
        "control_key": key,
        "value": values[key],
        "state": option[2],
        "reason": option[3],
    }


def _dependent_row(factor, keys, values, state, reason):
    return {
        "factor": factor,
        "control_key": "+".join(keys),
        "value": "; ".join(key + "=" + values[key] for key in keys),
        "state": state,
        "reason": reason,
    }


def _dependencies(gap_id, values):
    rows = []
    # Contradictions between invented choices are not judgments about actual
    # reviewers and cannot substitute for authentic evidence.
    if values["decision_review"] == "separate":
        for key, expected, gap_ids, reason in (
            ("purpose", "discussion", ("G01", "G02", "G07", "G11", "G12"),
             "The selected fictional exact-revision note records the discussion-only purpose, but the selected purpose is different. The note cannot cover an unchosen or widened scope without reconsideration."),
            ("practical", "reasoned", ("G02", "G05", "G11"),
             "The selected fictional decision note records a qualitative rationale without a measured-benefit claim, but the selected practical condition is different. The note cannot replace an absent rationale or turn it into demonstrated benefit."),
            ("protected_scope", "synthetic-only", ("G01", "G07", "G08", "G11"),
             "The selected fictional decision note records a synthetic-only boundary, but the selected protected scope is different. The note cannot establish an unknown boundary or authorize a protected-data extension."),
        ):
            if gap_id in gap_ids and values[key] != expected:
                rows.append(_dependent_row(
                    "Decision-note dependency: " + _CONTROL_INDEX[key][1],
                    ("decision_review", key), values, "conflict",
                    reason + " Selected option: " + _OPTION_INDEX[key][values[key]][1] + "."))
    if values["source_review"] == "separate":
        for key, expected, gap_ids, reason in (
            ("definitions", "aligned", ("G03", "G04", "G06", "G09", "G12"),
             "The selected fictional source note records the distinct invented dictionary meanings, but the selected definition condition is different. Unresolved meaning or a merged Guidance label contradicts that exact toy-source account."),
            ("rights", "teaching-only", ("G03", "G07", "G09", "G11", "G12"),
             "The selected fictional source note records narrow Planning Circle teaching terms, but the selected rights condition is different. The note cannot supply absent terms or widen their scope."),
            ("vintage", "first-issue", ("G04", "G05", "G06", "G09", "G11", "G12"),
             "The selected fictional source note records the first issue before the cutoff and the correction afterward and excluded there, but the selected availability condition is different. Unknown lineage or backfilling the later correction contradicts that exact account."),
        ):
            if gap_id in gap_ids and values[key] != expected:
                rows.append(_dependent_row(
                    "Source-note dependency: " + _CONTROL_INDEX[key][1],
                    ("source_review", key), values, "conflict",
                    reason + " Selected option: " + _OPTION_INDEX[key][values[key]][1] + "."))
    if values["rights"] == "teaching-only":
        for key, incompatible, reason in (
            ("purpose", "individual-use",
             "Planning Circle teaching-only terms cannot cover selected individual decisions or onward sharing."),
            ("protected_scope", "protected-extension",
             "The invented dictionary's narrow teaching terms do not cover a selected extension to protected-data use."),
            ("operations", "deployment-assumed",
             "Planning Circle teaching-only terms do not establish permission or qualification for the selected assumed deployment."),
            ("pilot", "pilot-assumed",
             "Planning Circle teaching-only terms cannot authorize the selected assumed real pilot."),
        ):
            if gap_id in ("G03", "G07", "G09", "G11") and values[key] == incompatible:
                rows.append(_dependent_row("Use and terms dependency",
                                           ("rights", key), values, "conflict", reason))
    if values["pilot"] == "teaching-handover" and gap_id == "G11":
        adverse = tuple(key for key in CONTROL_KEYS if values[key] in
                        ("individual-use", "overlap", "benefit-assumed", "mismatch",
                         "outside-scope", "correction-backfill", "protected-extension",
                         "all-routes-assumed", "deployment-assumed", "authority-assumed"))
        if adverse:
            rows.append(_dependent_row(
                "Handover must disclose selected conflicts", ("pilot",) + adverse,
                values, "conflict",
                "The teaching handover remains non-operational, but the simultaneous selected conflicts must be retained in its prerequisite list. A handover label cannot smooth them into a coherent or authorized package."))
        unresolved = tuple(key for key in
                           ("purpose", "definitions", "rights", "vintage", "source_review")
                           if _OPTION_INDEX[key][values[key]][2] == "unresolved")
        if unresolved:
            rows.append(_dependent_row(
                "Handover has unresolved teaching prerequisites",
                ("pilot",) + unresolved, values, "unresolved",
                "The selected teaching handover is a held gate. Its source and scope prerequisites remain unanswered in this mixed configuration; a list of requirements is not evidence that they are supplied."))
    return rows


def _gap_row(spec, values):
    identifier, title, dependencies, explanation, receipt = spec
    rows = [_control_row(key, values) for key in dependencies]
    rows.extend(_dependencies(identifier, values))
    if identifier in ("G05", "G06"):
        rows.append({
            "factor": "Empirical evidence remains absent",
            "control_key": "empirical_checkpoint",
            "value": "not_demonstrated",
            "state": "unresolved",
            "reason": (
                "No benchmark, fit, draw, replay, eligible validation or favorable scientific result is supplied by any selection. The real sealed fail result and twelve unsupported null findings remain unchanged. A coherent teaching plan cannot demonstrate a new scientific claim."
                if identifier == "G05" else
                "The fabricated dictionary and source chronology are not untouched target-setting validation. Prior knowledge, dependence, selection and inference assumptions require authentic evidence and independent review. No future, population or person-level validity is demonstrated."
            ),
        })
    lesson_states = tuple(row["state"] for row in rows)
    if "conflict" in lesson_states:
        state = "illustration_conflict"
        transition = "Selected fictional assumptions conflict; the cited contradiction must remain visible."
    elif "unresolved" in lesson_states:
        state = "illustration_incomplete"
        transition = "One or more lesson assumptions remain unresolved; no missing condition is silently filled."
    else:
        state = "illustration_coherent"
        transition = "The selected teaching conditions align within their stated fictional boundary; this establishes no real requirement."
    triggers = [row["factor"] + ": " + row["reason"]
                for row in rows if row["state"] != "illustrated"]
    if not triggers:
        triggers = [
            "Only the selected invented conditions align. The authentic receipt remains not supplied and the real gap remains open."
        ]
    rows.append({
        "factor": "Authentic real receipt",
        "control_key": "real_receipt",
        "value": "not_supplied",
        "state": "authentic_receipt_required",
        "reason": receipt,
    })
    return {
        "id": identifier,
        "title": title,
        "state": state,
        "label": _STATE_LABELS[state],
        "reason": transition + " " + explanation,
        "dependencies": list(dependencies),
        "triggers": triggers,
        "checklist": rows,
        "real_gap_status": "open",
        "real_receipt_status": "not_supplied",
        "authentic_receipt_supplied": False,
        "demonstrated_result": False,
        "real_receipt_needed": receipt,
    }


def evaluate_assumptions(values=None, preset_id=None):
    """Return fresh fictional conditions, dependency effects and real boundaries.

    Coherence describes internal teaching assumptions only. It never denotes
    completed evidence, scientific performance or a real gap state.
    """
    chosen = _preset_id(preset_id)
    assumptions = normalize_assumptions(values, chosen)
    baseline = preset_assumptions(chosen)
    selected = []
    for key, label, description, options in _CONTROL_DATA:
        option = _OPTION_INDEX[key][assumptions[key]]
        selected.append({
            "key": key,
            "label": label,
            "description": description,
            "value": option[0],
            "value_label": option[1],
            "lesson_state": option[2],
            "reason": option[3],
        })
    return {
        "schema": SCHEMA,
        "preset_id": chosen,
        "preset_title": _PRESET_TITLES[chosen],
        "modified": assumptions != baseline,
        "assumptions": assumptions,
        "changed_controls": [key for key in CONTROL_KEYS
                             if assumptions[key] != baseline[key]],
        "title": "Interactive fictional decision and source-evidence lesson",
        "summary": (
            "Change finite fictional decisions and source assumptions to inspect their reasoned effects on twelve teaching checklists. Choices are independent; mixed selections can expose unresolved prerequisites or contradictions. No configuration supplies authentic records, changes actual agency decisions or closes a real gap."
        ),
        "fictional_example": True,
        "public_synthetic_only": True,
        "authentic_source_records_included": False,
        "real_agency_decisions": "pending",
        "original_substantive_gaps_closed": 0,
        "original_substantive_gaps_open": 12,
        "authorization_effect": "none",
        "benchmark_executed": False,
        "case": deepcopy(_CASE),
        "selected_controls": selected,
        "simulated": {
            "gap_checklists": [_gap_row(spec, assumptions) for spec in _GAPS],
            "scientific_result": "not_demonstrated",
            "operational_evidence": "not_supplied",
            "agency_acceptance": "pending",
        },
        "guidance": deepcopy(_GUIDANCE),
    }


def configuration_json(values=None, preset_id=None):
    """Return deterministic canonical UTF-8 JSON for the distinct teaching schema."""
    return (json.dumps(evaluate_assumptions(values, preset_id),
                       ensure_ascii=False, allow_nan=False, sort_keys=True,
                       separators=(",", ":")) + "\n").encode("utf-8")
