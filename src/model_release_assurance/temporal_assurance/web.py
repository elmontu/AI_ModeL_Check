"""Trusted-loopback web adapter for verified research and an existing ledger.

Mount behind the application's same-origin JSON and trusted-host middleware.
There is no upload, initialization, budget reset, arbitrary-file endpoint or
remote authentication here. Research results and operator state are separate:
a missing research corpus does not authorize, initialize or disable a ledger.
The local repository receipts, inventory and administrator remain trusted.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
import hashlib
import html
import json
from pathlib import Path
import re
import sqlite3
import threading
import time

from fastapi import APIRouter, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field

from .store import AssuranceError, AssuranceStore
from .pipeline import Pipeline, ensure_schema, has_schema


# Optional local input location. The service only reads an existing verified run
# and operator registry; selecting this path never initializes either one.
DEFAULT_ROOT = Path(".local/temporal-assurance")
EVIDENCE_RELATIVE = Path("reproduction/acs-temporal-assurance-20260921")
LIMITATIONS = [
    "Trusted local research operator; the authority label is not an authenticated agency role.",
    "Fixed-roster disability-attribute DP, not membership, whole-record or DP-SGD protection.",
    "Commitment spends budget even if a later download fails; revocation cannot recall earlier copies.",
    "Administrator rollback, direct-file bypass and real-person identity resolution are outside this boundary.",
]


def _sha(content):
    return hashlib.sha256(content).hexdigest()


def _json_file(path):
    content = path.read_bytes()
    return json.loads(content), content


class BackendError(RuntimeError):
    def __init__(self, code, detail, status=409):
        self.code, self.detail, self.status = code, detail, status
        super().__init__(detail)


class SafeRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()
        async def handler(request: Request):
            try:
                response = await original(request)
            except RequestValidationError:
                response = JSONResponse({"code": "invalid_request", "detail": "Request fields do not match the allowed schema."}, status_code=422)
            except BackendError as error:
                response = JSONResponse({"code": error.code, "detail": error.detail}, status_code=error.status)
            except AssuranceError as error:
                response = JSONResponse({"code": error.code, "detail": str(error)}, status_code=409)
            except (OSError, ValueError, KeyError, TypeError, sqlite3.Error):
                response = JSONResponse({"code": "evidence_unavailable", "detail": "Required local evidence is unavailable or inconsistent."}, status_code=503)
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Content-Type-Options"] = "nosniff"
            return response
        return handler


class PrepareBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    request_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,80}$")
    model_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,160}$")
    expected_revision: int = Field(ge=0, le=2**63 - 1)


class RequestBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    request_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,80}$")


class ReviewBody(RequestBody):
    check_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    rationale: str = Field(min_length=20, max_length=2000)
    accept_scope: bool


class Study:
    def __init__(self, repo, run):
        self.root = repo / EVIDENCE_RELATIVE
        self.run = run
        self.report = self.root / "report-v2"
        self.files = {
            "report.html": (self.report / "index.html", "text/html"),
            "report.md": (self.report / "REPORT.md", "text/plain"),
            "summary.md": (self.root / "README.md", "text/plain"),
            "theory.md": (self.root / "THEORY.md", "text/plain"),
            "verification.json": (self.root / "verification-v1.json", "application/json"),
        }
        for name in ("attribute-inference-trajectories", "privacy-budget-trajectories"):
            self.files[name + ".svg"] = (self.report / (name + ".svg"), "image/svg+xml")
            self.files[name + ".pdf"] = (self.report / (name + ".pdf"), "application/pdf")
        for name in ("attack_metrics", "budget_histograms", "prefix_metrics", "scenario_summaries", "utility_metrics"):
            self.files[name + ".csv"] = (self.report / (name + ".csv"), "text/csv")
        self.links = {
            "report_html": "/api/temporal/evidence/report.html", "report_markdown": "/api/temporal/evidence/report.md",
            "summary": "/api/temporal/evidence/summary.md", "theory": "/api/temporal/evidence/theory.md",
            "verification": "/api/temporal/evidence/verification.json",
            "inference_pdf": "/api/temporal/evidence/attribute-inference-trajectories.pdf",
            "budget_pdf": "/api/temporal/evidence/privacy-budget-trajectories.pdf",
            "inference_svg": "/api/temporal/evidence/attribute-inference-trajectories.svg",
            "budget_svg": "/api/temporal/evidence/privacy-budget-trajectories.svg",
            "scenario_csv": "/api/temporal/evidence/scenario_summaries.csv",
            "prefix_csv": "/api/temporal/evidence/prefix_metrics.csv",
            "attack_csv": "/api/temporal/evidence/attack_metrics.csv",
            "utility_csv": "/api/temporal/evidence/utility_metrics.csv",
        }

    def checked(self):
        receipt, _ = _json_file(self.root / "verification-v1.json")
        result, result_bytes = _json_file(self.run / "results.json")
        registration, registration_bytes = _json_file(self.run / "registration.json")
        completion, completion_bytes = _json_file(self.run / "completion.json")
        report_receipt, _ = _json_file(self.report / "verification.json")
        if (receipt.get("status") != "verified" or result.get("status") != "complete"
                or completion.get("status") != "complete" or report_receipt.get("status") != "complete"
                or Path(receipt["run"]).resolve() != self.run.resolve()
                or _sha(result_bytes) != receipt["results_sha256"]
                or _sha(registration_bytes) != receipt["registration_sha256"]
                or result.get("registration_sha256") != receipt["registration_sha256"]
                or completion.get("results_sha256") != receipt["results_sha256"]
                or report_receipt.get("results_sha256") != receipt["results_sha256"]
                or report_receipt.get("registration_sha256") != receipt["registration_sha256"]):
            raise BackendError("study_integrity_failure", "Study completion and verification bindings do not agree.", 503)
        for key in ("attempts", "admitted", "blocked"):
            if result.get(key) != receipt.get(key) or completion.get(key) != receipt.get(key):
                raise BackendError("study_integrity_failure", "Verified study counts do not agree.", 503)
        # The report receipt binds the completion bytes; the independent receipt
        # binds results/registration. No archive or private SQLite file is read.
        completion_key = str((self.run / "completion.json").resolve()).casefold()
        completion_hashes = {str(Path(k).resolve()).casefold(): value for k, value in report_receipt.get("checked_files", {}).items()}
        if completion_hashes.get(completion_key) != _sha(completion_bytes):
            raise BackendError("study_integrity_failure", "Study completion bytes differ from the checked report receipt.", 503)
        return receipt, result, registration, report_receipt

    def view(self):
        receipt, result, registration, _ = self.checked()
        scenario_keys = ("id", "policy", "admitted", "blocked", "final_full_member_ba", "final_full_nonmember_ba", "final_ledger", "lifecycle_controls")
        prefix_keys = ("scenario", "step", "arm", "family", "dataset", "model_id", "decision", "reason", "scoring",
                       "ledger", "attack", "query_only", "raw_bypass_control", "utility", "simulated_at")
        return {"status": "verified", "summary": {key: result.get(key) for key in
                ("study_id", "attempts", "admitted", "blocked", "distinct_source_models", "new_training_runs", "new_randomized_response_draws", "runtime_seconds")}
                | {"recipient_packages_verified": receipt["recipient_packages_verified"],
                   "metric_groups_rescored": receipt["metric_groups_rescored"],
                   "unit_channel_charges_reconstructed": receipt["unit_channel_charges_reconstructed"],
                   "scenario_count": len(result["scenarios"])},
                "scenarios": [{k: item[k] for k in scenario_keys if k in item} for item in result["scenarios"]],
                "schedule": registration["schedule"],
                "prefixes": [{k: item[k] for k in prefix_keys if k in item} for item in result["prefixes"]],
                "limitations": result["limitations"] + receipt.get("scope_limits", []), "links": self.links}

    def evidence(self, name):
        if name not in self.files:
            raise BackendError("not_found", "This evidence name is not in the public research allowlist.", 404)
        _, _, _, report_receipt = self.checked()
        path, media_type = self.files[name]
        # Reject a symlink that changes an allowlisted file into another file.
        if (path.resolve() != path.absolute()
                or path.resolve().parent not in {self.root.resolve(), self.report.resolve()}):
            raise BackendError("evidence_integrity_failure", "Evidence path left its allowlisted directory.", 503)
        content = path.read_bytes()
        if path.parent == self.report:
            if _sha(content) != report_receipt["report_files"][path.name]["sha256"]:
                raise BackendError("evidence_integrity_failure", "Report evidence differs from its verified bytes.", 503)
        headers = {"Content-Security-Policy": "default-src 'none'; script-src 'none'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'"}
        if media_type == "text/html":
            styles = re.findall(rb"<style(?:\s[^>]*)?>(.*?)</style\s*>", content, flags=re.I | re.S)
            hashes = " ".join("'sha256-" + base64.b64encode(hashlib.sha256(style).digest()).decode("ascii") + "'" for style in styles)
            headers["Content-Security-Policy"] = (
                "default-src 'none'; img-src 'self'; style-src 'self' " + hashes +
                "; script-src 'none'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
        elif media_type == "image/svg+xml":
            # ReportLab writes CSS as SVG style attributes. Permit only hashes
            # of those exact verified values; never enable scripts or arbitrary
            # inline CSS for other evidence or the interactive application.
            attributes = re.findall(r"\bstyle\s*=\s*([\"'])(.*?)\1", content.decode("utf-8"), flags=re.I | re.S)
            hashes = sorted({"'sha256-" + base64.b64encode(hashlib.sha256(html.unescape(value).encode()).digest()).decode("ascii") + "'"
                             for _, value in attributes})
            headers["Content-Security-Policy"] += "; style-src-attr 'unsafe-hashes' " + " ".join(hashes)
        if media_type in {"text/csv", "application/pdf"}:
            headers["Content-Disposition"] = f'attachment; filename="{path.name}"'
        return Response(content, media_type=media_type, headers=headers)


class ExistingStore(AssuranceStore):
    """Use the frozen broker without running its database-creation constructor."""
    def __init__(self, operator, *, request_id=None, operation=None):
        self.operator = operator
        inventory = operator.inventory()
        self.path = str(operator.db)
        self.scope_digest = inventory["scope_digest"]
        self.budget_micros = operator.budget(inventory)
        self.clock = time.time
        self.request_id = request_id
        self.operation = operation

    @contextmanager
    def _connection(self):
        # mode=rw is important: a missing ledger is never silently initialized.
        db = sqlite3.connect(Path(self.path).as_uri() + "?mode=rw", uri=True, timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=30000")
        db.execute("PRAGMA synchronous=FULL")
        try:
            yield db
        except BaseException:
            if db.in_transaction:
                db.rollback()
            raise
        finally:
            db.close()

    @contextmanager
    def _transaction(self):
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            inventory = self.operator.validate(db)
            if self.request_id is not None:
                row = db.execute("SELECT manifest FROM requests WHERE id=?", (self.request_id,)).fetchone()
                if row is None and self.operation != "prepare":
                    raise BackendError("unknown_request", "Request is not registered in this operator ledger.", 404)
                manifest = json.loads(row["manifest"]) if row else None
                if manifest and (manifest.get("model_id") not in {m["model_id"] for m in inventory["models"]}
                                 or manifest.get("authority_id") != inventory["authority_id"]):
                    raise BackendError("request_scope_mismatch", "Request is outside the website's initialized model and authority scope.", 403)
            pipeline = Pipeline(db, self, inventory, self.operator.inventory_hash, self.request_id)
            if self.operation in {"prepare", "checks", "review", "commit", "revoke"}:
                ensure_schema(db)
            if self.operation == "commit":
                pipeline.before_commit()
            elif self.operation == "download":
                if not has_schema(db):
                    raise AssuranceError("pipeline_review_required", "This package has no recorded website pipeline review.")
                pipeline.approval(committed=True)
            yield db
            if self.operation == "prepare":
                pipeline.prepared()
            elif self.operation == "commit":
                pipeline.after_commit()
            elif self.operation == "download":
                pipeline.delivery()
            elif self.operation == "revoke":
                pipeline.revoked()
            elif self.operation == "review":
                pipeline.approval()
            if self.operation in {"prepare", "review", "commit", "download"}:
                # Pipeline audit writes also consume time. Authorization must
                # still be current after those writes, at publication admission.
                final_request = db.execute("SELECT manifest FROM requests WHERE id=?", (self.request_id,)).fetchone()
                final_manifest = json.loads(final_request["manifest"])
                self._live(db, final_manifest["model_id"], final_manifest["authority_id"], None, check_integrity=False)
            db.commit()


class Operator:
    def __init__(self, root):
        self.root = root.resolve()
        self.db = self.root / "assurance.sqlite3"
        self.inventory_hash = None
        self.database_identity = None
        self.lock = threading.Lock()

    @staticmethod
    def budget(inventory):
        value = inventory["budget_epsilon"]
        if type(value) not in (int, float) or value < 0 or int(value * 1_000_000) != value * 1_000_000:
            raise BackendError("operator_configuration_changed", "Inventory budget is invalid.", 503)
        return int(value * 1_000_000)

    def inventory(self):
        inventory, content = _json_file(self.root / "workflow.json")
        if Path(inventory["db"]).resolve() != self.db or not self.db.is_file():
            raise BackendError("operator_unavailable", "The initialized operator ledger is missing or has a different path.", 503)
        models = inventory.get("models")
        if (inventory.get("status") != "registered_not_released" or not isinstance(models, list) or not models
                or any(not isinstance(model, dict) or not isinstance(model.get("model_id"), str)
                       or not re.fullmatch(r"[A-Za-z0-9_-]{1,160}", model["model_id"]) for model in models)
                or len({model["model_id"] for model in models}) != len(models)
                or not isinstance(inventory.get("authority_id"), str) or not inventory["authority_id"]):
            raise BackendError("operator_configuration_changed", "Operator inventory is not a supported initialization record.", 503)
        identity = (self.db.stat().st_dev, self.db.stat().st_ino)
        with self.lock:
            if self.inventory_hash is not None and self.inventory_hash != _sha(content):
                raise BackendError("operator_configuration_changed", "Operator inventory changed after it was loaded.", 503)
            if self.database_identity is not None and self.database_identity != identity:
                raise BackendError("operator_configuration_changed", "Operator ledger file was replaced.", 503)
            self.inventory_hash, self.database_identity = _sha(content), identity
        return inventory

    def validate(self, db):
        inventory = self.inventory()
        config = dict(db.execute("SELECT key,value FROM meta"))
        if (config.get("schema") != "1" or config.get("scope_digest") != inventory["scope_digest"]
                or config.get("budget_micros") != str(self.budget(inventory))):
            raise BackendError("operator_configuration_changed", "Ledger scope or budget differs from the initialized inventory.", 503)
        return inventory

    @contextmanager
    def readonly(self):
        self.inventory()
        db = sqlite3.connect(self.db.as_uri() + "?mode=ro", uri=True, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            db.execute("BEGIN")
            inventory = self.validate(db)
            yield db, inventory
            db.rollback()
        finally:
            db.close()

    @staticmethod
    def _validity(db, model_id, authority_id, now):
        def get(table, key, column="id"):
            return db.execute(f"SELECT * FROM {table} WHERE {column}=?", (key,)).fetchone()
        authority, model = get("authorities", authority_id), get("models", model_id)
        flags = {"authority_active": bool(authority and not authority["revoked"] and now < authority["expires_at"]),
                 "evidence_valid": True, "cache_valid": True, "dataset_valid": True, "artifact_valid": True,
                 "model_active": bool(model and now < model["expires_at"])}
        expires = [authority["expires_at"]] if authority else []
        reasons = []
        if not model:
            flags.update(evidence_valid=False, cache_valid=False, dataset_valid=False, artifact_valid=False)
        else:
            required = [("model", model), ("cache", get("caches", model["cache_id"])),
                        ("dataset", get("datasets", model["dataset_id"]))]
            if model["serving_cache_id"]:
                required.append(("cache", get("caches", model["serving_cache_id"])))
            for kind, item in required:
                if not item:
                    flags["evidence_valid"] = False
                    if kind + "_valid" in flags:
                        flags[kind + "_valid"] = False
                    continue
                expires.append(item["expires_at"])
                if now >= item["expires_at"] and kind + "_valid" in flags:
                    flags[kind + "_valid"] = False
                evidence = get("evidence", item["evidence"], "digest")
                if evidence:
                    expires.append(evidence["expires_at"])
                if (not evidence or evidence["invalidated"] or now >= evidence["expires_at"]
                        or _sha(evidence["payload"]) != evidence["digest"]):
                    flags["evidence_valid"] = False
            flags["artifact_valid"] = _sha(model["artifact"]) == model["artifact_digest"]
        reasons = [name for name, valid in flags.items() if not valid]
        return {"valid": all(flags.values()), "checked_at": now, "expires_at": min(expires, default=None),
                "reasons": reasons, **flags}

    @staticmethod
    def _preview(db, request, spent, existing, budget, revision):
        projected = dict(spent)
        new = 0
        for cache, units in json.loads(request["charge_records"]).items():
            cache_row = db.execute("SELECT epsilon FROM caches WHERE id=?", (cache,)).fetchone()
            if cache_row is None:
                return {"as_of_revision": revision, "within_budget": False, "reason": "missing_cache"}
            for unit in set(units):
                if (cache, unit) not in existing:
                    projected[unit] = projected.get(unit, 0) + cache_row["epsilon"]
                    new += 1
        maximum = max(projected.values(), default=0)
        return {"as_of_revision": revision, "maximum_spent_epsilon_after": maximum / 1_000_000,
                "minimum_remaining_epsilon_after": (budget - maximum) / 1_000_000,
                "new_unit_charges": new, "within_budget": maximum <= budget}

    def view(self):
        with self.readonly() as (db, inventory):
            revision = int(db.execute("SELECT value FROM meta WHERE key='revision'").fetchone()[0])
            now = int(time.time())
            spent, existing = {}, set()
            for row in db.execute("SELECT cache_id,record_id,epsilon FROM charges"):
                spent[row["record_id"]] = spent.get(row["record_id"], 0) + row["epsilon"]
                existing.add((row["cache_id"], row["record_id"]))
            budget = self.budget(inventory)
            models, validities = [], {}
            for entry in inventory["models"]:
                validity = self._validity(db, entry["model_id"], inventory["authority_id"], now)
                validities[entry["model_id"]] = validity
                model = db.execute("SELECT * FROM models WHERE id=?", (entry["model_id"],)).fetchone()
                provenance = {}
                if model:
                    cache = db.execute("SELECT * FROM caches WHERE id=?", (model["cache_id"],)).fetchone()
                    dataset = db.execute("SELECT * FROM datasets WHERE id=?", (model["dataset_id"],)).fetchone()
                    score_cache = db.execute("SELECT * FROM caches WHERE id=?", (model["serving_cache_id"],)).fetchone() if model["serving_cache_id"] else None
                    provenance = {"dataset_digest": model["dataset_id"], "attribute_version": dataset["attribute_version"] if dataset else None,
                        "training_units": len(json.loads(model["records"])), "serving_units": len(json.loads(model["serving_records"])),
                        "scoring": model["scoring"], "training_cache_id": model["cache_id"], "cache_id": model["cache_id"],
                        "cache_digest": cache["cache_digest"] if cache else None, "serving_cache_id": model["serving_cache_id"],
                        "epsilon_micros": cache["epsilon"] if cache else None,
                        "training_epsilon": cache["epsilon"] / 1_000_000 if cache else None,
                        "serving_epsilon": score_cache["epsilon"] / 1_000_000 if score_cache else None,
                        "artifact_digest": model["artifact_digest"],
                        "evidence_digests": sorted({row["evidence"] for row in (model, cache, dataset, score_cache) if row})}
                models.append({k: entry[k] for k in ("step", "model_id", "family", "dataset") if k in entry}
                              | {"validity": validity, "provenance": provenance})
            requests = []
            pipeline_store = ExistingStore(self)
            for row in db.execute("SELECT * FROM requests ORDER BY rowid DESC"):
                manifest = json.loads(row["manifest"])
                receipt = json.loads(row["receipt"]) if row["receipt"] else None
                validity = dict(validities.get(manifest["model_id"], {"valid": False, "reasons": ["unregistered_model"]}))
                in_scope = (manifest["model_id"] in validities and manifest.get("authority_id") == inventory["authority_id"])
                if not in_scope:
                    validity = {**validity, "valid": False,
                                "reasons": [*validity.get("reasons", []), "request_scope_mismatch"]}
                if row["revoked"]:
                    validity = {**validity, "valid": False, "reasons": [*validity.get("reasons", []), "release_revoked"]}
                state = "revoked" if row["revoked"] else "committed" if receipt else "prepared"
                preview = self._preview(db, row, spent, existing, budget, revision)
                pipeline = Pipeline(db, pipeline_store, inventory, self.inventory_hash, row["id"]).view(
                    core_validity=validity, core_state=state, revision=revision)
                keys = ("model_id", "scoring", "artifact_digest", "evidence_digests", "cache_footprints", "covered_units",
                        "new_unit_charges", "expected_revision", "prepared_at", "serving_units", "attribute_version")
                requests.append({k: manifest[k] for k in keys if k in manifest} | {
                    "request_id": row["id"], "state": state, "validity": validity,
                    "budget_preview": preview, "revision": receipt["revision"] if receipt else None,
                    "committed_at": receipt["committed_at"] if receipt else None,
                    "manifest_digest": receipt["manifest_digest"] if receipt else None,
                    "pipeline": pipeline, "can_check": pipeline["can_check"] and in_scope,
                    "can_review": pipeline["can_review"] and in_scope,
                    "can_commit": pipeline["can_commit"] and in_scope,
                    "can_download": pipeline["can_download"] and in_scope, "can_revoke": state != "revoked" and in_scope})
            maximum = max(spent.values(), default=0)
            return {"status": "available", "authority_id": inventory["authority_id"], "scope_digest": inventory["scope_digest"],
                "summary": {"revision": revision, "committed_releases": sum(bool(row[0]) for row in db.execute("SELECT receipt FROM requests")),
                    "budget_epsilon": budget / 1_000_000, "maximum_spent_epsilon": maximum / 1_000_000,
                    "minimum_remaining_epsilon": (budget - maximum) / 1_000_000,
                    "charged_units": len(spent), "mechanism_unit_charges": len(existing)},
                "models": models, "requests": requests,
                "workflow": {"version": "temporal-pipeline-v1", "server_enforced": True,
                    "required_stages": ["prepare", "checks", "review", "commit", "download"],
                    "review_kind": "trusted_local_operator_acknowledgement", "direct_core_access_outside_boundary": True},
                "validity": {"valid": all(v["valid"] for v in validities.values()), "checked_at": now,
                    "authority_active": all(v["authority_active"] for v in validities.values()),
                    "evidence_valid": all(v["evidence_valid"] for v in validities.values()),
                    "expires_at": min((v["expires_at"] for v in validities.values() if v["expires_at"] is not None), default=None)},
                "limitations": LIMITATIONS}

    def action(self, name, payload):
        inventory = self.inventory()
        models = {m["model_id"] for m in inventory["models"]}
        store = ExistingStore(self, request_id=payload.request_id, operation=name)
        if name == "prepare":
            if payload.model_id not in models:
                raise BackendError("unknown_model", "Choose a model from the initialized inventory.", 404)
            store.prepare(payload.request_id, payload.model_id, expected_revision=payload.expected_revision,
                          authority_id=inventory["authority_id"])
        elif name == "commit":
            store.commit(payload.request_id)
        elif name in {"checks", "review"}:
            error = None
            with store._transaction() as db:
                pipeline = Pipeline(db, store, inventory, self.inventory_hash, payload.request_id)
                if name == "checks":
                    error = pipeline.run_checks()
                else:
                    pipeline.review(payload.check_digest, payload.rationale, payload.accept_scope)
            if error:
                raise error
        else:
            store.revoke_release(payload.request_id)
        request = next(r for r in self.view()["requests"] if r["request_id"] == payload.request_id)
        return {"status": request["pipeline"]["state"], "request": request}

    def download(self, request):
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", request):
            raise BackendError("invalid_request", "Invalid request identifier.", 422)
        inventory = self.inventory()
        return ExistingStore(self, request_id=request, operation="download").download(request, authority_id=inventory["authority_id"])


def create_router(repo_root: Path, run_root: Path | None = None, operator_root: Path | None = None):
    router = APIRouter(prefix="/api/temporal", route_class=SafeRoute)
    study = Study(Path(repo_root).resolve(), Path(run_root) if run_root is not None else DEFAULT_ROOT / "run-v1")
    operator = Operator(Path(operator_root) if operator_root is not None else DEFAULT_ROOT / "operator-workflow-v1")

    @router.get("/study")
    def study_view():
        try:
            return study.view()
        except (BackendError, OSError, ValueError, KeyError, TypeError):
            return {"status": "unavailable", "code": "study_unavailable", "detail": "Verified study evidence is missing or inconsistent.",
                    "summary": {}, "scenarios": [], "schedule": [], "prefixes": [], "limitations": LIMITATIONS, "links": {}}

    @router.get("/operator")
    def operator_view():
        try:
            return operator.view()
        except (BackendError, OSError, ValueError, KeyError, TypeError, sqlite3.Error) as error:
            return {"status": "unavailable", "code": getattr(error, "code", "operator_unavailable"),
                    "detail": "The initialized operator inventory and ledger are unavailable or inconsistent.",
                    "summary": {}, "models": [], "requests": [], "validity": {"valid": False}, "limitations": LIMITATIONS}

    @router.get("/evidence/{name}")
    def evidence(name: str):
        return study.evidence(name)

    @router.post("/prepare")
    def prepare(payload: PrepareBody):
        return operator.action("prepare", payload)

    @router.post("/commit")
    def commit(payload: RequestBody):
        return operator.action("commit", payload)

    @router.post("/checks")
    def checks(payload: RequestBody):
        return operator.action("checks", payload)

    @router.post("/review")
    def review(payload: ReviewBody):
        return operator.action("review", payload)

    @router.post("/revoke")
    def revoke(payload: RequestBody):
        return operator.action("revoke", payload)

    @router.get("/downloads/{request_id}")
    def download(request_id: str):
        content = operator.download(request_id)
        return Response(content, media_type="application/zip", headers={
            "Content-Disposition": f'attachment; filename="{request_id}.zip"', "X-Artifact-SHA256": _sha(content)})

    return router
