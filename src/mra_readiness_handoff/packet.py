"""Portable, pinned local review preparation; no execution or authority."""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import stat
import zipfile

from mra_readiness_dashboard.bundle import (
    BundleError, CRITERIA_DIGEST, MAPPING_DIGEST, COMPARISONS_DIGEST,
    GAP_IDS, SHA_PATTERN, _json, _ordinary, _read_regular, _safe_path,
    canonical_digest, load_snapshot, require,
)
from mra_readiness_intake.checker import (
    BASELINE_PIN, _absolute, _ancestors, digest, report_markdown,
)
from mra_readiness_intake.report import DEPENDENCIES, load_report, validate_report

INTAKE_PIN = "7041b7ddf7cb9a299231b9f9516ef4d5f5a27290f63a7295d5fde56768ab9f1b"
MAX_FILE = 4 * 1024 * 1024
MAX_TOTAL = 16 * 1024 * 1024
CONTENT_NAMES = (
    "README.md", "overview.json", "gaps.json", "work-packages.json",
    "findings.json", "evidence-index.json", "intake-report.json",
    "intake-report.md", "provenance.json", "baseline-manifest.json",
    "intake-manifest.json",
)
ALL_NAMES = CONTENT_NAMES + ("packet-manifest.json",)
PRIMARY = {
    "readiness": "readiness.json", "gaps": "gap-register.json",
    "work_packages": "work-packages.json", "response_template": "agency-response-template.json",
    "evidence_index": "evidence-index.json", "findings": "research-findings.json",
    "baseline_readme": "README.md",
}
GAP_FIELDS = (
    "id", "title", "priority", "condition_type", "status", "local_action_state",
    "blocked_decision_or_claim", "existing_evidence_and_limits", "missing_evidence",
    "proposed_responsible_roles", "appointed_owner_reference", "dependencies",
    "closure_criteria", "independent_verifier_role", "verified_closure_reference",
    "authority_decision_reference", "source_ids",
)
WORK_FIELDS = (
    "gap_id", "package_id", "title", "local_status", "objective", "deliverables",
    "required_evidence", "review_checks", "evidence_matrix", "dependencies",
    "proposed_roles", "agency_owner", "independent_review", "authority_decision",
    "substantive_status", "closure_criteria", "source_ids",
    "can_complete_substantive_gap_locally", "next_permitted_action",
)
FINDING_FIELDS = (
    "overall_verdict", "all_domain_readiness", "comparisons", "agency_practical_margin",
    "agency_acceptance", "authorization_effect", "validation_scope", "numerical_qualification",
    "bindings", "original_evaluation_sha256", "original_completion_sha256",
    "source_admissions", "new_origins", "new_benchmark_executions",
)
SOURCE_FIELDS = ("id", "label", "sha256", "bytes", "classification")
OMISSIONS = (
    "Original captured source bytes and source locations",
    "Raw response drafts, attachment manifests and attachments",
    "Personal metadata and user-supplied free text",
    "Models, datasets and scientific runtime",
    "General advisory DOCX and its filesystem location",
    "Machine identifiers, absolute local paths and local server addresses",
)
LIMITATION = (
    "Local byte integrity and known captured-state checks only. "
    "Omitted original evidence bytes are not verified by this portable packet. "
    "Hashes are not authentication of evidence truth, independent custody, "
    "qualified review, legal permission, agency acceptance or release authority."
)
README = """# Local review preparation packet

Status: prepared_unaccepted. All twelve substantive gaps remain open.
Agency decisions and agency acceptance remain pending. Authorization effect: none.
The packet prepares local review materials only; no outside transmission is performed.

## Contents and limits

The packet contains sanitized, allowlisted projections of the pinned readiness
baseline and the validated sanitized intake summary. The eighteen preserved
comparison rows, including twelve unsupported null rows, remain unchanged.
The original overall finding remains fail and all-domain readiness not_evaluable.
No benchmark, training, fitting, random draws, scientific replay or source fetching
was run to prepare this packet.

Source labels and byte-integrity hashes are an index only. Original captured source
bytes are omitted. This packet cannot verify those omitted bytes offline or establish
evidence truth, independent custody, reviewer independence, legal permission,
agency acceptance, operational readiness or release authority.
Local preparation and structurally complete_unverified intake metadata do not close gaps.

Raw response drafts, attachment manifests, attachments, user free text, personal
metadata, models, datasets, scientific runtime, absolute local paths, local server
addresses and the general advisory DOCX are excluded. The book remains separate.

## Offline verification

Use a separately installed matching local toolkit and its Python standard library:
python -B -m mra_readiness_handoff verify --archive review-packet.zip --archive-sha256 EXPECTED_ARCHIVE_SHA256 --manifest-sha256 EXPECTED_PACKET_MANIFEST_SHA256

Obtain the two expected hashes from the local preparation receipt through a trusted
channel. Hashes copied from an untrusted replacement packet do not establish identity.
The verifier always requires the supported baseline and intake pins. Optional
--baseline-manifest-sha256 and --intake-manifest-sha256 flags assert them explicitly.
Verification reads the bounded archive without extracting files, writing output,
accessing the network or importing scientific execution code.
This archive is not a self-contained executable and does not include the toolkit.

File checksums in packet-manifest.json identify included bytes. The original baseline
and intake manifests bind the exact captured inputs. A successful result confirms
packet byte identity and known local preparation invariants only. Reviewers must
obtain and independently assess the omitted evidence through an authorized process.
"""
# Canonical hashes of permitted fixed-baseline projections, separately pinned from
# the transport manifest. These prevent coherent resealing of altered scope text.
PROJECTION_DIGESTS = {'overview.json': 'ae0f5b5a94d0dba7077f06d123512c69a6d09a464167902876407b4c4e7c951f', 'gaps.json': 'c81312e4e71afe46be4cd2e047a10ae8108ec78c5f5bb8b42dc9edd7956a27d4', 'work-packages.json': 'c5e066698ec2882f2b3a6364bc7c55121aa5eaf2ba99a2108c04380b701c0b9c', 'findings.json': '1ab5b3ccf5a5f2fd53b916d5e0b4484cf10259ba076a29b50cdeba26d7f04720', 'evidence-index.json': '2d5cd26a585d7513f2f0170db88b065eed09294fd8c42ac7354b41146b69a04e', 'provenance.json': 'bd28f30200124e8bec0c7a60c90db72a763144f4f0299ad884d9a7864aed703c'}


