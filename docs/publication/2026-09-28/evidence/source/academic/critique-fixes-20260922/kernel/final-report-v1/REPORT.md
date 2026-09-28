# Corrected kernel results

All 9 full-universe and 24 fragmentation trials passed the complete, separately implemented per-record oracle.

| Representation | Operation seconds, median [min,max] | Physical DB GiB | Whole-process peak GiB, median |
|---|---:|---:|---:|
| record | 430.579 [410.251,549.185] | 2.804352 | 3.010 |
| grouped | 322.436 [303.735,361.588] | 2.534649 | 3.015 |
| mask64 | 386.880 [386.328,427.687] | 2.323383 | 3.197 |

Record/grouped median-time ratio: 1.3354; grouped/record: 0.7488; mask/record: 0.8985.

| Full-scale phase median, seconds | Record | Grouped | Mask64 |
|---|---:|---:|---:|
| initialization_seconds | 19.952 | 21.855 | 19.870 |
| channel_registration_seconds | 0.335 | 0.213 | 0.242 |
| roster_registration_seconds | 128.094 | 299.563 | 128.053 |
| preparation_seconds | 45.459 | 0.546 | 45.643 |
| commitment_seconds | 236.864 | 0.366 | 193.094 |
| oracle_seconds | 107.158 | 96.040 | 97.707 |

Separate phase medians need not sum to the total median. The oracle is diagnostic and excluded from the accounting-operation total.

| Fragment N | Mode | Operation seconds, median [min,max] | DB MiB | Included migration seconds |
|---:|---|---:|---:|---:|
| 10000 | record | 0.923 [0.661,0.926] | 3.320 | 0.000 |
| 10000 | grouped | 1.394 [0.822,1.591] | 5.203 | 0.000 |
| 10000 | mask64 | 0.820 [0.716,0.916] | 2.641 | 0.000 |
| 10000 | adaptive | 0.896 [0.660,0.942] | 2.676 | 0.022 |
| 100000 | record | 3.785 [3.730,3.951] | 33.703 | 0.000 |
| 100000 | grouped | 5.393 [5.197,5.421] | 52.160 | 0.000 |
| 100000 | mask64 | 3.438 [3.117,3.521] | 26.566 | 0.000 |
| 100000 | adaptive | 3.791 [3.728,3.803] | 26.926 | 0.140 |

Fragmentation uses the unchanged 20-roster inputs and threshold. Migration is already within roster-registration time. The 24 full-state and decision oracles agree within each size.

| Planning pilot | Mode | Old query s | Count-only s | Durable-cache s |
|---|---|---:|---:|---:|
| pilot100k | record | 6.531 | 5.475 | 5.214 |
| pilot100k | grouped | 3.952 | 3.805 | 3.907 |
| pilot100k | mask64 | 5.672 | 4.498 | 4.418 |
| pilot1m | record | — | 37.536 | 38.091 |
| pilot1m | grouped | — | 26.000 | 25.444 |
| pilot1m | mask64 | — | 35.336 | 33.334 |

Each pilot cell is one retained run in version-major order, not a balanced repeated estimate. The cached record cell is slightly slower than count-only at 1M. Durable writes and cleanup are included, so saved planning time is not a subtractable counterfactual speedup.

The fixed full-universe structure has 25 blocks, 384 block/channel charges and 34,279,947 explicit record/roster memberships. Current grouped arrival traces match the retained public-signature reconstruction: J=16, K=132. This explains compression for this structured schedule, not arbitrary roster scalability.

The original real admission-grid boundary is driven by the 44k scoring panel. The new, separate 128-record training-driven control checks 48 decisions across three modes/two caps; all refusals have witnesses outside the query panel. It is a correctness control, not an actual model release or scale measurement.

Single-host repeated accounting operations; no privacy accountant or portable speedup claim. Nested timers, migration and cleanup are included costs. Whole-process peak includes oracle/mappings. Final physical bytes include free pages; transient journal/temp-file peaks not measured. Single-run pilot ablations are engineering evidence, not inferential comparisons.

Exact values, component timings, ratios and relative-path, byte-identical source JSON mirrors are in report.json. The cache metadata supplement reads only four small tables using SQLite mode=ro; it does not scan record state or mutate databases.
