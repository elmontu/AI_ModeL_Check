# Complete descriptive tables

Generated from immutable run records. Error is clipped squared prediction error; lower is better. SD is across eight independent histories, not a confidence interval.

## Full Gram perturbation

| Setting | Final n | Private error | Raw error | Paired excess mean ± SD | Accuracy | Update/recompute aggregation ms per event | Component ratio |
|---|---:|---:|---:|---:|---:|---:|---:|
| base | 9500 | 0.620180 | 0.618855 | 0.001325 ± 0.001952 | 0.75092 | 0.0781 / 2.3517 | 4.89× |
| n-2000 | 1900 | 0.641443 | 0.626765 | 0.014678 ± 0.012626 | 0.74710 | 0.0489 / 0.3532 | 1.78× |
| n-50000 | 47500 | 0.619037 | 0.618964 | 0.000074 ± 0.000400 | 0.75205 | 0.2736 / 33.0660 | 35.83× |
| d-4 | 9500 | 0.613296 | 0.613241 | 0.000056 ± 0.000420 | 0.74810 | 0.0684 / 0.1873 | 1.34× |
| d-64 | 9500 | 0.671708 | 0.673279 | -0.001571 ± 0.007917 | 0.75180 | 0.3177 / 93.8913 | 44.27× |
| events-1 | 9900 | 0.619156 | 0.618996 | 0.000160 ± 0.000751 | 0.75225 | 0.0987 / 2.3709 | 4.61× |
| events-20 | 8000 | 0.622539 | 0.619012 | 0.003526 ± 0.006730 | 0.75050 | 0.1037 / 1.9298 | 3.63× |
| fraction-0001 | 9950 | 0.626017 | 0.625131 | 0.000886 ± 0.001082 | 0.74925 | 0.0638 / 2.0533 | 4.35× |
| fraction-004 | 8000 | 0.621582 | 0.621389 | 0.000193 ± 0.001781 | 0.74938 | 0.2183 / 1.9609 | 3.34× |
| epsilon-1 | 9500 | 0.626647 | 0.620872 | 0.005775 ± 0.004265 | 0.75023 | 0.1062 / 1.9767 | 3.54× |
| epsilon-8 | 9500 | 0.619669 | 0.619839 | -0.000170 ± 0.001386 | 0.75097 | 0.0928 / 1.9978 | 4.13× |
| correlation-07 | 9500 | 0.797319 | 0.796750 | 0.000569 ± 0.004608 | 0.62640 | 0.0936 / 2.0911 | 4.54× |
| dense-d-4 | 9500 | 0.604955 | 0.604992 | -0.000037 ± 0.000342 | 0.75345 | 0.0788 / 0.2184 | 1.33× |
| dense-d-16 | 9500 | 0.636670 | 0.636625 | 0.000045 ± 0.000837 | 0.76877 | 0.0968 / 1.9878 | 4.21× |
| dense-d-64 | 9500 | 0.696616 | 0.693155 | 0.003461 ± 0.005716 | 0.76448 | 0.3079 / 110.0992 | 52.14× |
| matched-events-1 | 9500 | 0.616751 | 0.616402 | 0.000348 ± 0.001070 | 0.75243 | 0.2202 / 2.2551 | 4.26× |
| matched-events-20 | 9500 | 0.619342 | 0.617493 | 0.001849 ± 0.004523 | 0.75257 | 0.0515 / 2.3165 | 5.80× |

Component ratios are sums of measured operations, excluding source IO, authenticated requests, erasure and serving. Aggregation order was fixed; fit order alternated. These are not whole-system speedups.

### Secondary prediction-distance diagnostic

Post-run analysis of saved model weights on hash-verified reconstructed public test inputs; no models are refitted. Mean squared prediction distance to the same-cell raw model isolates output perturbation, not prediction error against labels. It was added after seeing the initial endpoint-error table.

