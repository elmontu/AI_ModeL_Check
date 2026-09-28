# Utility revision: cross

Status: complete.
Fits: 30; elapsed 823.0s. No controlled latency claim.

Three training caches Ã— three fit seeds Ã— three serving caches; fixed 2024 full RF roster and four utility periods.

| Contrast | Full-cube mean | Record interval | Independent-diagonal mean | Joint randomness t2 interval |
|---|---:|---:|---:|---:|
| both_rr1 âˆ’ degree_rr1 | +0.000557 | [+0.000066, +0.001047] | +0.000605 | [+0.000009, +0.001200] |
| degree_rr2 âˆ’ both_rr1 | +0.012926 | [+0.011128, +0.014725] | +0.013088 | [+0.012471, +0.013705] |
| degree_rr1 âˆ’ none | +0.009147 | [+0.007868, +0.010425] | +0.008945 | [+0.007541, +0.010349] |
| both_rr1 âˆ’ none | +0.009703 | [+0.008302, +0.011104] | +0.009550 | [+0.007949, +0.011151] |
| degree_rr2 âˆ’ none | +0.022630 | [+0.020386, +0.024874] | +0.022638 | [+0.021463, +0.023812] |

The full-cube estimate and diagonal estimate have different finite-sample centers. The diagonal interval uses exactly three triples treated as independent under the PRNG working model, not all 27 dependent cells. Training seeds are fixed public integers. Factor-marginal intervals and all cells are retained in results.json; they are conditional on other level sets and are not additive variance components.

Each candidate arm is an alternative package. Bound0/1/2 applies model plus one linked-score realization under joint two-bit replacement with public other fields/Y/IDs/rosters. TRAIN and utility IDs disjoint. Reused channel values are never recharged within the same candidate. Raw arms, labels, exact utility results and combined research archive have no recipient DP guarantee. Releasing all grid sanitized arms jointly composes to6 per record; all crossed sanitized candidates compose to12 per record on their roster or panel, not2; combining grids may compose further.

Report full cube mean and paired record interval separately from (a) three factor-marginal means/SD/t2 intervals conditional on other fixed level sets, (b) three diagonal t=f=s replicate effects treated as independent joint-randomness replicates under the PRNG working model, with t2 interval for total algorithm+training-channel+serving-channel variation conditional on data/panel. Training seeds are fixed public integers; secret channel draws are independent. No 27-independent-replicate claim, no joint coverage, no variance-component identification.

Illustrative cutoffs; neither practical requirements nor joint acceptance tests.

Warnings: 0. Every per-cell AUC names its score file, row filter and label source. All scenarios are exploratory public-data case studies; no universal ordering or practical privacy-utility requirement follows.
