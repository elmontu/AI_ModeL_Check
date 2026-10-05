"""Strict fixed-fixture intent, engineering charge and immutable receipt records."""
from __future__ import annotations

import copy
import hashlib
import json
import unittest

from model_release_assurance.production_registry import contracts as c
from model_release_assurance.production_storage.contracts import ObjectReference, PROVENANCE
from model_release_assurance.production_storage.backend import _FIXTURE_BYTES


def request_fixture(*, store_id="1" * 32, request_id="2" * 32, agency_id="agency", project_id="project",
                    case_id="case-a", actor_person_id="steward", account_sequence=0, case_sequence=0,
                    account_head=c.GENESIS_SHA256, case_head=c.GENESIS_SHA256):
    reference = ObjectReference("3" * 32, "4" * 32, agency_id, project_id, case_id,
        c.FIXTURE_SHA256, c.FIXTURE_SIZE_BYTES, "application/json", "public-counts-v1",
        **dict(PROVENANCE), created_at=1000, retention_until=1300)
    return {"schema": "mra-fixture-registry-request/v1", "environment": "public_fixture", "store_id": store_id,
        "account_id": c.account_id(agency_id, project_id), "request_id": request_id,
        "agency_id": agency_id, "project_id": project_id, "case_id": case_id, "actor_person_id": actor_person_id,
        "expected_account_sequence": account_sequence, "expected_account_head_sha256": account_head,
        "expected_case_sequence": case_sequence, "expected_case_head_sha256": case_head,
        "object_reference": reference.to_dict(), "source_sha256": c.FIXTURE_SHA256,
        "policy_sha256": c.digest(c.POLICY), **c.FLAGS}


def context_fixture(*, actor_person_id="steward", broker_id="5" * 32, broker_epoch=1):
    return {"broker_id": broker_id, "broker_epoch": broker_epoch, "actor_person_id": actor_person_id,
            "actor_credential_sha256": "6" * 64, "authority_revision": 1, "trust_revision": 1}


def receipt_fixture(request=None, context=None):
    return c.create_receipt(request or request_fixture(), context or context_fixture(),
                            receipt_id="7" * 32, event_id="8" * 32, committed_at=1001)


