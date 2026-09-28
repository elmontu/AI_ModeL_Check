# Corrective degree-task gate

Protocol, protected vector and 0.80 degree threshold unchanged. Raw inputs are non-private utility diagnostics.
Fresh evaluation panels for the named experiments; configurations selected only by public development log loss.
Three fitting seeds per setting, 192 development scores, 16 locked probability-average ensembles.

| Candidate | Chosen setting | Certification accuracy | Upper bound | Final accuracy | Status |
|---|---:|---:|---:|---:|---|
| coarse-omit-logistic_regression | 1.0 | 0.65287 | 0.66324 | 0.65815 | UTILITY_FAIL |
| coarse-omit-hist_gradient_boosting | 80 | 0.65077 | 0.66114 | 0.65740 | UTILITY_FAIL |
| coarse-omit-slm_small | 40 | 0.65213 | 0.66251 | 0.65885 | UTILITY_FAIL |
| coarse-omit-slm_medium | 20 | 0.65360 | 0.66398 | 0.65995 | UTILITY_FAIL |
| coarse-raw-logistic_regression | 1.0 | 0.65507 | 0.66544 | 0.66050 | UTILITY_FAIL |
| coarse-raw-hist_gradient_boosting | 80 | 0.65413 | 0.66451 | 0.65925 | UTILITY_FAIL |
| coarse-raw-slm_small | 40 | 0.65637 | 0.66674 | 0.66080 | UTILITY_FAIL |
| coarse-raw-slm_medium | 40 | 0.65567 | 0.66604 | 0.66120 | UTILITY_FAIL |
| fine-omit-logistic_regression | 1.0 | 0.65250 | 0.66288 | 0.65710 | UTILITY_FAIL |
| fine-omit-hist_gradient_boosting | 80 | 0.64743 | 0.65781 | 0.64855 | UTILITY_FAIL |
| fine-omit-slm_small | 40 | 0.65307 | 0.66344 | 0.65845 | UTILITY_FAIL |
| fine-omit-slm_medium | 20 | 0.65423 | 0.66461 | 0.65590 | UTILITY_FAIL |
| fine-raw-logistic_regression | 1.0 | 0.65440 | 0.66478 | 0.65915 | UTILITY_FAIL |
| fine-raw-hist_gradient_boosting | 80 | 0.65193 | 0.66231 | 0.65435 | UTILITY_FAIL |
| fine-raw-slm_small | 40 | 0.65490 | 0.66528 | 0.66090 | UTILITY_FAIL |
| fine-raw-slm_medium | 20 | 0.65447 | 0.66484 | 0.65910 | UTILITY_FAIL |

Downstream DP gate open: False
No private-release approval follows from a raw-input pass. If the necessary task fails for every candidate, stop the conditional DP search.
No claim of Bayes impossibility, survey-population coverage, exhaustive optimization, or newly collected population replication.
Historical two-epoch reproduction passed: False; maximum score difference 0.01561993. The initial verifier stopped at this failed comparison. It is retained as a separate limitation; no cause has been established. Current saved-model reconstruction uses the original 1e-5 tolerance.
Seed-level scores and all learning curves are retained separately; checkpoints are not independent models.
