"""Witness records replay real registry rules without upgrading fixture claims."""
from __future__ import annotations

import copy
import json
import unittest

from model_release_assurance.production_registry import contracts as rc
from model_release_assurance.production_registry import store as rs
from model_release_assurance.production_witness import contracts as c
from test_production_registry_contracts import request_fixture, context_fixture, receipt_fixture


def history_fixture(*, committed=False, migrated=False, delivered=False, broker=True, accounts=None):
    """Construct genuine PRD15 bodies; useful to witness store/service tests too."""
    interpreter = object.__new__(rs.RegistryStore)
    interpreter._store_id, interpreter._version = "1" * 32, 2
    state, rows = rs._blank(), []
    def append(kind, payload, now):
        body = {"schema": "mra-fixture-registry-history/v1", "store_id": interpreter.store_id,
                "sequence": state["count"] + 1, "previous_sha256": state["head"],
                "occurred_at": now, "kind": kind, "payload": payload}
        digest = rc.digest(body)
        interpreter._apply(state, body, digest)
        rows.append({"event_sha256": digest, "event": body})
    accounts = accounts or [{"agency_id": "agency", "project_id": "project"}]
    accounts = sorted(accounts, key=lambda row: rc.account_id(**row))
    append("created", {"schema_version": 1 if migrated else 2, "accounts": accounts}, 0)
    if broker:
        append("broker", {"broker_id": "5" * 32, "expected_epoch": 0}, 1000)
    if committed or delivered:
        append("committed", {"request": request_fixture(), "receipt": receipt_fixture()}, 1001)
    if migrated:
        append("migrated", {"from_version": 1, "to_version": 2,
                            "preserved_sha256": rs._core_digest(state)}, 1002)
        if delivered:
            append("broker", {"broker_id": "9" * 32, "expected_epoch": state["epoch"]}, 1003)
    if delivered:
        lease = {"store_id": "1" * 32, "event_id": "8" * 32, "account_id": rc.account_id("agency", "project"),
            "case_id": "case-a", "owner_sha256": "a" * 64, "lease_id": "b" * 32, "generation": 1,
            "broker_id": state["broker_id"], "broker_epoch": state["epoch"], "claimed_at": 1004, "expires_at": 1034}
        append("claimed", {"lease": lease}, 1004)
        append("acknowledged", {"lease": lease, "acknowledgment": interpreter._ack(lease, 1005)}, 1005)
    return {"schema": "mra-fixture-registry-history-snapshot/v1", "store_id": interpreter.store_id,
            "schema_version": state["version"], "broker_epoch": state["epoch"], "broker_id": state["broker_id"],
            "event_sequence": state["count"], "event_head_sha256": state["head"],
            "observed_at": max(1000, state["clock"]), "events": rows, **c.FLAGS}


def pin_fixture():
    return {"schema": "mra-fixture-witness-pin/v1", "witness_id": "c" * 32,
            "namespace_id": rc.account_id("agency", "project"), "registry_id": "1" * 32,
            "revision": 1, "head_sha256": "d" * 64}


def diagnosis_fixture(state="pending"):
    snapshot = history_fixture()
    intent = c.create_intent(snapshot, request_fixture())
    if state != "pending":
        snapshot = history_fixture(committed=True)
    return {"schema": "mra-fixture-witness-diagnosis/v1", "status": "quarantined" if state == "pending" else "consistent",
            "reconciled": state != "pending", "pin": pin_fixture(), "namespace_id": intent["namespace_id"],
            "registry_id": intent["registry_id"], "registry_sequence": snapshot["event_sequence"],
            "registry_head_sha256": snapshot["event_head_sha256"], "registry_epoch": 1,
            "registry_observed_at": snapshot["observed_at"], "pending_intents": int(state == "pending"),
            "committed_intents": int(state == "committed"), "aborted_intents": int(state == "aborted"),
            "quarantine_reasons": ["pending_intent"] if state == "pending" else [],
            "intents": [{"intent": intent, "state": state, "receipt": receipt_fixture() if state == "committed" else None}],
            **c.FLAGS}


def rehash(snapshot):
    """Repair hash links only; deliberately do not repair semantic corruption."""
    previous = rc.GENESIS_SHA256
    for i, row in enumerate(snapshot["events"], 1):
        row["event"]["sequence"], row["event"]["previous_sha256"] = i, previous
        previous = row["event_sha256"] = rc.digest(row["event"])
    snapshot["event_sequence"], snapshot["event_head_sha256"] = len(snapshot["events"]), previous
    return snapshot