class RegistryContractTests(unittest.TestCase):
    def test_fixed_policy_pins_real_fictional_bytes_and_never_claims_privacy(self):
        self.assertEqual(c.FIXTURE_SHA256, hashlib.sha256(_FIXTURE_BYTES).hexdigest())
        self.assertEqual(c.FIXTURE_SIZE_BYTES, len(_FIXTURE_BYTES))
        policy = c.fixed_policy()
        self.assertEqual((policy["charge_units"], policy["account_capacity_units"]), (1, 8))
        self.assertEqual(policy["charge_unit"], "fixture_commit")
        self.assertEqual(policy["purpose"], "engineering_atomicity_rehearsal")
        self.assertFalse(policy["model_artifacts_supported"])
        for name, value in c.FLAGS.items():
            self.assertIs(policy[name], value)
        policy["charge_units"] = 0
        self.assertEqual(c.fixed_policy()["charge_units"], 1)
        self.assertNotIn("epsilon", policy)
        self.assertNotIn("delta", policy)

    def test_valid_intent_and_context_are_deep_owned(self):
        original = request_fixture()
        owned = c.validate_request(original)
        original["object_reference"]["case_id"] = "changed"
        self.assertEqual(owned["object_reference"]["case_id"], "case-a")
        context = context_fixture()
        copied = c.validate_commit_context(context)
        context["broker_epoch"] = 2
        self.assertEqual(copied["broker_epoch"], 1)

    def test_account_is_shared_across_cases_but_not_projects_or_agencies(self):
        first = request_fixture(case_id="case-a")
        second = request_fixture(case_id="case-b")
        self.assertEqual(first["account_id"], second["account_id"])
        self.assertNotEqual(first["account_id"], request_fixture(project_id="other")["account_id"])
        self.assertNotEqual(first["account_id"], request_fixture(agency_id="other")["account_id"])

    def test_strict_json_denies_duplicate_keys_noninteger_numbers_depth_and_size(self):
        invalid = [b'{"a":1,"a":2}', b'{"a":{"b":1,"b":2}}', b'{"a":1.0}', b'{"a":1e999}',
                   b'{"a":NaN}', b'{"a":Infinity}', b'{"a":-Infinity}', b'[' * 18 + b'0' + b']' * 18,
                   b'{"a":9007199254740992}', b'{"a":"' + b'a' * 65536 + b'"}']
        for raw in invalid:
            with self.subTest(raw=raw[:50]), self.assertRaises(c.RegistryContractError):
                c.strict_json(raw)
        for bound in (True, 0, 65537, 1.0):
            with self.subTest(bound=bound), self.assertRaises(c.RegistryContractError):
                c.strict_json(b'{}', bound)
        for value in ({"a":1.0}, {"a":float("nan")}, {"a":(1,)}, {"a":object()}):
            with self.subTest(value=value), self.assertRaises(c.RegistryContractError):
                c.canonical_bytes(value)
        self.assertNotEqual(c.canonical_bytes({"a":False}), c.canonical_bytes({"a":0}))

    def test_unknown_dp_charge_or_broker_fields_are_not_request_options(self):
        for name, value in (("epsilon",0), ("delta",0), ("charge_units",0), ("capacity",1000),
                            ("model_path","malicious.pkl"), ("broker_epoch",2), ("authority_revision",5)):
            request = request_fixture()
            request[name] = value
            with self.subTest(name=name), self.assertRaises(c.RegistryContractError):
                c.validate_request(request)

    def test_flags_and_integer_fields_are_not_coerced(self):
        for name, value in (("fixture_only",1), ("authorization_eligible",0), ("privacy_accounting_supported",True),
                            ("production_authorized",True), ("expected_account_sequence",False),
                            ("expected_case_sequence",0.0)):
            request = request_fixture()
            request[name] = value
            with self.subTest(name=name), self.assertRaises(c.RegistryContractError):
                c.validate_request(request)
        for name in ("broker_epoch", "authority_revision", "trust_revision"):
            for value in (True, 0, 1.0, -1):
                context = context_fixture()
                context[name] = value
                with self.subTest(name=name,value=value), self.assertRaises(c.RegistryContractError):
                    c.validate_commit_context(context)

    def test_arbitrary_models_and_wrong_reference_scope_are_rejected(self):
        for name, value in (("sha256","a" * 64), ("size_bytes",358), ("case_id","other"),
                            ("agency_id","other"), ("project_id","other"), ("fixture_id","native-model"),
                            ("format","application/pickle"), ("created_at",True)):
            request = request_fixture()
            request["object_reference"][name] = value
            with self.subTest(name=name), self.assertRaises(c.RegistryContractError):
                c.validate_request(request)

    def test_source_policy_and_account_digest_are_derived(self):
        for name in ("source_sha256", "policy_sha256", "account_id"):
            request = request_fixture()
            request[name] = "a" * 64
            with self.subTest(name=name), self.assertRaises(c.RegistryContractError):
                c.validate_request(request)

    def test_genesis_sequence_and_cas_scope_are_consistent(self):
        invalid = [request_fixture(account_sequence=1), request_fixture(account_head="a" * 64),
                   request_fixture(account_sequence=0,case_sequence=1,case_head="a"*64),
                   request_fixture(account_sequence=9,account_head="a"*64)]
        for request in invalid:
            with self.subTest(request=request), self.assertRaises(c.RegistryContractError):
                c.validate_request(request)
        for name, value in (("request_id","not-a-hex-id"), ("store_id","A" * 32), ("actor_person_id","../owner")):
            request = request_fixture()
            request[name] = value
            with self.subTest(name=name), self.assertRaises(c.RegistryContractError):
                c.validate_request(request)

    def test_fixed_receipt_charge_heads_and_exact_request_binding(self):
        request = request_fixture()
        receipt = receipt_fixture(request)
        body = receipt["receipt"]
        self.assertEqual(receipt["receipt_sha256"], c.digest(body))
        self.assertEqual(body["request_sha256"], c.digest(request))
        self.assertEqual((body["charge_units"],body["total_engineering_charge_units"],
                          body["account_sequence"],body["case_sequence"]),(1,1,1,1))
        self.assertEqual(body["object_reference_sha256"], ObjectReference.from_dict(request["object_reference"]).reference_digest)
        self.assertEqual(c.validate_receipt(receipt,request=request),receipt)
        owned = c.validate_receipt(receipt)
        receipt["receipt"]["commit_context"]["actor_person_id"] = "changed"
        self.assertEqual(owned["receipt"]["commit_context"]["actor_person_id"], "steward")

    def test_other_case_cannot_reset_account_engineering_charges(self):
        first = receipt_fixture()
        second_request = request_fixture(case_id="case-b",request_id="9"*32,account_sequence=1,
                                         account_head=first["receipt_sha256"])
        second = receipt_fixture(second_request)
        self.assertEqual((second["receipt"]["account_sequence"],second["receipt"]["case_sequence"],
                          second["receipt"]["total_engineering_charge_units"]),(2,1,2))
        self.assertEqual(second["receipt"]["previous_account_head_sha256"], first["receipt_sha256"])

    def test_ninth_engineering_charge_has_no_valid_receipt(self):
        eighth = request_fixture(account_sequence=7,account_head="a"*64)
        self.assertEqual(receipt_fixture(eighth)["receipt"]["total_engineering_charge_units"],8)
        ninth = request_fixture(account_sequence=8,account_head="a"*64)
        with self.assertRaises(c.RegistryContractError):
            receipt_fixture(ninth)

    def test_current_context_changes_do_not_change_immutable_intent(self):
        request = request_fixture()
        original_hash = c.digest(c.validate_request(request))
        first = receipt_fixture(request)
        refreshed = context_fixture(broker_id="9"*32,broker_epoch=2)
        refreshed.update(actor_credential_sha256="a"*64,authority_revision=2,trust_revision=3)
        other = receipt_fixture(request,refreshed)
        self.assertEqual(first["receipt"]["request_sha256"], other["receipt"]["request_sha256"])
        self.assertEqual(c.digest(request),original_hash)
        self.assertNotEqual(first["receipt_sha256"],other["receipt_sha256"])
        # Store idempotency must return the first receipt, never create this second one.
        with self.assertRaises(c.RegistryContractError):
            receipt_fixture(request,context_fixture(actor_person_id="other-person"))

    def test_receipt_derived_fields_reject_tampering_even_with_new_hash(self):
        for name,value in (("charge_units",0), ("charge_units",True), ("total_engineering_charge_units",2),
                           ("account_sequence",True), ("case_sequence",2), ("source_sha256","a"*64),
                           ("policy_sha256","a"*64), ("production_authorized",True),
                           ("object_reference_sha256","a"*64), ("request_sha256","a"*64)):
            receipt = receipt_fixture()
            receipt["receipt"][name] = value
            receipt["receipt_sha256"] = c.digest(receipt["receipt"])
            with self.subTest(name=name,value=value), self.assertRaises(c.RegistryContractError):
                c.validate_receipt(receipt,request=request_fixture())
        receipt=receipt_fixture()
        receipt["receipt_sha256"]="a"*64
        with self.assertRaises(c.RegistryContractError):
            c.validate_receipt(receipt)

    def test_commit_time_cannot_precede_or_extend_object_commitment(self):
        for now in (999,1300,1301,True,1001.0):
            with self.subTest(now=now), self.assertRaises(c.RegistryContractError):
                c.create_receipt(request_fixture(),context_fixture(),receipt_id="7"*32,event_id="8"*32,committed_at=now)

    def test_outbox_event_is_exact_derived_non_authorizing_metadata(self):
        request=request_fixture()
        receipt=receipt_fixture(request)
        event=c.create_outbox_event(request,receipt)
        self.assertEqual(event["receipt_sha256"],receipt["receipt_sha256"])
        self.assertEqual(event["event_id"],receipt["receipt"]["event_id"])
        self.assertEqual(event["artifact_sha256"],c.FIXTURE_SHA256)
        self.assertEqual(c.validate_outbox_event(event),event)
        for name,value in c.FLAGS.items():self.assertIs(event[name],value)
        self.assertNotIn("actor_credential_sha256",event)
        self.assertNotIn("object_reference",event)

    def test_outbox_unknown_scope_privacy_and_artifact_claims_fail(self):
        original=c.create_outbox_event(request_fixture(),receipt_fixture())
        for name,value in (("account_id","a"*64), ("artifact_sha256","a"*64), ("source_sha256","a"*64),
                           ("policy_sha256","a"*64), ("event_id","a"*64), ("case_id",False),
                           ("epsilon",0), ("model_delivery",True), ("fixture_only",1)):
            event=copy.deepcopy(original)
            event[name]=value
            with self.subTest(name=name), self.assertRaises(c.RegistryContractError):
                c.validate_outbox_event(event)
        foreign=request_fixture(case_id="other")
        with self.assertRaises(c.RegistryContractError):
            c.create_outbox_event(foreign,receipt_fixture())

    def test_errors_are_generic_and_metadata_cannot_execute_objects(self):
        class Dangerous:
            def __str__(self):raise AssertionError("must not stringify input")
        request=request_fixture()
        request["actor_person_id"]=Dangerous()
        with self.assertRaisesRegex(c.RegistryContractError,"^Fixture registry record rejected$"):
            c.validate_request(request)


if __name__=="__main__":unittest.main()