def encode(value):
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def _pin(value, label):
    require(isinstance(value, str) and SHA_PATTERN.fullmatch(value), label + " pin is required")


def _bindings(baseline_pin=BASELINE_PIN, intake_pin=INTAKE_PIN):
    require(baseline_pin == BASELINE_PIN and intake_pin == INTAKE_PIN, "Unsupported captured input pin")
    return {"baseline_manifest_sha256": baseline_pin, "intake_manifest_sha256": intake_pin}


def _manifest_entries(raw, schema, paths=None, maximum=512):
    data = _json(raw)
    require(isinstance(data, dict) and set(data) == ({"schema", "files", "as_of"} if schema == "platform-readiness-bundle/1" else {"schema", "files"}) and data["schema"] == schema, "Unknown input manifest schema")
    entries = data["files"]
    require(isinstance(entries, list) and 0 < len(entries) <= maximum, "Invalid input manifest inventory")
    seen = set()
    for entry in entries:
        require(isinstance(entry, dict) and set(entry) == {"path", "sha256", "bytes"}, "Invalid input manifest declaration")
        _safe_path(entry["path"])
        require(entry["path"].casefold() not in seen, "Duplicate input manifest path")
        seen.add(entry["path"].casefold())
        _pin(entry["sha256"], "Input file")
        require(type(entry["bytes"]) is int and 0 <= entry["bytes"] <= 32 * 1024 * 1024, "Invalid input manifest size")
    if paths is not None:
        require([entry["path"] for entry in entries] == list(paths), "Input manifest files differ")
    return data


