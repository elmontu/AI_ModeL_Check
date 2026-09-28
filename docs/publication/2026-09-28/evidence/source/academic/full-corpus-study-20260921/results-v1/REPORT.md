# Full-corpus ACS model and release study

Status: **complete**. This report describes observed artifacts only.

The verified preparation manifest records 62,469,664 original rows and 44,567,449,884 bytes (44.57 GB), of which 24,454,622 adult-householder records were eligible. Completed target fits: **120/120**. The planned chronological history has 40 distinct models per arm, with raw, omitted and RR arms matched by period and family.

| Period | Eligible records | Training pool | Original rows |
| --- | --- | --- | --- |
| 2009 | 5,871,886 | 4,109,183 | 14874168 |
| 2014 | 6,044,283 | 4,232,006 | 15552144 |
| 2019 | 6,235,579 | 4,364,549 | 15947624 |
| 2024 | 6,302,874 | 4,412,237 | 16095728 |

The union of the training pools contains 17,117,975 release-qualified records, projected into eight public categorical fields. These pools are partitioned into registered D1/D2 rosters. The exact per-fit row counts below establish actual use; the original CSV storage size is not the size of a dense training feature matrix or a per-fit sample count.

Completed fit time totals 0.57 hours; query time 0.17 hours. These are summed measured phases, not total end-to-end wall time. Exported model files total 1.690 GB. 12 completed fits have recorded warnings.

## Utility

Utility uses 20,000 disjoint held-out records, divided by test period. The following comparison includes 40 completed period/family cells common to the 5 reportable variants. Budgeted scoring status: `corrected_v2_channels`.

Equal mean of per-model, per-test-period AUC over the common completed period/family cells; every variant uses the same utility records.

| Variant | Matched mean ROC AUC |
| --- | --- |
| Raw diagnostic | 0.84767 |
| Omitted | 0.83830 |
| RR cached | 0.83954 |
| RR fresh | 0.83947 |
| RR budgeted | 0.83616 |

| Paired contrast | AUC difference | Pointwise 95% interval |
| --- | --- | --- |
| Omitted minus Raw diagnostic | -0.00937 | [-0.01091, -0.00783] |
| RR cached minus Raw diagnostic | -0.00813 | [-0.00954, -0.00672] |
| RR fresh minus Raw diagnostic | -0.00820 | [-0.00948, -0.00692] |
| RR budgeted minus Raw diagnostic | -0.01151 | [-0.01305, -0.00997] |
| RR fresh minus RR cached | -0.00007 | [-0.00070, 0.00056] |
| RR budgeted minus RR cached | -0.00338 | [-0.00408, -0.00268] |

Pointwise normal 95% intervals from paired, tie-aware AUC structural components, averaged across fixed fitted models and stratified by test period. Uses a within-period, class-stratified IID-record approximation conditional on the fitted models, frozen RR draws and fixed corpus split; excludes training-seed/model-selection/source-population uncertainty, finite-population correction and multiple-comparison adjustment. No equivalence claim.

Per-model, per-test-period AUC, accuracy and log loss are retained in `results.json`.

## Release histories and attribute attacks

Replay status: **complete**. Observed finite-epsilon decisions: 840/840; admitted 626, denied 214. Diagnostic raw/omitted evaluations are separate from these decisions.

