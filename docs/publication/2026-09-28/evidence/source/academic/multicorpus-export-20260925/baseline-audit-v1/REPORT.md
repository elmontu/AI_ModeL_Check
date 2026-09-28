# Completed multicorpus model-export experiment: numerical audit

This is an audit of the frozen initial LR/HGB experiment. It performs no new fitting and preserves every source result. The strongest finding is heterogeneous usefulness: the same private-input construction improves the joint HMDA workload, does not raise the joint TLC demand, and harms the BTS HGB workload. Completion of the pipeline is not validation of a universally useful protocol.

## What was measured

Each corpus supplies four disjoint record panels of 50,000 rows (auxiliary, training, certification and final). The source preparation scans much larger temporal corpora; each target model uses only 50,000 training rows. There are 18 fits per corpus: two families, three input arms and three tasks. The same frozen randomized training cache is reused across the two families and three tasks. These are 54 fitted target models, not 54 independent randomization or training-dataset replications.

The primary interface gives an exported model unperturbed permitted semantic fields belonging to a new recipient input. The model's training features were either omitted, raw diagnostic inputs, or one equal-allocation categorical randomized-response cache. The cap is epsilon=1 for joint replacement of the three designated fields of one training record; labels, fixed context, membership and participation are outside this conditional feature-DP adjacency. Raw diagnostics have no finite claimed privacy bound and are not eligible for release at this cap. Releasing every saved arm together would not have the claimed finite bound.

Utility is class-balanced Brier utility: U = 1 - (mean(p² | Y=0) + mean((1-p)² | Y=1))/2. It is not accuracy. Constant p=0.5 gives exactly U=0.75 whenever both classes occur; thresholds below or equal to 0.75 cannot by themselves demonstrate useful prediction beyond that baseline. The training objective uses inverse-class-frequency weights, so natural-prevalence probability calibration is not established.

## Joint task results

The certification columns summarize the least-performing task; the grid demand is the largest common threshold on the prespecified 0.01-spaced grid supported by all three lower bounds. Raw rows show utility support only and are privacy-ineligible. Final values score all 50,000 final-panel records exactly.

| Corpus | Family | Arm | Min certification estimate | Min lower bound | Supported grid | Min final utility | Certification bottleneck |
|---|---|---|---:|---:|---:|---:|---|
| HMDA | LR | omit | 0.75631 | 0.74337 | 0.74 | 0.75734 | withdrawal_or_incompleteness |
| HMDA | HGB | omit | 0.75411 | 0.74117 | 0.74 | 0.75571 | withdrawal_or_incompleteness |
| HMDA | LR | raw | 0.83415 | 0.82121 | 0.82 | 0.83345 | denial |
| HMDA | HGB | raw | 0.84225 | 0.82931 | 0.82 | 0.83917 | denial |
| HMDA | LR | shared_equal | 0.77858 | 0.76564 | 0.76 | 0.77840 | origination |
| HMDA | HGB | shared_equal | 0.77813 | 0.76519 | 0.76 | 0.77874 | origination |
| TLC | LR | omit | 0.75350 | 0.74056 | 0.74 | 0.75345 | distance_over_10miles |
| TLC | HGB | omit | 0.74821 | 0.73527 | 0.73 | 0.74768 | base_fare_over_50 |
| TLC | LR | raw | 0.77224 | 0.75930 | 0.75 | 0.77075 | duration_over_30min |
| TLC | HGB | raw | 0.76851 | 0.75558 | 0.75 | 0.76754 | distance_over_10miles |
| TLC | LR | shared_equal | 0.75400 | 0.74106 | 0.74 | 0.75290 | duration_over_30min |
| TLC | HGB | shared_equal | 0.74796 | 0.73502 | 0.73 | 0.74492 | distance_over_10miles |
| BTS | LR | omit | 0.73141 | 0.71848 | 0.71 | 0.72570 | cancellation |
| BTS | HGB | omit | 0.68420 | 0.67126 | 0.67 | 0.67437 | cancellation |
| BTS | LR | raw | 0.72278 | 0.70984 | 0.70 | 0.72208 | cancellation |
| BTS | HGB | raw | 0.65477 | 0.64183 | 0.64 | 0.64777 | cancellation |
| BTS | LR | shared_equal | 0.72399 | 0.71105 | 0.71 | 0.71613 | cancellation |
| BTS | HGB | shared_equal | 0.61788 | 0.60495 | 0.60 | 0.61959 | cancellation |

