"""Portable fictional learning pages, independent of captured project evidence.

This mode never constructs a captured snapshot, verifies a project input or
imports a scientific application. The unchanged finite lesson renderers supply
controls and explanations; this module removes their historical project-state
wording from the separately labelled public presentation.
"""
from __future__ import annotations

from dataclasses import dataclass
from html import escape
import json
import re
from urllib.parse import parse_qs, urlsplit

from .guided_comparison import STEP_IDS
from .guided_practice import EXERCISE_IDS
from .interactive_tutorial import CONTROL_OPTIONS, PRESET_IDS, configuration_json, evaluate_assumptions
from .practice_saves import SAVES_CSP
from .protocol import ERROR_BODIES
from .tutorial import SCENARIO_IDS, scenario_json
from .tutorial_comparison import comparison_json
from .views import (
    STYLES, comparison_tutorial_page, guided_comparison_page,
    guided_practice_page, interactive_tutorial_page, practice_saves_page,
    tutorial_page,
)


@dataclass(frozen=True, slots=True)
class DemoConfig:
    """Select public fictional lessons; there are no evidence paths or pins."""


STATUS = {
    "schema": "mra-portable-teaching-status/1",
    "mode": "fictional_demo",
    "project_evidence_loaded": False,
    "captured_integrity_claimed": False,
    "agency_decisions": "pending",
    "authorization_effect": "none",
    "benchmark_executed": False,
}
BANNER = (
    '<aside class="notice" aria-label="Fictional demonstration context">'
    '<p><a href="/">Return to the MRA application</a></p>'
    '<p><strong>Fictional learning mode. No project evidence loaded.</strong> '
    'Agency decisions remain pending. No authorization or real gap state is '
    'established by this demonstration.</p></aside>'
)
_UNAVAILABLE = (
    b"Project evidence is not configured in fictional learning mode. "
    b"No captured findings, intake, review packet, integrity check or project "
    b"download is available. Agency decisions remain pending.\n"
)
_CONTROLS = {row["key"]: tuple(option[0] for option in row["options"])
             for row in CONTROL_OPTIONS}
_PAIRED = {side + "_" + key: values for side in ("left", "right")
           for key, values in _CONTROLS.items()}
_GAPS = tuple(f"G{number:02d}" for number in range(1, 13))
_LINKS = (
    ("/", "Readiness overview"), ("/remediation", "Gap checklists"),
    ("/evidence", "Evidence guide"), ("/tutorial", "Tutorial examples"),
    ("/tutorial-lab", "Interactive tutorial"), ("/tutorial-compare", "Compare demos"),
    ("/tutorial-walkthrough", "Guided tutorial"), ("/tutorial-practice", "Guided practice"),
    ("/practice-saves", "Saved demos"), ("/local-status", "Local mode"),
)
_CAPTURE_ROUTES = frozenset((
    "/findings", "/intake", "/intake-guide", "/review-handoff",
    "/api/readiness", "/api/gaps", "/api/work-packages", "/api/response-template",
    "/api/evidence", "/api/findings", "/api/intake-report", "/api/intake-checklist",
    "/api/review-handoff/archive", "/api/review-handoff/manifest", "/api/review-handoff/readme",
))


