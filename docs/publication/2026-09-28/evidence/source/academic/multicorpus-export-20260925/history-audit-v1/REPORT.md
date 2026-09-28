# Audit of six-event model export histories

All three completed runs were audited without retraining. Each corpus contributes 49 model bundles and 147 logistic-regression target fits; each fit uses 8,000 records. Each model is measured on the previously inspected 50,000-record final cohort. These measurements are exploratory; they are not a new independent validation study or a confidence certificate.

The matched comparison fixes the complete six-export history allowance at 1. Reuse sanitizes each record once at vector allowance 1. Fresh same-record and shared-core histories spend at most 1/6 per event; fresh disjoint histories spend 1 per record. The 50% schedule has one common core shared by every pair of events, not an adjacent-period overlap assumption.

## Matched-history-cap results

Entries are balanced-Brier utilities averaged over the six actual export events, in each corpus's task order. Constant probability 0.5 gives 0.75. The minimum column averages the minimum of the three task utilities at each event; it is not a pass/fail threshold.

| Corpus | Record schedule | Policy | Vector allowance | Task 1 | Task 2 | Task 3 | Mean minimum |
|---|---|---|---:|---:|---:|---:|---:|
| HMDA | same | reuse | 1 | 0.783287 | 0.784664 | 0.799606 | 0.783287 |
| HMDA | same | fresh | 0.166667 | 0.773979 | 0.781529 | 0.767478 | 0.766193 |
| HMDA | half overlap | reuse | 1 | 0.775783 | 0.783892 | 0.775036 | 0.771764 |
| HMDA | half overlap | fresh | 0.166667 | 0.768907 | 0.784877 | 0.758402 | 0.757995 |
| HMDA | disjoint | reuse | 1 | 0.778434 | 0.789830 | 0.792149 | 0.777340 |
| HMDA | disjoint | fresh | 1 | 0.779811 | 0.784531 | 0.781905 | 0.775815 |
| TLC | same | reuse | 1 | 0.753233 | 0.748809 | 0.752700 | 0.748809 |
| TLC | same | fresh | 0.166667 | 0.750080 | 0.745602 | 0.749437 | 0.745181 |
| TLC | half overlap | reuse | 1 | 0.753376 | 0.750321 | 0.752904 | 0.749438 |
| TLC | half overlap | fresh | 0.166667 | 0.746587 | 0.752079 | 0.749051 | 0.743849 |
| TLC | disjoint | reuse | 1 | 0.748423 | 0.747496 | 0.746949 | 0.744420 |
| TLC | disjoint | fresh | 1 | 0.748401 | 0.746933 | 0.742079 | 0.739684 |
| BTS | same | reuse | 1 | 0.758649 | 0.754557 | 0.632026 | 0.632026 |
| BTS | same | fresh | 0.166667 | 0.759738 | 0.751990 | 0.625670 | 0.625670 |
| BTS | half overlap | reuse | 1 | 0.757726 | 0.752809 | 0.632790 | 0.632790 |
| BTS | half overlap | fresh | 0.166667 | 0.757262 | 0.753074 | 0.621532 | 0.621532 |
| BTS | disjoint | reuse | 1 | 0.757415 | 0.752639 | 0.630614 | 0.630614 |
| BTS | disjoint | fresh | 1 | 0.757523 | 0.753992 | 0.631193 | 0.631193 |

Task order:

- **HMDA:** origination, denial, withdrawal_or_incompleteness.
- **TLC:** duration_over_30min, distance_over_10miles, base_fare_over_50.
- **BTS:** departure_disruption, arrival_disruption, cancellation.

## Combining retained model exports

A post-hoc descriptive control fixes equal weights before computing the new ensemble metrics. For each task, the recipient averages probability outputs from all models actually exported so far. Every prefix is retained in `audit.json`; the table shows the final six-model prefix. No weights, subsets, or stopping prefix are chosen using the final cohort, and no model is retrained. This is a feasible recipient use of retained model weights, not a best-possible utility or inference attack.

