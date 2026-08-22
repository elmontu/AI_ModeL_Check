# Local XGBoost audit worker

The local XGBoost worker trains and audits a classification pipeline from a trusted CSV or Parquet file. It runs outside the trusted `model_release_assurance` package because model training and `joblib` deserialization are executable operations.

The worker produces:

- independently preprocessed target and reference `XGBClassifier` models;
- utility metrics on a disjoint test split;
- exact leaf-signature structural metrics for both training sets;
- a calibrated reference-loss membership attack with retained raw counts and scores;
- hash-bound split, model, preprocessing, histogram, release-artifact, and run manifests.

An empirical attack can establish a lower bound and block a release. A failed or inconclusive attack cannot clear one. The worker therefore emits only `floor` or `screen` semantics and always records `can_clear: false`.

## Evidence basis

The [privacy-assurance literature review](literature-review.md#tree-ensembles-and-xgboost) documents the primary research behind this design. Loss-threshold and reference-model membership attacks are well grounded in the broader literature, but direct peer-reviewed evidence for modern released XGBoost/GBDT artifacts is substantially thinner than for neural classifiers. The implemented procedure is therefore a **reference-loss membership screen**, not full LiRA and not a complete XGBoost privacy audit.

Interpret results conservatively. The implemented probability-and-true-label attack is realizable by a full-artifact recipient, but it does not inspect white-box tree internals and is not a full-artifact privacy audit. A successful attack establishes leakage only under the registered split, observation, reference-data assumptions, and operating point. An unsuccessful attack does not bound stronger attacks or other recipients. Version 1.1 adds deployment-prior PPV, experiment-wide confidence correction across every registered replicate, low-FPR sample-support diagnostics, and descriptive score/class tails. The descriptive tails are noninferential. Future evidence still needs preregistered subgroup inference, reference-distribution mismatch, stronger multi-reference likelihood-ratio attacks, and separate profiles for label-only APIs, score APIs, explanation endpoints, and white-box full-artifact attacks.

## Install

Python 3.11 or newer is required.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[experiments]'
```

On Windows PowerShell, activate with `.venv\Scripts\Activate.ps1`.

## Configure

Copy [`reproduction/xgboost/config.example.json`](../reproduction/xgboost/config.example.json) and set:

- `dataset.path`: CSV or Parquet path, relative to the configuration file or absolute;
- `dataset.sha256`: lowercase SHA-256 of the exact dataset bytes;
- `dataset.target_column`: classification target;
- seeds, row cap, split fractions, model capacity, and attack operating point;
- `attack.membership_priors`: deployment membership base rates used for point and conservative PPV;
- `decision_game`: the immutable record-level game, threat-contract hash, candidate sampling, reference-data relationship, attacker observation, and recipient access. Replace the example game/scope IDs and all-zero threat-contract digest; placeholders are rejected. The candidate population, sampling, and reference relationship strings are canonical worker-controlled values and must not be edited.

Compute the dataset hash on PowerShell with:

```powershell
(Get-FileHash -Algorithm SHA256 .\data\classification.parquet).Hash.ToLowerInvariant()
```

The runner accepts only configuration schema `1.1` and rejects unknown XGBoost parameters, placeholders, or weakened game fields. It controls the objective, evaluation metric, CPU device, histogram tree method, single-worker execution, random seeds, true-label probability observation, split construction, reference relationship, threshold-selection rule, and recipient-access profile so a configuration cannot silently change those audit assumptions.

Each selected target class needs at least ten rows for the stratified five-way split.

## Run

```bash
python scripts/run_xgboost_audit.py \
  --config reproduction/xgboost/config.json \
  --output-dir output/xgboost
```

Use `--force` to retrain even when a complete cache entry has the same canonical configuration, dataset hash, implementation hashes, runtime versions, and valid artifact hashes. Cache reuse also replays the attack from retained raw scores and compares decision-critical results and provenance fields with the hash-checked `audit-evidence.json`; editing a cached conclusion, model parameter record, protected unit, or group count therefore causes recomputation. This is corruption detection, not authenticity—a signed framework envelope is still required for production evidence.

The summary is written to `output/xgboost/xgboost-audit-summary.json`. Each seed gets a deterministic `release-bundle.zip` containing the target UBJ model, target preprocessing, and an inert `release-artifact.json` manifest. Use the ZIP path and hash as `ReleaseContract.artifact_path` and `ReleaseContract.artifact_sha256`; this binds the actual deployable pipeline bytes rather than only a manifest that points to them. Dataset, audit-configuration, implementation, and runtime fingerprints remain in internal evidence and are omitted from the recipient bundle by default.

## Statistical interpretation

The threshold is selected only from the disjoint nonmember-calibration split. All equalized target-training members are then used to estimate audit TPR; no members are discarded for an unused calibration step. The audit FPR comes from a second disjoint nonmember split.

For family confidence (1-\alpha), (r) registered replicate seeds, and the TPR-lower/FPR-upper pair in each replicate, every bound uses Bonferroni confidence (1-\alpha/(2r)). The summary reports every registered seed and prohibits uncorrected best-seed selection. A floor exists only when the simultaneous FPR upper bound is no greater than the preregistered target. Otherwise the result is a screen, even when observed FPR is small or zero.

For each registered membership prior \(\pi\), the worker reports point PPV and the conservative simultaneous lower bound

```text
pi * TPR_lower / (pi * TPR_lower + (1 - pi) * FPR_upper)
```

PPV characterizes the registered operating point under that base rate; it is not a privacy ceiling.
When the audit produces no positive predictions, point PPV is undefined and is emitted as `null` with `estimate_status: undefined_no_positive_predictions`; it is not reported as zero. The simultaneous conservative lower bound remains available.

The field `certified_tpr_floor_at_controlled_fpr` is specifically the simultaneous TPR lower bound after the FPR upper bound attains the target. It is not automatically evidence of advantage over guessing. The worker separately reports `simultaneous_membership_advantage_lower_bound = max(0, TPR_lower - FPR_upper)`.

## Security boundary

- Treat the input dataset and output directory as sensitive.
- Load `joblib` only in an isolated, trusted worker and only after verifying its recorded hash.
- Do not extract or load the release ZIP, UBJ, or `joblib` files in the MRA decision core.
- The generated release artifact is not a complete assessment request. Interface, recipient, population, policy, portfolio, and decision-game bindings still need explicit contracts and independently validated evidence.
- Version 0.6 resolves the core evidence-context provenance finding, but this worker remains a screen and the repository still lacks production trust infrastructure; do not use it as a production authorization gate.
