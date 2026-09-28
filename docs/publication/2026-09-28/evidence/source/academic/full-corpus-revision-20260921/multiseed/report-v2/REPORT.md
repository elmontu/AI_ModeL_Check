# Cached RR versus omission: completed revision evidence

The original fitted-model comparison and the new training-seed repeats answer different uncertainty questions. They are reported separately.

The original 40-model matched mean cached-RR-minus-omission AUC is **0.001243**, with conditional pointwise 95% interval **[0.000550, 0.001936]**. Raw-referenced interval overlap does not determine this paired contrast. This positive conditional contrast does not, by itself, establish practical importance or justify spending epsilon=1.

The extension completed **108 new full-roster fits**: decision tree, random forest and extra trees; four periods; three new seeds; raw, omitted and cached-RR arms. Every seed uses the same original full registered roster and fixed 20,000-record utility panel. Model configurations were frozen before the new outcomes. Training records are approximately 2.05 to 2.21 million per fit.

The original RR1 training/scoring bits are fixed across seed repeats. These repeats vary training-algorithm randomness only, conditional on one RR realization, public data, rosters and test panel. They do not measure total mechanism variability, new-corpus variation or neural-family robustness.

## Seed-repeat paired gains

The primary gain is cached RR minus omission. Each seed averages AUC over four utility test periods. For family summaries, each seed also averages over four training periods; the fixed three-family summary additionally averages the three families. Seed SD and the Student-t interval use three replicate-level gains, not all model/test-period cells as independent observations.

| Group | Mean gain | Seed SD | Seed range | Pointwise 95% t interval (df = 2) |
| --- | ---: | ---: | --- | --- |
| All three fixed families | 0.001071 | 0.000092 | [0.000992, 0.001172] | [0.000842, 0.001299] |
| decision_tree | -0.000885 | 0.000025 | [-0.000907, -0.000858] | [-0.000947, -0.000823] |
| random_forest | 0.001732 | 0.000070 | [0.001651, 0.001775] | [0.001558, 0.001907] |
| extra_trees | 0.002366 | 0.000234 | [0.002230, 0.002636] | [0.001784, 0.002947] |
| decision_tree / 2009 | -0.003089 | 0.000077 | [-0.003141, -0.003000] | [-0.003280, -0.002898] |
| decision_tree / 2014 | -0.000208 | 0.000069 | [-0.000262, -0.000130] | [-0.000381, -0.000036] |
| decision_tree / 2019 | -0.000274 | 0.000030 | [-0.000300, -0.000241] | [-0.000349, -0.000199] |
| decision_tree / 2024 | 0.000030 | 0.000036 | [0.000006, 0.000072] | [-0.000060, 0.000120] |
| random_forest / 2009 | 0.002163 | 0.000144 | [0.002052, 0.002326] | [0.001806, 0.002521] |
| random_forest / 2014 | 0.001199 | 0.000063 | [0.001157, 0.001271] | [0.001043, 0.001355] |
| random_forest / 2019 | 0.001788 | 0.000291 | [0.001482, 0.002062] | [0.001064, 0.002511] |
| random_forest / 2024 | 0.001779 | 0.000035 | [0.001739, 0.001801] | [0.001692, 0.001867] |
| extra_trees / 2009 | 0.002494 | 0.000325 | [0.002283, 0.002868] | [0.001686, 0.003302] |
| extra_trees / 2014 | 0.001849 | 0.000514 | [0.001294, 0.002309] | [0.000571, 0.003127] |
| extra_trees / 2019 | 0.002578 | 0.000480 | [0.002095, 0.003054] | [0.001386, 0.003769] |
| extra_trees / 2024 | 0.002541 | 0.000208 | [0.002311, 0.002715] | [0.002025, 0.003057] |

With only three seeds, these t intervals depend on an approximately normal replicate-effect assumption and cannot reliably diagnose tail behavior. They are pointwise and unadjusted for the displayed multiple comparisons. A small interval or a positive result does not establish a universal gain across unseen families, channels or datasets; a nonsignificant result does not establish equivalence.

## Every predeclared family/period/seed cell

