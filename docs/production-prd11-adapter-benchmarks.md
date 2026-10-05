# PRD-11: typed adapters and broader public-data benchmarks

Status: **in progress**. This local milestone expands the engineering framework
beyond healthcare. It adds versioned numeric classification/regression adapters,
controls, uncertainty and saved-candidate replay. Production integration and
independent scientific acceptance remain pending. Work and new evidence stay in
the government repository on D:. The
original research and separate academic repositories are not edited.

## Scope requested by the user

The framework is sector-neutral. A CDC/MOH-type public-health agency remains one
example production pilot; it does not restrict model tests to healthcare. Each
actual deployment still needs its own agency, purpose, classification, recipient,
protection claim and acceptance profile. Agency private cloud remains the intended
hosting model, with provider and region open.

The research data currently available on D: includes four broad public-source
families. The new loader uses their small retained prepared matrices:

| Corpus | Domain | Prepared rows | Public covariates | Utility target |
| --- | --- | ---: | ---: | --- |
| ACS PUMS | Census, population and income | 27,000 | 8 | Historical income classification |
| BTS | Aviation and transport | 27,000 | 7 | Departure disruption |
| HMDA | Mortgage lending | 27,000 | 7 | Loan origination |
| NYC TLC FH-VHV | Taxi and mobility | 27,000 | 4 | Trip duration over 30 minutes |

Their fixed location is
`D:/model_audit_data/experiments/mixed-model-export-20260929-v1/<corpus>/data/`.
The adapter reads `B` public covariates and `y` utility labels. It does not use the
research withheld attribute `z`, record keys or existing fitted models. The
existing prepared feature engineering and labels remain the historical protocol;
this benchmark does not redefine them or repeat that protocol's privacy claim.

All four NPZ files were observed to match their retained manifest hashes before
implementation. The loader rechecks these hashes on each run. Those manifests
state that person-level disjointness and historically untouched data are **not**
established. Reusing these samples cannot create a fresh scientific audit.

The D: collection also contains much larger raw files, years, monthly partitions,
archives and duplicated experimental outputs. A read-only file inventory found
about 200 GB under the public-data root, including four ACS national vintages,
192 BTS months, seven HMDA years and 90 TLC months. These are file metadata
observations, not freshly verified raw-data hashes. This milestone does not scan
or train on their complete contents. Dataset-family coverage, prepared-sample
coverage and whole-corpus/partition qualification are separate measurements.

## Coverage catalog

`production_adapters.catalog` produces 87 source-profile entries:

- Four available prepared research families above.
- Four bundled scikit-learn fixtures: breast cancer, Wine, Digits and Diabetes.
  These exercise binary classification, multiclass classification, numeric digit
  features and continuous regression. The numeric Digits run is not CNN training.
- Seven other historically used research families: Adult, Covertype, MNIST,
  EuroSAT RGB, WildChat-4.8M, Dolly15k and 20Newsgroups. Eligible source snapshots
  and corresponding adapters are absent from this D-drive benchmark profile.
- The 72 entries in the retained OpenML-CC18 registration manifest. Registration
  is not proof of completed training. Adult/MNIST overlap other catalog entries;
  87 profiles must not be described as 87 independent datasets or experiments.

Catalog entries carry modality, sector and source references. Historical
references may identify recoverable objects in Git history; no retired archive
files are restored. The OpenML registry is structurally checked and pinned by a
canonical digest. This identifies the retained local catalog; it does not
establish remote authenticity, current licenses or dataset availability.

Every entry gets an outcome in the batch result. `passed` means the implemented
engineering execution and integrity checks completed; it is not a privacy pass.
`unavailable`, `unsupported` and `failed` remain distinct. Failed hashes or
malformed inputs cannot be relabelled missing. All batch reports explicitly keep
`all_research_datasets_tested=false`: the selected catalog cannot establish
universal research coverage. No missing dataset is downloaded automatically.

