"""Immutable public-frame qualification and prospective research registration.

This module does not fit models, derive outcome bits, draw random blocks, or
supply agency authorization. Earlier research stores remain separate.
"""
from __future__ import annotations

from datetime import datetime, timezone
import importlib.metadata
import json
import math
from pathlib import Path
import platform
import re
from typing import Any

from . import benchmark, qualified_encoding, web
from .benchmark_store import _read, _write, _decode

PREFIX = '/api/research-qualified-benchmark'
AGENCIES = ('moh', 'mas', 'msf')
ARTIFACTS = ('specification.json', 'runtime.json', 'preregistration.json',
             'encoding-audit.json', 'cohort-plan.json', 'margin-rationale.json',
             'qualification.txt', 'registration-completion.json',
             *(f'source-{agency}{suffix}' for agency in AGENCIES
               for suffix in ('.csv', '-metadata.json')))
IMPLEMENTATION = ('qualified_encoding.py', 'qualified_store.py',
                  'qualified_routes.py', 'qualified_console_app.py', 'benchmark.py',
                  'benchmark_store.py', 'web.py', 'certificates.py', 'sampling.py', 'cli.py')
SCOPE = {'data': 'official public aggregate records',
         'representation': 'Census of eligible published historical held-out observations only',
         'agency_acceptance': 'pending', 'operational_usefulness': 'not_evaluated',
         'authorization_effect': 'none', 'production_execution_qualified': False}
_RUN = re.compile(r'[a-f0-9]{32}\Z')
_SHA = re.compile(r'[a-f0-9]{64}\Z')
_CUSTODY = 'Local prospective registration; independent administration and agency acceptance pending'
_SPEC = Path(__file__).parent / 'static' / 'qualified-specification.json'


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def _canonical(value: Any) -> bytes:
    return benchmark.canonical_bytes(value)


def _json(path: Path, value: Any):
    _write(path, _canonical(value))


def research_decision(lower: float, upper: float) -> str:
    """Strict Brier dominance; equality at zero never passes."""
    if (type(lower) not in (int, float) or type(upper) not in (int, float)
            or not math.isfinite(lower) or not math.isfinite(upper) or lower > upper):
        raise ValueError('Research intervals must be finite and ordered')
    return 'pass' if lower > 0 else 'fail' if upper <= 0 else 'inconclusive'


