#!/usr/bin/env python3
"""Run or replay one explicit local public Wine profile; production is refused."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).absolute().parents[1]
if str(ROOT / 'src') not in sys.path:
    sys.path.insert(0, str(ROOT / 'src'))
_SPEC = importlib.util.spec_from_file_location('mra_profile_delivery_helpers', ROOT / 'scripts/rehearse_controlled_delivery.py')
_HELPERS = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_HELPERS)
_BASELINE = _HELPERS._BASELINE
from model_release_assurance.production_profile.contracts import FLAGS
from model_release_assurance.production_profile.runtime import load_runtime, RuntimeError as PinnedRuntimeError
from model_release_assurance.production_profile.rehearsal import exercise
from model_release_assurance.production_profile.receipt import verify_receipt

SOURCE_FILES = ('scripts/rehearse_public_profile.py', 'scripts/rehearse_controlled_delivery.py',
    'deploy/sacro/windows-cp312.json', 'deploy/sacro/windows-cp312.requirements.txt',
    *('src/model_release_assurance/production_profile/' + name + '.py' for name in
      ('__init__', 'contracts', 'journal', 'receipt', 'runtime', 'workflow', 'rehearsal')))
REQUIRED_CHECKS = frozenset({'production_profile_refused_before_fit',
    'combined_plan_frozen_before_fit', 'fresh_registered_native_replay',
    'fixed_external_attack_and_controls', 'external_bound_before_independent_reviews',
    'owner_and_operator_review_denied', 'native_only_activation_denied',
    'exact_candidate_delivery', 'partial_write_retains_attempt',
    'suspension_denies_next_chunk', 'resume_requires_new_admission',
    'grant_revocation_denies_chunk', 'activation_revocation_permanent',
    'exclusive_expiry_denies_chunk', 'historical_receipt_replayed',
    'pinned_receipt_tamper_denied', 'all_results_production_blocked', 'source_unchanged'})
MAX_REPORT_BYTES = 512 * 1024
LIMITATIONS = [
    'One fixed public Wine128 profile, native recipe and nine fixed SACRO target/control repetitions; no arbitrary or private inputs.',
    'The existing pinned SACRO environment is read only; the command never downloads, installs or repairs dependencies.',
    'Only explicit local_public_fixture operation is enabled; agency_private_cloud is refused before training or output creation.',
    'Signatures bind historical local fixture evidence; they do not attest original training, external execution or independent agency custody.',
    'Historical receipt replay does not check current authorization or reopen a delivery grant.',
    'No accepted privacy accounting, scientific clearance, hostile isolation, private-cloud qualification or production release is established.',
]


class ProfileRefused(ValueError):
    pass


class RehearsalError(RuntimeError):
    pass


def _local(profile):
    if type(profile) is not str or profile != 'local_public_fixture':
        raise ProfileRefused('Production profile is not qualified')


def source_snapshot(root):
    root = Path(root).absolute()
    base = _HELPERS.source_snapshot(root)
    files = {entry['path']: dict(entry) for entry in base['files']}
    for name in SOURCE_FILES:
        raw = _HELPERS._read_source(root, name)
        files[name] = {'path': name, 'sha256': hashlib.sha256(raw).hexdigest(), 'size_bytes': len(raw)}
    if len(files) > 256:
        raise RehearsalError('Profile source inventory exceeds its bound')
    selected = [files[name] for name in sorted(files)]
    return {'scope': 'All package Python, profile/delivery/output helpers and exact SACRO installation locks',
            'files': selected, 'sha256': _HELPERS._digest(selected)}


def _complete_checks(checks):
    return (type(checks) is list and len(checks) == len(REQUIRED_CHECKS)
        and all(type(row) is dict and set(row) == {'name', 'passed'}
                and type(row['name']) is str and row['passed'] is True for row in checks)
        and {row['name'] for row in checks} == REQUIRED_CHECKS)


def run_rehearsal(*, root, output, python, profile='agency_private_cloud'):
    _local(profile)
    spec = load_runtime(root, python)  # Reject unavailable runtime before creating output.
    destination = _BASELINE.prepare_output(Path(root).absolute(), output)
    report = {'schema': 'mra-public-profile-rehearsal/v1', 'status': 'failed',
        'profile': profile, 'checks': [], 'errors': [], 'source': None,
        'runtime': spec, 'limitations': LIMITATIONS, **FLAGS}
    baseline = None
    try:
        baseline = source_snapshot(root)
        report['source'] = baseline
        result = exercise(destination, python=spec['python'], versions=dict(spec['versions']),
                          lock_sha256=spec['lock_sha256'])
        if (type(result) is not dict or type(result.get('checks')) is not list
                or any(result.get(key) is not value for key, value in FLAGS.items())):
            raise RehearsalError('Fixture outcome rejected')
        for name in ('checks', 'summary', 'evidence'):
            if name in result:
                report[name] = result[name]
        if result.get('status') != 'passed':
            raise RehearsalError('Fixture workflow did not complete')
    except Exception as error:
        report['errors'].append({'stage': 'fixture_workflow', 'type': type(error).__name__})
    if baseline is not None:
        try:
            stable = source_snapshot(root) == baseline and load_runtime(root, python) == spec
            report['checks'].append({'name': 'source_unchanged', 'passed': stable})
            if not stable:
                raise RehearsalError('Source or runtime changed')
        except Exception as error:
            report['errors'].append({'stage': 'source_stability', 'type': type(error).__name__})
    if not report['errors'] and _complete_checks(report['checks']):
        report['status'] = 'passed'
    elif not report['errors']:
        report['errors'].append({'stage': 'milestones', 'type': 'IncompleteWorkflow'})
    try:
        content = json.dumps(report, indent=2, sort_keys=True, allow_nan=False).encode() + b'\n'
        if len(content) > MAX_REPORT_BYTES:
            raise RehearsalError('Report exceeds bound')
    except (TypeError, ValueError, RehearsalError):
        report = {'schema': 'mra-public-profile-rehearsal/v1', 'status': 'failed', 'checks': [],
            'errors': [{'stage': 'report', 'type': 'InvalidOrOversizedReport'}], **FLAGS}
        content = json.dumps(report, sort_keys=True).encode() + b'\n'
    with (destination / 'result.json').open('xb') as stream:
        stream.write(content)
    return report


def replay(*, root, path, expected_receipt_sha256, expected_key_sha256, profile='agency_private_cloud'):
    _local(profile)
    if any(type(pin) is not str or not re.fullmatch(r'[0-9a-f]{64}', pin)
           for pin in (expected_receipt_sha256, expected_key_sha256)):
        raise RehearsalError('Explicit receipt and key pins are required')
    root, supplied = Path(root).absolute(), Path(path)
    if '..' in supplied.parts or str(supplied).startswith(('//', '\\\\')):
        raise RehearsalError('Historical replay path refused')
    target = supplied.absolute() if supplied.is_absolute() else root / supplied
    if not target.is_relative_to(root / '.local') or target == root / '.local':
        raise RehearsalError('Historical replay must remain within government .local')
    relative = target.relative_to(root).as_posix()
    checked = _BASELINE._checked_path(root, relative)
    if not checked.is_dir():
        raise RehearsalError('Historical replay root unavailable')
    result = verify_receipt(checked, expected_receipt_sha256=expected_receipt_sha256,
                            expected_key_sha256=expected_key_sha256)
    if (type(result) is not dict or result.get('status') != 'historical_fixture_replay_verified'
            or result.get('current_authorization_checked') is not False
            or any(result.get(key) is not value for key, value in FLAGS.items())):
        raise RehearsalError('Historical replay outcome rejected')
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--output')
    mode.add_argument('--replay')
    parser.add_argument('--python', type=Path)
    parser.add_argument('--profile', choices=('agency_private_cloud', 'local_public_fixture'), default='agency_private_cloud')
    parser.add_argument('--expected-receipt-sha256')
    parser.add_argument('--expected-key-sha256')
    args = parser.parse_args(argv)
    try:
        _local(args.profile)
        if args.replay is not None:
            if args.python is not None or args.expected_receipt_sha256 is None or args.expected_key_sha256 is None:
                parser.error('Replay needs both expected hashes and accepts no --python')
            result = replay(root=ROOT, path=args.replay, expected_receipt_sha256=args.expected_receipt_sha256,
                expected_key_sha256=args.expected_key_sha256, profile=args.profile)
            print(json.dumps(result, sort_keys=True, allow_nan=False))
            return 0
        if args.python is None or args.expected_receipt_sha256 is not None or args.expected_key_sha256 is not None:
            parser.error('A fresh run needs --python and accepts no replay hashes')
        result = run_rehearsal(root=ROOT, output=args.output, python=args.python, profile=args.profile)
    except ProfileRefused:
        print(json.dumps({'status': 'profile_refused', **FLAGS}))
        return 2
    except (PinnedRuntimeError, _BASELINE.BaselineError, RehearsalError, OSError, ValueError) as error:
        print(json.dumps({'status': 'refused', 'type': type(error).__name__, **FLAGS}))
        return 2
    print(json.dumps({'status': result['status'], 'checks': len(result['checks']), 'errors': result['errors'], **FLAGS}))
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
