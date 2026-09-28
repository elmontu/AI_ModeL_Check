# Cap sensitivity and sanitized-table controls

This is a retrospective extension of the preserved ACS study. The new specification was frozen before running these analyses, after the historical findings and the critique were known. No target model was fitted or executed; no new randomized-response draw or attack classifier was fitted. Thresholds and retained attack prefixes were selected deterministically from the original calibration labels.

## Cap sensitivity

The absolute grid is epsilon = 0, 0.25, ..., 30. The grid was specified independently of complete-accounting expenditure. There are 121 caps, ten saved proposal histories and four rules: 4,840 history/rule/cap records. Each rule starts empty and updates only after its own admissions. A complete-dependency shadow ledger follows that same accepted history. Disagreement with a different rule's history is not counted as an unsafe admission.

The critique about the original caps is correct. In all eight fixed-arm histories, the original cap exactly equals the maximum complete cost of all ten proposals:

| Channel policy | Per-channel epsilon | Original cap | Full-proposal maximum | Slack |
|---|---:|---:|---:|---:|
| Cached | 1 | 1 | 1 | 0 |
| Fresh serving | 1 | 5 | 5 | 0 |
| Cached | 3 | 3 | 3 | 0 |
| Fresh serving | 3 | 15 | 15 | 0 |

Each row has two source cache/model-fit replicates. The mixed histories share an identical proposal sequence whose full-proposal cost is 8; their original caps are 8 and 3. These are two cap conditions, not independent release orders.

The sweep finds complete-bound violations from training-only accounting at intermediate caps in the fresh-serving histories: epsilon-1 channels at grid caps 1 through 4.75, and epsilon-3 channels at grid caps 3 through 14.75. Each such interval occurs in both replicates. Cached and mixed histories have no training-only over-cap admissions anywhere on this grid. The original caps still yield the original null result: training-only changes no admission and causes no over-cap admission there.

An over-cap admission means the declared complete-dependency upper bound exceeds the cap. It is not a measurement of tight privacy loss or a new successful inference attack. Multiple admissions after a cap breach are counted as admissions leaving the bound above cap; they are not independent privacy events. The unit-admission-event count can count the same unit at several admitted steps.

Exact grouped accounting reproduces complete per-record accounting in every one of the 1,210 history/cap combinations. Seven offline roster-membership atoms suffice in each history. The implementation checks dense per-unit charge arrays against the expanded grouped arrays. Grouping uses the known fixed roster family, including future proposals; this analysis measures neither physical storage nor online refinement overhead.

Per-release accounting is a deliberately conservative no-reuse diagnostic. Training-only is a deliberately incomplete-dependency diagnostic. Neither represents an implementation of Sage, PrivateKube or a competing scheduling policy. Curves are conditional on these fixed proposals and access arrangements, not universal advantages. There is no meaningful probabilistic average over the chosen grid.

Data: [per-history curves](caps/curves.csv), [fixed/mixed aggregate curves](caps/aggregate-curves.csv), [original caps](caps/original-caps.csv), [checks and violation ranges](caps/results.json). `cap_to_complete_full_cost` is a secondary descriptive normalization; it was not used to choose the grid.

## Direct sanitized-table control

The primary control publishes exactly the sanitized channel cells underlying the training and serving dependencies of each original admitted prefix. It uses the preserved RR caches and the same complete per-record privacy upper bound as the original package history. It does not publish the entire mixed-cache archive. Table publication is a more informative output interface; matching dependencies and accounting does not make the output transcripts identical.

The secondary control publishes only serving-channel cells. This isolates the difference between observing a sanitized bit directly and recovering it from a model score. In fresh-serving histories, the complete table additionally exposes cached training bits for relevant member records. Neither control draws new noise.

The attack starts with the frozen no-model scores using public covariates and income labels. Each observed named cache contributes one RR likelihood factor per record, even if several releases reuse it. Only the disjoint `ref_cal` labels select thresholds and the best retained prefix. `eval_member` and `eval_nonmember` remain held out. This is a finite plug-in attack; neither calibrated priors nor observed scores are claimed to form an optimal posterior.

Final member balanced accuracy, averaged over the two fixed cache/model-fit replicates:

| Setting | Original full linked scores | Serving-cell table | Complete-dependency table |
|---|---:|---:|---:|
| Cached, epsilon 1 | 75.937% | 75.937% | 75.937% |
| Fresh serving, epsilon 1 | 86.879% | 87.013% | 88.749% |
| Cached, epsilon 3 | 94.851% | 94.851% | 94.851% |
| Fresh serving, epsilon 3 | 99.596% | 99.596% | 99.894% |

Thus the cached full-score interface shows no measured final member-attack advantage over publishing the cached table. In fresh-serving histories, the complete table's extra member observations increase this attack's success. The serving-only comparison shows that most of that difference is due to the additional training-channel observation, not a general protection supplied by model export. These comparisons do not establish that a second private channel is necessary for the task.

Nonmember differences are small and not uniformly positive. In epsilon-3 fresh serving, direct-table mean nonmember balanced accuracy is about 0.003 percentage points below the original score attack. The mixed cap-8 member comparison is also slightly negative. These finite calibration/evaluation differences are retained; greater available information does not force a particular finite calibrated attack to perform better on a held-out sample. No significance or equivalence claim is made.

The same no-model baseline, original full/rounded/label score attacks, and query-only outcomes appear in every comparison row. All 200 original full-score member/nonmember metric groups were independently rescored from their saved prediction archives during control execution. New selected-score archives are evaluator-only evidence, not proposed exports.

Data: [all prefix comparisons](tables/prefix-comparisons.csv), [all final comparisons](tables/final-comparisons.csv), [results and hashes](tables/results.json).

## Scope and reproducibility

The conditional privacy scope fixes the public record roster, covariates, income labels and training membership and changes one DIS bit. It is not full-record, membership or lifelong citizen DP. Raw truth, private randomness, mixed-cache research files and evaluator artifacts are excluded from a hypothetical protected table export. The public ACS research publication is not itself a confidential DP release. Existing unprotected releases cannot be repaired by publishing a sanitized table later.

Run `study.py freeze`, then `study.py caps` and `study.py tables` using the existing training runtime. Existing specifications/output directories are never overwritten. The six tests in `test_study.py` cover repeated-cache accounting, omitted-serving violations, own-history behavior, equality at the cap, RR likelihoods and named-channel deduplication. `verify_results.py` supplies a separate grouped-arithmetic reconstruction and attack-array check. Its completed [receipt](verification.json) verifies all 4,840 cap-policy records and 400 direct-table held-out metric groups. Historical SQLite files are opened read-only and hashes are checked before and after analysis.

The first verifier pass found a numerical tie sensitivity, preserved in `verification-first-pass-failure.json`. An algebraically equivalent posterior calculation differed by at most 3.89e-16 in the affected selected scores, but near-ties changed the best calibration balanced accuracy by about 0.0051 percentage points in 20 mixed-history prefix/view checks. The completed verifier checks both posterior agreement and exact reconstruction of the intended frozen log-odds algorithm and its calibration-only decisions. No frozen study source or result was altered. This reinforces that tiny differences between finite attacks should not be interpreted as privacy improvements.