def _portable_text(text):
    """Project static historical wording into an explicitly unassessed context.

    This affects portable presentation only. The finite choices, dependency
    reasoning and original captured renderers remain unchanged.
    """
    replacements = (
        ("Preserved real findings remain unchanged.", "No project findings are loaded."),
        ("The recorded research verdict remains fail, with eighteen comparison rows and twelve unsupported null findings.",
         "This demonstration supplies no measured scientific result."),
        ("The recorded verdict remains fail, with eighteen comparison rows and twelve unsupported null findings.",
         "This demonstration supplies no measured scientific result."),
        ("The preserved verdict remains fail, with eighteen comparison rows and twelve unsupported null findings.",
         "This demonstration supplies no measured scientific result."),
        ("No configuration can change the real sealed fail result or twelve unsupported null findings;",
         "No configuration establishes an empirical result;"),
        ("The real sealed fail result and twelve unsupported null findings remain unchanged.",
         "No project findings are loaded or assessed here."),
        ("preserves the real fail result and twelve null findings", "leaves any separately held findings unchanged"),
        ("preserves the real adverse and unsupported findings", "leaves any separately held findings unchanged"),
        ("the original adverse finding remains preserved", "any original adverse finding must remain preserved"),
        ("The original adverse finding remains preserved", "Any original adverse finding must remain preserved"),
        ("the real unsupported findings", "any separately held unsupported findings"),
        ("the real adverse and unsupported findings", "any separately held adverse and unsupported findings"),
        ("the sealed adverse result or unsupported findings", "any separately held adverse result or unsupported findings"),
        ("the current captured-input checks", "the current finite lesson rules"),
        ("the captured agency record", "any separately held agency record"),
        ("the captured record", "any separately held project record"),
        ("the captured gaps", "any separately held project gaps"),
        ("Authentic receipts remain not supplied and the actual gap remains open on both sides.",
         "Authentic receipts are not supplied by either fictional configuration; no actual gap state is assessed."),
        ("The platform's agency record stays read-only; no benchmark runs.", "No agency record is loaded or changed; no benchmark runs."),
        ("the real captured record", "any separately held project record"),
        ("agency-record views", "learning views"),
        ("Real substantive gaps: twelve open", "Real gap state: not assessed"),
        ("Original substantive gaps closed: none", "Real gap state: not assessed"),
        ("Real gaps: twelve open", "Real gap state: not assessed"),
        ("Return to the captured open gaps", "Return to the teaching checklists"),
        ("Read the captured open gaps", "Read the teaching checklists"),
    )
    for original, replacement in replacements:
        text = text.replace(original, replacement)
    text = re.sub(r"[Aa]ll (?:twelve|12) (?:real |substantive )?gaps remain open",
                  "No real gap state is assessed in this demonstration", text)
    text = re.sub(r"[Rr]eal G\d{2} remains open on both sides\.",
                  "Neither side establishes a real gap state.", text)
    text = re.sub(r"[Rr]eal (G\d{2}) remains open", r"\1 real status is not assessed", text)
    text = text.replace("the real gap remains open", "no real gap state is established")
    text = text.replace("; No real gap", "; no real gap").replace("and No real gap", "and no real gap")
    text = re.sub(r"Read the captured (G\d{2}) requirements, still open",
                  r"Read teaching checklist \1", text)
    return text


def _project_lesson(value):
    """Copy lesson data without metadata asserting historical project state."""
    if isinstance(value, dict):
        omitted = {"schema", "original_substantive_gaps_open", "original_substantive_gaps_closed", "real_gap_status"}
        return {key: _project_lesson(item) for key, item in value.items() if key not in omitted}
    if isinstance(value, list):
        return [_project_lesson(item) for item in value]
    return _portable_text(value) if isinstance(value, str) else value


def _lesson_json(raw):
    result = {
        "schema": "mra-portable-fictional-lesson/1", "mode": "fictional_demo",
        "project_evidence_loaded": False, "real_gap_state": "not_assessed",
        "agency_decisions": "pending", "authorization_effect": "none",
        "benchmark_executed": False, "lesson": _project_lesson(json.loads(raw)),
    }
    return (json.dumps(result, ensure_ascii=False, allow_nan=False, sort_keys=True,
                       separators=(",", ":")) + "\n").encode("utf-8")