def _project(snapshot, report, baseline_raw, intake_raw):
    ready = snapshot["readiness.json"]
    gaps = snapshot["gap-register.json"]
    work = snapshot["work-packages.json"]
    findings = snapshot["research-findings.json"]
    evidence = snapshot["evidence-index.json"]
    baseline = _manifest_entries(baseline_raw, "platform-readiness-bundle/1")
    baseline_index = {entry["path"]: entry for entry in baseline["files"]}
    overview = {
        "schema": "local-review-packet-overview/1", "as_of": ready["as_of"],
        "package_status": "prepared_unaccepted", "agency_decisions": "pending",
        "agency_acceptance": "pending", "authorization_effect": "none",
        "substantive_open": 12, "substantive_closed": 0, "local_work_packages": 12,
        "pending_scope_decisions": 11, "unassigned_core_appointments": 4,
        "agency_practical_margin": None, "benchmark_executed": False,
        "docx_unchanged": True,
        "current_book": {key: ready["current_book"][key] for key in ("sha256", "pages")},
        "input_bindings": _bindings(),
        "validation_scope": "Sanitized local review preparation and byte integrity only",
        "limitations": LIMITATION,
    }
    gap_projection = {
        "schema": "local-review-packet-gaps/1", "substantive_open": 12,
        "substantive_closed": 0, "agency_decisions": "pending",
        "authorization_effect": "none",
        "gaps": [{key: row[key] for key in GAP_FIELDS} for row in gaps["gaps"]],
        "frozen_prd22_production_blocker_mapping": gaps["frozen_prd22_production_blocker_mapping"],
    }
    work_projection = {
        "schema": "local-review-packet-work-packages/1", "as_of": ready["as_of"],
        "local_completion_boundary": work["local_completion_boundary"],
        "packages": [{key: row[key] for key in WORK_FIELDS} for row in work["packages"]],
    }
    finding_projection = {"schema": "local-review-packet-findings/1",
                          **{key: findings[key] for key in FINDING_FIELDS}}
    index = {
        "schema": "local-review-packet-evidence-index/1", "as_of": ready["as_of"],
        "original_source_bytes_bundled": False,
        "verification_boundary": LIMITATION,
        "sources": [{key: row[key] for key in SOURCE_FIELDS} for row in evidence["sources"]],
    }
    provenance = {
        "schema": "local-review-packet-provenance/1", "input_bindings": _bindings(),
        "original_primary_file_identities": [
            {"id": key, "sha256": baseline_index[name]["sha256"], "bytes": baseline_index[name]["bytes"]}
            for key, name in PRIMARY.items()
        ],
        "projection_policy": "Fixed allowlist from verified captured baseline; validated sanitized intake report bytes unchanged",
        "omissions": list(OMISSIONS), "limitations": LIMITATION,
        "agency_decisions": "pending", "agency_acceptance": "pending",
        "authorization_effect": "none", "benchmark_executed": False,
    }
    return {
        "README.md": README.encode("utf-8"), "overview.json": encode(overview),
        "gaps.json": encode(gap_projection), "work-packages.json": encode(work_projection),
        "findings.json": encode(finding_projection), "evidence-index.json": encode(index),
        "intake-report.json": report["_files"]["report.json"],
        "intake-report.md": report["_files"]["report.md"],
        "provenance.json": encode(provenance), "baseline-manifest.json": baseline_raw,
        "intake-manifest.json": intake_raw,
    }


def _privacy(raw):
    import re
    text = raw.decode("utf-8")
    require(not re.search(r"(?i)(?:[a-z]:[\\/]|/(?:users|home|tmp|var)/|\\\\|127\.0\.0\.1|localhost)", text),
            "Disallowed local or personal metadata")
    require(not any(ord(char) < 32 and char not in "\n\r\t" for char in text), "Disallowed control character")


