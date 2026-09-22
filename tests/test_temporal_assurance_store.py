"""Lifecycle and accounting tests of the local temporal broker trust boundary."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from model_release_assurance.temporal_assurance import AssuranceError, AssuranceStore
from model_release_assurance.temporal_assurance import store as store_module


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


class TemporalAssuranceStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "ledger.sqlite"
        self.store = AssuranceStore(self.path, budget_micros=2_000_000, scope_digest=sha("fixed roster attribute"))
        self.evidence = self.store.register_evidence(b"trusted adapter receipt v1", expires_at=100)
        self.store.register_authority("agency-reviewer", expires_at=100)
        self.cache("cache-a", ["p1", "p2", "p3"])
        self.model("model-a", "cache-a", ["p1", "p2"])

    def cache(self, name, records, epsilon=1_000_000, *, version="v1", expiry=100, evidence=None):
        self.store.register_cache(name, cache_digest=sha(name), epsilon_micros=epsilon,
            record_ids=records, evidence_digest=evidence or self.evidence, expires_at=expiry,
            attribute_version=version)

    def model(self, name, cache, records, *, version="v1", expiry=100, scoring="model_only",
              serving=(), serving_cache=None, evidence=None, dataset=None):
        dataset = dataset or sha(name + " source")
        self.store.register_dataset(dataset, record_ids=records, evidence_digest=evidence or self.evidence,
                                    expires_at=expiry, attribute_version=version)
        self.store.register_model(name, cache_id=cache, dataset_digest=dataset, record_ids=records,
            artifact_bytes=("recipient sanitized package " + name).encode(),
            evidence_digest=evidence or self.evidence, expires_at=expiry, scoring=scoring,
            serving_records=serving, serving_cache_id=serving_cache)

    def prepare(self, request="r1", model="model-a", *, now=1, revision=None):
        return self.store.prepare(request, model, expected_revision=self.store.revision() if revision is None else revision,
                                  authority_id="agency-reviewer", now=now)

    def release(self, request="r1", model="model-a"):
        self.prepare(request, model)
        return self.store.commit(request, now=2)

    def assertCode(self, code, call):
        with self.assertRaises(AssuranceError) as error:
            call()
        self.assertEqual(error.exception.code, code)

    def test_exact_bytes_only_after_commit(self):
        manifest = self.prepare()
        self.assertEqual(self.store.ledger()["charges"], [])
        self.assertCode("not_committed", lambda: self.store.download("r1", authority_id="agency-reviewer", now=2))
        receipt = self.store.commit("r1", now=2)
        actual = self.store.download("r1", authority_id="agency-reviewer", now=3)
        self.assertEqual(actual, b"recipient sanitized package model-a")
        self.assertEqual(receipt["artifact_digest"], hashlib.sha256(actual).hexdigest())
        canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        self.assertEqual(receipt["manifest_digest"], hashlib.sha256(canonical).hexdigest())
        self.assertNotIn(b"scope_digest", actual)

    def test_retry_parameter_binding_and_exactly_once_charge(self):
        manifest = self.prepare()
        receipt = self.store.commit("r1", now=2)
        self.assertEqual(self.prepare(revision=0, now=3), manifest)
        self.assertEqual(self.store.commit("r1", now=3), receipt)
        self.assertEqual(len(self.store.ledger()["charges"]), 2)
        self.assertEqual(self.store.revision(), 1)
        self.assertCode("idempotency_conflict", lambda: self.prepare(revision=1))
        self.model("model-b", "cache-a", ["p1", "p2"])
        self.assertCode("idempotency_conflict", lambda: self.prepare(model="model-b", revision=0))

    def test_different_architectures_same_cache_postprocess_without_charge(self):
        self.release()
        self.model("different-transformer", "cache-a", ["p1", "p2"])
        receipt = self.release("r2", "different-transformer")
        self.assertEqual(receipt["new_unit_charges"], 0)
        self.assertEqual(self.store.ledger()["spent_micros"], {"p1": 1_000_000, "p2": 1_000_000})

    def test_overlap_union_and_disjoint_parallel_accounting(self):
        self.release()
        self.cache("cache-b", ["p2", "p3"])
        self.model("other-tree", "cache-b", ["p2", "p3"])
        self.release("r2", "other-tree")
        self.assertEqual(self.store.ledger()["spent_micros"], {"p1": 1_000_000, "p2": 2_000_000, "p3": 1_000_000})

    def test_new_dataset_name_does_not_reset_spending(self):
        self.release()
        self.cache("renewal-1", ["p1"], epsilon=1_000_000)
        self.model("renamed-source-model", "renewal-1", ["p1"])
        self.release("r2", "renamed-source-model")
        self.cache("renewal-2", ["p1"], epsilon=1)
        self.model("third-model", "renewal-2", ["p1"])
        self.assertCode("budget_exceeded", lambda: self.prepare("r3", "third-model"))
        self.assertEqual(self.store.revision(), 2)

    def test_cache_alias_conservatively_adds_cost(self):
        self.release()
        self.store.register_cache("alias", cache_digest=sha("cache-a"), epsilon_micros=1_000_000,
            record_ids=["p1"], evidence_digest=self.evidence, expires_at=100)
        self.model("alias-model", "alias", ["p1"])
        self.release("r2", "alias-model")
        self.assertEqual(self.store.ledger()["spent_micros"]["p1"], 2_000_000)

    def test_threshold_equality_allowed_one_micro_over_blocked(self):
        self.cache("full-cap", ["p3"], epsilon=2_000_000)
        self.model("full-model", "full-cap", ["p3"])
        self.release("full", "full-model")
        self.cache("one-more", ["p3"], epsilon=1)
        self.model("one-more-model", "one-more", ["p3"])
        self.assertCode("budget_exceeded", lambda: self.prepare("over", "one-more-model"))

    def test_integer_budget_rejects_float_bool_and_negative(self):
        for value in (1.0, True, -1):
            self.assertCode("invalid_integer", lambda value=value: AssuranceStore(self.path, budget_micros=value, scope_digest=sha("x")))

    def test_cached_serving_charges_union_including_nonmembers(self):
        self.model("scored", "cache-a", ["p1", "p2"], scoring="cached", serving=["p2", "p3"], serving_cache="cache-a")
        manifest = self.prepare(model="scored")
        self.assertEqual(manifest["covered_units"], 3)
        self.assertEqual(manifest["serving_units"], 2)
        self.store.commit("r1", now=2)
        self.assertEqual(self.store.ledger()["spent_micros"], {"p1": 1_000_000, "p2": 1_000_000, "p3": 1_000_000})

    def test_fresh_serving_charges_both_events_same_request(self):
        self.cache("score-cache", ["p1", "p3"])
        self.model("fresh", "cache-a", ["p1", "p2"], scoring="fresh", serving=["p1", "p3"], serving_cache="score-cache")
        self.release(model="fresh")
        self.assertEqual(self.store.ledger()["spent_micros"], {"p1": 2_000_000, "p2": 1_000_000, "p3": 1_000_000})

    def test_one_request_cross_cache_sum_over_cap_is_denied_atomically(self):
        self.cache("score-cache", ["p1"], epsilon=1_000_001)
        self.model("fresh", "cache-a", ["p1"], scoring="fresh", serving=["p1"], serving_cache="score-cache")
        self.assertCode("budget_exceeded", lambda: self.prepare(model="fresh"))
        self.assertEqual(self.store.ledger()["charges"], [])

    def test_fresh_scores_reused_are_counted_once_and_renewed_scores_add(self):
        self.cache("score-cache", ["p1"])
        for name in ("first", "second"):
            self.model(name, "cache-a", ["p1"], scoring="fresh", serving=["p1"], serving_cache="score-cache")
        self.release(model="first")
        receipt = self.release("r2", "second")
        self.assertEqual(receipt["new_unit_charges"], 0)
        self.cache("next-score-cache", ["p1"], epsilon=1)
        self.model("third", "cache-a", ["p1"], scoring="fresh", serving=["p1"], serving_cache="next-score-cache")
        self.assertCode("budget_exceeded", lambda: self.prepare("r3", "third"))

    def test_raw_unknown_and_underspecified_scoring_denied(self):
        for mode in ("raw", "unrecognized", "cached", "fresh"):
            self.assertCode("serving_denied", lambda mode=mode: self.model("bad-" + mode, "cache-a", ["p1"], scoring=mode))
        self.assertCode("serving_denied", lambda: self.model("wrong-reuse", "cache-a", ["p1"],
                        scoring="fresh", serving=["p1"], serving_cache="cache-a"))

    def test_registered_serving_contract_cannot_be_downgraded(self):
        self.model("scored", "cache-a", ["p1"], scoring="cached", serving=["p3"], serving_cache="cache-a")
        with self.assertRaises(TypeError):
            self.store.prepare("r1", "scored", expected_revision=0, authority_id="agency-reviewer", now=1, scoring="model_only")
        self.assertEqual(self.prepare(model="scored")["scoring"], "cached")

    def test_new_attribute_version_same_unit_adds_epsilon(self):
        self.release()
        self.cache("v2-cache", ["p1"], version="v2")
        self.model("v2-model", "v2-cache", ["p1"], version="v2")
        self.release("v2", "v2-model")
        self.assertEqual(self.store.ledger()["spent_micros"]["p1"], 2_000_000)

    def test_version_mismatch_rejected(self):
        self.assertCode("version_mismatch", lambda: self.model("bad-version", "cache-a", ["p1"], version="v2"))
        self.cache("v2-score", ["p1"], version="v2")
        self.assertCode("version_mismatch", lambda: self.model("bad-score-version", "cache-a", ["p1"],
            scoring="fresh", serving=["p1"], serving_cache="v2-score"))

    def test_cache_and_model_binding_immutable(self):
        self.assertCode("immutable_binding", lambda: self.cache("cache-a", ["p1", "p2", "p3"], epsilon=999))
        self.assertCode("immutable_binding", lambda: self.store.register_cache("cache-a", cache_digest=sha("changed bytes"),
            epsilon_micros=1_000_000, record_ids=["p1", "p2", "p3"], evidence_digest=self.evidence, expires_at=100))
        self.assertCode("immutable_binding", lambda: self.model("model-a", "cache-a", ["p1", "p2"], expiry=101))

    def test_missing_provenance_and_scope_fail_closed(self):
        self.assertCode("missing_evidence", lambda: self.store.register_dataset(sha("missing"), record_ids=["p1"],
            evidence_digest=sha("absent"), expires_at=100))
        self.assertCode("scope_mismatch", lambda: self.store.register_cache("bad", cache_digest=sha("bad"),
            epsilon_micros=1, record_ids=["p1"], evidence_digest=self.evidence, expires_at=100, scope_digest=sha("other")))
        self.assertCode("lineage_mismatch", lambda: self.model("outside", "cache-a", ["p9"]))

    def test_unregistered_serving_unit_denied(self):
        self.assertCode("lineage_mismatch", lambda: self.model("bad", "cache-a", ["p1"],
            scoring="cached", serving=["outside-roster"], serving_cache="cache-a"))

    def test_duplicate_or_noncanonical_unit_keys_denied(self):
        for ids in (["p1", "p1"], [" p1"], ["e\u0301"], [], "p1"):
            with self.assertRaises(AssuranceError):
                self.cache("bad", ids)

    def test_prepare_and_commit_check_current_authority(self):
        self.prepare()
        self.store.revoke_authority("agency-reviewer")
        self.assertCode("authority_inactive", lambda: self.store.commit("r1", now=2))
        self.assertEqual(self.store.ledger()["charges"], [])
        self.assertCode("authority_inactive", lambda: self.prepare("r2"))

    def test_expiry_boundary_and_download_authority(self):
        self.release()
        self.assertCode("authority_inactive", lambda: self.store.download("r1", authority_id="agency-reviewer", now=100))
        self.store.register_authority("other", expires_at=200)
        self.assertCode("authority_mismatch", lambda: self.store.download("r1", authority_id="other", now=2))

    def test_evidence_expiry_between_prepare_commit(self):
        evidence = self.store.register_evidence(b"short-lived", expires_at=2)
        self.model("short-lived", "cache-a", ["p1"], evidence=evidence)
        self.prepare(model="short-lived")
        self.assertCode("evidence_expired", lambda: self.store.commit("r1", now=2))

    def test_evidence_invalidation_blocks_commit_and_download_without_refund(self):
        self.release()
        self.prepare("pending")
        before = self.store.ledger()
        self.store.invalidate_evidence(self.evidence)
        self.assertCode("evidence_invalidated", lambda: self.store.commit("pending", now=3))
        self.assertCode("evidence_invalidated", lambda: self.store.download("r1", authority_id="agency-reviewer", now=3))
        self.assertEqual(self.store.ledger(), before)

    def test_serving_cache_invalidation_is_checked(self):
        evidence = self.store.register_evidence(b"scoring evidence", expires_at=100)
        self.cache("score-cache", ["p1"], evidence=evidence)
        self.model("fresh", "cache-a", ["p1"], scoring="fresh", serving=["p1"], serving_cache="score-cache")
        self.release(model="fresh")
        self.store.invalidate_evidence(evidence)
        self.assertCode("evidence_invalidated", lambda: self.store.download("r1", authority_id="agency-reviewer", now=3))

    def test_revocation_blocks_future_access_not_budget_refund(self):
        self.release()
        before = self.store.ledger()
        self.store.revoke_release("r1")
        self.assertCode("release_revoked", lambda: self.store.download("r1", authority_id="agency-reviewer", now=3))
        self.assertCode("release_revoked", lambda: self.store.commit("r1", now=3))
        self.assertEqual(self.store.ledger(), before)

    def test_stale_preparation_fails_and_new_request_can_retry(self):
        self.prepare("first")
        self.prepare("second")
        self.store.commit("first", now=2)
        self.assertCode("revision_conflict", lambda: self.store.commit("second", now=2))
        self.assertEqual(self.release("retry")["new_unit_charges"], 0)

    def test_exception_during_commit_rolls_back_charge_and_publication(self):
        self.prepare()
        def fail(_):
            raise RuntimeError("simulated interruption after charge writes")
        self.store._after_ledger_write = fail
        with self.assertRaises(RuntimeError):
            self.store.commit("r1", now=2)
        self.assertEqual(self.store.ledger()["charges"], [])
        self.assertEqual(self.store.revision(), 0)
        self.assertCode("not_committed", lambda: self.store.download("r1", authority_id="agency-reviewer", now=3))
        self.store._after_ledger_write = lambda _: None
        self.assertEqual(self.store.commit("r1", now=3)["new_unit_charges"], 2)

    def test_process_crash_recovery_has_no_partial_release(self):
        self.prepare()
        code = """