def _shell(title, body, path):
    navigation = "".join(
        '<a href="' + target + '"' + (' aria-current="page"' if target == path else '') + '>' + label + '</a>'
        for target, label in _LINKS)
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<title>' + escape(title) + ' | MRA learning</title>'
            '<link rel="stylesheet" href="/assets/style.css"></head><body>'
            '<a class="skip" href="#main">Skip to content</a>'
            '<header class="site-header"><div class="brand"><strong>MRA readiness &amp; learning</strong></div>'
            '<span class="local-label">Fictional demonstration</span></header><div class="shell">'
            '<div class="hero"><p class="eyebrow">Public fictional examples</p><h1>' + escape(title) + '</h1>'
            '<p>Explore decisions, source assumptions and the reasons behind checklist changes.</p></div>'
            '<nav aria-label="Readiness and learning">' + navigation + '</nav>'
            '<main id="main">' + _portable_text(body) + '</main>'
            '<footer><span>General advisory book separate · Project evidence not loaded</span>'
            '<span>Agency decisions pending · Authorization effect: none</span></footer>'
            '</div></body></html>').encode("utf-8")


def _overview():
    return ('<section><h2>Reason through readiness before making a claim</h2>'
            '<p>This portable workspace teaches how scope, decisions, evidence and dependencies fit together. '
            'Its twelve checklist identifiers organise fictional lessons; they are not a report of any organisation’s open or closed gaps.</p>'
            '<div class="two-col"><article class="panel"><h3>Explore and compare</h3>'
            '<p>Load a worked example, change a decision or source assumption, and compare the resulting checkpoint reasons. '
            'An internally coherent lesson does not supply authentic evidence or demonstrate performance.</p>'
            '<p><a href="/tutorial-walkthrough">Start the guided tutorial</a></p></article>'
            '<article class="panel"><h3>Practise and revisit</h3><p>Use guided practice to inspect a choice, '
            'then save its finite configuration in your browser. Reload two saved configurations to compare their assumptions.</p>'
            '<p><a href="/tutorial-practice">Open guided practice</a> · <a href="/practice-saves">Open saved demos</a></p></article></div>'
            '<h3>Keep decisions attributable</h3><p>Real scope, appointments, acceptance criteria and authority need '
            'accountable decisions and authentic evidence. They remain pending here. No project results, evidence files or '
            'captured integrity checks are loaded in this mode.</p></section>')


def _remediation(gap=None):
    rows = evaluate_assumptions()["simulated"]["gap_checklists"]
    cards = []
    for row in rows:
        if gap is not None and row["id"] != gap:
            continue
        identifier = row["id"]
        cards.append('<article class="panel" id="' + identifier + '"><h3>' + identifier + ' · ' + escape(row["title"]) + '</h3>'
                     '<p>' + escape(_portable_text(row["real_receipt_needed"])) + '</p>'
                     '<p><a href="/tutorial-lab#lab-' + identifier + '">Explore the fictional checkpoint reasons</a></p></article>')
    return ('<section><h2>Teaching checklist guide</h2><p>These topics explain the evidence a real review may require. '
            'No project checklist status, accepted receipt, appointment or closure is asserted. Use the interactive lesson '
            'to see dependencies and conflicts caused by the selected fictional assumptions.</p>' + ''.join(cards) + '</section>')


def _evidence():
    return ('<section><h2>How to reason about evidence</h2><p>No authentic project source records are loaded. '
            'The source notes, categories and issue chronology in the tutorials are invented teaching material.</p>'
            '<div class="two-col"><article class="panel"><h3>Ask separate questions</h3><ul>'
            '<li>Can the exact source and revision be identified?</li><li>Was it available at the relevant time?</li>'
            '<li>Do definitions and intended uses match?</li><li>Do the applicable terms permit the proposed use?</li>'
            '<li>Is custody traceable and review sufficiently independent?</li></ul></article>'
            '<article class="panel"><h3>Keep the limits visible</h3><p>A description, link or matching digest alone '
            'does not authenticate a source or establish permission, independence or agency acceptance. '
            'A later correction does not prove what was available earlier. Record missing evidence and unresolved '
            'assumptions separately from decisions.</p></article></div>'
            '<p><a href="/tutorial-lab">Explore source assumptions</a> · '
            '<a href="/tutorial-compare">Compare two fictional source accounts</a></p></section>')


