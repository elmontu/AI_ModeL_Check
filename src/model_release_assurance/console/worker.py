"""Execute allowlisted jobs outside the HTTP process."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import traceback
import uuid
from pathlib import Path

from .. import workflow
from .store import Store


def attach_training_case(store: Store, job: dict, output: Path, report: dict) -> str:
    """Inventory actual demo outputs; keep request paths relative to their original root."""
    artifacts = report["artifacts"]
    def artifact(key):
        ref = artifacts[key]
        path = (output / ref["path"]).resolve()
        if not path.is_relative_to(output.resolve()) or workflow.digest(path) != ref["sha256"]:
            raise ValueError("training output binding mismatch")
        return path
    candidate = artifact("release_bundle")
    original_request = artifact("assessment_request")
    request = output / "console-assessment-request.json"
    request.write_bytes(original_request.read_bytes())
    case = store.create_case(job["options"]["name"], "trained", "named-party-weights", "education")
    root = store.case_path(case["id"])
    for slot, path in {"candidate": candidate, "request": request,
                       "evaluation-plan": artifact("statistical_family_plan")}.items():
        workflow.bind(root, slot, path)
    utility = output / "console-utility.json"
    workflow.write_json(utility, {"source": "public teaching run", "utility": report["training"]["utility"],
                                  "limitations": report["limitations"]})
    workflow.bind(root, "utility-report", utility)
    overlap = output / "console-overlap.json"
    workflow.write_json(overlap, {"population_overlap": "single-source", "parents": [],
                                  "dataset_sha256": report["dataset"]["dataset_sha256"],
                                  "note": "Single public dataset; newly trained candidate, no parent models."})
    raw_request = json.loads(request.read_text(encoding="utf-8"))
    workflow.create_lineage(root, [], artifact("training_config"), artifact("dataset_source"),
                            overlap, "single-source", raw_request["release"]["previous_release_ids"])
    preflight, _, _ = workflow.inspect_project(root)
    if preflight["issues"]:
        raise ValueError("generated training case failed preflight: " + str(preflight["issues"]))
    return case["id"]


def execute(store: Store, job: dict) -> dict:
    job_root = store.root / "jobs" / job["id"]
    job_root.mkdir(parents=True, exist_ok=True)
    if job["kind"] in {"check", "assess"}:
        root = store.case_path(job["case_id"])
        if job["kind"] == "check":
            result, _, _ = workflow.inspect_project(root)
            workflow.write_json(job_root / "preflight.json", result)
            return result
        before = set((root / "runs").glob("*"))
        try:
            run = workflow.assess(root)
        finally:
            created = set((root / "runs").glob("*")) - before
            if len(created) == 1:
                workflow.write_json(job_root / "workflow-run.json", {
                    "relative_path": next(iter(created)).relative_to(store.root).as_posix()})
        result = json.loads((run / "workflow-result.json").read_text())
        result["report"] = json.loads((run / "assessment-report.json").read_text())
        result["artifact_directory"] = run.relative_to(store.root).as_posix()
        return result

    if job["kind"] == "language":
        root = store.root / "jobs" / job["id"]
        root.mkdir(parents=True, exist_ok=True)
        store.progress(job, "Running local language, document-injection and inert-tool tests")
        with (root / "worker.log").open("w",encoding="utf-8") as log:
            subprocess.run([sys.executable,"-m","model_release_assurance.language_red_team","--model",job["options"]["model"],
                            "--output",str(root / "artifacts")],stdout=log,stderr=subprocess.STDOUT,timeout=1200,check=True,
                           creationflags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0)
        result=json.loads((root / "artifacts" / "result.json").read_text(encoding="utf-8"))
        result["artifact_directory"]=f"jobs/{job['id']}/artifacts"
        return result

    if job["kind"] == "training" and job.get("options", {}) and job["options"]["preset"] != "xgboost-small":
        options = job["options"]
        root = store.root / "jobs" / job["id"]
        root.mkdir(parents=True, exist_ok=True)
        output = root / "artifacts"
        store.progress(job, "Training selected model and running compatible red-team tools")
        with (root / "worker.log").open("w", encoding="utf-8") as log:
            subprocess.run([sys.executable, "-m", "model_release_assurance.public_models", "--preset", options["preset"],
                            "--dataset", options["dataset"], "--output", str(output)], stdout=log, stderr=subprocess.STDOUT,
                           timeout=600, check=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        result = json.loads((output / "result.json").read_text(encoding="utf-8"))
        kind = "ensemble" if options["preset"] == "ensemble" else "fine-tuned" if options["preset"] == "mlp-finetuned" else "trained"
        case = store.create_case(options["name"], kind, "named-party-weights", "education")
        case_root = store.case_path(case["id"])
        for slot, name in {"candidate":"model.joblib","evaluation-plan":"family-plan.json","utility-report":"utility-report.json","request":"assessment-request.json"}.items():
            workflow.bind(case_root, slot, output / name)
        parents = [[item["component"], str(output / item["path"])] for item in result["component_comparisons"]]
        overlap = output / "overlap.json"
        workflow.write_json(overlap, {"population_overlap":"overlapping" if parents else "single-source", "note":"all components use the same public training partition"})
        workflow.create_lineage(case_root, parents, output / "training-config.json", output / "data-manifest.json", overlap,
                                "overlapping" if parents else "single-source", [])
        preflight, _, _ = workflow.inspect_project(case_root)
        if preflight["issues"]:
            raise ValueError("generated training case failed preflight: " + str(preflight["issues"]))
        result["case_id"] = case["id"]
        result["artifact_directory"] = f"jobs/{job['id']}/artifacts"
        result["next_step"] = "Review the registered membership assessment and remaining threat coverage; no release authorization is issued."
        return result

    repo = Path(__file__).resolve().parents[3]
    script = repo / "scripts" / ("run_training_release_demo.py" if job["kind"] == "training" else "run_government_health_demo.py")
    if not script.is_file():
        raise ValueError("demonstrations require the source checkout or console container image")
    root = store.root / "jobs" / job["id"]
    root.mkdir(parents=True, exist_ok=True)
    output = root / "artifacts"
    if job["kind"] == "training":
        args = ["--dataset-profile", "sklearn-breast-cancer", "--run-dir", str(output), "--red-team"]
        report_name = "pipeline-report.json"
    else:
        args = ["--output-root", str(root), "--run-id", "artifacts"]
        report_name = "suite-report.json"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo / "src")
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    with (root / "worker.log").open("w", encoding="utf-8") as log:
        with subprocess.Popen([sys.executable, str(script), *args], cwd=repo, env=env,
                              stdout=log, stderr=subprocess.STDOUT, creationflags=flags) as process:
            deadline = time.monotonic() + 600
            previous = None
            while True:
                stage = "Preparing public data" if job["kind"] == "training" else "Running reference scenarios"
                for marker, label in (("intake/data-source.json", "Freezing evaluation plan"),
                                      ("plan/training-config.json", "Training and exporting XGBoost"),
                                      ("contracts/release-contract.json", "Collecting membership evidence"),
                                      ("assessment/assessment-report.json", "Recording assessment")):
                    if (output / marker).is_file():
                        stage = label
                if stage != previous:
                    store.progress(job, stage)
                    previous = stage
                try:
                    code = process.wait(timeout=1)
                    if code:
                        raise subprocess.CalledProcessError(code, script)
                    break
                except subprocess.TimeoutExpired:
                    if time.monotonic() > deadline:
                        process.kill()
                        process.wait()
                        raise TimeoutError("training/demo exceeded ten minutes")
    report = json.loads((output / report_name).read_text(encoding="utf-8"))
    # Summaries deliberately omit absolute paths, raw rows and arbitrary log output.
    if job["kind"] == "training":
        case_id = None
        if job.get("options"):
            store.progress(job, "Attaching model and evidence to education case")
            case_id = attach_training_case(store, job, output, report)
        return {"case_id": case_id, "training": report["training"], "pipeline": report["pipeline"],
                "artifact_directory": f"jobs/{job['id']}/artifacts",
                "red_team": json.loads((output / "evidence" / "red-team-report.json").read_text(encoding="utf-8")),
                "demo": "real-public-data-training", "authorization_eligible": False,
                "authorized": False, "deployed": False,
                "verdict": report["assessment"]["verdict"],
                "workflow_state": report["workflow"]["final_state"],
                "training_executed": report["training_executed"],
                "dataset": {key: report["dataset"][key] for key in ("name", "rows", "features")},
                "evidence": report["evidence"], "bindings": report["bindings"],
                "limitations": report["limitations"]}
    return {"demo": "synthetic-reference-scenarios", "authorization_eligible": False,
            "artifact_directory": f"jobs/{job['id']}/artifacts",
            "authorized": False, "deployed": False,
            "scenarios": [{"scenario_id": r["scenario_id"], "result": r["result"]} for r in report["scenarios"]],
            "limitations": report["limitations"]}


def work_once(store: Store, worker: str) -> bool:
    store.recover()
    job = store.claim(worker)
    if job is None:
        return False
    root = store.root / "jobs" / job["id"]
    root.mkdir(parents=True, exist_ok=True)
    try:
        workflow.write_json(root / "job-input.json", {"id":job["id"], "kind":job["kind"], "case_id":job["case_id"],
                                                    "options":job["options"], "retry_of":job.get("retry_of")})
        result = execute(store, job)
        workflow.write_json(root / "console-result.json", result)
        store.finish(job["id"], worker, result=result)
    except Exception as exc:
        # Detailed source diagnostics stay in protected workflow/worker artifacts.
        (root / "worker-error.log").write_text(traceback.format_exc(), encoding="utf-8")
        store.finish(job["id"], worker, error=f"{type(exc).__name__}: job did not complete. Download retained artifacts for diagnostics, correct inputs, then retry.")
    return True


def run(root: Path):
    store = Store(root)
    worker = uuid.uuid4().hex
    stop = threading.Event()

    def heartbeat():
        while not stop.is_set():
            store.heartbeat(worker)
            stop.wait(5)

    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    try:
        while True:
            if not work_once(store, worker):
                time.sleep(0.5)
    finally:
        stop.set()
        thread.join(timeout=6)
