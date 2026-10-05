"""Actual signed witness fixture and exclusive checkpoint files on one host."""
from __future__ import annotations

from pathlib import Path
import os
import shutil
import stat

from ..production_registry.rehearsal import RegistryFixture
from ..production_registry.store import RegistryStore, StoreConflict, _directories
from ..production_registry.service import FixtureRegistryService
from ..production_registry.contracts import account_id
from .contracts import FLAGS, canonical_bytes, validate_pin
from .reader import RegistryHistoryReader
from .store import WitnessStore, WitnessConflict, WitnessUnavailable
from .service import FixtureWitnessService, WitnessQuarantined


class FileCheckpointSink:
    """Dedicated fixture directory; production independent custody unverified.

    Fresh creation requires explicit pin. This fixture never scans a restored
    directory to invent a floor. Retained pin files can be supplied explicitly
    to recovery, under a separately protected real deployment control.
    """
    def __init__(self, root, initial_pin):
        self.root = Path(root).absolute()
        _directories(self.root.parent)
        self.root.mkdir(exist_ok=False)
        _directories(self.root)
        info = self.root.lstat()
        self._root_identity = (info.st_dev, info.st_ino)
        self._floor = validate_pin(initial_pin)
        self(self._floor)

    def __call__(self, pin):
        pin = validate_pin(pin)
        if any(pin[name] != self._floor[name] for name in ("witness_id", "namespace_id", "registry_id")):
            raise ValueError("Checkpoint identity changed")
        if pin["revision"] < self._floor["revision"] or (pin["revision"] == self._floor["revision"] and pin != self._floor):
            raise ValueError("Checkpoint floor moved backwards")
        self._path_guard()
        raw = canonical_bytes(pin)
        target = self.root / (str(pin["revision"]) + ".json")
        if target.exists():
            if self._read_file(target) != raw:
                raise ValueError("Checkpoint file conflicts")
        else:
            with target.open("xb") as stream:
                stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        self._path_guard()
        if self._read_file(target) != raw:
            raise ValueError("Checkpoint changed after persistence")
        self._floor = validate_pin(pin)

    def _read_file(self, target):
        self._path_guard()
        before = target.lstat()
        def valid(info):
            return (stat.S_ISREG(info.st_mode) and info.st_nlink == 1
                    and not getattr(info, "st_file_attributes", 0) & 0x400
                    and 1 <= info.st_size <= 65536)
        def identity(info):
            return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns
        if not valid(before): raise ValueError("Checkpoint file rejected")
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        with os.fdopen(os.open(target, flags), "rb") as stream:
            opened = os.fstat(stream.fileno())
            if not valid(opened) or identity(opened) != identity(before):
                raise ValueError("Checkpoint changed during open")
            raw = stream.read(65537)
            after = os.fstat(stream.fileno())
        self._path_guard()
        final = target.lstat()
        if not valid(final) or identity(opened) != identity(after) or identity(after) != identity(final) or len(raw) != final.st_size:
            raise ValueError("Checkpoint changed during bounded read")
        return raw

    def _path_guard(self):
        _directories(self.root)
        info = self.root.lstat()
        if (info.st_dev, info.st_ino) != self._root_identity:
            raise ValueError("Checkpoint directory changed")

    @property
    def floor(self):
        return validate_pin(self._floor)


class WitnessFixture:
    def __init__(self, root):
        self.root = Path(root)
        self.registry = RegistryFixture(self.root)
        self.reader = RegistryHistoryReader(self.registry.service)
        history = self.reader.snapshot(guard=self.registry.clock)
        self.witness = WitnessStore.create(self.root / "witness",
            namespace_id=account_id("agency", "project"), registry_id=self.registry.store.store_id,
            initial_history=history, guard=self.registry.clock)
        self.sink = FileCheckpointSink(self.root / "checkpoints", self.witness.initial_pin)
        self.service = FixtureWitnessService(self.registry.service, self.witness,
            expected_pin=self.sink.floor, checkpoint_sink=self.sink)

    def request(self, case="case-a"):
        return self.registry.request(case)

    def commit(self, request):
        return self.service.commit(self.registry.token("operator"), request["case_id"], request)

    def recover(self, request):
        return self.service.recover(self.registry.token("auditor"), request["case_id"], request["request_id"])