| Family | Training period | Seed replicate | Cached-RR mean AUC | Omitted mean AUC | Paired gain |
| --- | --- | --- | ---: | ---: | ---: |
| decision_tree | 2009 | 1 | 0.835618 | 0.838618 | -0.003000 |
| extra_trees | 2009 | 1 | 0.843868 | 0.841585 | 0.002283 |
| random_forest | 2009 | 1 | 0.846154 | 0.843828 | 0.002326 |
| decision_tree | 2014 | 1 | 0.838287 | 0.838549 | -0.000262 |
| extra_trees | 2014 | 1 | 0.845928 | 0.843984 | 0.001944 |
| random_forest | 2014 | 1 | 0.848515 | 0.847358 | 0.001157 |
| decision_tree | 2019 | 1 | 0.839125 | 0.839366 | -0.000241 |
| extra_trees | 2019 | 1 | 0.846084 | 0.843989 | 0.002095 |
| random_forest | 2019 | 1 | 0.848354 | 0.846535 | 0.001820 |
| decision_tree | 2024 | 1 | 0.838581 | 0.838509 | 0.000072 |
| extra_trees | 2024 | 1 | 0.843741 | 0.841143 | 0.002597 |
| random_forest | 2024 | 1 | 0.846374 | 0.844575 | 0.001799 |
| decision_tree | 2009 | 2 | 0.835522 | 0.838662 | -0.003141 |
| extra_trees | 2009 | 2 | 0.844149 | 0.841280 | 0.002868 |
| random_forest | 2009 | 2 | 0.846025 | 0.843974 | 0.002052 |
| decision_tree | 2014 | 2 | 0.838339 | 0.838469 | -0.000130 |
| extra_trees | 2014 | 2 | 0.846280 | 0.843970 | 0.002309 |
| random_forest | 2014 | 2 | 0.848518 | 0.847350 | 0.001168 |
| decision_tree | 2019 | 2 | 0.839113 | 0.839413 | -0.000300 |
| extra_trees | 2019 | 2 | 0.846519 | 0.843465 | 0.003054 |
| random_forest | 2019 | 2 | 0.848571 | 0.846509 | 0.002062 |
| decision_tree | 2024 | 2 | 0.838537 | 0.838531 | 0.000006 |
| extra_trees | 2024 | 2 | 0.843866 | 0.841554 | 0.002311 |
| random_forest | 2024 | 2 | 0.846463 | 0.844662 | 0.001801 |
| decision_tree | 2009 | 3 | 0.835538 | 0.838664 | -0.003126 |
| extra_trees | 2009 | 3 | 0.843904 | 0.841574 | 0.002330 |
| random_forest | 2009 | 3 | 0.846050 | 0.843937 | 0.002113 |
| decision_tree | 2014 | 3 | 0.838313 | 0.838547 | -0.000234 |
| extra_trees | 2014 | 3 | 0.845859 | 0.844565 | 0.001294 |
| random_forest | 2014 | 3 | 0.848723 | 0.847452 | 0.001271 |
| decision_tree | 2019 | 3 | 0.839079 | 0.839360 | -0.000281 |
| extra_trees | 2019 | 3 | 0.846128 | 0.843543 | 0.002585 |
| random_forest | 2019 | 3 | 0.848157 | 0.846675 | 0.001482 |
| decision_tree | 2024 | 3 | 0.838605 | 0.838592 | 0.000013 |
| extra_trees | 2024 | 3 | 0.843928 | 0.841212 | 0.002715 |
| random_forest | 2024 | 3 | 0.846339 | 0.844601 | 0.001739 |

## All matched arms

These descriptive AUC means equally weight seed, training period and test period within each family. They are not additional independent replications.

| Family | Raw AUC | Omitted AUC | Cached-RR AUC |
| --- | ---: | ---: | ---: |
| All three fixed families | 0.851987 | 0.842350 | 0.843421 |
| decision_tree | 0.847071 | 0.838773 | 0.837888 |
| random_forest | 0.855507 | 0.845621 | 0.847354 |
| extra_trees | 0.853382 | 0.842655 | 0.845021 |

## Separate conditional utility-record uncertainty

Averaging the fixed new models first, the shared-record paired conditional gain is 0.001071, with pointwise 95% interval [0.000274, 0.001868]. This preserves covariance from all models scoring the same utility records. It is a different conditional uncertainty analysis from the seed-repeat t interval, and the two are not combined.

## Measured execution and limits

Run wall time: 2057.760s. Summed fit/persist time: 2004.530s; utility prediction time: 15.247s. Stored recipient model artifacts: 3,106,443,143 bytes. Repeated row-fit uses: 231,092,649; this is not a distinct-record count. Fits with recorded warnings: 0.

One six-thread worker ran the repeat study. Another six-thread training workload was allowed concurrently on the same laptop; these are observed resource costs, not controlled comparative latency or throughput benchmarks. No seed was substituted and no model was retuned according to outcomes.

Omission remains the zero-protected-input-cost alternative under fixed-public-X/Y/roster attribute adjacency. Choosing RR requires a task-specific utility/privacy tradeoff; no minimum worthwhile AUC difference was prespecified here. ACS benchmark truth is public, and this controlled mechanism evaluation does not estimate real-world confidentiality.

Raw-arm AUC for every seed/model/test period is retained in the machine-readable results. The targeted three-family extension does not resolve uncertainty for the seven original families not repeated.

The unchanged random-forest and extra-trees defaults use max_features='sqrt': nine input fields in raw/RR imply three candidate split features, while omission's eight fields imply two. Thus identical configuration strings do not imply identical effective feature-search budgets. These are comparisons of the declared algorithms, not isolated causal effects of the protected information. No configuration was changed after this observation.

`paper-values.json` stores every displayed AUC/gain/interval value with a JSON pointer to its source object; that object points to each contributing prediction array, label array and period selector. Hashes bind bytes but are not the only provenance.
