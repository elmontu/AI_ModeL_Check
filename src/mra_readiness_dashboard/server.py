"""Loopback-only GET/HEAD presentation, without scientific imports or writes."""
from __future__ import annotations

import argparse
import base64
import hashlib
import importlib
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .bundle import BundleError, GAP_IDS, load_snapshot
from .limits import BoundedConnectionsMixin
from .tutorial import SCENARIO_IDS, scenario_json
from .interactive_tutorial import CONTROL_OPTIONS, PRESET_IDS, configuration_json
from .tutorial_comparison import comparison_json
from .guided_comparison import STEP_IDS
from .guided_practice import EXERCISE_IDS
from .practice_saves import SAVES_CSP
from .protocol import BoundedRequestMixin, ERROR_BODIES
from .views import STATUS_STYLES, STYLES, render_page, render_status_page

API_FILES = {"/api/readiness": "readiness.json", "/api/gaps": "gap-register.json", "/api/work-packages": "work-packages.json", "/api/response-template": "agency-response-template.json", "/api/evidence": "evidence-index.json", "/api/findings": "research-findings.json"}
LAB_VALUES = {row["key"]: tuple(option[0] for option in row["options"]) for row in CONTROL_OPTIONS}
COMPARISON_VALUES = {side + "_" + key: values for side in ("left", "right") for key, values in LAB_VALUES.items()}
PRACTICE_SAVES_SCRIPT = Path(__file__).with_name("practice_saves.js").read_bytes()
SUSPENDED_BODY = b"Presentation suspended: captured views and downloads are withheld for this process. Agency decisions remain pending. Authorization effect: none.\n"


def _load_intake(directory, pin, baseline_pin):
    """Import only the independent local intake reader, when configured."""
    reader = importlib.import_module("mra_readiness_intake.report")
    return reader.load_report(directory, pin, baseline_pin)


def _load_handoff(directory, archive_pin, manifest_pin, baseline_pin, intake_pin):
    """Import only the independent, read-only review-packet verifier."""
    reader = importlib.import_module("mra_readiness_handoff.packet")
    return reader.load_packet(directory, archive_pin, manifest_pin, baseline_pin, intake_pin)


STATUS_CSP = "default-src 'none'; style-src 'sha256-" + base64.b64encode(hashlib.sha256(STATUS_STYLES.encode("utf-8")).digest()).decode("ascii") + "'; form-action 'none'; base-uri 'none'; frame-ancestors 'none'; object-src 'none'"


def _check_inputs(server):
    """Read configured captured inputs once for this request; no status cache."""
    checker = importlib.import_module("mra_readiness_status")
    return checker.check_inputs(server.bundle, server.manifest_sha256,
                                server.intake_report, server.intake_manifest_sha256,
                                server.handoff_packet, server.handoff_archive_sha256,
                                server.handoff_manifest_sha256,
                                _readers=(load_snapshot, _load_intake, _load_handoff))


class ReadinessServer(BoundedConnectionsMixin, ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, address, bundle, manifest_sha256, intake_report=None, intake_manifest_sha256=None, handoff_packet=None, handoff_archive_sha256=None, handoff_manifest_sha256=None, *, suspend_presentation=False):
        if type(suspend_presentation) is not bool:
            raise ValueError("Presentation suspension must be a boolean startup option")
        if address[0] != "127.0.0.1":
            raise ValueError("Readiness dashboard binds only to 127.0.0.1")
        if (intake_report is None) != (intake_manifest_sha256 is None):
            raise ValueError("Intake report directory and manifest pin must be supplied together")
        handoff_options = (handoff_packet, handoff_archive_sha256, handoff_manifest_sha256)
        if any(value is not None for value in handoff_options) and not all(value is not None for value in handoff_options):
            raise ValueError("Review packet directory, archive pin and manifest pin must be supplied together")
        if handoff_packet is not None and intake_report is None:
            raise ValueError("A review packet requires a configured pinned intake report")
        load_snapshot(bundle, manifest_sha256)
        if intake_report is not None:
            _load_intake(intake_report, intake_manifest_sha256, manifest_sha256)
        if handoff_packet is not None:
            _load_handoff(handoff_packet, handoff_archive_sha256, handoff_manifest_sha256, manifest_sha256, intake_manifest_sha256)
        importlib.import_module("mra_readiness_status")
        self.handoff_packet = Path(handoff_packet) if handoff_packet is not None else None
        self.handoff_archive_sha256 = handoff_archive_sha256
        self.handoff_manifest_sha256 = handoff_manifest_sha256
        self.intake_report = Path(intake_report) if intake_report is not None else None
        self.intake_manifest_sha256 = intake_manifest_sha256
        self.bundle = Path(bundle)
        self.manifest_sha256 = manifest_sha256
        self._suspend_presentation = suspend_presentation
        super().__init__(address, ReadinessHandler)

    @property
    def suspend_presentation(self):
        """Startup selection; no presentation control endpoint or setter."""
        return self._suspend_presentation


