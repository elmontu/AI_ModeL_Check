# Model Release Assurance

Model Release Assurance (MRA) is a Python reference implementation for evaluating and authorizing model-release contracts. It binds a model artifact to its interface, recipient, population, controls, utility requirements, evidence, and related releases before returning a typed decision.

MRA is sector-neutral and supports protected units such as people, households, organizations, programmes, transactions, devices, and events.

> **Status:** offline reference implementation, version 0.6.0. It is not an accredited production authorization service.

The `0.x` series is an alpha interface: decision invariants are tested, but schemas and APIs may change between minor versions. See the [changelog](CHANGELOG.md), [support policy](SUPPORT.md), and [release process](docs/releasing.md).

## Decisions

The engine returns one of four outcomes:

- `release_as_proposed`: every mandatory requirement is satisfied;
- `release_with_controls`: a restricted configuration satisfies the policy;
- `redesign_required`: the submitted evidence or configuration set is incomplete; or
- `reject`: a replayable exhaustive-search certificate shows that no submitted option can satisfy the policy.

Missing, stale, mismatched, underpowered, or unassessed evidence never becomes evidence of safety.

## Repository layout

```text
src/model_release_assurance/   Python package and CLI
schemas/                       versioned JSON contracts
examples/                      executable requests, evidence, and policies
tests/                         unit, replay, and integration tests
docs/                          architecture, security, adoption, and deployment guidance
scripts/                       optional benchmark and evidence-generation utilities
reproduction/                  benchmark configurations and retained manifests
.github/workflows/             GitHub Actions CI
```

Generated assessments, audit databases, trained models, benchmark output, reports, and local build intermediates are intentionally excluded from version control.

## Installation

MRA requires Python 3.11 or newer.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

Install the finite portfolio solver when required:

```bash
python -m pip install -e '.[portfolio]'
```

Install the optional benchmark dependencies separately:

```bash
python -m pip install -e '.[experiments]'
```

## Review any model family

MRA includes a governed catalog for classical, tree, kernel, neural, vision, audio, time-series, recommender, unsupervised, embedding, graph, generative, multimodal, composite and agentic systems. Catalog coverage routes the release to appropriate checks; it never clears a model by itself.

```bash
mra model-coverage --json
mra model-coverage examples/request.json --json
```

See the [all-model coverage matrix](docs/model-family-coverage.md) and the [0.6 framework update](docs/model-release-assurance-0.6-update.md). Unknown families route to custom review, and unsupported interactive protocols remain inconclusive.

### Coverage is not clearance

| Layer | Current coverage | Decision meaning |
|---|---|---|
| Model catalog | 20 categories covering classical, neural, generative, multimodal, composite and agentic systems | Routes checks and identifies gaps; always `can_clear: false` |
| Core analyzers | Tree linkage, differential-privacy replay, generic attack floors, controlled inference and population screens | May contribute only according to the declared evidence direction and exact release context |
| XGBoost worker | Deterministic classification, utility, structure and membership screening | Floor or screen only; never clears |
| LLM profile | Watermark and canary preregistration validation | Protocol linter only; emits no scientific evidence |
| Other model families | Contract and threat routing | Dedicated modality/family workers are required before evidence can be used |

Recommended threats that are absent from a request appear as policy-review advisories. They are not silently made mandatory, but the policy owner must justify why the corresponding secret or harm is out of scope.

### Assessment schema 3.0

Version 0.6 uses the breaking assessment v3 contract:

- every release requires a structured `model_profile` describing its task, modalities, training paradigm, components, generative behavior and state;
- every analyzer source requires an `evidence_context` observed before analysis and binding the release contract, policy, artifact, interface, population, decision game and observation time; and
- assessment reports preserve the model profile and source bindings used by each decision.

The current schemas are [`assessment-request-v3.json`](schemas/assessment-request-v3.json) and [`assessment-report-v3.json`](schemas/assessment-report-v3.json). Historical v2 evidence cannot be converted by copying current hashes into old results; it must be recollected or migrated by an approved worker that can establish the original observations.

## Run a local XGBoost audit

The repository includes an experiment worker for trusted local CSV or Parquet classification data. It trains independent target/reference XGBoost pipelines, measures utility and tree structure, runs a calibrated membership attack, and emits hash-bound artifacts without loading executable models in the MRA core.

```bash
python scripts/run_xgboost_audit.py \
  --config reproduction/xgboost/config.json \
  --output-dir output/xgboost
```

Start from [`reproduction/xgboost/config.example.json`](reproduction/xgboost/config.example.json) and see the [XGBoost worker guide](docs/xgboost.md). Configuration version 1.1 binds the decision game, corrects confidence across all replicate bounds, and reports PPV at preregistered membership priors. Attack output is a floor or screen and can never clear a release.

## Audit an interactive LLM

