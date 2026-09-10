"""Regressions for the preserved September lifecycle/integrity counterexamples."""
from __future__ import annotations

from contextlib import closing
from datetime import timedelta
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from pydantic import ValidationError

from model_release_assurance.audit import AuditStore
from model_release_assurance.errors import IntegrityError
from model_release_assurance.integrity import (
    canonical_json_bytes, generate_ed25519_keypair, sha256_bytes,
    sha256_file, sign_canonical, signer_key_id,
)
from model_release_assurance.models import AssessmentReport, OverallVerdict
from model_release_assurance.release_protocol import (
    ReleaseProtocolArtifactKind as Kind,
    ReleaseProtocolRun,
    ReleaseProtocolState as State,
    ReleaseProtocolVerification,
    ReleaseProtocolVerificationProfile as Profile,
    _verify_report_artifact,
    release_protocol_artifact_signature_payload,
    release_protocol_event_sha256,
    release_protocol_event_signature_payload,
    sign_release_protocol_artifact,
    sign_release_protocol_event,
    verify_release_protocol_run,
)

import test_audit_v2 as audit_fixtures
import test_release_protocol as lifecycle_fixtures
import test_release_protocol_verification_metadata as metadata_fixtures


class LifecycleCounterproofRegressions(unittest.TestCase):
    def registered(self, directory: Path):
        fixture = metadata_fixtures.ReleaseProtocolVerificationMetadataTests()
        run, private, trust = fixture.build_registered_run(directory, Profile.AUTHENTICATED)
        return run, private, trust, fixture.verification_time

    def verify(self, run, directory, trust, as_of):
        return verify_release_protocol_run(
            run, directory, as_of=as_of, trusted_public_keys=trust,
            required_profile=Profile.AUTHENTICATED,
        )

    def test_unsigned_population_substitution_is_rejected(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary)
            run, _keys, trust, when = self.registered(path)
            self.assertTrue(self.verify(run, path, trust, when).valid)
            changed = run.model_copy(update={"population_scope_sha256s": {"unrelated": "f" * 64}})
            result = self.verify(changed, path, trust, when)
            self.assertFalse(result.valid)
            self.assertFalse(result.authenticated_signatures_verified)
            self.assertTrue(any("signature verification failed" in reason for reason in result.reasons))

    def test_actor_declarations_are_bound_but_not_claimed_independently_verified(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary)
            run, _keys, trust, when = self.registered(path)
            changed = run.model_copy(update={"actors": tuple(
                actor.model_copy(update={"organization": "unapproved replacement"})
                for actor in run.actors
            )})
            self.assertFalse(self.verify(changed, path, trust, when).valid)

    def test_version_two_payloads_bind_every_immutable_context_field(self):
        with TemporaryDirectory() as temporary:
            run, _keys, _trust, _when = self.registered(Path(temporary))
            event = run.events[0]
            payloads = (
                release_protocol_event_signature_payload(run, event),
                release_protocol_artifact_signature_payload(run, event, event.artifacts[0]),
            )
            for payload in payloads:
                self.assertTrue(payload["domain"].endswith(":v2"))
                for key in (
                    "release_id", "release_instance_sha256", "artifact_sha256",
                    "interface_sha256", "policy_sha256", "population_scope_sha256s",
                    "registered_portfolio_head_sha256", "registered_portfolio_sequence",
                ):
                    self.assertEqual(payload[key], getattr(run, key))
                self.assertEqual(payload["actors"], [actor.model_dump(mode="json") for actor in run.actors])

    def test_legacy_version_and_profile_require_explicit_migration(self):
        with TemporaryDirectory() as temporary:
            run, _keys, _trust, _when = self.registered(Path(temporary))
            raw = run.model_dump(mode="json")
            for changes in ({"schema_version": "1.1"}, {"verification_profile": "authenticated_v1"}):
                with self.assertRaises(ValidationError):
                    ReleaseProtocolRun.model_validate(raw | changes)
            bypassed = run.model_copy(update={"schema_version": "1.1"})
            with self.assertRaisesRegex(IntegrityError, "legacy signatures"):
                release_protocol_event_signature_payload(bypassed, bypassed.events[0])

    def test_future_event_is_not_replayed_as_present_state(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary)
            run, _keys, trust, _when = self.registered(path)
            at = run.events[0].occurred_at
            self.assertTrue(self.verify(run, path, trust, at).valid)
            result = self.verify(run, path, trust, at - timedelta(microseconds=1))
            self.assertFalse(result.valid)
            self.assertEqual(result.final_state, State.DRAFT)
            self.assertFalse(result.authorization_recorded)
            self.assertFalse(result.deployment_recorded)
            self.assertTrue(any("after the verification time" in reason for reason in result.reasons))

    def test_legacy_domain_signature_cannot_be_relabelled_as_current(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary)
            run, keys, trust, when = self.registered(path)
            event = run.events[0]
            legacy = release_protocol_event_signature_payload(run, event) | {
                "domain": "MRAP/1.0:event-signature:v1"
            }
            _key_id, signature = sign_canonical(legacy, keys[event.actor_id])
            event = event.model_copy(update={"signature": event.signature.model_copy(update={"signature_b64": signature})})
            changed = run.model_copy(update={"events": (event,)})
            self.assertFalse(self.verify(changed, path, trust, when).valid)

    def test_active_replay_never_claims_production_issuance_or_activation(self):
        fixture = lifecycle_fixtures.ReleaseProtocolTests()
        fixture.setUp()
        result = fixture.replay(fixture.happy_run())
        self.assertTrue(result.valid, result.reasons)
        self.assertTrue(result.authorization_recorded)
        self.assertTrue(result.deployment_recorded)
        self.assertFalse(result.authorization_issued)
        self.assertFalse(result.deployment_active)
        self.assertEqual(result.schema_version, "3.0")
        for field in ("authorization_issued", "deployment_active"):
            with self.assertRaises(ValidationError):
                ReleaseProtocolVerification.model_validate(result.model_dump(mode="json") | {field: True})

    def assessment_run(self, directory: Path):
        request, report = audit_fixtures.assessment_pair()
        fixture = lifecycle_fixtures.ReleaseProtocolTests()
        fixture.setUp()
        fixture.base_time = report.created_at
        base = fixture.happy_run()
        events = []
        for event in base.events[:4]:
            artifacts = []
            for artifact in event.artifacts:
                path = directory / artifact.path
                if artifact.kind is Kind.POLICY_SNAPSHOT:
                    policy = audit_fixtures.ROOT / "examples" / request.policy.policy_path
                    path.write_bytes(policy.read_bytes())
                elif artifact.kind is Kind.RELEASE_INSTANCE:
                    path.write_bytes(canonical_json_bytes(request.release))
                elif artifact.kind is Kind.ASSESSMENT_REPORT:
                    path.write_bytes(canonical_json_bytes(report))
                else:
                    path.write_text('{"test_declaration":true}', encoding="utf-8")
                artifacts.append(artifact.model_copy(update={"sha256": sha256_file(path)}))
            events.append(event.model_copy(update={"artifacts": tuple(artifacts)}))
        run = base.model_copy(update={
            "events": tuple(events), "claimed_state": State.ASSESSED,
            "release_id": report.release_id,
            "release_instance_sha256": report.release_contract_sha256,
            "artifact_sha256": report.artifact_sha256,
            "interface_sha256": sha256_bytes(canonical_json_bytes(report.release_interface)),
            "policy_sha256": report.policy_sha256,
            "population_scope_sha256s": report.population_scope_sha256s,
            "verification_profile": Profile.AUTHENTICATED,
        })
        actors, private, trust = [], {}, {}
        for index, actor in enumerate(run.actors):
            secret, public = directory / f"key-{index}.private.pem", directory / f"key-{index}.public.pem"
            generate_ed25519_keypair(secret, public)
            kid = signer_key_id(serialization.load_pem_public_key(public.read_bytes()))
            actors.append(actor.model_copy(update={"key_id": kid}))
            private[actor.actor_id], trust[kid] = secret, public
        run = run.model_copy(update={"actors": tuple(actors)})
        return self.resign(run, private), private, trust, report

    @staticmethod
    def resign(run, private):
        previous, events = None, []
        for event in run.events:
            event = event.model_copy(update={"previous_event_sha256": previous, "signature": None})
            artifacts = tuple(sign_release_protocol_artifact(run, event, artifact.model_copy(update={"signature": None}), private[artifact.producer_actor_id]) for artifact in event.artifacts)
            event = sign_release_protocol_event(run, event.model_copy(update={"artifacts": artifacts}), private[event.actor_id])
            events.append(event)
            previous = release_protocol_event_sha256(event)
        return run.model_copy(update={"events": tuple(events)})

    def replace_report(self, run, directory, private, payload):
        events = list(run.events)
        artifact = events[-1].artifacts[0]
        (directory / artifact.path).write_bytes(payload)
        artifact = artifact.model_copy(update={"sha256": sha256_file(directory / artifact.path)})
        events[-1] = events[-1].model_copy(update={"artifacts": (artifact,)})
        return self.resign(run.model_copy(update={"events": tuple(events)}), private)

    def test_known_assessment_file_contract_and_chronology_are_replayed(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary)
            run, private, trust, report = self.assessment_run(path)
            when = run.events[-1].occurred_at + timedelta(seconds=1)
            self.assertTrue(self.verify(run, path, trust, when).valid)
            future = report.model_copy(update={"created_at": when})
            changed = self.replace_report(run, path, private, canonical_json_bytes(future))
            result = self.verify(changed, path, trust, when)
            self.assertFalse(result.valid)
            self.assertTrue(any("created after the event" in reason for reason in result.reasons))
            malformed = self.replace_report(run, path, private, b'{"not_an_assessment":true}')
            self.assertFalse(self.verify(malformed, path, trust, when).valid)

    def test_freshly_resigned_wrong_population_or_verdict_cannot_override_report(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary)
            run, private, trust, _report = self.assessment_run(path)
            when = run.events[-1].occurred_at + timedelta(seconds=1)
            changed = self.resign(run.model_copy(update={"population_scope_sha256s": {"other": "f" * 64}}), private)
            result = self.verify(changed, path, trust, when)
            self.assertFalse(result.valid)
            self.assertTrue(result.authenticated_signatures_verified)
            events = list(run.events)
            events[-1] = events[-1].model_copy(update={"assessment_verdict": OverallVerdict.BLOCK})
            changed = self.resign(run.model_copy(update={"events": tuple(events)}), private)
            self.assertFalse(self.verify(changed, path, trust, when).valid)

    def test_expired_policy_report_is_not_recorded_as_current_evidence(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary)
            run, private, trust, report = self.assessment_run(path)
            expired = report.model_copy(update={"policy_expires_at": run.events[-1].occurred_at})
            changed = self.replace_report(run, path, private, canonical_json_bytes(expired))
            result = self.verify(changed, path, trust, run.events[-1].occurred_at)
            self.assertFalse(result.valid)
            self.assertTrue(any("expired at its recording event" in reason for reason in result.reasons))

    def test_freshly_resigned_partial_report_cannot_omit_policy_required_threat(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary)
            run, private, trust, report = self.assessment_run(path)
            when = run.events[-1].occurred_at + timedelta(seconds=1)
            self.assertTrue(self.verify(run, path, trust, when).valid)
            self.assertGreater(len(report.decisions), 1)
            omitted = report.decisions[-1].threat_id
            partial = report.model_copy(update={
                "decisions": tuple(decision for decision in report.decisions if decision.threat_id != omitted),
                "evidence": tuple(record for record in report.evidence if record.threat_id != omitted),
            })
            # This is internally consistent as a report. Only its authenticated
            # policy predecessor exposes the omitted mandatory threat.
            AssessmentReport.model_validate_json(canonical_json_bytes(partial))
            changed = self.replace_report(run, path, private, canonical_json_bytes(partial))
            result = self.verify(changed, path, trust, when)
            self.assertFalse(result.valid)
            self.assertTrue(result.authenticated_signatures_verified)
            self.assertTrue(any("policy threat roster mismatch" in reason for reason in result.reasons))

    def test_optimization_report_binds_its_predecessor_and_selected_interface(self):
        request, report = audit_fixtures.optimization_pair()
        reference = next(
            configuration.assessment for configuration in request.configurations
            if configuration.configuration_id == report.selected_configuration_id
        )
        report_path = audit_fixtures.ROOT / "examples" / reference.report_path
        assessment = AssessmentReport.model_validate_json(report_path.read_text(encoding="utf-8"))
        fixture = lifecycle_fixtures.ReleaseProtocolTests()
        fixture.setUp()
        base = fixture.happy_run()
        run = base.model_copy(update={
            "release_id": assessment.release_id,
            "policy_sha256": report.policy_sha256,
            "registered_portfolio_head_sha256": report.portfolio_registry_head_sha256,
            "registered_portfolio_sequence": report.portfolio_registry_sequence,
            "artifact_sha256": report.selected_release_artifact_sha256,
            "interface_sha256": report.selected_release_interface_sha256,
        })
        event = run.events[4].model_copy(update={
            "occurred_at": report.created_at + timedelta(seconds=1),
            "optimization_outcome": report.outcome,
            "selected_configuration_id": report.selected_configuration_id,
        })
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "optimization.json"
            path.write_bytes(canonical_json_bytes(report))
            artifact = event.artifacts[0].model_copy(update={"sha256": sha256_file(path)})
            prior = (assessment, sha256_file(report_path))
            self.assertEqual(_verify_report_artifact(run, event, artifact, path, assessment=prior), report)
            with self.assertRaisesRegex(IntegrityError, "assessment or selected release"):
                _verify_report_artifact(run, event, artifact, path, assessment=(assessment, "f" * 64))
            with self.assertRaisesRegex(IntegrityError, "assessment or selected release"):
                _verify_report_artifact(run.model_copy(update={"interface_sha256": "f" * 64}), event, artifact, path, assessment=prior)


