"""Durable public usefulness experiments, isolated from release authority.

Each registration is made before retained responses exist. Completed evaluations
reuse the committed block, and are replayed from captured, hash-checked inputs
before any result or download is served. Reservations are never automatically
repaired or retried after an interruption.
"""
from __future__ import annotations

import importlib.metadata
import os
from pathlib import Path
import platform
import re
from typing import Any
from uuid import uuid4

from . import usefulness
from .certificates import ResearchContext, build_certificate, certificate_digest
from .cli import _keys, _load
from . import web

ARTIFACTS = (
    "evaluation.json", "models.json", "predictions.json", "independent-block.json",
    "simulation-diagnostics.json", "reproducibility.json", "evaluation.txt",
)
_EVAL_ID = re.compile(r"[a-f0-9]{64}\Z")
_IMPLEMENTATION = (
    "certificates.py", "sampling.py", "cli.py", "web.py", "console_app.py",
    "usefulness.py", "usefulness_store.py",
)
_MAX_ARTIFACT = 8 * 1024 * 1024


def _write_raw(path: Path, data: bytes) -> None:
    web._check_path(path)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(path, flags, 0o600), "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def _json(path: Path, value: Any) -> None:
    _write_raw(path, web._json_bytes(value))


def _same(actual: Any, expected: Any, label: str) -> None:
    # Canonical bytes also reject booleans masquerading as integer fields.
    if web._json_bytes(actual) != web._json_bytes(expected):
        raise web.ResearchWebError(f"The {label} differs from its frozen registration")


def _runtime() -> dict[str, Any]:
    versions = {}
    for name in ("model-release-assurance", "fastapi", "pydantic", "starlette"):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = "not-installed"
    base = Path(__file__).parent
    return {
        "python": platform.python_version(), "python_implementation": platform.python_implementation(),
        "packages": versions,
        "implementation_sha256": {name: web._sha(web._read_file(base / name, limit=_MAX_ARTIFACT)) for name in _IMPLEMENTATION},
    }


def _bundle_bytes(bundle: dict[str, Any]) -> dict[str, bytes]:
    if type(bundle) is not dict or set(bundle) != set(ARTIFACTS):
        raise web.ResearchWebError("The evaluator did not return the complete declared artifact set")
    result = {}
    for name in ARTIFACTS:
        if name.endswith(".txt"):
            if type(bundle[name]) is not str:
                raise web.ResearchWebError("The human-readable report must be text")
            result[name] = bundle[name].encode("utf-8")
        else:
            if type(bundle[name]) is not dict:
                raise web.ResearchWebError("Evaluation artifacts must be JSON objects")
            result[name] = web._json_bytes(bundle[name])
        if len(result[name]) > _MAX_ARTIFACT:
            raise web.ResearchWebError("An evaluation artifact exceeds the declared size bound")
    return result