| Scenario | Attempted | Admitted | Denied | Test model-query AUC | Test linked-score AUC |
| --- | --- | --- | --- | --- | --- |
| rr-cached-cap-1 | 40 | 40 | 0 | 0.766 | 0.842 |
| rr-cached-cap-2 | 40 | 40 | 0 | 0.766 | 0.842 |
| rr-cached-cap-4 | 40 | 40 | 0 | 0.766 | 0.842 |
| rr-cached-cap-8 | 40 | 40 | 0 | 0.766 | 0.842 |
| rr-cached-cap-16 | 40 | 40 | 0 | 0.766 | 0.842 |
| rr-cached-cap-32 | 40 | 40 | 0 | 0.766 | 0.842 |
| rr-cached-cap-64 | 40 | 40 | 0 | 0.766 | 0.842 |
| rr-fresh-cap-1 | 40 | 1 | 39 | 0.763 | 0.832 |
| rr-fresh-cap-2 | 40 | 1 | 39 | 0.766 | 0.839 |
| rr-fresh-cap-4 | 40 | 3 | 37 | 0.766 | 0.912 |
| rr-fresh-cap-8 | 40 | 7 | 33 | 0.766 | 0.975 |
| rr-fresh-cap-16 | 40 | 15 | 25 | 0.766 | 0.997 |
| rr-fresh-cap-32 | 40 | 31 | 9 | 0.766 | 1.000 |
| rr-fresh-cap-64 | 40 | 40 | 0 | 0.766 | 1.000 |
| rr-budgeted-cap-1 | 40 | 8 | 32 | 0.763 | 0.764 |
| rr-budgeted-cap-2 | 40 | 40 | 0 | 0.766 | 0.766 |
| rr-budgeted-cap-4 | 40 | 40 | 0 | 0.766 | 0.766 |
| rr-budgeted-cap-8 | 40 | 40 | 0 | 0.766 | 0.766 |
| rr-budgeted-cap-16 | 40 | 40 | 0 | 0.766 | 0.766 |
| rr-budgeted-cap-32 | 40 | 40 | 0 | 0.766 | 0.766 |
| rr-budgeted-cap-64 | 40 | 40 | 0 | 0.766 | 0.766 |

The accounting universe contains 17,153,975 release-qualified records; the attacker panel contains 44,000 records. The replay took 0.36 hours. Admission counts above come from actual gate decisions, not theoretical composition alone.

Attack summaries use calibration-selected retained prefixes. `fixed_current_prefix_groups` in the result JSON separately reports the latest fitted prefix. Test labels are used for final measurement, not attack fitting or prefix selection.

| Diagnostic/baseline | Attack interface | Test records | Balanced accuracy | ROC AUC |
| --- | --- | --- | --- | --- |
| no-model baseline | model_queries_only | 8000 | 0.700 | 0.763 |
| no-model baseline | linked_score_decode | 8000 | 0.700 | 0.763 |
| raw-diagnostic | model_queries_only | 8000 | 0.707 | 0.772 |
| raw-diagnostic | linked_score_decode | 8000 | 1.000 | 1.000 |
| omitted-control | model_queries_only | 8000 | 0.695 | 0.761 |
| omitted-control | linked_score_decode | 8000 | 0.700 | 0.763 |


Ledger storage and operation measurements are retained in `results.json`; local byte readback does not demonstrate atomic delivery over a network.

## Figures

![Utility AUC by training and test period; missing cells are gray.](utility-auc.png)

![Actual admissions at each registered absolute epsilon cap; equal positions correspond to the fixed cap grid.](release-admissions.png)

![Separate model-only and linked-score attack histories at the largest cap (64), with raw/omitted controls.](attack-prefixes.png)

![White-box KNN exact-public-pattern coverage; matching does not prove identity or membership. Agreement metrics are reported separately in the table.](knn-coverage.png)

## Completed fits

