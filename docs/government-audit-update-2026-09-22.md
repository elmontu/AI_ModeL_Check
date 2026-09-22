# Government audit update — 22 September 2026

This update connects the current academic manuscript to the government's local
model-release audit workflow. The [operating guide](government-audit-guide.md)
explains how to use it. Existing academic edits, study registrations and measured
results remain unchanged by this integration.

## Implementation

- Twelve review controls address purpose and omission, adjacency, recipient history,
  training/scoring dependencies, cache/version reuse, protected information flow,
  cumulative accounting, derivative lineage, attacks/uncertainty, exact-byte delivery,
  expiry/recovery and the accountable agency decision.
- Review entries are appended to the console database and bound to a versioned
  case-context digest. Evidence is selected from existing case bindings and read
  through the existing verified-byte path. Entries retain original cited hashes.
- A changed case configuration makes old entries stale. Missing or changed cited
  files prevent a current recorded-evidence status. Review writes serialize with
  console rebinding and are refused while case jobs are queued or running.
- The browser shows recorded entries, gaps, stale findings and earlier rationale.
  JSON downloads regenerate the report against current bindings and file bytes.
- Explicit `--repository`, `--temporal-run` and `--temporal-operator` launcher
  options select existing temporal inputs. Missing explicit prerequisites fail
  before opening stores; absent legacy defaults produce actionable diagnostics.
- The full guide, console guide, capability inventory, README, integrated audit
  specification and candidate protocol distinguish these new local functions
  from production authorization and from older research evidence.

The checklist is a local review record, not a new scientific gate. It never
changes the assessment engine's decision or issues release authorization.
Education-mode document requirements remain unchanged. No models are imported
from a console case into the temporal registry automatically.

## Verification scope

The government-only publication was checked from a clean export of the Git
staging area, excluding the revised academic manuscript and new ACS study files.
That selected tree completed **958 main tests (one Windows symlink skip), 43
previously published academic baseline tests, and five additional link-checker
regressions**, with no failures or errors. Its built wheel includes the console,
export and temporal assets and runs the export catalog from an isolated install.
See the [publication verification](../reproduction/government-publication-20260922/README.md)
for exact source hashes, runtime versions and logs. The following larger counts
describe the earlier full local workspace, which included separate academic work.

The main suite in the existing research-capable runtime completed **1,201 tests,
zero failures/errors, two skips**. It includes the local console, export broker,
temporal pipeline, adversarial stage/binding checks and broader framework tests.
The final focused run completed **133 tests, zero failures/errors and no skips**
after the download and historical-hash changes. Its source-bound receipt is in the
[retained verification index](../reproduction/government-audit-update-20260922/README.md).

Browser verification used a separate synthetic case store, not existing agency
cases. It exercised case creation, evidence binding, the twelve-control catalog,
recording a rationale, and changing cited evidence. Refresh changed the finding
from recorded to needs work and disabled the changed evidence. The real case
store remains separate from this browser-test workspace.

The original console runtime lacks the optional PyTorch dependency required by
some newer academic tests. A first broad run therefore recorded seven import/runtime
errors and an outdated README-navigation assertion. The documentation assertion
was updated to check the current manuscript and supported navigation. The subsequent
research-runtime run passed. Initial logs are retained; failures were not relabelled
as passing results.

Historical model replay must use a compatible producer runtime. The September 17
study recorded XGBoost 3.4.1 and scikit-learn 1.9.0, while the older console research
runtime has XGBoost 2.1.4 and scikit-learn 1.6.1. A 55-test academic run under that
older runtime reported eight XGBoost prediction-replay subcase failures, alongside
version warnings. Artifact hash checks passed. Replaying in the preserved
`.privacy-venv` environment, with all recorded dependency versions matched,
completed **55 academic tests with no failures, errors or skips**. No models,
registrations, tolerances or recorded predictions were changed. Both attempts
are retained; cross-version pickle inference is not validated.

The two main-suite skips are optional ReportLab rendering and a Windows symlink
capability check. The focused government audit tests have no dependency skips.
All 37 current schemas still match their existing byte manifest. JavaScript
syntax and the links in the edited current guides were checked separately.
The publication's repository-wide Markdown check passes. It explicitly reports
twelve historical links into ignored `output/` as local-only generated artifacts;
these are not bundled evidence. Other missing local targets still fail the check.
Those historical academic files were not rewritten for this update.

## Boundaries that remain

- Review rationale is a trusted local operator's statement. Matching hashes do
  not establish adequacy, honest collection or correct mechanism information flow.
- The local database does not authenticate independent reviewers or resist an
  administrator who can rewrite both storage and evidence. The current workflow
  is suitable for trusted local exercises.
- Individual cited files use the existing 10 MiB verified-read limit. A larger
  package needs a bound manifest; checking that manifest does not rehash every
  listed member as part of this checklist.
- Only identical protected values under their original attribute version and
  channel contract qualify as cache reuse. Fresh draws and raw-input-dependent
  selection or scoring need separately justified privacy treatment.
- The temporal service's registered disability-attribute contract is distinct
  from the paper's later recorded-sex and two-attribute studies. No scope is
  widened by a successful budget check, checklist record or test run.
- The September 10 training/adversary matrix and later ACS measurements remain
  historical, source-bound results. This integration does not refit those studies,
  claim general adversary completeness, validate Docker execution or rebuild Lean.
