from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from model_release_assurance.audit import (
    AuditCheckpoint,
    AuditStore,
    AuditVerification,
    GENESIS,
    _AUDIT_EVENT_HASH_FORMAT,
    _event_material,
    _event_material_v2,
)
from model_release_assurance.engine import AssuranceEngine
from model_release_assurance.errors import IntegrityError
from model_release_assurance.integrity import canonical_json_bytes, sha256_bytes, sha256_file
from model_release_assurance.models import AssessmentReport, AssessmentRequest
from model_release_assurance.optimizer import (
    OptimizationReport,
    OptimizationRequest,
    ReleaseOptimizer,
)


ROOT = Path(__file__).resolve().parents[1]


def assessment_request() -> AssessmentRequest:
    raw = json.loads((ROOT / "examples" / "request.json").read_text())
    raw["release"]["artifact_sha256"] = sha256_file(
        ROOT / "examples" / "artifacts" / "demo-tree.json"
    )
    return AssessmentRequest.model_validate(raw)


def assessment_pair() -> tuple[AssessmentRequest, AssessmentReport]:
    request = assessment_request()
    report = AssuranceEngine().assess(request, ROOT / "examples")
    return request, report


def optimization_pair() -> tuple[OptimizationRequest, OptimizationReport]:
    request = OptimizationRequest.model_validate_json(
        (ROOT / "examples" / "optimization-request.json").read_text()
    )
    report = ReleaseOptimizer().optimize(request, ROOT / "examples")
    return request, report