| Model | Rows | Passes | Fit seconds | Query seconds | Warnings |
| --- | --- | --- | --- | --- | --- |
| 01-2009-slm_small-raw | 2,054,591 | 2 | 35.3 | 0.6 | 0 |
| 01-2009-slm_small-omitted | 2,054,591 | 2 | 33.2 | 0.3 | 0 |
| 01-2009-slm_small-rr | 2,054,591 | 2 | 35.0 | 0.8 | 0 |
| 02-2009-slm_medium-raw | 2,054,591 | 2 | 58.4 | 0.9 | 0 |
| 02-2009-slm_medium-omitted | 2,054,591 | 2 | 55.5 | 0.4 | 0 |
| 02-2009-slm_medium-rr | 2,054,591 | 2 | 60.4 | 1.0 | 0 |
| 03-2009-decision_tree-raw | 2,054,592 | full matrix fit | 3.6 | 0.2 | 0 |
| 03-2009-decision_tree-omitted | 2,054,592 | full matrix fit | 3.2 | 0.2 | 0 |
| 03-2009-decision_tree-rr | 2,054,592 | full matrix fit | 3.8 | 0.4 | 0 |
| 04-2009-random_forest-raw | 2,054,591 | full matrix fit | 24.2 | 0.6 | 0 |
| 04-2009-random_forest-omitted | 2,054,591 | full matrix fit | 19.6 | 0.4 | 0 |
| 04-2009-random_forest-rr | 2,054,591 | full matrix fit | 24.3 | 0.8 | 0 |
| 05-2009-extra_trees-raw | 2,054,591 | full matrix fit | 19.3 | 0.6 | 0 |
| 05-2009-extra_trees-omitted | 2,054,591 | full matrix fit | 14.8 | 0.4 | 0 |
| 05-2009-extra_trees-rr | 2,054,591 | full matrix fit | 19.5 | 0.8 | 0 |
| 06-2009-hist_gradient_boosting-raw | 2,054,591 | full matrix fit | 5.4 | 0.5 | 0 |
| 06-2009-hist_gradient_boosting-omitted | 2,054,591 | full matrix fit | 4.8 | 0.3 | 0 |
| 06-2009-hist_gradient_boosting-rr | 2,054,591 | full matrix fit | 5.3 | 0.6 | 0 |
| 07-2009-xgboost-raw | 2,054,592 | full matrix fit | 3.5 | 0.3 | 0 |
| 07-2009-xgboost-omitted | 2,054,592 | full matrix fit | 3.3 | 0.3 | 0 |
| 07-2009-xgboost-rr | 2,054,592 | full matrix fit | 3.3 | 0.5 | 0 |
| 08-2009-knn-raw | 2,054,591 | full matrix fit | 8.1 | 54.2 | 0 |
| 08-2009-knn-omitted | 2,054,591 | full matrix fit | 7.3 | 23.3 | 0 |
| 08-2009-knn-rr | 2,054,591 | full matrix fit | 8.3 | 57.0 | 0 |
| 09-2009-logistic_regression-raw | 2,054,591 | full matrix fit | 4.2 | 0.3 | 1 |
| 09-2009-logistic_regression-omitted | 2,054,591 | full matrix fit | 4.4 | 0.2 | 1 |
| 09-2009-logistic_regression-rr | 2,054,591 | full matrix fit | 4.7 | 0.4 | 1 |
| 10-2009-mlp-raw | 2,054,591 | 3 | 5.1 | 0.3 | 0 |
| 10-2009-mlp-omitted | 2,054,591 | 3 | 4.7 | 0.2 | 0 |
| 10-2009-mlp-rr | 2,054,591 | 3 | 4.6 | 0.4 | 0 |
| 11-2014-slm_small-raw | 2,116,003 | 2 | 36.4 | 0.6 | 0 |
| 11-2014-slm_small-omitted | 2,116,003 | 2 | 35.4 | 0.3 | 0 |
| 11-2014-slm_small-rr | 2,116,003 | 2 | 42.1 | 0.8 | 0 |
| 12-2014-slm_medium-raw | 2,116,003 | 2 | 69.2 | 0.9 | 0 |
| 12-2014-slm_medium-omitted | 2,116,003 | 2 | 60.1 | 0.4 | 0 |
| 12-2014-slm_medium-rr | 2,116,003 | 2 | 62.7 | 1.1 | 0 |
| 13-2014-decision_tree-raw | 2,116,003 | full matrix fit | 4.1 | 0.2 | 0 |
| 13-2014-decision_tree-omitted | 2,116,003 | full matrix fit | 3.5 | 0.2 | 0 |
| 13-2014-decision_tree-rr | 2,116,003 | full matrix fit | 3.8 | 0.4 | 0 |
| 14-2014-random_forest-raw | 2,116,003 | full matrix fit | 25.1 | 0.6 | 0 |
| 14-2014-random_forest-omitted | 2,116,003 | full matrix fit | 20.5 | 0.4 | 0 |
| 14-2014-random_forest-rr | 2,116,003 | full matrix fit | 25.2 | 0.8 | 0 |
| 15-2014-extra_trees-raw | 2,116,003 | full matrix fit | 19.7 | 0.6 | 0 |
| 15-2014-extra_trees-omitted | 2,116,003 | full matrix fit | 14.7 | 0.4 | 0 |
| 15-2014-extra_trees-rr | 2,116,003 | full matrix fit | 20.6 | 0.8 | 0 |
| 16-2014-hist_gradient_boosting-raw | 2,116,003 | full matrix fit | 5.5 | 0.5 | 0 |
| 16-2014-hist_gradient_boosting-omitted | 2,116,003 | full matrix fit | 5.0 | 0.3 | 0 |
| 16-2014-hist_gradient_boosting-rr | 2,116,003 | full matrix fit | 5.4 | 0.6 | 0 |
| 17-2014-xgboost-raw | 2,116,003 | full matrix fit | 3.4 | 0.3 | 0 |
| 17-2014-xgboost-omitted | 2,116,003 | full matrix fit | 3.2 | 0.3 | 0 |
| 17-2014-xgboost-rr | 2,116,003 | full matrix fit | 3.5 | 0.5 | 0 |
| 18-2014-knn-raw | 2,116,003 | full matrix fit | 8.0 | 58.7 | 0 |
| 18-2014-knn-omitted | 2,116,003 | full matrix fit | 7.1 | 24.5 | 0 |
| 18-2014-knn-rr | 2,116,003 | full matrix fit | 8.3 | 57.6 | 0 |
| 19-2014-logistic_regression-raw | 2,116,003 | full matrix fit | 5.3 | 0.3 | 1 |
| 19-2014-logistic_regression-omitted | 2,116,003 | full matrix fit | 4.4 | 0.2 | 1 |
| 19-2014-logistic_regression-rr | 2,116,003 | full matrix fit | 5.2 | 0.4 | 1 |
| 20-2014-mlp-raw | 2,116,003 | 3 | 5.2 | 0.3 | 0 |
| 20-2014-mlp-omitted | 2,116,003 | 3 | 4.9 | 0.2 | 0 |
| 20-2014-mlp-rr | 2,116,003 | 3 | 4.9 | 0.4 | 0 |
| 21-2019-slm_small-raw | 2,182,274 | 2 | 37.1 | 0.6 | 0 |
| 21-2019-slm_small-omitted | 2,182,274 | 2 | 35.5 | 0.3 | 0 |
| 21-2019-slm_small-rr | 2,182,274 | 2 | 38.0 | 0.8 | 0 |
| 22-2019-slm_medium-raw | 2,182,274 | 2 | 62.9 | 0.9 | 0 |
| 22-2019-slm_medium-omitted | 2,182,274 | 2 | 59.8 | 0.4 | 0 |
| 22-2019-slm_medium-rr | 2,182,274 | 2 | 64.1 | 1.1 | 0 |
| 23-2019-decision_tree-raw | 2,182,275 | full matrix fit | 4.2 | 0.2 | 0 |
| 23-2019-decision_tree-omitted | 2,182,275 | full matrix fit | 3.5 | 0.2 | 0 |
| 23-2019-decision_tree-rr | 2,182,275 | full matrix fit | 3.9 | 0.4 | 0 |
| 24-2019-random_forest-raw | 2,182,274 | full matrix fit | 25.9 | 0.6 | 0 |
| 24-2019-random_forest-omitted | 2,182,274 | full matrix fit | 21.1 | 0.4 | 0 |
| 24-2019-random_forest-rr | 2,182,274 | full matrix fit | 26.1 | 0.8 | 0 |
| 25-2019-extra_trees-raw | 2,182,274 | full matrix fit | 21.2 | 0.6 | 0 |
| 25-2019-extra_trees-omitted | 2,182,274 | full matrix fit | 15.9 | 0.4 | 0 |
| 25-2019-extra_trees-rr | 2,182,274 | full matrix fit | 20.9 | 0.8 | 0 |
| 26-2019-hist_gradient_boosting-raw | 2,182,274 | full matrix fit | 5.9 | 0.4 | 0 |
| 26-2019-hist_gradient_boosting-omitted | 2,182,274 | full matrix fit | 5.1 | 0.3 | 0 |
| 26-2019-hist_gradient_boosting-rr | 2,182,274 | full matrix fit | 5.7 | 0.6 | 0 |
| 27-2019-xgboost-raw | 2,182,275 | full matrix fit | 3.5 | 0.3 | 0 |
| 27-2019-xgboost-omitted | 2,182,275 | full matrix fit | 3.4 | 0.3 | 0 |
| 27-2019-xgboost-rr | 2,182,275 | full matrix fit | 3.6 | 0.5 | 0 |
| 28-2019-knn-raw | 2,182,274 | full matrix fit | 8.8 | 53.6 | 0 |
| 28-2019-knn-omitted | 2,182,274 | full matrix fit | 7.6 | 26.6 | 0 |
| 28-2019-knn-rr | 2,182,274 | full matrix fit | 8.4 | 59.3 | 0 |
| 29-2019-logistic_regression-raw | 2,182,274 | full matrix fit | 5.2 | 0.3 | 1 |
| 29-2019-logistic_regression-omitted | 2,182,274 | full matrix fit | 4.6 | 0.2 | 1 |
| 29-2019-logistic_regression-rr | 2,182,274 | full matrix fit | 5.0 | 0.4 | 1 |
| 30-2019-mlp-raw | 2,182,274 | 3 | 5.1 | 0.2 | 0 |
| 30-2019-mlp-omitted | 2,182,274 | 3 | 4.9 | 0.2 | 0 |
| 30-2019-mlp-rr | 2,182,274 | 3 | 5.2 | 0.4 | 0 |
| 31-2024-slm_small-raw | 2,206,118 | 2 | 37.4 | 0.6 | 0 |
| 31-2024-slm_small-omitted | 2,206,118 | 2 | 35.6 | 0.3 | 0 |
| 31-2024-slm_small-rr | 2,206,118 | 2 | 38.4 | 0.8 | 0 |
| 32-2024-slm_medium-raw | 2,206,118 | 2 | 64.0 | 0.9 | 0 |
| 32-2024-slm_medium-omitted | 2,206,118 | 2 | 61.3 | 0.4 | 0 |
| 32-2024-slm_medium-rr | 2,206,118 | 2 | 65.5 | 1.1 | 0 |
| 33-2024-decision_tree-raw | 2,206,119 | full matrix fit | 4.6 | 0.2 | 0 |
| 33-2024-decision_tree-omitted | 2,206,119 | full matrix fit | 3.7 | 0.2 | 0 |
| 33-2024-decision_tree-rr | 2,206,119 | full matrix fit | 4.1 | 0.4 | 0 |
| 34-2024-random_forest-raw | 2,206,118 | full matrix fit | 26.4 | 0.6 | 0 |
| 34-2024-random_forest-omitted | 2,206,118 | full matrix fit | 21.7 | 0.4 | 0 |
| 34-2024-random_forest-rr | 2,206,118 | full matrix fit | 27.0 | 0.8 | 0 |
| 35-2024-extra_trees-raw | 2,206,118 | full matrix fit | 21.3 | 0.6 | 0 |
| 35-2024-extra_trees-omitted | 2,206,118 | full matrix fit | 16.5 | 0.4 | 0 |
| 35-2024-extra_trees-rr | 2,206,118 | full matrix fit | 21.9 | 0.8 | 0 |
| 36-2024-hist_gradient_boosting-raw | 2,206,118 | full matrix fit | 5.8 | 0.4 | 0 |
| 36-2024-hist_gradient_boosting-omitted | 2,206,118 | full matrix fit | 5.2 | 0.3 | 0 |
| 36-2024-hist_gradient_boosting-rr | 2,206,118 | full matrix fit | 5.8 | 0.6 | 0 |
| 37-2024-xgboost-raw | 2,206,119 | full matrix fit | 3.7 | 0.3 | 0 |
| 37-2024-xgboost-omitted | 2,206,119 | full matrix fit | 3.3 | 0.3 | 0 |
| 37-2024-xgboost-rr | 2,206,119 | full matrix fit | 3.6 | 0.5 | 0 |
| 38-2024-knn-raw | 2,206,118 | full matrix fit | 8.2 | 56.8 | 0 |
| 38-2024-knn-omitted | 2,206,118 | full matrix fit | 7.5 | 26.7 | 0 |
| 38-2024-knn-rr | 2,206,118 | full matrix fit | 8.8 | 59.1 | 0 |
| 39-2024-logistic_regression-raw | 2,206,118 | full matrix fit | 3.8 | 0.3 | 1 |
| 39-2024-logistic_regression-omitted | 2,206,118 | full matrix fit | 5.1 | 0.2 | 1 |
| 39-2024-logistic_regression-rr | 2,206,118 | full matrix fit | 4.6 | 0.4 | 1 |
| 40-2024-mlp-raw | 2,206,118 | 3 | 5.2 | 0.3 | 0 |
| 40-2024-mlp-omitted | 2,206,118 | 3 | 5.0 | 0.2 | 0 |
| 40-2024-mlp-rr | 2,206,118 | 3 | 5.1 | 0.4 | 0 |