| Setting | Unclipped prediction distance, mean ± SD | Clipped prediction distance, mean ± SD |
|---|---:|---:|
| base | 0.0007755 ± 0.0002091 | 0.0006761 ± 0.0001732 |
| n-2000 | 0.0221138 ± 0.0069114 | 0.0194316 ± 0.0059135 |
| n-50000 | 0.0000243 ± 0.0000088 | 0.0000206 ± 0.0000082 |
| d-4 | 0.0000252 ± 0.0000105 | 0.0000220 ± 0.0000104 |
| d-64 | 0.0133267 ± 0.0041475 | 0.0130866 ± 0.0038407 |
| events-1 | 0.0001466 ± 0.0000444 | 0.0001305 ± 0.0000386 |
| events-20 | 0.0042185 ± 0.0020916 | 0.0036433 ± 0.0018247 |
| fraction-0001 | 0.0006239 ± 0.0001649 | 0.0005473 ± 0.0001399 |
| fraction-004 | 0.0008200 ± 0.0001665 | 0.0007204 ± 0.0001755 |
| epsilon-1 | 0.0065465 ± 0.0034997 | 0.0057211 ± 0.0031817 |
| epsilon-8 | 0.0001403 ± 0.0000564 | 0.0001140 ± 0.0000435 |
| correlation-07 | 0.0012675 ± 0.0003606 | 0.0012357 ± 0.0003586 |
| dense-d-4 | 0.0000307 ± 0.0000145 | 0.0000288 ± 0.0000152 |
| dense-d-16 | 0.0006980 ± 0.0001650 | 0.0006568 ± 0.0001560 |
| dense-d-64 | 0.0099891 ± 0.0023579 | 0.0098384 ± 0.0022666 |
| matched-events-1 | 0.0001887 ± 0.0000681 | 0.0001625 ± 0.0000556 |
| matched-events-20 | 0.0030627 ± 0.0015312 | 0.0026907 ± 0.0013653 |

## Public Gram diagonal

| Setting | Final n | Private error | Raw error | Paired excess mean ± SD | Accuracy | Update/recompute aggregation ms per event | Component ratio |
|---|---:|---:|---:|---:|---:|---:|---:|
| base | 9500 | 0.620340 | 0.618855 | 0.001485 ± 0.002104 | 0.75060 | 0.0797 / 2.4299 | 5.64× |
| n-2000 | 1900 | 0.636920 | 0.626765 | 0.010155 ± 0.012381 | 0.74775 | 0.0487 / 0.3572 | 1.76× |
| n-50000 | 47500 | 0.618971 | 0.618964 | 0.000007 ± 0.000281 | 0.75152 | 0.2706 / 32.5992 | 32.51× |
| d-4 | 9500 | 0.613278 | 0.613241 | 0.000038 ± 0.000516 | 0.74810 | 0.0644 / 0.1891 | 1.35× |
| d-64 | 9500 | 0.671389 | 0.673279 | -0.001891 ± 0.006153 | 0.75120 | 0.2930 / 115.3655 | 54.46× |
| events-1 | 9900 | 0.618987 | 0.618996 | -0.000009 ± 0.000430 | 0.75193 | 0.0812 / 2.3258 | 4.75× |
| events-20 | 8000 | 0.621636 | 0.619012 | 0.002624 ± 0.005649 | 0.75035 | 0.0812 / 2.4590 | 5.24× |
| fraction-0001 | 9950 | 0.625541 | 0.625131 | 0.000411 ± 0.001197 | 0.74835 | 0.0483 / 3.1917 | 7.40× |
| fraction-004 | 8000 | 0.621504 | 0.621389 | 0.000115 ± 0.001410 | 0.75075 | 0.1898 / 2.6239 | 4.69× |
| epsilon-1 | 9500 | 0.627510 | 0.620872 | 0.006638 ± 0.003856 | 0.74992 | 0.0835 / 3.6882 | 7.84× |
| epsilon-8 | 9500 | 0.619683 | 0.619839 | -0.000156 ± 0.001177 | 0.75048 | 0.0844 / 3.5982 | 8.01× |
| correlation-07 | 9500 | 0.796887 | 0.796750 | 0.000137 ± 0.004465 | 0.62645 | 0.0948 / 2.2396 | 4.92× |
| dense-d-4 | 9500 | 0.604918 | 0.604992 | -0.000074 ± 0.000260 | 0.75310 | 0.0677 / 0.1954 | 1.28× |
| dense-d-16 | 9500 | 0.636384 | 0.636625 | -0.000241 ± 0.000771 | 0.76912 | 0.0825 / 3.3523 | 7.70× |
| dense-d-64 | 9500 | 0.696741 | 0.693155 | 0.003586 ± 0.005776 | 0.76505 | 0.3006 / 119.6970 | 55.46× |
| matched-events-1 | 9500 | 0.616813 | 0.616402 | 0.000411 ± 0.001010 | 0.75225 | 0.2318 / 2.2692 | 4.16× |
| matched-events-20 | 9500 | 0.619041 | 0.617493 | 0.001548 ± 0.003324 | 0.75157 | 0.0623 / 2.5325 | 5.11× |

