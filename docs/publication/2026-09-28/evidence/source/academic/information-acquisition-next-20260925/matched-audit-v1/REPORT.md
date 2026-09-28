# Equally optimized reuse and fresh acquisition on later cohorts

All three corpora completed five independent mechanism replicates per policy. The fixed training roster contains 8,000 source records; every six-event export history has a sufficient epsilon bound at most 1. Logistic regression fits the same six-C grid on the same six bootstrap schedules in both policies. C and shrinkage are selected from the whole six-event ensemble using public auxiliary data, with no later-cohort selection. The selection procedure was fixed before all runs; each policy's choices are frozen before its evaluation labels are loaded. Labels are read after each frozen policy, rather than literally once after all ten histories, and the fixed control flow does not adapt subsequent fits to those results.

The reserved later cohorts are HMDA 2024, TLC January–July 2026 and BTS 2025 (50,000 records each). They are disjoint from all previously prepared auxiliary, training, certification and final records. Existing public semantic schemas are unchanged. Model training uses 8,000 records, not the complete source volume. These are finite-cohort temporal stress tests, not population or operational authorization certificates.

## Primary comparison: full six-event LR ensemble

Utility is the minimum across three tasks of balanced-Brier utility. Constant probability 0.5 scores 0.75. The replicate is a new set of randomized channels; model fits and records are not counted as independent replications. Intervals use a small-sample paired t approximation (4 df), conditional on the fixed training/evaluation cohorts; they are not simultaneous or population intervals.

| Corpus | Reuse mean | Fresh mean | Fresh minus reuse | Conditional 95% t interval |
|---|---:|---:|---:|---:|
| hmda | 0.770344 | 0.757503 | -0.012840 | [-0.024215, -0.001465] |
| tlc | 0.750619 | 0.750716 | +0.000096 | [-0.001349, +0.001542] |
| bts | 0.747143 | 0.743387 | -0.003756 | [-0.008809, +0.001297] |

## All fixed controls and public-auxiliary choices

Corrected ridge inverts the known categorical-RR channel for sufficient statistics, replaces within-category Gram blocks by diagonal first moments, and averages fresh observations of the same 8,000 records. Its empirical Gram can be indefinite; PSD projection and ridge stabilize fitting and are not claimed unbiased. All 5 ridge penalties and fixed shrinkage are selected from public auxiliary records. This is a mechanism-aware control, not a novel or optimal estimator.

The public-only LR uses 8,000 separate public auxiliary records. B-only uses the same private training roster but only fields fixed by the adjacency. Both controls have zero incremental privacy expenditure under this conditional adjacency. The per-task method chooser may select these controls or constant; a selected control must not be described as useful protected information.

| Corpus | Method | Reuse mean minimum | Fresh mean minimum | Fresh minus reuse |
|---|---|---:|---:|---:|
| hmda | B_only | 0.754283 | 0.754283 | +0.000000 |
| hmda | all36_lr | 0.768982 | 0.756304 | -0.012678 |
| hmda | aux_selected_method | 0.823885 | 0.823885 | +0.000000 |
| hmda | constant | 0.750000 | 0.750000 | +0.000000 |
| hmda | corrected_ridge | 0.750731 | 0.750000 | -0.000731 |
| hmda | matched_lr | 0.770344 | 0.757503 | -0.012840 |
| hmda | public_only | 0.823885 | 0.823885 | +0.000000 |
| tlc | B_only | 0.751528 | 0.751528 | +0.000000 |
| tlc | all36_lr | 0.750661 | 0.750616 | -0.000045 |
| tlc | aux_selected_method | 0.765618 | 0.765618 | +0.000000 |
| tlc | constant | 0.750000 | 0.750000 | +0.000000 |
| tlc | corrected_ridge | 0.750000 | 0.750000 | +0.000000 |
| tlc | matched_lr | 0.750619 | 0.750716 | +0.000096 |
| tlc | public_only | 0.765618 | 0.765618 | +0.000000 |
| bts | B_only | 0.747314 | 0.747314 | +0.000000 |
| bts | all36_lr | 0.747908 | 0.746794 | -0.001114 |
| bts | aux_selected_method | 0.751139 | 0.751139 | +0.000000 |
| bts | constant | 0.750000 | 0.750000 | +0.000000 |
| bts | corrected_ridge | 0.750000 | 0.750000 | +0.000000 |
| bts | matched_lr | 0.747143 | 0.743387 | -0.003756 |
| bts | public_only | 0.751139 | 0.751139 | +0.000000 |

## Complete accounting and evidence limits

A per-policy cap 1 is not the bound for releasing every experimental artifact together. Five reuse histories plus five fresh histories cost approximately 10 additional epsilon on their overlapping source records. Earlier finite-bound histories and the original privatized cache remain charged (approximately 20), making the retained finite-bound experiment account approximately 30. Raw diagnostic exports cannot be included in that finite bound. OS random-byte quality, independent draws and trusted execution remain assumptions; deterministic checks do not cryptographically verify them.

All serialized weights, corrected-ridge coefficients and deterministic recipes are exported without raw training records, private caches or row keys. Standalone recipient processes exactly reproduced every reported probability. The independent reader verified artifact/cache bindings, all five replicate pairs, matched search counts, finite-cohort metrics and exact Decimal accounting against the complete history. No generic model-weight optimality, information-impossibility theorem or production security result follows.

An export metadata defect was found in self-review: the original fresh-history preprocessing file inherited the prior epsilon1 allocation, although executed channels, saved ledgers and moment correction correctly used epsilon1/6 per fresh cache. Original artifacts remain preserved. New metadata-correction-v1 packages contain exactly the same weights and recipes, corrected training-channel metadata and independently replayed identical probabilities. No fits, draws, privacy charges or numerical results changed. The audit requires all 30 correction receipts and checks equal weight/prediction hashes and the corrected allocation.

Only five channel replicates are available; intervals describe mechanism variation conditional on fixed cohorts. They omit source-sampling uncertainty and do not account for the broader research programme's historical adaptive questions. The benchmark's protected-field adjacency fixes labels, B, participation and roster and is record-level. Source fields' operational as-of availability remains unverified.

## Provenance

Total new target fits: 3798. All source results and per-replicate/task comparisons are in audit.json.

- hmda: result SHA256 `e3c28aadbbdb96e663c521388999294ccb8e9a4026c85ee5089aad2ce180eb90`; scanned 12,229,298 reserved-source rows; target fits 1266; complete finite-bound account30.
- tlc: result SHA256 `dcbef7e653a083d70536e743e8032558c3616c89b6280bdfffb49e3cd84996f4`; scanned 147,693,231 reserved-source rows; target fits 1266; complete finite-bound account30.
- bts: result SHA256 `8fa3004677b7d3a0adc6f373c39b6fced4af339c1a52a189d868304fa0b29285`; scanned 7,001,619 reserved-source rows; target fits 1266; complete finite-bound account30.
