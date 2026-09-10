# Set up a model-release case

Use this workflow to prepare the exact release, find missing inputs and run the
existing assessment engine. It supports trained, fine-tuned, adapter, merged,
ensemble and distilled candidates. It does not train arbitrary models, approve
agency documents, implement a production registry or authorize release.

See the [implementation and validation report](pipeline-implementation-report-2026-09-08.md)
for checks executed locally and remaining gaps.

For trusted testers who prefer a browser, use the [local service console](local-console.md):
separate API and worker processes, a persistent queue, guided demos and case results.
The setup script's `--profile console` installs that runtime and the demo dependencies.

## 1. Install once

From a source checkout, use Python 3.11 or newer. No Make, shell activation or
administrator access is required. On Windows, `py -3` can replace `python` if
that is your installed Python launcher.

```console
python scripts/setup_pipeline.py --profile training
```

The default creates a **new** `.venv-pipeline` environment, installs the locked
core and experiment dependency tier, installs this checkout and prints runtime
versions. The training tier supplies the public-data model and attack dependencies;
the console tier additionally supplies the browser API and HTTP test client. Use
`--profile core` for case preparation and assessment of existing evidence.
Optional analyzers may need their separately documented dependencies.

The installer refuses an existing directory, including a broken virtual
environment. Choose another `--venv PATH` rather than overwriting it. Failed
installations retain their partial environment for diagnosis. Package installs
normally use the configured package index; no dataset is downloaded by setup.
Use `--dry-run` to inspect commands. In an offline environment, supply
`--wheelhouse APPROVED_DIRECTORY`; it must contain compatible setuptools/wheel,
all locked core wheels, and the selected experiment dependencies. This is local
index installation, not operating-system network isolation. Capture the resolved
environment separately for prospective experiments; the experiment tier is not
an exact historical runtime lock.

For the commands below, use the environment's `mra-workflow` executable:

- Windows PowerShell: `& .\.venv-pipeline\Scripts\mra-workflow.exe ...`
- Linux/macOS: `./.venv-pipeline/bin/mra-workflow ...`
- Or the environment's Python: `python -m model_release_assurance.workflow ...`.

## 2. See a working pipeline

```console
mra-workflow doctor
mra-workflow demo --output output/my-first-training-run
```

`demo` selects the existing **offline** scikit-learn breast-cancer dataset,
trains real XGBoost models, packages the candidate, collects its registered
membership evidence and records the MRAP prefix ending at ASSESSED. Read the
generated `START-HERE.md`. Expected scientific disposition is HOLD or BLOCK;
successful execution is not a privacy pass. The command never overwrites an
existing run. It requires the source checkout and training dependencies.

For OpenML or approved local training data, use the existing
[training runner](guided-government-health-demo.md). Fine-tuning, merges and
other training operations remain in your approved external trainer. The local
workflow consumes their artifacts; it never executes commands from case files
or loads model weights as executable objects.

## 3. Initialise your agency case

Choose a protected local location, outside a publicly synchronized folder or
public checkout when handling confidential material.

```console
mra-workflow init CASE --kind adapter --route named-party-weights
```

Kinds: `trained`, `fine-tuned`, `adapter`, `merged`, `ensemble`, `distilled`.
Routes: `api`, `named-party-weights`, `public-weights`.

The command creates `project.json`, `lineage.template.json`, `START-HERE.md`
and a `.gitignore` that ignores case content. It refuses an existing directory.
Git ignore is an accidental-publication aid, not access control or encryption.
Every required input starts **missing**; no mock evidence is inserted.

## 4. Bind real inputs

```console
mra-workflow bind CASE candidate PATH_TO_EXPORTED_BUNDLE
mra-workflow bind CASE request PATH_TO_ASSESSMENT_REQUEST_JSON
mra-workflow bind CASE agency-scope PATH_TO_SCOPE_REVIEW
mra-workflow bind CASE evaluation-plan PATH_TO_FROZEN_PLAN
mra-workflow bind CASE utility-report PATH_TO_UTILITY_REPORT
mra-workflow bind CASE security-report PATH_TO_SECURITY_REPORT
mra-workflow bind CASE independent-review PATH_TO_REVIEW_REPORT
```

`bind` stores the absolute path and observed SHA-256; it does not copy private
data, approve a document or prove when a plan was frozen. Rebinding is an
explicit update of the local inventory. Previous assessment attempts retain
their old project snapshots. Run from one operator at a time; this local config
editor is not a concurrent case-management service.

The request must be a current `AssessmentRequest`, referencing actual evidence
accepted by the existing Engine. Relative request/evidence paths keep their
original meaning; do not relocate a request without its referenced materials.
The request artifact must match the candidate digest. Weight-release routes
require `full_artifact` access. Selecting a public/named-party route does not
authenticate the recipient or certify that the policy addresses public access.
Review those obligations in the agency scope.

