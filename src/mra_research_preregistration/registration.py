"""Metadata-only, reviewed Phase 7B preregistration; no numerical evaluator."""
from pathlib import Path
import argparse
import hashlib
import json
import math
import os
import re
from datetime import datetime, timezone

READINESS_SHA256 = '39b29a1bf46880e4986b4af97e934bbad31579eaaad8300ae19a2f67ee903294'
READINESS_RELATIVE = '.local/demo-data-rr-readiness-20261013/source-readiness-manifest.json'
COMPLETION_RELATIVE = '.local/verification/rr-phase7a-20261013/completion.json'
PHASE7A_COMPLETION_SHA256 = '48cb6f214e8dd76074555ffc658aa08cd6d66f671e8cf240d6475db785631cfa'
SOURCE_COMPLETION_SHA256 = '8beb6d8bf44a3f6617dbf63e017af4910bba8ed8fff32989cfce0fe420ae41e7'
APPROVED_SPEC_SHA256 = '93a124607498c5cec6a93d06b4e3648094b683983ae59518a7fd22169a62d915'
APPROVED_CONTRACT_SHA256 = 'f40128dfe794a9cd7ef8a95e1a09fb3cc17e53c3cc2cf47d216cad6742f0d159'
APPROVED_REVIEW_SHA256 = {'scientific': 'bc50737f262cef17756bb741837db8d4a60c35e77370bcf6ec4fa5c8a60b9bdd', 'mechanical': 'e980271a441a6a5d073482c89f3b95c66fc9c77a835d746a633afceb15419f61', 'readiness': '1fe5e2d1a0bb2496154222d922bc11cf28e5960ff14ecaee7f4a085bcb0c65ce'}
REVIEWER_BY_ROLE = {'scientific': '/root/phase7b_science', 'mechanical': '/root/phase7b_contract', 'readiness': '/root/phase7b_validation'}
STORE_RELATIVE = '.local/demo-data-rr-preregistration-20261013'
ROSTER = ['moh', 'mas', 'msf']
REVIEW_ROLES = {'scientific', 'mechanical', 'readiness'}
HEX = re.compile(r'^[0-9a-f]{64}$')

class RegistrationError(ValueError):
    """A refusal that preserves the original inputs and reservation."""

def sha(data):
    return hashlib.sha256(data).hexdigest()

def canonical(value):
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + '\n').encode('utf-8')

def strict_json(data):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise RegistrationError('Duplicate JSON key: ' + key)
            result[key] = value
        return result
    def refuse(value):
        raise RegistrationError('Nonfinite JSON number: ' + value)
    def finite_float(value):
        number = float(value)
        if not math.isfinite(number):
            raise RegistrationError('Nonfinite JSON number: ' + value)
        return number
    try:
        result = json.loads(data, object_pairs_hook=pairs, parse_constant=refuse, parse_float=finite_float)
        if type(result) is not dict:
            raise RegistrationError('Expected a JSON document object')
        return result
    except (ValueError, UnicodeError) as exc:
        raise RegistrationError(str(exc)) from exc

def bound_path(repository, relative):
    if not isinstance(relative, str) or not relative or '\\' in relative:
        raise RegistrationError('Binding requires a POSIX repository-relative path')
    p = Path(relative)
    if p.is_absolute() or '..' in p.parts or ':' in relative:
        raise RegistrationError('Unsafe binding path')
    root = Path(repository).resolve()
    result = (root / p).resolve()
    if not result.is_relative_to(root):
        raise RegistrationError('Binding escapes repository')
    return result

def verify_binding(repository, item):
    if not isinstance(item, dict) or not HEX.fullmatch(item.get('sha256', '')) or type(item.get('bytes')) is not int:
        raise RegistrationError('Malformed artifact binding')
    p = bound_path(repository, item['path'])
    try:
        data = p.read_bytes()
    except OSError as exc:
        raise RegistrationError('Missing bound artifact: ' + item['path']) from exc
    if len(data) != item['bytes'] or sha(data) != item['sha256']:
        raise RegistrationError('Changed bound artifact: ' + item['path'])
    return data

