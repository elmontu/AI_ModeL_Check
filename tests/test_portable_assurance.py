"""Fresh-checkout teaching UI checks; no captured inputs or scientific execution.

The upstream application is deliberately minimal. Finite JavaScript checks use
in-memory browser storage and Node from PATH, never the real saved-demo library.
"""
from __future__ import annotations

import asyncio
from contextlib import redirect_stderr
import io
import types
from dataclasses import FrozenInstanceError
from html.parser import HTMLParser
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, unquote, urlencode, urlsplit

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, Response
from fastapi.testclient import TestClient
from mra_readiness_dashboard import console_integration as integration
from mra_readiness_dashboard import interactive_tutorial, practice_saves
from mra_readiness_dashboard.configuration import load_readiness_config, SCHEMA
from mra_readiness_dashboard.guided_comparison import STEP_IDS
from mra_readiness_dashboard.guided_practice import EXERCISE_IDS
from mra_rr_continuation import main_assurance_app, console
from mra_rr_continuation.main_assurance_app import (
    MAIN_PAGES, NAV_CSS_PATH, decorate_main_navigation)

PREFIX = "/assurance"
BASE = "http://127.0.0.1:8765"
CANARY = "SYNTHETIC-PRIVATE-INPUT-MUST-NOT-BE-ECHOED"
PAGES = ("", "/", "/readiness", "/remediation", "/evidence", "/tutorial",
         "/tutorial-lab", "/tutorial-compare", "/tutorial-walkthrough",
         "/tutorial-practice", "/practice-saves", "/local-status")
CAPTURED = ("/findings", "/intake", "/intake-guide", "/review-handoff",
            "/api/readiness", "/api/findings", "/api/intake-report",
            "/api/review-handoff/archive")
ORDINARY_CSP = ("default-src 'none'; style-src 'self'; form-action 'self'; "
                "base-uri 'none'; frame-ancestors 'none'; object-src 'none'")
GOOD = {"purpose": "discussion", "decision_review": "separate", "practical": "reasoned",
        "definitions": "aligned", "rights": "teaching-only", "vintage": "first-issue",
        "source_review": "separate", "protected_scope": "synthetic-only",
        "custody": "teaching-route", "operations": "teaching-stewardship",
        "pilot": "teaching-handover", "governance": "teaching-index"}


class Document(HTMLParser):
    def __init__(self, raw):
        super().__init__(convert_charrefs=True)
        self.tags = []
        self.feed(raw.decode() if isinstance(raw, bytes) else raw)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


def upstream():
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    for path in MAIN_PAGES:
        def render():
            return HTMLResponse('<!doctype html><html><head><title>MRA test</title></head>'
                                '<body><nav><a href="/sentinel">Existing</a></nav><main>'
                                '<section id="datasets">Existing datasets</section></main></body></html>')
        app.add_api_route(path, render, methods=["GET", "HEAD"])
    @app.get("/sentinel")
    def sentinel():
        return Response(b"existing-upstream", headers={"X-Upstream": "preserved"})
    return app


def client(configuration=None):
    return TestClient(integration.AssuranceApplication(
        upstream(), integration.DemoConfig() if configuration is None else configuration),
        base_url=BASE, follow_redirects=False)


def raw_request(raw_path=b"/assurance/tutorial", *, query=b"", headers=None,
                method="GET", body=b"", more_body=False, receive_forbidden=False,
                server=("127.0.0.1", 8765), config=None, http_version="1.1"):
    application = integration.AssuranceApplication(
        upstream(), integration.DemoConfig() if config is None else config)
    scope = {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"},
             "http_version": http_version, "method": method, "scheme": "http", "root_path": "",
             "path": unquote(raw_path.decode("latin-1")), "raw_path": raw_path,
             "query_string": query, "headers": headers if headers is not None else
             [(b"host", b"127.0.0.1:8765")], "client": ("127.0.0.1", 50001), "server": server}
    messages = []
    async def receive():
        if receive_forbidden:
            raise AssertionError("Denied request must not read a body")
        return {"type": "http.request", "body": body, "more_body": more_body}
    async def send(message):
        messages.append(message)
    asyncio.run(application(scope, receive, send))
    start = next(row for row in messages if row["type"] == "http.response.start")
    return (start["status"], {key.decode().lower(): value.decode() for key, value in start["headers"]},
            b"".join(row.get("body", b"") for row in messages if row["type"] == "http.response.body"))


