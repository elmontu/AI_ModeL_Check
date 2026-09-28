# Strong reuse of previously privatized training records

Status: all three corpora complete. All results below are descriptive on previously inspected final records.

Each new model uses the same 8,000 training records and exact epsilon-1 cache as the original same-record reuse history. Raw protected training attributes were not loaded. No new randomization was performed. Auxiliary-only regularization, calibration and shrinkage use the declared public auxiliary panel, outside the protected training-record adjacency.

## Minimum balanced-Brier utility across three tasks

A constant probability of 0.5 scores 0.75. Values below 0.75 fail that reference for at least one task. The minimum can refer to different tasks; per-task values are retained in JSON.

| Fixed arm | HMDA | TLC | BTS |
|---|---:|---:|---:|
| constant | 0.750000 | 0.750000 | 0.750000 |
| bootstrap_ensemble | 0.783774 | 0.748135 | 0.611833 |
| regularization_ensemble | 0.779698 | 0.750750 | 0.687171 |
| heterogeneous_ensemble | 0.781071 | 0.742332 | 0.682005 |
| all18_ensemble | 0.783898 | 0.749577 | 0.669113 |
| omit-lr | 0.755419 | 0.749863 | 0.696290 |
| omit-hgb | 0.742864 | 0.706967 | 0.535160 |
| aux_selected_regularization | 0.782407 | 0.751516 | 0.747714 |
| aux_selected_shrinkage | 0.782407 | 0.751516 | 0.750000 |
| aux_selected_calibration | 0.785351 | 0.751517 | 0.749865 |
| historical_reuse_six | 0.783287 | 0.748809 | 0.632026 |
| historical_fresh_six | 0.769188 | 0.748819 | 0.671265 |

## Interpretation and limits

The hypothesis under test is whether fresh access improves utility beyond substantially stronger learning from the already available object. A successful reuse arm refutes necessity for that observed performance comparison; its failure does not establish information insufficiency. None of these finite learners is an optimal reuse oracle. All registered arms are reported; the final cohort does not select an arm.

There are 60 target fits and three public auxiliary calibrator fits per corpus. Every reported new arm is a deterministic recipe over exported estimators, replayed exactly in a separate recipient process. Export packages contain no training cache or row keys. This checks a bounded packaging and replay property, not security against a malicious host.

All new fits have zero incremental privacy charge as postprocessing of the same verified randomized object and fixed nonprotected fields. Their standalone shared dependency has epsilon approximately 1. The actual retained experimental record includes all older finite-bound histories (approximately 19) plus the original finite-bound cache (approximately 20 total); those charges are not erased. Unbounded raw diagnostic artifacts remain outside every finite-bound joint-release claim.

One cached randomization and one bootstrap schedule are used per corpus. No new held-out cohort, privacy-feasibility theorem, optimal acquisition rule, agency validation or population-wide guarantee is established. Public auxiliary calibration may exploit cohort-specific effects and must be repeated on genuinely untouched later cohorts. Native categorical HGB and one-hot tree learners are bounded controls; channel-aware loss correction remains untested.

## Provenance

Plan: `<REPOSITORY>\academic\information-acquisition-20260925\strong-reuse-plan.json`; SHA256 `c5e8d51059072de5deca526d9c0a6137cf447d7647689918c152e5ec9f970d06`.

- hmda: cache `08d71b8a6e2294d6aab05a3562fae76ce720bd54fff3c145fad72bd6e2ec8c49`; manifest `436d63b3a892701e2081fbc8818cc8bf4adcb0735fb719717b3e18fa3b1c890f`; replay exact; final rows 50000; target fits 60.
- tlc: cache `507e452c7f3ad5261b095a1d437b0e4c6f001f8fb8db9cd3e78dead898fcdc91`; manifest `c2ffc97fdab8bbcdcb5a0dd1ad46b38c0c7f97340b273ef280245c3013cea61a`; replay exact; final rows 50000; target fits 60.
- bts: cache `7285dc1ee530efae252e8c9d6410d936191afd361d7f096291f645c62fe91ac2`; manifest `2bb9375dcc078a9e537855532394f4fe820023c9cc22f276c259918436a72a60`; replay exact; final rows 50000; target fits 60.