## Typed candidate and replay contract

The native adapter accepts bounded finite numeric matrices, up to 4,096 rows and
128 features. Classification uses train-only StandardScaler and GaussianNB with
2 to 32 classes. Regression uses train-only StandardScaler and Ridge with fixed
regularization. Feature names, task, classes, numeric parameters, dataset/source
identity, plan and matrix hashes are bound into a strict versioned candidate.
Extra fields, unsafe dimensions, nonfinite parameters and incompatible tasks are
refused. Candidate loading never imports a class named by the file or unpickles
an external estimator.

Before fitting, the runner writes its plan with the fixed seed, resource bounds,
feature-group train/holdout split, calibration/audit groups, controls and stopping
rule. All rows with identical features stay in one train/holdout group, including
groups with differing labels. This prevents identical-feature overlap across
those partitions. Feature grouping is not an established person-level privacy
unit, and it does not prove independence between linked records.

The candidate is inert numeric JSON. A separate NumPy implementation computes
predictions from the exact saved bytes and compares them with the freshly fitted
scikit-learn estimator. The retained bundle can be replayed without retraining or
loading an executable model. Plan/data/candidate and report bindings are checked;
changed candidate bytes or changed scored evidence fail replay. These local
hashes establish consistency, not worker authenticity or an independent trust
root. PRD-12 handles authenticated execution evidence.

## Controls, uncertainty and limits

Classification reports utility and loss membership measurements; regression uses
squared-error membership scores and regression utility. Calibration and final
audit feature groups are separate, and membership measurements use one mean loss
per group. A known-leak control deliberately uses membership and known labels to
construct near-certain versus wrong predictions or controlled residuals. The null
control gives flat loss. These are scorer-path oracles, not realistic fitted
models or attacks against every possible recipient interface.

Reports include raw and direction-symmetric membership AUC, group counts,
calibrated TPR/FPR and conditional 95% binomial rate intervals. Intervals describe
the sampled empirical trial model; they are not population guarantees, validated
privacy ceilings or protection against untested attacks. The sample, task,
preprocessing and group definition can change the apparent attack strength.
Extraction, sensitive-attribute attacks, white-box parameter attacks, LLM/vision
adapters, composition and large-scale protected training require separate work.

Row, feature, file, archive-expansion and JSON bounds limit this engineering
profile. They are not OS-enforced CPU/memory quotas or a hostile-code sandbox.
PRD-10's fixed fictional-count worker remains unchanged. The broader benchmark
is a separate trusted local process; it cannot admit private agency data into
that worker or create a release registry or privacy budget.

## Read-only source handling

The loader accepts an explicit existing data root and fixed corpus-relative
paths. It refuses links/reparse points, unsafe file identities, hardlinks,
malformed/duplicate JSON, wrong schema/corpus/features, changed bytes and unsafe
ZIP/NPY members. NPZ loading disables pickle, validates declared bounds before
array use and checks finite numeric `B`/`y`. A fixed-seed permutation chooses the
bounded rows before outcome inspection; the selected matrix and indices are
hashed. Source bytes and identity are checked again before returning.

New plans, numeric sample replay material, candidates and measurements are
written only to a fresh ignored government `.local/` directory. The research
root is read-only. Large upstream raw-source hashes in the historical manifests
remain declarations: this command does not rehash those large files or claim
fresh acquisition, license approval or current official-source validation.

## Run and inspect

From the D: government checkout with its prepared test environment:

```powershell
& .\.venv-pipeline\Scripts\python.exe -B scripts/benchmark_research_adapters.py --data-root D:/model_audit_data --output .local/research-adapters-v1
& .\.venv-pipeline\Scripts\python.exe -B scripts/replay_native_adapter.py --run .local/research-adapters-v1/cases/acs
& .\.venv-pipeline\Scripts\python.exe -B scripts/run_required_tests.py --profile government --output .local/required-prd11
```