class PortableAssuranceTests(unittest.TestCase):
    def assert_security(self, response, csp=None):
        self.assertEqual(response.headers["cache-control"], "no-store, max-age=0")
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertEqual(response.headers["x-frame-options"], "DENY")
        self.assertEqual(response.headers["referrer-policy"], "no-referrer")
        if csp:
            self.assertEqual(response.headers["content-security-policy"], csp)

    def test_demo_configuration_is_distinct_immutable_and_needs_no_input_io(self):
        demo = integration.DemoConfig()
        self.assertNotIsInstance(demo, integration.ReadinessConfig)
        with self.assertRaises((FrozenInstanceError, AttributeError, TypeError)):
            demo.bundle = Path("private")
        with patch.object(Path, "read_bytes", side_effect=AssertionError("No capture reads")):
            app = integration.AssuranceApplication(upstream(), demo)
            self.assertIs(app.config, demo)
        with self.assertRaises(TypeError):
            integration.AssuranceApplication(upstream(), {"mode": "demo"})

    def test_every_public_learning_page_has_head_and_scoped_local_links(self):
        with client() as session:
            for path in PAGES:
                with self.subTest(path=path):
                    get, head = session.get(PREFIX + path), session.head(PREFIX + path)
                    self.assertEqual((get.status_code, head.status_code, head.content), (200, 200, b""))
                    self.assertEqual(int(head.headers["content-length"]), len(get.content))
                    self.assert_security(get)
                    self.assertIn("pending", get.text.lower())
                    for tag, attrs in Document(get.content).tags:
                        for attr in ("href", "src", "action"):
                            value = attrs.get(attr, "")
                            if value.startswith("/") and not value.startswith("//"):
                                self.assertTrue(value == "/" or value.startswith(PREFIX + "/"), value)

    def test_fictional_status_explicitly_disclaims_project_evidence_and_authority(self):
        with client() as session:
            response = session.get(PREFIX + "/api/local-status")
            self.assertEqual(response.status_code, 200)
            status = response.json()
            self.assertEqual(status["schema"], "mra-portable-teaching-status/1")
            self.assertEqual(status["mode"], "fictional_demo")
            self.assertIs(status["project_evidence_loaded"], False)
            self.assertIs(status["captured_integrity_claimed"], False)
            self.assertEqual(status["agency_decisions"], "pending")
            self.assertEqual(status["authorization_effect"], "none")
            self.assertIs(status["benchmark_executed"], False)

    def test_capture_downloads_never_present_fabricated_project_results(self):
        with client() as session:
            for path in CAPTURED:
                with self.subTest(path=path):
                    response = session.get(PREFIX + path)
                    self.assertEqual(response.status_code, 503)
                    self.assertNotIn(CANARY, response.text)
                    self.assertNotIn('"overall_verdict"', response.text)
            self.assertEqual(session.get(PREFIX + "/not-a-page").status_code, 404)

    def test_explicit_missing_captured_profile_never_falls_back_to_demo(self):
        with tempfile.TemporaryDirectory(prefix="mra-captured-unavailable-") as directory:
            capture = integration.ReadinessConfig(bundle=Path(directory) / "absent", manifest_sha256="a" * 64)
            with client(capture) as session:
                for path in ("/tutorial", "/tutorial-practice", "/practice-saves", "/api/tutorial-config"):
                    response = session.get(PREFIX + path)
                    self.assertEqual(response.status_code, 503)
                    self.assertNotIn('"fictional_demo"', response.text)
                self.assertEqual(session.get("/sentinel").content, b"existing-upstream")
        application = integration.AssuranceApplication(upstream(), None)
        with TestClient(application, base_url=BASE) as session:
            self.assertEqual(session.get(PREFIX + "/tutorial").status_code, 503)

    def test_demo_cannot_read_capture_readers_or_import_scientific_factory(self):
        with (patch("mra_readiness_dashboard.server.load_snapshot", side_effect=AssertionError("No captures")),
              patch("mra_readiness_dashboard.server._load_intake", side_effect=AssertionError("No reports")),
              patch("mra_readiness_dashboard.server._load_handoff", side_effect=AssertionError("No packets"))):
            with client() as session:
                self.assertEqual(session.get(PREFIX + "/tutorial-practice").status_code, 200)
        self.assertNotIn("mra_rr_continuation.qualified_evaluation_console_app", sys.modules)
        self.assertNotIn("mra_preregistered_evaluation", sys.modules)

    def test_finite_json_options_and_changed_checklists_remain_fictional(self):
        with client() as session:
            starting = session.get(PREFIX + "/api/tutorial-lab-config?preset=starting-point")
            worked = session.get(PREFIX + "/api/tutorial-lab-config?preset=worked-example")
            self.assertEqual((starting.status_code, worked.status_code), (200, 200))
            self.assertNotEqual(starting.json(), worked.json())
            for preset in ("starting-point", "draft-decisions", "reviewed-decisions", "traceable-sources", "worked-example"):
                self.assertEqual(session.get(PREFIX + "/api/tutorial-config?scenario=" + preset).status_code, 200)
            paired = session.get(PREFIX + "/api/tutorial-comparison?left_preset=starting-point&right_preset=worked-example")
            self.assertEqual(paired.status_code, 200)
            self.assertEqual(len(paired.json()["lesson"]["comparison"]["gap_checklists"]), 12)

    def test_all_finite_lessons_avoid_claiming_the_historical_project_state(self):
        forbidden = ("eighteen comparison", "twelve unsupported", "sealed fail result",
                     "real gaps: twelve open", "original substantive gaps closed: none",
                     "actual gap remains open", "actual gap remains closed")
        paths = ["/tutorial?scenario=" + value for value in interactive_tutorial.PRESET_IDS]
        paths += ["/tutorial-lab?preset=" + value for value in interactive_tutorial.PRESET_IDS]
        paths += ["/tutorial-walkthrough?step=" + value for value in STEP_IDS]
        paths += ["/tutorial-practice?exercise=" + value for value in EXERCISE_IDS]
        with client() as session:
            for path in paths:
                with self.subTest(path=path):
                    response = session.get(PREFIX + path)
                    self.assertEqual(response.status_code, 200)
                    text = response.text.lower()
                    self.assertIn("no project evidence loaded", text)
                    for phrase in forbidden:
                        self.assertNotIn(phrase, text)
            for family, parameter in (("tutorial-config", "scenario"), ("tutorial-lab-config", "preset")):
                for value in interactive_tutorial.PRESET_IDS:
                    response = session.get(PREFIX + "/api/" + family + "?" + parameter + "=" + value)
                    lesson = response.json()
                    self.assertEqual(lesson["schema"], "mra-portable-fictional-lesson/1")
                    self.assertEqual(lesson["real_gap_state"], "not_assessed")
                    self.assertFalse(lesson["project_evidence_loaded"])
                    self.assertNotIn("original_substantive_gaps_open", response.text)
                    self.assertNotIn("real_gap_status", response.text)

    def test_practice_and_comparison_choices_never_assert_an_actual_gap_state(self):
        # Individual finite choices and preset pairs exercise each presentation
        # branch without claiming an exhaustive Cartesian product or benchmark.
        paths = ["/tutorial-practice?exercise=" + exercise for exercise in EXERCISE_IDS]
        paths += ["/tutorial-compare?" + urlencode({"left_preset": left, "right_preset": right})
                  for left in interactive_tutorial.PRESET_IDS
                  for right in interactive_tutorial.PRESET_IDS]
        for row in interactive_tutorial.CONTROL_OPTIONS:
            for option, _ in row["options"]:
                changed = {**GOOD, row["key"]: option}
                paths.append("/tutorial-practice?" + urlencode({"exercise": "free-practice", **changed}))
                for side in ("left", "right"):
                    paths.append("/tutorial-compare?" + urlencode({
                        "left_preset": "worked-example", "right_preset": "worked-example",
                        side + "_" + row["key"]: option}))
        actual_state = re.compile(
            r"\bactual gap remains (?:open|closed)\b|"
            r"\breal (?:G\d{2} )?gaps? remain(?:s)? (?:open|closed)\b|"
            r"\breal G\d{2} remains (?:open|closed)\b", re.IGNORECASE)
        with client() as session:
            for path in paths:
                with self.subTest(path=path):
                    response = session.get(PREFIX + path)
                    self.assertEqual(response.status_code, 200)
                    self.assertIn("no project evidence loaded", response.text.lower())
                    self.assertIsNone(actual_state.search(response.text))
                    self.assertNotIn("Authentic receipts remain not supplied", response.text)

    def test_main_default_is_demo_and_explicit_captured_config_is_preserved(self):
        fake = types.ModuleType("mra_rr_continuation.qualified_evaluation_console_app")
        calls = []
        def existing(root, rr_data):
            calls.append((root, rr_data))
            return upstream()
        fake.create_app = existing
        with tempfile.TemporaryDirectory(prefix="mra-factory-contract-") as directory:
            with patch.dict(sys.modules, {fake.__name__: fake}):
                default = main_assurance_app.create_app(Path(directory))
                self.assertIsInstance(default.config, integration.DemoConfig)
                capture = integration.ReadinessConfig(bundle=Path(directory) / "missing", manifest_sha256="a" * 64)
                explicit = main_assurance_app.create_app(Path(directory), readiness_config=capture)
                self.assertIs(explicit.config, capture)
            self.assertEqual(calls, [(Path(directory), None), (Path(directory), None)])

    def test_strict_profile_paths_resolve_beside_the_profile_without_loading_evidence(self):
        with tempfile.TemporaryDirectory(prefix="mra-profile-contract-") as directory:
            root = Path(directory)
            profiles = root / "profiles"
            profiles.mkdir()
            path = profiles / "private.json"
            path.write_text(json.dumps({"schema": SCHEMA, "bundle": "../private-bundle",
                                        "manifest_sha256": "a" * 64,
                                        "intake_report": "../private-report", "intake_manifest_sha256": "b" * 64,
                                        "handoff_packet": "../private-packet", "handoff_archive_sha256": "c" * 64,
                                        "handoff_manifest_sha256": "d" * 64, "suspend_presentation": True}))
            config = load_readiness_config(path)
            self.assertIsInstance(config, integration.ReadinessConfig)
            self.assertEqual(config.bundle.resolve(), root / "private-bundle")
            self.assertEqual(config.intake_report.resolve(), root / "private-report")
            self.assertEqual(config.handoff_packet.resolve(), root / "private-packet")
            self.assertTrue(config.suspend_presentation)
            self.assertFalse(config.bundle.exists())

    def test_strict_profile_schema_duplicates_nonfinite_size_and_types_are_rejected(self):
        valid = {"schema": SCHEMA, "bundle": "bundle", "manifest_sha256": "a" * 64}
        bad = [[], None, True, {}, {**valid, "unknown": "private"},
               {**valid, "schema": "demo"}, {**valid, "bundle": True},
               {**valid, "bundle": None}, {**valid, "bundle": ""},
               {**valid, "bundle": "invalid\npath"}, {**valid, "manifest_sha256": "A" * 64},
               {**valid, "manifest_sha256": True}, {**valid, "suspend_presentation": 1}]
        raw_bad = [json.dumps(value).encode() for value in bad]
        raw_bad += [b'{"schema":"' + SCHEMA.encode() + b'","bundle":"bundle","bundle":"other","manifest_sha256":"' + b"a" * 64 + b'"}' ,
                    b'{"schema":"' + SCHEMA.encode() + b'","bundle":"bundle","manifest_sha256":NaN}',
                    b'{"schema":"' + SCHEMA.encode() + b'","bundle":"bundle","manifest_sha256":Infinity}',
                    b" " * 65537, b"\xff"]
        with tempfile.TemporaryDirectory(prefix="mra-invalid-profile-") as directory:
            path = Path(directory) / "private.json"
            for raw in raw_bad:
                with self.subTest(raw=raw[:100]):
                    path.write_bytes(raw)
                    with self.assertRaises((ValueError, TypeError)):
                        load_readiness_config(path)
            with self.assertRaises(ValueError):
                load_readiness_config(Path(directory))

    def test_strict_profile_requires_all_optional_paths_and_pins_to_be_paired(self):
        valid = {"schema": SCHEMA, "bundle": "bundle", "manifest_sha256": "a" * 64}
        additions = ({"intake_report": "report"}, {"intake_manifest_sha256": "b" * 64},
                     {"handoff_packet": "packet"}, {"handoff_archive_sha256": "c" * 64},
                     {"handoff_packet": "packet", "handoff_archive_sha256": "c" * 64,
                      "handoff_manifest_sha256": "d" * 64})
        with tempfile.TemporaryDirectory(prefix="mra-paired-profile-") as directory:
            path = Path(directory) / "private.json"
            for added in additions:
                path.write_text(json.dumps({**valid, **added}))
                with self.subTest(added=added), self.assertRaises(ValueError):
                    load_readiness_config(path)

    def test_explicit_bad_cli_profile_fails_before_server_factory_or_child_start(self):
        with tempfile.TemporaryDirectory(prefix="mra-cli-profile-") as directory:
            absent = Path(directory) / "missing-private.json"
            with (patch.dict(os.environ, {}, clear=True), redirect_stderr(io.StringIO()) as stderr,
                  patch("uvicorn.run", side_effect=AssertionError("Server must not start")),
                  patch.object(main_assurance_app, "create_app", side_effect=AssertionError("No factory")),
                  patch.object(subprocess, "Popen", side_effect=AssertionError("No child"))):
                with self.assertRaises(SystemExit) as stopped:
                    console.main(["serve", "--data", str(Path(directory) / "data"),
                                  "--readiness-config", str(absent)])
                self.assertEqual(stopped.exception.code, 2)
                self.assertIn("no demo fallback", stderr.getvalue())
                self.assertFalse((Path(directory) / "data").exists())

    def test_complete_practice_candidate_is_copied_and_has_twelve_finite_choices(self):
        query = urlencode({"exercise": "free-practice", **GOOD})
        with client() as session:
            practice = session.get(PREFIX + "/tutorial-practice?" + query)
            self.assertEqual(practice.status_code, 200)
            page = session.get(PREFIX + "/practice-saves?" + query)
            section = next(attrs for tag, attrs in Document(page.content).tags
                           if tag == "section" and attrs.get("id") == "practice-saves")
            payload = json.loads(section["data-library"])
            self.assertEqual(payload["candidate"], {"exercise": "free-practice", "assumptions": GOOD})
            self.assertEqual(len(payload["controls"]), 12)
            self.assert_security(page, practice_saves.SAVES_CSP)
            self.assertNotIn("http://127.0.0.1:8770", page.text)
        returned = practice_saves.library_payload(GOOD, "free-practice")
        returned["candidate"]["assumptions"]["purpose"] = CANARY
        self.assertEqual(practice_saves.library_payload(GOOD, "free-practice")["candidate"]["assumptions"], GOOD)

    def test_script_style_and_ordinary_csp_are_exact_and_head_safe(self):
        with client() as session:
            script = session.get(PREFIX + "/assets/practice-saves.js")
            self.assertEqual(script.content, integration.DERIVED_PRACTICE_SAVES_SCRIPT)
            self.assertIn(b'/assurance/tutorial-practice?', script.content)
            for path in ("/assets/practice-saves.js", "/assets/style.css"):
                get, head = session.get(PREFIX + path), session.head(PREFIX + path)
                self.assertEqual((get.status_code, head.status_code, head.content), (200, 200, b""))
                self.assertEqual(int(head.headers["content-length"]), len(get.content))
            self.assert_security(session.get(PREFIX + "/tutorial-practice"), ORDINARY_CSP)
            self.assertFalse(any(tag == "script" for tag, _ in
                                 Document(session.get(PREFIX + "/tutorial-practice").content).tags))

    def test_main_navigation_and_unrelated_upstream_responses_are_preserved(self):
        main = decorate_main_navigation(upstream())
        with TestClient(integration.AssuranceApplication(main, integration.DemoConfig()), base_url=BASE) as session:
            response = session.get("/")
            self.assertIn('id="readiness-learning"', response.text)
            self.assertIn("Existing datasets", response.text)
            self.assertIn('/assurance/practice-saves', response.text)
            self.assertEqual(session.get(NAV_CSS_PATH).status_code, 200)
            sentinel = session.get("/sentinel")
            self.assertEqual((sentinel.content, sentinel.headers["x-upstream"]), (b"existing-upstream", "preserved"))

    def test_ambiguous_paths_are_owned_and_rejected_before_reading_body(self):
        for path in (b"/assurance/%74utorial", b"/assurance//tutorial", b"/assurance/../tutorial",
                     b"/assurance\\tutorial", b"/%61ssurance/tutorial"):
            with self.subTest(path=path):
                self.assertEqual(raw_request(path, receive_forbidden=True)[0], 400)
        self.assertEqual(raw_request(query=b"x=\x00", receive_forbidden=True)[0], 400)

    def test_duplicate_or_cross_origin_headers_are_denied_before_body_reads(self):
        for headers in ([], [(b"host", b"evil.example")],
                        [(b"host", b"127.0.0.1:8765")] * 2,
                        [(b"host", b"127.0.0.1:8765"), (b"origin", b"https://127.0.0.1:8765")],
                        [(b"host", b"127.0.0.1:8765"), (b"origin", b"http://127.0.0.1:8765")] +
                        [(b"origin", b"http://127.0.0.1:8765")]):
            with self.subTest(headers=headers):
                self.assertEqual(raw_request(headers=headers, receive_forbidden=True)[0], 403)
        self.assertEqual(raw_request(server=("0.0.0.0", 8765), receive_forbidden=True)[0], 403)
        self.assertEqual(raw_request(headers=[(b"host", b"127.0.0.1:8765"),
                                              (b"origin", b"http://127.0.0.1:8765")])[0], 200)

    def test_expect_and_body_framing_and_methods_are_denied_without_receive(self):
        base = [(b"host", b"127.0.0.1:8765")]
        for header, code in (((b"expect", b"100-continue"), 417),
                             ((b"transfer-encoding", b"chunked"), 400),
                             ((b"content-length", b"1"), 400),
                             ((b"content-length", b"00"), 400)):
            with self.subTest(header=header):
                self.assertEqual(raw_request(headers=base + [header], receive_forbidden=True)[0], code)
        for method in ("POST", "PUT", "PATCH", "DELETE", "OPTIONS"):
            status, headers, _ = raw_request(method=method, receive_forbidden=True)
            self.assertEqual(status, 405)
            self.assertEqual(headers["allow"], "GET, HEAD")

    def test_actual_body_and_streamed_empty_chunk_are_rejected_without_accumulation(self):
        self.assertEqual(raw_request(body=CANARY.encode())[0], 400)
        self.assertEqual(raw_request(more_body=True)[0], 400)
        self.assertNotIn(CANARY.encode(), raw_request(body=CANARY.encode())[2])

    def test_asgi_target_header_and_protocol_bounds_fail_with_fixed_errors(self):
        for kwargs, status in (({"query": b"x=" + b"a" * 4100}, 414),
                               ({"headers": [(b"host", b"127.0.0.1:8765"), (b"x", b"a" * 4100)]}, 431),
                               ({"headers": [(b"host", b"127.0.0.1:8765")] + [(b"x", b"a")] * 33}, 431),
                               ({"headers": [(b"host", b"127.0.0.1:8765"), (b"x", b"bad\r\n")]}, 400),
                               ({"http_version": "2"}, 505)):
            with self.subTest(kwargs=kwargs):
                self.assertEqual(raw_request(receive_forbidden=True, **kwargs)[0], status)

    def test_queries_reject_unknown_duplicate_blank_or_nonfinite_values(self):
        paths = ("/tutorial?scenario=unknown", "/tutorial?scenario=starting-point&scenario=worked-example",
                 "/tutorial?scenario=", "/tutorial-lab?purpose=" + CANARY,
                 "/tutorial-practice?exercise=unknown", "/tutorial-practice?purpose=discussion&purpose=discussion",
                 "/practice-saves?exercise=free-practice", "/tutorial-compare?right_purpose=invalid",
                 "/tutorial-walkthrough?step=unknown", "/remediation?gap=G99",
                 "/remediation?gap=G01&gap=G02", "/evidence?execute=true", "/tutorial?scenario")
        with client() as session:
            for path in paths:
                with self.subTest(path=path):
                    response = session.get(PREFIX + path)
                    self.assertEqual(response.status_code, 400)
                    self.assertNotIn(CANARY, response.text)

    def test_saved_library_import_export_uses_fiction_guards_and_native_finite_urls(self):
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node.js must be on PATH for the portable saved-demo check")
        with client() as session:
            query = urlencode({"exercise": "free-practice", **GOOD})
            page = session.get(PREFIX + "/practice-saves?" + query)
            attrs = next(attrs for tag, attrs in Document(page.content).tags
                         if tag == "section" and attrs.get("id") == "practice-saves")
            payload = json.loads(attrs["data-library"])
            asset = session.get(PREFIX + "/assets/practice-saves.js").content
        script = r"""
const fs=require("node:fs"),assert=require("node:assert/strict");
const domain=JSON.parse(fs.readFileSync(0,"utf8"));let sequence=1,stored=null;
Object.defineProperty(globalThis,"crypto",{configurable:true,value:{randomUUID(){
 return "00000000-0000-4000-8000-"+(sequence++).toString(16).padStart(12,"0");}}});
const api=require(process.argv[1]);
const storage={getItem(){return stored;},setItem(key,value){stored=value;}};
const lib=api.createLibrary(domain,storage),a=lib.save("First fictional demo",domain.candidate);
const changed=JSON.parse(JSON.stringify(domain.candidate));changed.assumptions.vintage="correction-backfill";
const b=lib.save("Second fictional demo",changed),before=lib.read(),text=lib.exportText();
const exported=JSON.parse(text);assert.equal(exported.real_agency_decisions,"pending");
assert.equal(exported.authorization_effect,"none");assert.equal(exported.benchmark_executed,false);
assert.equal(exported.authentic_source_records_included,false);assert.equal(exported.fictional_example,true);
const added=lib.importText(text);assert.equal(added.length,2);assert.equal(lib.read().length,4);
assert.notEqual(added[0].id,a.id);assert.deepEqual(lib.read().slice(0,2),before);
const reload=new URL(lib.practiceUrl(b.id),"http://127.0.0.1:8765");
const compare=new URL(lib.compareUrl(a.id,b.id),"http://127.0.0.1:8765");
assert.equal(reload.pathname,"/assurance/tutorial-practice");assert.equal([...reload.searchParams].length,13);
assert.equal(compare.pathname,"/assurance/tutorial-compare");assert.equal([...compare.searchParams].length,26);
assert.equal(reload.searchParams.get("vintage"),"correction-backfill");
assert.equal(compare.searchParams.get("left_vintage"),"first-issue");
assert.equal(compare.searchParams.get("right_vintage"),"correction-backfill");
const bad=JSON.parse(text);bad.authorization_effect="approved";const saved=stored;
assert.throws(()=>lib.importText(api.canonicalStringify(bad)+"\n"));assert.equal(stored,saved);
process.stdout.write(JSON.stringify({reload:reload.pathname+reload.search,compare:compare.pathname+compare.search}));
"""
        with tempfile.TemporaryDirectory(prefix="mra-finite-js-") as directory:
            asset_path = Path(directory) / "practice-saves.cjs"
            asset_path.write_bytes(asset)
            run = subprocess.run([node, "-e", script, str(asset_path)], input=json.dumps(payload),
                                 capture_output=True, text=True, timeout=20, cwd=directory,
                                 env={**os.environ, "NODE_OPTIONS": "", "NODE_PATH": ""})
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertEqual(run.stderr, "")
        links = json.loads(run.stdout)
        with client() as session:
            for link in links.values():
                self.assertEqual(session.get(link).status_code, 200)


if __name__ == "__main__":
    unittest.main()
