# Model Release Assurance

Model Release Assurance (MRA) is a Python reference implementation for evaluating and authorizing model-release contracts. It binds a model artifact to its interface, recipient, population, controls, utility requirements, evidence, and related releases before returning a typed decision.

MRA is sector-neutral and supports protected units such as people, households, organizations, programmes, transactions, devices, and events.

> **Status:** offline reference implementation, version 0.5.0. It is not an accredited production authorization service.

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
- Every result is bound to the artifact, complete interface, recipient information, population, policy, controls, and portfolio state.
- Evaluated-to-released transfer requires direct reassessment or a verified information-reduction certificate in the safe direction.
- Utility is enforced before selecting a least-informative feasible release.
- Portfolio dependence must be assessed directly, composed analytically, or bounded by a replayable incomplete-portfolio certificate.
- `unassessed` and `inconclusive` states cannot authorize release.
- Signatures protect integrity and non-repudiation; they do not validate the truth of submitted evidence.

See [architecture](docs/architecture.md), [threat model](docs/reference/threat-model.md), and [production roadmap](docs/reference/production-roadmap.md).

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
