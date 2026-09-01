# Model Release Assurance

[![CI](https://github.com/elmontu/AI_ModeL_Check/actions/workflows/ci.yml/badge.svg)](https://github.com/elmontu/AI_ModeL_Check/actions/workflows/ci.yml)

Model Release Assurance (MRA) has an offline, fail-closed Python reference core for validating model-release contracts, assessing evidence bound to a proposed release, selecting policy-compliant configurations, and replaying [MRAP/1.0](docs/model-release-assurance-protocol.md) protocol records.

MRA produces recommendations and replayable certificates. It does **not** authorize, deploy, or serve models.

> **Status:** alpha (`0.7.0`) and sector-neutral. The supported core is offline; optional evidence-lab workers may execute local model code, launch subprocesses, or download public datasets. The repository implements MRAP conformance levels L0–L2 and a machine-checked protocol core. Interfaces and schemas may change between minor `0.x` releases.

## Operational model: contracts, pipelines, and workflows

| Layer | Responsibility | Where it lives | Current boundary |
|---|---|---|---|
| **Contracts** | Define valid requests, evidence, reports, policies, and protocol records | [`schemas/`](schemas/), Pydantic models, [MRAP/1.0](docs/model-release-assurance-protocol.md), [`formal/`](formal/) | Versioned public contracts and reference semantics |
| **Pipelines** | Analyze evidence, evaluate gates, optimize configurations, and generate replayable artifacts | `mra` CLI, [`src/model_release_assurance/`](src/model_release_assurance/), [`scripts/`](scripts/) | Supported core plus clearly labelled experimental workers |
| **Workflows** | Coordinate lifecycle states, authorization, activation, monitoring, suspension, and revocation | MRAP specification and offline transcript verifier | Durable production orchestration is **not implemented** here |

Evidence pipelines feed the reference implementation. Its reports then feed an external authority, registry, and serving gateway. Assessment output is never an authorization.

The [integrated system audit specification](docs/system-audit-specification.md) provides one standalone view of the architecture, normative MRAP lifecycle, contracts, controls, formal boundary, deployment obligations, and audit checklist. The [full software architecture](docs/architecture.md) remains the detailed implementation map.

## What the toolkit does

- Validates versioned model-release requests and policies.
- Evaluates linkage, membership, attribute, reconstruction, and population evidence bound to the release, policy, source, analyzer implementation/version, and analyzer configuration.
- Returns `release_as_proposed`, `release_with_controls`, `redesign_required`, or `reject` recommendations.
- Selects the least-informative feasible configuration when the required evidence supports one.
- Separately checks candidate utility, controls, portfolio support, active-policy authorization of the selection rule, and supplied lifecycle-transcript structure or signatures.
- Generates and replays feasibility and portfolio certificates, verifies interface-bound signed manifests and ledger-namespaced audit chains, and replays protocol transcripts.
- Routes model families and threats to applicable checks without treating catalog coverage as clearance.
- After successful request parsing/validation, records assessment/optimization intent before analyzer/optimizer execution and detects failed or orphaned runs in the required CLI audit database.

Missing, stale, mismatched, underpowered, or unassessed evidence never becomes evidence of safety. A successful attack may block a release; an unsuccessful attack does not prove safety.

## What remains outside this repository

Production MRAP-L3/L4 deployments still require authenticated identities and separation of duties, isolated evidence workers, managed keys and immutable retained records, a linearizable authorization and budget registry, an enforcing gateway, durable retries and incident handling, monitoring and revocation, independent security review, and institutional accreditation. In particular, a gateway must independently prove that the deployed bundle and every live output/side channel conform to the declared interface; no assessment report performs that live check. See the [production roadmap](docs/reference/production-roadmap.md).

## Supported surfaces

| Surface | Status | Intended use |
|---|---|---|
| Python package and `mra` CLI | **Reference core** | Contract validation, assessment, optimization, schema generation, signing, and replay |
| Versioned JSON Schemas | **Public contracts** | A deterministic manifest inventories every current schema byte-for-byte; superseded files preserve historical structure for archival or external validation, not executable replay by the current CLI |
| MRAP specification and Lean model | **Normative/reference** | Lifecycle semantics, protocol review, and scoped machine-checked properties |
| `scripts/` and `reproduction/` | **Experimental** | Evidence generation, benchmarks, and retained study inputs; not a stable API |
| MCP/RAG, empirical workflows, and red-team helpers | **Incubating** | Source-tree evaluation and integration experiments |

The logical Python components are documented in the [project scope](docs/project-scope.md). Internal modules are not automatically stable public APIs merely because they are importable.

## Quick start

MRA requires Python 3.11 or newer.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

Validate and assess the example release contract:

```bash
mra validate examples/request.json
mra assess examples/request.json \
  --output output/assessments/demo-report.json \
  --audit-db output/audit/mra.sqlite3
```

Select a candidate configuration:

```bash
python -m pip install -e '.[portfolio]'
mra optimize examples/optimization-request.json \
  --output output/assessments/demo-optimization.json \
  --audit-db output/audit/mra.sqlite3
```

Inspect model-family coverage:

```bash
mra model-coverage --json
mra model-coverage examples/request.json --json
```

Generate or verify the other supported contract families with `mra --help`. The [`examples/`](examples/) directory contains small executable inputs for assessment, optimization, protocol feasibility, and portfolio commands.

## Decision and protocol boundary

The offline assessment recommendations are inputs to the larger MRAP lifecycle:

```text
DRAFT -> REGISTERED -> PLAN_FROZEN -> EVIDENCE_FROZEN
      -> ASSESSED -> OPTIMIZED -> COMMIT_PENDING
      -> AUTHORIZED -> ACTIVE -> SUSPENDED / EXPIRED / REVOKED
```

Only an external atomic registry transition from `COMMIT_PENDING` to `AUTHORIZED` creates an authorization. Activation additionally requires a gateway to verify the exact approved artifact, interface, controls, expiry, and revocation state.

The offline verifier can replay structural or authenticated protocol transcripts:

```bash
mra release-protocol-verify path/to/release-protocol-run.json \
  --artifact-base path/to/protocol-artifacts \
  --output output/protocol-verification.json
```

Authenticated replay additionally requires a trust store and `--require-authenticated`. It verifies signatures and protocol bindings; it is not an identity provider, registry, gateway, or scientific-evidence validator.

## Evidence lab

Experimental tools are kept separate from the supported CLI. Install their dependencies only when working on evidence generation or benchmarks:

```bash
python -m pip install -e '.[experiments]'
```

The public-privacy worker additionally needs the `privacy-experiments` extra,
and a live MCP server needs the `mcp` extra. The [script catalog](scripts/README.md#dependency-guide)
maps each optional capability to its dependency tier.

| Capability | Entry point | Guide or retained input |
|---|---|---|
| Local XGBoost classification audit | `scripts/run_xgboost_audit.py` | [XGBoost worker guide](docs/xgboost.md) |
| XGBoost/MLP empirical and red-team workflow | `scripts/run_empirical_xgboost_mlp_workflow.py` | [SACRO-ML-inspired red-team guide](docs/sacro-ml-red-team.md) |
| Post-critique control regressions | `scripts/evaluate_design_controls.py` | [Retained 12-case result](reproduction/design-control-validation/results.json) and [interpretation](reproduction/design-control-validation/README.md) |
| LLM watermark/canary profile validation | `scripts/validate_llm_audit_profile.py` | [LLM audit guide](docs/llm-watermark-canary.md) |
| OpenML, public-privacy, portfolio, and strategic studies | grouped runners in `scripts/` | [`reproduction/`](reproduction/) |

These tools emit bounded measurements, candidate attack floors, or screens—never authorization.
Their output is not an admissible `EvidenceRecord` until an approved worker binds or recollects it for
a complete assessment request. Generated research reports, models, audit databases, and benchmark
output may use ignored `output/` paths. Governance records must instead be copied transactionally to
adopter-owned immutable storage with retention, legal-hold, backup, restore, access, and destruction
rules.

## Repository map

```text
src/model_release_assurance/   Installable reference implementation and CLI
schemas/                       Versioned public machine contracts
formal/                        Abstract protocol specification and Lean proofs
examples/                      Small supported CLI examples
tests/                         Core, integration, and experimental verification
scripts/                       Developer and study entry points; not public CLI
reproduction/                  Retained study inputs, configurations, and manifests
docs/                          Product, protocol, operational, and research guidance
output/                        Generated local artifacts; ignored by Git
```

The paths stay intentionally stable because scripts, tests, documentation, and retained manifests cross-reference them. Their ownership and maturity are defined in the [project scope](docs/project-scope.md), [documentation index](docs/README.md), [script catalog](scripts/README.md), and [reproduction index](reproduction/README.md).

## Core safety invariants

- Attack floors can block but never clear a threat.
- Clearance requires applicable exact values, verified upper bounds, accountants, or replayable certificates.
- Evidence is bound to the release contract, policy, artifact, interface, population, decision game, and observation time before analysis.
- Evidence records identify the analyzer service/version and implementation/configuration digests; policy pins the minimum and accepted producer set.
- Every retained evidence record is dispositioned by identifier as included or excluded, and the active policy allowlists the exact selection-policy digest.
- Evaluated-to-released transfer requires reassessment or a verified information-reduction argument in the safe direction.
- Utility is enforced before selecting a least-informative feasible release.
- Portfolio dependence must be measured, composed, or conservatively bounded.
- Assessment `clear` is explicitly scoped to one release and the submitter-declared interface; it is non-authorizing. Offline selection binds a declared snapshot; production authorization still requires an authenticated authoritative portfolio snapshot and a separate live gateway-conformance receipt.
- `unassessed` and `inconclusive` mandatory threats cannot produce an overall clearance.
- A contradictory ceiling cannot weaken an independently established blocking floor; contradiction is recorded separately from missing evidence.
- Signatures establish integrity and provenance; they do not establish that submitted evidence is true.
- Reports and verification outputs carry source/component/runtime profiles for replay attribution; those self-reported digests are not trusted-build attestations.

See the [architecture](docs/architecture.md), [mathematical foundations](docs/mathematical-foundations.md), [threat model](docs/reference/threat-model.md), and [formal verification scope](docs/formal-verification.md) for the detailed claims and non-claims.

## Development and verification

Install the pinned core and experimental test dependencies before running the complete Python suite:

```bash
python -m pip install -r requirements.lock
python -m pip install -r requirements-experiments.txt
make check
```

With the pinned Lean toolchain installed, run all Python, schema, documentation-link, regression, and formal checks:

```bash
make verify
```

Contribution rules are in [CONTRIBUTING.md](CONTRIBUTING.md); releases follow [docs/releasing.md](docs/releasing.md). Release history and migration notes are recorded in [CHANGELOG.md](CHANGELOG.md).

## Security, support, and licensing

- Report vulnerabilities using [SECURITY.md](SECURITY.md), not a public issue.
- Use [SUPPORT.md](SUPPORT.md) for supported-use and issue-routing guidance.
- The complete documentation map is in [docs/README.md](docs/README.md).
- No public-use licence has been selected. Repository visibility is not permission to use, modify, or redistribute the software.