def verify_readiness(repository):
    """Verify bytes/metadata only. Never call the 7A numeric CSV profiler."""
    data = bound_path(repository, READINESS_RELATIVE).read_bytes()
    if sha(data) != READINESS_SHA256:
        raise RegistrationError('Phase 7A manifest differs from verified handoff')
    manifest = strict_json(data)
    complete_data = bound_path(repository, COMPLETION_RELATIVE).read_bytes()
    if sha(complete_data) != PHASE7A_COMPLETION_SHA256:
        raise RegistrationError('Changed verified Phase 7A completion')
    source_complete = bound_path(repository, '.local/demo-data-rr-readiness-20261013/completion.json').read_bytes()
    if sha(source_complete) != SOURCE_COMPLETION_SHA256:
        raise RegistrationError('Changed verified source-store completion')
    complete = strict_json(complete_data)
    if (complete.get('phase7a_complete') is not True or complete.get('manifest_sha256') != READINESS_SHA256
            or complete.get('phase6_result_unchanged') != 'fail' or complete.get('phase6_rerun_or_replay') is not False
            or set(manifest.get('tasks', {})) != set(ROSTER) or len(manifest.get('artifacts', [])) != 223):
        raise RegistrationError('Incomplete or inconsistent Phase 7A handoff')
    paths = set()
    for binding in manifest['artifacts']:
        if binding['path'] in paths:
            raise RegistrationError('Duplicate artifact binding')
        paths.add(binding['path'])
        verify_binding(repository, binding)
    cards = {}
    for domain in ROSTER:
        path = '.local/demo-data-rr-readiness-20261013/task-card-' + domain + '.json'
        if path not in paths:
            raise RegistrationError('Unbound task card')
        card = strict_json(bound_path(repository, path).read_bytes())
        if card != manifest['tasks'][domain]:
            raise RegistrationError('Task card differs from manifest')
        if (card['domain'] != domain or card['historical_outcomes_unobserved'] is not False
                or card['real_time_validity'] != 'unresolved' or card['real_time_asof_qualified_cells'] != 0
                or card['agency_practical_margin'] is not None or card['agency_acceptance'] != 'pending'):
            raise RegistrationError('Unsupported readiness claim')
        cards[domain] = card
    if any(cards[d].get('next_preregistration_required') is not True for d in ROSTER):
        raise RegistrationError('Separate preregistration required')
    if cards['mas']['next_preregistration_required'] is not True or cards['mas']['usable_observation_count'] != 340:
        raise RegistrationError('MAS readiness mismatch')
    if any(cards[d]['usable_observation_count'] != 0 for d in ('moh', 'msf')):
        raise RegistrationError('Mandatory unsupported domains changed')
    return manifest, sha(complete_data)

def validate_plan(specification, contract):
    if sha(canonical(specification)) != APPROVED_SPEC_SHA256 or sha(canonical(contract)) != APPROVED_CONTRACT_SHA256:
        raise RegistrationError('Protocol override differs from independently reviewed fixed plan')
    # Whole-file independent-review hashes protect every scientific and numerical field.
    # These additional guards prevent a reviewed document from violating Phase 7 scope.
    if (specification.get('schema') != 'mra-phase7b-scientific-preregistration/1.0'
            or contract.get('schema') != 'mra-phase7b-execution-contract/1.0'
            or specification.get('phase') != '7B'
            or specification.get('mandatory_domains') != ROSTER
            or specification.get('benchmark_executed') is not False
            or specification.get('agency_practical_margin') is not None
            or specification.get('agency_acceptance') != 'pending'
            or specification.get('readiness_manifest_sha256') != READINESS_SHA256):
        raise RegistrationError('Invalid Phase 7B scientific scope')
    if contract.get('phase7b_permitted_operations') != ['metadata_validation', 'review', 'freeze', 'status']:
        raise RegistrationError('Execution is forbidden in Phase 7B')
    if specification.get('all_domain_readiness') != 'not_evaluable_mandatory_domains_unsupported':
        raise RegistrationError('Missing-domain aggregation cannot pass')
    domains = specification.get('domain_status', {})
    if set(domains) != set(ROSTER) or any(domains[d].get('status') != 'unsupported' for d in ('moh', 'msf')):
        raise RegistrationError('Unsupported domain silently removed')
    if specification.get('historical_outcomes_unobserved') is not False:
        raise RegistrationError('Historical values cannot be called untouched')
    if specification.get('new_usefulness_result') is not None:
        raise RegistrationError('Outcome derivation is forbidden in Phase 7B')

