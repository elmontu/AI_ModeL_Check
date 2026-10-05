"""Adversarial checks for bounded local build evidence; no network or key files."""
from __future__ import annotations

import base64
from copy import deepcopy
import hashlib
import json
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from model_release_assurance.production_build.evidence import (
    BuildEvidenceError, MAX_AGE_SECONDS, MAX_RESPONSE_BYTES, canonical_bytes,
    canonical_sha256, evaluate_admission, evaluate_advisories, parse_pypi_observation,
    sign_fixture_provenance, strict_json_bytes, verify_fixture_provenance,
)


def artifact(name="runtime", version="1.0"):
    return {"name": name, "version": version, "filename": name + "-" + version + "-py3-none-any.whl",
            "sha256": "1" * 64, "size_bytes": 100}


def observation(name="runtime", version="1.0", *, time=1000, vulnerabilities=None):
    body = {"info": {"name": name, "version": version, "summary": "fictional public fixture"},
            "vulnerabilities": [] if vulnerabilities is None else vulnerabilities}
    return parse_pypi_observation(name, version, canonical_bytes(body), fetched_at=time)


def receipt():
    ids = ["test_fixture.TestFixture.test_public_one"]
    return {"schema": "required-test-profile/v1", "profile": "government", "status": "passed",
            "counts": {"selected": 1, "run": 1, "skipped": 0, "failures": 0, "errors": 0,
                       "expected_failures": 0, "unexpected_successes": 0},
            "discovery_problems": [], "skips": [], "failures": [], "errors": [],
            "expected_failures": [], "unexpected_successes": [], "missing_dependency_reasons": [],
            "duplicate_test_ids": [], "selected_test_ids": ids,
            "selected_modules": [{"path": "tests/test_fixture.py", "test_count": 1, "test_ids": ids}],
            "source_ownership": [{"module": "model_release_assurance.fixture", "from_current_source": True}],
            "source_hashes": [{"path": "src/model_release_assurance/fixture.py", "sha256": "4" * 64},
                              {"path": "tests/test_fixture.py", "sha256": "5" * 64}]}