class WitnessContractTests(unittest.TestCase):
    def test_complete_commit_migration_delivery_history_derives_all_state(self):
        snapshot = history_fixture(committed=True, migrated=True, delivered=True)
        self.assertEqual(c.validate_history(snapshot), snapshot)
        state = c.replay_history(snapshot)
        self.assertEqual(state["version"], 2)
        self.assertEqual(state["epoch"], 3)
        self.assertEqual(len(state["receipts"]), 1)
        self.assertEqual(len(state["outbox"]), 1)
        self.assertEqual(state["accounts"][rc.account_id("agency", "project")]["total_engineering_charge_units"], 1)
        self.assertEqual(state["deliveries"]["8" * 32]["acknowledgment"]["acked_at"], 1005)

    def test_history_and_derived_state_are_owned(self):
        snapshot = history_fixture(committed=True)
        owned, state = c.validate_history(snapshot), c.replay_history(snapshot)
        snapshot["events"][0]["event"]["payload"]["accounts"][0]["agency_id"] = "changed"
        state["accounts"].clear()
        self.assertEqual(owned["events"][0]["event"]["payload"]["accounts"][0]["agency_id"], "agency")
        self.assertEqual(len(c.replay_history(owned)["accounts"]), 1)

    def test_json_duplicates_floats_overflow_nonfinite_depth_nodes_rejected(self):
        invalid = [b'{"x":1,"x":2}', b'{"x":{"a":1,"a":2}}', b'1.0', b'1e999', b'NaN', b'Infinity',
                   b'[' * 34 + b'0' + b']' * 34, b'9007199254740992']
        for raw in invalid:
            with self.subTest(raw=raw[:30]), self.assertRaises(c.WitnessContractError):
                c.strict_json(raw)
        with self.assertRaises(c.WitnessContractError):
            c.canonical_bytes([0] * c.MAX_NODES, c.MAX_STATE_BYTES)
        self.assertNotEqual(c.canonical_bytes(False), c.canonical_bytes(0))
        for value in (1.0, float("nan"), (1,), object()):
            with self.subTest(value=value), self.assertRaises(c.WitnessContractError):
                c.canonical_bytes(value)

    def test_large_records_need_explicit_bounded_size(self):
        value = {"text": "a" * 70000}
        with self.assertRaises(c.WitnessContractError):
            c.canonical_bytes(value)
        raw = c.canonical_bytes(value, c.MAX_HISTORY_BYTES)
        self.assertEqual(c.strict_json(raw, c.MAX_HISTORY_BYTES), value)
        for bound in (True, 0, c.MAX_STATE_BYTES + 1, 1.0):
            with self.subTest(bound=bound), self.assertRaises(c.WitnessContractError):
                c.strict_json(b'{}', bound)

    def test_history_summary_must_match_complete_replay(self):
        mutations = {"event_sequence": 1, "event_head_sha256": "a" * 64, "schema_version": 1,
                     "broker_epoch": 2, "broker_id": "b" * 32, "store_id": "c" * 32, "observed_at": 999}
        for key, value in mutations.items():
            snapshot = history_fixture()
            snapshot[key] = value
            with self.subTest(key=key), self.assertRaises(c.WitnessContractError):
                c.validate_history(snapshot)

    def test_history_rejects_unknown_fields_and_boolean_integer_aliases(self):
        for key, value in (("extra", 1), ("broker_epoch", True), ("schema_version", True),
                           ("event_sequence", True), ("observed_at", False), ("fixture_only", 1),
                           ("independent_custody_verified", 0)):
            snapshot = history_fixture()
            snapshot[key] = value
            with self.subTest(key=key), self.assertRaises(c.WitnessContractError):
                c.validate_history(snapshot)

    def test_missing_reordered_duplicate_or_modified_event_rejected(self):
        base = history_fixture(committed=True)
        cases = []
        item = copy.deepcopy(base); item["events"].pop(1); cases.append(item)
        item = copy.deepcopy(base); item["events"].reverse(); cases.append(item)
        item = copy.deepcopy(base); item["events"].append(copy.deepcopy(item["events"][-1])); cases.append(item)
        item = copy.deepcopy(base); item["events"][1]["event"]["occurred_at"] = 1001; cases.append(item)
        for index, item in enumerate(cases):
            with self.subTest(index=index), self.assertRaises(c.WitnessContractError):
                c.validate_history(item)

    def test_rehashed_forged_charge_receipt_is_not_accepted_as_valid_history(self):
        snapshot = history_fixture(committed=True)
        envelope = snapshot["events"][-1]["event"]["payload"]["receipt"]
        envelope["receipt"]["charge_units"] = 0
        envelope["receipt_sha256"] = rc.digest(envelope["receipt"])
        with self.assertRaises(c.WitnessContractError):
            c.validate_history(rehash(snapshot))

    def test_rehashed_broker_reuse_or_backwards_time_rejected(self):
        for changed in ("epoch", "time"):
            snapshot = history_fixture(committed=True)
            if changed == "epoch":
                snapshot["events"][1]["event"]["payload"]["expected_epoch"] = 1
            else:
                snapshot["events"][2]["event"]["occurred_at"] = 999
            with self.subTest(changed=changed), self.assertRaises(c.WitnessContractError):
                c.validate_history(rehash(snapshot))

    def test_rehashed_migration_and_ack_semantics_remain_enforced(self):
        for kind in ("migrated", "acknowledged"):
            snapshot = history_fixture(committed=True, migrated=True, delivered=True)
            event = next(row["event"] for row in snapshot["events"] if row["event"]["kind"] == kind)
            if kind == "migrated":
                event["payload"]["preserved_sha256"] = "a" * 64
            else:
                event["payload"]["acknowledgment"]["owner_sha256"] = "b" * 64
            with self.subTest(kind=kind), self.assertRaises(c.WitnessContractError):
                c.validate_history(rehash(snapshot))

    def test_events_and_individual_event_size_are_bounded(self):
        snapshot = history_fixture()
        snapshot["event_sequence"] = rs.MAX_EVENTS + 1
        with self.assertRaises(c.WitnessContractError):
            c.validate_history(snapshot)
        snapshot = history_fixture()
        snapshot["events"][0]["event"]["payload"]["oversized"] = "a" * 65536
        with self.assertRaises(c.WitnessContractError):
            c.validate_history(snapshot)

    def test_namespace_requires_exactly_one_configured_account(self):
        snapshot = history_fixture()
        self.assertEqual(c.history_namespace(snapshot, "agency", "project"), rc.account_id("agency", "project"))
        for agency, project in (("other", "project"), ("agency", "other")):
            with self.assertRaises(c.WitnessContractError):
                c.history_namespace(snapshot, agency, project)
        snapshot = history_fixture(accounts=[{"agency_id": "agency", "project_id": "project"},
                                            {"agency_id": "agency", "project_id": "second"}])
        c.validate_history(snapshot)  # General history can contain PRD15's multiple accounts.
        with self.assertRaises(c.WitnessContractError):
            c.history_namespace(snapshot, "agency", "project")

    def test_intent_binds_current_predecessor_cas_and_owns_request(self):
        snapshot, request = history_fixture(), request_fixture()
        intent = c.create_intent(snapshot, request)
        self.assertEqual(c.validate_intent(intent), intent)
        self.assertEqual(intent["predecessor_head_sha256"], snapshot["event_head_sha256"])
        self.assertEqual(intent["namespace_id"], rc.account_id("agency", "project"))
        request["object_reference"]["sha256"] = "f" * 64
        self.assertEqual(intent["request"]["object_reference"]["sha256"], rc.FIXTURE_SHA256)
        self.assertNotIn("commit_context", intent)
        self.assertNotIn("pin", intent)

    def test_intent_rejects_foreign_registry_scope_missing_broker_or_stale_cas(self):
        cases = [(history_fixture(), request_fixture(store_id="9" * 32)),
                 (history_fixture(), request_fixture(project_id="other")),
                 (history_fixture(broker=False), request_fixture()),
                 (history_fixture(committed=True), request_fixture())]
        for snapshot, request in cases:
            with self.subTest(request=request["project_id"]), self.assertRaises(c.WitnessContractError):
                c.create_intent(snapshot, request)

    def test_intent_after_commit_uses_shared_account_and_exact_case_heads(self):
        snapshot = history_fixture(committed=True)
        head = receipt_fixture()["receipt_sha256"]
        same = request_fixture(request_id="e" * 32, account_sequence=1, case_sequence=1, account_head=head, case_head=head)
        other = request_fixture(request_id="f" * 32, case_id="case-b", account_sequence=1, account_head=head)
        self.assertEqual(c.create_intent(snapshot, same)["request"]["expected_case_sequence"], 1)
        self.assertEqual(c.create_intent(snapshot, other)["request"]["expected_case_sequence"], 0)
        same["expected_case_head_sha256"] = "a" * 64
        with self.assertRaises(c.WitnessContractError):
            c.create_intent(snapshot, same)

    def test_intent_structural_bindings_and_transient_extra_fields_rejected(self):
        original = c.create_intent(history_fixture(), request_fixture())
        for key, value in (("namespace_id", "a" * 64), ("registry_id", "a" * 32),
                           ("request_sha256", "a" * 64), ("broker_epoch", True),
                           ("predecessor_sequence", 1), ("commit_context", context_fixture()), ("pin", pin_fixture())):
            intent = copy.deepcopy(original); intent[key] = value
            with self.subTest(key=key), self.assertRaises(c.WitnessContractError):
                c.validate_intent(intent)

    def test_pin_exact_integer_and_lowercase_digest_bindings(self):
        self.assertEqual(c.validate_pin(pin_fixture()), pin_fixture())
        for key, value in (("revision", True), ("revision", 0), ("head_sha256", c.GENESIS_SHA256),
                           ("head_sha256", "A" * 64), ("registry_id", "z" * 32), ("signature", "fake")):
            pin = pin_fixture(); pin[key] = value
            with self.subTest(key=key), self.assertRaises(c.WitnessContractError):
                c.validate_pin(pin)

    def test_diagnosis_counts_and_reconciliation_are_derived_from_intent_roster(self):
        for state in ("pending", "committed", "aborted"):
            item = diagnosis_fixture(state)
            self.assertEqual(c.validate_diagnosis(item), item)
            item["reconciled"] = not item["reconciled"]
            with self.subTest(state=state), self.assertRaises(c.WitnessContractError):
                c.validate_diagnosis(item)

    def test_diagnosis_rejects_false_clearance_omitted_intent_and_duplicate_request(self):
        for key, value in (("production_authorized", True), ("independent_custody_verified", True),
                           ("pending_intents", 0), ("quarantine_reasons", []), ("status", "consistent"),
                           ("namespace_id", "a" * 64), ("reconciled", 0)):
            item = diagnosis_fixture(); item[key] = value
            with self.subTest(key=key), self.assertRaises(c.WitnessContractError):
                c.validate_diagnosis(item)
        item = diagnosis_fixture(); item["intents"].append(copy.deepcopy(item["intents"][0])); item["pending_intents"] = 2
        with self.assertRaises(c.WitnessContractError):
            c.validate_diagnosis(item)

    def test_diagnosis_receipt_matches_original_intent_and_epoch(self):
        for changed in ("missing", "epoch", "unexpected"):
            item = diagnosis_fixture("committed" if changed != "unexpected" else "pending")
            row = item["intents"][0]
            if changed == "missing":
                row["receipt"] = None
            elif changed == "epoch":
                row["receipt"] = receipt_fixture(context=context_fixture(broker_epoch=2))
            else:
                row["receipt"] = receipt_fixture()
            with self.subTest(changed=changed), self.assertRaises(c.WitnessContractError):
                c.validate_diagnosis(item)

    def test_diagnosis_cannot_resolve_an_intent_before_registry_progress(self):
        for state in ("committed", "aborted"):
            item = diagnosis_fixture(state)
            item["registry_sequence"] = item["intents"][0]["intent"]["predecessor_sequence"]
            with self.subTest(state=state), self.assertRaises(c.WitnessContractError):
                c.validate_diagnosis(item)
        item = diagnosis_fixture("committed"); item["registry_observed_at"] = 1000
        with self.assertRaises(c.WitnessContractError):
            c.validate_diagnosis(item)
        item = diagnosis_fixture(); item["registry_epoch"] = item["registry_sequence"]
        with self.assertRaises(c.WitnessContractError):
            c.validate_diagnosis(item)

    def test_witness_flags_do_not_mutate_prior_contract_flags_or_claim_privacy(self):
        self.assertNotIn("independent_custody_verified", rc.FLAGS)
        item = c.create_intent(history_fixture(), request_fixture())
        for name, expected in c.FLAGS.items():
            self.assertIs(item[name], expected)
        self.assertNotIn("epsilon", item)
        self.assertNotIn("delta", item)


if __name__ == "__main__":
    unittest.main()