def _validate_content(files):
    require(set(files) == set(CONTENT_NAMES), "Packet content differs from allowlist")
    for name, raw in files.items():
        require(isinstance(raw, bytes) and len(raw) <= MAX_FILE, "Packet content exceeds size limit")
        _privacy(raw)
    require(sum(map(len, files.values())) <= MAX_TOTAL, "Packet content exceeds total limit")
    require(files["README.md"] == README.encode("utf-8"), "Packet boundary README changed")
    baseline_raw, intake_raw = files["baseline-manifest.json"], files["intake-manifest.json"]
    require(digest(baseline_raw) == BASELINE_PIN and digest(intake_raw) == INTAKE_PIN, "Captured input manifest pin mismatch")
    baseline = _manifest_entries(baseline_raw, "platform-readiness-bundle/1")
    intake = _manifest_entries(intake_raw, "platform-evidence-intake-report-bundle/1", ("report.json", "report.md"), 2)
    for entry, packet_name in zip(intake["files"], ("intake-report.json", "intake-report.md")):
        require(digest(files[packet_name]) == entry["sha256"] and len(files[packet_name]) == entry["bytes"], "Intake report differs from captured manifest")
    report = validate_report(_json(files["intake-report.json"]), BASELINE_PIN)
    require(files["intake-report.md"] == report_markdown(report), "Intake Markdown differs from validated report")
    parsed = {name: _json(files[name]) for name in (
        "overview.json", "gaps.json", "work-packages.json", "findings.json",
        "evidence-index.json", "provenance.json",
    )}
    require(set(PROJECTION_DIGESTS) == set(parsed), "Projection contract is unavailable")
    for name, data in parsed.items():
        require(files[name] == encode(data) and canonical_digest(data) == PROJECTION_DIGESTS[name], "Fixed baseline projection differs")
    overview, gaps, work, findings, evidence, provenance = (parsed[name] for name in (
        "overview.json", "gaps.json", "work-packages.json", "findings.json", "evidence-index.json", "provenance.json"))
    require(overview["input_bindings"] == provenance["input_bindings"] == _bindings(), "Packet input binding mismatch")
    require([row["id"] for row in gaps["gaps"]] == list(GAP_IDS), "Gap inventory differs")
    require([row["gap_id"] for row in work["packages"]] == list(GAP_IDS), "Work package inventory differs")
    require(canonical_digest({row["id"]: row["closure_criteria"] for row in gaps["gaps"]}) == CRITERIA_DIGEST, "Closure criteria changed")
    require(canonical_digest(gaps["frozen_prd22_production_blocker_mapping"]) == MAPPING_DIGEST, "Production blockers changed")
    for i, (gap, package) in enumerate(zip(gaps["gaps"], work["packages"])):
        require(gap["dependencies"] == package["dependencies"] == list(DEPENDENCIES[i]), "Captured dependencies changed")
        require(gap["status"] == package["substantive_status"] == "open", "Substantive state changed")
        require(all(gap[key] is None for key in ("appointed_owner_reference", "verified_closure_reference", "authority_decision_reference")), "Gap cannot grant authority")
        require(all(package[key] is None for key in ("agency_owner", "independent_review", "authority_decision")), "Package cannot grant authority")
        require(len(package["evidence_matrix"]) == 3 and all(row["state"] == "awaiting_evidence" and row["evidence_reference"] is None and row["verification_reference"] is None for row in package["evidence_matrix"]), "Evidence requirements changed")
    comparison_projection = [{key: row[key] for key in ("domain", "comparator", "verdict", "mean_gain", "lower", "upper")} for row in findings["comparisons"]]
    require(canonical_digest(comparison_projection) == COMPARISONS_DIGEST and len(findings["comparisons"]) == 18, "Preserved comparisons changed")
    require(sum(row["mean_gain"] is None for row in findings["comparisons"]) == 12 and findings["overall_verdict"] == "fail" and findings["all_domain_readiness"] == "not_evaluable", "Unsupported findings changed")
    baseline_index = {entry["path"]: entry for entry in baseline["files"]}
    expected_primary = [{"id": key, "sha256": baseline_index[name]["sha256"], "bytes": baseline_index[name]["bytes"]} for key, name in PRIMARY.items()]
    require(provenance["original_primary_file_identities"] == expected_primary, "Primary file identities differ")
    source_index = {entry["path"]: entry for entry in baseline["files"]}
    require(len(evidence["sources"]) == 28 and len({row["id"] for row in evidence["sources"]}) == 28, "Evidence index differs")
    for row in evidence["sources"]:
        require(set(row) == set(SOURCE_FIELDS), "Source metadata exceeds allowlist")
        require(any(entry["sha256"] == row["sha256"] and entry["bytes"] == row["bytes"] for entry in source_index.values()), "Source identity is not in captured manifest")
    return parsed


def _zip_bytes(files):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED, allowZip64=False) as archive:
        for name in ALL_NAMES:
            item = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            item.compress_type = zipfile.ZIP_STORED
            item.create_system = 3
            item.external_attr = (stat.S_IFREG | 0o644) << 16
            item.extra = b""
            item.comment = b""
            archive.writestr(item, files[name])
    raw = stream.getvalue()
    require(len(raw) <= MAX_TOTAL, "Packet archive exceeds total limit")
    return raw


def _inventory(files):
    return [{"path": name, "sha256": digest(files[name]), "bytes": len(files[name])} for name in CONTENT_NAMES]