## Failures and incomplete work

Adapter-recorded failures: 0; worker failure records: 0; missing completions: 0. Full details and pending model IDs are in `results.json`. Incomplete cells are not assigned zero-valued results.

- `09-2009-logistic_regression-raw`: OptimizeWarning: Unknown solver options: iprint
- `09-2009-logistic_regression-omitted`: OptimizeWarning: Unknown solver options: iprint
- `09-2009-logistic_regression-rr`: OptimizeWarning: Unknown solver options: iprint
- `19-2014-logistic_regression-raw`: OptimizeWarning: Unknown solver options: iprint
- `19-2014-logistic_regression-omitted`: OptimizeWarning: Unknown solver options: iprint
- `19-2014-logistic_regression-rr`: OptimizeWarning: Unknown solver options: iprint
- `29-2019-logistic_regression-raw`: OptimizeWarning: Unknown solver options: iprint
- `29-2019-logistic_regression-omitted`: OptimizeWarning: Unknown solver options: iprint
- `29-2019-logistic_regression-rr`: OptimizeWarning: Unknown solver options: iprint
- `39-2024-logistic_regression-raw`: OptimizeWarning: Unknown solver options: iprint
- `39-2024-logistic_regression-omitted`: OptimizeWarning: Unknown solver options: iprint
- `39-2024-logistic_regression-rr`: OptimizeWarning: Unknown solver options: iprint

