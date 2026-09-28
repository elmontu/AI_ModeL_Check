# Two-attribute extension

Status: complete; all 40 full-roster fits succeeded.

Different adjacency: replace both degree and married-status bits for one record, fixing six other covariates and income.

| Input | Mean income AUC | Sufficient bound |
|---|---:|---:|
| none | 0.791373 | 0 |
| education | 0.800911 | 1 |
| married | 0.792287 | 1 |
| both | 0.801543 | 2 |
| raw_both | 0.834243 | unbounded diagnostic |

| Paired contrast | Difference | Conditional pointwise 95% interval |
|---|---:|---:|
| both - education | 0.000632 | [0.000038, 0.001226] |
| both - married | 0.009256 | [0.007488, 0.011024] |
| education - none | 0.009538 | [0.007772, 0.011304] |
| married - none | 0.000914 | [0.000162, 0.001665] |
| both - none | 0.010170 | [0.008298, 0.012041] |

Equal weight across eight fixed period/family fits and four test periods. The intervals account for shared test observations via paired AUC structural components; they exclude seed, channel-realization and survey-design uncertainty.

This is exploratory evidence after the earlier SEX/DIS outcomes and reviewer critique. It does not establish an agency need, a policy utility threshold, fairness, or legality. A two-bit charged mask suffices for the two static channels. A joint publication of the same product-RR pair has the same distribution and bound; the model gate adds authorization and binding, not stronger DP.

Every per-cell metric in results.json points to its prediction file, array and test-period filter. Raw controls and the combined research archive are not designated private exports.
