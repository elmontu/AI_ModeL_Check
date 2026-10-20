"""Shared public synthetic histories without changing historical research code.

Aliases reuse one retained draw and one prospective usefulness experiment. A
shared reservation precedes all informative sampling, and uncertain reservations
remain blocked. This local witness is a custody fixture, not agency authority.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from . import web, usefulness_store
from .certificates import ResearchContext, SOURCE_PDF_SHA256, build_certificate, certificate_digest
from .cli import _keys, _load
from .disclosure_history import HistoryLedger, HistoryError

_RUNTIME_FILES = ("disclosure_history.py", "history_store.py", "history_routes.py", "history_console_app.py")
_REGISTRATION = "history-registration.json"
_OUTPUTS = ("randomized-block.json", "sample-reservation.json", "sampling-completion.json")


def _runtime_digest() -> str:
    base = Path(__file__).parent
    hashes = {name: web._sha(web._read_file(base / name)) for name in _RUNTIME_FILES}
    return web._sha(web._json_bytes({"implementation_sha256": hashes, "phase2_runtime": usefulness_store._runtime()}))


class HistoryRunStore(usefulness_store.UsefulnessRunStore):
    """Extend immutable research runs with a shared, witnessed history ledger."""

    def __init__(self, data_dir: str | Path, *, source_pdf: str | Path = web.DEFAULT_SOURCE_PDF,
                 usefulness_dir: str | Path | None = None, history_dir: str | Path | None = None,
                 witness_dir: str | Path | None = None):
        super().__init__(data_dir, source_pdf=source_pdf, usefulness_dir=usefulness_dir)
        self.history_root = (Path(history_dir).absolute() if history_dir is not None
                             else self.root.with_name(self.root.name + "-history"))
        self.witness_root = (Path(witness_dir).absolute() if witness_dir is not None
                             else self.root.with_name(self.root.name + "-history-witness"))
        if len({self.root, self.usefulness_root, self.history_root, self.witness_root}) != 4:
            raise web.ResearchWebError("Research, usefulness, history and witness storage must be separate")
        self.ledger = HistoryLedger(self.history_root, self.witness_root)

    def catalog(self) -> dict[str, Any]:
        result = super().catalog()
        result.update({"history_reservation": "shared public synthetic history; one retained RR and one certified continuation",
                       "history_scope": "Local custody witness fixture; agency administration and production qualification remain pending."})
        return result

    def _bindings(self, run_id: str) -> dict[str, Any]:
        _, manifest, _, context, data, verified, _ = self._inputs(run_id, check_source=True)
        return {
            "preset": manifest["preset"], "source_pdf_sha256": SOURCE_PDF_SHA256,
            "retained_law_sha256": context.retained_law_sha256,
            "retained_response_sha256": context.retained_response_sha256,
            "complete_history_sha256": context.complete_history_sha256,
            "request_plan_sha256": context.request_plan_sha256,
            "certificate_sha256": verified.digest, "labels_sha256": manifest["labels_sha256"],
            "source_input_sha256": {name: web._sha(raw) for name, raw in data.items()},
            "runtime_sha256": _runtime_digest(),
        }

    @staticmethod
    def _declaration(snapshot: dict[str, Any], run_id: str) -> dict[str, Any]:
        owner = snapshot["owner_run_id"]
        return {
            "schema": "mra-public-shared-history-registration/1.0", "run_id": run_id,
            "history_id": snapshot["history_id"], "owner_run_id": owner,
            "origin": "created_before_retained_draw" if owner == run_id else "alias_reuses_registered_retained_draw",
            "public_synthetic": True, **web.AUTHORITY,
        }

    def _history(self, run_id: str, *, require_runtime: bool = False) -> dict[str, Any] | None:
        self._directory(run_id)
        snapshot = self.ledger.history_for_run(run_id)
        declaration = self.root / run_id / _REGISTRATION
        web._check_path(declaration)
        if snapshot is None:
            if declaration.exists():
                raise web.ResearchWebError("Shared history registration has no witnessed ledger entry")
            return None
        raw = web._read_file(declaration)
        if raw != web._json_bytes(self._declaration(snapshot, run_id)):
            raise web.ResearchWebError("The shared history registration is missing or changed")
        bound = self._bindings(run_id)
        retained = snapshot.get("retained_bindings")
        if retained is None:
            return snapshot
        if not require_runtime:
            # Historical inspection pins saved source bytes while the current
            # implementation identity is required for any new execution.
            bound["runtime_sha256"] = retained["runtime_sha256"]
        if web._json_bytes(bound) != web._json_bytes(retained):
            raise web.ResearchWebError("Shared retained inputs differ from the witnessed history binding")
        return snapshot

    def create(self, preset: str) -> dict[str, Any]:
        if type(preset) is not str or preset not in web.PRESETS:
            raise web.ResearchWebError("Choose a fixed public research preset", 422)
        self._source()
        spec, dataset = self._frozen(write=True)
        run_id = uuid4().hex
        parameters = web.PRESETS[preset]
        records = web._roster()
        labels = {"schema": web.LABELS_SCHEMA, "records": records}
        request = {"schema": web.REQUEST_SCHEMA, "parameters": parameters.to_dict(),
                   "record_ids": [record["record_id"] for record in records], "visible_decisions": "public_fixed"}
        snapshot = self.ledger.create_history(run_id, {
            "preset": preset, "source_pdf_sha256": SOURCE_PDF_SHA256,
            "labels_sha256": web._sha(web._json_bytes(labels)),
            "request_plan_sha256": web._sha(web._json_bytes(request)),
            "parameters": parameters.to_dict(), "public_synthetic": True,
        })
        directory, phase = self.root / run_id, self.usefulness_root / run_id
        web._check_path(directory)
        web._check_path(phase)
        directory.mkdir(exist_ok=False)
        phase.mkdir(exist_ok=False)
        web._write_exclusive(directory / _REGISTRATION, self._declaration(snapshot, run_id))
        usefulness_store._json(phase / "prospective.json", {
            "schema": "mra-public-usefulness-prospective/1.0", "run_id": run_id,
            "preset": preset, "registered_at": web._now(),
            "specification_sha256": web._sha(web._json_bytes(spec)),
            "dataset_sha256": web._sha(web._json_bytes(dataset)), "runtime": usefulness_store._runtime(),
            "registered_before_retained_response": True, **web.AUTHORITY,
        })
        # Both history initialization and prospective experiment registration
        # are durable before even the first retained randomized response.
        for name, value in (
            ("synthetic-labels.json", labels),
            ("retained-law.json", {"schema": web.LAW_SCHEMA, "d": parameters.to_dict()["d"]}),
            ("retained-responses.json", {"schema": web.RESPONSES_SCHEMA, "records": [
                {"record_id": record["record_id"], "w": record["labels"][0]
                 if web.secrets.randbelow(parameters.d.numerator + parameters.d.denominator) < parameters.d.numerator
                 else 1 - record["labels"][0]} for record in records]}),
        ):
            web._write_exclusive(directory / name, value)
        digest = lambda name: web._sha(web._read_file(directory / name))
        law_digest, response_digest = digest("retained-law.json"), digest("retained-responses.json")
        web._write_exclusive(directory / "history.json", {
            "schema": web.HISTORY_SCHEMA, "retained_law_sha256": law_digest,
            "retained_response_sha256": response_digest, "additional_protected_outputs": False,
        })
        web._write_exclusive(directory / "request-plan.json", request)
        context = ResearchContext(law_digest, response_digest, digest("history.json"), digest("request-plan.json"))
        web._write_exclusive(directory / "plan.json", {
            "schema": web.PLAN_SCHEMA, "parameters": parameters.to_dict(), "context": context.to_dict(),
        })
        certificate = build_certificate(parameters, context)
        web._write_exclusive(directory / "certificate.json", certificate)
        web._write_exclusive(directory / "run.json", {
            "schema": "mra-rr-public-web-run/1.0", "run_id": run_id, "preset": preset,
            "created_at": web._now(), "context": context.to_dict(),
            "certificate_sha256": certificate_digest(certificate), "labels_sha256": digest("synthetic-labels.json"),
        })
        inputs = phase / "registered-inputs"
        inputs.mkdir(exist_ok=False)
        hashes = {}
        for name in (*web.INPUT_ARTIFACTS, "run.json"):
            raw = web._read_file(directory / name)
            hashes[name] = web._sha(raw)
            usefulness_store._write_raw(inputs / name, raw)
        usefulness_store._json(phase / "registration.json", {
            "schema": "mra-public-usefulness-registration/1.0", "run_id": run_id,
            "prospective_sha256": web._sha(web._read_file(phase / "prospective.json")),
            "source_input_sha256": hashes, **web.AUTHORITY,
        })
        self._registered(run_id)
        self.ledger.bind_retained(snapshot["history_id"], run_id, snapshot["revision"],
                                  snapshot["head_sha256"], self._bindings(run_id))
        return self.detail(run_id)

    def alias(self, run_id: str) -> dict[str, Any]:
        snapshot = self._history(run_id, require_runtime=True)
        if snapshot is None:
            raise web.ResearchWebError("legacy_history_unregistered: historical runs cannot be enrolled retroactively")
        if snapshot["state"] not in {"ready", "committed"}:
            raise web.ResearchWebError("An uncertain or interrupted shared history cannot acquire aliases")
        owner = snapshot["owner_run_id"]
        canonical = self._history(owner, require_runtime=True)
        if canonical is None or canonical["retained_bindings"] != snapshot["retained_bindings"]:
            raise web.ResearchWebError("Canonical retained inputs differ from the alias history")
        owner_dir, manifest, _, _, raw, _, _ = self._inputs(owner, check_source=True)
        if {name: web._sha(data) for name, data in raw.items()} != snapshot["retained_bindings"]["source_input_sha256"]:
            raise web.ResearchWebError("Captured alias inputs differ from witnessed retained bytes")
        alias_id = uuid4().hex
        directory = self.root / alias_id
        web._check_path(directory)
        directory.mkdir(exist_ok=False)
        for name, data in raw.items():
            usefulness_store._write_raw(directory / name, data)
        web._write_exclusive(directory / "run.json", {
            **manifest, "run_id": alias_id, "created_at": web._now(),
        })
        # No new response and no new usefulness experiment are fabricated.
        web._write_exclusive(directory / _REGISTRATION, self._declaration(snapshot, alias_id))
        if web._json_bytes(self._bindings(alias_id)) != web._json_bytes(snapshot["retained_bindings"]):
            raise web.ResearchWebError("Copied alias inputs differ from the witnessed retained binding")
        self.ledger.attach_alias(snapshot["history_id"], alias_id, snapshot["revision"], snapshot["head_sha256"])
        return self.detail(alias_id)

    @staticmethod
    def _request(snapshot: dict[str, Any]) -> dict[str, Any]:
        retained = snapshot["retained_bindings"]
        return {"retained": retained,
                "public_request": {"request_plan_sha256": retained["request_plan_sha256"],
                                   "recipient_scope": "public-synthetic-shared-output", "informative_extension": 1},
                "certificate_sha256": retained["certificate_sha256"]}

    def _ensure_owner_verified(self, owner: str, verified: Any, receipt: dict[str, Any]) -> None:
        directory = self._directory(owner)
        if self._receipt(directory, owner, verified) is None:
            try:
                web._write_exclusive(directory / "verification.json", {
                    "schema": "mra-rr-web-verification/1.0", "run_id": owner,
                    "verified_at": receipt["verified_at"], "verification": web._summary(verified),
                })
            except FileExistsError:
                self._receipt(directory, owner, verified)

    @staticmethod
    def _validate_captured_receipts(owner: str, verified: Any, raw: dict[str, bytes]) -> None:
        reserved = _keys(_load(raw["sample-reservation.json"]), {
            "schema", "status", "run_id", "reserved_at", "certificate_sha256",
            "authorization_effect", "production_execution_qualified",
        }, "captured sampling reservation")
        completed = _keys(_load(raw["sampling-completion.json"]), {
            "schema", "run_id", "completed_at", "block_sha256", "certificate_sha256",
            "authorization_effect", "production_execution_qualified",
        }, "captured sampling completion")
        if type(reserved["reserved_at"]) is not str or type(completed["completed_at"]) is not str:
            raise web.ResearchWebError("Captured sampling receipt timestamps must be strings")
        expected_reserved = {
            "schema": "mra-rr-web-reservation/1.0", "status": "reserved_incomplete",
            "run_id": owner, "reserved_at": reserved["reserved_at"],
            "certificate_sha256": verified.digest, **web.AUTHORITY,
        }
        expected_completed = {
            "schema": "mra-rr-web-completion/1.0", "run_id": owner,
            "completed_at": completed["completed_at"],
            "certificate_sha256": verified.digest,
            "block_sha256": web._sha(raw["randomized-block.json"]), **web.AUTHORITY,
        }
        if (raw["sample-reservation.json"] != web._json_bytes(expected_reserved)
                or raw["sampling-completion.json"] != web._json_bytes(expected_completed)):
            raise web.ResearchWebError("Captured sampling receipt bytes differ from their exact canonical certificate and run bindings")

    def sample(self, run_id: str, expected_revision: int, expected_head_sha256: str) -> dict[str, Any]:
        if (type(expected_revision) is not int or not 1 <= expected_revision < 2 ** 63
                or type(expected_head_sha256) is not str or len(expected_head_sha256) != 64
                or any(character not in "0123456789abcdef" for character in expected_head_sha256)):
            raise web.ResearchWebError("A typed history revision and lowercase SHA-256 predecessor are required")
        snapshot = self._history(run_id, require_runtime=True)
        if snapshot is None:
            raise web.ResearchWebError("legacy_history_unregistered: new sampling requires a prospectively registered shared history")
        directory, _, _, _, _, verified, _ = self._inputs(run_id, check_source=True)
        receipt = self._receipt(directory, run_id, verified)
        if receipt is None:
            raise web.ResearchWebError("Verify the original registered certificate before sampling or redelivery")
        if verified.claim == "infeasible":
            raise web.ResearchWebError("An infeasible certificate cannot be sampled")
        owner = snapshot["owner_run_id"]
        canonical = self._history(owner, require_runtime=True)
        if canonical is None or canonical["retained_bindings"] != snapshot["retained_bindings"]:
            raise web.ResearchWebError("The canonical retained inputs differ from the shared history")
        request = self._request(snapshot)
        reservation = self.ledger.reserve(snapshot["history_id"], run_id, expected_revision,
                                          expected_head_sha256, web._sha(web._json_bytes(request)), request,
                                          str(self.root / owner / "randomized-block.json"))
        if reservation["replayed"]:
            result = self.detail(run_id)
            result["sampling"].update({"replayed": True, "redelivered": True})
            return result
        # From this point, any failure leaves the witnessed reservation blocked.
        self._ensure_owner_verified(owner, verified, receipt)
        try:
            super().sample(owner)
            after = self._history(owner, require_runtime=True)
            if after is None or after["retained_bindings"] != snapshot["retained_bindings"]:
                raise web.ResearchWebError("The canonical retained inputs changed during sampling")
            owner_directory, _, _, owner_context, _, owner_verified, _ = self._inputs(owner)
            block = self._block(owner_directory, owner_context, owner_verified)
            if block is None:
                raise web.ResearchWebError("The canonical sampled block has invalid certificate or response bindings")
            raw_outputs = {name: web._read_file(owner_directory / name) for name in _OUTPUTS}
            self._validate_captured_receipts(owner, owner_verified, raw_outputs)
            captured_block = _load(raw_outputs["randomized-block.json"])
            if (raw_outputs["randomized-block.json"] != web._json_bytes(block)
                    or captured_block["certificate_sha256"] != snapshot["retained_bindings"]["certificate_sha256"]
                    or captured_block["retained_response_sha256"] != snapshot["retained_bindings"]["retained_response_sha256"]):
                raise web.ResearchWebError("Captured sampled bytes differ from the shared certificate and retained law")
            if _load(raw_outputs["sampling-completion.json"])["block_sha256"] != web._sha(raw_outputs["randomized-block.json"]):
                raise web.ResearchWebError("The captured sampling completion does not bind the exact block")
            artifacts = {name: {"path": str(owner_directory / name), "sha256": web._sha(raw)}
                         for name, raw in raw_outputs.items()}
            self.ledger.commit(snapshot["history_id"], reservation["reservation"]["reservation_id"], artifacts)
        except Exception as exc:
            raise web.ResearchWebError("Shared sampling did not commit; the durable reservation is preserved and replacement draws are refused") from exc
        result = self.detail(run_id)
        result["sampling"].update({"replayed": False, "redelivered": False})
        return result

    def new_disclosure(self, run_id: str, expected_revision: int, expected_head_sha256: str) -> None:
        snapshot = self._history(run_id)
        if snapshot is None:
            raise web.ResearchWebError("legacy_history_unregistered")
        if type(expected_revision) is not int or expected_revision != snapshot["revision"] or expected_head_sha256 != snapshot["head_sha256"]:
            raise web.ResearchWebError("Stale shared-history predecessor; refresh the history")
        raise web.ResearchWebError("A further informative draw requires an independently verified complete-history law; the supported law permits one continuation only")

    def _shared(self, run_id: str, snapshot: dict[str, Any] | None) -> dict[str, Any]:
        if snapshot is None:
            return {"registered": False, "status": "legacy_history_unregistered", "state": "legacy_history_unregistered",
                    "reason": "Historical runs remain readable; shared history enrollment and new draws are refused.",
                    "history_id": None, "revision": None, "head_sha256": None, "canonical_run_id": None,
                    "artifacts": [], **web.AUTHORITY}
        cap = snapshot["registration"]["parameters"]["L"]
        return {**snapshot, "registered": True, "status": snapshot["state"],
                "canonical_run_id": snapshot["owner_run_id"],
                "supported_law": "one retained RR response plus one certified conditional continuation",
                "whole_history_cap": f"pure differential privacy cap E = log({cap}); no additive spending of correlated outputs",
                "custody": "separate local witness fixture; authoritative agency administration remains pending",
                "reason": {"ready": "One continuation may be reserved after certificate verification.",
                           "committed": "The exact saved block may be redelivered; further informative draws are refused."}.get(
                               snapshot["state"], "Active or interrupted reservation is preserved; replacement draws are refused."),
                "artifacts": [{"name": name, "url": f"{web.PREFIX}/runs/{run_id}/history/artifacts/{name}"}
                              for name in ("shared-history.json", _REGISTRATION)], **web.AUTHORITY}

    def detail(self, run_id: str) -> dict[str, Any]:
        detail = super().detail(run_id)
        try:
            snapshot = self._history(run_id)
            detail["shared_history"] = self._shared(run_id, snapshot)
            if snapshot is None:
                if detail["sampling"]["status"] != "completed":
                    detail["sampling"]["status"] = "legacy_history_unregistered"
                return detail
            owner = snapshot["owner_run_id"]
            if owner != run_id:
                owner_detail = usefulness_store.UsefulnessRunStore.detail(self, owner)
                detail["usefulness"] = {**owner_detail["usefulness"], "source_run_id": owner,
                                        "alias_uses_canonical_experiment": True}
            if snapshot["state"] == "committed":
                owner_directory, _, _, context, _, verified, _ = self._inputs(owner)
                block = _load(self._pinned_output(snapshot, "randomized-block.json"))
                detail["sampling"]["status"] = "completed"
                for record, sampled in zip(detail["records"], block["records"]):
                    record["sampled_labels"] = sampled["labels"]
                names = {item["name"] for item in detail["artifacts"]}
                for name in ("randomized-block.json", "sampling-completion.json"):
                    if name not in names:
                        detail["artifacts"].append({"name": name, "url": f"{web.PREFIX}/runs/{owner}/artifacts/{name}"})
            elif snapshot["state"] != "ready":
                detail["sampling"]["status"] = "reserved_incomplete"
                detail["artifacts"] = [item for item in detail["artifacts"] if item["name"] not in _OUTPUTS]
                for record in detail["records"]:
                    record.pop("sampled_labels", None)
                detail["usefulness"] = {**detail["usefulness"], "status": "waiting_block", "artifacts": [], "result": None}
            detail["sampling"]["history_reservation"] = "shared witnessed public synthetic history"
        except (HistoryError, web.ResearchWebError, OSError) as exc:
            detail["shared_history"] = {"registered": True, "state": "integrity_error", "status": "integrity_error",
                                        "reason": str(exc), "artifacts": [], **web.AUTHORITY}
            detail["sampling"]["status"] = "integrity_error"
            detail["artifacts"] = [item for item in detail["artifacts"] if item["name"] not in _OUTPUTS]
            for record in detail["records"]:
                record.pop("sampled_labels", None)
            detail["usefulness"] = {**detail["usefulness"], "status": "integrity_error", "artifacts": [], "result": None, "reason": str(exc)}
        return detail

    def history(self, run_id: str) -> dict[str, Any]:
        snapshot = self._history(run_id)
        if snapshot is None:
            return {"shared_history": self._shared(run_id, None), "events": [], **web.AUTHORITY}
        exported = _load(self.ledger.export(snapshot["history_id"]))
        return {**exported, "shared_history": self._shared(run_id, exported["history"]), **web.AUTHORITY}

    def histories(self) -> dict[str, Any]:
        snapshots = self.ledger.histories()
        return {"histories": snapshots, **web.AUTHORITY}

    def history_artifact(self, run_id: str, name: str) -> bytes:
        if name not in {"shared-history.json", _REGISTRATION}:
            raise web.ResearchWebError("Shared history artifact not found", 404)
        snapshot = self._history(run_id)
        if snapshot is None:
            raise web.ResearchWebError("Shared history is unregistered", 404)
        if name == "shared-history.json":
            return self.ledger.export(snapshot["history_id"])
        data = web._read_file(self._directory(run_id) / _REGISTRATION)
        if data != web._json_bytes(self._declaration(snapshot, run_id)):
            raise web.ResearchWebError("Shared registration changed during download")
        return data

    def _pinned_output(self, snapshot: dict[str, Any], name: str) -> bytes:
        if snapshot["state"] != "committed":
            raise web.ResearchWebError("Shared output is reserved or incomplete", 404)
        pin = snapshot["reservation"]["artifacts"][name]
        expected_path = self.root / snapshot["owner_run_id"] / name
        if Path(pin["path"]).absolute() != expected_path.absolute():
            raise web.ResearchWebError("The committed artifact is outside its canonical history")
        raw = web._read_file(expected_path)
        if web._sha(raw) != pin["sha256"]:
            raise web.ResearchWebError("Captured output bytes differ from the witnessed history pin")
        # Validate custody again after capture. Return these exact bytes without
        # reopening a path after the check.
        after = self.ledger.snapshot(snapshot["history_id"])
        if after["state"] != "committed" or after["reservation"]["artifacts"] != snapshot["reservation"]["artifacts"]:
            raise web.ResearchWebError("Shared history changed during output capture")
        return raw

    def artifact(self, run_id: str, name: str) -> bytes:
        snapshot = self._history(run_id)
        if snapshot is not None and name in _OUTPUTS:
            return self._pinned_output(snapshot, name)
        raw = super().artifact(run_id, name)
        if snapshot is not None and name in web.INPUT_ARTIFACTS:
            if web._sha(raw) != snapshot["retained_bindings"]["source_input_sha256"][name]:
                raise web.ResearchWebError("Captured input bytes differ from the witnessed history pin")
        return raw

    def _capture(self, run_id: str) -> tuple[Any, ...]:
        snapshot = self._history(run_id)
        if snapshot is not None and snapshot["state"] not in {"ready", "committed"}:
            raise web.ResearchWebError("An uncertain shared reservation blocks usefulness capture")
        captured = super()._capture(run_id)
        if snapshot is None:
            return captured
        raw = captured[2]
        retained = snapshot["retained_bindings"]
        for name, digest in retained["source_input_sha256"].items():
            if web._sha(raw[name]) != digest:
                raise web.ResearchWebError("Captured usefulness inputs differ from shared history pins")
        if snapshot["state"] == "committed":
            pins = snapshot["reservation"]["artifacts"]
            for name in _OUTPUTS:
                if name not in raw or web._sha(raw[name]) != pins[name]["sha256"]:
                    raise web.ResearchWebError("Captured usefulness block or receipt differs from its witnessed history pin")
        elif any(name in raw for name in _OUTPUTS):
            raise web.ResearchWebError("Uncommitted source outputs cannot enter the usefulness experiment")
        after = self._history(run_id)
        if after is None or after["history_id"] != snapshot["history_id"] or after["state"] != snapshot["state"]:
            raise web.ResearchWebError("Shared history changed during usefulness capture")
        if after.get("reservation") != snapshot.get("reservation"):
            raise web.ResearchWebError("Shared reservation changed during usefulness capture")
        return captured

    def _evaluation_owner(self, run_id: str, *, execute: bool) -> str:
        snapshot = self._history(run_id, require_runtime=execute)
        if snapshot is None:
            phase = self._phase_directory(run_id, required=False)
            if execute and not (phase / "evaluation-reservation.json").exists():
                raise web.ResearchWebError("legacy_history_unregistered: new evaluations require shared history registration")
            return run_id
        if execute:
            if snapshot["state"] not in {"ready", "committed"}:
                raise web.ResearchWebError("An uncertain shared reservation blocks every new evaluation")
            directory, _, _, _, _, verified, _ = self._inputs(run_id)
            receipt = self._receipt(directory, run_id, verified)
            if receipt is None:
                raise web.ResearchWebError("Verify this alias certificate before using the canonical experiment")
            self._ensure_owner_verified(snapshot["owner_run_id"], verified, receipt)
            if snapshot["retained_bindings"]["preset"] == "optimal" and snapshot["state"] != "committed":
                raise web.ResearchWebError("Commit the shared conditional block before usefulness evaluation")
        return snapshot["owner_run_id"]

    def evaluate(self, run_id: str) -> dict[str, Any]:
        owner = self._evaluation_owner(run_id, execute=True)
        super().evaluate(owner)
        return self.detail(run_id)

    def evaluation(self, run_id: str, evaluation_id: str) -> dict[str, Any]:
        return super().evaluation(self._evaluation_owner(run_id, execute=False), evaluation_id)

    def evaluation_artifact(self, run_id: str, evaluation_id: str, name: str) -> bytes:
        return super().evaluation_artifact(self._evaluation_owner(run_id, execute=False), evaluation_id, name)