Component ratios are sums of measured operations, excluding source IO, authenticated requests, erasure and serving. Aggregation order was fixed; fit order alternated. These are not whole-system speedups.

### Secondary prediction-distance diagnostic

Post-run analysis of saved model weights on hash-verified reconstructed public test inputs; no models are refitted. Mean squared prediction distance to the same-cell raw model isolates output perturbation, not prediction error against labels. It was added after seeing the initial endpoint-error table.

| Setting | Unclipped prediction distance, mean ± SD | Clipped prediction distance, mean ± SD |
|---|---:|---:|
| base | 0.0007458 ± 0.0001911 | 0.0006342 ± 0.0001487 |
| n-2000 | 0.0199063 ± 0.0058120 | 0.0171367 ± 0.0050169 |
| n-50000 | 0.0000226 ± 0.0000100 | 0.0000195 ± 0.0000088 |
| d-4 | 0.0000212 ± 0.0000081 | 0.0000163 ± 0.0000058 |
| d-64 | 0.0129478 ± 0.0033110 | 0.0127394 ± 0.0031481 |
| events-1 | 0.0001233 ± 0.0000509 | 0.0001110 ± 0.0000454 |
| events-20 | 0.0040365 ± 0.0015588 | 0.0034826 ± 0.0013876 |
| fraction-0001 | 0.0006146 ± 0.0001547 | 0.0005360 ± 0.0001121 |
| fraction-004 | 0.0007187 ± 0.0001387 | 0.0006290 ± 0.0001315 |
| epsilon-1 | 0.0058672 ± 0.0025030 | 0.0051848 ± 0.0023285 |
| epsilon-8 | 0.0001228 ± 0.0000525 | 0.0000997 ± 0.0000389 |
| correlation-07 | 0.0011865 ± 0.0002940 | 0.0011578 ± 0.0002905 |
| dense-d-4 | 0.0000203 ± 0.0000119 | 0.0000192 ± 0.0000125 |
| dense-d-16 | 0.0006208 ± 0.0001413 | 0.0005816 ± 0.0001331 |
| dense-d-64 | 0.0096433 ± 0.0020859 | 0.0095084 ± 0.0020080 |
| matched-events-1 | 0.0001701 ± 0.0000648 | 0.0001458 ± 0.0000548 |
| matched-events-20 | 0.0028596 ± 0.0014283 | 0.0025099 ± 0.0013148 |

## Paired stronger-control comparison

Negative differences favor keeping the public Gram diagonal exact. These are alternative whole training pipelines sharing data and privacy draws, not updates to identical original model bytes.

| Setting | Exact-public-diagonal minus full-noise endpoint error, mean ± SD |
|---|---:|
| base | 0.0001599 ± 0.0007868 |
| n-2000 | -0.0045225 ± 0.0039905 |
| n-50000 | -0.0000662 ± 0.0001557 |
| d-4 | -0.0000180 ± 0.0002794 |
| d-64 | -0.0003195 ± 0.0035761 |
| events-1 | -0.0001685 ± 0.0006148 |
| events-20 | -0.0009021 ± 0.0021930 |
| fraction-0001 | -0.0004754 ± 0.0008970 |
| fraction-004 | -0.0000783 ± 0.0012520 |
| epsilon-1 | 0.0008628 ± 0.0012678 |
| epsilon-8 | 0.0000143 ± 0.0003920 |
| correlation-07 | -0.0004323 ± 0.0010776 |
| dense-d-4 | -0.0000373 ± 0.0001723 |
| dense-d-16 | -0.0002852 ± 0.0003023 |
| dense-d-64 | 0.0001252 ± 0.0014768 |
| matched-events-1 | 0.0000628 ± 0.0003683 |
| matched-events-20 | -0.0003012 ± 0.0025513 |
