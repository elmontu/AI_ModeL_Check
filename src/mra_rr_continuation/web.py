"""Public retained-RR research routes, isolated from assurance and release authority.

The durable reservation protects one demo block across threads and restarts.
It is not an agency-wide history service or a production execution boundary.
"""
from __future__ import annotations

from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from .certificates import (
    CertificateError, MAX_JSON_BYTES, RRParameters, ResearchContext,
    SOURCE_PDF_SHA256, build_certificate, certificate_digest,
    verify_certificate,
)
from .cli import (
    BLOCK_SCHEMA, HISTORY_SCHEMA, LABELS_SCHEMA, LAW_SCHEMA, PLAN_SCHEMA,
    REQUEST_SCHEMA, RESPONSES_SCHEMA, _keys, _load,
)
from .sampling import ConditionalSampler, SamplingError

DEFAULT_SOURCE_PDF = Path(
    r"D:\model_audit_data\paper-work\v34-structural-visual-revision-20261008\main_submission.pdf"
)
PREFIX = "/api/research-rr"
_RUN_ID = re.compile(r"[a-f0-9]{32}\Z")
_ATTEMPT = re.compile(r"verify-attempt-[a-f0-9]{32}\.json\Z")
AUTHORITY = {"authorization_effect": "none", "production_execution_qualified": False}
HISTORY_RESERVATION = "one public demo run only; no authoritative agency history reservation"
INPUT_ARTIFACTS = (
    "synthetic-labels.json", "retained-law.json", "retained-responses.json",
    "history.json", "request-plan.json", "plan.json", "certificate.json",
)
PRESETS = {
    "optimal": RRParameters(2, Fraction(3), Fraction(9), Fraction(2, 3)),
    "infeasible": RRParameters(2, Fraction(3), Fraction(9), Fraction(3, 4)),
    "uniform": RRParameters(2, Fraction(1), Fraction(1), Fraction(1, 2)),
}
_TITLES = {
    "optimal": ("Optimal continuation", "Both conditional floors hold; exact marginal correctness is 17/24."),
    "infeasible": ("Infeasible floor", "The requested 3/4 floor exceeds the exact 7/10 capacity."),
    "uniform": ("Uniform boundary", "Retained RR odds d = 1 and joint odds L = 1 give correctness 1/2."),
}


class ResearchWebError(ValueError):
    def __init__(self, message: str, status_code: int = 409):
        super().__init__(message)
        self.status_code = status_code


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _roster() -> list[dict[str, Any]]:
    # Dimension is r+1; d is the retained RR odds, not a vector dimension.
    return [
        {"record_id": f"public-synthetic-{index:03}", "labels": [(index >> shift) & 1 for shift in (2, 1, 0)]}
        for index in range(8)
    ]


def _check_path(path: Path) -> None:
    """Reject symlinks and Windows junctions/reparse points, including ancestors."""
    for entry in reversed((path, *path.parents)):
        try:
            info = entry.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
            raise ResearchWebError("Research paths must not contain symbolic links or reparse points")


def _read_file(path: Path, *, limit: int = MAX_JSON_BYTES) -> bytes:
    _check_path(path)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise ResearchWebError("Research artifacts must be regular files")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        opened = os.fstat(stream.fileno())
        if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
            raise ResearchWebError("Research artifact changed during access")
        data = stream.read(limit + 1)
    _check_path(path)
    if len(data) > limit:
        raise ResearchWebError("Research artifact exceeds the file-size limit")
    return data


def _write_exclusive(path: Path, value: Any) -> None:
    _check_path(path)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(path, flags, 0o600), "wb") as stream:
        stream.write(_json_bytes(value))
        stream.flush()
        os.fsync(stream.fileno())


def _summary(verified: Any) -> dict[str, Any]:
    return {
        "status": "verified", "claim": verified.claim,
        "certificate_sha256": verified.digest,
        "marginal_label_correctness": None if verified.marginal_accuracy is None else str(verified.marginal_accuracy),
        "conditional_label_correctness": None if verified.conditional_accuracies is None else [str(value) for value in verified.conditional_accuracies],
        "premises_independently_verified": False, **AUTHORITY,
    }