def _runtime():
    base = Path(__file__).parent
    packages = {}
    for package in ('model-release-assurance', 'fastapi', 'starlette', 'numpy', 'threadpoolctl'):
        try:
            packages[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            packages[package] = 'not-installed'
    return {'python': platform.python_version(), 'implementation': platform.python_implementation(),
            'packages': packages, 'implementation_sha256': {
                name: web._sha(_read(base / name)) for name in IMPLEMENTATION}}


def _margin_rationale(spec):
    return {'schema': 'mra-qualified-research-margin/1.0',
            'primary_metric': 'mean held-out Brier loss',
            'gain': 'comparator Brier loss minus certified-continuation Brier loss',
            'research_margin': '0/1', 'pass': 'lower gain > 0',
            'fail': 'upper gain <= 0', 'otherwise': 'inconclusive',
            'justification': 'Strict risk reduction under a strictly proper probability scoring rule; zero is the no-benefit boundary, not an arbitrary positive effect size.',
            'decision_cost_identity': {
                'prediction': 'a(t)=1 when forecast p >= threshold t',
                'normalized_cost': 't for a false positive; 1-t for a false negative',
                'threshold_distribution': 'Uniform over [0,1], a public research reference assumption',
                'y=0': 'integral from 0 to p of t dt = p^2/2',
                'y=1': 'integral from p to 1 of (1-t) dt = (1-p)^2/2',
                'identity': 'Average normalized threshold decision loss equals Brier loss / 2',
                'interpretation': 'Strict positive Brier gain reduces this declared reference expected decision cost. Actual agency thresholds/stakes are not asserted.'},
            'mandatory_comparisons': spec['comparisons'],
            'operational_practical_margin': None,
            'operational_margin_status': 'Pending service-owner cost, stakes and threshold evidence; not inferred from sample size, confidence width or research superiority',
            'agency_acceptance': 'pending', 'authorization_effect': 'none'}


class QualifiedRunStore:
    def __init__(self, data_dir: str | Path, *, source_base: str | Path | None = None,
                 specification_override: dict[str, Any] | None = None):
        self.root = Path(data_dir).absolute()
        web._check_path(self.root)
        self.root.mkdir(parents=True, exist_ok=True)
        web._check_path(self.root)
        self.source_base = (Path(source_base).absolute() if source_base is not None
                            else self.root.parent / 'public-data-rr-qualified')
        self.spec_raw = (_canonical(specification_override) if specification_override is not None
                         else _read(_SPEC))
        self.spec = _decode(self.spec_raw)
        if (self.spec.get('schema') != 'mra-qualified-public-preregistration/1.0'
                or self.spec.get('tasks_order') != list(AGENCIES)
                or self.spec.get('scope') != SCOPE
                or set(self.spec.get('sources', {})) != set(AGENCIES)
                or len(self.spec.get('comparisons', [])) != 6):
            raise web.ResearchWebError('Invalid fixed qualified benchmark specification')
        self.spec_sha = web._sha(self.spec_raw)
        self.runtime = _runtime()

    def _ensure_runtime(self):
        if _runtime() != self.runtime:
            raise web.ResearchWebError('Bound public qualification implementation changed; registration and delivery are blocked')

    def _folder(self, run_id: str) -> Path:
        if type(run_id) is not str or not _RUN.fullmatch(run_id):
            raise web.ResearchWebError('Unknown qualified benchmark identifier', 404)
        folder = self.root / run_id
        web._check_path(folder)
        if not folder.is_dir():
            raise web.ResearchWebError('Unknown qualified benchmark identifier', 404)
        return folder

    def _capture(self):
        result = {}
        for agency in AGENCIES:
            source = self.spec['sources'][agency]
            for suffix, field in (('.csv', 'csv_sha256'), ('-metadata.json', 'metadata_sha256')):
                name = f'source-{agency}{suffix}'
                data = _read(self.source_base / name, 8 * 1024 * 1024)
                if web._sha(data) != source[field]:
                    raise web.ResearchWebError('Official public source differs from its prospective source pin')
                result[name] = data
        return result

    def _qualify(self, sources):
        audit = qualified_encoding.qualify_sources({agency: sources[f'source-{agency}.csv'] for agency in AGENCIES})
        if (audit.get('status') != 'validated' or audit.get('no_labels_derived') is not True
                or audit.get('no_fits') is not True or audit.get('no_random_draws') is not True):
            raise web.ResearchWebError('Public encoding qualification did not meet the fixed research plan')
        for agency in AGENCIES:
            domain = audit['agencies'][agency]
            source = self.spec['sources'][agency]
            if (domain['raw_observations'] != source['expected_observations']
                    or domain['source_sha256'] != source['csv_sha256']
                    or any(domain['split_counts'][split] < 1 for split in ('train', 'auxiliary', 'test'))
                    or domain['unknown_or_missing_encodings'] != 0):
                raise web.ResearchWebError('Source frame counts or semantic encodings are inconsistent')
        return audit

    def _tasks(self, audit=None):
        tasks = []
        for agency in AGENCIES:
            source = self.spec['sources'][agency]
            qualification = None
            if audit is not None:
                domain = audit['agencies'][agency]
                qualification = {key: domain[key] for key in
                                 ('raw_observations', 'eligible_observations', 'split_counts',
                                  'features', 'unknown_or_missing_encodings', 'calendar_method', 'limitations')}
            tasks.append({'id': agency, 'agency': source['agency'], 'title': source['task_title'],
                          'source_url': source['source_url'], 'licence_url': source['licence_url'],
                          'source_attribution': source['source_attribution'], 'unit': source['unit'],
                          'temporal_splits': source['temporal_splits'],
                          'research_margin': source['research_margin'], 'qualification': qualification})
        return tasks

    def catalog(self):
        audit = None
        blocked = []
        try:
            self._ensure_runtime()
            audit = self._qualify(self._capture())
        except (OSError, ValueError, KeyError, qualified_encoding.QualificationError, web.ResearchWebError):
            blocked.append('Pinned complete public sources or their semantic encodings are unavailable or invalid')
        return {'schema': 'mra-qualified-benchmark-catalog/1.0', 'specification_sha256': self.spec_sha,
                'scope': dict(SCOPE), 'ready': audit is not None, 'blocked_reasons': blocked,
                'tasks_order': list(AGENCIES), 'tasks': self._tasks(audit)}

    def _planned_artifacts(self, sources, audit):
        audit_without_rows = {**audit, 'agencies': {
            agency: {key: value for key, value in domain.items() if key != 'rows'}
            for agency, domain in audit['agencies'].items()}}
        cohort = {'schema': 'mra-qualified-cohort-plan/1.0',
                  'selection': 'Census of every eligible source observation in each fixed temporal window; no outcome-based selection',
                  'sampling_inclusion_probability': '1/1 for every eligible held-out published observation',
                  'sampling_uncertainty': 'None for complete fixed finite published frame; no iid person or future-population interval',
                  'no_labels_derived': True, 'no_fits': True, 'no_random_draws': True,
                  'agencies': {agency: {'features': domain['features'], 'split_counts': domain['split_counts'],
                                        'rows': domain['rows']} for agency, domain in audit['agencies'].items()}}
        summary = ('Phase 5 public research preregistration\n'
                   'MOH, MAS and MSF public aggregate test beds; no agency endorsement.\n'
                   'Every eligible held-out published observation is included.\n'
                   'Exact calendar, numeric, category and source-line feature validation passed.\n'
                   'Strict Brier dominance uses research margin zero and lower gain > zero.\n'
                   'No binary outcome bits were derived; no model fit or randomized block was generated.\n'
                   'Public usefulness: not evaluated. Agency acceptance: pending. Release authority: none.\n'
                   'Finite historical frame coverage does not establish population or future usefulness.\n')
        return {'specification.json': self.spec_raw, 'runtime.json': _canonical(self.runtime),
                'encoding-audit.json': _canonical(audit_without_rows),
                'cohort-plan.json': _canonical(cohort),
                'margin-rationale.json': _canonical(_margin_rationale(self.spec)),
                'qualification.txt': summary.encode('utf-8'), **sources}

    def create(self):
        self._ensure_runtime()
        sources = self._capture()
        audit = self._qualify(sources)
        identity = {'specification_sha256': self.spec_sha, 'runtime': self.runtime,
                    'source_sha256': {name: web._sha(data) for name, data in sources.items()}}
        run_id = web._sha(_canonical(identity))[:32]
        folder = self.root / run_id
        web._check_path(folder)
        try:
            folder.mkdir(exist_ok=False)
        except FileExistsError:
            return self.detail(run_id)
        registration = {'schema': 'mra-qualified-preregistration/1.0', 'run_id': run_id,
                        'preregistered_at': _now(), 'identity': identity,
                        'registration_before_binary_outcome_derivation': True,
                        'registration_before_model_fitting': True,
                        'registration_before_benchmark_randomness': True,
                        'public_source_values_inspected_for_encoding_validation': True,
                        'historically_untouched_holdout_claim': False,
                        'scope': dict(SCOPE), 'public_usefulness': 'not_evaluated',
                        'custody': _CUSTODY}
        # Registration is flushed first. Completion publishes last. A crash or
        # concurrent observation of incomplete work remains blocked on restart.
        _json(folder / 'preregistration.json', registration)
        expected = {'preregistration.json': _canonical(registration),
                    **self._planned_artifacts(sources, audit)}
        for name, data in expected.items():
            if name != 'preregistration.json':
                _write(folder / name, data)
        completion = {'schema': 'mra-qualified-registration-completion/1.0', 'run_id': run_id,
                      'specification_sha256': self.spec_sha,
                      'artifacts': {name: {'sha256': web._sha(data), 'bytes': len(data)}
                                    for name, data in expected.items()}}
        _json(folder / 'registration-completion.json', completion)
        return self.detail(run_id)

    def _verified(self, run_id):
        self._ensure_runtime()
        try:
            return self._verified_impl(run_id)
        except web.ResearchWebError:
            raise
        except (OSError, ValueError, TypeError, KeyError, AttributeError, qualified_encoding.QualificationError) as exc:
            raise web.ResearchWebError('Invalid captured public qualification evidence; delivery is blocked') from exc

    def _verified_impl(self, run_id):
        folder = self._folder(run_id)
        if not (folder / 'registration-completion.json').exists():
            raise web.ResearchWebError('Incomplete public preregistration is reserved and blocked; preserve its incident evidence', 409)
        captured = {name: _read(folder / name) for name in ARTIFACTS}
        registration = _decode(captured['preregistration.json'])
        completion = _decode(captured['registration-completion.json'])
        fields = {'schema', 'run_id', 'preregistered_at', 'identity',
                  'registration_before_binary_outcome_derivation', 'registration_before_model_fitting',
                  'registration_before_benchmark_randomness', 'public_source_values_inspected_for_encoding_validation',
                  'historically_untouched_holdout_claim', 'scope', 'public_usefulness', 'custody'}
        if (type(registration) is not dict or set(registration) != fields
                or type(completion) is not dict or registration.get('custody') != _CUSTODY
                or type(registration.get('identity')) is not dict
                or set(registration['identity']) != {'specification_sha256', 'runtime', 'source_sha256'}
                or type(registration['identity'].get('source_sha256')) is not dict
                or set(registration['identity']['source_sha256']) !=
                   {name for name in ARTIFACTS if name.startswith('source-')}
                or any(type(value) is not str or not _SHA.fullmatch(value)
                       for value in registration['identity']['source_sha256'].values())
                or type(registration.get('preregistered_at')) is not str):
            raise web.ResearchWebError('Invalid exact preregistration fields or local custody claim')
        stamp = registration['preregistered_at']
        if not stamp.endswith('Z') or len(stamp) > 32:
            raise web.ResearchWebError('Invalid local prospective registration timestamp')
        parsed = datetime.fromisoformat(stamp[:-1] + '+00:00')
        if parsed.isoformat().replace('+00:00', 'Z') != stamp:
            raise web.ResearchWebError('Noncanonical local prospective registration timestamp')
        if (registration.get('schema') != 'mra-qualified-preregistration/1.0'
                or registration.get('run_id') != run_id
                or registration.get('scope') != SCOPE
                or registration.get('public_usefulness') != 'not_evaluated'
                or registration.get('identity', {}).get('runtime') != self.runtime
                or registration['identity'].get('specification_sha256') != self.spec_sha
                or captured['specification.json'] != self.spec_raw
                or web._sha(_canonical(registration['identity']))[:32] != run_id
                or not all(registration.get(key) is True for key in
                           ('registration_before_binary_outcome_derivation', 'registration_before_model_fitting',
                            'registration_before_benchmark_randomness', 'public_source_values_inspected_for_encoding_validation'))
                or registration.get('historically_untouched_holdout_claim') is not False):
            raise web.ResearchWebError('Saved preregistration differs from its bound public research plan')
        sources = {name: captured[name] for name in ARTIFACTS if name.startswith('source-')}
        source_hashes = {name: web._sha(data) for name, data in sources.items()}
        if source_hashes != registration['identity']['source_sha256']:
            raise web.ResearchWebError('Captured public sources differ from their registered identity')
        for agency in AGENCIES:
            for suffix, field in (('.csv', 'csv_sha256'), ('-metadata.json', 'metadata_sha256')):
                if source_hashes[f'source-{agency}{suffix}'] != self.spec['sources'][agency][field]:
                    raise web.ResearchWebError('Captured source differs from the fixed original source pin')
        audit = self._qualify(sources)
        expected = {'preregistration.json': captured['preregistration.json'],
                    **self._planned_artifacts(sources, audit)}
        if any(captured[name] != data for name, data in expected.items()):
            raise web.ResearchWebError('Encoding or cohort artifacts differ from deterministic semantic reconstruction')
        expected_completion = {'schema': 'mra-qualified-registration-completion/1.0', 'run_id': run_id,
                               'specification_sha256': self.spec_sha,
                               'artifacts': {name: {'sha256': web._sha(data), 'bytes': len(data)}
                                             for name, data in expected.items()}}
        if completion != expected_completion:
            raise web.ResearchWebError('Registration completion differs from captured immutable artifacts')
        return captured, registration, audit

    def detail(self, run_id):
        captured, registration, audit = self._verified(run_id)
        return {'schema': 'mra-qualified-benchmark-run/1.0', 'run_id': run_id,
                'status': 'preregistered', 'preregistered_at': registration['preregistered_at'],
                'specification_sha256': self.spec_sha, 'scope': dict(SCOPE),
                'tasks': self._tasks(audit), 'comparisons_required': 6,
                'public_usefulness': 'not_evaluated',
                'artifacts': [{'name': name, 'url': f'{PREFIX}/runs/{run_id}/artifacts/{name}',
                               'sha256': web._sha(data), 'bytes': len(data)}
                              for name, data in captured.items()]}

    def artifact(self, run_id, name):
        if type(name) is not str or name not in ARTIFACTS:
            raise web.ResearchWebError('Unknown qualified benchmark artifact', 404)
        captured, _, _ = self._verified(run_id)
        return captured[name]

    def runs(self):
        result = []
        for folder in sorted(self.root.iterdir()):
            if _RUN.fullmatch(folder.name) and folder.is_dir():
                try:
                    detail = self.detail(folder.name)
                    result.append({key: detail[key] for key in
                                   ('run_id', 'status', 'preregistered_at', 'specification_sha256')})
                except (web.ResearchWebError, OSError, ValueError, KeyError):
                    result.append({'run_id': folder.name, 'status': 'blocked',
                                   'preregistered_at': None, 'specification_sha256': self.spec_sha})
        return {'schema': 'mra-qualified-benchmark-runs/1.0', 'runs': result}