class UsefulnessRunStore(web.ResearchRunStore):
    """Extend public runs with prospective specifications and immutable jobs."""

    def __init__(self, data_dir: str | Path, *, source_pdf: str | Path = web.DEFAULT_SOURCE_PDF,
                 usefulness_dir: str | Path | None = None):
        super().__init__(data_dir, source_pdf=source_pdf)
        self.usefulness_root = (Path(usefulness_dir).absolute() if usefulness_dir is not None
                                else self.root.with_name(self.root.name + "-usefulness"))
        if self.usefulness_root == self.root:
            raise web.ResearchWebError("Usefulness evidence must have separate sibling storage")
        web._check_path(self.usefulness_root)
        self.usefulness_root.mkdir(parents=True, exist_ok=True)
        web._check_path(self.usefulness_root)

    def specification(self) -> dict[str, Any]:
        spec, dataset = self._frozen(write=False)
        return {
            "specification": spec, "specification_sha256": web._sha(web._json_bytes(spec)),
            "dataset_sha256": web._sha(web._json_bytes(dataset)), **web.AUTHORITY,
        }

    def _frozen(self, *, write: bool) -> tuple[dict[str, Any], dict[str, Any]]:
        web._check_path(self.usefulness_root)
        spec, dataset = usefulness.frozen_specification(), usefulness.benchmark_dataset()
        for name, value in (("specification.json", spec), ("dataset.json", dataset)):
            path = self.usefulness_root / name
            web._check_path(path)
            expected = web._json_bytes(value)
            if not path.exists() and write:
                try:
                    _write_raw(path, expected)
                except FileExistsError:
                    pass
            if path.exists() and web._read_file(path, limit=_MAX_ARTIFACT) != expected:
                raise web.ResearchWebError("The prospectively frozen usefulness specification or fixture changed")
            if write and not path.exists():
                raise web.ResearchWebError("The prospective usefulness specification is unavailable")
        return spec, dataset

    def _phase_directory(self, run_id: str, *, required: bool = True) -> Path:
        self._directory(run_id)  # Validate the bounded source run identity first.
        path = self.usefulness_root / run_id
        web._check_path(path)
        if required and not path.is_dir():
            raise web.ResearchWebError("This historical run lacks prospective usefulness registration; create a fresh run")
        return path

    def create(self, preset: str) -> dict[str, Any]:
        if type(preset) is not str or preset not in web.PRESETS:
            raise web.ResearchWebError("Choose a fixed public research preset", 422)
        self._source()
        # These global bytes and the per-run declaration exist BEFORE the first
        # retained response is generated. A historical response cannot be enrolled.
        spec, dataset = self._frozen(write=True)
        runtime = _runtime()
        run_id = uuid4().hex
        directory = self.root / run_id
        phase = self.usefulness_root / run_id
        web._check_path(directory)
        web._check_path(phase)
        directory.mkdir(exist_ok=False)
        phase.mkdir(exist_ok=False)
        prospective = {
            "schema": "mra-public-usefulness-prospective/1.0", "run_id": run_id,
            "preset": preset, "registered_at": web._now(),
            "specification_sha256": web._sha(web._json_bytes(spec)),
            "dataset_sha256": web._sha(web._json_bytes(dataset)), "runtime": runtime,
            "registered_before_retained_response": True, **web.AUTHORITY,
        }
        _json(phase / "prospective.json", prospective)
        parameters = web.PRESETS[preset]
        records = web._roster()
        documents = {
            "synthetic-labels.json": {"schema": web.LABELS_SCHEMA, "records": records},
            "retained-law.json": {"schema": web.LAW_SCHEMA, "d": parameters.to_dict()["d"]},
            "retained-responses.json": {
                "schema": web.RESPONSES_SCHEMA,
                "records": [
                    {"record_id": record["record_id"], "w": record["labels"][0]
                     if web.secrets.randbelow(parameters.d.numerator + parameters.d.denominator) < parameters.d.numerator
                     else 1 - record["labels"][0]}
                    for record in records
                ],
            },
        }
        for name, value in documents.items():
            web._write_exclusive(directory / name, value)
        digest = lambda name: web._sha(web._read_file(directory / name))
        law_digest, response_digest = digest("retained-law.json"), digest("retained-responses.json")
        web._write_exclusive(directory / "history.json", {
            "schema": web.HISTORY_SCHEMA, "retained_law_sha256": law_digest,
            "retained_response_sha256": response_digest, "additional_protected_outputs": False,
        })
        web._write_exclusive(directory / "request-plan.json", {
            "schema": web.REQUEST_SCHEMA, "parameters": parameters.to_dict(),
            "record_ids": [record["record_id"] for record in records], "visible_decisions": "public_fixed",
        })
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
            _write_raw(inputs / name, raw)
        _json(phase / "registration.json", {
            "schema": "mra-public-usefulness-registration/1.0", "run_id": run_id,
            "prospective_sha256": web._sha(web._read_file(phase / "prospective.json")),
            "source_input_sha256": hashes, **web.AUTHORITY,
        })
        self._registered(run_id)
        return self.detail(run_id)

    def _registered(self, run_id: str) -> tuple[Path, dict[str, Any], bytes, bytes]:
        phase = self._phase_directory(run_id)
        spec, dataset = self._frozen(write=False)
        if not all((self.usefulness_root / name).exists() for name in ("specification.json", "dataset.json")):
            raise web.ResearchWebError("Prospectively frozen evaluation inputs are missing")
        registration_raw = web._read_file(phase / "registration.json")
        prospective_raw = web._read_file(phase / "prospective.json")
        registration = _keys(_load(registration_raw), {
            "schema", "run_id", "prospective_sha256", "source_input_sha256",
            "authorization_effect", "production_execution_qualified",
        }, "usefulness registration")
        prospective = _keys(_load(prospective_raw), {
            "schema", "run_id", "preset", "registered_at", "specification_sha256", "dataset_sha256",
            "runtime", "registered_before_retained_response", "authorization_effect", "production_execution_qualified",
        }, "prospective declaration")
        if registration_raw != web._json_bytes(registration) or prospective_raw != web._json_bytes(prospective):
            raise web.ResearchWebError("Prospective registration bytes changed from their canonical immutable encoding")
        directory, manifest, _, _, data, _, _ = self._inputs(run_id)
        expected_prospective = {
            "schema": "mra-public-usefulness-prospective/1.0", "run_id": run_id,
            "preset": manifest["preset"], "registered_at": prospective["registered_at"],
            "specification_sha256": web._sha(web._json_bytes(spec)),
            "dataset_sha256": web._sha(web._json_bytes(dataset)), "runtime": _runtime(),
            "registered_before_retained_response": True, **web.AUTHORITY,
        }
        if type(prospective["registered_at"]) is not str:
            raise web.ResearchWebError("Invalid prospective registration time")
        _same(prospective, expected_prospective, "prospective specification/runtime")
        source_raw = {**data, "run.json": web._read_file(directory / "run.json")}
        hashes = {name: web._sha(raw) for name, raw in source_raw.items()}
        _same(registration, {
            "schema": "mra-public-usefulness-registration/1.0", "run_id": run_id,
            "prospective_sha256": web._sha(prospective_raw), "source_input_sha256": hashes, **web.AUTHORITY,
        }, "source input registration")
        for name, raw in source_raw.items():
            if web._read_file(phase / "registered-inputs" / name) != raw:
                raise web.ResearchWebError("Registered source input bytes changed; usefulness is blocked")
        return phase, prospective, registration_raw, prospective_raw

    def sample(self, run_id: str) -> dict[str, Any]:
        phase = self._phase_directory(run_id, required=False)
        # Legacy research runs retain their prior single-draw workflow and never
        # acquire usefulness registration retroactively.
        if phase.exists():
            self._registered(run_id)
        return super().sample(run_id)

    def _capture(self, run_id: str) -> tuple[Path, dict[str, Any], dict[str, bytes], dict[str, Any]]:
        phase, prospective, registration_raw, prospective_raw = self._registered(run_id)
        directory, manifest, parameters, context, inputs, verified, records = self._inputs(run_id, check_source=True)
        receipt_raw = web._read_file(directory / "verification.json") if (directory / "verification.json").exists() else None
        if receipt_raw is not None and receipt_raw != web._json_bytes(_load(receipt_raw)):
            raise web.ResearchWebError("The original verification receipt bytes changed")
        if receipt_raw is None or self._receipt(directory, run_id, verified, raw=receipt_raw) is None:
            raise web.ResearchWebError("Verify the original registered certificate before evaluation")
        block = self._block(directory, context, verified)
        optional = ("randomized-block.json", "sample-reservation.json", "sampling-completion.json")
        if any((directory / name).exists() for name in optional) and block is None:
            raise web.ResearchWebError("The conditional block is missing, corrupt or incompletely reserved")
        if manifest["preset"] == "optimal" and block is None:
            raise web.ResearchWebError("Commit the single conditional block before usefulness evaluation")
        raw = {**inputs, "run.json": web._read_file(directory / "run.json"),
               "verification.json": receipt_raw, "registration.json": registration_raw, "prospective.json": prospective_raw,
               "specification.json": web._read_file(self.usefulness_root / "specification.json", limit=_MAX_ARTIFACT),
               "dataset.json": web._read_file(self.usefulness_root / "dataset.json", limit=_MAX_ARTIFACT)}
        if block is not None:
            for name in optional:
                raw[name] = web._read_file(directory / name)
                if raw[name] != web._json_bytes(_load(raw[name])):
                    raise web.ResearchWebError("Conditional sampling receipt or block bytes changed")
            # The exact captured source block and completion bytes, not a later
            # parsed read, are used by the fitter and lineage.
            captured_block = _load(raw["randomized-block.json"])
            completion = _load(raw["sampling-completion.json"])
            if web._sha(raw["randomized-block.json"]) != completion.get("block_sha256"):
                raise web.ResearchWebError("The conditional block changed during capture")
            _same(captured_block, block, "captured conditional block")
            block = captured_block
        lineage = {
            "schema": "mra-public-usefulness-lineage/1.0", "run_id": run_id, "preset": manifest["preset"],
            "certificate_sha256": verified.digest, "context": context.to_dict(),
            "specification_sha256": prospective["specification_sha256"],
            "dataset_sha256": prospective["dataset_sha256"],
            "runtime": prospective["runtime"],
            "source_artifacts": {name: web._sha(data) for name, data in sorted(raw.items())},
            "source_block_reused": block is not None, "replacement_draws": 0, **web.AUTHORITY,
        }
        arguments = {
            "specification": _load(raw["specification.json"]), "dataset": _load(raw["dataset.json"]),
            "records": records, "block": block, "parameters": parameters, "context": context,
            "certificate": raw["certificate.json"], "lineage": lineage,
        }
        return phase, lineage, raw, arguments

    def _replay(self, arguments: dict[str, Any]) -> dict[str, bytes]:
        try:
            return _bundle_bytes(usefulness.evaluate_bundle(**arguments))
        except ValueError as exc:
            raise web.ResearchWebError(f"Usefulness evaluation refused: {exc}") from exc

    def _completed(self, run_id: str, evaluation_id: str | None = None) -> tuple[str, dict[str, Any], dict[str, bytes]]:
        phase, lineage, raw, arguments = self._capture(run_id)
        expected_id = web._sha(web._json_bytes(lineage))
        if evaluation_id is not None and (type(evaluation_id) is not str or not _EVAL_ID.fullmatch(evaluation_id) or evaluation_id != expected_id):
            raise web.ResearchWebError("Usefulness evaluation not found", 404)
        reservation_raw = web._read_file(phase / "evaluation-reservation.json")
        reservation = _keys(_load(reservation_raw), {
            "schema", "run_id", "evaluation_id", "reserved_at", "status", "lineage_sha256",
            "authorization_effect", "production_execution_qualified",
        }, "evaluation reservation")
        if reservation_raw != web._json_bytes(reservation):
            raise web.ResearchWebError("Evaluation reservation bytes changed")
        if type(reservation["reserved_at"]) is not str:
            raise web.ResearchWebError("Invalid evaluation reservation")
        _same(reservation, {
            "schema": "mra-public-usefulness-reservation/1.0", "run_id": run_id,
            "evaluation_id": expected_id, "reserved_at": reservation["reserved_at"],
            "status": "reserved_incomplete", "lineage_sha256": expected_id, **web.AUTHORITY,
        }, "evaluation reservation")
        job = phase / expected_id
        web._check_path(job)
        completion_raw = web._read_file(job / "completion.json")
        completion = _keys(_load(completion_raw), {
            "schema", "run_id", "evaluation_id", "completed_at", "lineage", "reservation_sha256", "artifacts",
            "authorization_effect", "production_execution_qualified",
        }, "evaluation completion")
        if completion_raw != web._json_bytes(completion):
            raise web.ResearchWebError("Evaluation completion receipt bytes changed")
        artifacts = {name: web._read_file(job / name, limit=_MAX_ARTIFACT) for name in ARTIFACTS}
        if type(completion["completed_at"]) is not str:
            raise web.ResearchWebError("Invalid evaluation completion time")
        _same(completion, {
            "schema": "mra-public-usefulness-completion/1.0", "run_id": run_id,
            "evaluation_id": expected_id, "completed_at": completion["completed_at"],
            "lineage": lineage, "reservation_sha256": web._sha(reservation_raw),
            "artifacts": {name: web._sha(data) for name, data in artifacts.items()}, **web.AUTHORITY,
        }, "evaluation completion and artifact hashes")
        for name, data in raw.items():
            if web._read_file(job / "inputs" / name, limit=_MAX_ARTIFACT) != data:
                raise web.ResearchWebError("Captured evaluation input is missing or changed")
        # An output plus its mutable digest receipt could be rewritten together.
        # Reproducible semantic replay is the independent expectation for every
        # model, prediction, metric, diagnostic and report byte.
        expected = self._replay(arguments)
        if artifacts != expected:
            raise web.ResearchWebError("Saved evaluation artifacts do not match deterministic source-block refitting")
        _, after_lineage, after_raw, _ = self._capture(run_id)
        if after_raw != raw or web._json_bytes(after_lineage) != web._json_bytes(lineage):
            raise web.ResearchWebError("Evaluation source evidence changed during validation")
        return expected_id, _load(artifacts["evaluation.json"]), artifacts

    @staticmethod
    def _links(run_id: str, evaluation_id: str) -> list[dict[str, str]]:
        return [{"name": name, "url": f"{web.PREFIX}/runs/{run_id}/evaluations/{evaluation_id}/artifacts/{name}"} for name in ARTIFACTS]

    def _status(self, run_id: str, detail: dict[str, Any]) -> dict[str, Any]:
        spec = usefulness.frozen_specification()
        status = {
            "status": "not_evaluated", "registered": False, "specification": spec,
            "specification_sha256": None, "dataset_sha256": None,
            "evaluation_id": None, "result": None, "diagnostics": None, "artifacts": [], **web.AUTHORITY,
        }
        phase = self._phase_directory(run_id, required=False)
        if not phase.exists():
            return {**status, "reason": "Historical run lacks prospective Phase 2 registration; create a fresh public run."}
        try:
            phase, prospective, _, _ = self._registered(run_id)
            status.update({"registered": True, "specification_sha256": prospective["specification_sha256"],
                           "dataset_sha256": prospective["dataset_sha256"]})
            reserved = phase / "evaluation-reservation.json"
            web._check_path(reserved)
            if reserved.exists():
                reservation = _load(web._read_file(reserved))
                evaluation_id = reservation.get("evaluation_id")
                if type(evaluation_id) is not str or not _EVAL_ID.fullmatch(evaluation_id):
                    raise web.ResearchWebError("Invalid evaluation reservation identity")
                completion = phase / evaluation_id / "completion.json"
                web._check_path(completion)
                if not completion.exists():
                    return {**status, "status": "reserved_incomplete", "evaluation_id": evaluation_id,
                            "reason": "Interrupted or active reservation is preserved; automatic retries are refused."}
                evaluation_id, result, artifacts = self._completed(run_id, evaluation_id)
                return {**status, "status": "completed", "evaluation_id": evaluation_id,
                        "result": result, "diagnostics": _load(artifacts["simulation-diagnostics.json"]),
                        "artifacts": self._links(run_id, evaluation_id)}
            if detail["verification"]["status"] != "verified":
                return {**status, "status": "waiting_verification", "reason": "Verify the original certificate first."}
            if detail["preset"] == "infeasible":
                return {**status, "reason": "The valid infeasibility certificate permits no certified continuation."}
            if detail["preset"] == "uniform":
                return {**status, "reason": "Uniform p=1/2 makes the frozen randomized-label decoder singular."}
            if detail["sampling"]["status"] != "completed":
                return {**status, "status": "waiting_block", "reason": "Commit the single permitted conditional block first."}
            return {**status, "status": "ready"}
        except (OSError, ValueError) as exc:
            return {**status, "status": "integrity_error", "reason": str(exc)}

    def detail(self, run_id: str) -> dict[str, Any]:
        detail = super().detail(run_id)
        detail["usefulness"] = self._status(run_id, detail)
        return detail

    def runs(self) -> dict[str, Any]:
        result = super().runs()
        for item in result["runs"]:
            item["usefulness"] = self.detail(item["run_id"])["usefulness"]
        return result

    def evaluate(self, run_id: str) -> dict[str, Any]:
        phase, lineage, raw, arguments = self._capture(run_id)
        evaluation_id = web._sha(web._json_bytes(lineage))
        reservation = phase / "evaluation-reservation.json"
        web._check_path(reservation)
        if reservation.exists():
            job = phase / evaluation_id
            web._check_path(job)
            if not (job / "completion.json").exists():
                raise web.ResearchWebError("This evaluation is reserved or interrupted; replacement evaluation is refused")
            self._completed(run_id, evaluation_id)
            return self.detail(run_id)
        try:
            _json(reservation, {
                "schema": "mra-public-usefulness-reservation/1.0", "run_id": run_id,
                "evaluation_id": evaluation_id, "reserved_at": web._now(), "status": "reserved_incomplete",
                "lineage_sha256": evaluation_id, **web.AUTHORITY,
            })
        except FileExistsError as exc:
            raise web.ResearchWebError("This evaluation is already reserved; concurrent replacement is refused") from exc
        try:
            job = phase / evaluation_id
            web._check_path(job)
            job.mkdir(exist_ok=False)
            captured = job / "inputs"
            captured.mkdir(exist_ok=False)
            for name, data in raw.items():
                _write_raw(captured / name, data)
            artifacts = self._replay(arguments)
            for name, data in artifacts.items():
                _write_raw(job / name, data)
            _, after_lineage, after_raw, _ = self._capture(run_id)
            if after_raw != raw or web._json_bytes(after_lineage) != web._json_bytes(lineage):
                raise web.ResearchWebError("Evaluation inputs changed before publication")
            _json(job / "completion.json", {
                "schema": "mra-public-usefulness-completion/1.0", "run_id": run_id,
                "evaluation_id": evaluation_id, "completed_at": web._now(), "lineage": lineage,
                "reservation_sha256": web._sha(web._read_file(reservation)),
                "artifacts": {name: web._sha(data) for name, data in artifacts.items()}, **web.AUTHORITY,
            })
        except Exception as exc:
            raise web.ResearchWebError("Evaluation did not complete; reservation and evidence are preserved and replacement retries are refused") from exc
        self._completed(run_id, evaluation_id)
        return self.detail(run_id)

    def evaluation(self, run_id: str, evaluation_id: str) -> dict[str, Any]:
        try:
            identity, result, artifacts = self._completed(run_id, evaluation_id)
        except FileNotFoundError as exc:
            raise web.ResearchWebError("Usefulness evaluation is unavailable or incomplete", 404) from exc
        return {"evaluation_id": identity, "result": result, "diagnostics": _load(artifacts["simulation-diagnostics.json"]),
                "artifacts": self._links(run_id, identity), **web.AUTHORITY}

    def evaluation_artifact(self, run_id: str, evaluation_id: str, name: str) -> bytes:
        if type(name) is not str or name not in ARTIFACTS:
            raise web.ResearchWebError("Usefulness artifact not found", 404)
        try:
            _, _, artifacts = self._completed(run_id, evaluation_id)
        except FileNotFoundError as exc:
            raise web.ResearchWebError("Usefulness artifact is unavailable or incomplete", 404) from exc
        # Return the exact validated snapshot, never reopen a path after checks.
        return artifacts[name]