## Task-specific shared-cache minus omission contrasts

Final-panel differences are descriptive differences for these frozen models and records. The certification intervals below are conservative differences of the existing simultaneous intervals, not new independent-model replications or population confidence intervals.

| Corpus | Family | Task | Final difference | Certification difference interval |
|---|---|---|---:|---|
| HMDA | LR | origination | +0.00813 | [-0.01768, +0.03408] |
| HMDA | LR | denial | +0.00514 | [-0.02080, +0.03096] |
| HMDA | LR | withdrawal_or_incompleteness | +0.03260 | [+0.00699, +0.05875] |
| HMDA | HGB | origination | +0.00734 | [-0.01846, +0.03329] |
| HMDA | HGB | denial | -0.00029 | [-0.02598, +0.02578] |
| HMDA | HGB | withdrawal_or_incompleteness | +0.02822 | [+0.00285, +0.05461] |
| TLC | LR | duration_over_30min | -0.00055 | [-0.02610, +0.02566] |
| TLC | LR | distance_over_10miles | +0.00101 | [-0.02476, +0.02700] |
| TLC | LR | base_fare_over_50 | +0.00682 | [-0.01874, +0.03301] |
| TLC | HGB | duration_over_30min | -0.00304 | [-0.02832, +0.02343] |
| TLC | HGB | distance_over_10miles | -0.00402 | [-0.02829, +0.02346] |
| TLC | HGB | base_fare_over_50 | -0.00276 | [-0.02558, +0.02618] |
| BTS | LR | departure_disruption | -0.00169 | [-0.02716, +0.02460] |
| BTS | LR | arrival_disruption | -0.00212 | [-0.02765, +0.02410] |
| BTS | LR | cancellation | -0.00957 | [-0.03330, +0.01845] |
| BTS | HGB | departure_disruption | -0.00544 | [-0.03058, +0.02118] |
| BTS | HGB | arrival_disruption | -0.00562 | [-0.03211, +0.01964] |
| BTS | HGB | cancellation | -0.05478 | [-0.09219, -0.04044] |

## Interpretation and failure diagnosis

HMDA: both families raise the common supported threshold from 0.74 to 0.76 under the primary interface. The smallest final shared-cache utility is about 0.778, above the constant-half comparator. This is positive finite-cohort evidence for this workload and frozen cache, not an optimality result. The raw diagnostic shows substantial additional performance, especially for withdrawal/incompleteness. The preparation explicitly does not verify whether every recorded field and missing-value pattern existed at the intended decision time; a retrospective association cannot be relabeled as a prospective at-application prediction result.

TLC: shared RR leaves the supported common threshold unchanged (.74 LR, .73 HGB). The LR fare task improves descriptively, but trip-duration performance is the joint-workload bottleneck. Improving one task does not resolve the all-task requirement. Neither candidate certifies a common threshold above the analytic .75 constant comparator. This is not proof that the permitted fields contain no useful information: the raw baseline is stronger, and no learner-independent upper bound was computed.

BTS: cancellation is the bottleneck in every arm. Its training/certification/final panels contain only 1,046/633/654 positives. Shared RR reduces final cancellation utility relative to omission by approximately .00957 (LR) and .05478 (HGB). Every fitted cancellation model is worse than the constant-half comparator, including the raw diagnostics. Thus attributing this failure solely to DP noise or intrinsic information infeasibility would be incorrect. Candidate learning, task imbalance, temporal changes and representation need diagnosis; the present run does not isolate their causal contributions. A data-independent constant fallback would meet common demands up to .75, but was not an exported candidate in this historical run and is not retroactively counted as an admission.