Each new run requires a new output path. `--max-rows` permits 128 to 4,096 rows per
profile; its default is 4,096. A batch can return exit zero with
`status=completed_with_gaps`; inspect its counts and per-entry reasons. Add
`--require-complete` to return nonzero whenever any catalog profile is missing or
unsupported. Failed source/adapter execution or source-code drift returns nonzero
and retains the failure receipt. No outcome authorizes a release.

Four mandatory test suites cover catalog claims, bounded data custody, native
candidate/replay behavior and batch orchestration. Source receipts include the
adapter implementation, test helpers, scripts, runtime declarations and OpenML
registry. External data is never required for unit tests; those use small local
public/synthetic fixtures, while an explicit D-drive run measures actual available
research inputs separately.

## Observed local results

The D-drive benchmark completed all eight runnable profiles on 1 October 2026,
using **19,370 selected rows** in total. Every candidate passed its numeric replay
and scorer controls (positive AUC 1.0; null AUC 0.5). The batch correctly reports
`completed_with_gaps`: **8 tested, 79 unavailable** catalog profiles. The latter
comprise seven other historical families and 72 OpenML registrations; overlaps
and registration-only status prevent interpreting these as independent datasets.

| Dataset profile | Selected rows | Holdout accuracy / RMSE | Majority / mean baseline | Membership AUC (symmetric) |
| --- | ---: | ---: | ---: | ---: |
| acs | 4,096 | 70.168% | 50.542% | 0.5089 |
| bts | 4,096 | 79.717% | 79.717% | 0.5063 |
| hmda | 4,096 | 61.957% | 59.938% | 0.5004 |
| tlc | 4,096 | 82.390% | 82.390% | 0.5035 |
| sklearn-breast-cancer | 569 | 92.982% | 60.351% | 0.5152 |
| sklearn-wine | 178 | 93.258% | 35.955% | 0.5642 |
| sklearn-digits | 1,797 | 79.199% | 8.899% | 0.5174 |
| sklearn-diabetes | 442 | RMSE 54.914 | RMSE 79.022 | 0.5330 |

BTS and TLC matched their majority-class baselines and had balanced accuracy
0.5. They demonstrate working artifact/control/replay paths, not useful task
models. GaussianNB applied to the retained numeric category encodings is a
simple diagnostic baseline; task-specific encoding and model selection need a
separate frozen plan and independent audit. The descriptive membership values
are not privacy clearances. Diabetes uses regression RMSE, which is not comparable
to the classification percentages.

**762 required government tests passed with zero skips, failures or errors**,
including 84 new checks (18 catalog, 23 loader, 31 native adapter and 12 CLI).
The same 84 adapter checks also passed in a fresh 31-wheel hash-locked Windows
environment; these overlap the government profile. Another 35 runner/documentation
checks passed. Source remained stable during the actual benchmark and required run.

Evidence is under `.local/verification/prd11-adapters-20261001/`, with per-profile
plans, source observations, candidates, scores, controls and replay receipts in
`research-benchmark/`. The final `validation.json` records the repeat build,
installed-wheel replays, source hashes and preservation checks. All 105 package
files present at PRD-10 remain unchanged; the new adapters are additive. Original
research data, earlier milestone evidence and the retired archive deletions remain
preserved. Linux execution, remote CI and production acceptance remain pending.

## Production closure

PRD-11 remains open for agency-approved task and protected-unit definitions,
independent statistical/scientific review, qualified resource/isolation controls,
production worker and image admission integration, authenticated provenance,
representative independent audits and further model/modality adapters. Wider
benchmark coverage does not close PRD-01 data decisions or earlier production
acceptance gates. Current license and use-condition review is still required.

[PRD-12](production-prd12-authenticated-evidence.md) now adds authenticated local
replay, exact bindings and durable replay prevention. Production image/isolation
attestation and job integration remain pending.