## Interpretation limits

- ACS source files publicly include the benchmark truth. Attacker views are restricted by experimental design; a recipient could obtain the original public data. These are controlled public-data mechanism evaluations, not real-world confidentiality or citizen-secrecy estimates.
- Fixed public roster/X/Y adjacency protects one published binary SEX value. This is not membership, whole-record, person-level or cross-period citizen privacy.
- Raw exports are diagnostics, not finite-epsilon DP releases. Cached, fresh and budgeted branches are alternative histories; simultaneous disclosure composes their costs.
- Attack and utility panels are finite and disjoint. D1-member means membership in D1, not every released model. Every target-model fit uses its full registered roster.
- One training seed per period/family, matched across arms. Fits, releases, periods and policies are not independent statistical replications.
- The two language models are small scratch-trained causal structured-record models, not pretrained general-language SLMs.
- Income exceeds $50,000 in each release endpoint's dollars; thresholds do not represent equal purchasing power. Metrics are unweighted ACS-record results.
- Bounded optimizer budgets do not establish convergence or equivalent optimization across families. A small or nonsignificant difference does not establish utility equivalence.
- Model-only candidate queries and additional record-linked scores are separate attack interfaces; linked-score disclosure does not establish training memorization or an optimal white-box attack.
- The no-model comparator is one fixed HGB learner on the reference panel, not an optimal use of all public X/Y/rosters. Omitted models may assist attribute inference through computation on public information at zero protected-SEX-channel cost; observed query gain over this baseline does not establish private-label memorization or DP failure.
- The release exercise is a local transactional kernel and verified byte readback, not a deployed network authority or remote training attestation.

