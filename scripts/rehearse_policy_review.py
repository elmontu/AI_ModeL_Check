#!/usr/bin/env python3
"""Run one public Wine policy-before-fit and independent-review rehearsal."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
from itertools import islice
import json
import os
from pathlib import Path
import platform
import stat
import sys

ROOT = Path(__file__).absolute().parents[1]
if str(ROOT / 'src') not in sys.path:
    sys.path.insert(0, str(ROOT / 'src'))
_SPEC = importlib.util.spec_from_file_location('mra_review_baseline', ROOT / 'scripts/verify_build_baseline.py')
_BASELINE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_BASELINE)
from model_release_assurance.production_review.contracts import FLAGS
from model_release_assurance.production_review.rehearsal import exercise

SOURCE_FILES = ('scripts/rehearse_policy_review.py', 'scripts/verify_build_baseline.py',
    'pyproject.toml', 'requirements.lock', 'src/model_release_assurance/__init__.py',
    'src/model_release_assurance/analyzers/attack.py', 'src/model_release_assurance/portfolio_statistics.py',
    *('src/model_release_assurance/production_review/' + name + '.py' for name in
      ('__init__', 'contracts', 'store', 'service', 'authorization', 'rehearsal')),
    *('src/model_release_assurance/production_registration/' + name + '.py' for name in
      ('__init__', 'contracts', 'store', 'profiles', 'workflow')),
    *('src/model_release_assurance/production_evidence/' + name + '.py' for name in
      ('__init__', 'contracts', 'signing', 'verifier', 'replay', 'ledger')))
REQUIRED_CHECKS = frozenset({'policy_required_before_any_fit',
    'policy_approved_before_registration_and_fit', 'owner_and_alias_cannot_assess',
    'operator_cannot_approve', 'actual_native_training_and_authenticated_replay',
    'independent_current_reviews_are_usable', 'retained_evidence_tamper_invalidates_reviews',
    'post_result_policy_weakening_refused',
    'recipient_change_refused', 'old_campaign_evidence_cannot_be_rebound',
    'delegation_is_campaign_scoped', 'expired_or_revoked_delegation_denied',
    'current_revocation_invalidates_reviews', 'restart_preserves_history_without_current_authority',
    'all_results_remain_non_authorizing', 'source_unchanged'})
LIMITATIONS = [
    'One fixed public Wine sample and native recipe; this is not evaluation of all datasets or external attacks.',
    'Thresholds are frozen engineering fixture policy, not agency-approved scientific risk limits or privacy clearance.',
    'Fresh signed evidence authenticates retained native replay; original training, hostile isolation and independent agency trust remain unverified.',
    'Identity and review proof contexts remain local and in memory; durable history alone cannot restore current approval authority.',
    'No private data, arbitrary model import, model delivery, production authorization or accepted DP accounting is enabled.',
]
MAX_REPORT_BYTES = 256 * 1024


class RehearsalError(RuntimeError):
    pass


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _read_source(root, name, maximum=2 * 1024 * 1024):
    path = _BASELINE._checked_path(root, name)
    before = path.lstat()
    def identity(info):
        return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns
    def valid(info):
        return stat.S_ISREG(info.st_mode) and not _BASELINE._is_link(info) and info.st_nlink == 1 and 0 <= info.st_size <= maximum
    if not valid(before):
        raise RehearsalError('Source is not a bounded ordinary file')
    flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
    with os.fdopen(os.open(path, flags), 'rb') as stream:
        opened = os.fstat(stream.fileno())
        if not valid(opened) or identity(opened) != identity(before):
            raise RehearsalError('Source changed during open')
        content = stream.read(maximum + 1)
        after = os.fstat(stream.fileno())
    final = _BASELINE._checked_path(root, name).lstat()
    if (not valid(final) or identity(opened) != identity(after) or identity(after) != identity(final)
            or len(content) != after.st_size or len(content) > maximum):
        raise RehearsalError('Source changed during bounded read')
    return content


def source_snapshot(root):
    root = Path(root).absolute()
    package = _BASELINE._checked_path(root, 'src/model_release_assurance')
    paths = list(islice(package.rglob('*.py'), 257))
    if not paths or len(paths) > 256:
        raise RehearsalError('Package source inventory is unavailable or exceeds its bound')
    selected = set(SOURCE_FILES)
    selected.update(path.relative_to(root).as_posix() for path in paths)
    if len(selected) > 256:
        raise RehearsalError('Source snapshot exceeds its file bound')
    files = []
    for name in sorted(selected):
        raw = _read_source(root, name)
        files.append({'path': name, 'sha256': hashlib.sha256(raw).hexdigest(), 'size_bytes': len(raw)})
    return {'scope': 'All package Python sources, policy rehearsal/helper and runtime declarations',
            'files': files, 'sha256': _digest(files)}


def _complete_checks(checks):
    return (type(checks) is list and len(checks) == len(REQUIRED_CHECKS)
            and all(type(row) is dict and set(row) == {'name', 'passed'}
                    and type(row['name']) is str and row['passed'] is True for row in checks)
            and {row['name'] for row in checks} == REQUIRED_CHECKS)


def run_rehearsal(*, root, output):
    destination = _BASELINE.prepare_output(Path(root).absolute(), output)
    report = {'schema': 'mra-fixture-policy-review-rehearsal/v1', 'status': 'failed', 'checks': [],
              'errors': [], 'source': None, 'limitations': LIMITATIONS, **FLAGS}
    baseline = None
    try:
        baseline = source_snapshot(root)
        report['source'] = baseline
        result = exercise(destination)
        if type(result) is not dict or type(result.get('checks')) is not list:
            raise RehearsalError('Incomplete workflow')
        if any(result.get(key) is not value for key, value in FLAGS.items()):
            raise RehearsalError('Fixture outcome flags rejected')
        for name in ('checks', 'summary', 'evidence'):
            if name in result:
                report[name] = result[name]
        if result.get('status') != 'passed':
            raise RehearsalError('Fixture workflow did not complete')
    except Exception as error:
        report['errors'].append({'stage': 'fixture_workflow', 'type': type(error).__name__})
    if baseline is not None:
        try:
            stable = source_snapshot(root) == baseline
            report['checks'].append({'name': 'source_unchanged', 'passed': stable})
            if not stable:
                raise RehearsalError('Source changed')
        except Exception as error:
            report['errors'].append({'stage': 'source_stability', 'type': type(error).__name__})
    if not report['errors'] and _complete_checks(report['checks']):
        report['status'] = 'passed'
    elif not report['errors']:
        report['errors'].append({'stage': 'milestones', 'type': 'IncompleteWorkflow'})
    report['runtime'] = {'python': platform.python_version(), 'system': platform.system()}
    content = json.dumps(report, indent=2, sort_keys=True, allow_nan=False).encode() + b'\n'
    if len(content) > MAX_REPORT_BYTES:
        report = {'schema': 'mra-fixture-policy-review-rehearsal/v1', 'status': 'failed', 'checks': [],
                  'errors': [{'stage': 'report', 'type': 'ReportBoundExceeded'}], **FLAGS}
        content = json.dumps(report, sort_keys=True).encode() + b'\n'
    with (destination / 'result.json').open('xb') as stream:
        stream.write(content)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args = parser.parse_args(argv)
    try:
        result = run_rehearsal(root=ROOT, output=args.output)
    except (_BASELINE.BaselineError, OSError):
        print(json.dumps({'status': 'output_refused', **FLAGS}))
        return 2
    print(json.dumps({'status': result['status'], 'checks': len(result['checks']), 'errors': result['errors'], **FLAGS}))
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
