#!/usr/bin/env python3
"""Rehearse explicit local-fixture delivery after a fresh independent review."""
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
_SPEC = importlib.util.spec_from_file_location('mra_delivery_baseline', ROOT / 'scripts/verify_build_baseline.py')
_BASELINE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_BASELINE)
from model_release_assurance.production_delivery.contracts import FLAGS
from model_release_assurance.production_delivery.rehearsal import exercise

SOURCE_FILES = (*('src/model_release_assurance/production_delivery/' + name + '.py' for name in
      ('__init__', 'contracts', 'store', 'authorization', 'review_bridge', 'gateway', 'checkpoint', 'api', 'rehearsal')),
    'scripts/rehearse_controlled_delivery.py', 'scripts/verify_build_baseline.py',
    'pyproject.toml', 'requirements.lock', 'src/model_release_assurance/__init__.py',
    'src/model_release_assurance/analyzers/attack.py', 'src/model_release_assurance/portfolio_statistics.py',
    *('src/model_release_assurance/production_review/' + name + '.py' for name in
      ('__init__', 'contracts', 'store', 'service', 'authorization', 'rehearsal')),
    *('src/model_release_assurance/production_registration/' + name + '.py' for name in
      ('__init__', 'contracts', 'store', 'profiles', 'workflow')),
    *('src/model_release_assurance/production_evidence/' + name + '.py' for name in
      ('__init__', 'contracts', 'signing', 'verifier', 'replay', 'ledger')))
REQUIRED_CHECKS = frozenset({
    'production_profile_is_refused', 'fresh_training_and_independent_review',
    'activation_requires_explicit_local_profile', 'activation_requires_current_independent_review',
    'recipient_scope_is_exact',
    'exact_candidate_chunks_and_fresh_admissions', 'interrupted_transfer_retains_admission',
    'recipient_receipt_is_not_claimed', 'suspension_blocks_next_chunk',
    'resume_requires_fresh_admission', 'grant_revocation_blocks_next_chunk',
    'activation_revocation_is_permanent', 'current_authority_revocation_blocks_delivery',
    'caller_artifact_and_direct_object_routes_are_refused',
    'external_checkpoint_detects_restored_delivery_log',
    'all_results_remain_production_blocked', 'source_unchanged'})
LIMITATIONS = [
    'One fixed public Wine sample, fresh native fit, authenticated replay and independent fixture acknowledgments.',
    'Only explicit local_public_fixture delivery is enabled; agency_private_cloud remains blocked by default.',
    'Local public candidate bytes may be written to a trusted callback; private-data intake and arbitrary artifact imports are unavailable.',
    'Each chunk records current local admission before callback invocation; interrupted writes do not prove recipient receipt.',
    'Checkpoint files are retained separately on the same host; independent agency custody and privileged coherent rollback protection are not established.',
    'No scientific clearance, accepted privacy accounting, remote isolation, cloud failover or production release authority is demonstrated.',
]
MAX_REPORT_BYTES = 256 * 1024


class RehearsalError(RuntimeError):
    pass


class ProfileRefused(ValueError):
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
    return {'scope': 'All package Python sources, delivery rehearsal/helper and runtime declarations',
            'files': files, 'sha256': _digest(files)}


def _complete_checks(checks):
    return (type(checks) is list and len(checks) == len(REQUIRED_CHECKS)
            and all(type(row) is dict and set(row) == {'name', 'passed'}
                    and type(row['name']) is str and row['passed'] is True for row in checks)
            and {row['name'] for row in checks} == REQUIRED_CHECKS)


def run_rehearsal(*, root, output, profile='agency_private_cloud'):
    if profile != 'local_public_fixture':
        raise ProfileRefused('Production delivery is not enabled')
    destination = _BASELINE.prepare_output(Path(root).absolute(), output)
    report = {'schema': 'mra-fixture-controlled-delivery-rehearsal/v1', 'status': 'failed', 'checks': [],
              'errors': [], 'source': None, 'limitations': LIMITATIONS, 'profile': profile, **FLAGS}
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
        report = {'schema': 'mra-fixture-controlled-delivery-rehearsal/v1', 'status': 'failed', 'checks': [],
                  'errors': [{'stage': 'report', 'type': 'ReportBoundExceeded'}], **FLAGS}
        content = json.dumps(report, sort_keys=True).encode() + b'\n'
    with (destination / 'result.json').open('xb') as stream:
        stream.write(content)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--profile', choices=('agency_private_cloud', 'local_public_fixture'), default='agency_private_cloud')
    args = parser.parse_args(argv)
    try:
        result = run_rehearsal(root=ROOT, output=args.output, profile=args.profile)
    except ProfileRefused:
        print(json.dumps({'status': 'profile_refused', **FLAGS}))
        return 2
    except (_BASELINE.BaselineError, OSError):
        print(json.dumps({'status': 'output_refused', **FLAGS}))
        return 2
    print(json.dumps({'status': result['status'], 'checks': len(result['checks']), 'errors': result['errors'], **FLAGS}))
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