## KNN model-export retention audit

White-box exact public-X matching of the full exported KNN training arrays. Infer a protected bit only when all retained rows with that exact public pattern agree. No exported row IDs are available, so an exact public match is not proof of individual identity or membership; held-out matches can reflect population correlations. RR stored bits are sanitized, not raw truth. Omission physically removes the protected column.

Audited exports: 12; missing exports: 0. This is a separate white-box retained-array check, not a linked-score attack.

| Period/arm | Retained rows | Fields | Panel | Guesses / n | Coverage | Raw-truth agreement | Cached-bit agreement |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2009/raw | 2054591 | 9 | member | 178 / 2000 | 0.089 | 1.000 | unavailable |
| 2009/raw | 2054591 | 9 | test | 123 / 2000 | 0.061 | 0.821 | unavailable |
| 2009/omitted | 2054591 | 8 | member | 0 / 2000 | 0.000 | unavailable | unavailable |
| 2009/omitted | 2054591 | 8 | test | 0 / 2000 | 0.000 | unavailable | unavailable |
| 2009/rr | 2054591 | 9 | member | 128 / 2000 | 0.064 | 0.656 | 1.000 |
| 2009/rr | 2054591 | 9 | test | 76 / 2000 | 0.038 | 0.632 | 0.632 |
| 2014/raw | 2116003 | 9 | member | 165 / 2000 | 0.083 | 1.000 | unavailable |
| 2014/raw | 2116003 | 9 | test | 103 / 2000 | 0.051 | 0.641 | unavailable |
| 2014/omitted | 2116003 | 8 | member | 0 / 2000 | 0.000 | unavailable | unavailable |
| 2014/omitted | 2116003 | 8 | test | 0 / 2000 | 0.000 | unavailable | unavailable |
| 2014/rr | 2116003 | 9 | member | 127 / 2000 | 0.064 | 0.811 | 1.000 |
| 2014/rr | 2116003 | 9 | test | 79 / 2000 | 0.040 | 0.570 | 0.532 |
| 2019/raw | 2182274 | 9 | member | 150 / 2000 | 0.075 | 1.000 | unavailable |
| 2019/raw | 2182274 | 9 | test | 96 / 2000 | 0.048 | 0.729 | unavailable |
| 2019/omitted | 2182274 | 8 | member | 0 / 2000 | 0.000 | unavailable | unavailable |
| 2019/omitted | 2182274 | 8 | test | 0 / 2000 | 0.000 | unavailable | unavailable |
| 2019/rr | 2182274 | 9 | member | 118 / 2000 | 0.059 | 0.771 | 1.000 |
| 2019/rr | 2182274 | 9 | test | 58 / 2000 | 0.029 | 0.603 | 0.534 |
| 2024/raw | 2206118 | 9 | member | 174 / 2000 | 0.087 | 1.000 | unavailable |
| 2024/raw | 2206118 | 9 | test | 113 / 2000 | 0.057 | 0.708 | unavailable |
| 2024/omitted | 2206118 | 8 | member | 0 / 2000 | 0.000 | unavailable | unavailable |
| 2024/omitted | 2206118 | 8 | test | 0 / 2000 | 0.000 | unavailable | unavailable |
| 2024/rr | 2206118 | 9 | member | 147 / 2000 | 0.073 | 0.741 | 1.000 |
| 2024/rr | 2206118 | 9 | test | 86 / 2000 | 0.043 | 0.628 | 0.605 |


