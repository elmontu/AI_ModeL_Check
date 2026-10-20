"""Fail-closed, stdlib-only draft preparation checks; no evidence execution."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re

from mra_readiness_dashboard.bundle import (
    BundleError, GAP_IDS, SHA_PATTERN, _json, _ordinary, _read_regular,
    _safe_path, load_snapshot, require,
)

IntakeError = BundleError
BASELINE_PIN = '397f8734a1b5b248e97fe116cea01f638039254fdc129b1df9b1e62ab4c99c13'
MAX_ATTACHMENT = 16 * 1024 * 1024
MAX_TOTAL = 64 * 1024 * 1024
MAX_FILES = 256
STATES = ('missing', 'partial', 'complete_unverified')
SCOPE_IDS = tuple(f'S{i:02d}' for i in range(1, 12))
APPOINTMENT_IDS = ('service_owner', 'data_owner', 'security_owner', 'scientific_owner')
REQUIREMENT_IDS = tuple(f'{gap}-E{i:02d}' for gap in GAP_IDS for i in range(1, 4))
CLASSES = ('public_official', 'public_synthetic', 'local_preparation')
INTERPRETATION = ('Local structural preparation only. Complete_unverified means supplied draft metadata and attachment bytes are present; it does not authenticate appointments, verify truth or independence, establish lawful authority, close gaps, accept policy, authorize a pilot or release, or change preserved findings. All agency decisions remain pending.')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _encode(value):
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + '\n').encode('utf-8')


def _ancestors(path):
    for parent in reversed((path, *path.parents)):
        _ordinary(parent, directory=True)


def _absolute(path):
    candidate = Path(os.path.abspath(path))
    require(not any(str(part).endswith((' ', '.')) for part in candidate.parts), 'Unsafe absolute path')
    require(not str(candidate).startswith(('\\\\', '//')), 'UNC paths are not accepted')
    # Reject ADS even on hosts where colons have no special meaning.
    require(':' not in str(candidate)[len(candidate.anchor):], 'Alternate data streams are not accepted')
    return candidate


def _read_pinned(path, pin, limit):
    require(isinstance(pin, str) and SHA_PATTERN.fullmatch(pin), 'A lowercase SHA-256 input pin is required')
    path = _absolute(path)
    _ancestors(path.parent)
    info = _ordinary(path)
    require(getattr(info, 'st_nlink', 1) == 1, 'Hard-linked input is not accepted')
    raw = _read_regular(path.parent, path.name, limit)
    require(digest(raw) == pin, 'Input digest pin mismatch')
    return raw


def _date(value):
    require(isinstance(value, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)', value), 'Timestamp must be a timezone-aware ISO instant')
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        require(parsed.tzinfo is not None and parsed.utcoffset() is not None, 'Timestamp has no timezone')
        return parsed.astimezone(timezone.utc)
    except (ValueError, OverflowError) as error:
        raise IntakeError('Invalid timestamp') from error


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _metadata(value):
    require(value is None or (isinstance(value, str) and len(value) <= 4096 and not any(ord(c) < 32 and c not in '\n\t\r' for c in value)), 'Invalid draft metadata type or size')


def _keys(row, template):
    require(isinstance(row, dict) and set(row) == set(template), 'Missing or unknown response fields')


def _rows(rows, templates, key):
    require(isinstance(rows, list) and len(rows) == len(templates) and all(isinstance(row, dict) for row in rows), 'Missing required response rows')
    require([row.get(key) for row in rows] == [row[key] for row in templates], 'Missing, duplicate, unknown or unordered identifiers')
    for row, template in zip(rows, templates):
        _keys(row, template)


def _refs(value, attachments):
    require(isinstance(value, list) and len(value) <= MAX_FILES and all(_text(item) for item in value) and len(value) == len(set(value)), 'Invalid evidence references')
    require(all(item in attachments for item in value), 'Unresolved evidence reference')


def _reference(value, attachments):
    _metadata(value)
    require(not _text(value) or value in attachments, 'Unresolved evidence reference')


def _attachments(root, path, pin):
    root = _absolute(root)
    _ancestors(root)
    raw = _read_pinned(path, pin, 1024 * 1024)
    manifest = _json(raw)
    require(isinstance(manifest, dict) and set(manifest) == {'schema', 'files'} and manifest['schema'] == 'platform-evidence-intake-attachments/1', 'Unknown evidence manifest schema')
    entries = manifest['files']
    require(isinstance(entries, list) and len(entries) <= MAX_FILES, 'Invalid evidence manifest entries')
    by_id, paths, identities, total = {}, set(), set(), 0
    for entry in entries:
        require(isinstance(entry, dict) and set(entry) == {'id', 'path', 'sha256', 'bytes', 'evidence_class'}, 'Invalid evidence declaration')
        identifier = entry['id']
        require(isinstance(identifier, str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,63}', identifier) and identifier not in by_id, 'Invalid or duplicate evidence identifier')
        relative = entry['path']
        safe = _safe_path(relative)
        require(relative.casefold() not in paths, 'Duplicate or case-aliased evidence path')
        require(isinstance(entry['sha256'], str) and SHA_PATTERN.fullmatch(entry['sha256']) and type(entry['bytes']) is int and 0 <= entry['bytes'] <= MAX_ATTACHMENT and entry['evidence_class'] in CLASSES, 'Invalid evidence metadata')
        candidate = root.joinpath(*safe.parts)
        before = _ordinary(candidate)
        require(getattr(before, 'st_nlink', 1) == 1, 'Hard-linked evidence is not accepted')
        identity = (before.st_dev, before.st_ino)
        require(identity not in identities, 'Aliased evidence file')
        body = _read_regular(root, relative, MAX_ATTACHMENT)
        total += len(body)
        require(total <= MAX_TOTAL and len(body) == entry['bytes'] and digest(body) == entry['sha256'], 'Evidence digest or byte size mismatch')
        by_id[identifier] = entry
        paths.add(relative.casefold())
        identities.add(identity)
    require(_read_pinned(path, pin, 1024 * 1024) == raw, 'Evidence manifest changed')
    return by_id


def _row(identifier, missing, present, *, gap_id=None):
    state = 'complete_unverified' if not missing else ('partial' if present else 'missing')
    row = {'id': identifier, 'state': state, 'missing_fields': sorted(missing), 'errors': []}
    if gap_id is not None:
        row['gap_id'] = gap_id
    return row


def _states(rows):
    return {state: sum(row['state'] == state for row in rows) for state in STATES}


def check_intake(*, bundle, manifest_sha256, response, response_sha256, evidence_root,
                 evidence_manifest, evidence_manifest_sha256, as_of=None):
    """Validate pinned bytes and produce privacy-preserving preparation states."""
    from .report import DEPENDENCIES
    require(manifest_sha256 == BASELINE_PIN, 'Unsupported baseline manifest pin')
    snapshot = load_snapshot(bundle, manifest_sha256)
    require([gap['dependencies'] for gap in snapshot['gap-register.json']['gaps']] == [list(value) for value in DEPENDENCIES], 'Baseline dependencies differ from the fixed intake contract')
    template = snapshot['agency-response-template.json']
    require([row['id'] for row in template['scope_decisions']] == list(SCOPE_IDS) and [row['id'] for row in template['core_appointments']] == list(APPOINTMENT_IDS) and [row['requirement_id'] for gap in template['gap_responses'] for row in gap['requirement_responses']] == list(REQUIREMENT_IDS), 'Baseline response identifiers differ from the fixed intake contract')
    raw = _read_pinned(response, response_sha256, 2 * 1024 * 1024)
    candidate = _json(raw)
    _keys(candidate, template)
    require(candidate['schema'] == template['schema'], 'Unknown response schema')
    for key in ('agency_decisions', 'authorization_effect', 'agency_acceptance', 'agency_practical_margin', 'protected_data_authority', 'instructions'):
        require(candidate[key] == template[key] and type(candidate[key]) is type(template[key]), 'Agency authority and baseline instructions must remain pending')
    _metadata(candidate['revision'])
    revision_present = _text(candidate['revision']) and candidate['revision'].strip() != template['revision']
    checked_at = datetime.now(timezone.utc) if as_of is None else _date(as_of)
    if isinstance(checked_at, datetime):
        checked_at = checked_at.astimezone(timezone.utc)
    require(checked_at <= datetime.now(timezone.utc), 'Checking instant is in the future')
    attachments = _attachments(evidence_root, evidence_manifest, evidence_manifest_sha256)
    scope_rows, appointment_rows, requirement_rows = [], [], []
    _rows(candidate['scope_decisions'], template['scope_decisions'], 'id')
    for item, base in zip(candidate['scope_decisions'], template['scope_decisions']):
        require(item['title'] == base['title'] and item['status'] == 'pending', 'Scope decisions must remain pending')
        _keys(item['requested_fields'], base['requested_fields'])
        _refs(item['evidence_references'], attachments)
        fields = {'decision': item['decision'], 'accountable_role': item['accountable_role'], 'exact_revision_reference': item['exact_revision_reference']}
        fields.update({f'requested_fields.{key}': value for key, value in item['requested_fields'].items()})
        for value in fields.values():
            _metadata(value)
        missing = [key for key, value in fields.items() if not _text(value)]
        if not item['evidence_references']:
            missing.append('evidence_references')
        if not revision_present:
            missing.append('revision')
        scope_rows.append(_row(item['id'], missing, any(_text(value) for value in fields.values()) or bool(item['evidence_references'])))
    _rows(candidate['core_appointments'], template['core_appointments'], 'id')
    for item, base in zip(candidate['core_appointments'], template['core_appointments']):
        require(item['role'] == base['role'] and item['status'] == 'pending', 'Core appointments must remain pending')
        fields = ('appointed_person', 'appointment_reference', 'accepted_remit_reference', 'conflict_declaration_reference')
        for key in fields:
            _metadata(item[key])
            if key != 'appointed_person':
                _reference(item[key], attachments)
        missing = [key for key in fields if not _text(item[key])]
        if not revision_present:
            missing.append('revision')
        appointment_rows.append(_row(item['id'], missing, any(_text(item[key]) for key in fields)))
    _rows(candidate['gap_responses'], template['gap_responses'], 'gap_id')
    for item, base in zip(candidate['gap_responses'], template['gap_responses']):
        require(item['status'] == 'pending' and all(item[key] is None for key in ('agency_owner', 'independent_review', 'authority_decision')), 'Gap owner, review and authority cannot be assigned by intake')
        _refs(item['evidence_references'], attachments)
        _rows(item['requirement_responses'], base['requirement_responses'], 'requirement_id')
        for requirement in item['requirement_responses']:
            fields = tuple(key for key in requirement if key != 'requirement_id')
            for key in fields:
                _metadata(requirement[key])
            for key in ('evidence_reference', 'independent_verification', 'custodian_reference'):
                _reference(requirement[key], attachments)
            require(not _text(requirement['disposition']) or requirement['disposition'] == 'draft', 'Requirement disposition must remain draft')
            evidence_id = requirement['evidence_reference']
            sha = requirement['evidence_sha256']
            if _text(sha):
                require(SHA_PATTERN.fullmatch(sha) and _text(evidence_id) and sha == attachments[evidence_id]['sha256'], 'Requirement evidence hash does not match an attachment')
            if _text(requirement['observed_at']):
                require(_date(requirement['observed_at']) <= checked_at, 'Observation timestamp is in the future')
            missing = [key for key in fields if not _text(requirement[key])]
            if not revision_present:
                missing.append('revision')
            if _text(evidence_id) and evidence_id not in item['evidence_references']:
                missing.append('gap_evidence_references')
            requirement_rows.append(_row(requirement['requirement_id'], missing, any(_text(requirement[key]) for key in fields), gap_id=item['gap_id']))
    counts = {}
    for prefix, rows in (('scope', scope_rows), ('appointments', appointment_rows), ('requirements', requirement_rows)):
        counts.update({f'{prefix}_{state}': count for state, count in _states(rows).items()})
    gap_summaries = []
    for gap in snapshot['gap-register.json']['gaps']:
        gap_summaries.append({'gap_id': gap['id'], 'dependencies': gap['dependencies'], **_states([row for row in requirement_rows if row['gap_id'] == gap['id']])})
    report = {'schema': 'platform-evidence-intake-report/1', 'checked_at': checked_at.isoformat().replace('+00:00', 'Z'),
              'result': 'complete_unverified' if all(row['state'] == 'complete_unverified' for row in scope_rows + appointment_rows + requirement_rows) else 'incomplete',
              'counts': counts, 'scope_decisions': scope_rows, 'core_appointments': appointment_rows, 'requirements': requirement_rows,
              'gap_summaries': gap_summaries, 'input_bindings': {'baseline_manifest_sha256': manifest_sha256, 'response_sha256': response_sha256, 'evidence_manifest_sha256': evidence_manifest_sha256},
              'agency_decisions': 'pending', 'agency_acceptance': 'pending', 'authorization_effect': 'none', 'substantive_open': 12, 'substantive_closed': 0,
              'benchmark_executed': False, 'interpretation': INTERPRETATION}
    require(_read_pinned(response, response_sha256, 2 * 1024 * 1024) == raw, 'Response changed during validation')
    # Recheck all attachments after interpreting the response; no mutable cache.
    _attachments(evidence_root, evidence_manifest, evidence_manifest_sha256)
    return report


def report_markdown(report):
    lines = ['# Local evidence-intake preparation report', '', f"Checked at: {report['checked_at']}", '', f"Result: {report['result']}", '', INTERPRETATION, '', 'All 12 substantive gaps remain open; agency acceptance remains pending. No benchmark was executed.', '', '| Group | Missing | Partial | Complete, unverified |', '| --- | ---: | ---: | ---: |']
    for prefix in ('scope', 'appointments', 'requirements'):
        lines.append(f"| {prefix} | {report['counts'][prefix + '_missing']} | {report['counts'][prefix + '_partial']} | {report['counts'][prefix + '_complete_unverified']} |")
    lines.extend(['', '| Item | State | Missing fields |', '| --- | --- | --- |'])
    for key in ('scope_decisions', 'core_appointments', 'requirements'):
        for row in report[key]:
            lines.append(f"| {row['id']} | {row['state']} | {', '.join(row['missing_fields']) or 'none'} |")
    return ('\n'.join(lines) + '\n').encode('utf-8')


def _overlaps(left, right):
    return left == right or left in right.parents or right in left.parents


def write_report(report, output, *, protected_paths):
    """Create a new report directory; no existing report or input is overwritten."""
    from .report import validate_report
    validate_report(report, report.get('input_bindings', {}).get('baseline_manifest_sha256'))
    target = _absolute(output)
    _ancestors(target.parent)
    require(not target.exists() and not target.is_symlink(), 'Output must be a new directory')
    require(bool(protected_paths), 'Explicit input exclusion paths are required')
    for protected in protected_paths:
        require(not _overlaps(target, _absolute(protected)), 'Output overlaps an input or protected directory')
    files = {'report.json': _encode(report), 'report.md': report_markdown(report)}
    manifest = {'schema': 'platform-evidence-intake-report-bundle/1', 'files': [{'path': name, 'sha256': digest(raw), 'bytes': len(raw)} for name, raw in files.items()]}
    target.mkdir(exist_ok=False)
    # Manifest is written last. A failed write has no valid completed manifest.
    for name, raw in files.items():
        with (target / name).open('xb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    encoded = _encode(manifest)
    with (target / 'manifest.json').open('xb') as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    return digest(encoded)