def _query(path):
    target = urlsplit(path)
    if target.scheme or target.netloc or target.fragment or "%" in target.path or "\\" in target.path:
        raise ValueError("Invalid target")
    name = target.path
    limit = 26 if name in ("/tutorial-compare", "/api/tutorial-comparison") else (13 if name in (
        "/tutorial-lab", "/api/tutorial-lab-config", "/tutorial-practice", "/practice-saves") else 2)
    query = parse_qs(target.query, keep_blank_values=True, strict_parsing=True, max_num_fields=limit)
    if any(len(values) != 1 for values in query.values()):
        raise ValueError("Repeated query")
    if name == "/remediation":
        if set(query) - {"gap"} or query.get("gap", [""])[0] not in ("", *_GAPS):
            raise ValueError("Invalid checklist")
    elif name in ("/tutorial", "/api/tutorial-config"):
        if set(query) - {"scenario"} or ("scenario" in query and query["scenario"][0] not in SCENARIO_IDS):
            raise ValueError("Invalid scenario")
    elif name in ("/tutorial-lab", "/api/tutorial-lab-config"):
        if set(query) - ({"preset"} | set(_CONTROLS)) or ("preset" in query and query["preset"][0] not in PRESET_IDS):
            raise ValueError("Invalid preset")
        if any(key in query and query[key][0] not in values for key, values in _CONTROLS.items()):
            raise ValueError("Invalid assumption")
    elif name == "/practice-saves":
        if query and (set(query) != ({"exercise"} | set(_CONTROLS)) or
                      query["exercise"][0] not in EXERCISE_IDS or
                      any(query[key][0] not in values for key, values in _CONTROLS.items())):
            raise ValueError("Invalid saved demo")
    elif name == "/tutorial-practice":
        if set(query) - ({"exercise"} | set(_CONTROLS)) or ("exercise" in query and query["exercise"][0] not in EXERCISE_IDS):
            raise ValueError("Invalid exercise")
        if any(key in query and query[key][0] not in values for key, values in _CONTROLS.items()):
            raise ValueError("Invalid practice assumption")
    elif name == "/tutorial-walkthrough":
        if set(query) - {"step"} or ("step" in query and query["step"][0] not in STEP_IDS):
            raise ValueError("Invalid step")
    elif name in ("/tutorial-compare", "/api/tutorial-comparison"):
        if set(query) - ({"left_preset", "right_preset"} | set(_PAIRED)):
            raise ValueError("Invalid comparison")
        if any(key in query and query[key][0] not in PRESET_IDS for key in ("left_preset", "right_preset")):
            raise ValueError("Invalid comparison preset")
        if any(key in query and query[key][0] not in values for key, values in _PAIRED.items()):
            raise ValueError("Invalid comparison assumption")
    elif query:
        raise ValueError("Query not accepted")
    return name, query


