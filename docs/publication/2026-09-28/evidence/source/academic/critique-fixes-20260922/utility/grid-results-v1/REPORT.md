# Utility revision: grid

Status: complete.
Fits: 72; elapsed 366.3s. No controlled latency claim.

## logistic_regression

| Arm | Mean AUC | Candidate bound |
|---|---:|---:|
| none | 0.787454 | 0 |
| degree_rr1 | 0.796650 | 1 |
| marriage_rr1 | 0.788516 | 1 |
| both_rr1 | 0.797479 | 2 |
| raw_both | 0.830537 | None |
| raw_degree | 0.828175 | None |
| raw_marriage | 0.791669 | None |
| degree_rr2 | 0.810887 | 2 |
| marriage_rr2 | 0.789505 | 2 |

| Contrast | Mean difference | Pointwise record 95% interval |
|---|---:|---:|
| raw_degree − none | +0.040721 | [+0.037082, +0.044360] |
| raw_marriage − none | +0.004215 | [+0.002820, +0.005610] |
| raw_both − raw_degree | +0.002361 | [+0.001394, +0.003329] |
| raw_both − raw_marriage | +0.038868 | [+0.035310, +0.042425] |
| degree_rr1 − none | +0.009196 | [+0.007375, +0.011016] |
| marriage_rr1 − none | +0.001061 | [+0.000327, +0.001796] |
| both_rr1 − degree_rr1 | +0.000829 | [+0.000238, +0.001420] |
| both_rr1 − marriage_rr1 | +0.008963 | [+0.007156, +0.010771] |
| both_rr1 − none | +0.010025 | [+0.008108, +0.011942] |
| degree_rr2 − both_rr1 | +0.013408 | [+0.010576, +0.016239] |
| marriage_rr2 − both_rr1 | -0.007974 | [-0.010027, -0.005920] |
| raw_both − both_rr1 | +0.033057 | [+0.029729, +0.036386] |

## hist_gradient_boosting

| Arm | Mean AUC | Candidate bound |
|---|---:|---:|
| none | 0.795473 | 0 |
| degree_rr1 | 0.804667 | 1 |
| marriage_rr1 | 0.796651 | 1 |
| both_rr1 | 0.805576 | 2 |
| raw_both | 0.838172 | None |
| raw_degree | 0.835723 | None |
| raw_marriage | 0.800176 | None |
| degree_rr2 | 0.819008 | 2 |
| marriage_rr2 | 0.797941 | 2 |

| Contrast | Mean difference | Pointwise record 95% interval |
|---|---:|---:|
| raw_degree − none | +0.040250 | [+0.036591, +0.043909] |
| raw_marriage − none | +0.004703 | [+0.003291, +0.006115] |
| raw_both − raw_degree | +0.002449 | [+0.001467, +0.003432] |
| raw_both − raw_marriage | +0.037996 | [+0.034477, +0.041516] |
| degree_rr1 − none | +0.009194 | [+0.007421, +0.010967] |
| marriage_rr1 − none | +0.001179 | [+0.000362, +0.001995] |
| both_rr1 − degree_rr1 | +0.000909 | [+0.000287, +0.001530] |
| both_rr1 − marriage_rr1 | +0.008924 | [+0.007151, +0.010698] |
| both_rr1 − none | +0.010103 | [+0.008215, +0.011991] |
| degree_rr2 − both_rr1 | +0.013432 | [+0.010696, +0.016168] |
| marriage_rr2 − both_rr1 | -0.007635 | [-0.009656, -0.005614] |
| raw_both − both_rr1 | +0.032596 | [+0.029304, +0.035889] |

## pooled_two_families

| Arm | Mean AUC | Candidate bound |
|---|---:|---:|
| none | 0.791464 | 0 |
| degree_rr1 | 0.800659 | 1 |
| marriage_rr1 | 0.792584 | 1 |
| both_rr1 | 0.801527 | 2 |
| raw_both | 0.834354 | None |
| raw_degree | 0.831949 | None |
| raw_marriage | 0.795922 | None |
| degree_rr2 | 0.814947 | 2 |
| marriage_rr2 | 0.793723 | 2 |

| Contrast | Mean difference | Pointwise record 95% interval |
|---|---:|---:|
| raw_degree − none | +0.040486 | [+0.036880, +0.044091] |
| raw_marriage − none | +0.004459 | [+0.003092, +0.005825] |
| raw_both − raw_degree | +0.002405 | [+0.001460, +0.003350] |
| raw_both − raw_marriage | +0.038432 | [+0.034932, +0.041932] |
| degree_rr1 − none | +0.009195 | [+0.007426, +0.010964] |
| marriage_rr1 − none | +0.001120 | [+0.000366, +0.001875] |
| both_rr1 − degree_rr1 | +0.000869 | [+0.000281, +0.001457] |
| both_rr1 − marriage_rr1 | +0.008944 | [+0.007177, +0.010710] |
| both_rr1 − none | +0.010064 | [+0.008191, +0.011937] |
| degree_rr2 − both_rr1 | +0.013420 | [+0.010663, +0.016177] |
| marriage_rr2 − both_rr1 | -0.007804 | [-0.009814, -0.005795] |
| raw_both − both_rr1 | +0.032827 | [+0.029550, +0.036104] |


Each candidate arm is an alternative package. Bound0/1/2 applies model plus one linked-score realization under joint two-bit replacement with public other fields/Y/IDs/rosters. TRAIN and utility IDs disjoint. Reused channel values are never recharged within the same candidate. Raw arms, labels, exact utility results and combined research archive have no recipient DP guarantee. Releasing all grid sanitized arms jointly composes to6 per record; all crossed sanitized candidates compose to12 per record on their roster or panel, not2; combining grids may compose further.

Paired pointwise normal structural-component intervals, preserving shared-row covariance; fixed fitted models/training caches, IID within-period record/observed serving-score working distribution. No seed/cache/population/survey-design joint inference.

Illustrative sensitivity cutoffs only; no agency requirement, noninferiority declaration or cost-benefit rule.

Warnings: 36. Every per-cell AUC names its score file, row filter and label source. All scenarios are exploratory public-data case studies; no universal ordering or practical privacy-utility requirement follows.
