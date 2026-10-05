# Model Release Assurance

[![CI](https://github.com/elmontu/AI_ModeL_Check/actions/workflows/ci.yml/badge.svg)](https://github.com/elmontu/AI_ModeL_Check/actions/workflows/ci.yml)

MRA is a **local government model-release audit framework** for trusted testers.
Use its browser console to train examples on bundled public data, run adversarial
checks, assess bound evidence and record an agency's review questions before
releasing a model to another party or the public. It covers original, fine-tuned
and combined-model review contexts. Its recommendations and review records do
not authorize agency releases.

Status: alpha **0.8.0**. The implementation is sector-neutral and model-family
routing is advisory—not proof that every model, attack or live channel is covered.
The Lean proofs concern a scoped abstract protocol, not the Python or Ed25519
implementation.

The [1 October technical advisory](docs/advisory/technical-report-2026-10-01.md)
interprets historical experiments alongside later research and adverse findings.
Its [later displayed-table digest](docs/advisory/displayed-tables-2026-10-01.md)
and [fine-grained gap plan](docs/government-academic-separation-plan-2026-10-01.md)
show the newer curated evidence and work still needed.

The dated 28 September advisory archive has been
[removed from this checkout](docs/government-academic-separation-plan-2026-10-01.md#retired-28-september-archive)
at the user's request. Its files and verifier remain in Git history. The
[local verification receipt](docs/advisory/local-verification-2026-10-01.md)
records checks performed before that retirement; it does not describe the
current file inventory.

## Start the government audit console

Python 3.11 or newer is required. From a source checkout, create the console
environment and start the API and separate worker. No activation is required.

Windows PowerShell:

```powershell
python scripts/setup_pipeline.py --profile console
& .\.venv-pipeline\Scripts\python.exe -m model_release_assurance.console local --data .local/console-data --port 8765
```

Linux/macOS:

```bash
python3 scripts/setup_pipeline.py --profile console
./.venv-pipeline/bin/python -m model_release_assurance.console local --data .local/console-data --port 8765
```

Open [the local console](http://127.0.0.1:8765/). Keep the launcher running;
Ctrl+C stops both services. The installer refuses to overwrite an existing
environment: use that environment's Python or select a new `--venv PATH`.
Installation needs package access or a prepared `--wheelhouse`; the bundled
training examples then run offline.

1. Use the training wizard with a supported model and public sample dataset,
   or create a case for an existing candidate and bind its required files.
2. Run preflight, training/adversarial jobs and assessment as appropriate.
   Inspect failures, unsupported tools and uncertainty alongside completed tests.
3. Open **Government audit review** for the selected case. Record rationale,
   bound evidence and gaps against its twelve controls.
4. Download the review and case evidence. Rebinding a case or changing cited
   bytes makes affected review entries stale and requires a fresh review.

Start with the [government audit guide](docs/government-audit-guide.md) for the
full walkthrough, control inventory and required evidence. Education mode keeps
institutional documents optional for trusted local exercises. It preserves
scientific and evidence-integrity checks; a recorded checklist is not a
scientific pass or agency approval.

## Implemented workflows

| Workflow | Implemented behavior | Boundary |
|---|---|---|
| Public-data training and red teaming | Ten CPU training presets, four bundled datasets, classifier/regression tools and optional local language-model probes | Only supported model/data pairs and declared attacks run; failed attacks cannot establish a privacy ceiling |
| Government case review | Twelve controls, evidence references and hashes, retained rationale/history, stale-evidence findings and JSON download | Records a trusted local operator's review; does not judge scientific adequacy or authenticate agency approvers |
| Assessment core | Versioned contracts, scoped privacy evidence, optimization, signing and lifecycle replay | Produces non-authorizing recommendations |
| Synthetic export lab | Bounded protected-data training, accounting, atomic commitment and exact-byte delivery | Fixed public synthetic fixtures; no arbitrary citizen-data uploads |
| Temporal release service | Required red-team report screening, prepare/check/review, atomic charge/receipt commit and current delivery checks | Requires an operator-approved policy and a separately initialized registry; does not import console models automatically |
| Public red-team export pilot | Offline GaussianNB package, exact-byte reload, loss membership attack, known-leak/null controls and a reviewer receipt | One public fixture; an operational screen cannot establish privacy or authorize a release |

Review covers recipient access, prior exports, preprocessing, parent models,
fine-tuning, adapters, merges, ensembles and distillation. A case type does not
imply an implemented trainer or privacy proof for every model family.

## Optional export and controlled-delivery exercises

The [synthetic export lab](docs/model-export-poc.md) runs with the same console
environment in a second terminal:

```powershell
& .\.venv-pipeline\Scripts\python.exe -m model_release_assurance.export_poc serve --data .local/model-export-poc --port 8767
```

On Linux/macOS substitute `./.venv-pipeline/bin/python` for the executable.
Open [the synthetic exercise](http://127.0.0.1:8767/synthetic). It separates
identical-model reuse, retained-state extension, independent randomized response
and a central-DP count baseline. `mra export` also supplies operator commands;
read-only MCP tools expose construction discovery, bundle inspection, history
verification and planning.

The root page at port 8767 hosts the separate
[enforced release workflow](docs/enforced-release-workflow.md). To use an existing
verified temporal study and initialized operator registry, explicitly select
their locations:

```powershell
& .\.venv-pipeline\Scripts\python.exe -m model_release_assurance.export_poc serve --data .local/model-export-poc --repository "PATH_TO_RETAINED_RESEARCH_WORKSPACE" --temporal-run "PATH_TO_VERIFIED_RUN" --temporal-operator "PATH_TO_INITIALIZED_OPERATOR" --port 8767
```

Replace the placeholder paths with existing directories. The repository path
must contain the retained ACS temporal verification receipts; this government
checkout and the curated academic checkout do not contain that full research
workspace. Without those study/model stores, temporal views are
unavailable and the launcher explains the missing inputs; the synthetic lab
still works. It does not silently create a registry or restore privacy budget.
The [temporal service guide](docs/temporal-release-assurance.md) explains its
channel/unit accounting and trusted-storage assumptions.

## Run the public red-team export pilot

From the console environment, run one bundled public-data example offline:

```powershell
& .\.venv-pipeline\Scripts\python.exe -m model_release_assurance.export_red_team demo --output .local/red-team-pilot-v1
```

Choose a new output directory; existing results are never overwritten. The
[red-team export guide](docs/red-team-export-review.md) explains the package,
report, controls, evaluator, tool discovery and required temporal-service policy.
The pilot does not create a private-data registry or privacy budget. Existing
operator inventories must supply a policy to use the new required screening gate;
older teaching fixtures can explicitly select the labelled legacy mode.

## Production planning

The [agency private-cloud production plan](docs/production-private-cloud-plan.md)
defines the architecture, 27 implementation tasks, responsible roles, acceptance
gates, recovery requirements and staged rollout. It builds on the local red-team
milestone; production identity, protected custody, isolated workers and
authoritative release services still need implementation and independent
acceptance. The framework now targets broader government uses and public research
benchmarks; a major public-health agency remains one proposed pilot. Each real
agency deployment still needs an approved tabular release profile and data scope.
[PRD-01 scope and ownership](docs/production-prd01-scope-and-ownership.md) is in
progress; the exact agency, programme, data and accountable owners remain pending.
[PRD-02 threat model and cloud decisions](docs/production-prd02-threat-model.md)
is drafted for review; provider and region remain open at the user's request.
[PRD-03 source/build baseline](docs/production-prd03-source-build-baseline.md)
captures the current working tree and verifies repeat local wheel builds;
publication, licensing/ownership and protected release settings remain pending.
[PRD-04 required CI profile](docs/production-prd04-required-ci.md) adds explicit
red-team/temporal coverage, refuses required-test skips and gates packaging on
Windows/Ubuntu checks; remote execution remains pending authentication.
[PRD-05 infrastructure preparation](docs/production-prd05-infrastructure-scaffold.md)
adds a validated provider-neutral blueprint and a local API/worker lifecycle
rehearsal with public fixtures. Cloud deployment and isolation remain unverified;
provider/region decisions and agency approvals are still open.
[PRD-06 identity and approvals](docs/production-prd06-identity-and-approvals.md)
adds pinned access-token verification, current case permissions and distinct
assessor/approver checks in an isolated public fixture. Live agency SSO/MFA,
durable authority state and protection of production routes remain pending.
[PRD-07 governed storage](docs/production-prd07-governed-storage.md) adds immutable
public-fixture object/snapshot references, exact single-use workload read grants,
and retention/hold decisions. Private intake, cloud storage custody and
large-data access remain pending qualification.
[PRD-08 key trust](docs/production-prd08-key-trust.md) adds a provider-interface
signing fixture and a current trust registry for access-token enrollment,
rotation and revocation. Saved reviews and storage grants consult current trust;
agency KMS/HSM custody and other signing/encryption purposes remain pending.
[PRD-09 build controls](docs/production-prd09-build-controls.md) adds exact wheel
locks, SBOM/license inventory, current dependency-advisory checks and a signed
local provenance fixture. License approval, production images, protected builders
and deployed admission remain pending.
[PRD-10 durable jobs](docs/production-prd10-durable-jobs.md) adds SQLite job/lease
state, permanent one-use input reservations and a fixed public worker with
timeout, cancellation and descendant cleanup. Durable agency authority and
private-cloud isolation remain pending.
[PRD-11 broader adapter benchmarks](docs/production-prd11-adapter-benchmarks.md)
adds typed numeric classification/regression packages and independent replay,
with read-only tests of available ACS, aviation, lending and taxi research
samples on D:. Healthcare is one example use case; dataset support is sector-neutral.
Missing research corpora and untested registered inputs remain explicit.
[PRD-12 authenticated evidence](docs/production-prd12-authenticated-evidence.md)
adds purpose-bound signatures, exact replay and durable one-use challenges.
Production admission rejects unavailable image/isolation evidence; the local
fixture cannot authorize a model release.
[PRD-13 model registration](docs/production-prd13-model-registration.md) adds
registration before fitting for eight pinned public profiles, exact source/sample
lineage, explicit population and non-DP limits, a frozen utility comparison and
local disclosure history. Arbitrary model import is refused; external disclosure
history remains unknown. PRD-13 remains in progress for agency and scientific
qualification, and no candidate receives clearance.
[PRD-14 SACRO-ML adapter](docs/production-prd14-sacro-adapter.md) uses the pinned
external probability-membership attack in a separate runtime, with fixed controls
and independent score/count replay. Seven public classifiers are applicable;
Diabetes regression remains explicitly unsupported. Production qualification
stays in progress, and no attack result clears a model.
[PRD-15 registry transactions](docs/production-prd15-registry-transactions.md) adds
atomic fictional charges, guarded heads, immutable receipts and a durable outbox,
with explicit migration, process-crash and retry tests. Real privacy accounting,
PostgreSQL failover and agency qualification remain pending.
[PRD-16 witness recovery](docs/production-prd16-witness-recovery.md) adds separate
retained intents/history and externally pinned checkpoint floors, with rollback,
uncertain-commit and recovery checks. Independent agency custody and authenticated
remote witness services remain pending.
[PRD-17 policy review](docs/production-prd17-policy-review.md) binds signed policy
approval before prospective training, exact retained candidate/replay evidence,
independent reviewers and scoped delegation with durable history. Agency
authority and scientific qualification remain pending.
[PRD-18 controlled delivery](docs/production-prd18-controlled-delivery.md) adds
current human-recipient grants, per-chunk admissions, exact public-fixture bytes,
suspension/revocation and retained checkpoint floors. Production delivery is
refused by default; protected agency routes and independent custody remain
pending.
[PRD-19 end-to-end profile](docs/production-prd19-end-to-end-profile.md) freezes
native and SACRO requirements before a fresh public Wine run, binds both results
to independent reviews and controlled fixture delivery, and retains a signed
historical receipt under external pins. Production authorization remains blocked.
[PRD-20 monitoring and incidents](docs/production-prd20-monitoring-incidents.md)
adds fixed redacted fault events, local custody floors, a durable alert outbox
and guarded incident records. Its local receiver sends no external notifications;
agency SIEM, on-call ownership and independent custody remain pending.
[PRD-21 capacity and recovery](docs/production-prd21-capacity-recovery.md) adds
bounded public I/O and job-concurrency measurements, witnessed historical
backup/restore and delivery-restart denial drills. Agency-approved scale,
provider failover and current-authority recovery remain pending.
[PRD-22 assessment handoff](docs/production-prd22-independent-assessment.md) now
adds fresh fixed adversarial probes, externally pinned signed local packets and
current independent fixture finding review. Eleven production blockers remain
open; deployed penetration testing and agency/scientific acceptance are pending.
[PRD-23 restricted pilot plan](docs/production-prd23-restricted-pilot.md) now
adds exact public-evidence scope, seven current signed fixture participants and
local plan review/suspension/withdrawal controls. Actual agency pilot admission
remains blocked. Next is **PRD-24**, pilot exit and operational handover.

## Research relationship and deployment boundary

The research manuscript and curated experiment reports are in a local checkout
of the [separate academic repository](https://github.com/elmontu/AI_Model_Academic)
at commit `826b5e5fbda2cd50e6bb856a90be1b18619afc11`. Its public GitHub
publication is pending; full raw study archives remain local. The later advisory
and displayed-table digest remain in this repository; the dated 28 September
bundle is available from Git history. These saved results do not validate every
current implementation path or establish a privacy guarantee for an arbitrary
agency model.
Older dated receipts retain commands from the former combined checkout; use
the setup and test commands above for this government-only tree.

The government and research work use related versioned contracts and formal
artifacts. The local services do not provide authenticated custody, independent
approvers or enforcement against a storage administrator. No deployment
obligation is waived. See the
[industrial track and acceptance evidence](docs/system-audit-specification.md#industrial-track)
before extending the boundary to an agency deployment.

## Reference implementation quick start

Read the [implementation and motivation guide](docs/implementation-and-motivation-guide.md) for the purpose of each component, a complete walkthrough, model and adversary coverage, evidence interpretation and remaining work.

The [government integration report](docs/government-audit-update-2026-09-22.md)
records the newer review and delivery checks. The
[government-only publication verification](reproduction/government-publication-20260922/README.md)
records checks against the exact selected source tree and its built wheel. The
[September 10 training verification report](docs/framework-e2e-validation-2026-09-10.md)
retains that source snapshot's option/adversary matrix and explicit coverage gaps.

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

Start with the government operating guide, then use these shared references.
Industrial requirements remain in the integrated system specification.

| Question | Reference |
|---|---|
| How do I review a government model release? | [Government audit guide](docs/government-audit-guide.md) |
| What was checked for this integration? | [Government audit verification report](docs/government-audit-update-2026-09-22.md) |
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

The [retained government integration checks](reproduction/government-audit-update-20260922/README.md)
distinguish focused implementation tests, earlier broader runs and failed
setup/replay attempts. Broader results include locally maintained research work;
they are not a claim that every associated study is published in this update.
Temporal service admission under a declared attribute-DP budget does not
establish membership protection, whole-record privacy or general release clearance.

The [government reproduction index](reproduction/README.md) distinguishes
retained results, negative results, configured experiments and templates. The
[technical advisory](docs/advisory/technical-report-2026-10-01.md) links the
historical and later academic result inventories. [Scripts](scripts/README.md) is
the executable tool catalog.

Historical registrations and results retain their original source/runtime
bindings. They do not validate the revised implementation. Changed source hashes
must fail old registrations; new scalability claims require prospective
registration and fresh execution. Negative results and manifest-bound artifacts
are preserved, including the [ceiling experiment summary](reproduction/ceiling-experiment-summary.json).

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
