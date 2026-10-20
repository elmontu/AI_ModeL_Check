"""Fail-closed validation of captured preparation bytes, never agency authority."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat

GAP_IDS = tuple(f"G{i:02d}" for i in range(1, 13))
ROOT_FILES = frozenset(("readiness.json", "gap-register.json", "work-packages.json", "agency-response-template.json", "evidence-index.json", "research-findings.json", "README.md"))
CRITERIA_DIGEST = "6d8d2cef0ff04d1249aa2bec0162e7f218c014ff372f97053d8cf9db5bf961a1"
MAPPING_DIGEST = "e8aba7b2616ad4a26d2ac79e2204198005cb2e866a5576df2173b30b1f43cccb"
COMPARISONS_DIGEST = "35498c218569d0726330d290aed2cb7f4f6e9b8aba2720dc1f83963368e39725"
SHA_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
MAX_FILE_BYTES = 32 * 1024 * 1024
MAX_BUNDLE_BYTES = 128 * 1024 * 1024


class BundleError(ValueError):
    """The captured snapshot cannot be safely presented."""


def require(condition, message):
    if not condition:
        raise BundleError(message)


def canonical_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def _pairs(items):
    value = {}
    for key, item in items:
        require(key not in value, "Duplicate JSON key")
        value[key] = item
    return value


def _json(raw):
    from math import isfinite

    def finite_float(token):
        value = float(token)
        require(isfinite(value), "Non-finite JSON number")
        return value

    def bounded_int(token):
        try:
            return int(token)
        except ValueError:
            raise BundleError("Invalid JSON") from None

    try:
        parsed = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_pairs, parse_int=bounded_int, parse_float=finite_float, parse_constant=lambda value: (_ for _ in ()).throw(BundleError("Non-finite JSON number")))
        pending = [parsed]
        while pending:
            current = pending.pop()
            if isinstance(current, str):
                require(not any(0xD800 <= ord(character) <= 0xDFFF for character in current), "Invalid JSON")
            elif isinstance(current, dict):
                pending.extend(current)
                pending.extend(current.values())
            elif isinstance(current, list):
                pending.extend(current)
        return parsed
    except (UnicodeError, json.JSONDecodeError, RecursionError) as error:
        raise BundleError("Invalid JSON") from error


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _strings(value, *, empty=False):
    return isinstance(value, list) and (empty or bool(value)) and all(_text(x) for x in value)


def _safe_path(value):
    require(_text(value) and len(value) <= 240 and "\\" not in value and ":" not in value and not any(ord(c) < 32 or c in '<>"|?*' for c in value), "Unsafe bundle path")
    path = PurePosixPath(value)
    require(not path.is_absolute() and str(path) == value and all(p not in (".", "..") and not p.endswith((".", " ")) for p in path.parts), "Unsafe bundle path")
    require(all(not re.fullmatch(r"(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?", p) for p in path.parts), "Unsafe bundle path")
    return path


def _ordinary(path, *, directory=False):
    try:
        info = path.lstat()
    except OSError as error:
        raise BundleError("Missing or inaccessible bundle path") from error
    require(not path.is_symlink() and not (getattr(info, "st_file_attributes", 0) & 0x400), "Links and reparse points are not accepted")
    require(stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode), "Bundle path is not an ordinary file or directory")
    return info


def _read_regular(root, relative, limit):
    parts = _safe_path(relative).parts
    for index in range(1, len(parts)):
        _ordinary(root.joinpath(*parts[:index]), directory=True)
    path = root.joinpath(*parts)
    before = _ordinary(path)
    require(before.st_size <= limit, "Bundle file too large")
    try:
        with path.open("rb") as stream:
            opened = os.fstat(stream.fileno())
            require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) == (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns), "File changed while opening")
            raw = stream.read(limit + 1)
            after_opened = os.fstat(stream.fileno())
    except OSError as error:
        raise BundleError("Cannot read captured bundle") from error
    after = _ordinary(path)
    identity = lambda item: (item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns)
    require(identity(before) == identity(after_opened) == identity(after) and len(raw) == before.st_size and len(raw) <= limit, "File changed while reading")
    return raw


def _schema(data, expected):
    require(isinstance(data, dict) and data.get("schema") == expected, "Unknown or missing schema")


def _validate_dependencies(rows, id_key):
    edges = {}
    for row in rows:
        dependencies = row.get("dependencies")
        require(_strings(dependencies, empty=True) and len(dependencies) == len(set(dependencies)) and all(x in GAP_IDS for x in dependencies), "Invalid dependencies")
        edges[row[id_key]] = dependencies
    visiting, visited = set(), set()

    def walk(node):
        require(node not in visiting, "Dependency cycle")
        if node in visited:
            return
        visiting.add(node)
        for other in edges[node]:
            walk(other)
        visiting.remove(node)
        visited.add(node)

    for node in edges:
        walk(node)


def _ids(rows, key, expected=GAP_IDS):
    require(isinstance(rows, list) and len(rows) == len(expected) and all(isinstance(x, dict) for x in rows), "Missing required rows")
    require([x.get(key) for x in rows] == list(expected), "Missing, duplicate or unordered identifiers")


def _validate(snapshot):
    ready, gaps, work, response, evidence, findings = (snapshot[name] for name in ("readiness.json", "gap-register.json", "work-packages.json", "agency-response-template.json", "evidence-index.json", "research-findings.json"))
    _schema(ready, "platform-readiness/1")
    required = {"as_of": "2026-10-19", "substantive_open": 12, "substantive_closed": 0, "local_work_packages_prepared": 12, "agency_decisions": "pending", "pending_scope_decisions": 11, "unassigned_core_appointments": 4, "authorization_effect": "none", "benchmark_executed": False, "docx_unchanged": True, "validation_scope": "Local preparation and captured evidence integrity only"}
    for key, value in required.items():
        require(key in ready and type(ready[key]) is type(value) and ready[key] == value, "Readiness state is missing or inconsistent")
    _schema(gaps, "project-remediation-gap-register/1.0")
    require(str(gaps.get("revision")) == "7" and gaps.get("substantive_gap_closure_claimed") is False and gaps.get("agency_approval_or_release_authority_granted") is False and gaps.get("future_execution_authorized_by_this_register") is False, "Unsupported gap-register authority or revision")
    rows = gaps.get("gaps")
    _ids(rows, "id")
    for gap in rows:
        require(gap.get("status") == "open" and gap.get("priority") in ("P0", "P1", "P2"), "Gap is not open")
        require(all(key in gap and gap[key] is None for key in ("appointed_owner_reference", "verified_closure_reference", "authority_decision_reference")), "Gap authority cannot be inferred")
        require(all(_text(gap.get(key)) for key in ("title", "condition_type", "local_action_state", "blocked_decision_or_claim", "existing_evidence_and_limits", "next_action", "independent_verifier_role")), "Incomplete gap details")
        require(all(_strings(gap.get(key)) for key in ("missing_evidence", "proposed_responsible_roles", "closure_criteria", "source_ids")), "Incomplete gap evidence requirements")
    _validate_dependencies(rows, "id")
    require(canonical_digest({g["id"]: g["closure_criteria"] for g in rows}) == CRITERIA_DIGEST, "Historical closure criteria changed")
    require(canonical_digest(gaps.get("frozen_prd22_production_blocker_mapping")) == MAPPING_DIGEST, "Historical production blocker mapping changed")
    _schema(work, "platform-readiness-work-packages/1")
    packages = work.get("packages")
    _ids(packages, "gap_id")
    for package, gap in zip(packages, rows):
        require(package.get("local_status") == "prepared" and package.get("substantive_status") == "open", "Invalid local preparation status")
        require(all(key in package and package[key] is None for key in ("agency_owner", "independent_review", "authority_decision")), "Work package cannot grant authority")
        require(all(_text(package.get(key)) for key in ("title", "objective")), "Incomplete work package")
        require(all(_strings(package.get(key)) for key in ("deliverables", "required_evidence", "review_checks", "proposed_roles")), "Missing package requirements")
        require(package.get("dependencies") == gap["dependencies"], "Package dependencies differ from gap register")
        matrix = package.get("evidence_matrix")
        require(isinstance(matrix, list) and len(matrix) > 0 and all(isinstance(x, dict) for x in matrix), "Missing evidence matrix")
        require(len({x.get("id") for x in matrix if _text(x.get("id"))}) == len(matrix), "Invalid evidence-matrix identifiers")
        for entry in matrix:
            require(all(_text(entry.get(key)) for key in ("id", "requirement", "existing_coverage", "required_receipt", "verification_question")), "Incomplete evidence matrix")
            require(entry.get("state") == "awaiting_evidence" and all(key in entry and entry[key] is None for key in ("evidence_reference", "verification_reference")), "Evidence matrix is not pending")
    _validate_dependencies(packages, "gap_id")
    _schema(response, "platform-readiness-agency-response/1")
    require(response.get("agency_decisions") == "pending", "Agency decision status missing")
    scope, appointments, answers = (response.get(key) for key in ("scope_decisions", "core_appointments", "gap_responses"))
    require(isinstance(scope, list) and len(scope) == 11 and all(isinstance(x, dict) and _text(x.get("id")) and _text(x.get("title")) and x.get("status") == "pending" and "decision" in x and x["decision"] is None and x.get("evidence_references") == [] for x in scope), "Scope responses must remain pending")
    require(len({x["id"] for x in scope}) == 11, "Duplicate scope decisions")
    require(isinstance(appointments, list) and len(appointments) == 4 and all(isinstance(x, dict) and _text(x.get("id")) and _text(x.get("role")) and x.get("status") == "pending" and all(key in x and x[key] is None for key in ("appointed_person", "appointment_reference")) for x in appointments), "Appointments must remain pending")
    require(len({x["id"] for x in appointments}) == 4, "Duplicate appointments")
    _ids(answers, "gap_id")
    require(all(x.get("status") == "pending" and x.get("evidence_references") == [] and all(key in x and x[key] is None for key in ("agency_owner", "independent_review", "authority_decision")) for x in answers), "Agency gap responses must remain pending")
    _schema(evidence, "platform-readiness-evidence-index/1")
    sources = evidence.get("sources")
    require(isinstance(sources, list) and len(sources) > 0 and all(isinstance(x, dict) for x in sources), "Missing evidence index")
    require(len({x.get("id") for x in sources if _text(x.get("id"))}) == len(sources), "Invalid evidence identifiers")
    for source in sources:
        require(all(_text(source.get(key)) for key in ("id", "label", "path")) and SHA_PATTERN.fullmatch(str(source.get("sha256", ""))) and type(source.get("bytes")) is int and source["bytes"] >= 0, "Invalid evidence metadata")
        require(Path(source["path"]).is_absolute(), "Original evidence path must be absolute metadata")
        captured = source.get("captured_path")
        _safe_path(captured)
        require(captured.startswith("evidence/") and captured in snapshot["_files"], "Evidence index must bind a captured file")
        captured_bytes = snapshot["_files"][captured]
        require(len(captured_bytes) == source["bytes"] and hashlib.sha256(captured_bytes).hexdigest() == source["sha256"], "Evidence metadata does not match captured bytes")
    _schema(findings, "preserved-research-findings/1")
    require(findings.get("overall_verdict") == "fail" and findings.get("all_domain_readiness") == "not_evaluable" and _text(findings.get("validation_scope")), "Preserved failure state is missing")
    comparisons = findings.get("comparisons")
    require(isinstance(comparisons, list) and len(comparisons) == 18 and all(isinstance(x, dict) and all(key in x for key in ("domain", "comparator", "verdict", "mean_gain", "lower", "upper")) for x in comparisons), "All 18 preserved comparisons are required")
    projection = [{key: row[key] for key in ("domain", "comparator", "verdict", "mean_gain", "lower", "upper")} for row in comparisons]
    require(canonical_digest(projection) == COMPARISONS_DIGEST, "Preserved comparison rows changed")


def load_snapshot(bundle, manifest_sha256):
    """Re-read pinned manifest, every declared file and interpreted states."""
    require(isinstance(manifest_sha256, str) and SHA_PATTERN.fullmatch(manifest_sha256), "A lowercase SHA-256 manifest pin is required")
    root = Path(os.path.abspath(bundle))
    for ancestor in reversed((root, *root.parents)):
        _ordinary(ancestor, directory=True)
    manifest_raw = _read_regular(root, "manifest.json", 1024 * 1024)
    require(hashlib.sha256(manifest_raw).hexdigest() == manifest_sha256, "Manifest pin mismatch")
    manifest = _json(manifest_raw)
    _schema(manifest, "platform-readiness-bundle/1")
    entries = manifest.get("files")
    require(isinstance(entries, list) and len(entries) >= len(ROOT_FILES) and len(entries) <= 512, "Invalid manifest entries")
    raw_files, casefold_names, total = {}, set(), 0
    for entry in entries:
        require(isinstance(entry, dict) and set(entry) == {"path", "sha256", "bytes"}, "Invalid manifest file declaration")
        name = entry["path"]
        _safe_path(name)
        require(name.casefold() not in casefold_names and name != "manifest.json" and SHA_PATTERN.fullmatch(str(entry["sha256"])) and type(entry["bytes"]) is int and 0 <= entry["bytes"] <= MAX_FILE_BYTES, "Invalid or duplicate manifest file")
        raw = _read_regular(root, name, MAX_FILE_BYTES)
        total += len(raw)
        require(total <= MAX_BUNDLE_BYTES and len(raw) == entry["bytes"] and hashlib.sha256(raw).hexdigest() == entry["sha256"], "Captured file digest or byte size mismatch")
        raw_files[name] = raw
        casefold_names.add(name.casefold())
    require(ROOT_FILES <= raw_files.keys(), "Required bundle files are missing")
    # Opaque captured evidence is not interpreted as a new approval schema.
    # Undeclared files are ignored and can never be served.
    snapshot = {name: _json(raw_files[name]) for name in ROOT_FILES if name.endswith(".json")}
    snapshot["_files"] = raw_files
    _validate(snapshot)
    require(_read_regular(root, "manifest.json", 1024 * 1024) == manifest_raw, "Manifest changed during validation")
    for ancestor in reversed((root, *root.parents)):
        _ordinary(ancestor, directory=True)
    snapshot["_files"] = raw_files
    snapshot["_manifest_sha256"] = manifest_sha256
    return snapshot
