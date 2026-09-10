# Model Release Assurance

[![CI](https://github.com/elmontu/AI_ModeL_Check/actions/workflows/ci.yml/badge.svg)](https://github.com/elmontu/AI_ModeL_Check/actions/workflows/ci.yml)

MRA is an **offline, non-authorizing reference implementation** of model-release
assurance. It validates versioned contracts, evaluates release-bound privacy
evidence, selects feasible configurations, signs records and replays MRAP/1.0
lifecycle transcripts. It does not deploy or serve models.

Status: alpha **0.8.0**. The implementation is sector-neutral and model-family
routing is advisory—not proof that every model, attack or live channel is covered.
The Lean proofs concern a scoped abstract protocol, not the Python or Ed25519
implementation.

## Two tracks, one shared core

| Track | Priority and purpose | Main entry point |
|---|---|---|
| **Academic** | **Current focus:** evidence-bound model governance for government bodies, with privacy as the worked technical assurance case | [Paper source](academic/paper/mra-paper.tex), [data companion](academic/paper/experimental-data.json) and [build instructions](reproduction/README.md#paper-draft) |
| **Industrial** | Deferred implementation work: turn the reference protocol into an independently enforced deployment system | [Industrial track and acceptance evidence](docs/system-audit-specification.md#industrial-track) |

These are workstreams, not separate implementations or conformance levels. Both
use the same versioned contracts, reference library and formal artifacts. No
source trees or schemas are duplicated, and no deployment obligation is waived.

## Academic track — start here

The academic workspace groups the [manuscript and retained companions](academic/paper/),
[paper assembly scripts](academic/scripts/) and [academic consistency tests](academic/tests/).
The shared implementation, schemas, Lean proofs and source studies remain in
`src/`, `schemas/`, `formal/` and `reproduction/`. Generated PDFs stay in
ignored `output/pdf/`; build instructions remain in the reproduction index.

The [full paper draft](academic/paper/mra-paper.tex), *Model Governance for Government
Bodies: An Evidence-Bound Release Assurance Protocol*, uses the IEEE Computer
Society conference format for an S&P-oriented research argument. Its object is
a government body's accountable decision to authorize model use, an update or
renewal—not privacy testing alone. Privacy is the worked technical case:
context-bound floor/ceiling evidence supports a scoped recommendation, but does
not establish the adequacy of every legal, rights, fairness or public-service
obligation.

The government profile binds accountable authority, purpose and impact review,
procurement and vendor limits, human oversight and redress, transparency records
with justified exemptions, monitoring and retirement. Required evidence and
approvals are checked when they become due in the lifecycle. A privacy RELEASE
is not institutional authorization; RELEASE-WITH-RISK cannot waive mandatory
rights or legal obligations. The profile is jurisdiction-neutral, not a claim
of compliance with a particular government's rules. It is a normative paper
profile, not an implemented government-policy checker.

Section 3 contains the full protocol and six main conditional guarantees.
Six appendix algorithms, detailed proofs, seven gap arguments and the proof
inventory retain the technical foundation. Primary finite-construction and
ceiling-study tables support the main findings. Detailed workload, timing and
supplementary tables are preserved in the appendices and companion rather than
treated as interchangeable support for the central theorem. The
[seven exact finite construction studies](academic/paper/gap-construction-results.json)
are separate from the historical trained-model experiments. Neither those data
nor the written arguments establish government field validation, agency approval,
or legal/fairness correctness. No new model experiments or verified Python
implementation are claimed. This is an
**extended research draft**, not a submission-length manuscript. The
[aggregate companion](academic/paper/experimental-data.json) contains 63 tables and
4,754 rows linked to 109 hashed sources; it is research data, not an MRAP
contract. [Build and evidence-access instructions](reproduction/README.md#paper-draft)
explain what can be reproduced from this checkout. Venue-style formatting does
not establish novelty, acceptance or submission readiness.

The paper asks three linked questions: under which conditions a government body
may authorize use, update or renewal; how privacy floor/ceiling evidence should
represent uncertainty within that decision; and which protocol components the
retained tree, image and language-model evidence validates while institutional
validation remains missing. Observation-relative impossibility results explain
scoped refusal, not impossibility under every stronger observation model.

Section 3 incorporates constructive admission rules and explicit refusal
boundaries: impossibility annotations cannot substitute for clearance, waive
required evidence or bypass mandatory gates. The draft supplies a
claim-to-proof map; its unproved premises remain open
research obligations. Develop and validate it in this order:

1. Fix the [protocol claim and assumptions](docs/model-release-assurance-protocol.md#academic-track): accountable decision authority, stage-specific obligations, and the worked privacy case's games, declared channels, simultaneous coverage and exact verdict meanings.
2. Connect the [mathematical arguments](docs/mathematical-foundations.md) and [four-verdict arguments](docs/gap-remediation.md#conditional-correctness-arguments) to the [actual Lean theorem boundary](docs/formal-verification.md). Unproved links remain labelled obligations.
3. Challenge those claims using the [counterexample regressions](docs/gap-remediation.md) and the [primary-source literature review](docs/literature-review.md); demonstrate what fails when each material assumption is removed.
4. Prospectively register and execute the [academic evaluation plan](reproduction/README.md#academic-plan), reporting current reference-pipeline correctness and scaling separately from historical measurements.

The candidate contribution connects public-body governance obligations, scoped
technical evidence and lifecycle decision invariants. Its novelty and publication readiness
are **not established** by organizing the repository. Abstract proofs, Python
tests and empirical measurements must remain separate evidence categories.

“Inclusiveness” means coverage of the declared scenario universe, not proof of
all possible attacks or models. Game theory stays supplemental; it cannot
replace a privacy bound or a governance obligation. A concrete database or
gateway is not required to state an ideal-model theorem, but its assumptions
must remain visible and deployment correctness remains unproved.

## Reference implementation quick start

Read the [implementation and motivation guide](docs/implementation-and-motivation-guide.md) for the purpose of each component, a complete walkthrough, model and adversary coverage, evidence interpretation and remaining work.

The [detailed local verification report](docs/framework-e2e-validation-2026-09-10.md) retains results for every supported training option and adversary, plus explicit coverage gaps.

For trusted local testers, the [browser console](docs/local-console.md) adds a
REST API, separate worker and persistent job queue. Run guided scenarios or the
real offline training demo, create release cases and inspect results. Start
with `python scripts/setup_pipeline.py --profile console`, then `mra-console
local`; Docker Compose is also provided. This is a local pre-POC, not a shared
production authorization service.

For a cross-platform installer, offline training demo and a case workflow for
trained, fine-tuned, adapter, merged, ensemble and distilled releases, start with
the [pipeline quickstart](docs/pipeline-quickstart.md). `mra-workflow` inventories
inputs and lineage, reports missing evidence and invokes the existing assessment
engine. It does not authorize releases or verify institutional approvals.

Python 3.11 or newer is required. From a virtual environment:

```bash
python -m pip install -e .
mra validate examples/request.json
mra assess examples/request.json \
  --output output/assessments/demo-report.json \
  --audit-db output/audit/mra.sqlite3
```

For configuration selection, install `.[portfolio]` and use
`mra optimize examples/optimization-request.json --output output/optimization.json
--audit-db output/audit/mra.sqlite3`. The [example catalog](examples/README.md)
explains the synthetic, hash-bound inputs.

For actual training followed by assessment:

```bash
python -m pip install -e '.[experiments]'
make demo DEMO_DATASET_PROFILE=sklearn-breast-cancer
```

The default `make demo` uses the public OpenML sick/thyroid dataset and may download
data. The [training demo guide](docs/guided-government-health-demo.md) describes
the workflow and its limitations. Its evidence cannot justify privacy clearance
or deployment. `make demo-reference` is the separate synthetic/mock workflow
rehearsal, not model training.

## Decisions and enforcement boundary

The decision-maker-facing assurance record contains each threat's exact
floor, ceiling, gap, threshold, evidence and scope. Its signed gate returns:

| Verdict | Meaning |
|---|---|
| RELEASE | Every threat has admissible evidence and a ceiling within threshold |
| RELEASE-WITH-RISK | No blocking condition; every crossing ceiling is explicitly accepted under permitted policy by a trusted signer |
| BLOCK | A demonstrated violation, missing required evidence, contradiction or failed integrity/validity check |
| INCONCLUSIVE | Protocol-defined actionable gap; reserved until an applicable resolving-plan verifier is implemented |

See [record, signing and gate commands](docs/gap-remediation.md#four-verdict-record-and-gate).
These are recommendations: the gate always sets `authorization_eligible=false`.
The lower-level assessment and optimizer retain their own scoped vocabularies.
The current outward gate blocks an unaccepted crossing: generic recollection
advice does not verify that suitable data and fresh error budget are available.
The optimizer requires all in-scope threats, including optional ones, to CLEAR
and requires a version 1.1 cumulative disclosure roster. Revoking service does
not remove a release from that roster. Optional risk-accepting optimization
remains unsupported. See the [September review revision](docs/gap-remediation.md#september-9-2026-review-revision).

A failed attack is not an upper bound on privacy risk. Signatures establish byte
and key binding, not truthful collection. Complete live interfaces, independent
worker attestation, authoritative portfolio state, atomic commit, gateway
enforcement, monitoring and revocation remain external obligations.

## Documentation

Use these shared references. The academic reading order above is the default;
industrial requirements remain in the integrated system specification.

| Question | Reference |
|---|---|
| What is the lifecycle protocol? | [MRAP/1.0](docs/model-release-assurance-protocol.md) |
| What does the implementation enforce, and what remains external? | [System architecture and audit specification](docs/system-audit-specification.md) |
| What changed in 0.8.0, and which gaps remain? | [Remediation and migration guide](docs/gap-remediation.md) |
| What are the mathematical arguments and assumptions? | [Mathematical foundations](docs/mathematical-foundations.md) |
| What has actually been machine-checked? | [Formal verification scope](docs/formal-verification.md) |
| What does the research support? | [Consolidated literature review](docs/literature-review.md) |
| Which contracts are current? | [37-schema registry](schemas/README.md) |

Focused guides: [XGBoost](docs/xgboost.md),
[LLM watermark/canary](docs/llm-watermark-canary.md),
[model-family coverage](docs/model-family-coverage.md),
[red-team tools](docs/sacro-ml-red-team.md), and [MCP/RAG](docs/rag-mcp.md).

## Experiments and historical evidence

The [reproduction index](reproduction/README.md) is the single study inventory:
it distinguishes retained results, negative results, configured experiments and
templates. [Scripts](scripts/README.md) is the executable tool catalog.

Historical registrations and results retain their original source/runtime
bindings. They do not validate the revised implementation. Changed source hashes
must fail old registrations; new scalability claims require prospective
registration and fresh execution. Negative results and manifest-bound artifacts
are preserved, including the [generated ceiling report](academic/paper/ceiling-experiment-results.md).

## Development and support

```bash
python -m pip install -r requirements.lock
python -m pip install -r requirements-experiments.txt
make check
make verify  # also requires the pinned Lean toolchain
```

See [contribution and support guidance](CONTRIBUTING.md),
[test coverage](tests/README.md), [release process](docs/releasing.md) and
[change history](CHANGELOG.md). Python modules are not stable public APIs unless
explicitly documented.

Report vulnerabilities through [SECURITY.md](SECURITY.md), not public issues.
Do not upload confidential data, model artifacts or signing keys.
No public-use licence has been selected; repository visibility is not permission
to use, modify or redistribute the software.