| Corpus | Record schedule | Policy | Ensemble task 1 | Ensemble task 2 | Ensemble task 3 | Ensemble minimum | Latest-model minimum | Mean event minimum |
|---|---|---|---:|---:|---:|---:|---:|---:|
| HMDA | same | reuse | 0.783287 | 0.784664 | 0.799606 | 0.783287 | 0.783287 | 0.783287 |
| HMDA | same | fresh | 0.775104 | 0.783298 | 0.769188 | 0.769188 | 0.770911 | 0.766193 |
| HMDA | half overlap | reuse | 0.777000 | 0.785847 | 0.777140 | 0.777000 | 0.776420 | 0.771764 |
| HMDA | half overlap | fresh | 0.771075 | 0.788095 | 0.761340 | 0.761340 | 0.769047 | 0.757995 |
| HMDA | disjoint | reuse | 0.780799 | 0.794098 | 0.796200 | 0.780799 | 0.780749 | 0.777340 |
| HMDA | disjoint | fresh | 0.782319 | 0.788900 | 0.785990 | 0.782319 | 0.777152 | 0.775815 |
| TLC | same | reuse | 0.753233 | 0.748809 | 0.752700 | 0.748809 | 0.748809 | 0.748809 |
| TLC | same | fresh | 0.753048 | 0.748819 | 0.754369 | 0.748819 | 0.753304 | 0.745181 |
| TLC | half overlap | reuse | 0.755480 | 0.753382 | 0.756362 | 0.753382 | 0.753411 | 0.749438 |
| TLC | half overlap | fresh | 0.751183 | 0.756834 | 0.757767 | 0.751183 | 0.747996 | 0.743849 |
| TLC | disjoint | reuse | 0.752546 | 0.753124 | 0.754701 | 0.752546 | 0.744070 | 0.744420 |
| TLC | disjoint | fresh | 0.752973 | 0.752761 | 0.754568 | 0.752761 | 0.745126 | 0.739684 |
| BTS | same | reuse | 0.758649 | 0.754557 | 0.632026 | 0.632026 | 0.632026 | 0.632026 |
| BTS | same | fresh | 0.765537 | 0.758637 | 0.671265 | 0.671265 | 0.617624 | 0.625670 |
| BTS | half overlap | reuse | 0.763071 | 0.757757 | 0.668361 | 0.668361 | 0.628380 | 0.632790 |
| BTS | half overlap | fresh | 0.765008 | 0.760190 | 0.676158 | 0.676158 | 0.616483 | 0.621532 |
| BTS | disjoint | reuse | 0.767170 | 0.762632 | 0.688268 | 0.688268 | 0.639361 | 0.630614 |
| BTS | disjoint | fresh | 0.767768 | 0.763503 | 0.691360 | 0.691360 | 0.641293 | 0.631193 |

Averaging already released predictions adds no training-record privacy charge. For the Brier score, an equally weighted ensemble is mathematically at least as good as the mean individual-model utility because squared loss is convex; that inequality is established mathematics, not a new empirical discovery. Improvement over the latest model is a separate, descriptive comparison. The ensemble uses the same already inspected final cohort and does not restore independent validation.

## Actual and shadow admissions

For fixed per-object quality (vector allowance 1), the actual six-event histories used cap 6. Reuse and disjoint fresh histories have record-level cost 1; fresh same-record/shared-core histories have cost 6. Smaller-cap replay admits 1, 2, 3 or 6 fresh overlapping events at caps 1, 2, 3 or 6, respectively; all six reuse/disjoint events remain admissible. These smaller-cap replays are accounting-only comparisons, with quality measured from the cap-6 artifacts.

A separate actual cap-1 fresh same-record control generated and exported its first event, then refused all five subsequent requests before generating a new cache or fitting a model. The audit checked refusal records, absence of generated caches, and the retained charge. This is bounded implementation evidence, not untrusted-host enforcement.

## Complete experiment costs and scope

The maximum per-record charge across **all newly executed policy worlds together is approximately 19**, not 1 or 6. Adding the original POC private cache gives approximately 20. Exact outward-rounded values are in `audit.json`. This combined finite bound excludes original raw-diagnostic exports and all other earlier experiments; it is not a blanket bound for the repository's entire research history.

The guarantee concerns replacement of the designated groups of one fixed source record. Public context, labels, membership and participation remain fixed. Opaque source-position keys do not establish person identity across records or time. A larger cohort is not a larger per-fit training set.

Reuse reduces repeated expenditure by construction, and the runs test the resulting exported models' utility. Higher utility for reuse is not guaranteed: it preserves one realized perturbation, whereas fresh histories vary the perturbation and, under a matched cap, divide the allowance. There is one noise realization per newly generated cache and one seed per fit; the six events do not provide six independent validation datasets or a population-level confidence interval.

## Audit coverage

The independent audit reconstructed key-based overlap, exact Decimal privacy sums, complete artifact dependencies, cache and model-file hashes, actual refusal counts, and all 441 saved task-utility values from recipient predictions. Producer logs report separate-process reload equality; this audit validates those artifacts and saved predictions but does not rerun recipient inference or prove the model was trained only from declared inputs. No files in completed experiment directories were changed.