def exercise(output):
    """Retain an intent before charge; recover uncertainty and detect rollback."""
    fixture = WitnessFixture(output); registry = fixture.registry
    checks = []
    def check(name, condition):
        checks.append({"name": name, "passed": bool(condition)})
        if not condition: raise RuntimeError("Witness milestone failed")
    def denied(action):
        try: action()
        except (WitnessConflict, WitnessUnavailable, WitnessQuarantined, StoreConflict, ValueError): return True
        return False
    old_history = fixture.reader.snapshot(guard=registry.clock)
    backup = Path(output) / "registry-before.sqlite"
    shutil.copyfile(registry.store.root / "registry.sqlite", backup)
    old_pin = fixture.sink.floor
    witness_backup = Path(output) / "witness-before.sqlite"
    shutil.copyfile(fixture.witness.root / "witness.sqlite", witness_backup)
    first_request = fixture.request()
    first = fixture.commit(first_request)
    check("intent_checkpoint_precedes_registry_charge", first["status"] == "witnessed_metadata"
          and fixture.sink.floor["revision"] > old_pin["revision"])
    again = fixture.commit(first_request)
    check("exact_retry_preserves_one_charge_and_receipt", again["receipt"] == first["receipt"]
          and registry.service.state(registry.token("auditor"), "case-a")["account"]["total_engineering_charge_units"] == 1)
    check("stale_replica_is_rejected", denied(lambda: fixture.witness.observe(old_history,
          expected_pin=fixture.sink.floor, guard=registry.clock)))
    # Real committed outcome with an unavailable witness response. The external
    # intent floor already exists, so the charge remains recoverable metadata.
    second_request = fixture.request("case-b")
    observe = fixture.witness.observe
    calls = [0]
    def interrupted(history, **kwargs):
        calls[0] += 1
        if calls[0] == 2: raise WitnessUnavailable("fixture outage after registry commit")
        return observe(history, **kwargs)
    fixture.witness.observe = interrupted
    failed = denied(lambda: fixture.commit(second_request))
    fixture.witness.observe = observe
    check("witness_outage_after_commit_retains_charge", failed
          and registry.service.state(registry.token("auditor"), "case-b")["account"]["total_engineering_charge_units"] == 2)
    recovered = fixture.recover(second_request)
    check("uncertain_commit_recovers_original_receipt", recovered["status"] == "witnessed_metadata"
          and recovered["receipt"] == registry.service.read(registry.token("auditor"), "case-b", second_request["request_id"]))
    restored_root = Path(output) / "restored-registry"; restored_root.mkdir()
    shutil.copyfile(backup, restored_root / "registry.sqlite")
    restored = FixtureRegistryService(registry.identity, registry.storage,
        RegistryStore.open(restored_root, registry.store.store_id))
    restored_service = FixtureWitnessService(restored, fixture.witness,
        expected_pin=fixture.sink.floor, checkpoint_sink=fixture.sink)
    check("whole_registry_restore_is_rejected", denied(lambda: restored_service.recover(
        registry.token("auditor"), "case-a", first_request["request_id"])))
    restored_witness = Path(output) / "restored-witness"; restored_witness.mkdir()
    shutil.copyfile(witness_backup, restored_witness / "witness.sqlite")
    check("witness_restore_below_external_floor_is_rejected", denied(lambda:
        WitnessStore.open(restored_witness, expected_pin=fixture.sink.floor)))
    other_store = RegistryStore.create(Path(output) / "replacement-registry",
        accounts=[{"agency_id": "agency", "project_id": "project"}])
    other_service = FixtureRegistryService(registry.identity, registry.storage, other_store)
    check("replacement_ledger_id_cannot_reset_namespace", denied(lambda:
        FixtureWitnessService(other_service, fixture.witness, expected_pin=fixture.sink.floor,
                              checkpoint_sink=fixture.sink)))
    status = fixture.witness.status(expected_pin=fixture.sink.floor, guard=registry.clock)
    check("full_history_and_irreversible_intents_are_retained", status["committed_intents"] == 2
          and status["pending_intents"] == 0 and status["reconciled"])
    check("all_results_remain_non_authorizing", first["production_authorized"] is False
          and recovered["model_delivery"] is False and recovered["independent_custody_verified"] is False)
    return {"schema": "mra-fixture-witness-rehearsal/v1", "status": "passed", "checks": checks,
        "summary": {"committed_requests": 2, "engineering_charge_units": 2,
                    "committed_intents": 2, "detected_registry_restore": True,
                    "detected_witness_restore_below_floor": True},
        "evidence": {"first": first, "recovered": recovered, "witness": status,
                     "external_checkpoint": fixture.sink.floor},
        "postgresql_tested": False, "cloud_failover_tested": False,
        "physical_independent_custody_verified": False, **FLAGS}
