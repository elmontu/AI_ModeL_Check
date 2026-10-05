"""Durability, corruption and concurrency checks for local registration history."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import sysconfig
import tempfile
from threading import Barrier
import time
import unittest
from unittest import mock
import uuid

from model_release_assurance.production_adapters import native
from model_release_assurance.production_registration import contracts, store as stores
from test_production_registration_contracts import registration_fixture, review_fixture

_CHILD = r"""import sys,json,time,os
from pathlib import Path
config=json.loads(sys.argv[1])
sys.path[:0]=config['paths']
from model_release_assurance.production_registration.store import RegistrationStore,StoreError,StoreUnavailable
store=RegistrationStore.open(config['root'],config['store_id'])
Path(config['ready']).write_text('ready',encoding='ascii')
end=time.monotonic()+10
while not Path(config['gate']).exists():
    if time.monotonic()>end: raise SystemExit(24)
    time.sleep(.01)
calls=0
def guard():
    global calls
    calls+=1
    if config['operation']=='crash_before_commit' and calls==2: os._exit(23)
    return 100
try:
    result=store.reserve(config['registration'],guard=guard)
    if config['operation']=='crash_after_commit': os._exit(23)
    print(json.dumps({'ok':True,'ticket':result}),flush=True)
except (StoreError,StoreUnavailable) as error:
    print(json.dumps({'ok':False,'error':type(error).__name__}),flush=True)