### Complete the lineage file

The easiest path is to generate and bind it from actual files. For an adapter:

```console
mra-workflow lineage CASE --parent base PATH_TO_BASE_MODEL --recipe TRAINING_CONFIG --data-manifest DATA_MANIFEST --overlap-evidence OVERLAP_REVIEW --population-overlap overlapping
```

Repeat `--parent ID FILE` for each merge/ensemble component or teacher. Use
`--previous-release ID` for each prior release named in the request. The command
hashes the inputs, validates structural requirements, writes a new lineage file
and binds it without overwriting earlier lineage files. The overlap declaration
must come from the protected review; the command does not infer it from hashes.

Alternatively, use `mra-workflow fingerprint FILE` to get a `{path, sha256}` reference. Populate
the template and save it as `lineage.json`; then bind it:

```console
mra-workflow bind CASE lineage PATH_TO_LINEAGE_JSON
mra-workflow check CASE
```

The local lineage format requires:

| Field | Content |
|---|---|
| `format_version` | `local-lineage/1` |
| `kind` | The same candidate kind as the case |
| `candidate_sha256` | Exact exported candidate digest |
| `parents` | List of `{parent_id, path, sha256}` for immediate parent artifacts; at least one for fine-tuning/adapters/distillation, at least two distinct artifacts for merging/ensembles |
| `recipe` | `{path, sha256}` for actual training/merge/router/distillation configuration |
| `data_manifest` | `{path, sha256}` for the protected dataset and ancestry inventory, including teacher-generated data where relevant |
| `population_overlap` | `single-source`, `disjoint` or `overlapping`; multiple parents require disjoint/overlapping. `unknown` blocks preflight |
| `overlap_evidence` | `{path, sha256}` for the review supporting the population declaration; single-source cases still document their basis |
| `previous_release_ids` | Exact set of previous release IDs declared in the AssessmentRequest |

Paths inside lineage resolve relative to the lineage file, not the case directory.
Parent IDs and bytes must be distinct; the candidate cannot be its own parent.
This checks immediate references, not the truth/completeness of an ancestry graph,
the adequacy of overlap analysis or privacy composition. Keep full ancestry in
the protected manifest and have it independently reviewed. Contracts are local
workflow formats, separate from the 37 registered MRAP schemas.

For derivatives, the evaluation plan and reports should contain these tests:

- Fine-tuned/adapters: base versus derivative; adapter plus recipient's base;
  synthetic known-leak controls; extraction/membership and utility/subgroups.
- Merged/ensemble: each component, actual combination and joint recipient
  access; exact coefficients/router, intermediate channels and overlapping data.
- Distilled: teacher outputs/prompts and student; private-data access at every
  step; assess any released synthetic dataset separately and jointly.
- All: justified upper evidence where applicable; full export inspection;
  bounded recipient-modification screens; independent replay. An attack failure
  or parent approval cannot be promoted into derivative clearance.

## 5. Assess and review

```console
mra-workflow assess CASE
```

`check` exits 2 for missing/invalid inputs and 0 for `inputs_complete`. This
means file/lineage preflight passed, **not** scientific readiness or release.
Documents are not parsed as approvals. The Engine validates the actual request,
policy and scientific inputs during assessment.

Every `assess` creates a unique directory under `CASE/runs/`, snapshots the
project, performs preflight and runs the existing Engine with local audit
intent/completion/failure events. It checks input bindings again afterwards.
A failed attempt is retained, with a machine-readable non-authorizing result;
retry starts another directory. Successful output includes the assessment,
local audit verification, runtime inventory and `START-HERE.md`.

Exit 0 means the orchestration completed even when the scientific verdict is
block/inconclusive. Automated consumers must read `assessment-report.json`.
`workflow-result.json` always has `authorized=false`, `deployed=false` and
`authorization_eligible=false`. The workflow does not synthesize an authenticated
MRAP transcript, sign a release or fabricate institutional approval. Continue
through the [existing record/sign/gate process](gap-remediation.md#four-verdict-record-and-gate)
only with appropriate scope and keys; that gate is also non-authorizing.

Runs retain references, not a complete immutable archive of source evidence.
Independent custody, anti-rollback anchors, authenticated workers, managed keys,
recipient enforcement and agency authorization remain the
[production obligations](system-audit-specification.md#industrial-track).
Pre/post hashing is not isolation from a malicious concurrent filesystem actor.
Audit storage may contain sensitive request/report content; protect it accordingly.

## Educational exercises

Use `mra-workflow init CASE --mode education` to make agency-scope, security-report
and independent-review optional. Omissions are recorded as warnings. Evidence
hashes, lineage and scientific checks still apply. The CLI default is review;
new [console](local-console.md) cases default to education and support binding
local files in the browser. Existing cases retain their mode.
