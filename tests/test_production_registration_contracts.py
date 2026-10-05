"""Strict scientific scope and prospective registration-to-replay bindings."""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from model_release_assurance.production_registration import contracts as module
from model_release_assurance.production_registration.contracts import (
    RegistrationError, build_registration, canonical_bytes, digest, evaluate_native,
    strict_json, validate_registration, validate_review,
)
from model_release_assurance.production_registration.profiles import load_profile
from model_release_assurance.production_adapters import native
from model_release_assurance.production_adapters.contracts import canonical_bytes as native_bytes
from model_release_assurance.production_evidence.replay import snapshot_native_bundle
from model_release_assurance.production_evidence.verifier import runtime_observation


def registration_fixture(profile_id="sklearn-wine", history=None, registration_id="2" * 32):
    """Actual pinned public input and pre-fit registration, with no filesystem writes."""
    data = load_profile(profile_id, max_rows=128)
    x, y = native._arrays(data["x"], data["y"])
    raw = native_bytes({"schema_version": "mra-native-tabular-data/v1", "x": x.tolist(), "y": y.tolist(),
                        "feature_names": data["feature_names"], "task": data["task"]}) + b"\n"
    plan = native._plan(x, y, data["dataset_id"], data["source_sha256"], data["feature_names"],
                        data["task"], 20261001, hashlib.sha256(raw).hexdigest())
    plan_bytes = native_bytes(plan) + b"\n"
    if history is None:
        history = {"ledger_id": "1" * 32, "scope_id": digest({"agency_id": "agency", "project_id": "project"}),
                   "sequence": 0, "head_sha256": "0" * 64, "local_registrations": 0, "known_disclosures": 0,
                   "external_history": "unknown", "privacy_accounting_supported": False}
    registration = build_registration(registration_id=registration_id, agency_id="agency", project_id="project",
        case_id="case", profile_id=profile_id, data=data, data_bytes=raw, plan_bytes=plan_bytes,
        history=history, workflow_sha256="3" * 64, runtime_sha256=digest(runtime_observation()))
    return registration, data, raw, plan_bytes


def review_fixture(registration):
    """Typed STORE-UNIT-TEST payload only; does not claim actual execution evidence."""
    task = registration["source"]["task"]
    metrics = {"accuracy": .8, "majority_accuracy": .5} if task == "classification" else {"rmse": 1., "training_mean_baseline_rmse": 2.}
    return validate_review({"schema": "mra-native-registration-review/v1", "status": "production_blocked", "registration_sha256": digest(registration),
        "artifacts_sha256": "a" * 64, "candidate_sha256": "b" * 64, "report_sha256": "c" * 64,
        "profile_id": registration["profile_id"], "utility": module._utility_review(task, metrics),
        "permanent_block_reasons": list(module.BLOCK_REASONS),
        "evidence_scope": "numeric_replay_only_prospective_ordering_requires_workflow_ledger", **module.FLAGS})


class RegistrationContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parent = tempfile.TemporaryDirectory(prefix="registration-contract-")
        cls.root = Path(cls.parent.name)
        cls.inputs = {}
        cls.blobs = {}
        for profile in ("sklearn-wine", "sklearn-diabetes"):
            prepared = registration_fixture(profile)
            cls.inputs[profile] = prepared
            registration, data, _, _ = prepared
            output = cls.root / profile
            result = native.run_native(data["x"], data["y"], dataset_id=data["dataset_id"],
                source_sha256=data["source_sha256"], feature_names=data["feature_names"], task=data["task"], output=output)
            if result["status"] != "completed":
                raise AssertionError(result)
            cls.blobs[profile] = snapshot_native_bundle(output)

    @classmethod
    def tearDownClass(cls):
        cls.parent.cleanup()

    def setUp(self):
        self.registration = copy.deepcopy(self.inputs["sklearn-wine"][0])

    def build(self, *, data=None, data_bytes=None, plan_bytes=None, **changes):
        registration, original, original_bytes, original_plan = self.inputs["sklearn-wine"]
        values = dict(registration_id="2" * 32, agency_id="agency", project_id="project", case_id="case",
            profile_id="sklearn-wine", data=original if data is None else data,
            data_bytes=original_bytes if data_bytes is None else data_bytes,
            plan_bytes=original_plan if plan_bytes is None else plan_bytes,
            history=registration["history"], workflow_sha256="3" * 64, runtime_sha256=digest(runtime_observation()))
        values.update(changes)
        return build_registration(**values)

    def test_build_binds_exact_plan_sample_metadata_and_runtime(self):
        registration = self.registration
        _, data, raw, plan_raw = self.inputs["sklearn-wine"]
        self.assertEqual(registration["source"]["data_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(registration["plan"]["plan_sha256"], hashlib.sha256(plan_raw).hexdigest())
        self.assertEqual(registration["source"]["metadata_sha256"], digest(data["metadata"]))
        self.assertEqual(registration["plan"]["runtime_sha256"], digest(runtime_observation()))
        self.assertEqual(registration["plan"]["rows"], 128)
        self.assertEqual(registration["plan"]["train_groups"], 64)
        self.assertIsNone(registration["population"]["protected_unit"])
        self.assertEqual(registration["history"]["external_history"], "unknown")

    def test_validation_returns_owned_deep_copy(self):
        validated = validate_registration(self.registration)
        self.registration["source"]["metadata"]["selected_rows"] = 999
        self.registration["history"]["sequence"] = 99
        self.assertEqual(validated["source"]["metadata"]["selected_rows"], 128)
        self.assertEqual(validated["history"]["sequence"], 0)

    def test_evaluate_classification_replays_exact_bytes_without_authorizing(self):
        review = evaluate_native(self.registration, self.blobs["sklearn-wine"])
        self.assertEqual(review["utility"]["metric"], "accuracy")
        self.assertGreater(review["utility"]["improvement"], 0)
        self.assertEqual(review["utility"]["result"], "met")
        self.assertEqual(review["registration_sha256"], digest(self.registration))
        self.assertEqual(review["candidate_sha256"], hashlib.sha256(self.blobs["sklearn-wine"]["candidate.json"]).hexdigest())
        for key in module.FLAGS:
            self.assertIs(review[key], key == "fixture_only")
        self.assertIn("non_dp_mechanism", review["permanent_block_reasons"])
        self.assertIn("agency_approval_pending", review["permanent_block_reasons"])

    def test_regression_review_keeps_full_cohort_preprocessing_caveat(self):
        registration = self.inputs["sklearn-diabetes"][0]
        self.assertIn("full-cohort centering", registration["population"]["upstream_preprocessing"])
        self.assertIs(registration["population"]["upstream_preprocessing_qualified"], False)
        review = evaluate_native(registration, self.blobs["sklearn-diabetes"])
        self.assertEqual(review["utility"]["metric"], "rmse")
        self.assertEqual(review["utility"]["improvement"], review["utility"]["baseline"] - review["utility"]["candidate"])
        self.assertIs(review["scientific_evidence_qualified"], False)

    def test_dp_claims_zero_epsilon_and_privacy_clearance_cannot_be_inserted(self):
        for mutate in (lambda r: r["mechanism"].update(epsilon=0), lambda r: r["mechanism"].update(delta=0.0),
                       lambda r: r["mechanism"].update(accountant="rdp"), lambda r: r["mechanism"].update(protection_claim="DP"),
                       lambda r: r.update(authorization_eligible=True), lambda r: r.update(can_clear=0),
                       lambda r: r["mechanism"].update(privacy_budget_supported=True),
                       lambda r: r["utility"].update(privacy_auc_threshold=.6)):
            registration = copy.deepcopy(self.registration)
            mutate(registration)
            with self.assertRaises(RegistrationError):
                validate_registration(registration)

    def test_lineage_and_external_estimators_are_fixed_fresh_native_only(self):
        for fields in ({"parents": ["a" * 64]}, {"external_import": True}, {"mode": "continued_training"},
                       {"components": ["pickle"]}):
            registration = copy.deepcopy(self.registration)
            registration["lineage"].update(fields)
            with self.assertRaises(RegistrationError):
                validate_registration(registration)

    def test_unknown_fields_missing_fields_and_bool_integer_aliases_fail(self):
        for mutate in (lambda r: r.update(extra="x"), lambda r: r.pop("recipient"),
                       lambda r: r["plan"].update(seed=True), lambda r: r["plan"].update(rows=128.),
                       lambda r: r["history"].update(sequence=False), lambda r: r["history"].update(privacy_accounting_supported=0),
                       lambda r: r["plan"].update(external_model_path="x")):
            registration = copy.deepcopy(self.registration)
            mutate(registration)
            with self.assertRaises(RegistrationError):
                validate_registration(registration)

    def test_no_record_to_person_or_representativeness_upgrade(self):
        for field, value in (("protected_unit", "person"), ("contribution_bound", 1), ("feature_group_is_privacy_unit", True),
                             ("person_level_disjointness_established", True), ("fresh_audit_evidence", True),
                             ("representativeness_established", True), ("historical_training_data_reused", False)):
            registration = copy.deepcopy(self.registration)
            registration["population"][field] = value
            with self.assertRaises(RegistrationError):
                validate_registration(registration)

    def test_post_result_utility_threshold_or_metric_change_rejected(self):
        for fields in ({"threshold": -.1}, {"threshold": 0}, {"criterion": "always_pass"}, {"metric": "membership_auc"},
                       {"agency_criterion_approved": True}, {"evaluation_partition": "training"}):
            registration = copy.deepcopy(self.registration)
            registration["utility"].update(fields)
            with self.assertRaises(RegistrationError):
                validate_registration(registration)

    def test_metadata_pins_and_false_qualifications_are_validated(self):
        mutations = [("fresh_audit_evidence", True), ("local_public_fixture_pin_verified", 1),
                     ("source", "arbitrary source"), ("profile_id", "acs"), ("full_fixture_sha256", "f" * 64),
                     ("upstream_preprocessing", "independently proven"), ("unknown", None)]
        for key, value in mutations:
            registration = copy.deepcopy(self.registration)
            registration["source"]["metadata"][key] = value
            registration["source"]["metadata_sha256"] = digest(registration["source"]["metadata"])
            with self.assertRaises(RegistrationError):
                validate_registration(registration)

    def test_profile_task_source_and_descriptor_cannot_be_relabeled(self):
        for mutate in (lambda r: r.update(profile_id="arbitrary"), lambda r: r["source"].update(task="regression"),
                       lambda r: r["source"].update(source_sha256="f" * 64),
                       lambda r: r["source"]["profile_descriptor"].update(expected_source_sha256="f" * 64)):
            registration = copy.deepcopy(self.registration)
            mutate(registration)
            with self.assertRaises(RegistrationError):
                validate_registration(registration)

    def test_history_scope_is_agency_project_wide_and_not_profile_specific(self):
        same_scope = digest({"agency_id": "agency", "project_id": "project"})
        self.assertEqual(self.registration["history"]["scope_id"], same_scope)
        self.assertEqual(self.inputs["sklearn-diabetes"][0]["history"]["scope_id"], same_scope)
        changed = copy.deepcopy(self.registration)
        changed["case_id"] = "other-case"
        self.assertEqual(validate_registration(changed)["history"]["scope_id"], same_scope)
        changed["project_id"] = "other-project"
        with self.assertRaises(RegistrationError):
            validate_registration(changed)
        for fields in ({"external_history": "complete"}, {"privacy_accounting_supported": True}, {"head_sha256": "bad"},
                       {"sequence": -1}, {"ledger_id": "A" * 32}):
            changed = copy.deepcopy(self.registration)
            changed["history"].update(fields)
            with self.assertRaises(RegistrationError):
                validate_registration(changed)

    def test_evaluate_refuses_changed_plan_data_runtime_and_recipe(self):
        for field in ("plan_sha256", "adapter_implementation_sha256", "runtime_sha256"):
            changed = copy.deepcopy(self.registration)
            changed["plan"][field] = "f" * 64
            with self.assertRaises(RegistrationError):
                evaluate_native(changed, self.blobs["sklearn-wine"])
        changed = copy.deepcopy(self.registration)
        changed["source"]["data_sha256"] = "f" * 64
        with self.assertRaises(RegistrationError):
            evaluate_native(changed, self.blobs["sklearn-wine"])

    def test_changed_seed_cannot_rebind_old_execution(self):
        changed = copy.deepcopy(self.registration)
        changed["plan"]["seed"] += 1
        validate_registration(changed)  # A different prospective plan needs fresh execution.
        with self.assertRaises(RegistrationError):
            evaluate_native(changed, self.blobs["sklearn-wine"])

    def test_build_refuses_changed_input_even_if_caller_relabels_source(self):
        _, original, raw, plan = self.inputs["sklearn-wine"]
        altered = dict(original, x=original["x"].copy())
        altered["x"][0, 0] += 1.
        with self.assertRaises(RegistrationError):
            self.build(data=altered)
        with self.assertRaises(RegistrationError):
            self.build(data_bytes=raw + b" ")
        with self.assertRaises(RegistrationError):
            self.build(plan_bytes=plan + b" ")
        with self.assertRaises(RegistrationError):
            self.build(runtime_sha256="0" * 64)

    def test_recomputed_snapshot_still_must_match_loader_sample_metadata(self):
        _, data, _, _ = self.inputs["sklearn-wine"]
        changed = dict(data, x=data["x"].copy())
        changed["x"][0, 0] += 1
        x, y = native._arrays(changed["x"], changed["y"])
        raw = native_bytes({"schema_version": "mra-native-tabular-data/v1", "x": x.tolist(), "y": y.tolist(),
                            "feature_names": data["feature_names"], "task": data["task"]}) + b"\n"
        plan = native._plan(x, y, data["dataset_id"], data["source_sha256"], data["feature_names"], data["task"],
                            20261001, hashlib.sha256(raw).hexdigest())
        with self.assertRaises(RegistrationError):
            self.build(data=changed, data_bytes=raw, plan_bytes=native_bytes(plan) + b"\n")

    def test_normalized_classification_float_labels_preserve_sample_binding(self):
        _, original, _, _ = self.inputs["sklearn-wine"]
        normalized = dict(original, y=original["y"].astype(float))
        result = self.build(data=normalized)
        self.assertEqual(result, self.registration)

    def test_utility_strict_ties_and_wrong_direction_do_not_pass(self):
        for task, metrics in (("classification", {"accuracy": .5, "majority_accuracy": .5}),
                              ("classification", {"accuracy": .4, "majority_accuracy": .5}),
                              ("regression", {"rmse": 2., "training_mean_baseline_rmse": 2.}),
                              ("regression", {"rmse": 3., "training_mean_baseline_rmse": 2.})):
            review = module._utility_review(task, metrics)
            self.assertEqual(review["result"], "not_met")
            self.assertLessEqual(review["improvement"], 0)

    def test_review_counts_float_types_and_permanent_blockers_are_checked(self):
        original = review_fixture(self.registration)
        for mutate in (lambda r: r["utility"].update(candidate=True), lambda r: r["utility"].update(improvement=0.),
                       lambda r: r["utility"].update(result="not_met"), lambda r: r["utility"].update(baseline=-1.),
                       lambda r: r["utility"].update(candidate=float("nan")), lambda r: r.update(permanent_block_reasons=[]),
                       lambda r: r.update(scientific_evidence_qualified=True), lambda r: r.update(extra="x")):
            changed = copy.deepcopy(original)
            mutate(changed)
            with self.assertRaises(RegistrationError):
                validate_review(changed)

    def test_utility_met_never_removes_non_dp_or_population_blocker(self):
        review = review_fixture(self.registration)
        self.assertEqual(review["utility"]["result"], "met")
        self.assertEqual(review["permanent_block_reasons"], list(module.BLOCK_REASONS))
        self.assertIs(review["authorization_eligible"], False)
        with self.assertRaises(TypeError):
            evaluate_native(self.registration, self.blobs["sklearn-wine"], admission={"approved": True})

    def test_artifact_tampering_and_missing_reports_are_rejected(self):
        for key in ("candidate.json", "report.json", "dataset.json"):
            blobs = dict(self.blobs["sklearn-wine"])
            blobs[key] += b" "
            with self.assertRaises(RegistrationError):
                evaluate_native(self.registration, blobs)
        blobs = dict(self.blobs["sklearn-wine"])
        del blobs["report.json"]
        with self.assertRaises(RegistrationError):
            evaluate_native(self.registration, blobs)

    def test_registration_is_snapshotted_before_replay_callback(self):
        original = module.replay_native_bundle
        incoming = copy.deepcopy(self.registration)
        def mutate(blobs):
            incoming["source"]["data_sha256"] = "0" * 64
            return original(blobs)
        with patch.object(module, "replay_native_bundle", side_effect=mutate):
            review = evaluate_native(incoming, self.blobs["sklearn-wine"])
        self.assertEqual(review["registration_sha256"], digest(self.registration))

    def test_metadata_json_bounds_nonfinite_duplicates_and_null_distinction(self):
        for raw in (b'{"x":1,"x":2}', b'{"x":1e999}', b'{"x":NaN}', b'[' * 17 + b'0' + b']' * 17,
                    b'"' + b'x' * 65536 + b'"'):
            with self.assertRaises(RegistrationError):
                strict_json(raw)
        self.assertNotEqual(canonical_bytes(None), canonical_bytes(0))
        self.assertNotEqual(canonical_bytes(False), canonical_bytes(0))


if __name__ == "__main__":
    unittest.main()