def _packet_manifest(files):
    return {"schema": "local-review-handoff-packet/1", "input_bindings": _bindings(), "files": _inventory(files)}


def _verify_bytes(raw, expected_archive_sha256, expected_manifest_sha256, baseline_pin, intake_pin):
    _pin(expected_archive_sha256, "Archive")
    _pin(expected_manifest_sha256, "Packet manifest")
    _bindings(baseline_pin, intake_pin)
    require(len(raw) <= MAX_TOTAL and digest(raw) == expected_archive_sha256, "Archive size or digest pin mismatch")
    files = {}
    try:
        with zipfile.ZipFile(io.BytesIO(raw), "r", allowZip64=False) as archive:
            entries = archive.infolist()
            require(not archive.comment and len(entries) == len(ALL_NAMES) and len(entries) <= 20, "Invalid archive inventory")
            require([item.filename for item in entries] == list(ALL_NAMES), "Archive has missing, extra, duplicate or unordered entries")
            require(len({item.filename.casefold() for item in entries}) == len(entries), "Case-aliased archive entry")
            total = 0
            for item in entries:
                _safe_path(item.filename)
                require(item.filename in ALL_NAMES and not item.is_dir(), "Unexpected archive path")
                require(item.compress_type == zipfile.ZIP_STORED and item.flag_bits == 0 and not item.extra and not item.comment, "Unsupported archive encoding or metadata")
                require(item.create_system == 3 and item.external_attr == (stat.S_IFREG | 0o644) << 16, "Special or linked archive entry")
                require(item.date_time == (1980, 1, 1, 0, 0, 0) and 0 <= item.file_size <= MAX_FILE and item.compress_size == item.file_size, "Invalid archive timestamp or size")
                total += item.file_size
                require(total <= MAX_TOTAL, "Archive content exceeds total limit")
                with archive.open(item, "r") as stream:
                    content = stream.read(MAX_FILE + 1)
                    require(len(content) == item.file_size and len(content) <= MAX_FILE and stream.read(1) == b"", "Archive content size differs")
                files[item.filename] = content
    except (OSError, ValueError, zipfile.BadZipFile, zipfile.LargeZipFile, RuntimeError, NotImplementedError, OverflowError) as error:
        if isinstance(error, BundleError):
            raise
        raise BundleError("Invalid or unreadable packet archive") from error
    manifest_raw = files.pop("packet-manifest.json")
    require(digest(manifest_raw) == expected_manifest_sha256, "Packet manifest pin mismatch")
    manifest = _json(manifest_raw)
    require(isinstance(manifest, dict) and set(manifest) == {"schema", "input_bindings", "files"} and manifest["schema"] == "local-review-handoff-packet/1", "Unknown packet manifest schema")
    require(manifest["input_bindings"] == _bindings(baseline_pin, intake_pin), "Packet manifest input binding mismatch")
    require(manifest == _packet_manifest(files) and manifest_raw == encode(manifest), "Packet inventory differs from declared bytes")
    parsed = _validate_content(files)
    require(_zip_bytes({**files, "packet-manifest.json": manifest_raw}) == raw, "Noncanonical archive structure")
    return {
        "overview": parsed["overview.json"], "manifest": manifest,
        "inventory": manifest["files"],
        "_archive_bytes": raw, "_manifest_bytes": manifest_raw,
        "_readme_bytes": files["README.md"],
        "_archive_sha256": expected_archive_sha256,
        "_manifest_sha256": expected_manifest_sha256,
    }


def _read_single(path, limit):
    path = _absolute(path)
    _ancestors(path.parent)
    before = _ordinary(path)
    require(getattr(before, "st_nlink", 1) == 1, "Hard-linked packet file is not accepted")
    raw = _read_regular(path.parent, path.name, limit)
    after = _ordinary(path)
    require(getattr(after, "st_nlink", 1) == 1 and (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns), "Packet file changed while validating")
    _ancestors(path.parent)
    return raw


def verify_archive(archive, expected_archive_sha256, expected_manifest_sha256,
                   expected_baseline_manifest_sha256=BASELINE_PIN,
                   expected_intake_manifest_sha256=INTAKE_PIN):
    """Verify bounded ordinary archive bytes offline without extraction or writes."""
    raw = _read_single(archive, MAX_TOTAL)
    return _verify_bytes(raw, expected_archive_sha256, expected_manifest_sha256,
                         expected_baseline_manifest_sha256, expected_intake_manifest_sha256)


