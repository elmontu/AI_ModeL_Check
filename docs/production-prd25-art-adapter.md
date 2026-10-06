# PRD-25: scoped ART retained-loss membership comparison

Status: **in progress**. This phase adds a real pinned Adversarial Robustness
Toolbox (ART) learner to the government repository. It evaluates eight existing
public tabular profiles, including continuous Diabetes regression, using the
explicit interface `trusted-retained-group-loss-oracle/v1`. It does not qualify
agency deployment, scientific acceptance, target-query attacks or model release.
All clearance, assessment and production-authorization flags remain false.

## Selected dependency and interface

The official [ART 1.20.1 release](https://pypi.org/project/adversarial-robustness-toolbox/1.20.1/)
was verified on 6 October 2026. The selected wheel
`adversarial_robustness_toolbox-1.20.1-py3-none-any.whl` has SHA256
`03b15b35d2a1a564a436b023ad90968d64542e3ff191c668bffb8207f38683f5`.
Its metadata declares MIT; agency dependency and licensing acceptance remain open.
The [Windows lock](../deploy/art/windows-cp312.json) and
[hash requirements](../deploy/art/windows-cp312.requirements.txt) select 35 public
wheels for Windows AMD64 / CPython 3.12.14. The application wheel can additionally
be installed only when its version and physical package location match the
currently executing application; unrelated or shadow packages are rejected.
No Linux runtime is qualified here.
The worker checks the exact package-version roster, ART metadata, RECORD entries
and all 361 ART package files before and after execution. These checks detect
local drift; they do not attest a host or independently prove external execution.

The application runtime and earlier SACRO environment are preserved. Preparing
the separate ART runtime is an explicit offline/hash-locked installation step;
the comparison command neither installs dependencies nor fetches datasets.
Missing dependencies have an explicit `unavailable` disposition, with no native
substitution reported as ART execution. Mismatched or modified runtimes fail.

[Upstream membership inference](https://github.com/Trusted-AI/adversarial-robustness-toolbox/blob/1.20.1/art/attacks/inference/membership_inference/black_box.py)
supports loss input. The adapter uses actual `MembershipInferenceBlackBox.fit`
and `infer` with ART's built-in logistic-regression attack, then fixes `C=1`,
`solver=lbfgs`, `max_iter=500`, `random_state=20261006` and standard scaling.
Using a bare caller-supplied sklearn attack would route through its `predict`
method; the pinned built-in path returns membership probabilities instead.
There is no parameter search or outcome-dependent retry.

This is a narrow comparison of retained group losses. A fixed trusted loss oracle
provides the loss feature to ART; the second feature is an exact constant-zero
target placeholder. ART receives no extra label signal. The oracle cannot fit,
query or load a target model. This is not a stock ART GaussianNB/Ridge wrapper,
a label-aware ART attack, or a newly observed target endpoint. The parent uses
known true labels/targets to compute the retained losses; attack training also
receives known-member and known-nonmember groups. That is privileged auxiliary
access, not an unsupervised recipient attack.

## Frozen public inputs and comparisons

The rehearsal command validates each source observation, data matrix, plan,
inert numeric candidate and native bundle through the existing pinned PRD-13
profile loader and native replay. No pickle, arbitrary estimator import, private dataset or protected
endpoint enters this path. The target is not refitted. Original evidence bytes
are checked before and after the comparison and are never restamped.

| Profile | Native target | ART diagnostic |
| --- | --- | --- |
| ACS prepared public covariates | GaussianNB classification | Mean group cross-entropy loss |
| BTS prepared public flight covariates | GaussianNB classification | Mean group cross-entropy loss |
| HMDA prepared public mortgage covariates | GaussianNB classification | Mean group cross-entropy loss |
| TLC prepared public trip covariates | GaussianNB classification | Mean group cross-entropy loss |
| Scikit-learn Breast Cancer | GaussianNB classification | Cross-entropy loss |
| Scikit-learn Wine | Multiclass GaussianNB | Cross-entropy loss |
| Scikit-learn Digits | Multiclass GaussianNB on numeric pixels | Cross-entropy loss |
| Scikit-learn Diabetes | Continuous Ridge regression | Squared-error loss |

Identical-feature groups remain indivisible across each attack split. Conflicting
labels are retained in the mean loss, without choosing a representative label.
Feature groups are measurement units, not validated persons or privacy adjacency
units. Existing dataset provenance and preprocessing limitations remain; Diabetes
retains its existing full-cohort bundled preprocessing. Reused public data does
not become a fresh holdout, and catalog-only research datasets are not tested.

The comparison plan is retained before execution, binding source/runtime/input
hashes, the exact group roster, three stratified half train/test splits with seeds
`20261006`, `20261007`, `20261008`, all parameters, required controls and stopping
rule. Every repeat is retained. Repeats overlap and are not pooled as independent
trials, confidence intervals or significance evidence. Native loss AUC is computed
on the exact same held-out ART groups; the original native metric remains distinct.

## Controls, replay and execution limits

The positive fixture assigns member loss zero and nonmember loss one. The null
assigns loss one to every group. Both pass through the actual ART learner's fit,
scaling and inference for all three splits. Every positive raw AUC must be at
least 0.9 and each null raw AUC must be 0.5 within numerical tolerance. Constant
null probabilities can sit above or below 0.5; the report retains actual counts
at the fixed strict `score > 0.5` threshold. These controls validate the learner
path, not a realistic fitted control model or the target's privacy.

ART casts losses to float32. The adapter rejects nonfinite/bounded conversion
failures, retains the exact converted features and independently replays scaler
parameters, class order, fitted logistic coefficients and membership scores.
Tie-aware raw AUC and confusion counts are independently recomputed. Score,
split, parameter, metric, runtime, control or artifact drift rejects completion.
A chance target AUC does not clear privacy risk. No population confidence,
low-FPR certificate, privacy ceiling or release authority is claimed.

The Windows child process has an owned job and bounded deadline/output capture.
Separate dependencies and process ownership do not establish hostile-code,
network/filesystem isolation or verified CPU/memory quotas. Retained hashes and
numeric replay are local consistency evidence; `external_execution_attested` and
`assessment_eligible` stay false. This path is separate from the older two-tool
typed assessment catalog, the 25-entry console discovery catalog and PRD-14 SACRO
contracts. No earlier assessment gate is widened and no blocker is closed.

## Run and inspect

From this D: government checkout, prepare the declared runtime in a new ignored
`.local` directory using the hash requirements, then pass its Python executable:

```powershell
& .\.venv-pipeline\Scripts\python.exe -B scripts/rehearse_art_adapter.py --python .local/verification/prd25-art-20261006/art-env/Scripts/python.exe --output .local/art-v1
```

`--benchmark` selects an eligible captured PRD-13 case roster under this
repository's `.local`. `--data-root` defaults to `D:/model_audit_data` and is
read-only. Output must be a fresh ignored `.local` directory. All eight profiles
must have explicit dispositions; inspect controls, numeric replay and process
cleanup for each, not only the command's exit status.

## Local validation and remaining acceptance

The source checkout and a fresh installed application wheel each completed all
eight real ART profiles, with 72 target/positive/null repetitions per batch. All
controls and independent score/process/artifact replay passed; source and original
input artifacts remained unchanged. The 35 dependency wheels were installed
offline with required hashes, and all 197 packaged files matched frozen source
bytes. The pinned sklearn/SciPy combination emits an `iprint` solver-option
warning; convergence warnings remain failures. This observed compatibility detail
is retained in worker logs and remains part of independent dependency acceptance.

The required government profile passed **2,056 tests across 115 modules**, with
zero failures, errors, skips, expected failures or unexpected successes. Its 467
source hashes still match the final implementation. The new ART suites contribute
147 tests. Schema verification retained all 37 existing bindings, and local links
in 73 Markdown files passed. All 942 prior tracked files outside the six intended
documentation/required-runner updates remain byte-identical, including the frozen
advisory and earlier implementation.

Receipts are retained separately under
`.local/verification/prd25-art-20261006/`; earlier source-bound receipts remain
unchanged and must be replayed using their original source versions.

Observed means of the three overlapping held-out comparisons are descriptive
only; values below 0.5 retain their original direction. No result clears privacy.

| Profile | ART raw AUC mean | Paired native loss raw AUC mean |
| --- | --- | --- |
| acs | 0.488186 | 0.511287 |
| bts | 0.492142 | 0.491258 |
| hmda | 0.504285 | 0.506550 |
| tlc | 0.503078 | 0.496922 |
| sklearn-breast-cancer | 0.482230 | 0.486720 |
| sklearn-wine | 0.525084 | 0.538047 |
| sklearn-digits | 0.531880 | 0.529049 |
| sklearn-diabetes | 0.502512 | 0.502512 |

Scientific acceptance still requires an approved adversary/interface, realistic
end-to-end control targets, valid attack-specific perturbations, cohort and
privacy-unit justification, dependency/security/license review and independent
agency acceptance. Additional regression families, extraction, evasion, poisoning,
attribute inference and live interfaces each need separate acceptance. The public
retained-loss comparison alone does not complete PRD-25 production qualification.

The next local phase is **PRD-26**: scoped garak then PyRIT profiles for selected
LLM/RAG/agent interfaces, with validated scorers and approved sandbox/egress.
