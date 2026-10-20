"""Pinned, reread-on-every-request validation for privacy-preserving receipts."""
from __future__ import annotations

from datetime import datetime, timezone
from mra_readiness_dashboard.bundle import GAP_IDS, SHA_PATTERN, _json, _ordinary, _read_regular, require
from .checker import (APPOINTMENT_IDS, BASELINE_PIN, INTERPRETATION, REQUIREMENT_IDS, SCOPE_IDS,
                      STATES, _absolute, _ancestors, _date, _states, digest, report_markdown)

DEPENDENCIES = ((), ('G01',), ('G01',), ('G03',), ('G02', 'G03'), ('G02', 'G03', 'G04'), ('G01',), ('G01', 'G07'), ('G07', 'G08'), ('G01', 'G08', 'G09'), ('G02', 'G05', 'G06', 'G08', 'G09', 'G10', 'G12'), ())
REQUESTED = (
    'agency_reference jurisdiction programme task intended_users_and_decision harmful_errors human_review benefit_rationale',
    'model_family model_version preprocessing source_and_dependency_provenance parent_and_component_lineage',
    'dataset_and_snapshot_references population source_authority classification residency retention repeated_records cross_source_linkage cohort_conditions sensitive_or_protected_fields_schema_reference',
    'recipient_reference purpose interface retained_copies_and_outputs onward_use prior_disclosure_history_reference',
    'protected_unit adjacency raw_to_derived_contribution_map public_feature_status membership_and_attribute_scope mechanism_and_composition_assumptions',
    'decision_horizon_and_origin target_and_unit metric_and_direction positive_practical_margin benefit_and_cost_rationale credible_alternatives_and_information harmful_error_limits affected_group_criteria uncertainty_and_selection_rules',
    'justified_tolerance_or_cumulative_budget protected_scope_reference prior_spending_and_disclosure accountant_and_assumptions unknown_history_treatment',
    'recipient_realistic_threats required_attacks_and_interfaces controls stopping_and_blocking_rules permitted_exclusions independent_review_qualification',
    'accepted_exclusions unresolved_issues package_data_interface_recipient_change_triggers new_disclosure_or_invalid_evidence_triggers maintenance_and_retirement_requirements policy_change_triggers',
    'sponsor_reference core_owner_appointments policy_delegation release_delegation role_combinations_and_conflicts independent_reviewer_appointments',
    'dataset_rows_and_bytes tables_and_sources entity_and_linkage_counts history_depth update_cadence extraction_limits concurrent_jobs_and_releases resource_and_cost_envelope service_and_recovery_objectives',
)
REQUIREMENT_FIELDS = {'evidence_reference', 'evidence_sha256', 'custodian_reference', 'configuration_or_scope_revision', 'observed_at', 'independent_verification', 'disposition', 'revision', 'gap_evidence_references'}
APPOINTMENT_FIELDS = {'appointed_person', 'appointment_reference', 'accepted_remit_reference', 'conflict_declaration_reference', 'revision'}
REPORT_KEYS = {'schema', 'checked_at', 'result', 'counts', 'scope_decisions', 'core_appointments', 'requirements', 'gap_summaries', 'input_bindings', 'agency_decisions', 'agency_acceptance', 'authorization_effect', 'substantive_open', 'substantive_closed', 'benchmark_executed', 'interpretation'}


def _report_rows(rows, expected_ids, kind):
    require(isinstance(rows, list) and len(rows) == len(expected_ids) and all(isinstance(row, dict) for row in rows), 'Incomplete report rows')
    require([row.get('id') for row in rows] == list(expected_ids), 'Invalid report identifiers')
    for index, row in enumerate(rows):
        keys = {'id', 'state', 'missing_fields', 'errors'} | ({'gap_id'} if kind == 'requirements' else set())
        require(set(row) == keys and row['state'] in STATES and row['errors'] == [], 'Invalid report row fields')
        if kind == 'scope':
            allowed = {'decision', 'accountable_role', 'exact_revision_reference', 'evidence_references', 'revision'} | {f'requested_fields.{name}' for name in REQUESTED[index].split()}
        elif kind == 'appointments':
            allowed = APPOINTMENT_FIELDS
        else:
            allowed = REQUIREMENT_FIELDS
            require(row['gap_id'] == row['id'].split('-')[0], 'Requirement belongs to another gap')
        missing = row['missing_fields']
        require(isinstance(missing, list) and all(isinstance(field, str) and field in allowed for field in missing) and missing == sorted(set(missing)), 'Invalid missing-field report')
        require((not missing) == (row['state'] == 'complete_unverified'), 'Inconsistent structural completeness')
        if row['state'] == 'missing':
            required = allowed - {'revision', 'gap_evidence_references'}
            require(required <= set(missing), 'Missing row omits absent fields')