The LLM audit profile separates two different checks:

- output watermark detection tests a declared provenance signal under the exact decoding and transformation protocol;
- synthetic canary testing measures bounded memorization or extraction evidence for canaries that were authorized and verifiably inserted into training.

Start from [`reproduction/llm/audit-profile.example.json`](reproduction/llm/audit-profile.example.json), validate it with `python scripts/validate_llm_audit_profile.py ...`, and follow the [watermarking and canary-testing guide](docs/llm-watermark-canary.md). Do not place real secrets or plaintext canaries in the retained profile. The linter is not an analyzer: a detected canary may block only through future dedicated, provenance-complete evidence; a missing watermark or unsuccessful extraction attempt is only a screen. Neither result clears an interactive LLM, which still requires transcript-level assurance for the complete protocol.

## Quick start

Validate and assess an example release contract:

```bash
mra validate examples/request.json
mra assess examples/request.json \
  --output output/assessments/demo-report.json \
  --audit-db output/audit/mra.sqlite3
```

Select a release configuration:

```bash
mra optimize examples/optimization-request.json \
  --output output/assessments/demo-optimization.json \
  --audit-db output/audit/mra.sqlite3
```

Solve and independently replay a finite protocol certificate:

```bash
mra protocol-solve examples/protocol-feasibility-problem.json \
  --output output/assessments/demo-protocol-certificate.json
mra protocol-verify output/assessments/demo-protocol-certificate.json \
  --problem examples/protocol-feasibility-problem.json
```

Solve and replay an incomplete-portfolio certificate:

```bash
mra portfolio-solve examples/incomplete-portfolio-problem.json \
  --output output/assessments/demo-portfolio-certificate.json \
  --evidence-base examples
mra portfolio-verify output/assessments/demo-portfolio-certificate.json \
  --evidence-base examples
```

## Core safety invariants

- A validated attack establishes a lower bound and may block; it cannot clear.
- Clearance requires an applicable exact value, verified upper bound, accountant, or replayable certificate.
- Every analyzer source carries a pre-analysis evidence context binding the release contract, policy, artifact, interface, population and decision game; results copy those bindings without restamping.
- Evaluated-to-released transfer requires direct reassessment or a verified information-reduction certificate in the safe direction.
- Utility is enforced before selecting a least-informative feasible release.
- Portfolio dependence must be assessed directly, composed analytically, or bounded by a replayable incomplete-portfolio certificate.
- `unassessed` and `inconclusive` states cannot authorize release.
- Signatures protect integrity and non-repudiation; they do not validate the truth of submitted evidence.

See [architecture](docs/architecture.md), [threat model](docs/reference/threat-model.md), and [production roadmap](docs/reference/production-roadmap.md).

The [2026-08-22 framework audit](docs/audit-2026-08-22.md) records the production-boundary findings. Version 0.6 resolves its signing, claimant-selected payload and source-originated release-binding defects. The repository remains non-production because dedicated analyzers, exact clearance-boundary arithmetic, trusted workers, registry/gateway enforcement and accreditation are still incomplete.

The [privacy-assurance literature review](docs/literature-review.md) synthesizes the primary conference literature behind the framework's XGBoost, membership-inference, differential-privacy, LLM-canary, and watermarking evidence semantics. Its central constraint is that an unsuccessful empirical attack is not evidence of safety.

The [literature-driven check critique](docs/check-critique-2026-08-22.md) maps those findings to the implemented checks, records what was strengthened, and identifies the provenance and coverage work that still blocks production use.

## Development

The standard local verification command is:

```bash
make check
```

Run the test suite:

```bash
python -m pip install -r requirements.lock
PYTHONPATH=src python -m unittest discover -s tests -v
```

Run a source compilation check:

```bash
PYTHONPATH=src python -m compileall -q src tests
```

The GitHub Actions workflow runs both checks and verifies that committed JSON schemas match the current models.

## Production boundary

The repository supplies an offline decision core. A production deployment also needs authoritative identity and separation of duties, isolated analyzer workers, managed keys and storage, monitoring and incident response, a transactionally locked portfolio registry, population validation, independent security review, and institutional accreditation.

Interactive LLM services require transcript-level analysis covering prompts, retrieval, tools, memory, updates, concurrency, and query budgets. One-shot attack results are not sufficient to authorize such a service.

## Security and contributions

- Report security issues using [SECURITY.md](SECURITY.md).
- Development and pull-request guidance is in [CONTRIBUTING.md](CONTRIBUTING.md).
- Supported use and issue-routing guidance is in [SUPPORT.md](SUPPORT.md).
- Operational documentation is indexed in [docs/README.md](docs/README.md).

## Licensing

No public-use licence has been selected. Do not treat repository visibility as permission to use, modify, or redistribute the software. Selecting and approving a licence is a required gate before a public release.
