"""Operator CLI for the isolated retained-RR research kernel, not MRAP authority."""
from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import secrets
import sys
from typing import Any

from .certificates import (
    CertificateError, MAX_JSON_BYTES, RRParameters, ResearchContext,
    build_certificate, certificate_json, verify_certificate,
)
from .sampling import ConditionalSampler, SamplingError

PLAN_SCHEMA = "mra-rr-research-plan/1.0"
LAW_SCHEMA = "mra-retained-binary-rr/1.0"
RESPONSES_SCHEMA = "mra-rr-retained-responses/1.0"
HISTORY_SCHEMA = "mra-rr-single-retained-history/1.0"
REQUEST_SCHEMA = "mra-rr-fixed-request-plan/1.0"
LABELS_SCHEMA = "mra-rr-preexisting-labels/1.0"
BLOCK_SCHEMA = "mra-rr-randomized-block/1.0"
MAX_RECORDS = 10000


def _keys(value: Any, expected: set[str], name: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != expected:
        raise CertificateError(f"Invalid {name} fields")
    return value


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    value = {}
    for key, item in items:
        if key in value:
            raise CertificateError("Duplicate JSON field")
        value[key] = item
    return value


def _constant(value: str) -> None:
    raise CertificateError("Nonfinite JSON input")


def _read(path: str | Path) -> bytes:
    with Path(path).open("rb") as stream:
        data = stream.read(MAX_JSON_BYTES + 1)
    if len(data) > MAX_JSON_BYTES:
        raise CertificateError("Research input exceeds the file-size limit")
    return data


def _load(data: bytes) -> dict[str, Any]:
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_constant)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise CertificateError("Invalid research input JSON") from exc
    if type(value) is not dict:
        raise CertificateError("Research input must be a JSON object")
    return value


def _plan(path: str) -> tuple[RRParameters, ResearchContext]:
    value = _keys(_load(_read(path)), {"schema", "parameters", "context"}, "plan")
    if value["schema"] != PLAN_SCHEMA:
        raise CertificateError("Unsupported research plan schema")
    return RRParameters.from_dict(value["parameters"]), ResearchContext.from_dict(value["context"])


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"