## Scoring amendment

The original budgeted scoring path used floating-point 1/40, whose realized RR threshold slightly exceeded the exact 25,000-micro-epsilon bound. The original evidence is retained. This report uses the corrected source manifest and its newly drawn conservative budgeted channels; trained models and raw/cached/fresh results are reused. This implementation correction precedes attack-outcome analysis.

Amendment provenance: `{"coin_policy": "one fresh independent OS-randomized bit per scored record per model; no outcome-based rejection or redraw", "corrected_parameters": {"denominator": 18446744073709551616, "epsilon_effective": 0.024999999999999998, "epsilon_requested": 0.024999999999999998, "flip_probability": 0.4937503255004896, "keep_probability": 0.5062496744995104, "keep_threshold": 9338658182891233570, "randomness_bits": 64}, "created_utc": "2026-09-21T10:47:54.468039+00:00", "discovery": "mathematical input/accounting audit during training, before release replay or attack outcome inspection", "epsilon_micros": 25000, "exact_log_ratio_upper": "0.02499999999999999785297351207866017918991268820512857750456463571812907016101288230785919039254261194", "inventory": {"bytes": 104317, "path": "<LOCAL_DRIVE_D>/model_audit_data\\experiments\\acs-full-corpus-20260921\\run-v1\\inventory.json", "sha256": "2e933d6ce52a0d8ecccc94f1a90a32539db98b8f11ae6daaf041131d090a3c4e"}, "model_training": "unchanged; training and cached/fresh epsilon1 channels are unaffected", "old_parameters": {"denominator": 18446744073709551616, "epsilon_effective": 0.025, "epsilon_requested": 0.025, "flip_probability": 0.4937503255004896, "keep_probability": 0.5062496744995104, "keep_threshold": 9338658182891233586, "randomness_bits": 64}, "preservation": "No original fits, randomization realizations or evidence are overwritten", "reason": "float(1/40) exceeds exact25000/1e6; quantized RR epsilon also exceeds the original integer charge", "schema": "acs-full-budget-correction-v2", "script_sha256": "f516331d64686ecba7177d18320f71417cfc2ae24589553629d620b35336d5ec", "study_root": "<LOCAL_DRIVE_D>/model_audit_data\\experiments\\acs-full-corpus-20260921\\run-v1"}`.

Checks recorded JSON/NPZ checksums and row alignment. Does not independently retrain models, reparse source CSVs, rehash model binaries or certify remote execution.