def _receipt(archive_raw, manifest_raw):
    return {
        "schema": "local-review-handoff-receipt/1",
        "archive_sha256": digest(archive_raw), "archive_bytes": len(archive_raw),
        "packet_manifest_sha256": digest(manifest_raw),
        "input_bindings": _bindings(), "package_status": "prepared_unaccepted",
        "agency_decisions": "pending", "agency_acceptance": "pending",
        "authorization_effect": "none", "substantive_open": 12,
        "substantive_closed": 0, "benchmark_executed": False,
        "validation_scope": LIMITATION,
    }


def load_packet(directory, expected_archive_sha256, expected_manifest_sha256,
                expected_baseline_manifest_sha256=BASELINE_PIN,
                expected_intake_manifest_sha256=INTAKE_PIN):
    """Freshly verify every served byte and receipt on every call."""
    root = _absolute(directory)
    _ancestors(root)
    archive_raw = _read_single(root / "review-packet.zip", MAX_TOTAL)
    manifest_raw = _read_single(root / "packet-manifest.json", MAX_FILE)
    receipt_raw = _read_single(root / "receipt.json", 65536)
    require(digest(manifest_raw) == expected_manifest_sha256, "External manifest pin mismatch")
    receipt = _json(receipt_raw)
    require(receipt_raw == encode(receipt) and receipt == _receipt(archive_raw, manifest_raw), "Packet receipt differs from prepared state")
    result = _verify_bytes(archive_raw, expected_archive_sha256, expected_manifest_sha256,
                           expected_baseline_manifest_sha256, expected_intake_manifest_sha256)
    require(result["_manifest_bytes"] == manifest_raw, "External and internal packet manifests differ")
    require(_read_single(root / "review-packet.zip", MAX_TOTAL) == archive_raw and _read_single(root / "packet-manifest.json", MAX_FILE) == manifest_raw and _read_single(root / "receipt.json", 65536) == receipt_raw, "Packet changed during validation")
    _ancestors(root)
    return result


def _write_exclusive(path, raw):
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def build_packet(bundle, manifest_sha256, intake_report, intake_manifest_sha256, output):
    """Create a new local directory only after verifying exact supported inputs."""
    _bindings(manifest_sha256, intake_manifest_sha256)
    bundle_root, report_root, output_root = (_absolute(value) for value in (bundle, intake_report, output))
    for input_root in (bundle_root, report_root):
        require(output_root != input_root and not output_root.is_relative_to(input_root) and not input_root.is_relative_to(output_root), "Output must be separate from captured inputs")
    _ancestors(output_root.parent)
    require(not output_root.exists() and not output_root.is_symlink(), "Output already exists")
    snapshot = load_snapshot(bundle_root, manifest_sha256)
    report = load_report(report_root, intake_manifest_sha256, manifest_sha256)
    baseline_raw = _read_single(bundle_root / "manifest.json", 1024 * 1024)
    intake_raw = _read_single(report_root / "manifest.json", 65536)
    require(digest(baseline_raw) == manifest_sha256 and digest(intake_raw) == intake_manifest_sha256, "Input manifests changed")
    files = _project(snapshot, report, baseline_raw, intake_raw)
    _validate_content(files)
    manifest_raw = encode(_packet_manifest(files))
    archive_raw = _zip_bytes({**files, "packet-manifest.json": manifest_raw})
    receipt = _receipt(archive_raw, manifest_raw)
    _verify_bytes(archive_raw, receipt["archive_sha256"], receipt["packet_manifest_sha256"], manifest_sha256, intake_manifest_sha256)
    try:
        output_root.mkdir()
        _ordinary(output_root, directory=True)
        _write_exclusive(output_root / "review-packet.zip", archive_raw)
        _write_exclusive(output_root / "packet-manifest.json", manifest_raw)
        # Written last: no complete receipt is left by an interrupted preparation.
        _write_exclusive(output_root / "receipt.json", encode(receipt))
    except OSError as error:
        raise BundleError("Cannot create new packet output") from error
    load_packet(output_root, receipt["archive_sha256"], receipt["packet_manifest_sha256"], manifest_sha256, intake_manifest_sha256)
    return receipt
