from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from validate_llm_audit_profile import (  # noqa: E402
    ProfileValidationError,
    load_profile,
    validate_profile,
)


class LlmAuditProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.profile = json.loads(
            (ROOT / "reproduction" / "llm" / "audit-profile.example.json").read_text(
                encoding="utf-8"
            )
        )

    def ready_profile(self) -> dict:
        def replace_sentinels(value, path: str = "profile"):
            if isinstance(value, dict):
                return {
                    key: replace_sentinels(item, f"{path}.{key}")
                    for key, item in value.items()
                }
            if isinstance(value, list):
                return [
                    replace_sentinels(item, f"{path}[{index}]")
                    for index, item in enumerate(value)
                ]
            if isinstance(value, str):
                if value == "0" * 64:
                    return "a" * 64
                if value == "sha256:" + "0" * 64:
                    return "sha256:" + "a" * 64
                if value.startswith("replace-") or "placeholder" in value.lower():
                    suffix = hashlib.sha256(path.encode("utf-8")).hexdigest()[:16]
                    return f"approved-{suffix}"
            return value

        ready = replace_sentinels(copy.deepcopy(self.profile))
        ready["protocol_status"] = "approved_for_collection"
        ready["preregistered_at"] = "2026-08-22T00:00:00Z"
        ready["release_binding"]["valid_until"] = "2099-01-01T00:00:00Z"

        for family_name in ("watermark_family", "canary_family"):
            family = ready["multiplicity"][family_name]
            family["correction_order"] = [
                item["test_id"] for item in family["registered_tests"]
            ]

        components = ready["release_binding"]["llm_protocol_components"]
        components["maximum_session_tokens"] = 8192
        components["maximum_lifetime_queries"] = 3000
        components["maximum_concurrent_sessions"] = 4

        watermark = ready["watermark_study"]
        sample = watermark["sample_size_and_power"]
        sample.update(
            registered_cell_count=2,
            null_outputs_per_cell=100,
            release_outputs_per_cell=100,
            positive_control_outputs=10,
            retry_query_budget=10,
            tail_claim_minimum_null_count=72,
            minimum_detectable_effect=0.1,
            target_power=0.8,
            operational_fpr_targets=[0.05],
        )
        scheme = watermark["scheme"]
        scheme["key_count"] = 1
        scheme["maximum_key_or_generation_budget"] = 10000
        detector = watermark["detector"]
        detector.update(
            key_count=1,
            custody_roles=["embedding_provider", "independent_assessor"],
            compromise_status="uncompromised",
            revocation_status="active",
            threshold=4.0,
            minimum_eligible_tokens=100,
            detector_api_visibility="offline",
            detector_api_output="score",
            detector_api_rate_limit=100,
            detector_api_total_query_budget=12,
        )
        calibration = watermark["null_calibration"]
        calibration.update(
            domains=["general_prose"],
            languages=["en"],
            length_strata=["100_to_299_tokens"],
            entropy_strata=["registered_mid_entropy"],
        )
        search = watermark["search_spec"]
        search.update(
            window_stride=0,
            key_ids_searched=["verification-key-1"],
            tokenizers_searched=[components["tokenizer_sha256"]],
        )
        watermark["quality_study"]["paired_prompt_count"] = 20
        for index, attack in enumerate(watermark["attack_matrix"]):
            attack.update(
                attack_id=f"attack-{index:02d}",
                model_query_budget=1,
                detector_query_budget=1,
                observed_watermarked_token_budget=100,
            )

        watermark_queries = 2 * (100 + 100) + 10 + 10 + 2 * 20 + 12
        ready["decision_games"]["watermark"]["operational_false_positive_target"] = 0.05
        ready["decision_games"]["watermark"]["query_budget"] = watermark_queries
        canary = ready["canary_study"]
        canary_queries = (
            canary["member_canary_count"] + canary["nonmember_decoy_count"]
        ) * canary["queries_per_canary_total"]
        ready["decision_games"]["canary"]["query_budget"] = canary_queries
        ready["collection_controls"]["maximum_concurrent_sessions"] = 2
        return ready

    def test_example_is_a_valid_fail_closed_template(self) -> None:
        profile = validate_profile(copy.deepcopy(self.profile))
        self.assertEqual(set(profile["decision_games"]), {"watermark", "canary"})
        self.assertFalse(profile["decision_semantics"]["can_clear"])
        self.assertFalse(profile["naturalistic_extraction_probe"]["treated_as_canary"])

    def test_profile_cannot_promote_watermark_or_null_results(self) -> None:
        unsafe = copy.deepcopy(self.profile)
        unsafe["decision_semantics"]["can_clear"] = True
        with self.assertRaisesRegex(ProfileValidationError, "can_clear=false"):
            validate_profile(unsafe)

        unsafe = copy.deepcopy(self.profile)
        unsafe["decision_semantics"]["watermark_can_block_privacy"] = True
        with self.assertRaisesRegex(ProfileValidationError, "cannot block privacy"):
            validate_profile(unsafe)

    def test_registered_family_and_dose_allocation_are_replayable(self) -> None:
        wrong_family = copy.deepcopy(self.profile)
        wrong_family["multiplicity"]["watermark_family"]["family_size"] = 1
        with self.assertRaisesRegex(ProfileValidationError, "family_size"):
            validate_profile(wrong_family)

        boolean_family = copy.deepcopy(self.profile)
        boolean_family["multiplicity"]["canary_family"]["family_size"] = True
        with self.assertRaisesRegex(ProfileValidationError, "integer"):
            validate_profile(boolean_family)

        indivisible = copy.deepcopy(self.profile)
        indivisible["canary_study"]["member_canary_count"] = 200
        with self.assertRaisesRegex(ProfileValidationError, "integral equal allocation"):
            validate_profile(indivisible)

    def test_complete_payload_binding_and_artifact_contract_are_mandatory(self) -> None:
        incomplete_binding = copy.deepcopy(self.profile)
        incomplete_binding["analyzer_provenance"]["required_bound_sections"].remove(
            "protocol_status"
        )
        with self.assertRaisesRegex(ProfileValidationError, "complete payload"):
            validate_profile(incomplete_binding)

        incomplete_artifacts = copy.deepcopy(self.profile)
        incomplete_artifacts["required_evidence_artifacts"].pop()
        with self.assertRaisesRegex(ProfileValidationError, "post-collection digest contract"):
            validate_profile(incomplete_artifacts)

    def test_adaptive_attack_entries_are_strict_and_unique(self) -> None:
        incomplete = copy.deepcopy(self.profile)
        incomplete["watermark_study"]["attack_matrix"][0].pop("stopping_rule")
        with self.assertRaisesRegex(ProfileValidationError, "missing required fields"):
            validate_profile(incomplete)

        duplicate = copy.deepcopy(self.profile)
        duplicate["watermark_study"]["attack_matrix"][1]["attack_id"] = duplicate[
            "watermark_study"
        ]["attack_matrix"][0]["attack_id"]
        with self.assertRaisesRegex(ProfileValidationError, "duplicate attack IDs"):
            validate_profile(duplicate)

    def test_collection_ready_profile_has_a_successful_path(self) -> None:
        ready = validate_profile(self.ready_profile(), collection_ready=True)
        self.assertEqual(ready["protocol_status"], "approved_for_collection")

    def test_collection_ready_rejects_placeholders_and_required_nulls(self) -> None:
        with self.assertRaisesRegex(ProfileValidationError, "protocol_status"):
            validate_profile(copy.deepcopy(self.profile), collection_ready=True)

        ready = self.ready_profile()
        ready["watermark_study"]["detector"]["threshold"] = None
        with self.assertRaisesRegex(ProfileValidationError, "unresolved null"):
            validate_profile(ready, collection_ready=True)

    def test_collection_ready_rejects_bad_hash_and_nonfinite_number(self) -> None:
        bad_hash = self.ready_profile()
        bad_hash["release_binding"]["artifact_sha256"] = "not-a-digest"
        with self.assertRaisesRegex(ProfileValidationError, "lowercase SHA-256"):
            validate_profile(bad_hash, collection_ready=True)

        nonfinite = self.ready_profile()
        nonfinite["watermark_study"]["detector"]["threshold"] = float("inf")
        with self.assertRaisesRegex(ProfileValidationError, "finite"):
            validate_profile(nonfinite, collection_ready=True)

    def test_json_loader_rejects_nonfinite_constants(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile.json"
            path.write_text('{"threshold": NaN}', encoding="utf-8")
            with self.assertRaisesRegex(ProfileValidationError, "non-finite JSON constant"):
                load_profile(path)

    def test_collection_ready_rejects_unsupported_tail_plan(self) -> None:
        ready = self.ready_profile()
        ready["watermark_study"]["sample_size_and_power"]["null_outputs_per_cell"] = 1
        with self.assertRaisesRegex(ProfileValidationError, "cannot support"):
            validate_profile(ready, collection_ready=True)

        missing_target = self.ready_profile()
        missing_target["watermark_study"]["sample_size_and_power"]["operational_fpr_targets"] = [0.1]
        with self.assertRaisesRegex(ProfileValidationError, "must include"):
            validate_profile(missing_target, collection_ready=True)

    def test_collection_ready_counts_quality_attacks_and_all_query_paths(self) -> None:
        ready = self.ready_profile()
        ready["watermark_study"]["attack_matrix"][0]["model_query_budget"] += 1
        with self.assertRaisesRegex(ProfileValidationError, "complete registered plan"):
            validate_profile(ready, collection_ready=True)

        overflow = self.ready_profile()
        overflow["release_binding"]["llm_protocol_components"]["maximum_lifetime_queries"] = 100
        with self.assertRaisesRegex(ProfileValidationError, "complete registered query plan"):
            validate_profile(overflow, collection_ready=True)

    def test_key_tokenizer_concurrency_and_assignment_consistency(self) -> None:
        wrong_key_count = self.ready_profile()
        wrong_key_count["watermark_study"]["detector"]["key_count"] = 2
        with self.assertRaisesRegex(ProfileValidationError, "key counts must match"):
            validate_profile(wrong_key_count, collection_ready=True)

        independent_fixed_arms = copy.deepcopy(self.profile)
        independent_fixed_arms["canary_study"]["inclusion_randomization"]["independent_inclusion_bits"] = True
        with self.assertRaisesRegex(ProfileValidationError, "cannot claim independent"):
            validate_profile(independent_fixed_arms)

        excessive_concurrency = self.ready_profile()
        excessive_concurrency["collection_controls"]["maximum_concurrent_sessions"] = 5
        with self.assertRaisesRegex(ProfileValidationError, "exceeds"):
            validate_profile(excessive_concurrency, collection_ready=True)

        compromised_key = self.ready_profile()
        compromised_key["watermark_study"]["detector"]["compromise_status"] = "compromised"
        with self.assertRaisesRegex(ProfileValidationError, "must be uncompromised"):
            validate_profile(compromised_key, collection_ready=True)

        revoked_key = self.ready_profile()
        revoked_key["watermark_study"]["detector"]["revocation_status"] = "revoked"
        with self.assertRaisesRegex(ProfileValidationError, "must be active"):
            validate_profile(revoked_key, collection_ready=True)

    def test_calibration_decision_rule_cannot_be_reversed(self) -> None:
        reversed_rule = copy.deepcopy(self.profile)
        reversed_rule["watermark_study"]["hypotheses"]["null_calibration"][
            "decision_rule"
        ] = "failure_to_reject_null_means_calibrated"
        with self.assertRaisesRegex(ProfileValidationError, "decision_rule"):
            validate_profile(reversed_rule)

    def test_future_preregistration_is_rejected(self) -> None:
        ready = self.ready_profile()
        ready["preregistered_at"] = "2098-01-01T00:00:00Z"
        with self.assertRaisesRegex(ProfileValidationError, "in the future"):
            validate_profile(ready, collection_ready=True)


if __name__ == "__main__":
    unittest.main()
