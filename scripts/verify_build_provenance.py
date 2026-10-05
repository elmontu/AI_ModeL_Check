#!/usr/bin/env python3
"""Verify and sign a public local build fixture; never authorize deployment."""
from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import stat
import sys
import time
import uuid

ROOT = Path(__file__).absolute().parents[1]
sys.path.insert(0, str(ROOT / "src"))
_SPEC = importlib.util.spec_from_file_location("_mra_provenance_baseline", ROOT / "scripts/verify_build_baseline.py")
BASELINE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(BASELINE)

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from model_release_assurance.production_build.artifacts import (
    _read_file as _read_bounded_file, build_cyclonedx_sbom, validate_manifest)
from model_release_assurance.production_build.evidence import (
    MAX_DOCUMENT_BYTES, MAX_OBSERVATION_BYTES, canonical_sha256, evaluate_admission,
    sign_fixture_provenance, strict_json_bytes,
)

FLAGS = {"fixture_only": True, "production_authorized": False, "deployable": False}
LIMITATIONS = [
    "Self-generated memory-only signing key demonstrates local integrity, not agency signing trust.",
    "Saved public key is a fixture pin, not an independent certificate or custody attestation.",
    "Source consistency detects ordinary drift, not a malicious host or hermetic execution.",
    "PyPI JSON advisory coverage is not a code, malware, container or license approval scan.",
    "Inventory and observations have signed canonical semantic bindings; raw report file hashes are recorded in this unsigned run receipt.",
]
MAX_WHEEL_BYTES = 64 * 1024 * 1024


class ProvenanceCLIError(RuntimeError):
    pass


def _relative(root, path):
    path = Path(path)
    if ".." in path.parts:
        raise ProvenanceCLIError("Input traversal is refused")
    absolute = path.absolute() if path.is_absolute() else root / path
    try:
        relative = absolute.relative_to(root).as_posix()
    except ValueError:
        raise ProvenanceCLIError("Inputs must remain beneath the current repository") from None
    BASELINE._relative(relative)
    return relative


def _read(root, path, *, maximum=MAX_DOCUMENT_BYTES):
    relative = _relative(root, path)
    checked = BASELINE._checked_path(root, relative)
    info = checked.lstat()
    if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= maximum:
        raise ProvenanceCLIError("Input must be a bounded nonempty regular file")
    content = _read_bounded_file(checked, info.st_size)
    BASELINE._checked_path(root, relative)
    if not 0 < len(content) <= maximum:
        raise ProvenanceCLIError("Input exceeded its byte bound")
    return content