class AuditAppendCounterproofRegressions(unittest.TestCase):
    def test_corrupted_prefix_rejects_append_before_any_new_event(self):
        request = audit_fixtures.assessment_request()
        with TemporaryDirectory() as temporary:
            store = AuditStore(Path(temporary) / "audit.sqlite")
            run = store.append_assessment_intent(request)
            store.append_assessment_failed(run, "test-terminal")
            with closing(sqlite3.connect(store.path)) as connection:
                connection.execute("UPDATE audit_events SET event_hash=? WHERE sequence=1", ("f" * 64,))
                connection.commit()
                before = connection.execute("SELECT * FROM audit_events ORDER BY sequence").fetchall()
            with self.assertRaisesRegex(IntegrityError, "hash mismatch"):
                store.append_assessment_intent(request)
            with closing(sqlite3.connect(store.path)) as connection:
                self.assertEqual(before, connection.execute("SELECT * FROM audit_events ORDER BY sequence").fetchall())
                self.assertEqual(connection.execute("SELECT seq FROM sqlite_sequence WHERE name='audit_events'").fetchone()[0], 2)

    def test_prefix_verification_holds_writer_lock_and_allows_open_workers(self):
        request = audit_fixtures.assessment_request()
        with TemporaryDirectory() as temporary:
            store = AuditStore(Path(temporary) / "audit.sqlite")
            first = store.append_assessment_intent(request)
            original_verify = store.verify
            checked = []
            def verify_under_lock(*args, **kwargs):
                with closing(sqlite3.connect(store.path, timeout=0)) as competitor:
                    with self.assertRaisesRegex(sqlite3.OperationalError, "locked"):
                        competitor.execute("BEGIN IMMEDIATE")
                checked.append(True)
                self.assertFalse(kwargs["require_complete"])
                return original_verify(*args, **kwargs)
            with patch.object(store, "verify", side_effect=verify_under_lock):
                second = store.append_assessment_intent(request)
            self.assertEqual(len(checked), 1)
            store.append_assessment_failed(first, "first-done")
            store.append_assessment_failed(second, "second-done")
            self.assertTrue(store.verify(require_events=True).complete)

    def test_independent_checkpoint_still_needed_against_repaired_truncation(self):
        request = audit_fixtures.assessment_request()
        with TemporaryDirectory() as temporary:
            store = AuditStore(Path(temporary) / "audit.sqlite")
            first = store.append_assessment_intent(request)
            store.append_assessment_failed(first, "first-done")
            second = store.append_assessment_intent(request)
            store.append_assessment_failed(second, "second-done")
            checkpoint = store.export_checkpoint()
            with closing(sqlite3.connect(store.path)) as connection:
                connection.execute("DELETE FROM audit_events WHERE sequence>2")
                connection.execute("UPDATE sqlite_sequence SET seq=2 WHERE name='audit_events'")
                connection.commit()
            self.assertTrue(store.verify(require_events=True).complete)
            with self.assertRaisesRegex(IntegrityError, "head mismatch"):
                store.verify(expected_head_sha256=checkpoint.head_sha256)


if __name__ == "__main__":
    unittest.main()
