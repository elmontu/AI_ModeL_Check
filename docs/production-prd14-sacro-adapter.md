# PRD-14: scoped SACRO-ML probability membership adapter

Status: **in progress**. This local milestone uses the actual pinned SACRO-ML
implementation in a separate dependency environment and compares its retained
scores with independent calculations and native results. It covers one bounded
public probability-membership method. Production isolation, scientific
qualification, agency acceptance and dependency-license review remain open.
No result clears, authorizes or delivers a model.

## Source and environment

The selected release is [SACRO-ML 2.0.1 on PyPI](https://pypi.org/project/sacroml/2.0.1/),
observed in official release metadata on 1 October 2026. The selected artifact is
`sacroml-2.0.1-py3-none-any.whl`, with SHA256
`8b0d5d9b32cff57d283a82722cbd244560d04cb6184ae7c493c6c94496957741`.
The [upstream project](https://github.com/AI-SDC/SACRO-ML) and wheel metadata
identify the MIT license. That observation does not approve this repository's
licensing, the entire dependency environment, data rights or agency deployment.

The worker uses a separately prepared, fully pinned runtime selected through
`--python`. Installing that environment is an explicit preparation step; the
comparison command does not download data or install dependencies. The native
application's existing runtime and prior source-bound evidence are preserved.
Runtime/package mismatches and absent dependencies are failures, not permission
to substitute the native attack and report external execution.

The [Windows wheel manifest](../deploy/sacro/windows-cp312.json) records 73
artifacts for Windows AMD64 / CPython 3.12.14; the accompanying
[hash requirements](../deploy/sacro/windows-cp312.requirements.txt) pin their
installation inputs. This is not a Linux execution or production-image claim.
Upstream requires `fpdf` 1.7.2, available as a source distribution: its selected
wheel was built locally from the verified PyPI source, with declared license
`LGPLv3+`. It was not silently replaced with `fpdf2`. That build and the full
runtime's transitive-license review remain separate from SACRO's MIT metadata.

This is separate from MRA's earlier
[independent SACRO-ML-inspired tools](sacro-ml-red-team.md). Those native tools and
the policy-bound scientific attack-battery contracts remain distinct. The new
comparison is not `AttackBatteryWorkerOutput` and cannot inherit that contract's
assessment role.

## Public profile and artifact boundary

The input is the exact captured native bundle from
[PRD-13 registered public training](production-prd13-model-registration.md).
The source/profile pins and original data, plan, candidate, predictions, scores,
report and replay bindings are checked. The parent also reloads the pinned
public profile and reconstructs its exact native data and plan bytes. A caller's
source label or restamped self-consistent bundle cannot substitute for that
source observation. Research sources use `--data-root`, defaulting to
`D:/model_audit_data`, through the existing read-only loader. The target is not
silently refitted for SACRO, and earlier registration or evidence bytes are not
restamped.

| Profile | This method's applicability |
| --- | --- |
| ACS prepared public covariates | Classification probability membership |
| BTS prepared public flight covariates | Classification probability membership |
| HMDA prepared public mortgage covariates | Classification probability membership |
| TLC prepared public trip covariates | Classification probability membership |
| Scikit-learn Breast Cancer | Classification probability membership |
| Scikit-learn Wine | Multiclass probability membership |
| Scikit-learn Digits | Multiclass probability membership on numeric pixel features |
| Scikit-learn Diabetes | Explicitly unsupported: the retained Ridge candidate has continuous outputs |

All eight profiles must receive a disposition. Seven classifier executions do
not become eight successful attacks by dropping Diabetes. Regression labels are
not binarized, and residuals are not relabeled as class probabilities. This does
not add a CNN, LLM, extraction, attribute-inference, LiRA, QMIA or regression
attack adapter, nor make the other 79 research-catalog profiles available.

Only inert numeric probabilities and declared split/lineage metadata reach the
external attack. The path does not call SACRO's `Target.load`, unpickle a model,
accept a caller-selected estimator class or import a private candidate. It has
no protected-data intake or external target endpoint.

## Frozen comparison protocol

The comparison plan is written before the external attack runs. It binds the
input bundle, profile and implementation/runtime observations, exact group
roster, attack parameters, repetitions, controls and stopping rule.

There is one probability vector per identical-feature group. The input order is
frozen: target-training member groups first, then nonmember calibration and audit
groups. Repeated attack-train/test splits operate on these groups, with retained
identities for independent replay. Repeated rows in a group cannot be presented
as independent attack trials. These groups are measurement units, not proven
persons or a validated privacy adjacency relation.

The scoped upstream probability worst-case attack uses three repetitions with
split seeds `20261001`, `20261002` and `20261003`, and attack test fraction `0.5`.
Its fixed RandomForestClassifier has 32 trees, maximum depth 5, minimum leaf size
10, minimum split size 20, `n_jobs=1` and `random_state=20261001`. There is no
hyperparameter tuning; upstream dummy repetitions are zero because the explicit
positive and null fixtures below are run and retained separately. Probability
features are sorted, and the model-correctness feature is disabled. The adapter
uses the fixed public `run_attack_reps` path. All repetitions remain in the
result; there is no best-run selection or outcome-dependent retry. Repetitions
overlap and are not pooled as independent trials or a confidence interval.

The attack assumes labeled member and nonmember prediction outputs for attack
training. This is a deliberately strong diagnostic setup, not proof that a
particular recipient has those labels or that its full interface is covered.

## Controls and independent metrics

The positive control gives members concentrated probability vectors and
nonmembers uniform vectors. The null gives both groups the same uniform vector.
Both traverse the external attack/scoring path. Every positive-control repetition
must have raw AUC at least 0.9; every null repetition must be within `1e-12` of
0.5 under tie handling. These public probability fixtures test that the configured
attack detects the deliberately exposed signal, not the privacy of a realistic
fitted control model. A completed metric calculation with failed controls cannot
be counted as a successful profile comparison.

The native PRD-11 label-aware controls remain separate. For binary classification,
a native member's high true-label probability and a nonmember's low true-label
probability can have identical sorted probability vectors. Reusing those vectors
as the external positive control would fail to expose membership to the selected
attack's features.

Retained attack-test membership labels and scores support independent raw AUC
and confusion-count calculations. A positive decision uses the exact rule
`member_score > 0.5`; threshold ties are not counted as positive. This is a fixed
classifier operating point, not a calibrated low-FPR claim. The comparison does
not make a p-value, population confidence, statistical-significance or privacy
ceiling claim.

The report keeps both the original native loss-membership AUC and a newly
calculated native loss AUC on the exact external attack-test groups. The paired
statistic separates attack differences from differences in evaluation records.
Native loss and SACRO probability-vector attacks need not return equal target
AUCs. Independent replay requires agreement between each retained score vector
and its own reported metrics, not agreement between distinct attacks.

Missing repetitions, failed controls, changed artifacts, malformed/nonfinite
probabilities or metrics, dependency errors and timeouts remain explicit failure
outcomes. Unsupported scope is recorded separately. A small or chance target
AUC never converts a failed or unsupported run into a privacy pass.

## Execution and retained output

From this D: government checkout, pass the Python executable of the separately
prepared SACRO environment:

```powershell
& .\.venv-pipeline\Scripts\python.exe -B scripts/rehearse_sacro_adapter.py --python .local/verification/prd14-sacro-20261001/sacro-env/Scripts/python.exe --output .local/sacro-v1
```

The default input is the retained PRD-13 case roster. `--benchmark` selects another
eligible benchmark location with that case roster; it does not admit arbitrary
model files. Output must be a fresh ignored directory under this government's
`.local/`. Original/academic workspaces, research sources and earlier evidence
are not changed. Inspect every profile's disposition and control/replay result,
not only the top-level command status.

The external worker runs in a child process with a deadline. A separate Python
environment and subprocess deadline do not establish network/filesystem
isolation, a hostile-code sandbox, verified resource quotas or cloud admission.
The comparison does not attest original training or the execution platform.
All clearance, assessment and authorization eligibility flags stay false.

A fresh PRD-12 native replay signature binds the comparison, raw worker output
and frozen comparison-plan hashes through its job context. Its signed operation
remains `retained_native_replay`. This protects the linkage to local retained
bytes; it is not a SACRO execution attestation, an original-training signature
or proof that an independently trusted worker executed the external attack.

## Observed local comparison

All seven classifier profiles completed the real pinned SACRO attack, both
controls and fresh comparison-bound native replay. Each profile ran three target,
three positive-control and three null-control repetitions: **63 external
repetitions total**. Positive controls produced AUC 1 and flat null controls AUC
0.5. Diabetes retained `unsupported`; all eight profiles received a disposition.
Source and original bundles remained unchanged.

The following means use the same frozen held-out feature groups within each
repetition. They are descriptive historical-sample statistics with no uncertainty
claim or release threshold. Repetitions overlap and are not independent samples.

| Profile | SACRO raw AUC mean | Paired native loss AUC mean |
| --- | --- | --- |
| acs | 0.501268 | 0.507204 |
| bts | 0.492856 | 0.496289 |
| hmda | 0.520380 | 0.503422 |
| tlc | 0.515380 | 0.484063 |
| sklearn-breast-cancer | 0.501042 | 0.492400 |
| sklearn-wine | 0.546801 | 0.586869 |
| sklearn-digits | 0.482294 | 0.521870 |

SACRO rounds its exported AUC to eight decimal places. The comparison checks that
rounded value against the independently calculated statistic while retaining the
full-precision independent result. A preliminary Wine run exposed that formatting
difference and was retained as a failed comparison; the corrected complete run
above was executed afresh.

Validation logs and `validation.json` are retained in
`.local/verification/prd14-sacro-20261001/`. They record the complete required
suite, the new tests in the hash-locked external environment, repeated package
builds, installed-package runs and preservation checks. Test doubles in unit tests
are separate from the actual external executions reported above. Local success
does not demonstrate remote CI, Linux execution, fresh audit data or privacy.

## Ownership and production closure

The planned maintenance role is **ML/test lead**; an accountable person still
needs appointment. Agency license and security reviewers and the independent
scientific assessor must approve the actual dependency/data/model scope. The
upstream MIT license does not resolve this repository's absent top-level license
or the full runtime's transitive-license review. Current advisory observations,
maintenance and change review are separate from a successful numerical run.

PRD-14 remains open for an agency-approved target/interface, independently
qualified attacks and realistic controls, complete required threat coverage,
protected worker custody, current authentication, verified isolation and
integration with authoritative jobs, evidence and release gates. Historical
public samples remain reused; protected populations and complete external
disclosure histories remain unresolved. This local adapter cannot remove any
PRD-13 production blocker.

The next planned task is **PRD-15**: an authoritative registry, migrations and
atomic head/charge/outbox operations, with race, duplicate, failure and failover
histories that preserve the release and accounting invariants. GitHub publication
remains pending authentication.
