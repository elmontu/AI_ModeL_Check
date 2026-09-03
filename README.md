# Model Release Assurance

[![CI](https://github.com/elmontu/AI_ModeL_Check/actions/workflows/ci.yml/badge.svg)](https://github.com/elmontu/AI_ModeL_Check/actions/workflows/ci.yml)

Model Release Assurance (MRA) has an offline, fail-closed Python reference core for validating model-release contracts, assessing evidence bound to a proposed release, selecting policy-compliant configurations, and replaying [MRAP/1.0](docs/model-release-assurance-protocol.md) protocol records.

MRA produces recommendations and replayable certificates. It does **not** authorize, deploy, or serve models.

> **Status:** alpha (`0.7.0`) and sector-neutral. The supported core is offline; optional evidence-lab workers may execute local model code, launch subprocesses, or download public datasets. The repository provides reference capabilities aligned with MRAP L0–L2 and a machine-checked protocol core; it does not claim complete conformance while the documented G7 numeric and production-control obligations remain open. Interfaces and schemas may change between minor `0.x` releases.

## Operational model: contracts, pipelines, and workflows

| Layer | Responsibility | Where it lives | Current boundary |
|---|---|---|---|
| **Contracts** | Define valid requests, evidence, reports, policies, and protocol records | [`schemas/`](schemas/), Pydantic models, [MRAP/1.0](docs/model-release-assurance-protocol.md), [`formal/`](formal/) | Versioned public contracts and reference semantics |
| **Pipelines** | Analyze evidence, evaluate gates, optimize configurations, and generate replayable artifacts | `mra` CLI, [`src/model_release_assurance/`](src/model_release_assurance/), [`scripts/`](scripts/) | Supported core plus clearly labelled experimental workers |
| **Workflows** | Coordinate lifecycle states, authorization, activation, monitoring, suspension, and revocation | MRAP specification and offline transcript verifier | Durable production orchestration is **not implemented** here |

Evidence pipelines feed the reference implementation. Its reports then feed an external authority, registry, and serving gateway. Assessment output is never an authorization.

The [integrated system audit specification](docs/system-audit-specification.md) provides one standalone view of the architecture, normative MRAP lifecycle, contracts, controls, formal boundary, deployment obligations, and audit checklist. The [full software architecture](docs/architecture.md) remains the detailed implementation map. The [ceiling experiment report](paper/ceiling-experiment-results.md) records a completed controlled validation and a completed mixed model-backed result; the [2026-09-02 real-data execution audit](docs/real-data-training-hook-audit-2026-09-02.md) records the five-model GPU hook experiments and their non-authorizing release implications. Authors can begin with the dedicated [MLSys paper workspace](paper/README.md), which separates supportable claims from configured or missing experiments.

## What the toolkit does

- Validates versioned model-release requests and policies.
- Evaluates linkage, membership, attribute, reconstruction, and population evidence bound to the release, policy, source, analyzer implementation/version, and analyzer configuration.
- Returns `release_as_proposed`, `release_with_controls`, `redesign_required`, or `reject` recommendations.
- Selects the least-informative feasible configuration when the required evidence supports one.
- Separately checks candidate utility, controls, portfolio support, active-policy authorization of the selection rule, and supplied lifecycle-transcript structure or signatures.
- Generates and replays feasibility and portfolio certificates, verifies interface-bound signed manifests and ledger-namespaced audit chains, and replays protocol transcripts.
- Routes model families and threats to applicable checks without treating catalog coverage as clearance.
- Requires every policy-accepted generic attack, controlled-inference, and canary floor family to be
  submitted under a required analyzer rule, with content-addressed outcome-free member design
  registrations; omitting an approved family cannot improve the decision.
- Accepts a model-family-neutral `finite_channel_ceiling` submission when a release has a complete,
  enforced finite recipient interface and selection-valid simultaneous state-conditioned evidence;
  the analyzer emits both a confidence floor and an outward-replayed confidence ceiling for the
  canonical exact-guess game frozen by policy.
- Requires a policy-bound, complete attack battery with centrally replayed positive controls, catalog/time-valid execution, supported multiplicity, observable resource-limit checks, and per-run executor identity before a statistical ceiling may clear a threat; individual attacks remain floor-or-screen evidence only.
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
| Typed attack-battery contracts and trusted-core analyzer | **Reference core** | Policy-bound floor/screen translation and a mandatory ceiling-clearance precondition; no model execution |
| [`finite_channel_ceiling` analyzer](schemas/finite-channel-ceiling-submission-v1.json) | **Reference core** | Model-family-neutral finite-channel confidence bounds; requires a [policy-frozen game](schemas/finite-decision-game-v1.json), [typed prior evidence](schemas/finite-state-prior-evidence-v1.json), complete-interface recipient-realizable evidence, and exact/outward replay |
| MCP/RAG, empirical workflows, and red-team execution helpers | **Incubating** | Source-tree evaluation and integration experiments |

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
the LLM training-hook worker needs the `llm-experiments` extra, the EuroSAT
vision worker needs the `vision-experiments` extra, and a live MCP server needs
the `mcp` extra. The [script catalog](scripts/README.md#dependency-guide) maps
each optional capability to its dependency tier.

| Capability | Entry point | Guide or retained input |
|---|---|---|
| Local XGBoost classification audit | `scripts/run_xgboost_audit.py` | [XGBoost worker guide](docs/xgboost.md) |
| XGBoost/MLP empirical and red-team workflow | `scripts/run_empirical_xgboost_mlp_workflow.py` | [SACRO-ML-inspired red-team guide](docs/sacro-ml-red-team.md) |
| Policy-bound attack-battery demonstration | `examples/request.json` | [Attack catalog, positive-control, worker-output, and submission contracts](schemas/README.md) |
| LLM watermark/canary profile validation | `scripts/validate_llm_audit_profile.py` | [LLM audit guide](docs/llm-watermark-canary.md) |
| Real-data three-model LLM training-hook and context-risk matrix | `scripts/run_llm_training_hook_audit.py --config reproduction/llm-training-hook/config.json` | [Pinned 8,192/1,024-row WildChat causal-LM matrix](reproduction/llm-training-hook/README.md) |
| Full real-data vision training-hook and release-context matrix | `scripts/run_vision_training_hook_audit.py --config reproduction/vision-training-hook/config.json` | [All 27,000 EuroSAT images with canonical from-scratch AlexNet/DenseNet-121](reproduction/vision-training-hook/README.md) |
| Five-model composition-scaling matrix | `scripts/run_composition_scaling_suite.py --config reproduction/composition-scaling/suite-config.json` | [Shared WildChat/EuroSAT scale, seed, hook, attack, and portfolio protocol](reproduction/composition-scaling/README.md) |
| Curated completed-run evidence | No execution entry point; publication-safe aggregate record | [Five-model WildChat/EuroSAT execution audit](docs/real-data-training-hook-audit-2026-09-02.md) |
| Exact-ground-truth ceiling validation | `scripts/run_finite_channel_ceiling_experiment.py` | [Controlled configuration and retained result](reproduction/finite-channel-ceiling/README.md) |
| Public-data model-backed ceiling validation | `scripts/run_model_backed_finite_channel.py` | [Completed v2 result and retained artifacts](reproduction/model-backed-finite-channel/README.md) |
| OpenML, public-privacy, portfolio, and strategic studies | grouped runners in `scripts/` | [`reproduction/`](reproduction/) |

Exploratory tools emit bounded measurements, candidate attack floors, or screens—never authorization.
Their reports are not assessment evidence. A separately isolated approved worker must emit the exact
typed, content-addressed attack-battery output required by policy; the trusted core then recomputes its
positive controls and translates eligible results. Generated research reports, models, audit databases, and benchmark
output may use ignored `output/` paths. Governance records must instead be copied transactionally to
adopter-owned immutable storage with retention, legal-hold, backup, restore, access, and destruction
rules.

`finite_channel_ceiling` does not promote an exploratory report after the fact. For a bound
exact-guess risk \(\theta\), decision-bearing use requires a simultaneous construction that truly
establishes \(\Pr(\theta\le U)\ge 1-\alpha\) over the complete registered selection family. The
active `PolicyRule` and submitted `ThreatContract` must carry the same
[`FiniteDecisionGame`](schemas/finite-decision-game-v1.json): ordered secret-state semantics and an
exact rational prior fixed before assessment. The analytic problem and typed
[`FiniteStatePriorEvidence`](schemas/finite-state-prior-evidence-v1.json) must match that game. The
rational vector in the policy-frozen game is authoritative inside the protocol. The analytic problem
must repeat it in `rational_prior`; exact replay, threshold decisions, and the
`MRA-FINITE-PRIOR-2` digest use that rational vector. The legacy float-valued `prior` is only a
solver/display projection and must approximate each authoritative entry within (10^{-12}); it
cannot redefine the prior or drive an exact decision. The typed prior-evidence source must equal the
rational vector exactly. The named authority and the substantive legitimacy of its prior remain
external governance questions. For the reference statistical path, the core regenerates the typed marginals from retained plan, count,
and error-budget sources and mechanically proves every serialized Clopper--Pearson endpoint's
defining binomial-tail inequality with directed arithmetic before exact-rational certificate replay.
Endpoints and allocated alpha are interpreted by their canonical JSON decimal values, matching the
downstream rational semantics rather than a host-only binary64 fraction. Endpoint eligibility comes
from compiler-generated evidence and `endpoint_validation=validated`, never a submitter-set validity
flag. The plan, counts, committed error-budget allocation, and compiled evidence must all carry the same public
[`EvidenceBindingContext`](schemas/evidence-binding-context-v1.json), exactly matching the assessment
release, policy, artifact, interface, population snapshot, and decision game; sampling must end no
later than the assessment evidence's `observed_at`.
The reference implementation accepts at most 10,000 simultaneous cells and 10,000,000 trials in any
state row. Directed-tail replay is separately capped at 2,000,000 terms for one endpoint and
2,000,000 terms across the complete submitted family. These are cumulative fail-closed limits, not
sample-size recommendations: a row can satisfy the trial cap and still exceed a proof-term cap.
Statistical `state_trials` are replayed from the capped raw rows and cannot override them.
It still does not authenticate the named prior/mechanism authorities, prove the IID sampling claim,
or inspect the live endpoint. For an otherwise
eligible interval, its ceiling is eligible to clear only when \(U\le\tau\), its validated
fixed-decoder floor blocks when \(L>\tau\), and a straddling interval is fail-closed inconclusive with
`recollect_more_state_conditioned_samples`. Other policy gates can still keep a below-tolerance
ceiling inconclusive. If the released transcript or interface is incomplete, continuous without an
enforced finite encoding, or adaptive outside the frozen protocol, the required disposition is
`redesign_interface`; the analyzer emits a non-authorizing screen rather than a decision-bearing
ceiling. Omitting the game from both policy and threat, or disagreeing with its analytic state/prior,
requires `register_policy_bound_finite_game` and recollection; changing the policy copy only in the
request fails policy validation. Existing LLM, vision, training-hook, composition-scaling, and
red-team reports remain screens; they require approved state-conditioned recollection under this
contract. The construction is neutral to model
architecture—for example XGBoost, other trees, CNNs, and LLMs—but
not to evidence quality or interface completeness.

The LLM and vision matrices use real public-source records rather than
synthetic training fixtures. Their completed baseline runs exercise ingestion,
model execution, hook coverage, telemetry replay, and report publication. The
separate composition-scaling design adds three nested real-data scales, five
registered seeds, same-population output composition, matched vision hook and
batch controls, and all 31 non-empty five-model portfolio subsets. It does not
pool incompatible LLM and vision measurements into a scalar, and a committed
configuration or queued run is not a completed result. None of these studies
creates statistical proof of safety, privacy, robustness, fairness,
generalization, production capacity, or release eligibility.

### What the ceiling experiments establish

The [publication summary](reproduction/ceiling-experiment-summary.json) and
[paper-ready tables](paper/ceiling-experiment-results.md) keep soundness and
decision usefulness separate. On exact controlled channels, 1,200 primary
analyzer replays observed no ceiling undercoverage and produced the registered
`CLEAR`, `HOLD`, and `BLOCK` decisions in all 400 repetitions per role; the
simultaneous undercoverage upper bound was `0.015606`. This is empirical
calibration for the frozen finite-channel family, not a universal proof.

The completed public-data v2 study also observed zero undercoverage in 1,200
repeated analyzer replays, but it met only eight of nine registered acceptance
criteria. The raw compact-Transformer proxy channel cleared in 109 of 200
repetitions, giving a simultaneous clear-rate lower bound of `0.449431`, below
the registered `0.95` target. The other five model/interface families met that
target. This preserved negative result shows why coverage alone does not make a
ceiling decision-useful.

Both studies used experimental attack-battery waivers and issued no release
authorization. In v2, counts were drawn by the aggregate sampler while the
zero-input wrapper surface was checked separately; the run therefore does not
demonstrate end-to-end traffic through an enforcing wrapper. Its CNN/MNIST,
XGBoost/Adult, and compact-Transformer/20-Newsgroups observations are
conditional on one artifact per family, 400 `IN`/400 `OUT` records for CNN and
XGBoost and 350/350 for the proxy, repeated sampling from those pools, and the
registered categorical abstraction. The
Transformer is an LLM proxy, not an interactive LLM.

## Repository map

```text
src/model_release_assurance/   Installable reference implementation and CLI
schemas/                       Versioned public machine contracts
formal/                        Abstract protocol specification and Lean proofs
examples/                      Small supported CLI examples
tests/                         Core, integration, and experimental verification
scripts/                       Developer and study entry points; not public CLI
reproduction/                  Study inputs, registrations, manifests, and selected aggregate results
paper/                         MLSys draft outline, evidence map, and reproducibility gates
docs/                          Product, protocol, operational, and research guidance
output/                        Generated local artifacts; ignored by Git
```

The paths stay intentionally stable because scripts, tests, documentation, and retained manifests cross-reference them. Their ownership and maturity are defined in the [project scope](docs/project-scope.md), [documentation index](docs/README.md), [script catalog](scripts/README.md), and [reproduction index](reproduction/README.md).

## Core safety invariants

- Attack floors can block but never clear a threat.
- Exact floors aggregate by maximum. Each generic `attack`, `controlled_inference`, or `llm_canary`
  floor family must use a typed, policy-allowlisted
  [`StatisticalFloorFamilyPlan 1.0`](schemas/statistical-floor-family-plan-v1.json), frozen before
  observation, with a unique and exactly complete member roster, one decision metric, supported
  Bonferroni multiplicity, and at least 95% familywise confidence. Every accepted generic family
  configuration must be submitted and its `AnalyzerRequirement` must be required, preventing
  policy-approved families from being cherry-picked after results are known. Each planned member
  references a hash-verified
  [`StatisticalFloorDesignRegistration 1.0`](schemas/statistical-floor-design-registration-v1.json)
  plus an outcome-free input-design digest. These bind population, dataset snapshot, procedure,
  seed, stopping rule, planned
  primary/control trials, and any required low-FPR target or canary sealed assignment. The engine
  rejects an omitted, duplicated, substituted, unregistered, or design-changed member. Content hashes
  do not authenticate the registration source or prove that collection followed the declared design.
  Within any recognized complete family—including the separately typed attack-battery and
  finite-channel families—the core uses the maximum of its
  already familywise-adjusted member floors. Across distinct families it conservatively uses the
  minimum of those maxima, then takes the maximum with the exact-floor maximum. If another family
  would cross either tolerance or the clearing ceiling while that conservative aggregate would not,
  the decision is a fail-closed `resolve_statistical_multiplicity` hold. A stronger cross-family
  statistical block requires one shared preregistered error ledger.
- Exact evidence may clear directly. Ceiling-based clearance additionally requires a complete policy-mandated attack battery with passing positive controls, unless the signed policy records an explicit waiver; a policy may also prohibit ceiling clearance.
- A finite-channel confidence interval may contribute both a blocking floor and a clearing ceiling,
  but only for the canonical exact-guess game after complete released-interface, finite-alphabet,
  recipient-realizability, nested-source, selection-valid simultaneous multinomial, approved
  engine-replayed confidence-endpoint validation, full statistical-source context binding, and
  rational outward-replay checks. Deterministic point
  tables remain screens with `collect_simultaneous_channel_evidence` because their channel derivation
  is not machine-replayed.
- Evidence is bound to the release contract, policy, artifact, interface, population, decision game, and observation time before analysis.
- Evidence records identify the analyzer service/version and implementation/configuration digests; policy pins the minimum and accepted producer set.
- Attack-battery evidence separately identifies the battery orchestrator and each catalogued run/control executor; these digest bindings provide integrity, not workload authentication or truth.
- Every retained evidence record is dispositioned by identifier as included or excluded, and the active policy allowlists the exact selection-policy digest.
- Evaluated-to-released transfer requires reassessment or a verified information-reduction argument in the safe direction.
- Utility is enforced before selecting a least-informative feasible release.
- Portfolio dependence must be measured, composed, or conservatively bounded.
- Assessment `clear` is explicitly scoped to one release and the submitter-declared interface; it is non-authorizing. Offline selection binds a declared snapshot; production authorization still requires an authenticated authoritative portfolio snapshot and a separate live gateway-conformance receipt.
- `unassessed` and `inconclusive` mandatory threats cannot produce an overall clearance.
- Every `ThreatDecision` carries a required machine-readable `resolution` with a code,
  `clear`/`block`/`hold` gate, actions, evidence identifiers, and missing obligations. Every
  inconclusive decision is a `hold` with at least one action; any indicative state-trial target is
  explicitly planning guidance, never decision evidence.
- A contradictory ceiling cannot weaken an independently established blocking floor; contradiction is recorded separately from missing evidence.
- Signatures establish integrity and provenance; they do not establish that submitted evidence is true.
- Reports and verification outputs carry source/component/runtime profiles for replay attribution; those self-reported digests are not trusted-build attestations.

See the [architecture](docs/architecture.md), [mathematical foundations](docs/mathematical-foundations.md), [threat model](docs/reference/threat-model.md), and [formal verification scope](docs/formal-verification.md) for the detailed claims and non-claims.

## Development and verification

Install the locked core runtime and the range-based experiment compatibility
band before running the complete Python suite:

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
