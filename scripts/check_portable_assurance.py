#!/usr/bin/env python3
"""Smoke-check a wheel installed into --installed-target, without project evidence.

Run with Python -I. Console dependencies must already be installed in that Python.
Only a minimal upstream ASGI app and finite fictional choices are exercised; no
actual MRA scientific factory, listener, worker, training or benchmark is started.
"""
from __future__ import annotations

import argparse
from html.parser import HTMLParser
import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import urlencode


class PayloadParser(HTMLParser):
    def __init__(self, raw):
        super().__init__(convert_charrefs=True)
        self.payload = None
        self.feed(raw.decode("utf-8"))

    def handle_starttag(self, tag, pairs):
        attrs = dict(pairs)
        if tag == "section" and attrs.get("id") == "practice-saves":
            self.payload = json.loads(attrs["data-library"])


def check(installed_target):
    target = Path(installed_target).resolve(strict=True)
    if not target.is_dir():
        raise ValueError("Installed target must be a directory")
    checkout = Path(__file__).resolve().parents[1]
    sys.path[:] = [entry for entry in sys.path
                   if entry and Path(entry).resolve() not in (checkout, checkout / "src", checkout / "tests")]
    sys.path.insert(0, str(target))
    modules = ("mra_readiness_dashboard", "mra_readiness_intake", "mra_readiness_handoff",
               "mra_readiness_status", "mra_readiness_dashboard.console_integration",
               "mra_rr_continuation.main_assurance_app")
    origins = {}
    for name in modules:
        module = importlib.import_module(name)
        origin = Path(module.__file__).resolve(strict=True)
        if not origin.is_relative_to(target):
            raise AssertionError("Package import escaped the installed target: " + name)
        origins[name] = origin.relative_to(target).as_posix()
    from fastapi import FastAPI
    from fastapi.responses import Response
    from fastapi.testclient import TestClient
    from mra_readiness_dashboard.console_integration import AssuranceApplication, DemoConfig
    from mra_readiness_dashboard import practice_saves

    asset_path = target / "mra_readiness_dashboard" / "practice_saves.js"
    if not asset_path.is_file() or not asset_path.read_bytes():
        raise AssertionError("Wheel omitted saved-demo JavaScript")
    main = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    @main.get("/sentinel")
    def sentinel():
        return Response(b"minimal-upstream")
    pages = ("/", "/readiness", "/remediation", "/evidence", "/tutorial", "/tutorial-lab",
             "/tutorial-compare", "/tutorial-walkthrough", "/tutorial-practice", "/practice-saves", "/local-status")
    values = {"purpose": "discussion", "decision_review": "separate", "practical": "reasoned",
              "definitions": "aligned", "rights": "teaching-only", "vintage": "first-issue",
              "source_review": "separate", "protected_scope": "synthetic-only", "custody": "teaching-route",
              "operations": "teaching-stewardship", "pilot": "teaching-handover", "governance": "teaching-index"}
    with TestClient(AssuranceApplication(main, DemoConfig()), base_url="http://127.0.0.1:8765") as client:
        for path in pages:
            response = client.get("/assurance" + path)
            assert response.status_code == 200, (path, response.status_code)
            head = client.head("/assurance" + path)
            assert head.status_code == 200 and head.content == b"", path
            assert int(head.headers["content-length"]) == len(response.content), path
            assert response.headers["x-frame-options"] == "DENY", path
        status = client.get("/assurance/api/local-status").json()
        assert status["mode"] == "fictional_demo"
        assert status["project_evidence_loaded"] is False
        assert status["captured_integrity_claimed"] is False
        assert status["agency_decisions"] == "pending"
        assert status["authorization_effect"] == "none"
        assert status["benchmark_executed"] is False
        assert client.get("/sentinel").content == b"minimal-upstream"
        assert client.get("/assurance/api/findings").status_code == 503
        for path in ("/api/tutorial-config?scenario=worked-example", "/api/tutorial-lab-config?preset=worked-example",
                     "/api/tutorial-comparison?left_preset=starting-point&right_preset=worked-example"):
            assert client.get("/assurance" + path).status_code == 200, path
        page = client.get("/assurance/practice-saves?" + urlencode({"exercise": "free-practice", **values}))
        assert page.status_code == 200
        payload = PayloadParser(page.content).payload
        assert payload == practice_saves.library_payload(values, "free-practice")
        derived_js = client.get("/assurance/assets/practice-saves.js").content
        assert b'/assurance/tutorial-practice?' in derived_js
        assert b'/assurance/tutorial-compare?' in derived_js
        assert client.post("/assurance/tutorial").status_code == 405
        assert client.get("/assurance/tutorial?scenario=not-valid").status_code == 400
        assert client.get("/assurance/tutorial", headers={"Origin": "https://outside.invalid"}).status_code == 403
        assert client.get("/assurance/tutorial", headers={"Expect": "100-continue"}).status_code == 417
        assert client.get("/assurance/tutorial", headers={"Host": "outside.invalid"}).status_code == 403

        node = shutil.which("node")
        if node is None:
            raise AssertionError("Node.js must be on PATH for the finite saved-demo wheel check")
        script = r"""
const fs=require("node:fs"),assert=require("node:assert/strict");
const domain=JSON.parse(fs.readFileSync(0,"utf8"));let serial=1,raw=null;
Object.defineProperty(globalThis,"crypto",{configurable:true,value:{randomUUID(){
 return "00000000-0000-4000-8000-"+(serial++).toString(16).padStart(12,"0");}}});
const api=require(process.argv[1]),storage={getItem(){return raw;},setItem(k,v){raw=v;}};
const lib=api.createLibrary(domain,storage),a=lib.save("First fictional demo",domain.candidate);
const different=JSON.parse(JSON.stringify(domain.candidate));different.assumptions.vintage="correction-backfill";
const b=lib.save("Second fictional demo",different),original=lib.read(),exported=lib.exportText();
const envelope=JSON.parse(exported);assert.equal(envelope.real_agency_decisions,"pending");
assert.equal(envelope.authentic_source_records_included,false);assert.equal(envelope.authorization_effect,"none");
assert.equal(envelope.benchmark_executed,false);const copies=lib.importText(exported);
assert.equal(copies.length,2);assert.notEqual(copies[0].id,a.id);assert.deepEqual(lib.read().slice(0,2),original);
const reload=new URL(lib.practiceUrl(b.id),"http://127.0.0.1:8765");
const compare=new URL(lib.compareUrl(a.id,b.id),"http://127.0.0.1:8765");
assert.equal(reload.pathname,"/assurance/tutorial-practice");assert.equal([...reload.searchParams].length,13);
assert.equal(compare.pathname,"/assurance/tutorial-compare");assert.equal([...compare.searchParams].length,26);
process.stdout.write(JSON.stringify([reload.pathname+reload.search,compare.pathname+compare.search]));
"""
        with tempfile.TemporaryDirectory(prefix="mra-wheel-finite-js-") as directory:
            derived_path = Path(directory) / "practice-saves.cjs"
            derived_path.write_bytes(derived_js)
            run = subprocess.run([node, "-e", script, str(derived_path)], input=json.dumps(payload),
                                 capture_output=True, text=True, timeout=20, cwd=directory,
                                 env={**os.environ, "NODE_OPTIONS": "", "NODE_PATH": ""})
        if run.returncode or run.stderr:
            raise AssertionError("Finite saved-demo wheel check failed: " + run.stdout + run.stderr)
        links = json.loads(run.stdout)
        for link in links:
            assert client.get(link).status_code == 200, link
    forbidden = ("mra_rr_continuation.qualified_evaluation_console_app", "mra_preregistered_evaluation")
    assert not any(name == prefix or name.startswith(prefix + ".")
                   for prefix in forbidden for name in sys.modules), "Scientific factory imported"
    return {"schema": "mra-portable-wheel-smoke/1", "passed": True,
            "installed_target": str(target), "package_origins": origins,
            "learning_pages_checked": len(pages), "saved_demo_copy_import": True,
            "finite_reload_choices": 13, "finite_comparison_choices": 26,
            "project_evidence_loaded": False, "agency_decisions": "pending",
            "scientific_factory_called": False, "worker_started": False, "benchmark_executed": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installed-target", required=True, type=Path,
                        help="Fresh wheel installation directory, for example pip install --no-deps --target PATH WHEEL")
    args = parser.parse_args(argv)
    try:
        result = check(args.installed_target)
    except Exception as error:
        print(json.dumps({"schema": "mra-portable-wheel-smoke/1", "passed": False,
                          "error_type": type(error).__name__, "error": str(error),
                          "benchmark_executed": False}), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