def reviewed_inputs(repository, specification_path, contract_path, review_paths):
    spec_data = Path(specification_path).read_bytes()
    contract_data = Path(contract_path).read_bytes()
    spec, contract = strict_json(spec_data), strict_json(contract_data)
    validate_plan(spec, contract)
    reviews = []
    roles = set()
    reviewers = set()
    for path in review_paths:
        data = Path(path).read_bytes()
        review = strict_json(data)
        if (review.get('schema') != 'mra-phase7b-independent-review/1.0'
                or review.get('approved') is not True or review.get('blocking_issues') != []
                or review.get('specification_sha256') != sha(spec_data)
                or review.get('execution_contract_sha256') != sha(contract_data)
                or review.get('numeric_source_values_read') is not False
                or review.get('benchmark_executed') is not False
                or review.get('role') not in REVIEW_ROLES
                or review.get('reviewer') != REVIEWER_BY_ROLE.get(review.get('role'))
                or sha(data) != APPROVED_REVIEW_SHA256.get(review.get('role'))):
            raise RegistrationError('Missing, stale or non-independent draft review')
        roles.add(review['role'])
        reviewers.add(review['reviewer'])
        reviews.append((review['role'] + '-review.json', data))
    if roles != REVIEW_ROLES or len(reviewers) != 3 or len(reviews) != 3:
        raise RegistrationError('Three distinct independent review roles required')
    manifest, complete_sha = verify_readiness(repository)
    return spec_data, contract_data, reviews, manifest, complete_sha

def write_once(path, data):
    with Path(path).open('xb') as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())

def expected_status():
    return {'schema': 'mra-phase7b-readiness-status/1.0', 'phase7b_preregistered': True,
              'benchmark_executed': False, 'new_target_bits_derived': False, 'new_rr_histories_derived': False,
              'new_models_fitted': False, 'new_usefulness_result': None,
              'all_domain_readiness': 'not_evaluable_mandatory_domains_unsupported',
              'mas_diagnostic_readiness': 'limited_retrospective_only', 'moh': 'unsupported', 'msf': 'unsupported',
              'real_time_validity': {d: 'unresolved' for d in ROSTER}, 'agency_acceptance': 'pending',
              'agency_practical_margin': None, 'authorization_effect': 'none'}

def freeze(repository, specification_path, contract_path, review_paths):
    root = Path(repository).resolve()
    spec_data, contract_data, reviews, manifest, complete_sha = reviewed_inputs(root, specification_path, contract_path, review_paths)
    identity = sha(b'mra-phase7b-registration-v1\0' + bytes.fromhex(sha(spec_data)) + bytes.fromhex(sha(contract_data)))[:24]
    store = bound_path(root, STORE_RELATIVE + '/' + identity)
    store.mkdir(parents=True, exist_ok=True)
    reservation = {'schema': 'mra-phase7b-registration-reservation/1.0', 'registration_id': identity,
                   'specification_sha256': sha(spec_data), 'execution_contract_sha256': sha(contract_data),
                   'created_at': datetime.now(timezone.utc).isoformat(), 'benchmark_execution_reserved': False}
    try:
        write_once(store / 'registration-reservation.json', canonical(reservation))
    except FileExistsError:
        result = open_completed(root, store)
        if result['specification_sha256'] != sha(spec_data) or result['execution_contract_sha256'] != sha(contract_data):
            raise RegistrationError('Registration identity collision')
        return result
    files = [('scientific-preregistration.json', spec_data), ('execution-contract.json', contract_data)] + reviews
    status = expected_status()
    files.append(('readiness-status.json', canonical(status)))
    files.append(('source-bindings.json', canonical({'manifest_sha256': READINESS_SHA256,
                 'phase7a_completion_sha256': complete_sha, 'artifacts': manifest['artifacts']})))
    bound = []
    for name, data in files:
        write_once(store / name, data)
        bound.append({'path': name, 'sha256': sha(data), 'bytes': len(data)})
    bound.append({'path': 'registration-reservation.json', 'sha256': sha((store / 'registration-reservation.json').read_bytes()),
                  'bytes': (store / 'registration-reservation.json').stat().st_size})
    completion = {'schema': 'mra-phase7b-registration-completion/1.0', 'registration_id': identity,
                  'specification_sha256': sha(spec_data), 'execution_contract_sha256': sha(contract_data),
                  'readiness_manifest_sha256': READINESS_SHA256, 'completed_at': datetime.now(timezone.utc).isoformat(),
                  'files': bound, 'benchmark_executed': False, 'completion_written_last': True}
    completion_data = canonical(completion)
    # External local seal is fsynced before completion, which remains the last store artifact.
    write_once(store.parent / (identity + '.seal.json'), canonical({'schema': 'mra-phase7b-local-seal/1.0',
               'registration_id': identity, 'completion_sha256': sha(completion_data)}))
    write_once(store / 'registration-completion.json', completion_data)
    return open_completed(root, store)