"""


class ProductionRegistrationStoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = registration_fixture()[0]
        cls.agency = cls.template["agency_id"]
        cls.project = cls.template["project_id"]

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="mra-registration-store-")
        self.addCleanup(temporary.cleanup)
        self.parent = Path(temporary.name)
        self.root = self.parent / "store # percent%"
        self.store = stores.RegistrationStore.create(self.root)
        self.database = self.root / "registrations.sqlite"
        self.now = 100

    def guard(self):
        return self.now

    def history(self, agency=None, project=None, store=None):
        return (store or self.store).history(agency or self.agency, project or self.project, guard=self.guard)

    def registration(self, *, agency=None, project=None, history=None, **updates):
        agency, project = agency or self.agency, project or self.project
        result = copy.deepcopy(self.template)
        result.update(registration_id=uuid.uuid4().hex, agency_id=agency, project_id=project,
                      history=self.history(agency, project) if history is None else history)
        result.update(updates)
        return contracts.validate_registration(result)

    def reserve(self, registration=None, **kwargs):
        return self.store.reserve(registration or self.registration(), guard=kwargs.pop("guard", self.guard), **kwargs)

    def training(self):
        return self.store.start(self.reserve(), guard=self.guard)

    def completion(self, ticket):
        registration = self.store.get(ticket["registration_id"], guard=self.guard)["registration"]
        review = review_fixture(registration)
        return {**{key:review[key] for key in ("registration_sha256", "artifacts_sha256", "candidate_sha256", "report_sha256")},
            "evidence_envelope_sha256": "d"*64, "evidence_admission_sha256": "e"*64, "review": review}

    def disclosure(self, **changes):
        return {"disclosure_id": uuid.uuid4().hex, "artifact_sha256": "a"*64, "source_reference_sha256": "b"*64,
                "recipient_id": "observed-recipient", "channel": "model_parameters", "occurred_at": self.now, **changes}

    def disclose(self, value=None, *, agency=None, project=None, expected_history=None, store=None):
        agency, project = agency or self.agency, project or self.project
        return (store or self.store).record_disclosure(agency, project, value or self.disclosure(),
            expected_history=self.history(agency, project) if expected_history is None else expected_history,
            guard=self.guard)

    def query(self, sql, arguments=()):
        with closing(sqlite3.connect(self.database)) as connection:
            return connection.execute(sql, arguments).fetchall()

    def change(self, sql, arguments=()):
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute(sql, arguments)
            connection.commit()

    def processes(self, registration, operations):
        gate = self.parent / ("gate-" + uuid.uuid4().hex)
        paths = list(dict.fromkeys([str(Path(__file__).resolve().parents[1] / "src"),
                                  sysconfig.get_path("purelib"), sysconfig.get_path("platlib")]))
        interpreter = getattr(sys, "_base_executable", sys.executable)
        children, ready_files = [], []
        try:
            for operation in operations:
                ready = self.parent / ("ready-" + uuid.uuid4().hex)
                config = dict(paths=paths, root=str(self.root), store_id=self.store.store_id, ready=str(ready),
                              gate=str(gate), registration=registration, operation=operation)
                child = subprocess.Popen([interpreter, "-I", "-S", "-B", "-c", _CHILD, json.dumps(config)],
                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=True, encoding="utf-8", close_fds=True,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                children.append(child)
                ready_files.append(ready)
            deadline = time.monotonic() + 20
            while not all(path.exists() for path in ready_files):
                if any(child.poll() is not None for child in children) or time.monotonic() >= deadline:
                    self.fail("Trusted fixed registration subprocess did not reach barrier")
                time.sleep(.01)
            gate.write_text("go", encoding="ascii")
            outcomes = []
            for child, operation in zip(children, operations):
                output, error = child.communicate(timeout=20)
                if operation.startswith("crash_"):
                    self.assertEqual(child.returncode, 23, error)
                    outcomes.append({"crashed": True})
                else:
                    self.assertEqual(child.returncode, 0, error)
                    self.assertEqual(error, "")
                    outcomes.append(json.loads(output))
            return outcomes
        finally:
            for child in children:
                if child.poll() is None:
                    child.kill()
                child.communicate(timeout=5)

    def test_empty_history_is_unknown_and_clock_observation_does_not_change_it(self):
        history = self.history()
        self.assertEqual(history, {"ledger_id": self.store.store_id,
            "scope_id": contracts.digest({"agency_id": self.agency, "project_id": self.project}), "sequence": 0,
            "head_sha256": "0"*64, "local_registrations": 0, "known_disclosures": 0,
            "external_history": "unknown", "privacy_accounting_supported": False})
        self.now += 1
        self.assertEqual(self.history(), history)
        self.assertEqual(self.store.root, self.root)
        for name in ("root", "store_id"):
            with self.assertRaises(AttributeError):
                setattr(self.store, name, "changed")

    def test_durable_reserve_start_complete_barriers_and_restart(self):
        registration = self.registration()
        with mock.patch.object(native, "run_native", side_effect=AssertionError("store must never fit")):
            ticket = self.reserve(registration)
            self.assertEqual(ticket["registration_sha256"], contracts.digest(registration))
            self.assertEqual(ticket["state"], "registered")
            reopened = stores.RegistrationStore.open(self.root, self.store.store_id)
            record = reopened.get(registration["registration_id"], guard=self.guard)
            self.assertEqual(record["state"], "registered")
            self.assertIsNone(record["training_sequence"])
            ticket = reopened.start(ticket, guard=self.guard)
            reopened = stores.RegistrationStore.open(self.root, self.store.store_id)
            self.assertEqual(reopened.get(registration["registration_id"], guard=self.guard)["training_sequence"], 2)
            completion = self.completion(ticket)
            result = reopened.complete(ticket, completion, guard=self.guard)
        self.assertEqual(set(result), {"registration", "registration_sha256", "state", "completion", "failure_reason",
                                      "registered_sequence", "training_sequence", "terminal_sequence"})
        self.assertEqual((result["state"], result["terminal_sequence"]), ("completed", 3))
        self.assertEqual(result["completion"], completion)
        self.assertFalse(result["completion"]["review"]["model_delivery"])
        self.assertEqual(stores.RegistrationStore.open(self.root, self.store.store_id).get(
            registration["registration_id"], guard=self.guard), result)
        self.assertEqual(self.history()["local_registrations"], 1)
        self.assertEqual(self.query("SELECT count(*) FROM events"), [(3,)])

    def test_illegal_and_replayed_transitions_rejected(self):
        reserved = self.reserve()
        with self.assertRaises(stores.StoreConflict):
            self.store.complete(reserved, self.completion(reserved), guard=self.guard)
        running = self.store.start(reserved, guard=self.guard)
        for ticket in (reserved, running):
            with self.assertRaises(stores.StoreConflict):
                self.store.start(ticket, guard=self.guard)
        self.store.complete(running, self.completion(running), guard=self.guard)
        with self.assertRaises(stores.StoreConflict):
            self.store.complete(running, self.completion(running), guard=self.guard)
        with self.assertRaises(stores.StoreConflict):
            self.store.fail(running["registration_id"], "interrupted", guard=self.guard)
        self.assertEqual(self.history()["sequence"], 3)

    def test_case_rename_cannot_reset_history_and_other_scope_is_distinct(self):
        old = self.history()
        first = self.reserve()
        changed = self.registration(history=old, case_id="renamed-case")
        with self.assertRaises(stores.StoreConflict):
            self.reserve(changed)
        self.reserve(self.registration(agency="other-agency"))
        self.disclose(project="other-project")
        running = self.store.start(first, guard=self.guard)
        changed["history"] = self.history()
        second = self.reserve(changed)
        self.assertEqual(first["scope_id"], second["scope_id"])
        self.assertEqual(self.history()["local_registrations"], 2)
        with self.assertRaises(stores.StoreConflict):
            self.store.complete(running, self.completion(running), guard=self.guard)

    def test_disclosure_stales_start_complete_but_failure_retained(self):
        reserved = self.reserve()
        self.disclose()
        with self.assertRaises(stores.StoreConflict):
            self.store.start(reserved, guard=self.guard)
        failed = self.store.fail(reserved["registration_id"], "history_changed", guard=self.guard)
        self.assertEqual(failed["state"], "failed")
        running = self.training()
        self.disclose()
        with self.assertRaises(stores.StoreConflict):
            self.store.complete(running, self.completion(running), guard=self.guard)
        self.store.fail(running["registration_id"], "history_changed", guard=self.guard)
        self.assertEqual(self.history()["local_registrations"], 2)
        self.assertEqual(self.history()["known_disclosures"], 2)

    def test_failed_pending_history_survives_restart_without_refund_or_resume(self):
        first = self.reserve()
        self.store.fail(first["registration_id"], "training_failed", guard=self.guard)
        pending = self.reserve()
        reopened = stores.RegistrationStore.open(self.root, self.store.store_id)
        self.assertEqual(reopened.get(first["registration_id"], guard=self.guard)["failure_reason"], "training_failed")
        self.assertEqual(reopened.get(pending["registration_id"], guard=self.guard)["state"], "registered")
        self.assertEqual(self.history(store=reopened)["local_registrations"], 2)
        with self.assertRaises(stores.StoreConflict):
            reopened.start(first, guard=self.guard)
        for method in ("delete", "reset", "refund", "retry", "resume"):
            self.assertFalse(hasattr(reopened, method))

    def test_all_ticket_fields_are_bound(self):
        ticket = self.reserve()
        substitutions = {"ledger_id": "b"*32, "registration_id": "b"*32, "registration_sha256": "b"*64,
                         "scope_id": "b"*64, "sequence": 2, "head_sha256": "b"*64, "state": "training"}
        for key, value in substitutions.items():
            with self.subTest(field=key), self.assertRaises(stores.StoreConflict):
                self.store.start({**ticket, key: value}, guard=self.guard)
        self.store.start(ticket, guard=self.guard)

    def test_completion_review_hash_profile_and_shape_bound(self):
        ticket = self.training()
        completion = self.completion(ticket)
        for key in ("registration_sha256", "artifacts_sha256", "candidate_sha256", "report_sha256"):
            changed = copy.deepcopy(completion)
            changed[key] = "f"*64
            with self.subTest(field=key), self.assertRaises(stores.StoreError):
                self.store.complete(ticket, changed, guard=self.guard)
        changed = copy.deepcopy(completion)
        changed["registration_sha256"] = changed["review"]["registration_sha256"] = "f"*64
        with self.assertRaises(stores.StoreConflict):
            self.store.complete(ticket, changed, guard=self.guard)
        changed = copy.deepcopy(completion)
        changed["review"]["profile_id"] = "sklearn-digits"
        with self.assertRaises(stores.StoreConflict):
            self.store.complete(ticket, changed, guard=self.guard)
        for changed in ({**completion, "model_bytes": "forbidden"}, {k:v for k,v in completion.items() if k != "review"},
                        {**completion, "evidence_envelope_sha256": "file://secret"}):
            with self.assertRaises(stores.StoreError):
                self.store.complete(ticket, changed, guard=self.guard)
        self.store.complete(ticket, completion, guard=self.guard)

    def test_disclosure_scope_history_unique_tombstone_and_future_rejection(self):
        disclosure = self.disclosure()
        empty = self.history()
        result = self.disclose(disclosure)
        self.assertEqual((result["local_registrations"], result["known_disclosures"]), (0, 1))
        for agency in (self.agency, "other-agency"):
            with self.subTest(agency=agency), self.assertRaises(stores.StoreConflict):
                self.disclose(disclosure, agency=agency)
        with self.assertRaises(stores.StoreConflict):
            self.disclose(expected_history=empty)
        with self.assertRaises(stores.StoreConflict):
            self.disclose(self.disclosure(occurred_at=self.now+1))
        restored = stores.RegistrationStore.open(self.root, self.store.store_id)
        with self.assertRaises(stores.StoreConflict):
            self.disclose(disclosure, store=restored)
        self.assertEqual(self.history()["sequence"], 1)

    def test_every_observed_channel_retained_without_privacy_cost(self):
        for channel in ("model_parameters", "metrics", "selection_metadata", "refusal"):
            self.disclose(self.disclosure(channel=channel))
        history = self.history()
        self.assertEqual(history["known_disclosures"], 4)
        self.assertEqual(history["external_history"], "unknown")
        self.assertFalse(history["privacy_accounting_supported"])
        self.assertNotIn("epsilon", history)

    def test_guard_denial_at_commit_rolls_back_without_relabelling(self):
        registration = self.registration()
        calls = []
        def guard():
            calls.append(1)
            if len(calls) == 2:
                raise PermissionError("expired authorization")
            return self.now
        with self.assertRaisesRegex(PermissionError, "expired authorization"):
            self.reserve(registration, guard=guard)
        self.assertEqual(len(calls), 2)
        self.assertEqual(self.history()["sequence"], 0)
        ticket = self.store.start(self.reserve(registration), guard=self.guard)
        calls.clear()
        with self.assertRaises(PermissionError):
            self.store.complete(ticket, self.completion(ticket), guard=guard)
        self.assertEqual(self.store.get(ticket["registration_id"], guard=self.guard)["state"], "training")
        self.store.fail(ticket["registration_id"], "evidence_failed", guard=self.guard)

    def test_final_guard_runs_after_expensive_state_revalidation(self):
        registration = self.registration()
        validate = self.store._validate
        validations = []
        def slow_validation(connection):
            state = validate(connection)
            validations.append(1)
            if len(validations) == 2:
                self.now = 101
            return state
        def deadline_guard():
            if self.now >= 101:
                raise PermissionError("authorization expired during event replay")
            return self.now
        with mock.patch.object(self.store, "_validate", side_effect=slow_validation):
            with self.assertRaisesRegex(PermissionError, "expired during event replay"):
                self.reserve(registration, guard=deadline_guard)
        self.assertEqual(len(validations), 2)
        self.assertEqual(self.history()["sequence"], 0)

    def test_guard_required_typed_and_monotone_across_restart(self):
        registration = self.registration()
        for value in (True, -1, 1.0, "100", 2**53, None):
            with self.subTest(value=value), self.assertRaises(stores.StoreError):
                self.reserve(registration, guard=lambda: value)
        with self.assertRaises(stores.StoreError):
            self.reserve(registration, guard=None)
        with self.assertRaises(stores.StoreUnavailable):
            self.reserve(registration, guard=iter([101, 100]).__next__)
        self.now = 101
        self.reserve(registration)
        restored = stores.RegistrationStore.open(self.root, self.store.store_id)
        with self.assertRaises(stores.StoreUnavailable):
            restored.history(self.agency, self.project, guard=lambda: 100)
        self.assertEqual(self.query("SELECT value FROM meta WHERE key='last_clock'"), [("101",)])

    def test_input_output_owned_across_mutating_guard(self):
        registration = self.registration()
        expected = copy.deepcopy(registration)
        def guard():
            registration["case_id"] = "changed"
            registration["source"]["feature_names"][0] = "changed"
            return self.now
        ticket = self.reserve(registration, guard=guard)
        record = self.store.get(ticket["registration_id"], guard=self.guard)
        self.assertEqual(record["registration"], expected)
        record["registration"]["case_id"] = "changed-output"
        self.assertEqual(self.store.get(ticket["registration_id"], guard=self.guard)["registration"], expected)
        original = copy.deepcopy(ticket)
        def start_guard():
            ticket["head_sha256"] = "f"*64
            return self.now
        running = self.store.start(ticket, guard=start_guard)
        self.assertEqual(running["registration_sha256"], original["registration_sha256"])

    def test_invalid_shapes_identifiers_authority_and_history_claims(self):
        registration = self.registration()
        for changed in ({**registration, "extra": 1}, {**registration, "authorization_eligible": True},
                        {**registration, "registration_id": "../path"}):
            with self.assertRaises(stores.StoreError):
                self.reserve(changed)
        for identifier in ("../path", "https://host/object", "", True, "a"*129):
            with self.subTest(identifier=identifier), self.assertRaises(stores.StoreError):
                self.store.history(identifier, self.project, guard=self.guard)
        for changed in (self.disclosure(channel="epsilon"), self.disclosure(occurred_at=True),
                        self.disclosure(recipient_id="https://recipient"), self.disclosure(extra="bad")):
            with self.assertRaises(stores.StoreError):
                self.disclose(changed)
        for key, value in (("external_history", "complete"), ("privacy_accounting_supported", True)):
            changed = self.history()
            changed[key] = value
            with self.assertRaises(stores.StoreError):
                self.disclose(expected_history=changed)
        self.assertEqual(self.history()["sequence"], 0)

    def test_all_failure_reasons_terminal_tombstones_and_no_new_id(self):
        for reason in ("source_changed", "training_failed", "evidence_failed", "history_changed", "interrupted"):
            ticket = self.reserve()
            self.store.fail(ticket["registration_id"], reason, guard=self.guard)
            with self.assertRaises(stores.StoreConflict):
                self.store.fail(ticket["registration_id"], reason, guard=self.guard)
            with self.assertRaises(stores.StoreConflict):
                self.reserve(self.registration(registration_id=ticket["registration_id"]))
        with self.assertRaises(stores.StoreError):
            self.store.fail(ticket["registration_id"], "freeform secret", guard=self.guard)
        self.assertEqual(self.history()["local_registrations"], 5)

    def test_duplicate_reservation_serializes_independent_instances(self):
        registration = self.registration()
        barrier = Barrier(2)
        instances = [stores.RegistrationStore.open(self.root, self.store.store_id) for _ in range(2)]
        def reserve(store):
            barrier.wait(timeout=5)
            try:
                return store.reserve(registration, guard=self.guard)
            except stores.StoreConflict:
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(reserve, instances))
        self.assertEqual(sum(result is not None for result in results), 1)
        self.assertEqual(self.history()["local_registrations"], 1)

    def test_duplicate_reservation_serializes_real_processes(self):
        outcomes = self.processes(self.registration(), ("reserve", "reserve"))
        self.assertEqual(sum(value["ok"] for value in outcomes), 1)
        self.assertEqual(self.history()["sequence"], 1)

    def test_crash_before_commit_has_no_partial_reservation(self):
        registration = self.registration()
        self.processes(registration, ("crash_before_commit",))
        restored = stores.RegistrationStore.open(self.root, self.store.store_id)
        self.assertEqual(self.history(store=restored)["sequence"], 0)
        restored.reserve(registration, guard=self.guard)

    def test_crash_after_commit_retains_pending_reservation(self):
        registration = self.registration()
        self.processes(registration, ("crash_after_commit",))
        restored = stores.RegistrationStore.open(self.root, self.store.store_id)
        record = restored.get(registration["registration_id"], guard=self.guard)
        self.assertEqual(record["state"], "registered")
        self.assertIsNone(record["training_sequence"])
        with self.assertRaises(stores.StoreConflict):
            restored.reserve(registration, guard=self.guard)

    def test_capacity_permanent_for_registrations_disclosures_events(self):
        with mock.patch.object(stores, "MAX_REGISTRATIONS", 2):
            for _ in range(2):
                ticket = self.reserve()
                self.store.fail(ticket["registration_id"], "interrupted", guard=self.guard)
            with self.assertRaises(stores.StoreConflict):
                self.reserve()
        with mock.patch.object(stores, "MAX_DISCLOSURES", 2):
            self.disclose()
            self.disclose()
            with self.assertRaises(stores.StoreConflict):
                self.disclose()
        sequence = self.query("SELECT count(*) FROM events")[0][0]
        with mock.patch.object(stores, "MAX_EVENTS", sequence):
            with self.assertRaises(stores.StoreConflict):
                self.disclose()

    def test_create_open_identity_missing_and_existing_root(self):
        with self.assertRaises(stores.StoreUnavailable):
            stores.RegistrationStore.create(self.root)
        with self.assertRaises(stores.StoreUnavailable):
            stores.RegistrationStore.open(self.root, "f"*32)
        with self.assertRaises(stores.StoreUnavailable):
            stores.RegistrationStore.open(self.parent / "absent", self.store.store_id)
        self.assertFalse((self.parent / "absent").exists())
        self.database.unlink()
        with self.assertRaises(stores.StoreUnavailable):
            self.history()
        self.assertFalse(self.database.exists())

    def test_replaced_or_hardlinked_database_rejected(self):
        alternate = self.parent / "copied.sqlite"
        shutil.copyfile(self.database, alternate)
        self.database.unlink()
        alternate.rename(self.database)
        with self.assertRaises(stores.StoreUnavailable):
            self.history()
        restored = stores.RegistrationStore.open(self.root, self.store.store_id)
        link = self.parent / "linked.sqlite"
        os.link(self.database, link)
        try:
            with self.assertRaises(stores.StoreUnavailable):
                self.history(store=restored)
            with self.assertRaises(stores.StoreUnavailable):
                stores.RegistrationStore.open(self.root, self.store.store_id)
        finally:
            link.unlink()

    def test_path_traversal_unc_reparse_and_unexpected_journal_rejected(self):
        for path in (self.root / ".." / "next", Path(r"\\server\share\registration")):
            with self.subTest(path=str(path)), self.assertRaises(stores.StoreUnavailable):
                stores.RegistrationStore.create(path)
        with mock.patch.object(stores, "_unsafe", return_value=True):
            with self.assertRaises(stores.StoreUnavailable):
                self.history()
        (self.root / "registrations.sqlite-wal").write_bytes(b"unapproved")
        with self.assertRaises(stores.StoreUnavailable):
            self.history()

    def test_deleted_tail_detected_each_operation(self):
        ticket = self.reserve()
        self.store.start(ticket, guard=self.guard)
        self.change("DELETE FROM events WHERE sequence=2")
        for operation in (lambda: self.history(), lambda: self.store.get(ticket["registration_id"], guard=self.guard),
                          lambda: stores.RegistrationStore.open(self.root, self.store.store_id)):
            with self.assertRaises(stores.StoreUnavailable):
                operation()

    def test_restamped_invalid_state_transition_rejected(self):
        running = self.training()
        self.store.complete(running, self.completion(running), guard=self.guard)
        event = json.loads(self.query("SELECT event_json FROM events WHERE sequence=3")[0][0])
        event["kind"] = "training"
        event["payload"] = {"ticket": running}
        raw = stores._encode(event)
        digest = hashlib.sha256(raw).hexdigest()
        self.change("UPDATE events SET event_json=?,event_sha256=? WHERE sequence=3", (raw.decode(), digest))
        self.change("UPDATE meta SET value=? WHERE key='head_sha256'", (digest,))
        with self.assertRaises(stores.StoreUnavailable):
            self.history()

    def test_raw_json_duplicate_nonfinite_oversized_unknown_and_bad_hash_rejected(self):
        self.reserve()
        original = self.query("SELECT event_json,event_sha256 FROM events WHERE sequence=1")[0]
        cases = ('{"schema":1,"schema":2}', '{"unknown":NaN}', '{"unknown":' + '9'*5000 + '}',
                 '{"padding":"' + 'x'*65536 + '"}', '{"unknown":true}', original[0] + " ")
        for raw in cases:
            with self.subTest(length=len(raw)):
                self.change("UPDATE events SET event_json=?,event_sha256=? WHERE sequence=1",
                            (raw, hashlib.sha256(raw.encode()).hexdigest()))
                with self.assertRaises(stores.StoreUnavailable):
                    self.history()
                self.change("UPDATE events SET event_json=?,event_sha256=? WHERE sequence=1", original)
        self.change("UPDATE events SET event_sha256=? WHERE sequence=1", ("f"*64,))
        with self.assertRaises(stores.StoreUnavailable):
            self.history()

    def test_exact_schema_metadata_and_database_size_enforced(self):
        self.change("CREATE TABLE extra (secret TEXT)")
        with self.assertRaises(stores.StoreUnavailable):
            self.history()
        self.change("DROP TABLE extra")
        self.change("INSERT INTO meta VALUES('extra','value')")
        with self.assertRaises(stores.StoreUnavailable):
            self.history()
        self.change("DELETE FROM meta WHERE key='extra'")
        with self.database.open("ab") as stream:
            stream.truncate(stores.MAX_DATABASE_BYTES + 1)
        with self.assertRaises(stores.StoreUnavailable):
            self.history()

    def test_clock_anchor_scope_chain_corruption_detected(self):
        self.reserve()
        self.change("UPDATE meta SET value='99' WHERE key='last_clock'")
        with self.assertRaises(stores.StoreUnavailable):
            self.history()
        self.change("UPDATE meta SET value='100' WHERE key='last_clock'")
        event = json.loads(self.query("SELECT event_json FROM events WHERE sequence=1")[0][0])
        event["previous_scope_sha256"] = "f"*64
        raw = stores._encode(event)
        digest = hashlib.sha256(raw).hexdigest()
        self.change("UPDATE events SET event_json=?,event_sha256=? WHERE sequence=1", (raw.decode(), digest))
        self.change("UPDATE meta SET value=? WHERE key='head_sha256'", (digest,))
        with self.assertRaises(stores.StoreUnavailable):
            self.history()


if __name__ == "__main__":
    unittest.main()
