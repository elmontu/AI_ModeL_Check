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

The new [privacy-first model-export prototype](docs/private-export-systems.md)
implements an exact two-stage binary DP channel, durable cumulative reservations,
and built-in models trained exclusively on sanitized values. Its
[privacy argument](docs/private-export-privacy-argument.md) and
[systems study](academic/private-export-systems-20260925/README.md) separate the
bounded guarantee, measurements, and open MLSys research questions. This path is
operated through `mra-private-export`; it has not replaced the existing console.

The [current research plan](academic/research-plan-20260926.md) explains person-level
privacy across models that recipients may retain and share. The new
[bounded central gate](docs/central-audit.md) registers person-linked sources,
reserves a common allowance before computation, binds delivered bytes, and keeps
charges after revocation. It compares exact ledger and graph representations;
its approved-producer and local-authority assumptions remain explicit. The
[validation study](academic/central-audit-validation-20260926/README.md) separates
accounting tests, matched costs and generic person-level prediction experiments.
This path has not replaced the browser console.

The [current manuscript PDF](output/pdf/manuscript-expanded-graph-20260928/mra-paper.pdf)
retains claim-relevant experiments and keeps routine engineering test results in
the study companions; the [editorial record](academic/essential-results-20260926/README.md)
lists the removals and retained evidence.
The [latest technical revision](academic/gap-closure-20260928/README.md)
adds conditional-composition controls, compact exact certificates, cached public
checks, disjoint-block execution and real-data use of the finite optimizer.
The real-data utility result is negative; a public information-value screen
supports a verified no-LP reuse path when further adaptation cannot meet its goal.
The [finite-continuation guide](docs/finite-continuation.md) documents these APIs.
Section 3 distinguishes internal pseudonymization from separately accounted
private exports; removal of direct identifiers is not a privacy guarantee.
The [expanded Figure 1](academic/expanded-agency-graph-20260928/README.md) links
derived datasets and model releases to main-dataset versions and shows the
registration of new data.

Only the [current manuscript source](academic/paper/mra-paper.tex) and the
current PDF linked above are maintained as manuscript editions. Superseded
draft copies, PDF builds and page renders were removed on 28 September 2026;
the [cleanup record](academic/manuscript-cleanup-20260928/README.md) lists the
scope. Experimental records, research reports and implementation evidence remain.

The [referee-response revision](academic/referee-corrections-20260928/README.md)
checks the supplied review against proofs and saved results. The current draft
centers the finite-channel extension, restores primary utility outcomes, adds an
exact uniqueness certificate and corrects the deletion interpretation. Standard
accounting and synthetic calibration results appear in supporting appendices.

The [follow-up review and completed next steps](academic/review-followup-20260928/README.md)
add a lossless count reduction, exact-certified extension curves through forty
records, a corrected unknown-generator utility study, and an executable link
between the optimizer and the central gate. The [integrated release measurements](academic/extension-enforcement-20260928/README.md)
report full-path cost, verification cost and the one-extension trust boundary.
These are finite-model research results, not a deployed agency or a general
large-model privacy analyzer.

The separate [controlled deletion study](academic/unlearning-general-trends-20260925/README.md)
tests exact sufficient-statistic updates, private ridge retraining and retained
model histories on generic synthetic inputs. It is a research baseline, not
unlearning integrated into the console or a production privacy certificate.

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
| Temporal release service | Prepare, check, recorded local review, atomic charge/receipt commit and current delivery checks | Requires a separately initialized registry and verified run; does not import console models automatically |

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
& .\.venv-pipeline\Scripts\python.exe -m model_release_assurance.export_poc serve --data .local/model-export-poc --repository . --temporal-run "PATH_TO_VERIFIED_RUN" --temporal-operator "PATH_TO_INITIALIZED_OPERATOR" --port 8767
```

Replace the placeholder paths with existing directories. A fresh checkout does
not contain those study/model stores. Without them, temporal views are
unavailable and the launcher explains the missing inputs; the synthetic lab
still works. It does not silently create a registry or restore privacy budget.
The [temporal service guide](docs/temporal-release-assurance.md) explains its
channel/unit accounting and trusted-storage assumptions.

## Research relationship and deployment boundary

The current research draft is *Data Minimization and Dependency Accounting for
Repeated Model Export*. The [paper source](academic/paper/mra-paper.tex),
[current protocol revision](academic/protocol-rewrite-20260923/REPORT.md),
and [build and reproduction guide](reproduction/README.md#paper-draft) describe
its matched omission/privacy controls, complete training/scoring dependencies
and implementation boundaries. The draft and local study outputs are not an
externally validated or fully published model/data archive. Older aggregate
companions remain historical evidence, not the current paper's complete results.

The local release workflow and government exercises share the existing core.
The paper's new accounting kernels are separate experimental implementations;
their benchmark results do not imply that they have replaced the HTTP service.
The local services lack authenticated custody, independent approvers and
resistance to a privileged storage administrator. In particular, the conditional
adaptive privacy argument requires information-flow restrictions that the
operator UI does not enforce. See the
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