def _write(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")


def _runtime_target(target):
    expected_os = "win_amd64" if sys.platform == "win32" else "manylinux_2_28_x86_64"
    if (sys.platform not in {"win32", "linux"} or platform.machine().lower() not in {"amd64", "x86_64"}
            or platform.python_implementation().lower() != target["implementation"]
            or platform.python_version() != target["python_full_version"]
            or target["platform"] != expected_os):
        raise ProvenanceCLIError("Dependency target differs from this local builder runtime")
    if sys.platform == "linux":
        library, version = platform.libc_ver()
        try:
            parts = tuple(int(part) for part in version.split(".")[:2])
        except ValueError:
            parts = ()
        if library != "glibc" or len(parts) != 2 or parts < (2, 28):
            raise ProvenanceCLIError("Linux fixture target requires observed glibc 2.28 or newer")


def run_provenance(root, *, build_baseline, test_receipt, supply_chain, manifest, policy, output, now=None):
    root = Path(root).absolute()
    output = BASELINE.prepare_output(root, output)
    result = {"schema": "mra-local-build-provenance-run/v1", "status": "failed",
              "fixture_verified": False, "fixture_checks_passed": False, "expected_license_block": False,
              "source_verified": False, "errors": [], "inputs": {}, "limitations": LIMITATIONS, **FLAGS}
    source = None
    try:
        paths = {
            "source_manifest": Path(build_baseline) / "source-manifest.json",
            "build_result": Path(build_baseline) / "results.json",
            "test_receipt": Path(test_receipt),
            "inventory_report": Path(supply_chain) / "inventory.json",
            "sbom": Path(supply_chain) / "sbom.cdx.json",
            "observations_file": Path(supply_chain) / "observations.json",
            "advisory_report": Path(supply_chain) / "advisories.json",
            "dependency_manifest": Path(manifest), "policy": Path(policy),
        }
        bodies, parsed = {}, {}
        for label, path in paths.items():
            maximum = MAX_OBSERVATION_BYTES if label == "observations_file" else MAX_DOCUMENT_BYTES
            bodies[label] = _read(root, path, maximum=maximum)
            parsed[label] = strict_json_bytes(bodies[label], maximum=maximum)
            result["inputs"][label] = {"path": _relative(root, path), "sha256": hashlib.sha256(bodies[label]).hexdigest()}
        source = parsed["source_manifest"]
        BASELINE.verify_source(root, source)
        dependency_manifest = validate_manifest(parsed["dependency_manifest"])
        _runtime_target(dependency_manifest["target"])
        inventory = sorted(dependency_manifest["artifacts"], key=lambda item: item["name"])
        report = parsed["inventory_report"]
        if (type(report) is not dict or report.get("schema") != "mra-wheel-verification/v1"
                or report.get("status") != "verified" or report.get("environment") != "public_fixture"
                or report.get("production_approved") is not False or report.get("license_approved") is not False
                or report.get("target") != dependency_manifest["target"]
                or report.get("manifest_sha256") != canonical_sha256(dependency_manifest)
                or report.get("inventory_sha256") != canonical_sha256(inventory)):
            raise ProvenanceCLIError("Supply-chain report does not match the selected manifest")
        components = report.get("components")
        if type(components) is not list or len(components) != len(inventory):
            raise ProvenanceCLIError("Supply-chain inventory is incomplete")
        projected = [{key: item[key] for key in ("name", "version", "filename", "sha256", "size_bytes")}
                     for item in components]
        if sorted(projected, key=lambda item: item["name"]) != inventory:
            raise ProvenanceCLIError("Supply-chain inventory differs from exact artifacts")
        if parsed["sbom"] != build_cyclonedx_sbom(report):
            raise ProvenanceCLIError("SBOM differs from the supplied wheel report")
        build = parsed["build_result"]
        if type(build) is not dict or type(build.get("wheels")) is not list or len(build["wheels"]) != 2:
            raise ProvenanceCLIError("Two local baseline wheels are required")
        subject = {key: build["wheels"][0][key] for key in ("filename", "sha256", "size_bytes")}
        wheel_name = subject["filename"]
        if (type(wheel_name) is not str or Path(wheel_name).name != wheel_name
                or any(char in wheel_name for char in "/\\:") or not wheel_name.endswith(".whl")):
            raise ProvenanceCLIError("Unsafe baseline wheel name")
        for label in ("a", "b"):
            path = Path(build_baseline) / ("wheels-" + label) / wheel_name
            content = _read(root, path, maximum=MAX_WHEEL_BYTES)
            if len(content) != subject["size_bytes"] or hashlib.sha256(content).hexdigest() != subject["sha256"]:
                raise ProvenanceCLIError("Actual baseline wheel bytes differ from subject")
            # Existing wheel inspector checks every package member against source,
            # as well as RECORD hashes, without extracting or executing the wheel.
            wheel_report = BASELINE.verify_wheel(BASELINE._checked_path(root, _relative(root, path)), source)
            if wheel_report != build["wheels"][0 if label == "a" else 1]:
                raise ProvenanceCLIError("Actual wheel verification differs from baseline")
            paths["wheel_" + label] = path
            bodies["wheel_" + label] = content
            result["inputs"]["wheel_" + label] = {"path": _relative(root, path), "sha256": hashlib.sha256(content).hexdigest()}
        issued_at = int(time.time()) if now is None else now
        if type(issued_at) is not int or issued_at < 0:
            raise ProvenanceCLIError("Invalid fixture clock")
        materials = {name + "_sha256": hashlib.sha256(bodies[name]).hexdigest() for name in (
            "source_manifest", "dependency_manifest", "sbom", "advisory_report", "policy",
            "test_receipt", "build_result")}
        materials["inventory_sha256"] = canonical_sha256(inventory)
        statement = {"schema": "mra-local-build-provenance/v1", "environment": "public_fixture",
                     "build_id": "local-" + uuid.uuid4().hex, "builder_id": "mra-local-fixture-builder",
                     "platform": dependency_manifest["target"]["platform"],
                     "builder_versions": build["builder_versions"], "issued_at": issued_at,
                     "expires_at": issued_at + 3600, "subject": subject, "materials": materials}
        expected = {key: value for key, value in statement.items() if key not in {"issued_at", "expires_at"}}
        key = Ed25519PrivateKey.generate()
        envelope = sign_fixture_provenance(statement, key)
        public_key = key.public_key()
        # The fixture's current trust decision is explicit. No agency trust or
        # revocation service is inferred from this freshly generated local key.
        for label, path in paths.items():
            maximum = MAX_WHEEL_BYTES if label.startswith("wheel_") else (
                MAX_OBSERVATION_BYTES if label == "observations_file" else MAX_DOCUMENT_BYTES)
            if _read(root, path, maximum=maximum) != bodies[label]:
                raise ProvenanceCLIError("Input bytes changed during provenance verification")
        BASELINE.verify_source(root, source)
        result["source_verified"] = True
        admission = evaluate_admission(envelope, public_key, expected=expected, now=(int(time.time()) if now is None else now),
            signer_active=True, inventory=inventory, observations=parsed["observations_file"],
            advisory_report_bytes=bodies["advisory_report"], policy_bytes=bodies["policy"],
            test_receipt_bytes=bodies["test_receipt"], build_result_bytes=bodies["build_result"],
            source_manifest_bytes=bodies["source_manifest"])
        _write(output / "envelope.json", envelope)
        _write(output / "expected-context.json", expected)
        _write(output / "public-key.json", {"schema": "mra-local-build-public-key/v1",
            "algorithm": "Ed25519", "key_id": envelope["key_id"],
            "public_key_base64": base64.b64encode(public_key.public_bytes(
                serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode("ascii"),
            "trust": "self-generated-local-fixture-not-agency-trust", **FLAGS})
        _write(output / "admission.json", admission)
        result.update(fixture_verified=admission["fixture_verified"],
                      fixture_checks_passed=admission["fixture_checks_passed"],
                      admission_reasons=admission["reasons"])
        result["expected_license_block"] = (admission["fixture_verified"]
            and not admission["fixture_checks_passed"] and admission["reasons"] == ["license_review_pending"])
        if admission["fixture_verified"] and (admission["fixture_checks_passed"] or result["expected_license_block"]):
            result["status"] = "passed"
    except Exception as error:
        result["errors"].append(type(error).__name__ + ": local fixture provenance checks failed")
    finally:
        if source is not None:
            try:
                BASELINE.verify_source(root, source)
            except Exception:
                result["source_verified"] = False
                result["status"] = "failed"
                result["errors"].append("Source changed or could not be verified at completion")
        _write(output / "result.json", result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-baseline", type=Path, required=True)
    parser.add_argument("--test-receipt", type=Path, required=True)
    parser.add_argument("--supply-chain", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--policy", type=Path, default=Path("deploy/build/policy.json"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = run_provenance(ROOT, **vars(args))
    except (ProvenanceCLIError, BASELINE.BaselineError, OSError) as error:
        parser.exit(2, str(error) + "\n")
    print(json.dumps({key: result[key] for key in ("status", "fixture_verified", "fixture_checks_passed",
          "expected_license_block", "source_verified", "production_authorized", "deployable", "errors")}, indent=2))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())




