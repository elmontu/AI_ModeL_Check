#!/usr/bin/env python3
"""Validate non-deployable private-cloud design intent without provisioning anything."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).absolute().parents[1]
MAX_PLAN_BYTES = 128 * 1024
ENVIRONMENTS = ("dev", "staging", "prod")
RESOURCE_ROLES = ("account", "network", "identity", "artifact", "evidence", "data", "key", "registry", "witness", "audit", "backup")
ENDPOINT_ROLES = ("private_ingress", "agency_identity", "quarantine_objects", "artifact_store", "evidence_store",
                  "scoped_data_access", "job_queue", "key_service", "registry", "independent_witness", "audit_sink", "backup_restore")
NETWORK_CONTROLS = {"private_ingress": True, "private_dns": True, "tls_required": True,
                    "egress": "default_deny", "lateral": "default_deny", "metadata": "default_deny", "public_object_urls": False}
CUSTODY_CONTROLS = {"separate_environments": True, "independent_witness_administration": True, "api_bulk_data_grant": False,
                   "workers_use_scoped_job_grants": True, "immutable_artifact_and_evidence_versions": True,
                   "backup_restore_requires_quarantine": True, "gateway_is_only_recipient_delivery_path": True,
                   "worker_release_key_grant": False, "worker_registry_write_grant": False, "recipient_direct_store_grant": False}
BLOCKERS = [
    "Agency scope, classification, accountable owners and approvals remain pending (PRD-01/02).",
    "Provider and primary/recovery regions remain deferred by the user; compute runtime is unselected and jurisdictional custody unapproved.",
    "Provider infrastructure, resolved endpoints, DNS/TLS, network and administrative isolation are not implemented or tested (PRD-05).",
    "Agency identity, protected-data intake, keys, isolated workers, registry/witness and sole delivery gateway require their production gates (PRD-06 through PRD-18).",
    "Independent recovery, operations and agency go-live acceptance remain unproven (PRD-20 through PRD-27).",
]
NONCLAIMS = [
    "Valid design means this document meets preparatory constraints; it is not deployed infrastructure-as-code or an approval.",
    "Logical references and distinct administrator labels do not prove IAM, network isolation, independent custody or rollback resistance.",
    "A loopback public-fixture rehearsal does not demonstrate cloud DNS/TLS, workload isolation, private-data readiness or authorized model delivery.",
]


class PlanValidationError(ValueError):
    pass


def _fields(value, names, location):
    if type(value) is not dict:
        raise PlanValidationError(location + " must be an object")
    missing, unknown = set(names) - set(value), set(value) - set(names)
    if missing or unknown:
        raise PlanValidationError(location + " has missing or unknown fields: missing=" + repr(sorted(missing)) + "; unknown=" + repr(sorted(unknown, key=str)))


def _exact(value, expected, location):
    if type(value) is not type(expected) or value != expected:
        raise PlanValidationError(location + " must remain " + repr(expected))


def _fixed_object(value, expected, location):
    _fields(value, expected, location)
    for name, fixed in expected.items():
        _exact(value[name], fixed, location + "." + name)


def validate_plan(plan):
    """Return the validated design dictionary; reject any production-enabling variation."""
    _fields(plan, ("schema", "status", "deployment", "scope", "environments", "controls", "endpoint_roles", "local_rehearsal"), "plan")
    _exact(plan["schema"], "agency-private-cloud-blueprint/v1", "schema")
    _exact(plan["status"], "design_only", "status")
    _fixed_object(plan["deployment"], {"provider": None, "runtime": None, "primary_region": None, "recovery_region": None,
                  "decision_status": "provider_and_regions_deferred_by_user", "runtime_status": "unselected", "cloud_deployable": False}, "deployment")
    _fixed_object(plan["scope"], {"data": "public_or_synthetic_only", "agency_approvals": "pending",
                  "private_data_admission": False, "model_delivery": False}, "scope")
    _fields(plan["environments"], ENVIRONMENTS, "environments")
    references = set()
    for name in ENVIRONMENTS:
        location = "environments." + name
        environment = plan["environments"][name]
        _fields(environment, ("state", "cloud_enabled", "resources", "administrative_domains"), location)
        _exact(environment["state"], "planned_disabled", location + ".state")
        _exact(environment["cloud_enabled"], False, location + ".cloud_enabled")
        _fields(environment["resources"], RESOURCE_ROLES, location + ".resources")
        _fields(environment["administrative_domains"], ("application_admin", "witness_admin"), location + ".administrative_domains")
        for group in ("resources", "administrative_domains"):
            for role, reference in environment[group].items():
                if type(reference) is not str or not re.fullmatch(r"logical:" + name + r":[a-z][a-z0-9-]{0,63}", reference):
                    raise PlanValidationError(location + "." + group + "." + role + " must be an environment-scoped unresolved logical reference")
                if reference in references:
                    raise PlanValidationError("Resource and administrator references must be distinct: " + reference)
                references.add(reference)
    _fields(plan["controls"], ("network", "custody"), "controls")
    _fixed_object(plan["controls"]["network"], NETWORK_CONTROLS, "controls.network")
    _fixed_object(plan["controls"]["custody"], CUSTODY_CONTROLS, "controls.custody")
    _fixed_object(plan["endpoint_roles"], dict.fromkeys(ENDPOINT_ROLES, "unresolved"), "endpoint_roles")
    _fixed_object(plan["local_rehearsal"], {"allowed_environments": ["dev", "staging"], "bind_address": "127.0.0.1",
                  "transport": "plain_http_local_only", "data": "public_fixture_only", "private_data_admission": False,
                  "model_delivery": False}, "local_rehearsal")
    return plan


def _object(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise PlanValidationError("Duplicate JSON field: " + name)
        result[name] = value
    return result


def _nonfinite(value):
    raise PlanValidationError("Non-finite JSON value is forbidden: " + value)


def _read_plan(path):
    with Path(path).open("rb") as stream:
        content = stream.read(MAX_PLAN_BYTES + 1)
    if len(content) > MAX_PLAN_BYTES:
        raise PlanValidationError("Infrastructure plan exceeds size limit")
    return content


def _parse_plan(content):
    try:
        plan = json.loads(content.decode("utf-8"), object_pairs_hook=_object, parse_constant=_nonfinite)
    except PlanValidationError:
        raise
    except (UnicodeError, ValueError, RecursionError) as error:
        raise PlanValidationError("Invalid infrastructure plan JSON: " + str(error)) from error
    return validate_plan(plan)


def load_plan(path):
    """Read bounded strict JSON and return a validated design; never write or provision."""
    return _parse_plan(_read_plan(path))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=ROOT / "deploy/agency-private-cloud/blueprint.json")
    args = parser.parse_args(argv)
    result = {"cloud_deployable": False, "blockers": BLOCKERS, "nonclaims": NONCLAIMS}
    try:
        content = _read_plan(args.plan)
        _parse_plan(content)
        result.update(status="valid_design", sha256=hashlib.sha256(content).hexdigest())
    except (OSError, PlanValidationError) as error:
        result.update(status="invalid_design", errors=[str(error)])
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "valid_design" else 1


if __name__ == "__main__":
    raise SystemExit(main())