def _write(path: str | Path, value: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(_json(value))


def _summary(verified: Any) -> dict[str, Any]:
    return {
        "status": verified.claim, "certificate_sha256": verified.digest,
        "marginal_label_correctness": None if verified.marginal_accuracy is None else str(verified.marginal_accuracy),
        "authorization_effect": "none", "premises_independently_verified": False,
        "scope": "one retained RR law and one preexisting fresh-label block",
    }


def _bound_file(path: str, expected: str, name: str) -> dict[str, Any]:
    data = _read(path)
    if hashlib.sha256(data).hexdigest() != expected:
        raise CertificateError(f"The {name} file differs from its registered digest")
    return _load(data)


def _records(value: Any, schema: str, field: str) -> tuple[list[str], dict[str, Any]]:
    value = _keys(value, {"schema", "records"}, field)
    if value["schema"] != schema or type(value["records"]) is not list or not 1 <= len(value["records"]) <= MAX_RECORDS:
        raise CertificateError(f"Invalid bounded {field} records")
    ids, contents = [], {}
    for record in value["records"]:
        record = _keys(record, {"record_id", field}, field + " record")
        record_id = record["record_id"]
        if type(record_id) is not str or not record_id or len(record_id) > 256 or record_id in contents:
            raise CertificateError("Invalid or duplicate public record identifier")
        ids.append(record_id)
        contents[record_id] = record[field]
    return ids, contents


def _sample(args: argparse.Namespace) -> dict[str, Any]:
    parameters, context = _plan(args.plan)
    certificate = _read(args.certificate)
    sampler = ConditionalSampler(
        certificate, expected_parameters=parameters, expected_context=context,
        expected_certificate_sha256=args.expected_digest,
    )
    law = _keys(_bound_file(args.retained_law, context.retained_law_sha256, "retained law"), {"schema", "d"}, "retained law")
    if law["schema"] != LAW_SCHEMA or law["d"] != parameters.to_dict()["d"]:
        raise CertificateError("The retained law does not match the registered binary RR law")
    response_document = _bound_file(args.retained_responses, context.retained_response_sha256, "retained responses")
    response_ids, responses = _records(response_document, RESPONSES_SCHEMA, "w")
    history = _keys(_bound_file(args.history, context.complete_history_sha256, "complete history"), {"schema", "retained_law_sha256", "retained_response_sha256", "additional_protected_outputs"}, "history")
    if (history["schema"] != HISTORY_SCHEMA or history["retained_law_sha256"] != context.retained_law_sha256
            or history["retained_response_sha256"] != context.retained_response_sha256
            or history["additional_protected_outputs"] is not False):
        raise CertificateError("This kernel requires the declared single retained RR history")
    requests = _keys(_bound_file(args.request_plan, context.request_plan_sha256, "request plan"), {"schema", "parameters", "record_ids", "visible_decisions"}, "request plan")
    if (requests["schema"] != REQUEST_SCHEMA or requests["parameters"] != parameters.to_dict()
            or requests["visible_decisions"] != "public_fixed" or type(requests["record_ids"]) is not list
            or requests["record_ids"] != response_ids):
        raise CertificateError("The fixed public request plan does not match the retained roster")
    label_ids, labels = _records(_load(_read(args.labels)), LABELS_SCHEMA, "labels")
    if label_ids != response_ids:
        raise CertificateError("Labels and retained responses must use the same fixed public record order")
    # Validate the entire fixed roster before reserving output or reading randomness.
    for record_id in response_ids:
        if type(responses[record_id]) is not int or responses[record_id] not in (0, 1):
            raise CertificateError("Retained responses must be integer binary values")
        vector = labels[record_id]
        if type(vector) is not list or len(vector) != parameters.r + 1 or any(type(bit) is not int or bit not in (0, 1) for bit in vector):
            raise CertificateError("Each record requires its complete preexisting binary label vector")
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive reservation precedes all draws. Failures retain the reservation
    # rather than silently retrying the protected block or overwriting evidence.
    with target.open("x+", encoding="utf-8", newline="\n") as stream:
        stream.write(_json({"schema": BLOCK_SCHEMA, "status": "reserved_incomplete", "certificate_sha256": sampler.certificate_sha256, "authorization_effect": "none"}))
        stream.flush()
        output = {
            "schema": BLOCK_SCHEMA, "status": "completed",
            "certificate_sha256": sampler.certificate_sha256,
            "retained_response_sha256": context.retained_response_sha256,
            "records": [{"record_id": record_id, "labels": list(sampler.sample(labels[record_id], responses[record_id], record_id=record_id))} for record_id in response_ids],
            "authorization_effect": "none", "production_execution_qualified": False,
            "history_reservation": "output-local only; no authoritative portfolio reservation",
        }
        stream.seek(0); stream.truncate(); stream.write(_json(output)); stream.flush()
    return {"status": "completed", "records": len(response_ids), "output": str(target), "certificate_sha256": sampler.certificate_sha256, "authorization_effect": "none"}


def _demo(path: str) -> dict[str, Any]:
    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=False)
    parameters = RRParameters(2, Fraction(3), Fraction(9), Fraction(2, 3))
    vectors = [tuple((index >> shift) & 1 for shift in (2, 1, 0)) for index in range(8)]
    ids = [f"public-synthetic-{index:03}" for index in range(8)]
    _write(directory / "synthetic-labels.json", {"schema": LABELS_SCHEMA, "records": [{"record_id": record_id, "labels": list(bits)} for record_id, bits in zip(ids, vectors)]})
    _write(directory / "retained-law.json", {"schema": LAW_SCHEMA, "d": "3/1"})
    _write(directory / "retained-responses.json", {"schema": RESPONSES_SCHEMA, "records": [{"record_id": record_id, "w": bits[0] if secrets.randbelow(4) < 3 else 1 - bits[0]} for record_id, bits in zip(ids, vectors)]})
    digest = lambda name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
    law_digest, response_digest = digest("retained-law.json"), digest("retained-responses.json")
    _write(directory / "history.json", {"schema": HISTORY_SCHEMA, "retained_law_sha256": law_digest, "retained_response_sha256": response_digest, "additional_protected_outputs": False})
    _write(directory / "request-plan.json", {"schema": REQUEST_SCHEMA, "parameters": parameters.to_dict(), "record_ids": ids, "visible_decisions": "public_fixed"})
    context = ResearchContext(law_digest, response_digest, digest("history.json"), digest("request-plan.json"))
    _write(directory / "plan.json", {"schema": PLAN_SCHEMA, "parameters": parameters.to_dict(), "context": context.to_dict()})
    document = build_certificate(parameters, context)
    _write(directory / "certificate.json", document)
    verified = verify_certificate(document, expected_parameters=parameters, expected_context=context)
    args = argparse.Namespace(plan=str(directory / "plan.json"), certificate=str(directory / "certificate.json"), retained_law=str(directory / "retained-law.json"), retained_responses=str(directory / "retained-responses.json"), history=str(directory / "history.json"), request_plan=str(directory / "request-plan.json"), labels=str(directory / "synthetic-labels.json"), output=str(directory / "randomized-block.json"), expected_digest=verified.digest)
    sampled = _sample(args)
    _write(directory / "verification.json", _summary(verified))
    return {**sampled, "demo": "fully public synthetic labels; no protected agency data", "marginal_label_correctness": str(verified.marginal_accuracy)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Exact retained-RR research certificates and one-block conditional sampling; no release authority")
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="Build an exact shell certificate from an external registered plan")
    build.add_argument("--plan", required=True); build.add_argument("--output", required=True)
    build.add_argument("--claim", choices=("feasible", "optimal"), default="optimal")
    verify = commands.add_parser("verify", help="Replay a certificate against the external plan")
    sample = commands.add_parser("sample", help="Sample one bound block; all history inputs are required")
    for command in (verify, sample):
        command.add_argument("--plan", required=True); command.add_argument("--certificate", required=True)
        command.add_argument("--expected-digest")
    for name in ("retained-law", "retained-responses", "history", "request-plan", "labels", "output"):
        sample.add_argument("--" + name, required=True)
    demo = commands.add_parser("demo", help="Create and execute a new fully public synthetic example")
    demo.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            parameters, context = _plan(args.plan)
            document = build_certificate(parameters, context, args.claim)
            verified = verify_certificate(document, expected_parameters=parameters, expected_context=context)
            _write(args.output, document); output = _summary(verified)
        elif args.command == "verify":
            parameters, context = _plan(args.plan)
            output = _summary(verify_certificate(_read(args.certificate), expected_parameters=parameters, expected_context=context, expected_certificate_sha256=args.expected_digest))
        elif args.command == "sample":
            output = _sample(args)
        else:
            output = _demo(args.output_dir)
        print(_json(output), end="")
        return 0
    except (CertificateError, SamplingError, OSError, ValueError) as exc:
        print(_json({"status": "error", "error": str(exc), "authorization_effect": "none"}), end="", file=sys.stderr)
        return 2
