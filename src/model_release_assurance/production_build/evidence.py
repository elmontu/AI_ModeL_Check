"""Bounded local build evidence for public fixtures, never production admission.

PyPI JSON observations cover listed distribution advisories only: they do not
authenticate the fetcher or scan wheel code, malware, containers or licenses.
Signatures bind a trusted local statement, not the truth of its observations.
This custom envelope makes no SLSA level or hermetic-build claim.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from packaging.version import InvalidVersion, Version

MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_OBSERVATION_BYTES = 32 * 1024 * 1024
MAX_DOCUMENT_BYTES = 8 * 1024 * 1024
MAX_COMPONENTS = 256
MAX_AGE_SECONDS = 86400
_DOMAIN = b"mra-local-build-provenance/v1\x00"
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/+-]{0,255}\Z")
_ARTIFACT_FIELDS = {"name", "version", "filename", "sha256", "size_bytes"}
_MATERIALS = {"source_manifest_sha256", "dependency_manifest_sha256", "inventory_sha256",
              "sbom_sha256", "advisory_report_sha256", "policy_sha256",
              "test_receipt_sha256", "build_result_sha256"}
_STATEMENT_FIELDS = {"schema", "environment", "build_id", "builder_id", "platform",
                     "builder_versions", "issued_at", "expires_at", "subject", "materials"}
_EXPECTED_FIELDS = _STATEMENT_FIELDS - {"issued_at", "expires_at"}
_FLAGS = {"fixture_only": True, "production_authorized": False, "deployable": False}
_PRODUCTION_PENDING = [
    "Agency approval of licenses, dependency policy and build scope.",
    "A qualified isolated builder, production signing trust and authenticated provenance.",
    "Production advisory, code/malware, container and infrastructure admission controls.",
]


class BuildEvidenceError(ValueError):
    """Malformed or inconsistent local fixture evidence; no raw input is echoed."""


def _fail():
    raise BuildEvidenceError("Invalid local build evidence")


def canonical_bytes(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                          allow_nan=False).encode("ascii")
    except (ValueError, TypeError, RecursionError, UnicodeError):
        _fail()


def canonical_sha256(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _integer(value, minimum=0, maximum=2**53 - 1):
    if type(value) is not int or not minimum <= value <= maximum:
        _fail()
    return value


def _text(value, maximum=256):
    if type(value) is not str or not 1 <= len(value) <= maximum or any(ord(c) < 32 or ord(c) > 126 for c in value):
        _fail()
    return value


def _identifier(value):
    if type(value) is not str or not _ID.fullmatch(value):
        _fail()
    return value


def _hash(value):
    if type(value) is not str or not _HASH.fullmatch(value):
        _fail()
    return value


def _exact(value, fields):
    if type(value) is not dict or set(value) != set(fields):
        _fail()
    return value


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            _fail()
        result[key] = value
    return result


def _depth(value, level=0):
    if level > 32:
        _fail()
    if type(value) is dict:
        for item in value.values():
            _depth(item, level + 1)
    elif type(value) is list:
        for item in value:
            _depth(item, level + 1)


def strict_json_bytes(content, *, maximum=MAX_DOCUMENT_BYTES):
    """Read bounded JSON with duplicate keys and nonfinite numbers refused."""
    if type(content) is not bytes or not 0 < len(content) <= maximum:
        _fail()
    try:
        parsed = json.loads(content.decode("utf-8"), object_pairs_hook=_pairs,
                            parse_constant=lambda _: _fail())
        _depth(parsed)
        return parsed
    except (ValueError, UnicodeError, TypeError, RecursionError):
        _fail()


def _copy(value, maximum=MAX_DOCUMENT_BYTES):
    return strict_json_bytes(canonical_bytes(value), maximum=maximum)


def _name(value):
    if type(value) is not str or len(value) > 128 or not _NAME.fullmatch(value):
        _fail()
    return value


def _version(value):
    _text(value, 128)
    try:
        Version(value)
    except InvalidVersion:
        _fail()
    return value


def _filename(value):
    _text(value, 255)
    if not value.endswith(".whl") or value in {".", ".."} or any(c in value for c in "/\\:"):
        _fail()
    return value


def validate_inventory(inventory):
    if type(inventory) is not list or not 1 <= len(inventory) <= MAX_COMPONENTS:
        _fail()
    result, names = [], set()
    for entry in inventory:
        _exact(entry, _ARTIFACT_FIELDS)
        name = _name(entry["name"])
        if name in names:
            _fail()
        names.add(name)
        _version(entry["version"])
        _filename(entry["filename"])
        _hash(entry["sha256"])
        _integer(entry["size_bytes"], 1, 2**31)
        result.append(dict(entry))
    return sorted(result, key=lambda item: item["name"])


def _vulnerabilities(value):
    if type(value) is not list or len(value) > 4096:
        _fail()
    identifiers = set()
    for entry in value:
        if type(entry) is not dict or "id" not in entry:
            _fail()
        identifier = _text(entry["id"], 256)
        if identifier in identifiers:
            _fail()
        identifiers.add(identifier)
    # PyPI advisory objects may gain fields. All findings, including withdrawn
    # entries, remain findings in this deliberately conservative local screen.
    return value


def parse_pypi_observation(name, version, response_bytes, *, fetched_at):
    """Bind the exact saved response body to its expected PyPI project/version."""
    _name(name)
    _version(version)
    _integer(fetched_at)
    body = strict_json_bytes(response_bytes, maximum=MAX_RESPONSE_BYTES)
    if type(body) is not dict or type(body.get("info")) is not dict:
        _fail()
    actual_name = body["info"].get("name")
    if type(actual_name) is not str or re.sub(r"[-_.]+", "-", actual_name).lower() != name:
        _fail()
    if body["info"].get("version") != version or "vulnerabilities" not in body:
        _fail()
    vulnerabilities = _vulnerabilities(body["vulnerabilities"])
    return {"name": name, "version": version, "fetched_at": fetched_at, "source": "pypi-json",
            "status": "ok", "response_sha256": hashlib.sha256(response_bytes).hexdigest(),
            "response_body_base64": base64.b64encode(response_bytes).decode("ascii"),
            "vulnerabilities": vulnerabilities}


def _observation(value):
    if type(value) is not dict:
        _fail()
    common = {"name", "version", "fetched_at", "source", "status"}
    if value.get("status") == "error":
        _exact(value, common | {"error"})
        if value["error"] != "fetch_failed":
            _fail()
    elif value.get("status") == "ok":
        _exact(value, common | {"response_sha256", "response_body_base64", "vulnerabilities"})
        encoded = value["response_body_base64"]
        if type(encoded) is not str or not 1 <= len(encoded) <= 4 * ((MAX_RESPONSE_BYTES + 2) // 3):
            _fail()
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (ValueError, TypeError):
            _fail()
        if base64.b64encode(raw).decode("ascii") != encoded:
            _fail()
        derived = parse_pypi_observation(value["name"], value["version"], raw,
                                         fetched_at=value["fetched_at"])
        if derived != value:
            _fail()
    else:
        _fail()
    _name(value["name"])
    _version(value["version"])
    _integer(value["fetched_at"])
    if value["source"] != "pypi-json":
        _fail()
    return value


def evaluate_advisories(inventory, observations, *, now):
    """No missing, extra, duplicate, error, stale or future observation is clear."""
    _integer(now)
    inventory = validate_inventory(inventory)
    if type(observations) is not list or len(observations) > MAX_COMPONENTS:
        _fail()
    observations = _copy(observations, maximum=MAX_OBSERVATION_BYTES)
    wanted = {(item["name"], item["version"]) for item in inventory}
    observed, checked, findings, reasons = set(), set(), [], []
    for observation in observations:
        _observation(observation)
        key = (observation["name"], observation["version"])
        if key in observed:
            reasons.append("duplicate_observation")
        observed.add(key)
        if key not in wanted:
            reasons.append("unexpected_component_or_version")
        fresh = 0 <= now - observation["fetched_at"] <= MAX_AGE_SECONDS
        if not fresh:
            reasons.append("stale_or_future_observation")
        if observation["status"] != "ok":
            reasons.append("observation_error")
            continue
        if key in wanted and fresh:
            checked.add(key)
        for finding in observation["vulnerabilities"]:
            findings.append({"name": key[0], "version": key[1], "advisory_id": finding["id"]})
    if wanted - observed:
        reasons.append("missing_component_observation")
    coverage = not reasons and checked == wanted
    if findings:
        reasons.append("reported_vulnerabilities")
    return {"schema": "mra-pypi-advisory-evaluation/v1", "evaluated_at": now,
            "inventory_sha256": canonical_sha256(inventory),
            "observations_sha256": canonical_sha256(observations),
            "source": "pypi-json", "scope": "listed-wheel-distributions-only",
            "required_components": len(wanted), "checked_components": len(checked),
            "coverage_complete": coverage, "advisory_clear": coverage and not findings,
            "findings": sorted(findings, key=lambda item: (item["name"], item["version"], item["advisory_id"])),
            "reasons": sorted(set(reasons)), **_FLAGS}


def _versions(value):
    if type(value) is not dict or not 1 <= len(value) <= 16:
        _fail()
    for name, version in value.items():
        _name(name)
        _version(version)
    return value


def _statement(value):
    value = _copy(value, maximum=64 * 1024)
    _exact(value, _STATEMENT_FIELDS)
    if value["schema"] != "mra-local-build-provenance/v1" or value["environment"] != "public_fixture":
        _fail()
    for field in ("build_id", "builder_id", "platform"):
        _identifier(value[field])
    _versions(value["builder_versions"])
    issued = _integer(value["issued_at"])
    expires = _integer(value["expires_at"])
    if not 0 < expires - issued <= MAX_AGE_SECONDS:
        _fail()
    subject = _exact(value["subject"], {"filename", "sha256", "size_bytes"})
    _filename(subject["filename"])
    _hash(subject["sha256"])
    _integer(subject["size_bytes"], 1, 2**31)
    _exact(value["materials"], _MATERIALS)
    for digest in value["materials"].values():
        _hash(digest)
    return value


def _public_key(value):
    if isinstance(value, Ed25519PublicKey):
        return value
    if type(value) is bytes and len(value) == 32:
        return Ed25519PublicKey.from_public_bytes(value)
    _fail()


def _key_id(key):
    return hashlib.sha256(key.public_bytes(serialization.Encoding.Raw,
                                           serialization.PublicFormat.Raw)).hexdigest()


def sign_fixture_provenance(statement, private_key):
    """Sign trusted fixture input; callers generate a distinct memory-only key."""
    statement = _statement(statement)
    if not isinstance(private_key, Ed25519PrivateKey):
        _fail()
    signature = private_key.sign(_DOMAIN + canonical_bytes(statement))
    return {"schema": "mra-local-build-attestation/v1", "algorithm": "Ed25519",
            "key_id": _key_id(private_key.public_key()), "statement": statement,
            "signature_base64url": base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")}


def verify_fixture_provenance(envelope, pinned_public_key, *, expected, now, signer_active):
    """Pinned current local trust plus exact expected context, never release authority."""
    reasons = []
    statement_digest = None
    try:
        _integer(now)
        if type(signer_active) is not bool or not signer_active:
            _fail()
        envelope = _copy(envelope, maximum=128 * 1024)
        _exact(envelope, {"schema", "algorithm", "key_id", "statement", "signature_base64url"})
        if envelope["schema"] != "mra-local-build-attestation/v1" or envelope["algorithm"] != "Ed25519":
            _fail()
        statement = _statement(envelope["statement"])
        _exact(expected, _EXPECTED_FIELDS)
        expected_statement = _statement({**expected, "issued_at": statement["issued_at"],
                                        "expires_at": statement["expires_at"]})
        if expected_statement != statement or not statement["issued_at"] <= now < statement["expires_at"]:
            _fail()
        key = _public_key(pinned_public_key)
        if envelope["key_id"] != _key_id(key):
            _fail()
        encoded = envelope["signature_base64url"]
        if type(encoded) is not str or not re.fullmatch(r"[A-Za-z0-9_-]{86}", encoded):
            _fail()
        signature = base64.urlsafe_b64decode(encoded + "==")
        if base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=") != encoded:
            _fail()
        key.verify(signature, _DOMAIN + canonical_bytes(statement))
        statement_digest = canonical_sha256(statement)
    except (BuildEvidenceError, InvalidSignature, ValueError, TypeError, RecursionError):
        reasons.append("provenance_not_verified")
    return {"schema": "mra-local-provenance-verification/v1", "fixture_verified": not reasons,
            "statement_sha256": statement_digest, "reasons": reasons, **_FLAGS}


def _policy(value):
    _exact(value, {"schema", "environment", "advisory_max_age_seconds", "license_review",
                   "required_test_profile", "require_zero_skips"})
    if (value["schema"] != "mra-local-build-policy/v1" or value["environment"] != "public_fixture"
            or type(value["advisory_max_age_seconds"]) is not int
            or value["advisory_max_age_seconds"] != MAX_AGE_SECONDS
            or value["license_review"] not in {"pending", "approved"}
            or value["required_test_profile"] != "government" or value["require_zero_skips"] is not True):
        _fail()
    return value


def _test_receipt(receipt):
    if type(receipt) is not dict or receipt.get("schema") != "required-test-profile/v1":
        _fail()
    if receipt.get("profile") != "government" or receipt.get("status") != "passed":
        _fail()
    counts = _exact(receipt.get("counts"), {"selected", "run", "skipped", "failures", "errors",
                                          "expected_failures", "unexpected_successes"})
    selected = _integer(counts["selected"], 1, 1000000)
    if type(counts["run"]) is not int or counts["run"] != selected:
        _fail()
    for field in ("skipped", "failures", "errors", "expected_failures", "unexpected_successes"):
        if type(counts[field]) is not int or counts[field] != 0:
            _fail()
    for field in ("discovery_problems", "skips", "failures", "errors", "expected_failures",
                  "unexpected_successes", "missing_dependency_reasons", "duplicate_test_ids"):
        if receipt.get(field) != []:
            _fail()
    ids = receipt.get("selected_test_ids")
    if type(ids) is not list or len(ids) != selected:
        _fail()
    for identifier in ids:
        _text(identifier, 1024)
    if len(set(ids)) != len(ids):
        _fail()
    modules = receipt.get("selected_modules")
    if type(modules) is not list or not modules:
        _fail()
    module_ids, paths = [], set()
    for item in modules:
        if type(item) is not dict or type(item.get("test_ids")) is not list:
            _fail()
        _text(item.get("path"), 1024)
        if item["path"] in paths:
            _fail()
        paths.add(item["path"])
        if _integer(item.get("test_count"), 1, 1000000) != len(item["test_ids"]):
            _fail()
        module_ids.extend(item["test_ids"])
    if module_ids != ids:
        _fail()
    ownership = receipt.get("source_ownership")
    if type(ownership) is not list or not ownership or any(
            type(item) is not dict or item.get("from_current_source") is not True for item in ownership):
        _fail()
    hashes = receipt.get("source_hashes")
    if type(hashes) is not list or not hashes:
        _fail()
    seen = set()
    for item in hashes:
        _exact(item, {"path", "sha256"})
        _text(item["path"], 1024)
        _hash(item["sha256"])
        if item["path"] in seen:
            _fail()
        seen.add(item["path"])


def _source_consistency(source, receipt):
    if type(source) is not dict or source.get("schema") != "local-build-source/v1":
        _fail()
    files = source.get("files")
    if type(files) is not list or not 1 <= len(files) <= 100000:
        _fail()
    captured = {}
    for item in files:
        _exact(item, {"path", "sha256", "size_bytes"})
        path = _text(item["path"], 1024)
        if any(c in path for c in "\\:") or any(part in {"", ".", ".."} for part in path.split("/")):
            _fail()
        if path in captured:
            _fail()
        captured[path] = _hash(item["sha256"])
        _integer(item["size_bytes"], 0, 2**31)
    tested = {item["path"]: item["sha256"] for item in receipt["source_hashes"]}
    if any(captured.get(path) != digest for path, digest in tested.items()):
        _fail()
    # Every selected test and shipped source/static asset must be represented.
    # This binds code bytes without mistaking a signature for proof of execution.
    required = {item["path"] for item in receipt["selected_modules"]}
    required.update(path for path in captured if path.startswith("src/model_release_assurance/")
                    and (path.endswith(".py") or "/static/" in path or path.endswith("/py.typed")))
    required.update(path for path in captured if path.startswith("scripts/")
                    and path.count("/") == 1 and path.endswith(".py"))
    required.update(path for path in captured if path.startswith("tests/") and path.endswith(".py"))
    if not any(path.startswith("src/model_release_assurance/") and path.endswith(".py") for path in required):
        _fail()
    if not required <= tested.keys():
        _fail()


def _build_result(result, statement):
    if (type(result) is not dict or result.get("schema") != "local-build-baseline/v1"
            or result.get("status") != "passed" or result.get("errors") != []
            or result.get("source_stable_at_end") is not True
            or result.get("source_manifest_sha256") != statement["materials"]["source_manifest_sha256"]
            or result.get("builder_versions") != statement["builder_versions"]):
        _fail()
    wheels = result.get("wheels")
    if type(wheels) is not list or len(wheels) != 2:
        _fail()
    for wheel in wheels:
        if type(wheel) is not dict or any(wheel.get(key) != value for key, value in statement["subject"].items()):
            _fail()
        _integer(wheel.get("verified_package_files"), 1, 1000000)
        _integer(wheel.get("verified_record_entries"), 1, 1000000)


def evaluate_admission(envelope, pinned_public_key, *, expected, now, signer_active,
                       inventory, observations, advisory_report_bytes, policy_bytes,
                       test_receipt_bytes, build_result_bytes, source_manifest_bytes):
    """Check actual bounded artifact bodies; successful fixture checks never deploy."""
    try:
        # Use one owned snapshot across signature and semantic checks. Caller
        # mutations must never replace signed materials after verification.
        envelope = _copy(envelope, maximum=128 * 1024)
        expected = _copy(expected, maximum=64 * 1024)
        inventory = _copy(inventory)
        observations = _copy(observations, maximum=MAX_OBSERVATION_BYTES)
    except BuildEvidenceError:
        return {"schema": "mra-local-build-admission/v1", "fixture_verified": False,
                "fixture_checks_passed": False, "reasons": ["provenance_not_verified"],
                "required_production_controls": list(_PRODUCTION_PENDING), **_FLAGS}
    verification = verify_fixture_provenance(envelope, pinned_public_key, expected=expected,
                                              now=now, signer_active=signer_active)
    reasons = list(verification["reasons"])
    if verification["fixture_verified"]:
        try:
            statement = _statement(envelope["statement"])
            inventory = validate_inventory(inventory)
            if canonical_sha256(inventory) != statement["materials"]["inventory_sha256"]:
                _fail()
            inventory_versions = {item["name"]: item["version"] for item in inventory}
            if any(inventory_versions.get(name) != version
                   for name, version in statement["builder_versions"].items()):
                _fail()
            bodies = {"advisory_report_sha256": advisory_report_bytes, "policy_sha256": policy_bytes,
                      "test_receipt_sha256": test_receipt_bytes, "build_result_sha256": build_result_bytes,
                      "source_manifest_sha256": source_manifest_bytes}
            parsed = {}
            for field, body in bodies.items():
                parsed[field] = strict_json_bytes(body)
                if hashlib.sha256(body).hexdigest() != statement["materials"][field]:
                    _fail()
            policy = _policy(parsed["policy_sha256"])
            advisory = parsed["advisory_report_sha256"]
            if type(advisory) is not dict:
                _fail()
            evaluated_at = _integer(advisory.get("evaluated_at"))
            if not 0 <= now - evaluated_at <= MAX_AGE_SECONDS:
                _fail()
            observed_report = evaluate_advisories(inventory, observations, now=evaluated_at)
            if observed_report != advisory:
                _fail()
            current_report = evaluate_advisories(inventory, observations, now=now)
            if not current_report["advisory_clear"]:
                reasons.extend(current_report["reasons"])
            if policy["license_review"] != "approved":
                reasons.append("license_review_pending")
            _test_receipt(parsed["test_receipt_sha256"])
            _source_consistency(parsed["source_manifest_sha256"], parsed["test_receipt_sha256"])
            _build_result(parsed["build_result_sha256"], statement)
        except (BuildEvidenceError, ValueError, TypeError, KeyError, RecursionError):
            reasons.append("material_evidence_not_verified")
    return {"schema": "mra-local-build-admission/v1",
            "fixture_verified": verification["fixture_verified"],
            "fixture_checks_passed": not reasons, "reasons": sorted(set(reasons)),
            "required_production_controls": list(_PRODUCTION_PENDING), **_FLAGS}





