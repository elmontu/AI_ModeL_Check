"""Privacy boundaries for the fixed redacted telemetry schema."""
import copy
import unittest

from model_release_assurance.production_monitoring import contracts as c


class MonitoringContractsTests(unittest.TestCase):
    def event(self):
        return {"schema": "mra-fixture-monitor-event/v1", "event_id": "a"*32,
                "resource_id": "b"*32, "observed_at": 1000,
                "code": "key_unavailable", "condition": "fault", **c.FLAGS}

    def test_owned_metadata_and_fixed_routes(self):
        event = self.event(); result = c.validate_event(event)
        event["code"] = "worker_unavailable"
        self.assertEqual(result["code"], "key_unavailable")
        self.assertEqual(c.RULES["key_unavailable"]["route"], "security")
        with self.assertRaises(TypeError):
            c.RULES["key_unavailable"]["route"] = "external"

    def test_sensitive_extensions_are_rejected(self):
        for field in ("token", "path", "exception", "details", "stdout", "dataset", "name", "url", "hash_of_secret"):
            with self.subTest(field=field):
                event = self.event(); event[field] = "PRIVATE-CANARY-DO-NOT-PERSIST"
                with self.assertRaises(c.MonitoringContractError) as denied:
                    c.validate_event(event)
                self.assertNotIn("PRIVATE", str(denied.exception))

    def test_missing_fields_and_claim_flags_rejected(self):
        for field in self.event():
            with self.subTest(field=field):
                event = self.event(); del event[field]
                with self.assertRaises(c.MonitoringContractError):
                    c.validate_event(event)
        for flag in c.FLAGS:
            event = self.event(); event[flag] = not event[flag]
            with self.assertRaises(c.MonitoringContractError):
                c.validate_event(event)

    def test_closed_event_values(self):
        for field, values in {"schema": ("other", None), "event_id": ("A"*32, "x"*32, ""),
                              "resource_id": ("health-person", "b"*64),
                              "observed_at": (True, -1, 1.5, "1000"),
                              "code": ("arbitrary-message", None, {}),
                              "condition": ("failed", 1, [])}.items():
            for value in values:
                with self.subTest(field=field, value=type(value).__name__):
                    event = self.event(); event[field] = value
                    with self.assertRaises(c.MonitoringContractError):
                        c.validate_event(event)

    def test_booleans_not_integer_flags(self):
        for flag in c.FLAGS:
            event = self.event(); event[flag] = int(event[flag])
            with self.assertRaises(c.MonitoringContractError):
                c.validate_event(event)

    def test_duplicate_json_fields_nonfinite_floats(self):
        for raw in (b'{"code":1,"code":2}', b'{"n":1.2}', b'{"n":NaN}', b'{"n":Infinity}'):
            with self.assertRaises(c.MonitoringContractError):
                c.strict_json(raw)

    def test_depth_and_size_bounded(self):
        for value in ({"data": "z"*65536}, [[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[1]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]):
            with self.assertRaises(c.MonitoringContractError):
                c.canonical_bytes(value)
        with self.assertRaises(c.MonitoringContractError):
            c.strict_json(b" "*65537)

    def test_exact_pin_schema(self):
        pin = {"schema": "mra-fixture-monitor-pin/v1", "store_id": "a"*32,
               "sequence": 0, "head_sha256": c.GENESIS_SHA256}
        self.assertEqual(c.validate_pin(pin), pin)
        for changes in ({"sequence": True}, {"head_sha256": "1"*64}, {"unknown": "value"},
                        {"sequence": 2049}, {"store_id": "human-name"}):
            with self.assertRaises(c.MonitoringContractError):
                c.validate_pin({**pin, **changes})

    def test_actor_omits_identity_and_credentials(self):
        self.assertEqual(c.validate_actor({"kind": "human", "authority_revision": 1}),
                         {"kind": "human", "authority_revision": 1})
        for actor in ({"kind": "worker", "authority_revision": 1},
                      {"kind": "human", "authority_revision": True},
                      {"kind": "human", "authority_revision": 1, "token_hash": "0"*64}):
            with self.assertRaises(c.MonitoringContractError):
                c.validate_actor(actor)

    def test_routed_alert_cannot_supply_severity_or_external_route(self):
        event = self.event()
        alert = {"alert_id": event["event_id"], "incident_id": "c"*32, "event": event,
                 **c.RULES[event["code"]], "acknowledged": False, "receiver_pin": None}
        self.assertEqual(c.validate_alert(alert), alert)
        for changes in ({"route": "email"}, {"severity": "low"}, {"runbook": "custom"},
                        {"receiver_pin": {}}, {"acknowledged": 0}, {"alert_id": "d"*32}):
            with self.assertRaises(c.MonitoringContractError):
                c.validate_alert({**alert, **changes})

    def test_only_fault_has_alert(self):
        event = self.event(); event["condition"] = "healthy"
        alert = {"alert_id": event["event_id"], "incident_id": "c"*32, "event": event,
                 **c.RULES[event["code"]], "acknowledged": False, "receiver_pin": None}
        with self.assertRaises(c.MonitoringContractError):
            c.validate_alert(alert)

    def test_serialization_rejects_custom_objects_and_tuples(self):
        for value in (object(), ("value",), {1: "value"}):
            with self.assertRaises(c.MonitoringContractError):
                c.canonical_bytes(value)
