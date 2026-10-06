# Model Release Assurance

Model Release Assurance (MRA) helps government teams evaluate a model before
sharing it with another agency, a partner or the public. It brings together
public-data training, red-team checks, evidence review and controlled-delivery
exercises in a sector-neutral framework.

**Status: alpha 0.8.0.** Local workflows and public-fixture production controls
are implemented. An agency deployment still needs approved data and policies,
qualified infrastructure and independent acceptance. Reports and local reviews
do not authorize a release.

Start with the [government audit guide](docs/government-audit-guide.md).
The [production roadmap](docs/production-private-cloud-plan.md) explains the
path to an agency private-cloud service.

## Quick start

Use **Python 3.11 or newer**, and run these commands from a source checkout.
The installer creates a new environment with the console, training tools and
local API dependencies.

**Windows PowerShell**

```powershell
python scripts/setup_pipeline.py --profile console
& .\.venv-pipeline\Scripts\python.exe -m model_release_assurance.console local --data .local/console-data --port 8765
```

**Linux/macOS**

```bash
python3 scripts/setup_pipeline.py --profile console
./.venv-pipeline/bin/python -m model_release_assurance.console local --data .local/console-data --port 8765
```

Open [the local console](http://127.0.0.1:8765/). The launcher starts the API and
a separate worker; Ctrl+C stops both. The local services are intended for
trusted testers.

Setup requires package access or a prepared wheel directory supplied with
`--wheelhouse PATH`. The bundled training examples then run offline. Setup
refuses to overwrite an existing environment: reuse its Python executable or
choose a new location with `--venv PATH`.

### First review

1. Select a supported model and bundled public dataset in the training wizard,
   or create a case and bind the required files for an existing candidate.
2. Run preflight, training and adversarial checks. Review failures, unsupported
   tools and uncertainty alongside completed tests.
3. Open **Government audit review** and record evidence, rationale and gaps
   against its twelve controls.
4. Download the case evidence and review record. Changing a binding or cited
   file makes affected review entries stale.

Education mode supports trusted local exercises with optional institutional
documents. Scientific and evidence-integrity checks still apply. See the
[console guide](docs/local-console.md) and
[pipeline quickstart](docs/pipeline-quickstart.md) for the full workflow.

## What is implemented

| Workflow | Current capability | Scope |
| --- | --- | --- |
| Training and case review | Ten CPU training presets, four bundled datasets, lineage records, adversarial jobs and a twelve-control review | Supported model/data pairs; local operator review |
| Assessment | Versioned contracts, scoped evidence, optimization, signed records and lifecycle replay | Non-authorizing recommendations |
| Export screening | Reloaded public model packages, a frozen membership screen, positive/null controls and reviewer receipts | Declared attacks and exact candidate bytes |
| Synthetic export lab | Public synthetic training, accounting exercises, atomic commitment and exact-byte delivery | Fixed fixtures |
| Temporal release workflow | Required screening, policy review, atomic charge/receipt commitment and current delivery checks | Separately verified study and initialized operator registry |
| Production engineering | Local identity, storage, trust, jobs, evidence, registration, review, delivery, monitoring, recovery and pilot-planning controls | Public fixtures; agency deployment qualification pending |

Review contexts include original models, fine-tuning, adapters, merges,
ensembles and distillation. A registered case type does not imply a trainer,
attack adapter or privacy guarantee for every model family. Console models are
not automatically admitted to a temporal or production registry.

### Red-team coverage

| Area | Available now | Limit |
| --- | --- | --- |
| Tabular classification | Membership checks and exploratory attack groups | Coverage depends on the supported model and declared interface |
| Regression | Membership, extraction and robustness screens | Scoped diagnostic evidence |
| Local language models | Nine synthetic probes and two controls through an installed Ollama model | No model download, real tool execution or general training-record extraction claim |
| Public export pilot | One loss-based membership screen on an offline GaussianNB package | One public fixture |
| SACRO-ML | Separate pinned 2.0.1 adapter for seven public classifier profiles | Separate runtime; Diabetes regression unsupported; not a console integration |
| ART | Separate pinned 1.20.1 retained-loss membership comparison across eight public profiles | Includes continuous regression; trusted loss oracle; no live target-query or console integration |
| garak | Separate pinned 0.17.0 prompt-injection component on one local Ollama model | Four templates, three synthetic wrappers; literal scoring; no live retrieval, tools or console integration |
| PyRIT | Separate pinned 1.1.0 multi-turn component with scripted attacker and local Ollama target | Two public synthetic objectives, three-turn limit and literal scorer; adaptive attacker and live RAG/tools remain pending |

Discovery lists available and unsupported tools; it does not establish that every dependency is installed.
See [tool coverage](docs/framework-capability-gaps.md),
[export screening](docs/red-team-export-review.md),
[scoped SACRO-ML](docs/production-prd14-sacro-adapter.md),
[ART retained-loss comparison](docs/production-prd25-art-adapter.md) and
[scoped garak](docs/production-prd26-garak-adapter.md) and
[PyRIT multi-turn orchestration](docs/production-prd26-pyrit-adapter.md).

Run the public export-screening example from the console environment:

```powershell
& .\.venv-pipeline\Scripts\python.exe -m model_release_assurance.export_red_team demo --output .local/red-team-pilot-v1
```

On Linux/macOS use `./.venv-pipeline/bin/python`. Choose a new output directory;
existing results are never overwritten. Failed attacks do not establish an
upper bound on privacy risk, and successful controls do not clear a model.

## Export and delivery exercises

Start the [synthetic export lab](docs/model-export-poc.md) in a second terminal:

```powershell
& .\.venv-pipeline\Scripts\python.exe -m model_release_assurance.export_poc serve --data .local/model-export-poc --port 8767
```

Open [the synthetic exercise](http://127.0.0.1:8767/synthetic). It compares
identical-model reuse, retained-state extension, independent randomized response
and a central-DP count baseline.

The root page hosts the separate
[enforced release workflow](docs/enforced-release-workflow.md). Temporal views
require an existing verified study and initialized operator registry:

```powershell
& .\.venv-pipeline\Scripts\python.exe -m model_release_assurance.export_poc serve --data .local/model-export-poc --repository "PATH_TO_RETAINED_RESEARCH_WORKSPACE" --temporal-run "PATH_TO_VERIFIED_RUN" --temporal-operator "PATH_TO_INITIALIZED_OPERATOR" --port 8767
```

Replace the placeholders with existing directories. The supplied research
workspace must contain the retained ACS temporal verification receipts; those
full study/model stores are not bundled in this government repository.
Missing inputs leave temporal views unavailable. The launcher does not create
a registry or restore privacy budget. See the
[temporal service guide](docs/temporal-release-assurance.md).

For command-line contract validation and assessment, use the installed
`mra` command. The [example catalog](examples/README.md) and
[implementation guide](docs/implementation-and-motivation-guide.md) explain
the required inputs, assessment commands and interpretation.

## Production roadmap

The target is an **agency private-cloud service** for government model assurance
over large private datasets. Provider and region remain open. The framework
supports broader government sectors; a major public-health agency is one
possible pilot.

PRD-01 through PRD-26 have reviewable local work. Each retains its own acceptance
gates and remains in progress for production qualification.

| Workstream | Local progress | Detailed records |
| --- | --- | --- |
| Scope and platform | Scope, threat model, source/build baseline, required CI and infrastructure blueprint | [PRD-01](docs/production-prd01-scope-and-ownership.md), [PRD-02](docs/production-prd02-threat-model.md), [PRD-03](docs/production-prd03-source-build-baseline.md), [PRD-04](docs/production-prd04-required-ci.md), [PRD-05](docs/production-prd05-infrastructure-scaffold.md) |
| Identity and operations | Scoped credentials, governed object references, key trust, build controls and durable jobs | [PRD-06](docs/production-prd06-identity-and-approvals.md), [PRD-07](docs/production-prd07-governed-storage.md), [PRD-08](docs/production-prd08-key-trust.md), [PRD-09](docs/production-prd09-build-controls.md), [PRD-10](docs/production-prd10-durable-jobs.md) |
| Models and evidence | Broader public benchmarks, authenticated replay, prospective registration and the separate SACRO-ML adapter | [PRD-11](docs/production-prd11-adapter-benchmarks.md), [PRD-12](docs/production-prd12-authenticated-evidence.md), [PRD-13](docs/production-prd13-model-registration.md), [PRD-14](docs/production-prd14-sacro-adapter.md) |
| Review and delivery | Fictional ledger charges, witness/recovery records, policy review and controlled public-fixture delivery | [PRD-15](docs/production-prd15-registry-transactions.md), [PRD-16](docs/production-prd16-witness-recovery.md), [PRD-17](docs/production-prd17-policy-review.md), [PRD-18](docs/production-prd18-controlled-delivery.md) |
| Assessment and pilot planning | End-to-end public profile, monitoring, capacity/recovery exercises, assessment packets and scoped pilot plans | [PRD-19](docs/production-prd19-end-to-end-profile.md), [PRD-20](docs/production-prd20-monitoring-incidents.md), [PRD-21](docs/production-prd21-capacity-recovery.md), [PRD-22](docs/production-prd22-independent-assessment.md), [PRD-23](docs/production-prd23-restricted-pilot.md) |

Public benchmarks include bundled datasets and prepared ACS, aviation, lending
and taxi samples. Catalog registration does not mean every dataset is available
or tested. Private agency data is not admitted by these rehearsals.

**Current: [PRD-26, scoped PyRIT multi-turn adapter](docs/production-prd26-pyrit-adapter.md).**
The real upstream attack loop, in-memory conversation store and literal scorer
execute two synthetic objectives with a scripted attacker and one local model.
Separate role identities, bounded turns, positive/null controls and independent
conversation replay are mandatory. The earlier [garak component](docs/production-prd26-garak-adapter.md)
remains a separate prompt-injection fixture. These local adapters grant no
agency acceptance or release authority.

Remaining PRD-26 acceptance includes adaptive attackers, semantic/human review,
approved agency endpoints, live interfaces and verified worker isolation.

Production acceptance still requires agency appointments and release criteria,
real identity/key services, isolated workers and networks, independent custody,
private-cohort and scientific validation, a justified privacy accountant,
agency-scale recovery tests and operational ownership. Hosted CI, protected
release settings and licensing/ownership also remain pending.

No deployment obligation is waived. Use the
[industrial acceptance requirements](docs/system-audit-specification.md#industrial-track)
and the [full roadmap](docs/production-private-cloud-plan.md) to assess readiness.

## How to interpret results

Findings apply to the recorded candidate, population, interface, policy and
evidence. The signed decision record can recommend `RELEASE`,
`RELEASE-WITH-RISK`, `BLOCK` or `INCONCLUSIVE`; its gate always sets
`authorization_eligible=false`. See the
[decision and gate guide](docs/gap-remediation.md#four-verdict-record-and-gate).

A signature binds bytes to a key; it does not establish truthful collection or
independent agency custody. An attack measures its declared access and sample;
it does not prove whole-record privacy. Revoking service does not erase prior
disclosure. The Lean proofs cover a scoped abstract protocol; the Python and
Ed25519 implementation are outside that proof boundary.

## Verification and development

Use the console environment and install the hash-pinned build-verifier
dependency before running the required government profile:

```powershell
& .\.venv-pipeline\Scripts\python.exe -m pip install --require-hashes --only-binary=:all: --no-deps -r deploy/build/verification-runtime.requirements.txt
& .\.venv-pipeline\Scripts\python.exe -B scripts/run_required_tests.py --profile government --output .local/verification/government-v1
& .\.venv-pipeline\Scripts\python.exe -B scripts/generate_schema_manifest.py --check
& .\.venv-pipeline\Scripts\python.exe -B scripts/check_markdown_links.py
```

On Linux/macOS substitute `./.venv-pipeline/bin/python`. Use a new output path
for each required-profile run. The runner rejects missing suites, test failures
and skips, and retains a log, source hashes and a JSON receipt.

For the broader maintainer checks, activate the console environment and use
`make PYTHON=python check` or `make PYTHON=python verify` with Make available.
`verify` also requires the pinned Lean toolchain.
See [required CI](docs/production-prd04-required-ci.md),
[build controls](docs/production-prd09-build-controls.md) and
[test coverage](tests/README.md) for the full prerequisites.

The PyRIT milestone passed **2,345 required tests across 127 modules with zero
failures, errors or skips**, with all 502 recorded source hashes still matching.
Checks verified 37 schemas and links in 75 Markdown files. Source and
installed-wheel PyRIT runs each completed six upstream campaigns, four real-model
turns and all controls and independent conversation/score replay. Each retained
two literal public-marker emissions; human/semantic review remains pending.
Actual upstream transport and truncation fixtures retained incomplete evidence
and undetermined scores. The [PyRIT record](docs/production-prd26-pyrit-adapter.md)
documents the partial runtime, D: storage hook and remaining agency acceptance.
Earlier [garak](docs/production-prd26-garak-adapter.md) and
[ART](docs/production-prd25-art-adapter.md) validation remain source-bound.
Hosted CI remains outside this phase at the user's request; the
[publication checkpoint](docs/government-academic-separation-plan-2026-10-01.md#government-publication-checkpoint)
retains earlier publication evidence.

## Documentation and research

| Need | Reference |
| --- | --- |
| Government review walkthrough | [Government audit guide](docs/government-audit-guide.md) |
| Lifecycle contracts and enforcement | [Release protocol](docs/model-release-assurance-protocol.md), [system audit specification](docs/system-audit-specification.md) |
| Supported model families and tools | [Model-family coverage](docs/model-family-coverage.md), [red-team tools](docs/sacro-ml-red-team.md), [MCP/RAG](docs/rag-mcp.md) |
| Current data contracts | [37-schema registry](schemas/README.md) |
| Mathematical and proof assumptions | [Mathematical foundations](docs/mathematical-foundations.md), [formal verification scope](docs/formal-verification.md) |
| Historical observations and executable tools | [Reproduction index](reproduction/README.md), [script catalog](scripts/README.md) |
| Contributions and releases | [Contribution guide](CONTRIBUTING.md), [release process](docs/releasing.md), [change history](CHANGELOG.md) |

The [1 October technical advisory](docs/advisory/technical-report-2026-10-01.md)
and [displayed-table digest](docs/advisory/displayed-tables-2026-10-01.md)
retain source-linked research observations, including adverse and incomplete
results. The dated 28 September archive was
[retired from this checkout](docs/government-academic-separation-plan-2026-10-01.md#retired-28-september-archive)
at the user's request and remains recoverable in Git history.

The [separate academic repository](https://github.com/elmontu/AI_Model_Academic)
has a curated local checkout at commit
`826b5e5fbda2cd50e6bb856a90be1b18619afc11`; its public GitHub publication is pending
in the project plan. Full raw study archives remain local. Research observations
and dated receipts retain their original source/runtime bindings.
The [fine-grained execution plan](docs/government-academic-separation-plan-2026-10-01.md)
tracks publication, evidence gaps and remaining work.

## Support and licensing

Use [SECURITY.md](SECURITY.md) for vulnerability reporting. Keep confidential
data, model artifacts and signing keys out of public issues and submissions.

No public-use licence has been selected. Repository visibility does not grant
permission to use, modify or redistribute the software. Python modules are not
stable public APIs unless explicitly documented.