class ResearchRunStore:
    """Fixed public examples, registered inputs, receipts, and exclusive draws."""

    def __init__(self, data_dir: str | Path, *, source_pdf: str | Path = DEFAULT_SOURCE_PDF):
        self.root = Path(data_dir).absolute()
        self.source_pdf = Path(source_pdf).absolute()
        _check_path(self.root)
        self.root.mkdir(parents=True, exist_ok=True)
        _check_path(self.root)
        if not self.root.is_dir():
            raise ResearchWebError("Research storage must be a directory")

    def _source(self) -> None:
        try:
            data = _read_file(self.source_pdf, limit=64 * 1024 * 1024)
        except (OSError, ResearchWebError) as exc:
            raise ResearchWebError("The reviewed research source PDF is unavailable or unsafe") from exc
        if _sha(data) != SOURCE_PDF_SHA256:
            raise ResearchWebError("The actual research source PDF differs from the reviewed source digest")

    def catalog(self) -> dict[str, Any]:
        available = False
        valid = False
        try:
            _read_file(self.source_pdf, limit=64 * 1024 * 1024)
            available = True
            self._source()
            valid = True
        except (OSError, ResearchWebError):
            pass
        presets = []
        for name, parameters in PRESETS.items():
            expected = "infeasible" if name == "infeasible" else "optimal"
            presets.append({
                "id": name, "title": _TITLES[name][0], "description": _TITLES[name][1],
                "parameters": parameters.to_dict(), "expected_claim": expected,
                "expected_marginal_correctness": {"optimal": "17/24", "uniform": "1/2"}.get(name),
                "expected_conditional_correctness": {"optimal": ["13/18", "2/3"], "uniform": ["1/2", "1/2"]}.get(name),
            })
        return {
            "presets": presets, "source_pdf_sha256": SOURCE_PDF_SHA256,
            "source_available": available, "source_integrity_valid": valid,
            "record_count": 8,
            "scope": "public synthetic full binary cube; one retained RR law and one fresh-label block",
            "history_reservation": HISTORY_RESERVATION, **AUTHORITY,
        }

    def _directory(self, run_id: str) -> Path:
        if type(run_id) is not str or not _RUN_ID.fullmatch(run_id):
            raise ResearchWebError("Research run not found", 404)
        _check_path(self.root)
        directory = self.root / run_id
        _check_path(directory)
        if not directory.is_dir():
            raise ResearchWebError("Research run not found", 404)
        return directory

    def create(self, preset: str) -> dict[str, Any]:
        if type(preset) is not str or preset not in PRESETS:
            raise ResearchWebError("Choose a fixed public research preset", 422)
        self._source()
        _check_path(self.root)
        run_id = uuid4().hex
        directory = self.root / run_id
        directory.mkdir(exist_ok=False)
        parameters = PRESETS[preset]
        records = _roster()
        documents = {
            "synthetic-labels.json": {"schema": LABELS_SCHEMA, "records": records},
            "retained-law.json": {"schema": LAW_SCHEMA, "d": parameters.to_dict()["d"]},
            "retained-responses.json": {
                "schema": RESPONSES_SCHEMA,
                "records": [
                    {"record_id": record["record_id"], "w": record["labels"][0] if secrets.randbelow(parameters.d.numerator + parameters.d.denominator) < parameters.d.numerator else 1 - record["labels"][0]}
                    for record in records
                ],
            },
        }
        for name, value in documents.items():
            _write_exclusive(directory / name, value)
        digest = lambda name: _sha(_read_file(directory / name))
        law_digest, response_digest = digest("retained-law.json"), digest("retained-responses.json")
        _write_exclusive(directory / "history.json", {
            "schema": HISTORY_SCHEMA, "retained_law_sha256": law_digest,
            "retained_response_sha256": response_digest, "additional_protected_outputs": False,
        })
        _write_exclusive(directory / "request-plan.json", {
            "schema": REQUEST_SCHEMA, "parameters": parameters.to_dict(),
            "record_ids": [record["record_id"] for record in records], "visible_decisions": "public_fixed",
        })
        context = ResearchContext(law_digest, response_digest, digest("history.json"), digest("request-plan.json"))
        _write_exclusive(directory / "plan.json", {
            "schema": PLAN_SCHEMA, "parameters": parameters.to_dict(), "context": context.to_dict(),
        })
        certificate = build_certificate(parameters, context)
        _write_exclusive(directory / "certificate.json", certificate)
        # Registration is independent of the browser's editable certificate.
        # Writing it last keeps interrupted creation from appearing as a saved run.
        _write_exclusive(directory / "run.json", {
            "schema": "mra-rr-public-web-run/1.0", "run_id": run_id, "preset": preset,
            "created_at": _now(), "context": context.to_dict(),
            "certificate_sha256": certificate_digest(certificate),
            "labels_sha256": digest("synthetic-labels.json"),
        })
        return self.detail(run_id)

    def _inputs(self, run_id: str, *, check_source: bool = False) -> tuple[Any, ...]:
        directory = self._directory(run_id)
        if check_source:
            self._source()
        manifest = _keys(_load(_read_file(directory / "run.json")), {
            "schema", "run_id", "preset", "created_at", "context", "certificate_sha256", "labels_sha256",
        }, "registered run")
        if (manifest["schema"] != "mra-rr-public-web-run/1.0" or manifest["run_id"] != run_id
                or type(manifest["preset"]) is not str or manifest["preset"] not in PRESETS
                or type(manifest["created_at"]) is not str):
            raise ResearchWebError("Invalid registered research run")
        parameters = PRESETS[manifest["preset"]]
        context = ResearchContext.from_dict(manifest["context"])
        data = {name: _read_file(directory / name) for name in INPUT_ARTIFACTS}
        bindings = {
            "retained-law.json": context.retained_law_sha256,
            "retained-responses.json": context.retained_response_sha256,
            "history.json": context.complete_history_sha256,
            "request-plan.json": context.request_plan_sha256,
            "synthetic-labels.json": manifest["labels_sha256"],
        }
        if any(_sha(data[name]) != expected for name, expected in bindings.items()):
            raise ResearchWebError("Bound research input bytes changed; execution is blocked")
        values = {name: _load(raw) for name, raw in data.items()}
        expected_labels = {"schema": LABELS_SCHEMA, "records": _roster()}
        if values["synthetic-labels.json"] != expected_labels or _json_bytes(values["synthetic-labels.json"]) != _json_bytes(expected_labels):
            raise ResearchWebError("The complete fixed public synthetic roster is required")
        if values["retained-law.json"] != {"schema": LAW_SCHEMA, "d": parameters.to_dict()["d"]}:
            raise ResearchWebError("The retained law differs from the fixed preset")
        expected_history = {
            "schema": HISTORY_SCHEMA, "retained_law_sha256": context.retained_law_sha256,
            "retained_response_sha256": context.retained_response_sha256,
            "additional_protected_outputs": False,
        }
        if values["history.json"] != expected_history or values["history.json"].get("additional_protected_outputs") is not False:
            raise ResearchWebError("The complete single retained RR history is required")
        ids = [record["record_id"] for record in _roster()]
        if values["request-plan.json"] != {
            "schema": REQUEST_SCHEMA, "parameters": parameters.to_dict(),
            "record_ids": ids, "visible_decisions": "public_fixed",
        }:
            raise ResearchWebError("The fixed public request plan differs from the registered preset")
        if values["plan.json"] != {"schema": PLAN_SCHEMA, "parameters": parameters.to_dict(), "context": context.to_dict()}:
            raise ResearchWebError("The external plan differs from the independently registered preset and context")
        responses = _keys(values["retained-responses.json"], {"schema", "records"}, "retained responses")
        if responses["schema"] != RESPONSES_SCHEMA or type(responses["records"]) is not list or len(responses["records"]) != 8:
            raise ResearchWebError("The retained response roster must contain all eight fixed records")
        for record, expected_id in zip(responses["records"], ids):
            _keys(record, {"record_id", "w"}, "retained response record")
            if record["record_id"] != expected_id or type(record["w"]) is not int or record["w"] not in (0, 1):
                raise ResearchWebError("The fixed retained roster requires integer binary responses")
        original_digest = certificate_digest(build_certificate(parameters, context))
        if manifest["certificate_sha256"] != original_digest:
            raise ResearchWebError("The original certificate registration differs from the fixed preset")
        verified = verify_certificate(
            data["certificate.json"], expected_parameters=parameters,
            expected_context=context, expected_certificate_sha256=original_digest,
        )
        records = [{**labels, "w": response["w"]} for labels, response in zip(_roster(), responses["records"])]
        return directory, manifest, parameters, context, data, verified, records

    def _receipt(self, directory: Path, run_id: str, verified: Any, *, raw: bytes | None = None) -> dict[str, Any] | None:
        path = directory / "verification.json"
        _check_path(path)
        if raw is None:
            if not path.exists():
                return None
            raw = _read_file(path)
        receipt = _keys(_load(raw), {"schema", "run_id", "verified_at", "verification"}, "verification receipt")
        if (receipt["schema"] != "mra-rr-web-verification/1.0" or receipt["run_id"] != run_id
                or type(receipt["verified_at"]) is not str or receipt["verification"] != _summary(verified)
                or _json_bytes(receipt["verification"]) != _json_bytes(_summary(verified))):
            raise ResearchWebError("The original-certificate verification receipt is invalid")
        return {**receipt["verification"], "verified_at": receipt["verified_at"]}

    def _block(self, directory: Path, context: ResearchContext, verified: Any) -> dict[str, Any] | None:
        target = directory / "randomized-block.json"
        reservation = directory / "sample-reservation.json"
        completion = directory / "sampling-completion.json"
        for path in (target, reservation, completion):
            _check_path(path)
        if not all(path.exists() for path in (target, reservation, completion)):
            return None
        try:
            reserved = _keys(_load(_read_file(reservation)), {
                "schema", "status", "run_id", "reserved_at", "certificate_sha256",
                "authorization_effect", "production_execution_qualified",
            }, "sampling reservation")
            if (reserved["schema"] != "mra-rr-web-reservation/1.0"
                    or reserved["run_id"] != directory.name
                    or type(reserved["reserved_at"]) is not str
                    or reserved["certificate_sha256"] != verified.digest
                    or reserved["status"] != "reserved_incomplete"
                    or reserved["authorization_effect"] != "none"
                    or reserved["production_execution_qualified"] is not False):
                return None
            completed = _keys(_load(_read_file(completion)), {
                "schema", "run_id", "completed_at", "block_sha256", "certificate_sha256",
                "authorization_effect", "production_execution_qualified",
            }, "sampling completion receipt")
            raw = _read_file(target)
            if (completed["schema"] != "mra-rr-web-completion/1.0"
                    or completed["run_id"] != directory.name
                    or type(completed["completed_at"]) is not str
                    or completed["certificate_sha256"] != verified.digest
                    or completed["block_sha256"] != _sha(raw)
                    or completed["authorization_effect"] != "none"
                    or completed["production_execution_qualified"] is not False):
                return None
            block = _keys(_load(raw), {
                "schema", "status", "certificate_sha256", "retained_response_sha256",
                "records", "authorization_effect", "production_execution_qualified", "history_reservation",
            }, "sampled block")
            if (block["schema"] != BLOCK_SCHEMA or block["status"] != "completed"
                    or block["certificate_sha256"] != verified.digest
                    or block["retained_response_sha256"] != context.retained_response_sha256
                    or block["authorization_effect"] != "none" or block["production_execution_qualified"] is not False
                    or block["history_reservation"] != HISTORY_RESERVATION
                    or type(block["records"]) is not list or len(block["records"]) != 8):
                return None
            for record, expected in zip(block["records"], _roster()):
                _keys(record, {"record_id", "labels"}, "sampled record")
                if (record["record_id"] != expected["record_id"] or type(record["labels"]) is not list
                        or len(record["labels"]) != verified.parameters.r
                        or any(type(bit) is not int or bit not in (0, 1) for bit in record["labels"])):
                    return None
            return block
        except (OSError, ValueError):
            return None

    def _sampling(self, directory: Path, context: ResearchContext, verified: Any, receipt: Any) -> tuple[dict[str, Any], Any]:
        reserved = directory / "sample-reservation.json"
        output = directory / "randomized-block.json"
        completion = directory / "sampling-completion.json"
        _check_path(reserved)
        _check_path(output)
        _check_path(completion)
        block = self._block(directory, context, verified)
        if block is not None:
            status = "completed"
        elif reserved.exists() or output.exists() or completion.exists():
            status = "reserved_incomplete"
        elif receipt is None:
            status = "blocked_verification"
        elif verified.claim == "infeasible":
            status = "infeasible"
        else:
            status = "ready"
        return {"status": status, "record_count": 8, "history_reservation": HISTORY_RESERVATION, **AUTHORITY}, block

    def detail(self, run_id: str) -> dict[str, Any]:
        directory, manifest, parameters, context, data, verified, records = self._inputs(run_id)
        receipt = self._receipt(directory, run_id, verified)
        sampling, block = self._sampling(directory, context, verified, receipt)
        if block is not None:
            for record, sampled in zip(records, block["records"]):
                record["sampled_labels"] = sampled["labels"]
        artifacts = list(INPUT_ARTIFACTS)
        if receipt is not None:
            artifacts.append("verification.json")
        if block is not None:
            artifacts.extend(("randomized-block.json", "sampling-completion.json"))
        attempts = sorted(path.name for path in directory.iterdir() if _ATTEMPT.fullmatch(path.name))
        return {
            "run_id": run_id, "preset": manifest["preset"], "created_at": manifest["created_at"],
            "parameters": parameters.to_dict(), "context": context.to_dict(),
            "certificate": _load(data["certificate.json"]),
            "certificate_text": data["certificate.json"].decode("utf-8"),
            "verification": receipt or {"status": "not_verified", **AUTHORITY},
            "sampling": sampling, "records": records,
            "artifacts": [{"name": name, "url": f"{PREFIX}/runs/{run_id}/artifacts/{name}"} for name in artifacts],
            "verification_attempt_count": len(attempts), **AUTHORITY,
        }

    def runs(self) -> dict[str, Any]:
        _check_path(self.root)
        summaries = []
        unavailable = 0
        for directory in self.root.iterdir():
            if not _RUN_ID.fullmatch(directory.name):
                continue
            try:
                detail = self.detail(directory.name)
                summaries.append({key: detail[key] for key in ("run_id", "preset", "created_at", "verification", "sampling")})
            except (OSError, ValueError):
                unavailable += 1
        summaries.sort(key=lambda entry: (entry["created_at"], entry["run_id"]), reverse=True)
        return {"runs": summaries, "unavailable_run_count": unavailable, **AUTHORITY}

    def verify(self, run_id: str, certificate: str) -> dict[str, Any]:
        if type(certificate) is not str or len(certificate.encode("utf-8")) > MAX_JSON_BYTES:
            raise ResearchWebError("A bounded certificate JSON string is required", 422)
        directory = self._directory(run_id)
        attempt: dict[str, Any] = {"accepted": False, "attempted_at": _now()}
        try:
            inputs = self._inputs(run_id, check_source=True)
            _, _, parameters, context, _, original, _ = inputs
            candidate = verify_certificate(
                certificate, expected_parameters=parameters, expected_context=context,
                expected_certificate_sha256=original.digest,
            )
            receipt = self._receipt(directory, run_id, original)
            if receipt is None:
                try:
                    _write_exclusive(directory / "verification.json", {
                        "schema": "mra-rr-web-verification/1.0", "run_id": run_id,
                        "verified_at": _now(), "verification": _summary(candidate),
                    })
                except FileExistsError:
                    # Another valid request may have created the same receipt.
                    self._receipt(directory, run_id, original)
            attempt.update({"accepted": True, "verification": _summary(candidate)})
        except (OSError, CertificateError, ResearchWebError) as exc:
            attempt["error"] = str(exc)
        # Invalid attempts have their own immutable files and never erase a receipt.
        _write_exclusive(directory / f"verify-attempt-{uuid4().hex}.json", {
            "schema": "mra-rr-web-verification-attempt/1.0", "run_id": run_id,
            "certificate": certificate, "attempt": attempt, **AUTHORITY,
        })
        return {"run": self.detail(run_id), "attempt": attempt, **AUTHORITY}

    def sample(self, run_id: str) -> dict[str, Any]:
        directory, _, parameters, context, data, verified, records = self._inputs(run_id, check_source=True)
        receipt = self._receipt(directory, run_id, verified)
        if receipt is None:
            raise ResearchWebError("Verify the original registered certificate before sampling")
        if verified.claim == "infeasible":
            raise ResearchWebError("An infeasible certificate cannot be sampled")
        for name in ("sample-reservation.json", "randomized-block.json", "sampling-completion.json"):
            target = directory / name
            _check_path(target)
            if target.exists():
                raise ResearchWebError("This public research run already has a draw reserved")
        sampler = ConditionalSampler(
            data["certificate.json"], expected_parameters=parameters,
            expected_context=context, expected_certificate_sha256=verified.digest,
        )
        try:
            _write_exclusive(directory / "sample-reservation.json", {
                "schema": "mra-rr-web-reservation/1.0", "status": "reserved_incomplete",
                "run_id": run_id, "reserved_at": _now(),
                "certificate_sha256": verified.digest, **AUTHORITY,
            })
        except FileExistsError as exc:
            raise ResearchWebError("This public research run already has a draw reserved") from exc
        try:
            # No file is made downloadable until every record has been drawn.
            sampled = [
                {"record_id": record["record_id"], "labels": list(sampler.sample(record["labels"], record["w"], record_id=record["record_id"]))}
                for record in records
            ]
            block = {
                "schema": BLOCK_SCHEMA, "status": "completed",
                "certificate_sha256": verified.digest,
                "retained_response_sha256": context.retained_response_sha256,
                "records": sampled, "history_reservation": HISTORY_RESERVATION, **AUTHORITY,
            }
            _write_exclusive(directory / "randomized-block.json", block)
            # Publishing this receipt is the final step. A crash while writing
            # either file leaves a durable reservation and no downloadable block.
            _write_exclusive(directory / "sampling-completion.json", {
                "schema": "mra-rr-web-completion/1.0", "run_id": run_id,
                "completed_at": _now(), "certificate_sha256": verified.digest,
                "block_sha256": _sha(_json_bytes(block)), **AUTHORITY,
            })
        except (OSError, SamplingError) as exc:
            raise ResearchWebError("Sampling did not complete; the reservation is preserved and another draw is refused") from exc
        return self.detail(run_id)

    def artifact(self, run_id: str, name: str) -> bytes:
        # Only fixed names are accepted; never interpret a browser path.
        if name not in (*INPUT_ARTIFACTS, "verification.json", "randomized-block.json", "sampling-completion.json"):
            raise ResearchWebError("Research artifact not found", 404)
        directory = self._directory(run_id)
        detail = self.detail(run_id)
        if name not in {entry["name"] for entry in detail["artifacts"]}:
            raise ResearchWebError("Research artifact is unavailable or incomplete", 404)
        data = _read_file(directory / name)
        # Revalidate the exact snapshot returned in the Response. The file may
        # change between detail validation and this read; never send partial or
        # changed block bytes from that gap, or reopen via FileResponse.
        _, _, _, context, inputs, verified, _ = self._inputs(run_id)
        if name in inputs:
            if data != inputs[name]:
                raise ResearchWebError("Research input changed during download")
        elif name == "verification.json":
            # Validate the captured bytes themselves. Comparing parsed values
            # from a later read could treat boolean and integer fields alike.
            receipt = self._receipt(directory, run_id, verified, raw=data)
            if receipt is None:
                raise ResearchWebError("Research verification is unavailable", 404)
        else:
            block = self._block(directory, context, verified)
            if block is None:
                raise ResearchWebError("Research artifact is unavailable or incomplete", 404)
            if name == "randomized-block.json":
                # A byte digest also catches benign whitespace changes after
                # completion rather than silently reinterpreting saved evidence.
                completion = _load(_read_file(directory / "sampling-completion.json"))
                if _sha(data) != completion["block_sha256"] or _load(data) != block:
                    raise ResearchWebError("Sampled block changed during download")
            elif data != _read_file(directory / "sampling-completion.json"):
                raise ResearchWebError("Sampling receipt changed during download")
        return data