def validate_report(report, expected_baseline_manifest_sha256):
    require(expected_baseline_manifest_sha256 == BASELINE_PIN, 'Unsupported baseline manifest pin')
    require(isinstance(report, dict) and set(report) == REPORT_KEYS and report['schema'] == 'platform-evidence-intake-report/1', 'Unknown report schema or fields')
    require(_date(report['checked_at']) <= datetime.now(timezone.utc), 'Report checking instant is in the future')
    require(report['agency_decisions'] == 'pending' and report['agency_acceptance'] == 'pending' and report['authorization_effect'] == 'none' and type(report['substantive_open']) is int and report['substantive_open'] == 12 and type(report['substantive_closed']) is int and report['substantive_closed'] == 0 and report['benchmark_executed'] is False and report['interpretation'] == INTERPRETATION, 'Report cannot grant authority or change preserved state')
    bindings = report['input_bindings']
    require(isinstance(bindings, dict) and set(bindings) == {'baseline_manifest_sha256', 'response_sha256', 'evidence_manifest_sha256'} and all(isinstance(pin, str) and SHA_PATTERN.fullmatch(pin) for pin in bindings.values()) and bindings['baseline_manifest_sha256'] == expected_baseline_manifest_sha256, 'Report input binding mismatch')
    groups = (('scope', 'scope_decisions', SCOPE_IDS), ('appointments', 'core_appointments', APPOINTMENT_IDS), ('requirements', 'requirements', REQUIREMENT_IDS))
    expected_counts = {}
    for prefix, key, identifiers in groups:
        _report_rows(report[key], identifiers, prefix)
        expected_counts.update({f'{prefix}_{state}': count for state, count in _states(report[key]).items()})
    require(isinstance(report['counts'], dict) and report['counts'] == expected_counts and all(type(count) is int for count in report['counts'].values()), 'Report counts are inconsistent')
    complete = all(row['state'] == 'complete_unverified' for _, key, _ in groups for row in report[key])
    require(report['result'] == ('complete_unverified' if complete else 'incomplete'), 'Report result is inconsistent')
    summaries = report['gap_summaries']
    require(isinstance(summaries, list) and len(summaries) == 12 and all(isinstance(row, dict) for row in summaries) and [row.get('gap_id') for row in summaries] == list(GAP_IDS), 'Report gap summaries are incomplete')
    edges = {}
    for index, row in enumerate(summaries):
        require(set(row) == {'gap_id', 'dependencies', *STATES}, 'Invalid summary fields')
        require(all(type(row[state]) is int and row[state] == _states([item for item in report['requirements'] if item['gap_id'] == row['gap_id']])[state] for state in STATES), 'Report summary counts differ')
        deps = row['dependencies']
        require(deps == list(DEPENDENCIES[index]), 'Report dependencies differ from the captured baseline')
        require(isinstance(deps, list) and len(deps) == len(set(deps)) and all(isinstance(dep, str) and dep in GAP_IDS and dep != row['gap_id'] for dep in deps), 'Invalid report dependencies')
        edges[row['gap_id']] = deps
    visited = set()
    def walk(node, trail):
        require(node not in trail, 'Report dependency cycle')
        if node not in visited:
            for dependency in edges[node]:
                walk(dependency, trail | {node})
            visited.add(node)
    for node in edges:
        walk(node, set())
    return report


def load_report(report_directory, expected_manifest_sha256, expected_baseline_manifest_sha256):
    """Read pinned report JSON and Markdown fresh; serve only declared bytes."""
    require(isinstance(expected_manifest_sha256, str) and SHA_PATTERN.fullmatch(expected_manifest_sha256), 'Report manifest pin is required')
    root = _absolute(report_directory)
    _ancestors(root)
    require(getattr(_ordinary(root / 'manifest.json'), 'st_nlink', 1) == 1, 'Hard-linked report manifest is not accepted')
    raw_manifest = _read_regular(root, 'manifest.json', 65536)
    require(digest(raw_manifest) == expected_manifest_sha256, 'Report manifest pin mismatch')
    manifest = _json(raw_manifest)
    require(isinstance(manifest, dict) and set(manifest) == {'schema', 'files'} and manifest['schema'] == 'platform-evidence-intake-report-bundle/1', 'Unknown report bundle schema')
    entries = manifest['files']
    require(isinstance(entries, list) and len(entries) == 2 and all(isinstance(entry, dict) for entry in entries) and [entry.get('path') for entry in entries] == ['report.json', 'report.md'], 'Report bundle files differ')
    files = {}
    for entry in entries:
        require(set(entry) == {'path', 'sha256', 'bytes'} and isinstance(entry['sha256'], str) and SHA_PATTERN.fullmatch(entry['sha256']) and type(entry['bytes']) is int and 0 <= entry['bytes'] <= 1024 * 1024, 'Invalid report file declaration')
        info = _ordinary(root / entry['path'])
        require(getattr(info, 'st_nlink', 1) == 1, 'Hard-linked report is not accepted')
        raw = _read_regular(root, entry['path'], 1024 * 1024)
        require(digest(raw) == entry['sha256'] and len(raw) == entry['bytes'], 'Report file digest or size mismatch')
        files[entry['path']] = raw
    report = validate_report(_json(files['report.json']), expected_baseline_manifest_sha256)
    require(files['report.md'] == report_markdown(report), 'Report Markdown does not match checked summary')
    require(_read_regular(root, 'manifest.json', 65536) == raw_manifest, 'Report manifest changed during validation')
    _ancestors(root)
    return {**report, '_files': files, '_manifest_sha256': expected_manifest_sha256}