class ReadinessHandler(BoundedRequestMixin, BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def version_string(self):
        return "MRAReadiness/1"

    def log_message(self, format, *args):
        # Do not put request-supplied text in terminals or evidence logs.
        return

    def _send(self, code, raw, mime="text/plain; charset=utf-8", filename=None, csp=None):
        self.close_connection = True
        self.send_response(code)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", csp or "default-src 'none'; style-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'; object-src 'none'")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header("Connection", "close")
        if code == 503:
            self.send_header("Link", '</local-status>; rel="help"; title="Local captured-input status"')
        if code == 405:
            self.send_header("Allow", "GET, HEAD")
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(raw)

    def _request(self):
        # Repeated even for denied methods and unknown routes. The same fresh
        # validated objects feed ordinary views; a failed chain serves no content.
        input_report, snapshot, intake, handoff = _check_inputs(self.server)
        inputs_match = input_report["result"] == "matches_captured_bytes"
        suspended = self.server.suspend_presentation
        available = inputs_match and not suspended
        report = {**input_report, "schema": "local-presentation-integrity-status/2",
                  "presentation": {"mode": "suspended" if suspended else "read_only",
                                   "captured_content": "available" if available else "withheld"}}
        message = b"Snapshot unavailable: captured readiness, intake or review packet validation failed. No readiness or authorization claim is presented.\n" if self.server.handoff_packet is not None else b"Snapshot unavailable: captured readiness or intake validation failed. No readiness or authorization claim is presented.\n"
        if inputs_match and suspended:
            message = SUSPENDED_BODY

        def deny(code, body):
            # Denied requests never receive diagnostic component information.
            self._send(code if available else 503, body if available else message)

        expected = f"127.0.0.1:{self.server.server_port}"
        hosts = self.headers.get_all("Host", [])
        origins = self.headers.get_all("Origin", [])
        if hosts != [expected] or len(origins) > 1 or (origins and origins != [f"http://{expected}"]):
            deny(403, b"Local host or origin rejected.\n")
            return
        if self.headers.get_all("Expect", []):
            deny(417, ERROR_BODIES[417])
            return
        if self.headers.get_all("Transfer-Encoding", []) or self.headers.get_all("Content-Length", []) not in ([], ["0"]):
            deny(400, b"Request bodies are not accepted.\n")
            return
        if self.command not in ("GET", "HEAD"):
            deny(405, b"Read-only dashboard: GET and HEAD only.\n")
            return
        try:
            target = urlsplit(self.path)
            if target.scheme or target.netloc or target.fragment or "%" in target.path or "\\" in target.path:
                raise ValueError("Invalid target")
            query_limit = 26 if target.path in ("/tutorial-compare", "/api/tutorial-comparison") else (13 if target.path in ("/tutorial-lab", "/api/tutorial-lab-config", "/tutorial-practice", "/practice-saves") else 2)
            query = parse_qs(target.query, keep_blank_values=True, strict_parsing=True, max_num_fields=query_limit)
            if target.path == "/remediation":
                if set(query) - {"gap"} or len(query.get("gap", [])) > 1 or (query.get("gap", [""])[0] not in ("", *GAP_IDS)):
                    raise ValueError("Invalid filter")
            elif target.path in ("/tutorial", "/api/tutorial-config"):
                if set(query) - {"scenario"} or len(query.get("scenario", [])) > 1 or ("scenario" in query and query["scenario"][0] not in SCENARIO_IDS):
                    raise ValueError("Invalid tutorial selection")
            elif target.path in ("/tutorial-lab", "/api/tutorial-lab-config"):
                if set(query) - ({"preset"} | set(LAB_VALUES)) or any(len(values) != 1 for values in query.values()):
                    raise ValueError("Invalid tutorial assumptions")
                if "preset" in query and query["preset"][0] not in PRESET_IDS:
                    raise ValueError("Invalid tutorial preset")
                if any(key in query and query[key][0] not in values for key, values in LAB_VALUES.items()):
                    raise ValueError("Invalid tutorial assumption")
            elif target.path == "/practice-saves":
                if query:
                    if set(query) != ({"exercise"} | set(LAB_VALUES)) or any(len(values) != 1 for values in query.values()):
                        raise ValueError("Invalid saved-demo candidate")
                    if query["exercise"][0] not in EXERCISE_IDS or any(query[key][0] not in values for key, values in LAB_VALUES.items()):
                        raise ValueError("Invalid saved-demo choices")
            elif target.path == "/tutorial-practice":
                if set(query) - ({"exercise"} | set(LAB_VALUES)) or any(len(values) != 1 for values in query.values()):
                    raise ValueError("Invalid practice selection")
                if "exercise" in query and query["exercise"][0] not in EXERCISE_IDS:
                    raise ValueError("Invalid practice exercise")
                if any(key in query and query[key][0] not in values for key, values in LAB_VALUES.items()):
                    raise ValueError("Invalid practice assumption")
            elif target.path == "/tutorial-walkthrough":
                if set(query) - {"step"} or any(len(values) != 1 for values in query.values()) or ("step" in query and query["step"][0] not in STEP_IDS):
                    raise ValueError("Invalid guided lesson")
            elif target.path in ("/tutorial-compare", "/api/tutorial-comparison"):
                if set(query) - ({"left_preset", "right_preset"} | set(COMPARISON_VALUES)) or any(len(values) != 1 for values in query.values()):
                    raise ValueError("Invalid comparison selection")
                if any(key in query and query[key][0] not in PRESET_IDS for key in ("left_preset", "right_preset")):
                    raise ValueError("Invalid comparison preset")
                if any(key in query and query[key][0] not in values for key, values in COMPARISON_VALUES.items()):
                    raise ValueError("Invalid comparison assumption")
            elif query:
                raise ValueError("Query not supported")
        except ValueError:
            deny(400, b"Invalid read-only view or filter.\n")
            return
        if target.path == "/local-status":
            self._send(200 if available else 503, render_status_page(report).encode("utf-8"), "text/html; charset=utf-8", csp=STATUS_CSP)
            return
        if target.path == "/api/local-status":
            raw = (json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")
            self._send(200 if available else 503, raw, "application/json; charset=utf-8", "local-status.json")
            return
        if not available:
            self._send(503, message)
            return
        if target.path == "/practice-saves":
            assumptions = {key: query[key][0] for key in LAB_VALUES} if query else None
            self._send(200, render_page(snapshot, "practice-saves", intake=intake, handoff=handoff, save_assumptions=assumptions, save_exercise=query.get("exercise", [None])[0]).encode("utf-8"), "text/html; charset=utf-8", csp=SAVES_CSP)
        elif target.path == "/assets/practice-saves.js":
            self._send(200, PRACTICE_SAVES_SCRIPT, "text/javascript; charset=utf-8")
        elif target.path == "/tutorial-practice":
            assumptions = {key: query[key][0] for key in LAB_VALUES if key in query}
            self._send(200, render_page(snapshot, "tutorial-practice", intake=intake, handoff=handoff, practice_assumptions=assumptions, practice_exercise=query.get("exercise", [None])[0]).encode("utf-8"), "text/html; charset=utf-8")
        elif target.path == "/tutorial-walkthrough":
            self._send(200, render_page(snapshot, "tutorial-walkthrough", intake=intake, handoff=handoff, walkthrough_step=query.get("step", [None])[0]).encode("utf-8"), "text/html; charset=utf-8")
        elif target.path in ("/tutorial-compare", "/api/tutorial-comparison"):
            left_preset = query.get("left_preset", [None])[0]
            right_preset = query.get("right_preset", [None])[0]
            left = {key: query["left_" + key][0] for key in LAB_VALUES if "left_" + key in query}
            right = {key: query["right_" + key][0] for key in LAB_VALUES if "right_" + key in query}
            if target.path == "/tutorial-compare":
                self._send(200, render_page(snapshot, "tutorial-compare", intake=intake, handoff=handoff, comparison_left=left, comparison_right=right, comparison_left_preset=left_preset, comparison_right_preset=right_preset).encode("utf-8"), "text/html; charset=utf-8")
            else:
                self._send(200, comparison_json(left, right, left_preset, right_preset), "application/json; charset=utf-8", "tutorial-comparison-example.json")
        elif target.path in ("/tutorial-lab", "/api/tutorial-lab-config"):
            preset = query.get("preset", [None])[0]
            assumptions = {key: query[key][0] for key in LAB_VALUES if key in query}
            if target.path == "/tutorial-lab":
                self._send(200, render_page(snapshot, "tutorial-lab", intake=intake, handoff=handoff, tutorial_assumptions=assumptions, tutorial_preset=preset).encode("utf-8"), "text/html; charset=utf-8")
            else:
                self._send(200, configuration_json(assumptions, preset), "application/json; charset=utf-8", "interactive-tutorial-example.json")
        elif target.path == "/tutorial":
            selected = query.get("scenario", [None])[0]
            self._send(200, render_page(snapshot, "tutorial", intake=intake, handoff=handoff, tutorial_scenario=selected).encode("utf-8"), "text/html; charset=utf-8")
        elif target.path == "/api/tutorial-config":
            selected = query.get("scenario", [None])[0]
            self._send(200, scenario_json(selected), "application/json; charset=utf-8", "tutorial-example.json")
        elif target.path in API_FILES:
            name = API_FILES[target.path]
            self._send(200, snapshot['_files'][name], "application/json; charset=utf-8", name)
        elif intake is not None and target.path in ("/api/intake-report", "/api/intake-checklist"):
            name = "report.json" if target.path == "/api/intake-report" else "report.md"
            mime = "application/json; charset=utf-8" if name.endswith(".json") else "text/markdown; charset=utf-8"
            self._send(200, intake['_files'][name], mime, name)
        elif handoff is not None and target.path in ("/api/review-handoff/archive", "/api/review-handoff/manifest", "/api/review-handoff/readme"):
            key, mime, filename = {
                "/api/review-handoff/archive": ("_archive_bytes", "application/zip", "review-packet.zip"),
                "/api/review-handoff/manifest": ("_manifest_bytes", "application/json; charset=utf-8", "packet-manifest.json"),
                "/api/review-handoff/readme": ("_readme_bytes", "text/markdown; charset=utf-8", "README.md"),
            }[target.path]
            self._send(200, handoff[key], mime, filename)
        elif handoff is not None and target.path == "/review-handoff":
            self._send(200, render_page(snapshot, "handoff", intake=intake, handoff=handoff).encode("utf-8"), "text/html; charset=utf-8")
        elif intake is not None and target.path == "/intake":
            self._send(200, render_page(snapshot, "intake", intake=intake, handoff=handoff).encode("utf-8"), "text/html; charset=utf-8")
        elif intake is not None and target.path == "/intake-guide":
            self._send(200, render_page(snapshot, "intake-guide", intake=intake, handoff=handoff).encode("utf-8"), "text/html; charset=utf-8")
        elif target.path == "/assets/style.css":
            self._send(200, STYLES.encode("utf-8"), "text/css; charset=utf-8")
        elif target.path in ("/", "/readiness", "/remediation", "/findings", "/evidence"):
            view = {"/": "overview", "/readiness": "overview", "/remediation": "remediation", "/findings": "findings", "/evidence": "evidence"}[target.path]
            selected = query.get("gap", [None])[0] or None
            self._send(200, render_page(snapshot, view, selected, intake=intake, handoff=handoff).encode("utf-8"), "text/html; charset=utf-8")
        else:
            self._send(404, b"Unknown read-only route.\n")

    do_GET = _request
    do_HEAD = _request
    do_POST = _request
    do_PUT = _request
    do_PATCH = _request
    do_DELETE = _request
    do_OPTIONS = _request
    do_TRACE = _request
    do_CONNECT = _request

    def __getattr__(self, name):
        if name.startswith("do_"):
            return self._request
        raise AttributeError(name)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Show a pinned readiness preparation bundle; no scientific execution or approvals")
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--intake-report", type=Path, help="Optional pinned local intake report directory")
    parser.add_argument("--intake-manifest-sha256", help="Required manifest pin when an intake report is configured")
    parser.add_argument("--handoff-packet", type=Path, help="Optional pinned local review-packet directory")
    parser.add_argument("--handoff-archive-sha256", help="Required archive pin when a review packet is configured")
    parser.add_argument("--handoff-manifest-sha256", help="Required manifest pin when a review packet is configured")
    parser.add_argument("--port", default=8770, type=int)
    parser.add_argument("--suspend-presentation", action="store_true", help="Withhold captured views and downloads for this process while retaining guarded local status")
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    try:
        server = ReadinessServer(("127.0.0.1", args.port), args.bundle, args.manifest_sha256, args.intake_report, args.intake_manifest_sha256, args.handoff_packet, args.handoff_archive_sha256, args.handoff_manifest_sha256, suspend_presentation=args.suspend_presentation)
    except (BundleError, OSError, TypeError, KeyError, ValueError, RecursionError, ImportError):
        parser.error("Captured readiness, intake or review packet configuration validation failed")
    print(f"Read-only readiness dashboard: http://127.0.0.1:{server.server_port}/readiness", flush=True)
    print(f"Pinned manifest: {args.manifest_sha256}; agency decisions pending; no authorization effect", flush=True)
    print("Presentation mode: suspended; captured content withheld for this process" if args.suspend_presentation else "Presentation mode: read_only; captured content remains subject to fresh input checks", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
