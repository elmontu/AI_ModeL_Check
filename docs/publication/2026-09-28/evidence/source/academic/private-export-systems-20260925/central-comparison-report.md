# Trusted central-count comparator

Lower Brier loss is better. Every reference cell is retained; no method or outcome is selected after evaluation.
This standard central-DP baseline accesses raw counts and exports only fitted probability models. It does not produce a reusable row-level privatized table.

| n | Tasks | Repetitions | Central | Coupled local | Independent joint local | Public stationary | Public shifted | Central minus coupled |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1000 | 3 | 5 | 0.190084 | 0.191994 | 0.195878 | 0.190135 | 0.225943 | -0.001911 |
| 1000 | 7 | 5 | 0.210295 | 0.215594 | 0.219577 | 0.210127 | 0.246942 | -0.005299 |
| 1000 | 15 | 5 | 0.216568 | 0.223162 | 0.235022 | 0.216163 | 0.256019 | -0.006594 |
| 10000 | 3 | 5 | 0.190096 | 0.190261 | 0.190346 | 0.190135 | 0.225943 | -0.000165 |
| 10000 | 7 | 5 | 0.210137 | 0.210456 | 0.211149 | 0.210127 | 0.246942 | -0.000320 |
| 10000 | 15 | 5 | 0.216164 | 0.216646 | 0.218031 | 0.216163 | 0.256019 | -0.000481 |
| 100000 | 3 | 5 | 0.190063 | 0.190083 | 0.190087 | 0.190135 | 0.225943 | -0.000019 |
| 100000 | 7 | 5 | 0.210100 | 0.210135 | 0.210223 | 0.210127 | 0.246942 | -0.000035 |
| 100000 | 15 | 5 | 0.216130 | 0.216178 | 0.216354 | 0.216163 | 0.256019 | -0.000048 |

## Interpretation boundaries

- Same original roster, evaluation cohort and unchanged old-model prefix; fresh independent central noise.
- Each alternative old-plus-new history has total privacy odds at most nine; all alternatives together do not.
- Existing releases remain charged. The companion records incremental central charges and a conservative whole-history sum.
- The central and local mechanisms have different intermediate-output contracts. Their exported marginal models address the same tested prediction task.
- If central counts win, coupled local noise has not established a benefit for this trusted marginal-model export workload.
- If coupled local noise wins a finite cell, that alone does not establish a general ordering.
- Offline central timings exclude broker gates, serialization and durable custody; do not compare them as full-workflow speedups.
- Public synthetic evidence; five noise repetitions are not five independent populations.