The conditional feature-DP mechanism attenuates each categorical field with copy weight (exp(epsilon_j)-1)/(exp(epsilon_j)+m_j-1). At epsilon_j approximately 1/3, a 65-category field has copy weight about .00605, and a 4-category field about .09000. Domain size as well as field count matters. This channel calculation helps formulate a mechanism hypothesis; it does not demonstrate that it caused every observed loss or upper-bound the achievable utility of centrally trained models.

## Uncertainty and scope

The original 95% simultaneous certification family contains six candidate bundles, three tasks and three estimands within one corpus. Each class contributes 25,000 with-replacement draws from a locked finite certification cohort; the common radius is approximately .012939. Drawing a rare positive repeatedly does not create additional independent citizens, events or future observations. The guarantee conditions on frozen models and the finite cohort. Across all three corpora the original construction yields at least 85% simultaneous coverage by a union bound, not 95%; reports do not claim pooled 95% coverage. Differences of simultaneous task intervals remain valid on the corresponding original event, with no new independence assumption.

The matched randomized inference interface is a separate control; it adds fresh input noise on every sampled occurrence. Its weaker results must not replace the primary raw-new-input export assessment. The final panel is disjoint by record key from certification, but record disjointness does not establish person disjointness. The current analysis has now inspected the final panel; any correction selected using these findings needs a fresh locked final cohort or an explicit exploratory label.

Only one training sample, one fitting seed per cell and one randomized training cache per corpus were evaluated. The three corpora are diverse record sources, but two are transportation systems and BTS is an operational-record proxy, not a citizen-privacy deployment. There is no universal all-model conclusion, no field validation, no evaluated future stress year, and no implemented repeated-history overlap experiment in this stage. A cryptographic or machine-checked security proof is not supplied by Python checks.

## Audit and provenance

The report rehashes pipeline-bound results, prepared NPZ panels, preparation companions, frozen runner/adapter code, every recipient manifest member and the shared cache. It independently recomputes primary final utilities and primary/matched certification utilities and radii from saved predictions. It verifies the joint grid against all task bounds and privacy eligibility. Models are not deserialized, and large source byte streams are not rehashed here; scan counts below are those recorded by the bound preparation receipts.

| Corpus | Source files scanned | Rows scanned | Result SHA-256 |
|---|---:|---:|---|
| HMDA | 6 | 111,905,627 | `f38149ba142ed19835c358781a0445105f1d74a414433d02ad84529cae29608d` |
| TLC | 83 | 1,480,503,022 | `ec3e3656c0b59629520a3d043964a569e56a30e9e43b9e1d58104ddb701414c9` |
| BTS | 180 | 93,900,879 | `a79173e89053fdc5ba77e1e69f78a7104e26c3c128269484121f2286c918f057` |

Machine-readable task scores, channel parameters, conservative contrast intervals, fit warnings, manifests and scope flags are in `analysis.json`. The audit does not assert that hash agreement proves a genuine source or a correct privacy mechanism.

## Next evidence that would change the conclusion

1. Include a frozen constant-half candidate and investigate rare-task losses with auxiliary-only calibration/regularization choices; retain these historical failures. Separate information limits from failure of the chosen fitted models.
2. Replicate randomized caches and training panels; compare alternative allocations or coarsenings at the same total bound using auxiliary-only selection and a fresh final cohort. Preserve joint-task bottlenecks, not just mean improvements.
3. Test genuinely repeated exports with shared, fresh, overlapping and disjoint cache dependencies, then extend model families including the planned SLMs. Their completion cannot be inferred from these 54 fits.

Reproduction: `python scripts/report_multicorpus_export_poc.py --run-root <original-run-root> --output <new-report-directory>`. The script refuses to overwrite an existing report directory.
