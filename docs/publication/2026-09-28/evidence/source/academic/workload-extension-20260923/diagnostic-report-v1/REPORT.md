# Why the workload pilot failed: diagnostic follow-up

Protocol, adjacency, privacy caps and original thresholds unchanged. Raw controls are non-private diagnostics.
36 new fits on the original public training partition. Previously inspected evaluation panels: exploratory, not new approval evidence.

| Family | Inputs | Epochs | Income accuracy | Degree accuracy | Married accuracy |
|---|---|---:|---:|---:|---:|
| logistic_regression | raw | 2 | 0.73135 | 0.65160 | 0.63260 |
| hist_gradient_boosting | raw | 2 | 0.73080 | 0.65390 | 0.64580 |
| slm_small | raw | 2 | 0.71455 | 0.60110 | 0.57240 |
| slm_medium | raw | 2 | 0.71740 | 0.63175 | 0.56570 |
| slm_small | omit | 20 | 0.70040 | 0.65240 | 0.61235 |
| slm_small | raw | 20 | 0.73245 | 0.65200 | 0.64050 |
| slm_small | equal-2 | 20 | 0.70030 | 0.64965 | 0.61225 |
| slm_small | representation-2 | 20 | 0.70280 | 0.65065 | 0.61470 |
| slm_medium | omit | 20 | 0.69975 | 0.64875 | 0.61255 |
| slm_medium | raw | 20 | 0.73175 | 0.65110 | 0.64255 |
| slm_medium | equal-2 | 20 | 0.70040 | 0.64985 | 0.61325 |
| slm_medium | representation-2 | 20 | 0.70235 | 0.64995 | 0.61535 |

## Longer-training changes (20 minus 2 epochs)

| Family | Inputs | Task | Accuracy change | AUC change |
|---|---|---|---:|---:|
| slm_small | omit | income | +0.01675 | +0.03335 |
| slm_small | omit | degree | +0.02010 | +0.03645 |
| slm_small | omit | married | +0.05320 | +0.05305 |
| slm_small | raw | income | +0.01790 | +0.02204 |
| slm_small | raw | degree | +0.05090 | +0.05354 |
| slm_small | raw | married | +0.06810 | +0.08267 |
| slm_small | equal-2 | income | +0.02670 | +0.04266 |
| slm_small | equal-2 | degree | +0.04855 | +0.06773 |
| slm_small | equal-2 | married | +0.05995 | +0.07350 |
| slm_small | representation-2 | income | +0.01540 | +0.04238 |
| slm_small | representation-2 | degree | +0.04955 | +0.04971 |
| slm_small | representation-2 | married | +0.06355 | +0.06458 |
| slm_medium | omit | income | +0.01265 | +0.02068 |
| slm_medium | omit | degree | +0.01795 | +0.02813 |
| slm_medium | omit | married | +0.05065 | +0.05187 |
| slm_medium | raw | income | +0.01435 | +0.01892 |
| slm_medium | raw | degree | +0.01935 | +0.04183 |
| slm_medium | raw | married | +0.07685 | +0.07695 |
| slm_medium | equal-2 | income | +0.01615 | +0.03147 |
| slm_medium | equal-2 | degree | +0.04040 | +0.04528 |
| slm_medium | equal-2 | married | +0.05285 | +0.05753 |
| slm_medium | representation-2 | income | +0.01125 | +0.02983 |
| slm_medium | representation-2 | degree | +0.02500 | +0.03950 |
| slm_medium | representation-2 | married | +0.05565 | +0.05183 |

## Interpretation limits
The raw controls isolate removal of RR at the tested input/learner settings, not the Bayes-optimal accuracy.
Longer training changes the optimizer budget only, retaining inputs, cache draws, models and fitting seed.
Per-task gains may differ. Twenty epochs do not prove convergence; compare held-out loss and AUC, not training loss alone.
No protocol rule or approval threshold is relaxed. Reused test data cannot certify a newly selected implementation.
All scores, training losses, warnings and fit configurations remain in the source and results.json.
Independent verification: 144 score vectors; 36 predictor reconstructions, maximum discrepancy 0.