def open_completed(repository, store):
    root, store = Path(repository).resolve(), Path(store).resolve()
    permitted = (root / STORE_RELATIVE).resolve()
    if not store.is_relative_to(permitted) or store == permitted:
        raise RegistrationError('Registration must use separate Phase 7B sibling store')
    try:
        data = (store / 'registration-completion.json').read_bytes()
    except OSError as exc:
        raise RegistrationError('Incomplete reservation retained; no replacement or retry execution') from exc
    try:
        seal = strict_json((store.parent / (store.name + '.seal.json')).read_bytes())
    except OSError as exc:
        raise RegistrationError('Missing local registration seal') from exc
    if seal != {'schema': 'mra-phase7b-local-seal/1.0', 'registration_id': store.name, 'completion_sha256': sha(data)}:
        raise RegistrationError('Changed registration completion')
    complete = strict_json(data)
    if (complete.get('schema') != 'mra-phase7b-registration-completion/1.0' or complete.get('benchmark_executed') is not False
            or complete.get('completion_written_last') is not True
            or set(complete) != {'schema','registration_id','specification_sha256','execution_contract_sha256','readiness_manifest_sha256','completed_at','files','benchmark_executed','completion_written_last'}
            or complete['readiness_manifest_sha256'] != READINESS_SHA256):
        raise RegistrationError('Invalid registration completion')
    expected = {'scientific-preregistration.json', 'execution-contract.json', 'scientific-review.json',
                'mechanical-review.json', 'readiness-review.json', 'readiness-status.json',
                'source-bindings.json', 'registration-reservation.json'}
    if {v['path'] for v in complete.get('files', [])} != expected or len(complete['files']) != len(expected):
        raise RegistrationError('Incomplete registration artifact roster')
    for item in complete['files']:
        if '/' in item['path'] or '\\' in item['path']:
            raise RegistrationError('Unsafe registration artifact path')
        verify_binding(store, item)
    spec_path, contract_path = store / 'scientific-preregistration.json', store / 'execution-contract.json'
    validate_plan(strict_json(spec_path.read_bytes()), strict_json(contract_path.read_bytes()))
    if sha(spec_path.read_bytes()) != complete['specification_sha256'] or sha(contract_path.read_bytes()) != complete['execution_contract_sha256']:
        raise RegistrationError('Completion digest mismatch')
    expected_id = sha(b'mra-phase7b-registration-v1\0' + bytes.fromhex(complete['specification_sha256']) + bytes.fromhex(complete['execution_contract_sha256']))[:24]
    if complete['registration_id'] != store.name or expected_id != store.name:
        raise RegistrationError('Registration identity mismatch')
    if canonical(strict_json((store / 'readiness-status.json').read_bytes())) != canonical(expected_status()):
        raise RegistrationError('Forged registration readiness status')
    reservation = strict_json((store / 'registration-reservation.json').read_bytes())
    if (set(reservation) != {'schema','registration_id','specification_sha256','execution_contract_sha256','created_at','benchmark_execution_reserved'}
            or reservation['schema'] != 'mra-phase7b-registration-reservation/1.0'
            or reservation['registration_id'] != store.name
            or reservation['specification_sha256'] != complete['specification_sha256']
            or reservation['execution_contract_sha256'] != complete['execution_contract_sha256']
            or reservation['benchmark_execution_reserved'] is not False):
        raise RegistrationError('Forged execution or registration reservation')
    source = strict_json((store / 'source-bindings.json').read_bytes())
    manifest, completion_sha = verify_readiness(root)
    if source['manifest_sha256'] != READINESS_SHA256 or source['artifacts'] != manifest['artifacts'] or source['phase7a_completion_sha256'] != completion_sha:
        raise RegistrationError('Source binding differs from verified readiness')
    reviewed_inputs(root, spec_path, contract_path, [store / (r + '-review.json') for r in sorted(REVIEW_ROLES)])
    return complete

def main(argv=None):
    parser = argparse.ArgumentParser(description='Phase 7B metadata-only preregistration; benchmark execution is unavailable.')
    parser.add_argument('--repository', type=Path, required=True)
    commands = parser.add_subparsers(dest='command', required=True)
    freeze_parser = commands.add_parser('freeze')
    freeze_parser.add_argument('--specification', type=Path, required=True)
    freeze_parser.add_argument('--contract', type=Path, required=True)
    freeze_parser.add_argument('--review', type=Path, action='append', required=True)
    for name in ('validate', 'status'):
        commands.add_parser(name).add_argument('--registration', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'freeze':
            value = freeze(args.repository, args.specification, args.contract, args.review)
        else:
            value = open_completed(args.repository, args.registration)
            if args.command == 'status':
                value = strict_json((args.registration / 'readiness-status.json').read_bytes())
        print(canonical(value).decode(), end='')
    except (RegistrationError, OSError) as exc:
        parser.exit(2, 'Registration refused: ' + str(exc) + '\n')
    return 0

