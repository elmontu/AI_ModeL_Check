"""Strict fixed findings and local dispositions cannot manufacture clearance."""
import copy
import hashlib
import unittest

from model_release_assurance.production_assessment import contracts as c


def binding():
    return {"schema": "mra-local-assessment-binding/v1", "packet_sha256": "a"*64,
            "catalog_sha256": c.catalog_sha256(), "agency_id": "agency", "project_id": "project", "case_id": "case-a"}


def record():
    return {"schema": "mra-local-assessment-review/v1", "kind": "assessment", "binding": binding(),
            "actor": {"person_id": "person-assessor", "authority_revision": 1, "credential_sha256": "b"*64},
            "recorded_at": 1000, "dispositions": c.default_dispositions(), **c.FLAGS}


class AssessmentContractsTests(unittest.TestCase):
    def test_catalog_is_fixed_owned_and_bound_by_canonical_hash(self):
        catalog = c.finding_catalog()
        self.assertEqual(len(catalog["findings"]), 13)
        self.assertEqual(c.validate_catalog(catalog), catalog)
        self.assertEqual(c.catalog_sha256(), hashlib.sha256(c.canonical_bytes(catalog)).hexdigest())
        catalog["findings"][0]["description"] = "changed"
        self.assertNotEqual(catalog, c.finding_catalog())
        with self.assertRaises(c.AssessmentError): c.validate_catalog(catalog)

    def test_flags_are_immutable_and_every_clearance_flag_false(self):
        with self.assertRaises(TypeError): c.FLAGS["can_clear"] = True
        self.assertIs(c.FLAGS["local_public_fixture"], True)
        self.assertTrue(all(value is False for key,value in c.FLAGS.items() if key != "local_public_fixture"))

    def test_all_production_blockers_cannot_be_accepted_closed_or_justified(self):
        for index, finding in enumerate(c.BLOCKING_FINDING_IDS):
            for disposition in ("closed", "accepted_for_local_fixture", "acknowledged"):
                rows = c.default_dispositions(); rows[index]["disposition"] = disposition
                with self.subTest(finding=finding, disposition=disposition), self.assertRaises(c.AssessmentError):
                    c.validate_dispositions(rows)
            rows = c.default_dispositions(); rows[index]["justification"] = "mitigated"
            with self.assertRaises(c.AssessmentError): c.validate_dispositions(rows)

    def test_local_acceptance_requires_exact_finding_specific_reason(self):
        rows = c.default_dispositions()
        reasons = ["descriptive_fixture_measurements_only", "trusted_local_fixture_only"]
        for index, reason in zip((-2,-1), reasons):
            rows[index].update(disposition="accepted_for_local_fixture", justification=reason)
        self.assertEqual(c.validate_dispositions(rows), rows)
        for replacement in (None, True, "", "trusted_local_fixture_only"):
            changed = copy.deepcopy(rows); changed[-2]["justification"] = replacement
            with self.assertRaises(c.AssessmentError): c.validate_dispositions(changed)

    def test_omission_duplicates_unknown_extra_and_reordered_dispositions_rejected(self):
        rows = c.default_dispositions()
        values = [rows[:-1], rows+[rows[0]], rows[::-1], {"rows": rows}]
        changed = copy.deepcopy(rows); changed[-1] = changed[-2]; values.append(changed)
        changed = copy.deepcopy(rows); changed[0]["evidence_passed"] = True; values.append(changed)
        changed = copy.deepcopy(rows); changed[0]["finding_id"] = "invented"; values.append(changed)
        for value in values:
            with self.assertRaises(c.AssessmentError): c.validate_dispositions(value)

    def test_json_duplicates_float_nonfinite_depth_and_size_refused(self):
        for raw in (b'{"a":1,"a":2}', b'{"a":1.0}', b'{"a":1e999}', b'{"a":NaN}', b'['*34+b'0'+b']'*34,
                    b'"'+b'x'*65536+b'"', '{"a":1}'):
            with self.subTest(kind=type(raw).__name__), self.assertRaises(c.AssessmentError): c.strict_json(raw)
        for value in (float("nan"), (1,2), object(), {1:"value"}):
            with self.assertRaises(c.AssessmentError): c.canonical_bytes(value)
        with self.assertRaises(c.AssessmentError): c.canonical_bytes({}, max_bytes=65537)

    def test_binding_rejects_wrong_catalog_scope_extra_and_digest_types(self):
        valid = binding(); self.assertEqual(c.validate_binding(valid), valid)
        for change in ({"catalog_sha256":"f"*64}, {"packet_sha256":"A"*64}, {"packet_sha256":True},
                       {"case_id":"../case"}, {"project_id":[]}, {"unverified":True}):
            with self.assertRaises(c.AssessmentError): c.validate_binding({**valid, **change})

    def test_records_have_exact_typed_flags_actor_and_digest_bindings(self):
        valid = record(); self.assertEqual(c.validate_review_record(valid), valid)
        mutations = [lambda row: row.update(production_ready=True), lambda row: row.update(can_clear=0),
                     lambda row: row.update(recorded_at=True), lambda row: row["actor"].update(authority_revision=True),
                     lambda row: row["actor"].update(token="secret"), lambda row: row.update(kind=[]),
                     lambda row: row.update(assessment_sha256="a"*64), lambda row: row.update(evidence_passed=True)]
        for mutation in mutations:
            changed=copy.deepcopy(valid);mutation(changed)
            with self.assertRaises(c.AssessmentError): c.validate_review_record(changed)
        approval = {key:value for key,value in valid.items() if key != "dispositions"}
        approval.update(kind="approval", assessment_sha256=c.digest(valid))
        self.assertEqual(c.validate_review_record(approval), approval)

    def test_production_default_and_unknown_profiles_refused(self):
        for profile in ("agency_private_cloud", "production", None, True, []):
            with self.assertRaises(c.AssessmentError): c.require_local(profile)
        self.assertIsNone(c.require_local("local_public_fixture"))

    def test_generic_errors_do_not_echo_private_payload(self):
        secret="private-token-value-never-echo"
        with self.assertRaises(c.AssessmentError) as error:
            c.validate_binding({"private":secret})
        self.assertNotIn(secret,str(error.exception))


if __name__ == "__main__": unittest.main()