async def _payload(request: Request, expected: set[str]) -> dict[str, Any]:
    if request.headers.get("content-type", "").split(";")[0] != "application/json":
        raise HTTPException(415, "JSON required")
    data = await request.body()
    if len(data) > 16_384:
        raise HTTPException(413, "request too large")
    try:
        return _keys(_load(data), expected, "research request")
    except CertificateError as exc:
        raise HTTPException(422, str(exc)) from exc


def _call(function: Any, *arguments: Any) -> Any:
    try:
        return function(*arguments)
    except ResearchWebError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    except (CertificateError, SamplingError, OSError) as exc:
        raise HTTPException(409, "Research evidence is unavailable or invalid; execution is blocked") from exc


def mount_research_routes(
    app: FastAPI, data_dir: str | Path, *, source_pdf: str | Path = DEFAULT_SOURCE_PDF,
) -> ResearchRunStore:
    """Mount under the existing console's trusted-host/same-origin boundary."""
    from .usefulness_store import UsefulnessRunStore
    store = UsefulnessRunStore(data_dir, source_pdf=source_pdf)

    @app.get(f"{PREFIX}/catalog")
    def catalog():
        return _call(store.catalog)

    @app.get(f"{PREFIX}/usefulness/specification")
    def usefulness_specification():
        return _call(store.specification)

    @app.get(f"{PREFIX}/runs")
    def runs():
        return _call(store.runs)

    @app.post(f"{PREFIX}/runs", status_code=201)
    async def create(request: Request):
        payload = await _payload(request, {"preset"})
        return await run_in_threadpool(_call, store.create, payload["preset"])

    @app.get(f"{PREFIX}/runs/{{run_id}}")
    def detail(run_id: str):
        return _call(store.detail, run_id)

    @app.post(f"{PREFIX}/runs/{{run_id}}/verify")
    async def verify(run_id: str, request: Request):
        payload = await _payload(request, {"certificate"})
        return await run_in_threadpool(_call, store.verify, run_id, payload["certificate"])

    @app.post(f"{PREFIX}/runs/{{run_id}}/sample")
    async def sample(run_id: str, request: Request):
        await _payload(request, set())
        return await run_in_threadpool(_call, store.sample, run_id)

    @app.post(f"{PREFIX}/runs/{{run_id}}/evaluate")
    async def evaluate(run_id: str, request: Request):
        await _payload(request, set())
        return await run_in_threadpool(_call, store.evaluate, run_id)

    @app.get(f"{PREFIX}/runs/{{run_id}}/evaluations/{{evaluation_id}}")
    def evaluation(run_id: str, evaluation_id: str):
        return _call(store.evaluation, run_id, evaluation_id)

    @app.get(f"{PREFIX}/runs/{{run_id}}/evaluations/{{evaluation_id}}/artifacts/{{name}}")
    def evaluation_artifact(run_id: str, evaluation_id: str, name: str):
        data = _call(store.evaluation_artifact, run_id, evaluation_id, name)
        return Response(
            data, media_type="text/plain" if name.endswith(".txt") else "application/json",
            headers={"Content-Disposition": f'attachment; filename="{name}"'},
        )

    @app.get(f"{PREFIX}/runs/{{run_id}}/artifacts/{{name}}")
    def artifact(run_id: str, name: str):
        data = _call(store.artifact, run_id, name)
        return Response(
            data, media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{name}"'},
        )

    return store