def dispatch_demo(method, path, headers, port, *, error=None, body_present=False):
    """Dispatch already bounded adapter parts without reading project inputs."""
    from .console_integration import DERIVED_PRACTICE_SAVES_SCRIPT, _response, prefix_html

    def respond(code, raw, mime="text/plain; charset=utf-8", filename=None, csp=None):
        return _response(code, raw, method, mime, filename, csp)

    if error:
        raw = b"Request bodies are not accepted.\n" if body_present and error == 400 else ERROR_BODIES.get(error, b"Local assurance listener rejected.\n")
        return respond(error, raw)
    expected = f"127.0.0.1:{port}"
    hosts, origins = headers.get_all("Host", []), headers.get_all("Origin", [])
    if hosts != [expected] or len(origins) > 1 or (origins and origins != ["http://" + expected]):
        return respond(403, b"Local host or origin rejected.\n")
    if headers.get_all("Expect", []):
        return respond(417, ERROR_BODIES[417])
    if headers.get_all("Transfer-Encoding", []) or headers.get_all("Content-Length", []) not in ([], ["0"]):
        return respond(400, b"Request bodies are not accepted.\n")
    if method not in ("GET", "HEAD"):
        return respond(405, b"Read-only learning workspace: GET and HEAD only.\n")
    try:
        name, query = _query(path)
    except ValueError:
        return respond(400, b"Invalid fictional learning view or filter.\n")
    selected = lambda key: query.get(key, [None])[0]
    choices = lambda side="": {key: query[side + key][0] for key in _CONTROLS if side + key in query}
    if name == "/assets/style.css":
        return respond(200, STYLES.encode("utf-8"), "text/css; charset=utf-8")
    if name == "/assets/practice-saves.js":
        return respond(200, DERIVED_PRACTICE_SAVES_SCRIPT, "text/javascript; charset=utf-8")
    if name == "/api/local-status":
        return respond(200, (json.dumps(STATUS, sort_keys=True, indent=2) + "\n").encode("utf-8"), "application/json; charset=utf-8")
    if name in _CAPTURE_ROUTES:
        return respond(503, _UNAVAILABLE)
    if name == "/api/tutorial-config":
        return respond(200, _lesson_json(scenario_json(selected("scenario"))), "application/json; charset=utf-8", "fictional-tutorial.json")
    if name == "/api/tutorial-lab-config":
        return respond(200, _lesson_json(configuration_json(choices(), selected("preset"))), "application/json; charset=utf-8", "fictional-assumptions.json")
    if name == "/api/tutorial-comparison":
        raw = comparison_json(choices("left_"), choices("right_"), selected("left_preset"), selected("right_preset"))
        return respond(200, _lesson_json(raw), "application/json; charset=utf-8", "fictional-comparison.json")
    csp = None
    if name in ("/", "/readiness"):
        title, body = "Readiness through reasoning", _overview()
    elif name == "/remediation":
        title, body = "Teaching checklists", _remediation(selected("gap") or None)
    elif name == "/evidence":
        title, body = "Evidence reasoning guide", _evidence()
    elif name == "/tutorial":
        title, body = "Tutorial examples", tutorial_page(selected("scenario"), snapshot=None)
    elif name == "/tutorial-lab":
        title, body = "Interactive tutorial", interactive_tutorial_page(choices(), selected("preset"), snapshot=None)
    elif name == "/tutorial-compare":
        title, body = "Compare fictional configurations", comparison_tutorial_page(choices("left_"), choices("right_"), selected("left_preset"), selected("right_preset"), snapshot=None)
    elif name == "/tutorial-walkthrough":
        title, body = "Guided tutorial", guided_comparison_page(selected("step"), snapshot=None)
    elif name == "/tutorial-practice":
        title, body = "Guided practice", guided_practice_page(choices(), selected("exercise"), snapshot=None)
    elif name == "/practice-saves":
        title, body = "Saved demo configurations", practice_saves_page(choices() if query else None, selected("exercise"))
        csp = SAVES_CSP
    elif name == "/local-status":
        title, body = "Current learning mode", (
            '<section><h2>Fictional demonstration mode</h2><p>No project evidence loaded. No captured integrity check is claimed. '
            'No project source paths, intake reports or scientific findings are configured.</p>'
            '<p>Agency decisions remain pending. Authorization effect: none. No benchmark is executed.</p>'
            '<p>Saved demos contain fictional choices in this browser only. Clearing browser storage can remove them; '
            'export a copy before doing so.</p><p><a href="/api/local-status">View mode information as JSON</a></p></section>')
    else:
        return respond(404, b"Unknown fictional learning route.\n")
    raw = prefix_html(_shell(title, body, name), banner=BANNER)
    return respond(200, raw, "text/html; charset=utf-8", csp=csp)


__all__ = ["DemoConfig"]
