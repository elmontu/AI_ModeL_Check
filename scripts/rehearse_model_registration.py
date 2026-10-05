#!/usr/bin/env python3
"""Prospectively register and fit fixed public profiles; production stays blocked."""
from __future__ import annotations
import argparse
from dataclasses import asdict
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
import uuid

ROOT = Path(__file__).absolute().parents[1]
if str(ROOT / "src") not in sys.path: sys.path.insert(0, str(ROOT / "src"))
_SPEC = importlib.util.spec_from_file_location("mra_registration_baseline", ROOT / "scripts/verify_build_baseline.py")
_BASELINE = importlib.util.module_from_spec(_SPEC); _SPEC.loader.exec_module(_BASELINE)

from model_release_assurance.production_adapters import native
from model_release_assurance.production_registration.contracts import canonical_bytes, digest
from model_release_assurance.production_registration.profiles import PROFILE_IDS
from model_release_assurance.production_registration.store import RegistrationStore
from model_release_assurance.production_registration.workflow import FLAGS, LocalRegistrationWorkflow
from model_release_assurance.production_evidence.ledger import ReplayLedger
from model_release_assurance.production_evidence.signing import MemoryFixtureEvidenceSigner
from model_release_assurance.production_trust.registry import FixtureTrustRegistry, TrustProfile

SOURCE_FILES = ("scripts/rehearse_model_registration.py", "scripts/verify_build_baseline.py",
                "pyproject.toml", "requirements.lock", "deploy/build/windows-cp312.json")
AGENCY, PROJECT = "fixture-agency", "cross-sector-public-registration"


def _write(path, value):
    with path.open("xb") as stream: stream.write(canonical_bytes(value) + b"\n")


def source_snapshot(root):
    root = Path(root).absolute(); names = set(SOURCE_FILES)
    names.update(path.relative_to(root).as_posix() for path in (root / "src/model_release_assurance").rglob("*.py"))
    if not 8 < len(names) <= 256: raise ValueError("Source inventory outside bound")
    return {name: hashlib.sha256(_BASELINE._read_file(root, name)).hexdigest() for name in sorted(names)}


