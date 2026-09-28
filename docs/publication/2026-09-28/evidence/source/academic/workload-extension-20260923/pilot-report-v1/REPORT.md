# Public-development workload pilot

180 fitted predictors; 3 public HGB encoders; 9 univariate relevance fits.
Fixed thresholds: income 0.80, degree 0.80, married 0.70. One seed; 20k public training, 10k search, 30k certification, 20k final test.
Simultaneous Hoeffding half-width: 0.012167. Conditional iid assumption, not validated Census population coverage.
Public training only: conditional privacy scope is fresh scoring inputs, not private training. Three protected fields; distinct from prior five-field experiments.

| Family | Cap | Decision | Selected |
|---|---:|---|---|
| hist_gradient_boosting | 1 | NO_FEASIBLE_CANDIDATE | - |
| hist_gradient_boosting | 2 | NO_FEASIBLE_CANDIDATE | - |
| logistic_regression | 1 | NO_FEASIBLE_CANDIDATE | - |
| logistic_regression | 2 | NO_FEASIBLE_CANDIDATE | - |
| slm_medium | 1 | NO_FEASIBLE_CANDIDATE | - |
| slm_medium | 2 | NO_FEASIBLE_CANDIDATE | - |
| slm_small | 1 | NO_FEASIBLE_CANDIDATE | - |
| slm_small | 2 | NO_FEASIBLE_CANDIDATE | - |

## All final-test results

| Family | Arm | Income accuracy | Degree accuracy | Married accuracy |
|---|---|---:|---:|---:|
| logistic_regression | omit | 0.69880 | 0.65080 | 0.61415 |
| logistic_regression | equal-1 | 0.69880 | 0.65045 | 0.61290 |
| logistic_regression | single0-1 | 0.69950 | 0.65110 | 0.61690 |
| logistic_regression | single1-1 | 0.69810 | 0.65035 | 0.61455 |
| logistic_regression | single2-1 | 0.70015 | 0.65035 | 0.61400 |
| logistic_regression | relevance-1 | 0.69925 | 0.65145 | 0.61325 |
| logistic_regression | representation-1 | 0.69765 | 0.65150 | 0.61290 |
| logistic_regression | fresh-1 | 0.69935 | 0.64985 | 0.61425 |
| logistic_regression | equal-2 | 0.69955 | 0.65005 | 0.61340 |
| logistic_regression | single0-2 | 0.70445 | 0.65045 | 0.62020 |
| logistic_regression | single1-2 | 0.69855 | 0.65185 | 0.61430 |
| logistic_regression | single2-2 | 0.70075 | 0.65005 | 0.61425 |
| logistic_regression | relevance-2 | 0.70170 | 0.65000 | 0.61355 |
| logistic_regression | representation-2 | 0.70100 | 0.65130 | 0.61435 |
| logistic_regression | fresh-2 | 0.70020 | 0.65000 | 0.61360 |
| hist_gradient_boosting | omit | 0.69840 | 0.64885 | 0.60965 |
| hist_gradient_boosting | equal-1 | 0.69745 | 0.65165 | 0.61005 |
| hist_gradient_boosting | single0-1 | 0.69895 | 0.65115 | 0.61790 |
| hist_gradient_boosting | single1-1 | 0.69705 | 0.64750 | 0.60855 |
| hist_gradient_boosting | single2-1 | 0.69850 | 0.64940 | 0.60795 |
| hist_gradient_boosting | relevance-1 | 0.69880 | 0.64740 | 0.61015 |
| hist_gradient_boosting | representation-1 | 0.69725 | 0.64960 | 0.61005 |
| hist_gradient_boosting | fresh-1 | 0.69800 | 0.64860 | 0.61005 |
| hist_gradient_boosting | equal-2 | 0.69675 | 0.64945 | 0.61075 |
| hist_gradient_boosting | single0-2 | 0.70210 | 0.64885 | 0.62610 |
| hist_gradient_boosting | single1-2 | 0.69680 | 0.64960 | 0.61065 |
| hist_gradient_boosting | single2-2 | 0.70365 | 0.64810 | 0.61115 |
| hist_gradient_boosting | relevance-2 | 0.70010 | 0.64590 | 0.61100 |
| hist_gradient_boosting | representation-2 | 0.70165 | 0.64905 | 0.61145 |
| hist_gradient_boosting | fresh-2 | 0.69830 | 0.64595 | 0.60910 |
| slm_small | omit | 0.68365 | 0.63230 | 0.55915 |
| slm_small | equal-1 | 0.68020 | 0.60110 | 0.55120 |
| slm_small | single0-1 | 0.67965 | 0.60110 | 0.56735 |
| slm_small | single1-1 | 0.67565 | 0.60110 | 0.53590 |
| slm_small | single2-1 | 0.66985 | 0.60110 | 0.55135 |
| slm_small | relevance-1 | 0.67995 | 0.60110 | 0.54750 |
| slm_small | representation-1 | 0.68010 | 0.60110 | 0.54775 |
| slm_small | fresh-1 | 0.67940 | 0.60110 | 0.55155 |
| slm_small | equal-2 | 0.67360 | 0.60110 | 0.55230 |
| slm_small | single0-2 | 0.68540 | 0.60110 | 0.56245 |
| slm_small | single1-2 | 0.67740 | 0.60110 | 0.53845 |
| slm_small | single2-2 | 0.67830 | 0.60180 | 0.55595 |
| slm_small | relevance-2 | 0.65340 | 0.60110 | 0.54940 |
| slm_small | representation-2 | 0.68740 | 0.60110 | 0.55115 |
| slm_small | fresh-2 | 0.67875 | 0.60110 | 0.55335 |
| slm_medium | omit | 0.68710 | 0.63080 | 0.56190 |
| slm_medium | equal-1 | 0.68030 | 0.60315 | 0.55925 |
| slm_medium | single0-1 | 0.68575 | 0.64020 | 0.57910 |
| slm_medium | single1-1 | 0.68695 | 0.63400 | 0.56705 |
| slm_medium | single2-1 | 0.69035 | 0.64220 | 0.56110 |
| slm_medium | relevance-1 | 0.68250 | 0.60470 | 0.55710 |
| slm_medium | representation-1 | 0.68245 | 0.60895 | 0.57340 |
| slm_medium | fresh-1 | 0.67930 | 0.60150 | 0.56550 |
| slm_medium | equal-2 | 0.68425 | 0.60945 | 0.56040 |
| slm_medium | single0-2 | 0.69130 | 0.64020 | 0.57215 |
| slm_medium | single1-2 | 0.68640 | 0.63495 | 0.56530 |
| slm_medium | single2-2 | 0.68950 | 0.63600 | 0.55280 |
| slm_medium | relevance-2 | 0.68505 | 0.60220 | 0.56175 |
| slm_medium | representation-2 | 0.69110 | 0.62495 | 0.55970 |
| slm_medium | fresh-2 | 0.68065 | 0.60335 | 0.55925 |

Majority accuracy by task: [0.51185, 0.6011, 0.5276]
Fits with recorded warnings: 45. Relevance fitting also emitted scipy/sklearn iprint OptimizeWarnings; these were observed on stderr and did not stop the run.

No threshold was changed; all candidate failures remain in the results. A marginal-relevance heuristic is not a CPBA reproduction; learned HGB task bits are not Cheng et al. reproduction.
No final-test-selected winner is claimed. Costs refer to each alternative complete three-task history, not the combined experimental archive.
Verification reconstructs 1024 final scores for every model, all stored metrics, privacy sums, cohort disjointness and certification choices; it does not verify private coins or arbitrary producers.
