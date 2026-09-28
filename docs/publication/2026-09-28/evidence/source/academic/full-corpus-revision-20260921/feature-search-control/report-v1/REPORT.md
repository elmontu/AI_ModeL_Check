# Nominal feature-search control

All 24 new omitted fits completed; 24 existing RR fits were reused. The independent verifier reloaded all 48 hash-bound model artifacts and verified nominal max_features_=3 and complete training-roster root counts for every tree.

| Family | RR AUC | Omitted AUC | RR minus omission | Pointwise seed 95% interval |
|---|---:|---:|---:|---|
| Both forests | 0.846187 | 0.844891 | +0.001296 | [+0.001139, +0.001454] |
| Random forest | 0.847354 | 0.845477 | +0.001876 | [+0.001844, +0.001908] |
| Extra trees | 0.845021 | 0.844304 | +0.000717 | [+0.000431, +0.001003] |

Outcome-informed amendment after the original and 108-fit seed results disclosed the sqrt candidate-count confound. Frozen before any outcomes of these 24 new fits. Not an external preregistration or a tuning search.

Equal nominal max_features removes this specific parameter difference. Scikit-learn may inspect more features until finding a valid split; neither exactly three examined features per node nor equal total compute is claimed. Protected field availability and total feature count still differ; this is not a fully causal privacy-utility decomposition, hyperparameter optimization, or evidence that an epsilon cost is operationally necessary. The post-result amendment and all earlier outcomes are retained.

Reuse the same three completed training seeds and fixed RR training/scoring realization. A seed pairing is not identical RNG consumption across different feature spaces. No new RR draws, raw fits or RR fits.

For each family/period and family/overall aggregation, reduce to three replicate-level paired gains first. Report n=3, sample SD, min/max, and Student-t pointwise95% interval with df2. These intervals assume approximately normal independent replicate effects, are unstable with only3 seeds, and condition on fixed RR, corpus, rosters and utility panel. Families, periods, test records and seeds are not pooled as independent replications. No multiple-testing adjustment; no equivalence margin or declaration.

Separately report paired conditional record-sampling intervals averaged over fixed fitted models, preserving shared utility-record correlations. Do not combine with training-seed intervals or interpret either as RR-draw or population uncertainty.

Separate shared-record intervals are retained in results.json and paper-values.json. They concern a different conditional uncertainty source and are not combined with seed intervals. Neither statistical exclusion of zero nor a larger AUC establishes that a privacy expenditure is operationally necessary.

New fit seconds: 662.532; row-fit uses: 51,353,916; warnings: 0. These training costs are not controlled accounting-kernel timings.