def run_rehearsal(*, root=ROOT, output, data_root=None, all_profiles=False, max_rows=4096):
    if type(all_profiles) is not bool or type(max_rows) is not int or not 128 <= max_rows <= 4096:
        raise ValueError("Invalid fixture bounds")
    root = Path(root).absolute(); destination = _BASELINE.prepare_output(root, output)
    profiles = tuple(PROFILE_IDS) if all_profiles else ("sklearn-wine",)
    report = {"schema": "mra-model-registration-rehearsal/v1", "status": "failed", "cases": [],
              "profiles": list(profiles), "source": None, "source_unchanged": False,
              "all_research_datasets_tested": False, "errors": [], **FLAGS}
    try:
        source = source_snapshot(root); report["source"] = source
        _write(destination / "batch-intent.json", {"schema": "mra-public-registration-batch/v1",
            "profiles": list(profiles), "max_rows": max_rows, "seed": 20261001,
            "recipe_selection": "one_fixed_native_recipe_per_task_no_outcome_selection",
            "source_sha256": digest(source), "external_disclosure_history": "unknown", **FLAGS})
        store = RegistrationStore.create(destination / "registrations")
        ledger = ReplayLedger.create(destination / "replay-ledger")
        (destination / "cases").mkdir(); (destination / "public-registrations").mkdir()
        clock = lambda: int(time.time())
        initial = store.history(AGENCY, PROJECT, guard=clock)
        report["initial_history"] = initial
        for profile_id in profiles:
            item = {"profile_id": profile_id, "status": "failed", "registration_id": None}
            report["cases"].append(item)
            try:
                now = clock()
                profile = TrustProfile(AGENCY, "public_fixture", "https://registration.example.invalid",
                                       "urn:mra:registered-public-replay", "worker_evidence")
                registry = FixtureTrustRegistry(now=clock, fresh_until=now + 300)
                signer = MemoryFixtureEvidenceSigner(profile, "fixture-worker", "registration-key-" + profile_id,
                                                      now, now + 300)
                registry.enroll(signer.registration, expected_revision=registry.revision)
                public = signer.registration
                _write(destination / "public-registrations" / (profile_id + ".json"),
                    {"profile": asdict(profile), "key_id": public.key_id, "owner_id": public.owner_id,
                     "fingerprint": public.fingerprint, "not_before": public.not_before, "not_after": public.not_after,
                     "public_key_pem": public.public_key_pem.decode("ascii"),
                     "scope": "ephemeral_local_fixture_not_independent_agency_trust"})
                workflow = LocalRegistrationWorkflow(registry, signer, store, ledger)
                case_output = destination / "cases" / profile_id
                result = workflow.run(profile_id, output=case_output, agency_id=AGENCY, project_id=PROJECT,
                    case_id=profile_id, data_root=data_root, max_rows=max_rows)
                item.update(status=result["status"], registration_id=result["registration_id"],
                            registration_sha256=result["registration_sha256"], review=result["review"], error=result["error"])
                if result["status"] != "review_recorded": continue
                # Record observed local candidate/review files. These two known
                # objects do not establish a complete external disclosure roster.
                for filename, channel in (("native/candidate.json", "model_parameters"), ("review.json", "metrics")):
                    bound = 2 * 1024 * 1024 if channel == "model_parameters" else 65536
                    observed = native._read(case_output / filename, bound)
                    observed_sha256 = hashlib.sha256(observed).hexdigest()
                    expected_sha256 = (result["review"]["candidate_sha256"] if channel == "model_parameters"
                                       else hashlib.sha256(canonical_bytes(result["review"]) + b"\n").hexdigest())
                    if observed_sha256 != expected_sha256:
                        raise ValueError("Observed artifact changed after reviewed completion")
                    history = store.history(AGENCY, PROJECT, guard=clock)
                    reference = {"registration_id": result["registration_id"], "relative_artifact": filename,
                                 "scope": "materialized_public_fixture_file_visible_to_local_operator"}
                    disclosure = {"disclosure_id": uuid.uuid4().hex,
                        "artifact_sha256": observed_sha256,
                        "source_reference_sha256": digest(reference), "recipient_id": "local-fixture-operator",
                        "channel": channel, "occurred_at": clock()}
                    _write(case_output / ("observed-" + channel + ".json"), {"reference": reference, "disclosure": disclosure})
                    store.record_disclosure(AGENCY, PROJECT, disclosure, expected_history=history, guard=clock)
                registry.revoke(public.key_id, expected_revision=registry.revision)
            except Exception as error:
                item["error"] = {"type": type(error).__name__, "stage": "profile_workflow"}
        final = store.history(AGENCY, PROJECT, guard=clock)
        reopened = RegistrationStore.open(store.root, store.store_id)
        report["restart_history_matches"] = reopened.history(AGENCY, PROJECT, guard=clock) == final
        report["final_history"] = final; report["registration_store_id"] = store.store_id
        report["source_unchanged"] = source_snapshot(root) == source
        if (report["source_unchanged"] and report["restart_history_matches"]
                and all(item["status"] == "review_recorded" and item.get("error") is None for item in report["cases"])):
            report["status"] = "passed"
    except Exception as error:
        report["errors"].append({"type": type(error).__name__, "stage": "rehearsal"})
    _write(destination / "result.json", report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--data-root", type=Path, help="Existing read-only public research root for four pinned prepared profiles")
    parser.add_argument("--all-profiles", action="store_true", help="Exercise all eight supported public profiles")
    parser.add_argument("--max-rows", type=int, default=4096)
    args = parser.parse_args(argv)
    try:
        report = run_rehearsal(root=ROOT, output=args.output, data_root=args.data_root,
                               all_profiles=args.all_profiles, max_rows=args.max_rows)
    except (ValueError, OSError, _BASELINE.BaselineError) as error:
        print(json.dumps({"status": "refused", "type": type(error).__name__})); return 2
    print(json.dumps({"status": report["status"], "profiles": len(report["cases"]), "errors": report["errors"]}))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__": raise SystemExit(main())