class AdvisoryTests(unittest.TestCase):
    def setUp(self):
        self.inventory = [artifact("builder"), artifact()]
        self.observations = [observation("builder"), observation()]

    def evaluate(self, **kwargs):
        return evaluate_advisories(kwargs.get("inventory", self.inventory),
                                   kwargs.get("observations", self.observations),
                                   now=kwargs.get("now", 1000))

    def test_complete_inventory_with_builder_is_clear_only_for_listed_advisories(self):
        result = self.evaluate()
        self.assertTrue(result["advisory_clear"])
        self.assertTrue(result["coverage_complete"])
        self.assertEqual(2, result["checked_components"])
        self.assertEqual(canonical_sha256(self.inventory), result["inventory_sha256"])
        self.assertEqual("listed-wheel-distributions-only", result["scope"])
        self.assertIs(result["production_authorized"], False)
        self.assertIs(result["deployable"], False)

    def test_missing_builder_and_duplicate_cannot_count_as_coverage(self):
        for observations in ([observation()], [observation(), observation()]):
            with self.subTest(observations=len(observations)):
                result = self.evaluate(observations=observations)
                self.assertFalse(result["coverage_complete"])
                self.assertFalse(result["advisory_clear"])
                self.assertIn("missing_component_observation", result["reasons"])

    def test_wrong_version_or_extra_component_block(self):
        for item in (observation("builder", "2.0"), observation("other")):
            with self.subTest(name=item["name"]):
                result = self.evaluate(observations=[observation(), item])
                self.assertIn("unexpected_component_or_version", result["reasons"])
                self.assertFalse(result["advisory_clear"])

    def test_error_and_unknown_skipped_status_do_not_clear(self):
        error = {"name": "builder", "version": "1.0", "fetched_at": 1000,
                 "source": "pypi-json", "status": "error", "error": "fetch_failed"}
        result = self.evaluate(observations=[observation(), error])
        self.assertIn("observation_error", result["reasons"])
        error["status"] = "skipped"
        with self.assertRaises(BuildEvidenceError):
            self.evaluate(observations=[observation(), error])

    def test_freshness_boundaries_and_future_timestamps(self):
        self.assertTrue(self.evaluate(now=1000 + MAX_AGE_SECONDS)["advisory_clear"])
        for now in (999, 1001 + MAX_AGE_SECONDS):
            with self.subTest(now=now):
                self.assertFalse(self.evaluate(now=now)["advisory_clear"])
        for now in (True, -1, 1.5):
            with self.assertRaises(BuildEvidenceError):
                self.evaluate(now=now)

    def test_reported_even_withdrawn_vulnerability_blocks(self):
        self.observations[0] = observation("builder", vulnerabilities=[
            {"id": "PYSEC-FIXTURE-1", "withdrawn": "2020-01-01", "aliases": []}])
        result = self.evaluate()
        self.assertTrue(result["coverage_complete"])
        self.assertFalse(result["advisory_clear"])
        self.assertEqual("PYSEC-FIXTURE-1", result["findings"][0]["advisory_id"])

    def test_raw_body_hash_and_summary_are_independently_revalidated(self):
        changes = [
            lambda item: item.update(response_sha256="f" * 64),
            lambda item: item.update(vulnerabilities=[{"id": "invented"}]),
            lambda item: item.update(response_body_base64=base64.b64encode(b"{}").decode()),
            lambda item: item.update(version="2.0"),
            lambda item: item.update(source="pip-audit"),
            lambda item: item.update(unknown=True),
        ]
        for change in changes:
            items = deepcopy(self.observations)
            change(items[0])
            with self.assertRaises(BuildEvidenceError):
                self.evaluate(observations=items)

    def test_raw_parser_requires_exact_name_version_and_explicit_findings_list(self):
        for body in (
            {"info": {"name": "other", "version": "1.0"}, "vulnerabilities": []},
            {"info": {"name": "runtime", "version": "1.0.0"}, "vulnerabilities": []},
            {"info": {"name": "runtime", "version": "1.0"}},
            {"info": {"name": "runtime", "version": "1.0"}, "vulnerabilities": None},
            {"info": {"name": "runtime", "version": "1.0"}, "vulnerabilities": [{}]},
        ):
            with self.assertRaises(BuildEvidenceError):
                parse_pypi_observation("runtime", "1.0", canonical_bytes(body), fetched_at=1000)
        normalized = {"info": {"name": "My_Package", "version": "1.0"}, "vulnerabilities": []}
        self.assertEqual("my-package", parse_pypi_observation(
            "my-package", "1.0", canonical_bytes(normalized), fetched_at=1000)["name"])

    def test_json_duplicate_nonfinite_depth_and_oversize_rejected(self):
        for content in (b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}',
                        b"[" * 100 + b"0" + b"]" * 100, b"\xff"):
            with self.assertRaises(BuildEvidenceError):
                strict_json_bytes(content)
        with self.assertRaises(BuildEvidenceError):
            parse_pypi_observation("runtime", "1.0", b" " * (MAX_RESPONSE_BYTES + 1), fetched_at=1000)

    def test_inventory_strictness_no_empty_duplicate_or_unknown_metadata(self):
        for inventory in ([], [artifact(), artifact()],
                          [{**artifact(), "license": "approved"}],
                          [{**artifact(), "name": "Runtime"}],
                          [{**artifact(), "size_bytes": True}],
                          [{**artifact(), "filename": "../runtime.whl"}]):
            with self.assertRaises(BuildEvidenceError):
                self.evaluate(inventory=inventory)


class ProvenanceAdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = Ed25519PrivateKey.generate()
        cls.other_key = Ed25519PrivateKey.generate()

    def setUp(self):
        self.inventory = [artifact("builder"), artifact()]
        self.observations = [observation("builder"), observation()]
        self.policy = {"schema": "mra-local-build-policy/v1", "environment": "public_fixture",
                       "advisory_max_age_seconds": 86400, "license_review": "approved",
                       "required_test_profile": "government", "require_zero_skips": True}
        self.tests = receipt()
        self.source = {"schema": "local-build-source/v1", "files": [
            {**item, "size_bytes": 10} for item in self.tests["source_hashes"]]}
        self.statement = {"schema": "mra-local-build-provenance/v1", "environment": "public_fixture",
                          "build_id": "public-build-1", "builder_id": "local-test-builder",
                          "platform": "win_amd64", "builder_versions": {"builder": "1.0"},
                          "issued_at": 1000, "expires_at": 1300,
                          "subject": {"filename": "fixture-1-py3-none-any.whl", "sha256": "a" * 64, "size_bytes": 10},
                          "materials": {key: "b" * 64 for key in (
                              "source_manifest_sha256", "dependency_manifest_sha256", "inventory_sha256",
                              "sbom_sha256", "advisory_report_sha256", "policy_sha256",
                              "test_receipt_sha256", "build_result_sha256")}}
        wheel = {**self.statement["subject"], "verified_package_files": 1, "verified_record_entries": 4}
        self.build = {"schema": "local-build-baseline/v1", "status": "passed", "errors": [],
                      "source_stable_at_end": True, "source_manifest_sha256": canonical_sha256(self.source),
                      "builder_versions": {"builder": "1.0"}, "wheels": [deepcopy(wheel), deepcopy(wheel)]}
        self.reseal()

    def reseal(self, *, advisory=None):
        self.advisory_report_bytes = canonical_bytes(advisory or evaluate_advisories(
            self.inventory, self.observations, now=1000))
        self.source_manifest_bytes = canonical_bytes(self.source)
        self.statement["materials"]["source_manifest_sha256"] = hashlib.sha256(self.source_manifest_bytes).hexdigest()
        self.policy_bytes = canonical_bytes(self.policy)
        self.test_receipt_bytes = canonical_bytes(self.tests)
        self.build_result_bytes = canonical_bytes(self.build)
        self.statement["materials"]["inventory_sha256"] = canonical_sha256(sorted(self.inventory, key=lambda item: item["name"]))
        for name in ("advisory_report", "policy", "test_receipt", "build_result"):
            self.statement["materials"][name + "_sha256"] = hashlib.sha256(getattr(self, name + "_bytes")).hexdigest()
        self.envelope = sign_fixture_provenance(self.statement, self.key)
        self.expected = {key: deepcopy(value) for key, value in self.statement.items() if key not in {"issued_at", "expires_at"}}

    def verify(self, **kwargs):
        return verify_fixture_provenance(kwargs.get("envelope", self.envelope),
            kwargs.get("key", self.key.public_key()), expected=kwargs.get("expected", self.expected),
            now=kwargs.get("now", 1001), signer_active=kwargs.get("signer_active", True))

    def admit(self, **kwargs):
        inputs = dict(expected=self.expected, now=1001, signer_active=True, inventory=self.inventory,
                      observations=self.observations, advisory_report_bytes=self.advisory_report_bytes,
                      policy_bytes=self.policy_bytes, test_receipt_bytes=self.test_receipt_bytes,
                      build_result_bytes=self.build_result_bytes, source_manifest_bytes=self.source_manifest_bytes)
        inputs.update(kwargs)
        return evaluate_admission(self.envelope, self.key.public_key(), **inputs)

    def test_pinned_signature_and_actual_semantics_can_pass_fixture_only(self):
        result = self.admit()
        self.assertTrue(result["fixture_checks_passed"], result["reasons"])
        self.assertTrue(result["fixture_verified"])
        self.assertFalse(result["production_authorized"])
        self.assertFalse(result["deployable"])
        self.assertTrue(result["required_production_controls"])
        raw = self.key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        self.assertTrue(self.verify(key=raw)["fixture_verified"])

    def test_wrong_key_inactive_unknown_trust_and_wrong_context_rejected(self):
        for options in ({"key": self.other_key.public_key()}, {"signer_active": False},
                        {"signer_active": 1}, {"signer_active": None}):
            self.assertFalse(self.verify(**options)["fixture_verified"])
        for field, value in (("build_id", "other-build"), ("builder_id", "other-builder"),
                             ("platform", "manylinux_2_28_x86_64"), ("environment", "production")):
            expected = deepcopy(self.expected)
            expected[field] = value
            self.assertFalse(self.verify(expected=expected)["fixture_verified"])
        for location in ("source_manifest_sha256", "inventory_sha256", "sbom_sha256", "policy_sha256"):
            expected = deepcopy(self.expected)
            expected["materials"][location] = "c" * 64
            self.assertFalse(self.verify(expected=expected)["fixture_verified"])

    def test_signature_tampering_unknown_fields_and_noncanonical_encoding(self):
        mutations = [
            lambda item: item.update(extra=True),
            lambda item: item.update(algorithm="RS256"),
            lambda item: item.update(key_id="f" * 64),
            lambda item: item.update(signature_base64url=item["signature_base64url"] + "="),
            lambda item: item.update(signature_base64url="A" * 86),
            lambda item: item["statement"]["subject"].update(sha256="f" * 64),
            lambda item: item["statement"].update(extra=True),
        ]
        for mutation in mutations:
            value = deepcopy(self.envelope)
            mutation(value)
            self.assertFalse(self.verify(envelope=value)["fixture_verified"])

    def test_domain_separation_rejects_signature_of_plain_statement(self):
        changed = deepcopy(self.envelope)
        changed["signature_base64url"] = base64.urlsafe_b64encode(
            self.key.sign(canonical_bytes(changed["statement"]))).decode().rstrip("=")
        self.assertFalse(self.verify(envelope=changed)["fixture_verified"])

    def test_future_expired_replay_and_lifetime_bounds(self):
        self.assertTrue(self.verify(now=1000)["fixture_verified"])
        self.assertTrue(self.verify(now=1299)["fixture_verified"])
        for now in (999, 1300, 1400, True):
            self.assertFalse(self.verify(now=now)["fixture_verified"])
        for expires in (1000, 999, 1001 + MAX_AGE_SECONDS):
            changed = deepcopy(self.statement)
            changed["expires_at"] = expires
            with self.assertRaises(BuildEvidenceError):
                sign_fixture_provenance(changed, self.key)

    def test_signer_owns_copy_and_rejects_bad_builder_versions_and_keys(self):
        envelope = sign_fixture_provenance(self.statement, self.key)
        self.statement["subject"]["sha256"] = "e" * 64
        self.assertEqual("a" * 64, envelope["statement"]["subject"]["sha256"])
        for versions in ({}, {"builder": True}, {"builder": "not a version"}):
            changed = deepcopy(self.statement)
            changed["builder_versions"] = versions
            with self.assertRaises(BuildEvidenceError):
                sign_fixture_provenance(changed, self.key)
        with self.assertRaises(BuildEvidenceError):
            sign_fixture_provenance(self.statement, b"private-key-is-not-imported")

    def test_actual_body_hashes_not_just_declared_digest(self):
        for field in ("policy_bytes", "test_receipt_bytes", "build_result_bytes", "advisory_report_bytes", "source_manifest_bytes"):
            result = self.admit(**{field: getattr(self, field) + b"\n"})
            self.assertFalse(result["fixture_checks_passed"])
            self.assertIn("material_evidence_not_verified", result["reasons"])

    def test_advisory_summary_cannot_claim_clean_without_matching_saved_observations(self):
        report = evaluate_advisories(self.inventory, self.observations, now=1000)
        report["checked_components"] = 99
        self.reseal(advisory=report)
        self.assertFalse(self.admit()["fixture_checks_passed"])
        self.setUp()
        self.observations[0] = observation("builder", vulnerabilities=[{"id": "GHSA-FIXTURE-1"}])
        self.reseal()
        result = self.admit()
        self.assertFalse(result["fixture_checks_passed"])
        self.assertIn("reported_vulnerabilities", result["reasons"])

    def test_missing_builder_observation_error_and_stale_reports_block_even_signed(self):
        self.observations.pop(0)
        self.reseal()
        self.assertIn("missing_component_observation", self.admit()["reasons"])
        self.setUp()
        self.statement["issued_at"] = 1000 + MAX_AGE_SECONDS
        self.statement["expires_at"] = 1300 + MAX_AGE_SECONDS
        self.reseal()
        self.assertFalse(self.admit(now=1001 + MAX_AGE_SECONDS)["fixture_checks_passed"])

    def test_declared_builder_must_exist_in_exact_scanned_inventory(self):
        self.inventory = [artifact()]
        self.observations = [observation()]
        self.reseal()
        self.assertFalse(self.admit()["fixture_checks_passed"])
        self.setUp()
        self.inventory[0]["version"] = "2.0"
        self.observations[0] = observation("builder", "2.0")
        self.reseal()
        self.assertFalse(self.admit()["fixture_checks_passed"])

    def test_license_pending_is_not_cleared_by_valid_signature(self):
        self.policy["license_review"] = "pending"
        self.reseal()
        result = self.admit()
        self.assertTrue(result["fixture_verified"])
        self.assertFalse(result["fixture_checks_passed"])
        self.assertIn("license_review_pending", result["reasons"])

    def test_bad_policy_shape_or_relaxed_skip_rule_rejected(self):
        for field, value in (("require_zero_skips", False), ("required_test_profile", "other"),
                             ("license_review", "not-required"), ("advisory_max_age_seconds", 86401),
                             ("extra", True)):
            self.setUp()
            self.policy[field] = value
            self.reseal()
            self.assertFalse(self.admit()["fixture_checks_passed"])

    def test_signed_passed_receipt_with_failure_skip_empty_counts_or_bad_ownership_denied(self):
        mutations = [
            lambda value: value.update(status="failed"),
            lambda value: value["counts"].update(selected=0, run=0),
            lambda value: value["counts"].update(run=2),
            lambda value: value["counts"].update(skipped=1),
            lambda value: value["counts"].update(errors=True),
            lambda value: value["failures"].append({"test_id": "failed"}),
            lambda value: value["discovery_problems"].append("missing suite"),
            lambda value: value["source_ownership"][0].update(from_current_source=False),
            lambda value: value.update(source_hashes=[]),
            lambda value: value.update(selected_modules=[]),
            lambda value: value["selected_modules"][0].update(test_count=2),
        ]
        for mutation in mutations:
            self.tests = receipt()
            mutation(self.tests)
            self.reseal()
            self.assertFalse(self.admit()["fixture_checks_passed"])

    def test_build_failure_source_drift_different_repeat_or_builder_versions_denied(self):
        original = deepcopy(self.build)
        mutations = [
            lambda value: value.update(status="failed"),
            lambda value: value.update(source_stable_at_end=False),
            lambda value: value["errors"].append("source drift"),
            lambda value: value["wheels"][1].update(sha256="f" * 64),
            lambda value: value.update(wheels=value["wheels"][:1]),
            lambda value: value.update(source_manifest_sha256="f" * 64),
            lambda value: value.update(builder_versions={"builder": "2.0"}),
            lambda value: value["wheels"][0].update(verified_package_files=0),
        ]
        for mutation in mutations:
            self.build = deepcopy(original)
            mutation(self.build)
            self.reseal()
            self.assertFalse(self.admit()["fixture_checks_passed"])

    def test_test_receipt_must_match_captured_shipped_and_selected_test_source(self):
        self.tests["source_hashes"][0]["sha256"] = "e" * 64
        self.reseal()
        self.assertFalse(self.admit()["fixture_checks_passed"])
        self.setUp()
        self.tests["source_hashes"].pop()
        self.reseal()
        self.assertFalse(self.admit()["fixture_checks_passed"])
        self.setUp()
        self.source["files"].append({"path": "src/model_release_assurance/new_source.py",
                                     "sha256": "f" * 64, "size_bytes": 10})
        self.build["source_manifest_sha256"] = canonical_sha256(self.source)
        self.reseal()
        self.assertFalse(self.admit()["fixture_checks_passed"])

    def test_unselected_test_helper_must_be_hashed_in_required_receipt(self):
        self.source["files"].append({"path": "tests/helpers/wheel_fixture.py",
                                     "sha256": "f" * 64, "size_bytes": 10})
        self.build["source_manifest_sha256"] = canonical_sha256(self.source)
        self.reseal()
        self.assertFalse(self.admit()["fixture_checks_passed"])
        self.tests["source_hashes"].append({"path": "tests/helpers/wheel_fixture.py", "sha256": "f" * 64})
        self.reseal()
        self.assertTrue(self.admit()["fixture_checks_passed"])

    def test_source_manifest_duplicate_path_or_missing_file_cannot_mask_test_drift(self):
        self.source["files"].pop()
        self.build["source_manifest_sha256"] = canonical_sha256(self.source)
        self.reseal()
        self.assertFalse(self.admit()["fixture_checks_passed"])
        self.setUp()
        self.source["files"].append(deepcopy(self.source["files"][0]))
        self.build["source_manifest_sha256"] = canonical_sha256(self.source)
        self.reseal()
        self.assertFalse(self.admit()["fixture_checks_passed"])

    def test_mutation_after_signature_verification_cannot_substitute_unsigned_materials(self):
        new_bytes = self.test_receipt_bytes + b"\n"
        replacement_hash = hashlib.sha256(new_bytes).hexdigest()
        original_verify = verify_fixture_provenance

        def verify_then_mutate(*args, **kwargs):
            result = original_verify(*args, **kwargs)
            self.envelope["statement"]["materials"]["test_receipt_sha256"] = replacement_hash
            return result

        with patch("model_release_assurance.production_build.evidence.verify_fixture_provenance",
                   side_effect=verify_then_mutate):
            result = self.admit(test_receipt_bytes=new_bytes)
        self.assertTrue(result["fixture_verified"])
        self.assertFalse(result["fixture_checks_passed"])
        self.assertIn("material_evidence_not_verified", result["reasons"])

    def test_inventory_mutation_or_duplicate_json_material_never_passes(self):
        changed = deepcopy(self.inventory)
        changed[0]["sha256"] = "f" * 64
        self.assertFalse(self.admit(inventory=changed)["fixture_checks_passed"])
        body = b'{"schema":"x","schema":"y"}'
        self.statement["materials"]["policy_sha256"] = hashlib.sha256(body).hexdigest()
        self.envelope = sign_fixture_provenance(self.statement, self.key)
        self.expected["materials"]["policy_sha256"] = self.statement["materials"]["policy_sha256"]
        self.assertFalse(self.admit(policy_bytes=body)["fixture_checks_passed"])


if __name__ == "__main__":
    unittest.main()





