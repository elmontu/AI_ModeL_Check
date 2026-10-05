"""Public fixture CLI lifecycle, actual tiny Git snapshots and inert wheel checks."""
from __future__ import annotations

import base64
from copy import deepcopy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from model_release_assurance.production_build.artifacts import build_cyclonedx_sbom
from model_release_assurance.production_build.evidence import (
    canonical_bytes, canonical_sha256, evaluate_advisories, parse_pypi_observation,
    verify_fixture_provenance,
)
from test_build_baseline import make_wheel
from test_production_build_evidence import receipt

SPEC = importlib.util.spec_from_file_location("verify_build_provenance",
    Path(__file__).resolve().parents[1] / "scripts/verify_build_provenance.py")
CLI = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CLI)


class ProvenanceCLITests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="mra-provenance-tests-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.git("init", "-q")
        self.write(".gitignore", b".local/\n")
        self.write("src/model_release_assurance/fixture.py", b"PUBLIC = True\n")
        self.write("tests/test_fixture.py", b"# A synthetic receipt fixture, no executed claim.\n")
        self.artifact = {"name": "builder", "version": "1.0", "filename": "builder-1.0-py3-none-any.whl",
                         "sha256": "1" * 64, "size_bytes": 100}
        self.manifest = {"schema": "mra-wheel-lock/v1", "environment": "public_fixture",
                         "target": {"python_version": "3.12", "python_full_version": "3.12.14",
                                    "implementation": "cpython", "platform": "win_amd64"},
                         "roots": ["builder==1.0"], "artifacts": [self.artifact]}
        self.write_json("deploy/build/manifest.json", self.manifest)
        self.policy = {"schema": "mra-local-build-policy/v1", "environment": "public_fixture",
                       "advisory_max_age_seconds": 86400, "license_review": "pending",
                       "required_test_profile": "government", "require_zero_skips": True}
        self.write_json("deploy/build/policy.json", self.policy)
        self.git("add", "--all")
        self.git("-c", "user.name=Public Fixture", "-c", "user.email=fixture@example.invalid",
                 "commit", "-q", "-m", "Synthetic provenance fixture")
        self.source = CLI.BASELINE.capture_source(self.root)
        self.source_path = self.write_json(".local/build/source-manifest.json", self.source)
        self.tests = receipt()
        self.tests["source_hashes"] = [{"path": item["path"], "sha256": item["sha256"]} for item in self.source["files"]]
        self.write_json(".local/tests/result.json", self.tests)
        wheel_reports = []
        for label in ("a", "b"):
            path = self.root / ".local/build" / ("wheels-" + label) / "model_release_assurance-0.0.0-py3-none-any.whl"
            path.parent.mkdir(parents=True)
            make_wheel(path, {"model_release_assurance/fixture.py": b"PUBLIC = True\n"})
            wheel_reports.append(CLI.BASELINE.verify_wheel(path, self.source))
        self.build = {"schema": "local-build-baseline/v1", "status": "passed", "errors": [],
                      "source_stable_at_end": True,
                      "source_manifest_sha256": hashlib.sha256(self.source_path.read_bytes()).hexdigest(),
                      "builder_versions": {"builder": "1.0"}, "wheels": wheel_reports}
        self.write_json(".local/build/results.json", self.build)
        component = {**self.artifact, "purl": "pkg:pypi/builder@1.0", "license_expression": None,
                     "declared_license": None, "license_status": "unknown", "license_files": []}
        self.inventory_report = {"schema": "mra-wheel-verification/v1", "status": "verified",
            "environment": "public_fixture", "production_approved": False, "license_approved": False,
            "target": self.manifest["target"], "manifest_sha256": canonical_sha256(self.manifest),
            "inventory_sha256": canonical_sha256(self.manifest["artifacts"]),
            "components": [component], "dependency_graph": {"builder": []}}
        self.write_json(".local/supply/inventory.json", self.inventory_report)
        self.write_json(".local/supply/sbom.cdx.json", build_cyclonedx_sbom(self.inventory_report))
        self.observations = [parse_pypi_observation("builder", "1.0",
            canonical_bytes({"info": {"name": "builder", "version": "1.0"}, "vulnerabilities": []}),
            fetched_at=1000)]
        self.write_json(".local/supply/observations.json", self.observations)
        self.write_json(".local/supply/advisories.json",
                        evaluate_advisories(self.manifest["artifacts"], self.observations, now=1000))

    def git(self, *args):
        completed = subprocess.run(["git", "-C", str(self.root), *args], capture_output=True, check=False)
        self.assertEqual(0, completed.returncode, completed.stderr.decode(errors="replace"))
        return completed.stdout

    def write(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def write_json(self, name, value):
        return self.write(name, canonical_bytes(value))

    def run_fixture(self, **changes):
        args = dict(build_baseline=Path(".local/build"), test_receipt=Path(".local/tests/result.json"),
                    supply_chain=Path(".local/supply"), manifest=Path("deploy/build/manifest.json"),
                    policy=Path("deploy/build/policy.json"), output=Path(".local/provenance"), now=1001)
        args.update(changes)
        # Tiny synthetic wheel/report fixtures are portable; the real CLI's
        # platform/version restriction is separately tested below.
        with patch.object(CLI, "_runtime_target"):
            return CLI.run_provenance(self.root, **args)

    def test_pending_license_retains_verified_fixture_and_never_deploys(self):
        result = self.run_fixture()
        self.assertEqual("passed", result["status"], result["errors"])
        self.assertTrue(result["fixture_verified"])
        self.assertTrue(result["source_verified"])
        self.assertFalse(result["fixture_checks_passed"])
        self.assertTrue(result["expected_license_block"])
        self.assertFalse(result["production_authorized"])
        self.assertFalse(result["deployable"])
        output = self.root / ".local/provenance"
        self.assertEqual({"envelope.json", "expected-context.json", "public-key.json", "admission.json", "result.json"},
                         {path.name for path in output.iterdir()})
        envelope = json.loads((output / "envelope.json").read_bytes())
        expected = json.loads((output / "expected-context.json").read_bytes())
        public = json.loads((output / "public-key.json").read_bytes())
        verified = verify_fixture_provenance(envelope,
            Ed25519PublicKey.from_public_bytes(base64.b64decode(public["public_key_base64"])),
            expected=expected, now=1002, signer_active=True)
        self.assertTrue(verified["fixture_verified"])
        self.assertEqual("self-generated-local-fixture-not-agency-trust", public["trust"])

    def test_existing_output_refused_and_existing_bytes_preserved(self):
        self.run_fixture()
        before = (self.root / ".local/provenance/result.json").read_bytes()
        with self.assertRaises(CLI.BASELINE.BaselineError):
            self.run_fixture()
        self.assertEqual(before, (self.root / ".local/provenance/result.json").read_bytes())

    def test_current_source_drift_fails_before_signing_and_retains_failed_receipt(self):
        self.write("src/model_release_assurance/fixture.py", b"PUBLIC = False\n")
        result = self.run_fixture()
        self.assertEqual("failed", result["status"])
        self.assertFalse(result["source_verified"])
        self.assertFalse((self.root / ".local/provenance/envelope.json").exists())
        self.assertTrue((self.root / ".local/provenance/result.json").is_file())

    def test_old_source_test_receipt_is_not_accepted_with_new_baseline(self):
        self.tests["source_hashes"][0]["sha256"] = "f" * 64
        self.write_json(".local/tests/result.json", self.tests)
        result = self.run_fixture()
        self.assertEqual("failed", result["status"])
        self.assertTrue(result["fixture_verified"])
        self.assertFalse(result["fixture_checks_passed"])
        self.assertFalse(result["expected_license_block"])

    def test_actual_wheel_drift_and_second_repeat_drift_fail(self):
        for label in ("a", "b"):
            with self.subTest(label=label):
                path = self.root / ".local/build" / ("wheels-" + label) / self.build["wheels"][0]["filename"]
                original = path.read_bytes()
                path.write_bytes(original + b"tampered")
                result = self.run_fixture(output=Path(".local/result-" + label))
                self.assertEqual("failed", result["status"])
                self.assertFalse(result["fixture_verified"])
                path.write_bytes(original)

    def test_failed_or_skipped_receipt_is_not_expected_license_only_failure(self):
        self.tests["counts"]["skipped"] = 1
        self.write_json(".local/tests/result.json", self.tests)
        result = self.run_fixture()
        self.assertEqual("failed", result["status"])
        self.assertFalse(result["expected_license_block"])
        self.assertIn("material_evidence_not_verified", result["admission_reasons"])

    def test_incomplete_or_conflicting_inventory_and_sbom_fail(self):
        self.inventory_report["components"][0]["sha256"] = "f" * 64
        self.write_json(".local/supply/inventory.json", self.inventory_report)
        self.assertEqual("failed", self.run_fixture()["status"])
        self.write_json(".local/supply/inventory.json", {**self.inventory_report, "components": [
            {**self.inventory_report["components"][0], "sha256": self.artifact["sha256"]}]})
        self.write_json(".local/supply/sbom.cdx.json", {"status": "unavailable"})
        self.assertEqual("failed", self.run_fixture(output=Path(".local/other"))["status"])

    def test_missing_advisory_observation_blocks_even_when_license_pending(self):
        self.write_json(".local/supply/observations.json", [])
        self.write_json(".local/supply/advisories.json", evaluate_advisories(
            self.manifest["artifacts"], [], now=1000))
        result = self.run_fixture()
        self.assertEqual("failed", result["status"])
        self.assertIn("missing_component_observation", result["admission_reasons"])
        self.assertFalse(result["expected_license_block"])

    def test_outside_repository_traversal_and_nonregular_inputs_refused(self):
        for value in (Path("../outside"), self.root.parent / "outside", Path(".local/supply")):
            with self.subTest(path=value):
                result = self.run_fixture(test_receipt=value,
                    output=Path(".local/path-" + str(len(list((self.root / ".local").iterdir())))))
                self.assertEqual("failed", result["status"])
                self.assertFalse(result["fixture_verified"])

    def test_input_mutation_during_signature_operation_fails(self):
        real_sign = CLI.sign_fixture_provenance

        def sign_and_mutate(*args, **kwargs):
            envelope = real_sign(*args, **kwargs)
            path = self.root / ".local/tests/result.json"
            path.write_bytes(path.read_bytes() + b"\n")
            return envelope

        with patch.object(CLI, "sign_fixture_provenance", side_effect=sign_and_mutate):
            result = self.run_fixture()
        self.assertEqual("failed", result["status"])
        self.assertFalse((self.root / ".local/provenance/envelope.json").exists())

    def test_linux_target_rejects_musl_old_or_unknown_glibc(self):
        target = {**self.manifest["target"], "platform": "manylinux_2_28_x86_64"}
        with patch.object(CLI.sys, "platform", "linux"), \
                patch.object(CLI.platform, "machine", return_value="x86_64"), \
                patch.object(CLI.platform, "python_implementation", return_value="CPython"), \
                patch.object(CLI.platform, "python_version", return_value="3.12.14"):
            for observed in (("musl", "1.2.5"), ("glibc", "2.27"), ("", ""), ("glibc", "unknown")):
                with patch.object(CLI.platform, "libc_ver", return_value=observed):
                    with self.assertRaises(CLI.ProvenanceCLIError):
                        CLI._runtime_target(target)
            with patch.object(CLI.platform, "libc_ver", return_value=("glibc", "2.28")):
                CLI._runtime_target(target)

    def test_bounded_reader_refuses_hardlink_alias_and_reads_exact_size(self):
        original = self.write(".local/regular.json", b"{}")
        alias = self.root / ".local/alias.json"
        os.link(original, alias)
        with self.assertRaises(ValueError):
            CLI._read(self.root, alias)
        regular = self.write(".local/single.json", b"{}")
        with patch.object(CLI, "_read_bounded_file", wraps=CLI._read_bounded_file) as checked:
            self.assertEqual(b"{}", CLI._read(self.root, regular))
        checked.assert_called_once_with(regular, 2)

    def test_runtime_target_and_oversized_input_refused(self):
        with patch.object(CLI.platform, "python_version", return_value="3.11.0"):
            with self.assertRaises(CLI.ProvenanceCLIError):
                CLI._runtime_target(self.manifest["target"])
        path = self.write(".local/large.json", b"123456789")
        with self.assertRaises(CLI.ProvenanceCLIError):
            CLI._read(self.root, path, maximum=8)


if __name__ == "__main__":
    unittest.main()



