"""Persistent local review gates layered on the unchanged assurance broker.

All writes use the caller's SAME SQLite transaction as the core operation.
No table is created by a status read. A review is a recorded acknowledgement by
the trusted local operator, not independent authentication or legal approval.
Privileged direct core/CLI/database access remains outside this web boundary.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import sqlite3

from .store import AssuranceError
from ..export_red_team import (evaluate_export_red_team, parse_policy_json,
                               parse_report_json, report_sha256)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value):
    return hashlib.sha256(value if isinstance(value, bytes) else value.encode()).hexdigest()


def fail(code, message):
    raise AssuranceError(code, message)


def ensure_schema(db):
    # executescript would implicitly commit an existing transaction. Individual
    # statements preserve the core commit + pipeline audit atomicity.
    for statement in (
        "CREATE TABLE IF NOT EXISTS tp_red_team(request_id TEXT PRIMARY KEY,report_json TEXT NOT NULL,report_digest TEXT NOT NULL,attached_at INTEGER NOT NULL)",
        "CREATE TABLE IF NOT EXISTS tp_checks(request_id TEXT PRIMARY KEY,binding_json TEXT NOT NULL,check_digest TEXT NOT NULL,checked_at INTEGER NOT NULL)",
        "CREATE TABLE IF NOT EXISTS tp_reviews(request_id TEXT PRIMARY KEY,check_digest TEXT NOT NULL,review_json TEXT NOT NULL,review_digest TEXT NOT NULL,reviewed_at INTEGER NOT NULL)",
        "CREATE TABLE IF NOT EXISTS tp_commits(request_id TEXT PRIMARY KEY,check_digest TEXT NOT NULL,review_digest TEXT NOT NULL,receipt_digest TEXT NOT NULL,committed_at INTEGER NOT NULL)",
        "CREATE TABLE IF NOT EXISTS tp_events(sequence INTEGER PRIMARY KEY AUTOINCREMENT,request_id TEXT NOT NULL,action TEXT NOT NULL,at INTEGER NOT NULL,detail TEXT NOT NULL)",
    ):
        db.execute(statement)


def has_schema(db):
    return db.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name IN ('tp_checks','tp_reviews','tp_commits','tp_events')").fetchone()[0] == 4


class Pipeline:
    def __init__(self, db, store, inventory, inventory_digest, request_id):
        self.db, self.store, self.inventory = db, store, inventory
        self.inventory_digest, self.request_id = inventory_digest, request_id

    def now(self):
        return self.store._operation_time(None)

    def event(self, action, message, **metadata):
        self.db.execute("INSERT INTO tp_events(request_id,action,at,detail) VALUES(?,?,?,?)",
                        (self.request_id, action, self.now(), canonical({"message": message, **metadata})))

    def row(self, table):
        return self.db.execute(f"SELECT * FROM {table} WHERE request_id=?", (self.request_id,)).fetchone()

    def request(self):
        row = self.db.execute("SELECT * FROM requests WHERE id=?", (self.request_id,)).fetchone()
        if row is None:
            fail("unknown_request", "Prepare a registered package before running pipeline checks.")
        if row["revoked"]:
            fail("release_revoked", "This release is revoked.")
        return row

    @staticmethod
    def records(text):
        values = json.loads(text)
        if (not isinstance(values, list) or any(not isinstance(v, str) or not v for v in values)
                or values != sorted(set(values))):
            fail("pipeline_lineage_mismatch", "Registered unit lists are not canonical unique unit sets.")
        return values

    @staticmethod
    def bound_row(row):
        return {k: digest(row[k]) if isinstance(row[k], bytes) else row[k] for k in row.keys()}

    def red_team(self, model=None, *, enforce=False):
        """Re-evaluate local screening without asserting privacy or release approval."""
        base = {"mode": "required", "required": True, "satisfied": False,
                "policy_sha256": None, "report_sha256": None,
                "can_clear": False, "authorization_eligible": False}
        if model is None:
            request = self.db.execute("SELECT manifest FROM requests WHERE id=?", (self.request_id,)).fetchone()
            model_id = json.loads(request["manifest"])["model_id"] if request else None
            model = self.db.execute("SELECT * FROM models WHERE id=?", (model_id,)).fetchone()
        entry = next((item for item in self.inventory["models"] if model and item["model_id"] == model["id"]), {})
        if entry.get("red_team_policy") is None:
            if self.inventory.get("red_team_mode") == "legacy_unassessed":
                result = {**base, "mode": "legacy_unassessed", "required": False,
                          "reasons": ["Legacy demonstration: red-team screening has not been assessed."]}
            else:
                result = {**base, "reasons": ["A trusted red-team policy is missing for this model."]}
        else:
            try:
                policy = parse_policy_json(canonical(entry["red_team_policy"]))
                report_row = None
                if self.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='tp_red_team'").fetchone():
                    report_row = self.row("tp_red_team")
                report = parse_report_json(report_row["report_json"]) if report_row else None
                result = {**base, **evaluate_export_red_team(policy, report,
                    artifact_sha256=model["artifact_digest"], now=datetime.fromtimestamp(self.now(), timezone.utc))}
                # Evaluation time changes without changing the reviewed evidence.
                result.pop("evaluated_at", None)
                result["tools"] = [item.model_dump(mode="json") for item in report.tools] if report else []
                reasons = list(result["reasons"])
                if model["scoring"] != "model_only" or policy.recipient_interface != "full_artifact":
                    reasons.append("This red-team profile supports only delivery of the full model-only artifact.")
                if (not entry.get("red_team_dataset_sha256")
                        or entry["red_team_dataset_sha256"] != policy.dataset_sha256):
                    reasons.append("The evaluation dataset and split identity is not pinned to this model's inventory.")
                if report_row and report_sha256(report) != report_row["report_digest"]:
                    reasons.append("The attached red-team report digest does not match its stored content.")
                result.update(reasons=reasons, satisfied=result["satisfied"] and not reasons)
            except (ValueError, TypeError, KeyError, AttributeError):
                result = {**base, "reasons": ["The red-team policy or attached report is invalid."]}
        if enforce and result["required"] and not result["satisfied"]:
            fail("pipeline_red_team_required", "Red-team screening is incomplete: " + "; ".join(result["reasons"]))
        return result

    def attach_red_team(self, report):
        if self.request()["receipt"]:
            fail("pipeline_stage_closed", "A committed release's red-team report cannot be replaced.")
        report_json = canonical(report.model_dump(mode="json"))
        report_digest = report_sha256(report)
        old = self.row("tp_red_team")
        if old and old["report_digest"] == report_digest and old["report_json"] == report_json:
            return
        self.db.execute("INSERT OR REPLACE INTO tp_red_team VALUES(?,?,?,?)",
                        (self.request_id, report_json, report_digest, self.now()))
        self.db.execute("DELETE FROM tp_reviews WHERE request_id=?", (self.request_id,))
        self.db.execute("DELETE FROM tp_checks WHERE request_id=?", (self.request_id,))
        summary = self.red_team()
        self.event("red_team_attached", "Red-team report attached; previous checks and local review were invalidated.",
                   report_digest=report_digest, red_team=summary)

    def snapshot(self, *, include_ledger):
        request = self.request()
        manifest = json.loads(request["manifest"])
        if (manifest.get("model_id") not in {m["model_id"] for m in self.inventory["models"]}
                or manifest.get("authority_id") != self.inventory["authority_id"]):
            fail("request_scope_mismatch", "Request is outside the initialized model and authority scope.")
        model, cache, dataset = self.store._live(self.db, manifest["model_id"], manifest["authority_id"], None)
        authority = self.store._get(self.db, "authorities", manifest["authority_id"])
        training = self.records(model["records"])
        if training != self.records(dataset["records"]) or not set(training).issubset(self.records(cache["records"])):
            fail("pipeline_lineage_mismatch", "Training units do not match their dataset and cache.")
        if dataset["attribute_version"] != cache["attribute_version"]:
            fail("pipeline_lineage_mismatch", "Dataset and training-cache attribute versions differ.")
        serving = self.records(model["serving_records"])
        caches = {cache["id"]: cache}
        scoring = model["scoring"]
        if scoring == "model_only":
            if serving or model["serving_cache_id"] is not None:
                fail("pipeline_lineage_mismatch", "Model-only registration contains a serving disclosure.")
        elif scoring in {"cached", "fresh"}:
            if not serving or not model["serving_cache_id"]:
                fail("pipeline_lineage_mismatch", "Scoring registration has no covered serving channel.")
            score_cache = self.store._get(self.db, "caches", model["serving_cache_id"])
            caches[score_cache["id"]] = score_cache
            if (not set(serving).issubset(self.records(score_cache["records"]))
                    or score_cache["attribute_version"] != dataset["attribute_version"]
                    or (scoring == "cached") != (score_cache["id"] == cache["id"])):
                fail("pipeline_lineage_mismatch", "Scoring channel membership, reuse or attribute version is invalid.")
        else:
            fail("serving_denied", "Unregistered raw or unknown serving mode.")
        footprints = self.store._footprints(model)
        if json.loads(request["charge_records"]) != footprints:
            fail("pipeline_footprint_mismatch", "Prepared charge units differ from the registered model and serving footprint.")
        covered = sorted(set().union(*map(set, footprints.values())))
        evidence_ids = sorted({model["evidence"], dataset["evidence"]} | {c["evidence"] for c in caches.values()})
        expected = {
            "schema": "temporal-assurance-v1", "request_id": self.request_id, "model_id": model["id"],
            "authority_id": self.inventory["authority_id"], "scope_digest": self.store.scope_digest,
            "privacy_scope": "fixed_roster_attribute_dp", "budget_micros": self.store.budget_micros,
            "cache_id": cache["id"], "cache_digest": cache["cache_digest"], "epsilon_micros": cache["epsilon"],
            "dataset_digest": dataset["id"], "artifact_digest": model["artifact_digest"],
            "evidence_digests": evidence_ids, "attribute_version": dataset["attribute_version"],
            "training_units_digest": digest(model["records"]), "covered_units_digest": digest(canonical(covered)),
            "covered_units": len(covered), "scoring": scoring, "serving_cache_id": model["serving_cache_id"],
            "serving_units_digest": digest(canonical(serving)), "serving_units": len(serving),
            "recipient_package_excludes_manifest": True,
            "cache_footprints": [{"cache_id": key, "cache_digest": caches[key]["cache_digest"],
                "epsilon_micros": caches[key]["epsilon"], "units": len(value), "units_digest": digest(canonical(value))}
                for key, value in sorted(footprints.items())],
        }
        if any(manifest.get(k) != v for k, v in expected.items()):
            fail("pipeline_manifest_mismatch", "Prepared manifest no longer matches current registered provenance.")
        registry = {"model": self.bound_row(model), "dataset": self.bound_row(dataset),
                    "caches": {key: self.bound_row(row) for key, row in caches.items()},
                    "evidence": {key: self.bound_row(self.store._get(self.db, "evidence", key)) for key in evidence_ids},
                    "authority": self.bound_row(authority)}
        result = {"static": {"manifest_digest": digest(request["manifest"]),
            "charge_records_digest": digest(request["charge_records"]), "inventory_digest": self.inventory_digest,
            "registry_digest": digest(canonical(registry)), "scope_digest": self.store.scope_digest,
            "model_id": model["id"], "authority_id": authority["id"], "artifact_digest": model["artifact_digest"],
            "red_team": self.red_team(model, enforce=True)}}
        if include_ledger:
            revision = self.store._revision(self.db)
            if revision != manifest.get("expected_revision"):
                fail("pipeline_stale", "Ledger changed after preparation; prepare a new request at the current revision.")
            needed = self.store._charge_plan(self.db, footprints)
            if len(needed) != manifest.get("new_unit_charges"):
                fail("pipeline_footprint_mismatch", "Prepared budget increment differs from the current ledger.")
            charges = [tuple(r) for r in self.db.execute("SELECT cache_id,record_id,epsilon,request_id FROM charges ORDER BY cache_id,record_id")]
            result["ledger"] = {"revision": revision, "charges_digest": digest(canonical(charges)),
                                "expected_committed_charges_digest": digest(canonical(sorted(charges + [
                                    (cache_id, unit, epsilon, self.request_id) for cache_id, unit, epsilon in needed]))),
                                "new_unit_charges": len(needed)}
        # Recheck authority/evidence time after all registry and ledger work.
        self.store._live(self.db, model["id"], authority["id"], None, check_integrity=False)
        self.red_team(model, enforce=True)
        return result

    def prepared(self):
        if not self.db.execute("SELECT 1 FROM tp_events WHERE request_id=? AND action='prepared'", (self.request_id,)).fetchone():
            request = self.request()
            self.event("prepared", "Registered package prepared; no privacy budget has been committed.",
                       manifest_digest=digest(request["manifest"]))

    def run_checks(self):
        request = self.request()
        if request["receipt"]:
            fail("pipeline_stage_closed", "Checks must be completed before the package is committed.")
        try:
            binding = self.snapshot(include_ledger=True)
            binding_json = canonical(binding)
            check_digest = digest(binding_json)
            old = self.row("tp_checks")
            if old and old["check_digest"] == check_digest and old["binding_json"] == binding_json:
                self.snapshot(include_ledger=True)
                return None
            self.db.execute("DELETE FROM tp_reviews WHERE request_id=?", (self.request_id,))
            self.db.execute("INSERT OR REPLACE INTO tp_checks VALUES(?,?,?,?)",
                            (self.request_id, binding_json, check_digest, self.now()))
            self.event("checks_passed", "Current provenance, unit coverage, artifacts, evidence and budget checks passed.", check_digest=check_digest)
            self.snapshot(include_ledger=True)
            return None
        except (AssuranceError, ValueError, KeyError, TypeError) as caught:
            error = caught if isinstance(caught, AssuranceError) else AssuranceError(
                "pipeline_invalid_evidence", "Prepared or registered evidence cannot be decoded into the required binding.")
            # This explicit failed refresh must durably invalidate old review.
            # The caller raises the HTTP failure only after this transaction.
            self.db.execute("DELETE FROM tp_reviews WHERE request_id=?", (self.request_id,))
            self.db.execute("DELETE FROM tp_checks WHERE request_id=?", (self.request_id,))
            self.event("checks_failed", "Checks failed; any previous local review was invalidated.", code=error.code)
            return error

    def checked(self, *, include_ledger):
        check = self.row("tp_checks")
        if not check:
            fail("pipeline_checks_required", "Run the server checks before recording a local review or committing.")
        if digest(check["binding_json"]) != check["check_digest"]:
            fail("pipeline_integrity_failure", "Stored check evidence was modified.")
        original, current = json.loads(check["binding_json"]), self.snapshot(include_ledger=include_ledger)
        if original["static"] != current["static"] or (include_ledger and original.get("ledger") != current.get("ledger")):
            fail("pipeline_stale", "The checked inputs or ledger changed; run checks again before review.")
        return check

    def review(self, check_digest, rationale, accept_scope):
        if self.request()["receipt"]:
            fail("pipeline_stage_closed", "A review must precede the release commitment.")
        if accept_scope is not True or not isinstance(rationale, str) or not 20 <= len(rationale.strip()) <= 2000:
            fail("pipeline_review_invalid", "A scope acknowledgement and a substantive 20–2000 character local review are required.")
        check = self.checked(include_ledger=True)
        if check_digest != check["check_digest"]:
            fail("pipeline_stale_check", "Review references a different server check digest.")
        old = self.row("tp_reviews")
        if old:
            prior = json.loads(old["review_json"])
            if (prior.get("rationale") == rationale.strip() and old["check_digest"] == check_digest
                    and digest(old["review_json"]) == old["review_digest"]):
                return
        now = self.now()
        review_json = canonical({"request_id": self.request_id, "check_digest": check_digest,
            "rationale": rationale.strip(), "accept_scope": True, "authority_id": self.inventory["authority_id"],
            "reviewed_at": now, "review_kind": "trusted_local_operator_acknowledgement"})
        self.checked(include_ledger=True)
        self.db.execute("INSERT OR REPLACE INTO tp_reviews VALUES(?,?,?,?,?)",
                        (self.request_id, check_digest, review_json, digest(review_json), now))
        self.event("review_recorded", "Local operator review recorded for the exact checked proposal.",
                   check_digest=check_digest, review_digest=digest(review_json), review=json.loads(review_json))

    def approval(self, *, committed=False):
        check = self.checked(include_ledger=not committed)
        review = self.row("tp_reviews")
        if not review:
            fail("pipeline_review_required", "Record the local review before committing or downloading.")
        value = json.loads(review["review_json"])
        if (review["check_digest"] != check["check_digest"] or digest(review["review_json"]) != review["review_digest"]
                or value.get("check_digest") != check["check_digest"] or value.get("request_id") != self.request_id
                or value.get("authority_id") != self.inventory["authority_id"] or value.get("accept_scope") is not True):
            fail("pipeline_integrity_failure", "The stored review is not bound to these checked inputs.")
        if committed:
            publication = self.row("tp_commits")
            request = self.request()
            if (not publication or not request["receipt"] or publication["check_digest"] != check["check_digest"]
                    or publication["review_digest"] != review["review_digest"]
                    or publication["receipt_digest"] != digest(request["receipt"])):
                fail("pipeline_commit_required", "No matching reviewed pipeline commitment authorizes this package.")
        return check, review

    def before_commit(self):
        request = self.request()
        self.approval(committed=bool(request["receipt"]))

    def after_commit(self):
        request = self.request()
        if self.row("tp_commits"):
            self.approval(committed=True)
            return
        check, review = self.approval_after_new_commit()
        receipt = json.loads(request["receipt"])
        self.db.execute("INSERT INTO tp_commits VALUES(?,?,?,?,?)", (self.request_id, check["check_digest"],
            review["review_digest"], digest(request["receipt"]), receipt["committed_at"]))
        self.event("committed", "Reviewed package and all new unit/channel charges committed atomically.", receipt=receipt,
                   check_digest=check["check_digest"], review_digest=review["review_digest"])

    def approval_after_new_commit(self):
        check = self.checked(include_ledger=False)
        review = self.row("tp_reviews")
        if not review or review["check_digest"] != check["check_digest"] or digest(review["review_json"]) != review["review_digest"]:
            fail("pipeline_review_required", "Matching reviewed evidence disappeared before commitment.")
        receipt = json.loads(self.request()["receipt"])
        original = json.loads(check["binding_json"])
        charges = [tuple(r) for r in self.db.execute("SELECT cache_id,record_id,epsilon,request_id FROM charges ORDER BY cache_id,record_id")]
        if (receipt["revision"] != original["ledger"]["revision"] + 1
                or self.store._revision(self.db) != receipt["revision"]
                or digest(canonical(charges)) != original["ledger"]["expected_committed_charges_digest"]
                or receipt["manifest_digest"] != original["static"]["manifest_digest"]
                or receipt["artifact_digest"] != original["static"]["artifact_digest"]
                or receipt["new_unit_charges"] != original["ledger"]["new_unit_charges"]):
            fail("pipeline_integrity_failure", "The committed receipt differs from the reviewed publication.")
        return check, review

    def delivery(self):
        self.approval(committed=True)
        request = self.request()
        receipt = json.loads(request["receipt"])
        self.event("delivery_authorized", "Exact committed bytes authorized for download; recipient receipt is not asserted.",
                   artifact_digest=receipt["artifact_digest"], receipt_digest=digest(request["receipt"]))

    def revoked(self):
        if not self.db.execute("SELECT 1 FROM tp_events WHERE request_id=? AND action='revoked'", (self.request_id,)).fetchone():
            self.event("revoked", "Future website delivery revoked; past disclosure and charged privacy budget retained.")

    def view(self, *, core_validity, core_state, revision):
        exists = has_schema(self.db)
        check, review, publication = (self.row(name) if exists else None for name in ("tp_checks", "tp_reviews", "tp_commits"))
        events = []
        if exists:
            for row in self.db.execute("SELECT * FROM tp_events WHERE request_id=? ORDER BY sequence", (self.request_id,)):
                detail = json.loads(row["detail"])
                events.append({"sequence": row["sequence"], "action": row["action"], "at": row["at"],
                               "detail": detail.get("message", row["action"]), "metadata": {k: v for k, v in detail.items() if k != "message"}})
        state, reason, detail = "prepared", None, "Run server checks for the prepared package."
        if core_state == "revoked":
            state, reason, detail = "revoked", "release_revoked", "Future delivery is revoked; earlier spending remains."
        elif not core_validity.get("valid"):
            state, reason, detail = "blocked", "current_evidence_invalid", "Current authority, evidence, artifact or scope is invalid."
        elif core_state == "committed" and not publication:
            state, reason, detail = "blocked", "pipeline_commit_required", "This core commitment has no recorded pipeline approval."
        else:
            try:
                if publication:
                    self.approval(committed=True)
                    state, detail = "committed", "Reviewed committed bytes are eligible for an explicit download."
                elif check:
                    self.checked(include_ledger=True)
                    state, detail = "checked", "Checks passed; record the local scope review."
                    if review:
                        self.approval()
                        state, detail = "reviewed", "Checks and local review match; commit is the next stage."
                else:
                    self.snapshot(include_ledger=True)
                    if events and events[-1]["action"] == "checks_failed":
                        state, reason, detail = "blocked", "pipeline_checks_required", "Previous checks failed; run checks again."
            except (AssuranceError, ValueError, KeyError, TypeError, sqlite3.Error) as error:
                state = "stale" if getattr(error, "code", "") in {"pipeline_stale", "revision_conflict", "pipeline_stale_check"} else "blocked"
                reason, detail = getattr(error, "code", "pipeline_integrity_failure"), str(error)
        can_check = core_state == "prepared" and core_validity.get("valid", False)
        can_review = state == "checked"
        can_commit, can_download = state == "reviewed", state == "committed"
        stages = []
        for identity, label, complete, ready in (
            ("prepare", "Prepare exact package", True, False),
            ("checks", "Run current assurance checks", bool(check), can_check and not check),
            ("review", "Record local scope review", bool(review), can_review),
            ("commit", "Commit release and budget", bool(publication), can_commit),
            ("download", "Authorize exact-byte download", any(e["action"] == "delivery_authorized" for e in events), can_download),
            ("revoke", "Retire future delivery", core_state == "revoked", core_state != "revoked"),
        ):
            status = "complete" if complete else "ready" if ready else "pending"
            if state in {"blocked", "stale", "revoked"} and identity not in {"prepare", "revoke"}:
                status = "blocked" if identity != "download" or not complete else "complete"
            stages.append({"id": identity, "label": label, "status": status, "detail": detail if status == "blocked" else label})
        return {"state": state, "reason": reason, "detail": detail, "stages": stages,
            "red_team": self.red_team(), "can_attach_red_team": core_state == "prepared",
            "check_digest": check["check_digest"] if check else None, "checked_at": check["checked_at"] if check else None,
            "reviewed_at": review["reviewed_at"] if review else None,
            "review_rationale": json.loads(review["review_json"]).get("rationale") if review else None,
            "review_kind": "trusted_local_operator_acknowledgement", "events": events,
            "can_check": can_check, "can_review": can_review, "can_commit": can_commit, "can_download": can_download,
            "ledger_revision": revision}