class AuditV2Tests(unittest.TestCase):
    def test_fresh_runs_reconcile_and_export_an_anchorable_checkpoint(self) -> None:
        request, report = assessment_pair()
        with tempfile.TemporaryDirectory() as directory:
            store = AuditStore(Path(directory) / "audit.sqlite3")
            completed_run = store.append_assessment_intent(request)
            failed_run = store.append_assessment_intent(request)

            self.assertNotEqual(completed_run.run_id, failed_run.run_id)
            completed = store.append_assessment_completed(completed_run, report)
            failed = store.append_assessment_failed(
                failed_run,
                "worker_timeout",
                "the isolated analyzer exceeded its deadline",
            )

            verified = store.verify(
                require_events=True,
                expected_event_count=4,
                expected_head_sha256=failed.event_hash,
            )
            self.assertEqual(verified.event_count, 4)
            self.assertEqual(verified.intent_count, 2)
            self.assertEqual(verified.completed_count, 1)
            self.assertEqual(verified.failed_count, 1)
            self.assertEqual(verified.redacted_failure_diagnostic_count, 1)
            self.assertEqual(verified.plaintext_failure_diagnostic_count, 0)
            self.assertEqual(verified.diagnostic_degradations, ())
            self.assertEqual(verified.legacy_hash_event_count, 0)
            self.assertEqual(verified.domain_separated_hash_event_count, 4)
            self.assertEqual(verified.release_ids, (request.release.release_id,))
            self.assertEqual(
                verified.release_instance_sha256s,
                (completed_run.release_instance_sha256,),
            )
            self.assertEqual(
                verified.runtime_identity.component_id, "audit_verifier"
            )
            self.assertEqual(completed.hash_format, _AUDIT_EVENT_HASH_FORMAT)
            self.assertEqual(verified.orphaned_run_ids, ())
            self.assertTrue(verified.complete)
            self.assertEqual(completed.sequence, 3)
            self.assertEqual(store.verify_chain(), 4)

            checkpoint = store.export_checkpoint(require_events=True)
            self.assertEqual(checkpoint.ledger_id, verified.ledger_id)
            self.assertEqual(checkpoint.event_count, verified.event_count)
            self.assertEqual(checkpoint.head_sha256, verified.head_sha256)
            store.verify(
                expected_event_count=checkpoint.event_count,
                expected_head_sha256=checkpoint.head_sha256,
                expected_ledger_id=checkpoint.ledger_id,
            )
            read_only = AuditStore.open_read_only(store.path)
            self.assertEqual(read_only.verify().head_sha256, checkpoint.head_sha256)
            with self.assertRaisesRegex(IntegrityError, "read-only audit store"):
                read_only.append_assessment_intent(request)

            with self.assertRaisesRegex(IntegrityError, "event count mismatch"):
                store.verify(expected_event_count=3)
            with self.assertRaisesRegex(IntegrityError, "head mismatch"):
                store.verify(expected_head_sha256="f" * 64)
            with self.assertRaisesRegex(IntegrityError, "expected ledger"):
                store.verify(expected_ledger_id=uuid.uuid4())

            with self.assertRaisesRegex(ValidationError, "head must be genesis"):
                AuditCheckpoint(
                    ledger_id=verified.ledger_id,
                    event_count=0,
                    last_sequence=0,
                    head_sha256="f" * 64,
                    created_at=datetime.now(timezone.utc),
                )
            with self.assertRaisesRegex(ValidationError, "categories do not reconcile"):
                AuditVerification(
                    ledger_id=verified.ledger_id,
                    event_count=4,
                    last_sequence=4,
                    head_sha256="f" * 64,
                    legacy_event_count=1,
                    legacy_hash_event_count=0,
                    domain_separated_hash_event_count=4,
                    intent_count=2,
                    completed_count=1,
                    failed_count=1,
                    redacted_failure_diagnostic_count=1,
                    plaintext_failure_diagnostic_count=0,
                    diagnostic_degradations=(),
                    orphaned_run_ids=(),
                    complete=True,
                    runtime_identity=verified.runtime_identity,
                )

            with self.assertRaisesRegex(
                ValidationError, "failure diagnostic counts do not reconcile"
            ):
                AuditVerification.model_validate(
                    {
                        **verified.model_dump(mode="json"),
                        "redacted_failure_diagnostic_count": 0,
                    }
                )
            with self.assertRaisesRegex(
                ValidationError, "diagnostic degradations disagree"
            ):
                AuditVerification.model_validate(
                    {
                        **verified.model_dump(mode="json"),
                        "redacted_failure_diagnostic_count": 0,
                        "plaintext_failure_diagnostic_count": 1,
                        "diagnostic_degradations": [],
                    }
                )

            invalid_runtime = verified.runtime_identity.model_copy(
                update={"component_id": "different_verifier"}
            )
            with self.assertRaisesRegex(ValidationError, "component identity"):
                AuditVerification.model_validate(
                    {
                        **verified.model_dump(mode="json"),
                        "runtime_identity": invalid_runtime.model_dump(mode="json"),
                    }
                )

    def test_orphaned_intent_is_visible_and_requires_one_terminal(self) -> None:
        request, _ = assessment_pair()
        with tempfile.TemporaryDirectory() as directory:
            store = AuditStore(Path(directory) / "audit.sqlite3")
            run = store.append_assessment_intent(request)

            incomplete = store.verify(require_complete=False)
            self.assertFalse(incomplete.complete)
            self.assertEqual(incomplete.orphaned_run_ids, (run.run_id,))
            with self.assertRaisesRegex(IntegrityError, "orphaned intent"):
                store.verify()

            store.append_assessment_failed(run, "invalid_evidence")
            self.assertTrue(store.verify().complete)
            with self.assertRaisesRegex(IntegrityError, "already has a terminal"):
                store.append_assessment_failed(run, "duplicate_terminal")

    def test_failed_events_persist_only_a_redacted_diagnostic_fingerprint(self) -> None:
        request = assessment_request()
        secret = "mra-secret-token-7b3e5f4d-diagnostic-sentinel"
        sensitive_path = "/private/tenant-482/patient-prompts/source.ndjson"
        diagnostic = f"provider token={secret}; source={sensitive_path}"
        with tempfile.TemporaryDirectory() as directory:
            store = AuditStore(Path(directory) / "audit.sqlite3")
            # Keep one connection open so platforms that retain a live WAL are
            # checked before their final connection-close checkpoint.
            connection = sqlite3.connect(store.path)
            try:
                connection.execute("PRAGMA journal_mode=WAL")
                first_run = store.append_assessment_intent(request)
                store.append_assessment_failed(
                    first_run,
                    "worker_failed",
                    diagnostic,
                )
                second_run = store.append_assessment_intent(request)
                store.append_assessment_failed(
                    second_run,
                    "worker_failed",
                    diagnostic,
                )

                verified = store.verify(require_events=True)
                self.assertTrue(verified.complete)
                self.assertEqual(verified.failed_count, 2)
                self.assertEqual(verified.redacted_failure_diagnostic_count, 2)
                self.assertEqual(verified.plaintext_failure_diagnostic_count, 0)
                self.assertEqual(verified.diagnostic_degradations, ())

                payload_jsons = [
                    row[0]
                    for row in connection.execute(
                        """
                        SELECT payload_json FROM audit_events
                        WHERE event_type = 'assessment_failed'
                        ORDER BY sequence
                        """
                    )
                ]
                payloads = [json.loads(value) for value in payload_jsons]
                self.assertEqual(
                    [payload["error_code"] for payload in payloads],
                    ["worker_failed", "worker_failed"],
                )
                fingerprints = [payload["error_message"] for payload in payloads]
                self.assertEqual(fingerprints[0], fingerprints[1])
                self.assertRegex(fingerprints[0], r"^redacted:sha256:[0-9a-f]{64}$")
                expected_fingerprint = "redacted:sha256:" + sha256_bytes(
                    b"AI_MODE_L_CHECK:AUDIT_DIAGNOSTIC\x00"
                    + canonical_json_bytes(
                        {
                            "error_code": "worker_failed",
                            "error_message": diagnostic,
                        }
                    )
                )
                self.assertEqual(fingerprints[0], expected_fingerprint)

                for payload_json in payload_jsons:
                    self.assertNotIn(secret, payload_json)
                    self.assertNotIn(sensitive_path, payload_json)

                sentinel_bytes = (
                    secret.encode("utf-8"),
                    sensitive_path.encode("utf-8"),
                )
                storage_paths = [
                    store.path,
                    store.path.with_name(f"{store.path.name}-wal"),
                ]
                for storage_path in storage_paths:
                    if not storage_path.exists():
                        continue
                    stored_bytes = storage_path.read_bytes()
                    for sentinel in sentinel_bytes:
                        self.assertNotIn(sentinel, stored_bytes)
            finally:
                connection.close()

    def test_failed_event_inputs_are_bounded_before_fingerprinting(self) -> None:
        request = assessment_request()
        with tempfile.TemporaryDirectory() as directory:
            store = AuditStore(Path(directory) / "audit.sqlite3")
            oversized_code_run = store.append_assessment_intent(request)
            oversized_message_run = store.append_assessment_intent(request)

            with self.assertRaises(ValidationError):
                store.append_assessment_failed(
                    oversized_code_run,
                    "x" * 129,
                    "bounded diagnostic",
                )
            with self.assertRaises(ValidationError):
                store.append_assessment_failed(
                    oversized_message_run,
                    "worker_failed",
                    "x" * 4097,
                )

            incomplete = store.verify(require_complete=False)
            self.assertEqual(incomplete.failed_count, 0)
            self.assertEqual(incomplete.redacted_failure_diagnostic_count, 0)
            self.assertEqual(incomplete.plaintext_failure_diagnostic_count, 0)
            self.assertEqual(
                set(incomplete.orphaned_run_ids),
                {oversized_code_run.run_id, oversized_message_run.run_id},
            )

            store.append_assessment_failed(oversized_code_run, "x" * 128)
            store.append_assessment_failed(
                oversized_message_run,
                "worker_failed",
                "x" * 4096,
            )
            verified = store.verify()
            self.assertEqual(verified.failed_count, 2)
            self.assertEqual(verified.redacted_failure_diagnostic_count, 2)
            self.assertEqual(verified.plaintext_failure_diagnostic_count, 0)

    def test_plaintext_v2_failure_is_reported_as_a_diagnostic_degradation(self) -> None:
        request = assessment_request()
        plaintext_diagnostic = "legacy plaintext diagnostic"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit.sqlite3"
            store = AuditStore(path)
            run = store.append_assessment_intent(request)
            store.append_assessment_failed(run, "worker_failed", "original")

            with sqlite3.connect(path) as connection:
                (
                    occurred_at,
                    event_type,
                    record_id,
                    payload_json,
                    previous_hash,
                ) = connection.execute(
                    """
                    SELECT occurred_at, event_type, assessment_id, payload_json,
                           previous_hash
                    FROM audit_events WHERE sequence = 2
                    """
                ).fetchone()
                ledger_id = connection.execute(
                    "SELECT value FROM audit_metadata WHERE key = 'ledger_id'"
                ).fetchone()[0]
                payload = json.loads(payload_json)
                payload["error_message"] = plaintext_diagnostic
                plaintext_payload_json = canonical_json_bytes(payload).decode("utf-8")
                plaintext_event_hash = sha256_bytes(
                    _event_material_v2(
                        ledger_id,
                        occurred_at,
                        event_type,
                        record_id,
                        plaintext_payload_json,
                        previous_hash,
                    )
                )
                connection.execute(
                    """
                    UPDATE audit_events
                    SET payload_json = ?, event_hash = ?
                    WHERE sequence = 2
                    """,
                    (plaintext_payload_json, plaintext_event_hash),
                )
                connection.commit()

            verified = store.verify(require_events=True)
            self.assertEqual(verified.schema_version, "3.0")
            self.assertEqual(verified.failed_count, 1)
            self.assertEqual(verified.redacted_failure_diagnostic_count, 0)
            self.assertEqual(verified.plaintext_failure_diagnostic_count, 1)
            self.assertEqual(
                verified.diagnostic_degradations,
                ("plaintext_failure_diagnostics_present",),
            )
            self.assertEqual(verified.legacy_event_count, 0)
            self.assertEqual(verified.legacy_hash_event_count, 0)
            self.assertEqual(
                verified.runtime_identity.algorithm_profile["failure_diagnostics"],
                "bounded-input-redacted-sha256-with-plaintext-v2-degradation",
            )

    def test_assessment_completion_must_match_the_intent_contract(self) -> None:
        request, report = assessment_pair()
        with tempfile.TemporaryDirectory() as directory:
            store = AuditStore(Path(directory) / "audit.sqlite3")
            run = store.append_assessment_intent(request)
            mismatched = report.model_copy(
                update={
                    "artifact_sha256": "0" * 64,
                    "decisions": tuple(
                        decision.model_copy(
                            update={"assessed_artifact_sha256": "0" * 64}
                        )
                        for decision in report.decisions
                    ),
                }
            )

            with self.assertRaisesRegex(IntegrityError, "does not bind its intent"):
                store.append_assessment_completed(run, mismatched)
            store.append_assessment_failed(run, "contract_binding_mismatch")
            self.assertTrue(store.verify().complete)

            invalid_request = request.model_copy(update={"threats": ()})
            with self.assertRaisesRegex(IntegrityError, "invalid assessment request"):
                store.append_assessment_intent(invalid_request)

    def test_optimization_completion_is_bound_to_the_intent_request(self) -> None:
        request, report = optimization_pair()
        with tempfile.TemporaryDirectory() as directory:
            store = AuditStore(Path(directory) / "audit.sqlite3")
            completed_run = store.append_optimization_intent(request)
            receipt = store.append_optimization_completed(completed_run, report)

            verified = store.verify(expected_head_sha256=receipt.event_hash)
            self.assertEqual(verified.intent_count, 1)
            self.assertEqual(verified.completed_count, 1)

            rejected_run = store.append_optimization_intent(request)
            mismatched_report = report.model_copy(
                update={"request_sha256": "0" * 64}
            )
            with self.assertRaisesRegex(IntegrityError, "different request"):
                store.append_optimization_completed(rejected_run, mismatched_report)
            store.append_optimization_failed(rejected_run, "request_mismatch")

            expiry_run = store.append_optimization_intent(request)
            overlong_report = report.model_copy(
                update={"expires_at": datetime(9999, 1, 1, tzinfo=timezone.utc)}
            )
            with self.assertRaisesRegex(IntegrityError, "does not bind its intent"):
                store.append_optimization_completed(expiry_run, overlong_report)
            store.append_optimization_failed(expiry_run, "authorization_exceeded")
            self.assertEqual(store.verify_chain(), 6)

    def test_semantically_valid_duplicate_terminal_is_rejected_on_replay(self) -> None:
        request, _ = assessment_pair()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit.sqlite3"
            store = AuditStore(path)
            run = store.append_assessment_intent(request)
            terminal = store.append_assessment_failed(run, "worker_failed")

            connection = sqlite3.connect(path)
            try:
                event_type, record_id, payload_json = connection.execute(
                    """
                    SELECT event_type, assessment_id, payload_json
                    FROM audit_events WHERE sequence = 2
                    """
                ).fetchone()
                ledger_id = connection.execute(
                    "SELECT value FROM audit_metadata WHERE key = 'ledger_id'"
                ).fetchone()[0]
                occurred_at = "2099-01-01T00:00:00+00:00"
                duplicate_hash = sha256_bytes(
                    _event_material_v2(
                        ledger_id,
                        occurred_at,
                        event_type,
                        record_id,
                        payload_json,
                        terminal.event_hash,
                    )
                )
                connection.execute(
                    """
                    INSERT INTO audit_events
                    (sequence, occurred_at, event_type, assessment_id, payload_json,
                     previous_hash, event_hash, hash_format)
                    VALUES (3, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        occurred_at,
                        event_type,
                        record_id,
                        payload_json,
                        terminal.event_hash,
                        duplicate_hash,
                        _AUDIT_EVENT_HASH_FORMAT,
                    ),
                )
                connection.commit()
            finally:
                connection.close()

            with self.assertRaisesRegex(IntegrityError, "more than one terminal"):
                store.verify()

    def test_sequence_gaps_and_tail_truncation_fail_closed(self) -> None:
        request, report = assessment_pair()
        with tempfile.TemporaryDirectory() as directory:
            gap_path = Path(directory) / "gap.sqlite3"
            gap_store = AuditStore(gap_path)
            gap_run = gap_store.append_assessment_intent(request)
            gap_store.append_assessment_completed(gap_run, report)
            connection = sqlite3.connect(gap_path)
            try:
                connection.execute(
                    "UPDATE audit_events SET sequence = 3 WHERE sequence = 2"
                )
                connection.commit()
            finally:
                connection.close()
            with self.assertRaisesRegex(IntegrityError, "refusing to extend"):
                gap_store.append_assessment_intent(request)
            with self.assertRaisesRegex(IntegrityError, "not contiguous"):
                gap_store.verify()

            truncated_path = Path(directory) / "truncated.sqlite3"
            truncated_store = AuditStore(truncated_path)
            truncated_run = truncated_store.append_assessment_intent(request)
            truncated_store.append_assessment_completed(truncated_run, report)
            checkpoint = truncated_store.export_checkpoint()
            connection = sqlite3.connect(truncated_path)
            try:
                connection.execute("DELETE FROM audit_events WHERE sequence = 2")
                connection.commit()
            finally:
                connection.close()
            with self.assertRaisesRegex(IntegrityError, "possible truncation"):
                truncated_store.verify(require_complete=False)

            # An attacker able to edit both the rows and SQLite's local counter
            # can erase the whole local history. The externally retained
            # checkpoint is what detects that rollback.
            connection = sqlite3.connect(truncated_path)
            try:
                connection.execute("DELETE FROM audit_events")
                connection.execute(
                    "DELETE FROM sqlite_sequence WHERE name = 'audit_events'"
                )
                connection.commit()
            finally:
                connection.close()
            with self.assertRaisesRegex(IntegrityError, "event count mismatch"):
                truncated_store.verify(
                    require_complete=False,
                    expected_event_count=checkpoint.event_count,
                    expected_head_sha256=checkpoint.head_sha256,
                )

    def test_deleted_ledger_identity_is_not_silently_regenerated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit.sqlite3"
            AuditStore(path)
            connection = sqlite3.connect(path)
            try:
                connection.execute(
                    "DELETE FROM audit_metadata WHERE key = 'ledger_id'"
                )
                connection.commit()
            finally:
                connection.close()

            with self.assertRaisesRegex(IntegrityError, "identifier is missing"):
                AuditStore(path)

            request, report = assessment_pair()
            v2_path = Path(directory) / "v2-audit.sqlite3"
            v2_store = AuditStore(v2_path)
            run = v2_store.append_assessment_intent(request)
            v2_store.append_assessment_completed(run, report)
            connection = sqlite3.connect(v2_path)
            try:
                connection.execute("DROP TABLE audit_metadata")
                connection.commit()
            finally:
                connection.close()

            with self.assertRaisesRegex(IntegrityError, "no readable metadata"):
                v2_store.verify()
            with self.assertRaisesRegex(IntegrityError, "without their ledger metadata"):
                AuditStore(v2_path)

    def test_intent_exposes_release_identity_and_can_be_filtered(self) -> None:
        request = assessment_request()
        expected_instance = sha256_bytes(canonical_json_bytes(request.release))
        with tempfile.TemporaryDirectory() as directory:
            store = AuditStore(Path(directory) / "audit.sqlite3")
            run = store.append_assessment_intent(request)
            store.append_assessment_failed(run, "test_terminal")

            self.assertEqual(run.release_id, request.release.release_id)
            self.assertEqual(run.release_instance_sha256, expected_instance)
            with sqlite3.connect(store.path) as connection:
                payload_json, hash_format = connection.execute(
                    """
                    SELECT payload_json, hash_format
                    FROM audit_events WHERE sequence = 1
                    """
                ).fetchone()
            payload = json.loads(payload_json)
            self.assertEqual(payload["release_id"], request.release.release_id)
            self.assertEqual(
                payload["release_instance_sha256"], expected_instance
            )
            self.assertEqual(hash_format, _AUDIT_EVENT_HASH_FORMAT)

            verified = store.verify(expected_release_id=request.release.release_id)
            self.assertEqual(verified.release_ids, (request.release.release_id,))
            self.assertEqual(
                verified.release_instance_sha256s, (expected_instance,)
            )
            with self.assertRaisesRegex(IntegrityError, "expected release"):
                store.verify(expected_release_id="different-release")

    def test_optimization_intent_exposes_candidate_instance_identity(self) -> None:
        request = OptimizationRequest.model_validate_json(
            (ROOT / "examples" / "optimization-request.json").read_text()
        )
        expected_instance = sha256_bytes(canonical_json_bytes(request))
        active = set(request.portfolio_registry.active_release_ids)
        candidate_ids = {
            release_id
            for configuration in request.configurations
            for release_id in configuration.portfolio.registered_release_ids
            if release_id not in active
        }
        self.assertEqual(len(candidate_ids), 1)
        expected_release_id = next(iter(candidate_ids))

        with tempfile.TemporaryDirectory() as directory:
            store = AuditStore(Path(directory) / "audit.sqlite3")
            run = store.append_optimization_intent(request)
            store.append_optimization_failed(run, "test_terminal")
            verified = store.verify(expected_release_id=expected_release_id)

            self.assertEqual(run.release_id, expected_release_id)
            self.assertEqual(run.release_instance_sha256, expected_instance)
            self.assertEqual(run.request_sha256, expected_instance)
            self.assertEqual(verified.release_ids, (expected_release_id,))
            self.assertEqual(
                verified.release_instance_sha256s, (expected_instance,)
            )

    def test_domain_hash_binds_ledger_and_rejects_metadata_tampering(self) -> None:
        request = assessment_request()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit.sqlite3"
            store = AuditStore(path)
            run = store.append_assessment_intent(request)
            store.append_assessment_failed(run, "test_terminal")
            verified = store.verify()

            with sqlite3.connect(path) as connection:
                row = connection.execute(
                    """
                    SELECT occurred_at, event_type, assessment_id, payload_json,
                           previous_hash
                    FROM audit_events WHERE sequence = 1
                    """
                ).fetchone()
            other_ledger_id = uuid.uuid4()
            original_material = _event_material_v2(verified.ledger_id, *row)
            other_material = _event_material_v2(other_ledger_id, *row)
            self.assertNotEqual(
                sha256_bytes(original_material), sha256_bytes(other_material)
            )

            with sqlite3.connect(path) as connection:
                connection.execute(
                    "UPDATE audit_metadata SET value = ? WHERE key = 'ledger_id'",
                    (str(other_ledger_id),),
                )
                connection.commit()
            with self.assertRaisesRegex(IntegrityError, "hash mismatch"):
                store.verify(expected_ledger_id=other_ledger_id)

    def test_spliced_events_and_fresh_ledger_impersonation_fail(self) -> None:
        request = assessment_request()
        with tempfile.TemporaryDirectory() as directory:
            source = AuditStore(Path(directory) / "source.sqlite3")
            source_run = source.append_assessment_intent(request)
            source.append_assessment_failed(source_run, "source_terminal")
            source_verification = source.verify()

            target = AuditStore(Path(directory) / "target.sqlite3")
            target_verification = target.verify()
            self.assertNotEqual(
                source_verification.ledger_id, target_verification.ledger_id
            )
            with sqlite3.connect(source.path) as source_connection:
                source_rows = source_connection.execute(
                    """
                    SELECT sequence, occurred_at, event_type, assessment_id,
                           payload_json, previous_hash, event_hash, hash_format
                    FROM audit_events ORDER BY sequence
                    """
                ).fetchall()
            with sqlite3.connect(target.path) as target_connection:
                target_connection.executemany(
                    """
                    INSERT INTO audit_events
                    (sequence, occurred_at, event_type, assessment_id, payload_json,
                     previous_hash, event_hash, hash_format)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    source_rows,
                )
                target_connection.commit()
            with self.assertRaisesRegex(IntegrityError, "hash mismatch"):
                target.verify(expected_ledger_id=target_verification.ledger_id)

            fresh = AuditStore(Path(directory) / "fresh.sqlite3")
            fresh_run = fresh.append_assessment_intent(request)
            fresh.append_assessment_failed(fresh_run, "fresh_terminal")
            fresh_verification = fresh.verify(
                expected_release_id=request.release.release_id
            )
            self.assertNotEqual(
                source_verification.head_sha256, fresh_verification.head_sha256
            )
            with self.assertRaisesRegex(IntegrityError, "expected ledger"):
                fresh.verify(expected_ledger_id=source_verification.ledger_id)

    def test_legacy_completion_only_rows_remain_readable(self) -> None:
        _, report = assessment_pair()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit.sqlite3"
            payload_json = canonical_json_bytes(report).decode("utf-8")
            occurred_at = "2025-01-01T00:00:00+00:00"
            digest = sha256_bytes(
                _event_material(
                    occurred_at,
                    "assessment_report",
                    report.assessment_id,
                    payload_json,
                    GENESIS,
                )
            )
            connection = sqlite3.connect(path)
            try:
                connection.execute(
                    """
                    CREATE TABLE audit_events (
                        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                        occurred_at TEXT NOT NULL,
                        event_type TEXT NOT NULL,
                        assessment_id TEXT NOT NULL,
                        payload_json TEXT NOT NULL,
                        previous_hash TEXT NOT NULL,
                        event_hash TEXT NOT NULL UNIQUE
                    )
                    """
                )
                connection.execute(
                    """
                    INSERT INTO audit_events
                    (sequence, occurred_at, event_type, assessment_id, payload_json,
                     previous_hash, event_hash)
                    VALUES (1, ?, 'assessment_report', ?, ?, ?, ?)
                    """,
                    (
                        occurred_at,
                        report.assessment_id,
                        payload_json,
                        GENESIS,
                        digest,
                    ),
                )
                connection.commit()
            finally:
                connection.close()

            store = AuditStore(path)
            with self.assertRaisesRegex(IntegrityError, "legacy event hash"):
                store.verify()
            verified = store.verify(
                allow_legacy_hashes=True,
                expected_event_count=1,
                expected_head_sha256=digest,
            )

            self.assertEqual(
                store.verify_chain(allow_legacy_hashes=True),
                1,
            )
            self.assertEqual(verified.head_sha256, digest)
            self.assertEqual(verified.legacy_event_count, 1)
            self.assertEqual(verified.legacy_hash_event_count, 1)
            self.assertEqual(verified.domain_separated_hash_event_count, 0)
            self.assertEqual(verified.intent_count, 0)
            self.assertEqual(verified.redacted_failure_diagnostic_count, 0)
            self.assertEqual(verified.plaintext_failure_diagnostic_count, 0)
            self.assertEqual(verified.diagnostic_degradations, ())
            self.assertEqual(verified.head_sha256, digest)
            self.assertNotEqual(verified.head_sha256, GENESIS)

            connection = sqlite3.connect(store.path)
            try:
                connection.execute("DROP TABLE audit_metadata")
                connection.commit()
            finally:
                connection.close()
            migrated = AuditStore(store.path)
            with self.assertRaisesRegex(IntegrityError, "legacy event hash"):
                migrated.verify_chain()
            self.assertEqual(
                migrated.verify_chain(allow_legacy_hashes=True),
                1,
            )


if __name__ == "__main__":
    unittest.main()
