"""Strict delivery formats; example candidate is inert unit-test metadata."""
import hashlib
import unittest

from model_release_assurance.production_adapters.contracts import NativeCandidate, canonical_bytes as native_bytes
from model_release_assurance.production_delivery.contracts import (DeliveryError, FLAGS, canonical_bytes,
    strict_json, validate_pin, validate_activation, validate_grant, validate_chunk, validate_payload, validate_artifact)


def candidate_fixture():
    candidate = NativeCandidate(task="classification", dataset_id="public-unit-fixture", source_sha256="a" * 64,
        data_sha256="b" * 64, plan_sha256="c" * 64, implementation_sha256="d" * 64,
        feature_names=["feature"], training_rows=128,
        preprocessing={"kind":"standard-scaler/v1", "mean":[0.0], "scale":[1.0]},
        model={"kind":"gaussian-nb/v1", "classes":[0,1], "prior":[0.5,0.5], "theta":[[0.0],[1.0]],
               "variance":[[1.0],[1.0]], "var_smoothing":1e-9},
        runtime={"python":"3.12", "numpy":"fixture", "scipy":"fixture", "scikit-learn":"fixture"})
    return native_bytes(candidate) + b"\n"


def actor_fixture(person="recipient", credential="e"):
    return {"person_id":person,"authority_revision":1,"credential_sha256":credential * 64}


def activation_fixture(raw=None, **changes):
    raw = candidate_fixture() if raw is None else raw
    result = {"schema":"mra-fixture-delivery-activation/v1", "activation_id":"1"*32, "campaign_id":"2"*32,
        "agency_id":"agency", "project_id":"project", "case_id":"case-a", "recipient_id":"public-recipient",
        "artifact_sha256":hashlib.sha256(raw).hexdigest(), "artifact_size":len(raw), "policy_sha256":"a"*64,
        "binding_sha256":"b"*64, "approval_sha256":"c"*64, "review_store_id":"3"*32,
        "review_head_sha256":"d"*64, "expires_at":1120, "format":"native_candidate_json", "profile":"local_public_fixture"}
    result.update(changes)
    return result


def grant_fixture(activation=None, **changes):
    activation = activation or activation_fixture()
    result = {"grant_id":"4"*32, "activation_id":activation["activation_id"], "transfer_id":"5"*32,
        "recipient_id":activation["recipient_id"], "recipient_person_id":"recipient", "recipient_credential_sha256":"e"*64,
        "expires_at":1060, "max_attempted_bytes":3*activation["artifact_size"]}
    result.update(changes)
    return result


def chunk_fixture(**changes):
    result = {"activation_id":"1"*32, "grant_id":"4"*32, "transfer_id":"5"*32,
        "request_id":"6"*32, "chunk_id":"7"*32, "offset":0, "length":32}
    result.update(changes)
    return result


class DeliveryContractTests(unittest.TestCase):
    def test_exact_activation_and_inert_bytes(self):
        raw = candidate_fixture()
        value = validate_activation(activation_fixture(raw))
        self.assertEqual(validate_artifact(raw, value), raw)
        self.assertEqual(value["format"], "native_candidate_json")
        self.assertFalse(FLAGS["model_delivery"])
        self.assertNotIn("public_fixture_bytes_delivered", FLAGS)

    def test_missing_unknown_or_execution_fields_rejected(self):
        activation = activation_fixture()
        for key in activation:
            with self.subTest(key=key), self.assertRaises(DeliveryError):
                validate_activation({name:item for name,item in activation.items() if name != key})
        with self.assertRaises(DeliveryError):
            validate_activation({**activation,"download_url":"https://example.invalid/model"})

    def test_bad_activation_profile_bounds_or_types_rejected(self):
        for key,value in (("artifact_size",True),("artifact_size",2*1024*1024+1),("format","pickle"),
                          ("profile","production"),("recipient_id","*"),("artifact_sha256","A"*64),
                          ("activation_id","../latest"),("expires_at",1000.5)):
            with self.subTest(key=key), self.assertRaises(DeliveryError):
                validate_activation(activation_fixture(**{key:value}))

    def test_opaque_archives_pickle_and_wrong_json_never_accepted(self):
        for raw in (b"PK\\x03\\x04arbitrary",b"\\x80\\x04pickle",b"{}",b"[1,2]",b'{"script":"run"}'):
            with self.assertRaises(DeliveryError):
                validate_artifact(raw,activation_fixture(raw))
        raw = candidate_fixture()
        with self.assertRaises(DeliveryError):
            validate_artifact(raw + b" ",activation_fixture(raw))
        with self.assertRaises(DeliveryError):
            validate_artifact(bytearray(raw),activation_fixture(raw))

    def test_grant_and_chunk_exact_ids_and_bounds(self):
        self.assertEqual(validate_grant(grant_fixture()),grant_fixture())
        self.assertEqual(validate_chunk(chunk_fixture()),chunk_fixture())
        for value in (chunk_fixture(length=16385),chunk_fixture(offset=-1),chunk_fixture(length=True),
                      {**chunk_fixture(),"recipient_override":"someone"}):
            with self.assertRaises(DeliveryError):
                validate_chunk(value)

    def test_pin_shape_never_proves_independent_custody(self):
        pin={"schema":"mra-fixture-delivery-pin/v1","store_id":"1"*32,"sequence":1,"head_sha256":"a"*64}
        self.assertEqual(validate_pin(pin),pin)
        for changes in ({"sequence":True},{"sequence":0},{"head_sha256":"0"*64},{"schema":"other"}):
            with self.assertRaises(DeliveryError):
                validate_pin({**pin,**changes})

    def test_unknown_write_extent_is_explicit_and_not_zero(self):
        observation={"request_id":"6"*32,"bytes_written":None,"status":"failed",
                     "write_extent_known":False,"recipient_receipt_verified":False}
        self.assertIsNone(validate_payload("observe",observation)["bytes_written"])
        for changes in ({"bytes_written":0},{"status":"returned"},{"write_extent_known":0},
                        {"recipient_receipt_verified":True}):
            with self.assertRaises(DeliveryError):
                validate_payload("observe",{**observation,**changes})
        with self.assertRaises(DeliveryError):
            validate_payload("observe",{**observation,"write_extent_known":True,"bytes_written":4})

    def test_metadata_json_rejects_duplicate_nonfinite_huge_integer_and_float(self):
        for raw in (b'{"x":1,"x":2}',b'{"x":NaN}',b'{"x":0.5}',b'{"x":'+b'9'*5000+b'}'):
            with self.assertRaises(DeliveryError):
                strict_json(raw)
        with self.assertRaises(DeliveryError):
            canonical_bytes({"token":object()})


if __name__ == "__main__":
    unittest.main()