import os, sys
sys.path.insert(0, sys.argv[3])
from model_release_assurance.temporal_assurance import AssuranceStore
s = AssuranceStore(sys.argv[1], budget_micros=2000000, scope_digest=sys.argv[2])
s._after_ledger_write = lambda db: os._exit(73)
s.commit('r1', now=2)
"""
        process = subprocess.run([sys.executable, "-c", code, str(self.path), self.store.scope_digest,
                                  str(Path(__file__).resolve().parents[1] / "src")], timeout=30, capture_output=True)
        self.assertEqual(process.returncode, 73, process.stderr)
        restored = AssuranceStore(self.path, budget_micros=2_000_000, scope_digest=self.store.scope_digest)
        self.assertEqual(restored.ledger()["charges"], [])
        self.assertEqual(restored.revision(), 0)
        self.assertEqual(restored.commit("r1", now=3)["new_unit_charges"], 2)

    def test_concurrent_distinct_commits_one_revision_winner(self):
        self.prepare("first")
        self.prepare("second")
        barrier = threading.Barrier(2)
        def run(request):
            barrier.wait()
            try:
                return self.store.commit(request, now=2)
            except AssuranceError as error:
                return error.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(run, ["first", "second"]))
        self.assertEqual(sum(isinstance(item, dict) for item in outcomes), 1)
        self.assertEqual(outcomes.count("revision_conflict"), 1)
        self.assertEqual(self.store.ledger()["committed_releases"], 1)

    def test_concurrent_same_request_returns_same_receipt(self):
        self.prepare()
        barrier = threading.Barrier(2)
        def run(_):
            barrier.wait()
            return self.store.commit("r1", now=2)
        with ThreadPoolExecutor(max_workers=2) as pool:
            receipts = list(pool.map(run, range(2)))
        self.assertEqual(receipts[0], receipts[1])
        self.assertEqual(len(self.store.ledger()["charges"]), 2)

    def test_restart_configuration_cannot_increase_cap_or_change_scope(self):
        for budget, scope in [(3_000_000, self.store.scope_digest), (2_000_000, sha("different"))]:
            self.assertCode("configuration_mismatch", lambda budget=budget, scope=scope: AssuranceStore(
                self.path, budget_micros=budget, scope_digest=scope))

    def test_removed_database_not_silently_recreated_by_release(self):
        self.path.unlink()
        self.assertCode("ledger_missing", lambda: self.store.revision())
        self.assertFalse(self.path.exists())

    def test_corrupted_artifact_and_manifest_fail_integrity(self):
        self.release()
        with self.store._transaction() as db:
            db.execute("UPDATE models SET artifact=? WHERE id='model-a'", (b"tampered",))
        self.assertCode("integrity_failure", lambda: self.store.download("r1", authority_id="agency-reviewer", now=3))
        with self.store._transaction() as db:
            db.execute("UPDATE models SET artifact=? WHERE id='model-a'", (b"recipient sanitized package model-a",))
            db.execute("UPDATE requests SET manifest=manifest || ' ' WHERE id='r1'")
        self.assertCode("integrity_failure", lambda: self.store.download("r1", authority_id="agency-reviewer", now=3))

    def test_live_clock_is_read_after_waiting_for_database_lock(self):
        clock_state = {"now": 99, "calls": 0}
        def clock():
            clock_state["calls"] += 1
            return clock_state["now"]
        self.store.clock = clock
        connection_opened = threading.Event()
        original = self.store._connection
        @contextmanager
        def observed_connection():
            with original() as db:
                connection_opened.set()
                yield db
        with ThreadPoolExecutor(max_workers=1) as pool:
            with self.store._transaction():
                self.store._connection = observed_connection
                future = pool.submit(self.store.prepare, "live", "model-a", expected_revision=0,
                                     authority_id="agency-reviewer")
                self.assertTrue(connection_opened.wait(5), "Worker never reached the locked database")
                self.assertEqual(clock_state["calls"], 0)
                clock_state["now"] = 100
            self.assertCode("authority_inactive", future.result)
        self.assertGreater(clock_state["calls"], 0)
        self.assertEqual(self.store.ledger()["charges"], [])

    def test_live_prepare_rechecks_expiry_after_budget_work(self):
        clock_state = {"now": 99}
        self.store.clock = lambda: clock_state["now"]
        original = self.store._charge_plan
        def slow_plan(db, footprints):
            result = original(db, footprints)
            clock_state["now"] = 100
            return result
        self.store._charge_plan = slow_plan
        self.assertCode("authority_inactive", lambda: self.store.prepare("live", "model-a", expected_revision=0,
                                                                        authority_id="agency-reviewer"))
        with self.store._transaction() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM requests WHERE id='live'").fetchone()[0], 0)

    def test_live_commit_expiry_after_ledger_write_rolls_back_publication(self):
        clock_state = {"now": 99}
        self.store.clock = lambda: clock_state["now"]
        self.prepare()
        def advance_clock(_):
            clock_state["now"] = 100
        self.store._after_ledger_write = advance_clock
        self.assertCode("authority_inactive", lambda: self.store.commit("r1"))
        self.assertEqual(self.store.ledger()["charges"], [])
        self.assertEqual(self.store.revision(), 0)
        self.assertCode("not_committed", lambda: self.store.download("r1", authority_id="agency-reviewer"))

    def test_live_commit_rechecks_evidence_expiry_independently_of_authority(self):
        clock_state = {"now": 99}
        self.store.clock = lambda: clock_state["now"]
        self.store.register_authority("long-lived", expires_at=200)
        self.store.prepare("live", "model-a", expected_revision=0, authority_id="long-lived")
        self.store._after_ledger_write = lambda _: clock_state.update(now=100)
        self.assertCode("evidence_expired", lambda: self.store.commit("live"))
        self.assertEqual(self.store.ledger()["charges"], [])

    def test_live_download_rechecks_expiry_after_manifest_hash(self):
        clock_state = {"now": 99}
        self.store.clock = lambda: clock_state["now"]
        self.release()
        original = store_module._hash
        def slow_manifest_hash(payload):
            result = original(payload)
            if b'"request_id":"r1"' in payload:
                clock_state["now"] = 100
            return result
        with mock.patch.object(store_module, "_hash", side_effect=slow_manifest_hash):
            self.assertCode("authority_inactive", lambda: self.store.download("r1", authority_id="agency-reviewer"))

    def test_explicit_time_is_deterministic_simulation_not_wall_time(self):
        self.store.clock = lambda: 1000
        self.release()
        self.assertEqual(self.store.download("r1", authority_id="agency-reviewer", now=3),
                         b"recipient sanitized package model-a")
        self.assertCode("authority_inactive", lambda: self.store.download("r1", authority_id="agency-reviewer"))

    def test_constructor_injected_clock_and_invalid_clock(self):
        clocked = AssuranceStore(self.path, budget_micros=2_000_000, scope_digest=self.store.scope_digest, clock=lambda: 99.9)
        manifest = clocked.prepare("live", "model-a", expected_revision=0, authority_id="agency-reviewer")
        self.assertEqual(manifest["prepared_at"], 99)
        for value in (True, float("inf"), float("nan"), -1.0, "99"):
            clocked.clock = lambda value=value: value
            self.assertCode("invalid_clock", lambda: clocked.commit("live"))


if __name__ == "__main__":
    unittest.main()
