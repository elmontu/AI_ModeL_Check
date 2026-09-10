"""Execute the local framework option matrix and retain every run and attack result.

Uses the real API application, persistent queue, subprocess trainers and assessment
worker. TestClient covers HTTP contracts; a separate browser check covers the UI.
No result in this report authorizes release. Use a new output directory each time.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import importlib.metadata
import json
import platform
import threading
import time
import traceback
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from model_release_assurance import workflow
from model_release_assurance.console.api import create_app
from model_release_assurance.console.store import Store
from model_release_assurance.console.worker import work_once
from model_release_assurance.public_models import PRESETS, DATASETS

ROOT = Path(__file__).resolve().parents[1]
CLASSIFIERS = {"logistic", "random-forest", "mlp", "mlp-finetuned", "svm", "ensemble"}


def expected_pair(preset, dataset):
    if preset == "xgboost-small":
        return dataset == "sklearn-breast-cancer"
    if preset == "cnn":
        return dataset == "sklearn-digits"
    if preset in {"ridge", "forest-regression"}:
        return dataset == "sklearn-diabetes"
    if preset in CLASSIFIERS:
        return dataset in {"sklearn-breast-cancer", "sklearn-wine", "sklearn-digits"}
    raise ValueError("New preset requires an explicit validation expectation: " + preset)


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def source_hashes():
    paths = list((ROOT / "src").rglob("*.py"))
    paths += list((ROOT / "src/model_release_assurance/console/static").glob("*"))
    paths += [Path(__file__), ROOT / "scripts/run_training_release_demo.py"]
    return {p.relative_to(ROOT).as_posix(): workflow.digest(p) for p in sorted(paths) if p.is_file()}


def render_report(report, output):
    rows = report["training_matrix"]
    attacks = [(row, tool) for row in rows for tool in row.get("attacks", [])]
    completed = sum(t["status"] == "completed" for _, t in attacks)
    unsupported = sum(t["status"] == "unsupported" for _, t in attacks)
    failed = sum(t["status"] == "failed" for _, t in attacks)
    lines = ["# End-to-end framework test results", "", f"Run status: **{report['status']}**.", "",
             "Execution PASS means the expected workflow behavior was observed. It is not a model safety verdict.", "",
             f"Attack executions: {completed} completed, {unsupported} unsupported, {failed} failed.", "",
             "## Every training option", "",
             "| Preset | Dataset | Expected | Execution | Assessment | Attacks (completed/unsupported/failed) |",
             "| --- | --- | --- | --- | --- | --- |"]
    for row in rows:
        tools = row.get("attacks", [])
        counts = "/".join(str(sum(t["status"] == state for t in tools)) for state in ("completed", "unsupported", "failed"))
        lines.append(f"| {row['preset']} | {row['dataset']} | {'execute' if row['supported'] else 'reject'} | {row['status']} | {row.get('verdict', '—')} | {counts} |")
    lines += ["", "## Every adversary execution", "",
              "Metrics, budgets, baselines and assumptions are retained verbatim in `validation-report.json` and each job artifact directory.", "",
              "| Preset | Dataset | Adversary | Execution |", "| --- | --- | --- | --- |"]
    for row, tool in attacks:
        lines.append(f"| {row['preset']} | {row['dataset']} | {tool['tool']} | {tool['status']} |")
    lines += ["", "## Utility and related experiments", "",
              "Utility baselines are learned only from training records. Low utility does not change an execution PASS into a safety pass.", "",
              "| Preset | Dataset | Held-out utility | Related reports |", "| --- | --- | --- | --- |"]
    for row in rows:
        if row.get("utility"):
            lines.append(f"| {row['preset']} | {row['dataset']} | {json.dumps(row['utility'], sort_keys=True)} | {', '.join(r['path'] for r in row.get('related_reports', [])) or '—'} |")
    lines += ["", "## Language endpoints", "", "| Model | Execution | Coverage | Observed violations | Controls |", "| --- | --- | --- | --- | --- |"]
    for row in report["language"]:
        r = row.get("result", {})
        lines.append(f"| {row['model']} | {row['status']} | {r.get('status', '—')} | {r.get('observed_violations', '—')} | {json.dumps(r.get('controls', {}))} |")
    lines += ["", "| Model | Language adversary | Execution | Observed violation |", "| --- | --- | --- | --- |"]
    for row in report["language"]:
        for attack in row.get("result", {}).get("tests", []):
            lines.append(f"| {row['model']} | {attack['id']} | {attack['status']} | {attack.get('observed_violation', '—')} |")
    lines += ["", "## Case and reference paths", "",
              f"Case kind × route × mode combinations checked: {len(report['case_matrix'])}.",
              "These are intake and missing-evidence rejection checks; they do not imply a trainer for each case kind.", "",
              f"Reference scenarios: {json.dumps(report.get('reference', {}), ensure_ascii=False)}", "",
              "## Failures and boundaries", ""]
    failures = [r for r in rows + report["case_matrix"] + report["language"] if r["status"] == "FAIL"]
    lines += [f"- {r.get('preset', r.get('model', r.get('kind')))}: {r.get('error', 'failed')}" for r in failures]
    lines += ["- No failed or unsupported tool is counted as a safety pass.",
              "- Live agency data, complete-interface privacy ceilings, production deployments, audio/diffusion and large-model training are outside this local matrix.",
              "- Synthetic RAG passages and inert agent tools do not validate a live retrieval index or tool executor.",
              "- See JSON for source hashes, dependency versions, all metrics, exact job IDs, and tamper/mode-switch outcomes."]
    (output / "validation-report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    temporary = output / "validation-report.json.tmp"
    temporary.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(output / "validation-report.json")


def run(output, language_models=(), *, presets=None):
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    store = Store(output / "workspace")
    report = {"format_version": "local-framework-validation/1", "status": "running",
              "started_at": datetime.now(timezone.utc).isoformat(), "python": platform.python_version(),
              "platform": platform.platform(), "implementation": source_hashes(),
              "dependencies": {name: importlib.metadata.version(name) for name in
                               ("numpy", "scikit-learn", "scipy", "xgboost", "pydantic", "fastapi", "httpx")},
              "training_matrix": [], "case_matrix": [], "language": [], "authorization_eligible": False}
    worker = "matrix-validator"
    stop = threading.Event()

    def heartbeat():
        while not stop.is_set():
            store.heartbeat(worker)
            stop.wait(2)

    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    client = TestClient(create_app(store.root))

    def job(payload):
        response = client.post("/api/jobs", json=payload)
        require(response.status_code == 202, response.text)
        identifier = response.json()["id"]
        require(work_once(store, worker), "Worker did not claim queued job")
        done = client.get("/api/jobs/" + identifier).json()
        require(done["state"] == "completed", f"{identifier}: {done.get('error')}")
        return done

    def exported(job_id):
        response = client.get(f"/api/jobs/{job_id}/artifacts")
        require(response.status_code == 200, response.text)
        inventory = response.json()
        require(inventory["files"], "Completed job has no accessible artifacts")
        for entry in inventory["files"]:
            downloaded = client.get(entry["download_url"])
            require(downloaded.status_code == 200, "Artifact download failed: " + entry["path"])
            require(hashlib.sha256(downloaded.content).hexdigest() == entry["sha256"], "Downloaded artifact hash mismatch")
        response = client.get(f"/api/jobs/{job_id}/bundle")
        require(response.status_code == 200, "Bundle export failed")
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            require(manifest["files"] == inventory["files"], "Bundle manifest differs from inventory")
            require(set(archive.namelist()) == {"manifest.json"} | {e["path"] for e in inventory["files"]}, "Unexpected archive entries")
            for entry in inventory["files"]:
                require(hashlib.sha256(archive.read(entry["path"])).hexdigest() == entry["sha256"], "Bundle artifact hash mismatch")
        return {"file_count": len(inventory["files"]), "total_bytes": inventory["total_bytes"],
                "archive_sha256": hashlib.sha256(response.content).hexdigest(), "all_download_hashes_verified": True}

    try:
        require(client.get("/healthz").status_code == 200, "API health")
        # Intake covers every exposed release type and route, independently of trainers.
        for kind in workflow.KINDS:
            for route in workflow.ROUTES:
                for mode in ("education", "review"):
                    row = {"kind": kind, "route": route, "mode": mode, "status": "FAIL"}
                    try:
                        response = client.post("/api/cases", json={"name": f"{kind} {route} {mode}", "kind": kind, "route": route, "mode": mode})
                        require(response.status_code == 201, response.text)
                        case = response.json()["id"]
                        detail = client.get("/api/cases/" + case).json()
                        expected = 5 if mode == "education" else 8
                        require(sum(i["required"] for i in detail["inputs"]) == expected, "Wrong required slot count")
                        checked = job({"kind": "check", "case_id": case})["result"]
                        require(checked["status"] == "inputs_incomplete", "Empty case was not blocked")
                        response = client.post("/api/jobs", json={"kind": "assess", "case_id": case})
                        require(response.status_code == 202, response.text)
                        work_once(store, worker)
                        require(store.job(response.json()["id"])["state"] == "failed", "Empty assessment did not fail closed")
                        row.update(status="PASS", case_id=case, missing_inputs=checked["issues"])
                    except Exception as exc:
                        row["error"] = str(exc)
                    report["case_matrix"].append(row)

        selected = list(PRESETS) if presets is None else presets
        report["selected_presets"] = selected
        report["scope"] = "all supported presets" if set(selected) == set(PRESETS) else "selected subset"
        for preset in selected:
            for dataset in DATASETS:
                row = {"preset": preset, "dataset": dataset, "supported": expected_pair(preset, dataset), "status": "FAIL"}
                started = time.monotonic()
                try:
                    response = client.post("/api/jobs", json={"kind": "training", "training": {"name": f"{preset} {dataset}", "preset": preset, "dataset": dataset}})
                    if not row["supported"]:
                        require(response.status_code == 422, "Unsupported pair accepted")
                        row.update(status="PASS", rejection_status=response.status_code)
                    else:
                        require(response.status_code == 202, response.text)
                        identifier = response.json()["id"]
                        row["training_job_id"] = identifier
                        work_once(store, worker)
                        done = client.get("/api/jobs/" + identifier).json()
                        require(done["state"] == "completed", f"Training failed: {done.get('error')}; see workspace/jobs/{identifier}/worker.log")
                        result = done["result"]
                        row.update(verdict=result["verdict"], utility=result["training"]["utility"],
                                   attacks=result["red_team"]["tools"], coverage_gaps=result["red_team"]["coverage_gaps"],
                                   artifact_directory=result["artifact_directory"], case_id=result["case_id"])
                        row["warnings"] = result.get("warnings", [])
                        row["related_reports"] = []
                        directory = (store.root / result["artifact_directory"]).resolve()
                        for related in result["red_team"].get("related_reports", []):
                            path = (directory / related["path"]).resolve()
                            require(path.is_relative_to(directory) and workflow.digest(path) == related["sha256"], "Related experiment binding mismatch")
                            row["related_reports"].append({**related, "result": json.loads(path.read_text(encoding="utf-8"))})
                        expected_related = set()
                        if preset == "mlp-finetuned": expected_related.add("derivative-privacy-comparison.json")
                        if preset == "ensemble": expected_related.add("joint-access-privacy.json")
                        if dataset == "sklearn-digits": expected_related.add("image-tests.json")
                        require(expected_related <= {r["path"] for r in row["related_reports"]}, "Required derivative, component or image experiments missing")
                        require(not result["authorized"], "Teaching run authorized release")
                        require(result["verdict"] in {"inconclusive", "block"}, "Unexpected clearing verdict")
                        require(not any(t["status"] == "failed" for t in row["attacks"]), "One or more adversaries failed")
                        case = result["case_id"]
                        checked = job({"kind": "check", "case_id": case})["result"]
                        require(not checked["issues"], "Generated case has missing bindings")
                        assessed = job({"kind": "assess", "case_id": case})
                        row["assessment_job_id"] = assessed["id"]
                        require(assessed["result"]["assessment_verdict"] == row["verdict"], "Reassessment changed verdict")
                        require(not assessed["result"]["authorized"], "Reassessment authorized release")
                        row["training_export"] = exported(identifier)
                        row["assessment_export"] = exported(assessed["id"])
                        require(client.post(f"/api/cases/{case}/mode", json={"mode": "review"}).status_code == 200, "Review switch failed")
                        review = job({"kind": "check", "case_id": case})["result"]
                        require(len(review["issues"]) == 3, "Review should require the three missing review documents")
                        declarations = output / "synthetic-review-inputs" / case
                        declarations.mkdir(parents=True)
                        for slot in sorted(workflow.EDUCATION_OPTIONAL):
                            declaration = declarations / (slot + ".json")
                            workflow.write_json(declaration, {"purpose":"public-data workflow validation only", "slot":slot,
                                                              "independent_review_performed":False, "agency_approval":False})
                            bound = client.post(f"/api/cases/{case}/bindings", json={"slot":slot,"path":str(declaration)})
                            require(bound.status_code == 200, "Review-mode binding failed: " + bound.text)
                        require(not job({"kind":"check","case_id":case})["result"]["issues"], "Complete review input inventory rejected")
                        reviewed = job({"kind":"assess","case_id":case})["result"]
                        require(reviewed["assessment_verdict"] == row["verdict"] and not reviewed["authorized"], "Review declarations changed scientific/authorization result")
                        require(client.post(f"/api/cases/{case}/mode", json={"mode": "education"}).status_code == 200, "Education restore failed")
                        project = workflow.load_project(store.case_path(case))
                        binding = project.files["candidate"]
                        candidate = Path(binding.path)
                        if not candidate.is_absolute():
                            candidate = store.case_path(case) / candidate
                        original = candidate.read_bytes()
                        try:
                            candidate.write_bytes(original + b"\nVALIDATION_TAMPER")
                            tamper = job({"kind": "check", "case_id": case})["result"]
                            require(tamper["issues"], "Candidate tampering was not detected")
                            response = client.post("/api/jobs", json={"kind":"assess", "case_id":case})
                            require(response.status_code == 202, response.text)
                            work_once(store, worker)
                            require(store.job(response.json()["id"])["state"] == "failed", "Tampered candidate assessment accepted")
                        finally:
                            candidate.write_bytes(original)
                        require(workflow.digest(candidate) == binding.sha256, "Candidate restoration changed bytes")
                        restored = job({"kind": "check", "case_id": case})["result"]
                        require(not restored["issues"], "Restored case still has integrity issues")
                        row.update(status="PASS", reassessment="matched", review_mode="missing review documents rejected; three synthetic declarations bound; reassessment matched without authorization",
                                   candidate_tamper="detected; assessment rejected; original restored")
                except Exception as exc:
                    row["error"] = str(exc)
                    row["traceback"] = traceback.format_exc()
                row["duration_seconds"] = round(time.monotonic() - started, 3)
                report["training_matrix"].append(row)
                render_report(report, output)
                print(f"{preset} / {dataset}: {row['status']} ({row['duration_seconds']}s) {row.get('error', '')}", flush=True)

        reference = job({"kind": "reference"})
        require(len(reference["result"]["scenarios"]) == 8, "Reference scenario inventory changed")
        report["reference"] = {"job_id": reference["id"], "scenarios": reference["result"]["scenarios"], "export": exported(reference["id"])}
        queued = client.post("/api/jobs", json={"kind":"reference"}).json()
        require(client.post(f"/api/jobs/{queued['id']}/cancel", json={}).status_code == 200, "Queued cancellation failed")
        require(store.job(queued["id"])["state"] == "cancelled", "Cancelled job did not persist")
        retry = client.post(f"/api/jobs/{queued['id']}/retry", json={})
        require(retry.status_code == 202, retry.text)
        retried_id = retry.json()["id"]
        require(retried_id != queued["id"], "Retry overwrote previous attempt")
        work_once(store, worker)
        require(store.job(retried_id)["state"] == "completed", "Retried job did not execute")
        require(store.job(queued["id"])["state"] == "cancelled", "Retry changed historical job")
        report["queue_recovery"] = {"queued_cancel": "PASS", "explicit_retry": "PASS", "history_preserved": True}
        for model in language_models:
            row = {"model": model, "status": "FAIL"}
            try:
                done = job({"kind":"language", "language":{"model": model}})
                row.update(job_id=done["id"], result=done["result"])
                row["export"] = exported(done["id"])
                require(done["result"]["status"] == "completed", "Language controls, endpoint or model binding incomplete")
                row["status"] = "PASS"
            except Exception as exc:
                row["error"] = str(exc)
            report["language"].append(row)
            render_report(report, output)
            print(f"language / {model}: {row['status']}", flush=True)
        if not language_models:
            report["language_scope"] = "not requested; optional local endpoint tests were not executed"
        require(source_hashes() == report["implementation"], "Source changed during validation; rerun against stable sources")
        report["status"] = "PASS" if all(r["status"] == "PASS" for r in report["training_matrix"] + report["case_matrix"] + report["language"]) else "FAIL"
    except Exception as exc:
        report.update(status="FAIL", fatal_error=str(exc), fatal_traceback=traceback.format_exc())
    finally:
        stop.set()
        thread.join(timeout=4)
        client.close()
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        render_report(report, output)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--language-model", action="append", default=[], help="Installed local Ollama model; repeat to test multiple models")
    parser.add_argument("--preset", action="append", choices=list(PRESETS), help="Optional explicitly partial matrix")
    args = parser.parse_args()
    result = run(args.output, args.language_model, presets=args.preset)
    print(f"Validation {result['status']}: {args.output / 'validation-report.md'}")
    raise SystemExit(0 if result["status"] == "PASS" else 1)
