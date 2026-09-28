# Complete descriptive tables

Generated from immutable run records. Error is clipped squared prediction error; lower is better. SD is across eight independent histories, not a confidence interval.

## Public Gram diagonal

| Setting | Final n | Private error | Raw error | Paired excess mean ± SD | Accuracy | Update/recompute aggregation ms per event | Component ratio |
|---|---:|---:|---:|---:|---:|---:|---:|
| base | 9500 | 0.621556 | 0.621542 | 0.000014 ± 0.001190 | 0.75170 | 0.0770 / 2.4260 | 5.83× |
| n-2000 | 1900 | 0.635117 | 0.620927 | 0.014190 ± 0.006256 | 0.74913 | 0.0485 / 0.3620 | 1.77× |
| n-50000 | 47500 | 0.622493 | 0.622456 | 0.000036 ± 0.000257 | 0.75008 | 0.2839 / 32.7784 | 34.42× |
| d-4 | 9500 | 0.603360 | 0.603277 | 0.000083 ± 0.000201 | 0.75025 | 0.0608 / 0.1854 | 1.35× |
| d-64 | 9500 | 0.665071 | 0.670086 | -0.005015 ± 0.006714 | 0.75290 | 0.2817 / 112.3362 | 50.54× |
| events-1 | 9900 | 0.618593 | 0.618420 | 0.000172 ± 0.000732 | 0.75225 | 0.0808 / 2.2375 | 5.06× |
| events-20 | 8000 | 0.622275 | 0.620786 | 0.001490 ± 0.004149 | 0.74977 | 0.0763 / 2.3202 | 5.40× |
| fraction-0001 | 9950 | 0.620812 | 0.619978 | 0.000833 ± 0.001353 | 0.74845 | 0.0525 / 2.5586 | 6.41× |
| fraction-004 | 8000 | 0.620562 | 0.619572 | 0.000991 ± 0.001716 | 0.75282 | 0.1824 / 2.3081 | 4.28× |
| epsilon-1 | 9500 | 0.623701 | 0.618902 | 0.004799 ± 0.004690 | 0.74992 | 0.0831 / 2.6128 | 6.07× |
| epsilon-8 | 9500 | 0.618380 | 0.618102 | 0.000278 ± 0.000608 | 0.75305 | 0.0785 / 2.6407 | 6.42× |
| correlation-07 | 9500 | 0.794307 | 0.794020 | 0.000288 ± 0.003640 | 0.62370 | 0.0809 / 2.4250 | 5.24× |
| dense-d-4 | 9500 | 0.610154 | 0.610180 | -0.000026 ± 0.000568 | 0.75020 | 0.0663 / 0.1895 | 1.32× |
| dense-d-16 | 9500 | 0.631488 | 0.630321 | 0.001167 ± 0.001040 | 0.77430 | 0.0772 / 2.8981 | 7.05× |
| dense-d-64 | 9500 | 0.693396 | 0.691812 | 0.001583 ± 0.009566 | 0.76058 | 0.2938 / 108.6319 | 50.50× |
| matched-events-1 | 9500 | 0.617626 | 0.617761 | -0.000134 ± 0.001427 | 0.75365 | 0.2131 / 2.3461 | 4.72× |
| matched-events-20 | 9500 | 0.619247 | 0.618003 | 0.001245 ± 0.004385 | 0.75192 | 0.0535 / 2.8130 | 6.80× |

Component ratios are sums of measured operations, excluding source IO, authenticated requests, erasure and serving. Aggregation order was fixed; fit order alternated. These are not whole-system speedups.

### Predeclared prediction-distance confirmation

The endpoint and five descriptive orderings were fixed in plan-confirmation.json before generating these fresh-seed histories. Saved weights are evaluated on hash-verified reconstructed test inputs without refitting. This repeats the earlier secondary diagnostic; it is not a simultaneous significance test.

| Setting | Unclipped prediction distance, mean ± SD | Clipped prediction distance, mean ± SD |
|---|---:|---:|
| base | 0.0006242 ± 0.0003588 | 0.0005211 ± 0.0002385 |
| n-2000 | 0.0245234 ± 0.0145436 | 0.0199360 ± 0.0106817 |
| n-50000 | 0.0000270 ± 0.0000176 | 0.0000236 ± 0.0000157 |
| d-4 | 0.0000166 ± 0.0000136 | 0.0000154 ± 0.0000127 |
| d-64 | 0.0121842 ± 0.0039391 | 0.0119938 ± 0.0037308 |
| events-1 | 0.0001196 ± 0.0000483 | 0.0001049 ± 0.0000418 |
| events-20 | 0.0039389 ± 0.0015542 | 0.0034052 ± 0.0012981 |
| fraction-0001 | 0.0005323 ± 0.0001866 | 0.0004653 ± 0.0001607 |
| fraction-004 | 0.0008013 ± 0.0004192 | 0.0007029 ± 0.0003623 |
| epsilon-1 | 0.0055882 ± 0.0013456 | 0.0048750 ± 0.0011106 |
| epsilon-8 | 0.0000857 ± 0.0000390 | 0.0000739 ± 0.0000335 |
| correlation-07 | 0.0012010 ± 0.0004761 | 0.0011694 ± 0.0004752 |
| dense-d-4 | 0.0000327 ± 0.0000247 | 0.0000259 ± 0.0000197 |
| dense-d-16 | 0.0005950 ± 0.0001561 | 0.0005584 ± 0.0001468 |
| dense-d-64 | 0.0128506 ± 0.0042926 | 0.0124739 ± 0.0040100 |
| matched-events-1 | 0.0001388 ± 0.0000708 | 0.0001155 ± 0.0000567 |
| matched-events-20 | 0.0026770 ± 0.0010658 | 0.0022378 ± 0.0009130 |

| Predeclared descriptive ordering | Observed? |
|---|---|
| dense_dimension_increasing_distance | Yes |
| epsilon_increasing_decreasing_distance | Yes |
| matched_release_count_increasing_distance | Yes |
| sample_size_decreasing_distance | Yes |
| sparse_dimension_increasing_distance | Yes |

