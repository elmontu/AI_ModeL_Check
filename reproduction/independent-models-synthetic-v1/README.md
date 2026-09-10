# Independent synthetic model study, September 9, 2026

This study completed **168 independently trained models**: 84 logistic models
and 84 depth-2 trees, each fitted to a fresh sample of 256 synthetic examples.
Four secret/task relationships and three randomized-response controls are
paired evaluations within each model, yielding 2,016 candidate rows. They are
not 2,016 independently trained models. All planned fits completed.

The [registration](registration.json), runner and separately implemented verifier
were hash-frozen locally before the fits. This is not an externally timestamped
preregistration. The original registration retains its prospective status text;
the local completion manifest, `output/independent-models-synthetic-v1-20260909/COMPLETE.json`,
records completion separately. No historical experiment or registration was rewritten.

The [paper section](../../academic/paper/independent-model-study.tex) reports
the assumptions and adverse results. The
[machine-readable companion](../../academic/paper/independent-model-study-data.json)
includes the registration, all model-level candidate/selection records, group
aggregates, primary confidence intervals and source digests. Original model
artifacts, training draws and evaluation draws remain in the named local
`output/independent-models-synthetic-v1-20260909` directory. Public access to
that directory is not asserted; shipping the companion does not ship the draws.

The simultaneous-bound rule made no observed invalid selections, but missed
all 50 oracle-feasible logistic cases and 67 of 68 oracle-feasible tree cases
in the boundary-stress context. The point comparator made three privacy-invalid
logistic selections and utility-invalid selections for six tree models. Those
same six tree models fail in three paired contexts; this is not 18 independent
failures. Always-refuse made no useful selections. The study supports neither
uniform decision usefulness nor general superiority of the bound rule.

The exact oracle concerns a single released label in a 36-input synthetic
attribute-inference world. It does not assess membership privacy, adaptive or
joint disclosures, larger architectures, real populations or a deployed endpoint.
Model-level intervals have halfwidth 0.20 before clipping; zero observed invalid
selections is compatible with positive failure probability.

The retained local verification receipt, `output/independent-models-synthetic-v1-20260909/VERIFIED.json`,
records replay of all 168 model records, 2,016 candidate rows and 16 primary
intervals. The verifier reconstructs predictions from saved model parameters,
recounts observations and enumerates the joint oracle without importing the
runner. It does not refit models or constitute external scientific validation.

With an existing compatible Python and NumPy environment and the retained local
source directory, check the published table and companion from the repository
root without fitting models. This command requires the original ignored
`output/independent-models-synthetic-v1-20260909` directory; a fresh clone alone
does not contain the inputs needed for this replay:

```powershell
python academic/scripts/build_independent_study_companion.py output/independent-models-synthetic-v1-20260909 --check
```

For a full replay of retained model artifacts and draws, choose a fresh receipt
path. The verifier refuses to overwrite an existing receipt:

```powershell
python academic/scripts/verify_independent_model_study.py output/independent-models-synthetic-v1-20260909 --receipt output/independent-study-recheck.json
```

This replay requires the local source directory and the unchanged frozen
verifier. A changed method or a new training run needs a separately identified
study and retained evidence. Do not overwrite or resume the completed run.

The six algebra/freeze regression checks and separate lifecycle tests can be
run through `python academic/scripts/verify_review_revision.py`. That command
does not perform model training and creates a fresh timestamped receipt.
