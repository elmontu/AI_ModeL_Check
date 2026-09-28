# General trends in private model export after deletion

Completed 25 September 2026. **A simple existing approach can remove records from
its current training statistics, produce exactly the same replacement model as
private retraining, and account for the entire sequence of exported models.**
This study verifies that baseline and measures its limits. It does not establish
a new unlearning algorithm or a universal privacy–accuracy law.

An agency can keep aggregate training statistics internally, subtract a deleted
record's contribution, and build a replacement model from the remaining
statistics. Fresh privacy noise protects each new export; the privacy account
still includes every earlier model retained by the recipient. This separates
three questions: whether deletion is correct, how much computation it saves, and
how repeated exports affect prediction quality.

The [updated research plan](../research-plan-20260925.md) incorporates these
results and the [literature/evidence review](../research-plan-evidence-20260925/README.md).

## What was missing and what was executed

| Missing comparison | Completed experiment |
|---|---|
| General factors instead of named citizen attributes | Synthetic bounded features; vary sample size, dimension, correlation and sparse/dense signal |
| Actual removal rather than another export of unchanged training data | Sequential deletion and exact comparison with recomputing retained-data statistics |
| Privacy for all model versions | Fresh stage noise with one lifetime privacy allowance per logical history |
| Separating release count from loss of training data | One, five and twenty deletion events all ending with 9,500 records |
| A simpler, stronger permissible baseline | Paired control leaving the already-public Gram diagonal unnoised |
| A concrete attack through exported model weights | Reused-noise versus fresh-noise mean-model diagnostic |
| Distinguishing output perturbation from test-label error | Secondary analysis of saved weights; no additional fitting |

There are **17 settings × eight independently generated data histories**. Two
mechanism variants use the same data, test cohorts, deletion schedules and
off-diagonal/cross-product noise draws. Thus there are **136 independent data
histories, 272 paired algorithm histories and 1,984 logical model releases**,
not 272 independent populations. A third, fresh-seed confirmation adds another
136 independent data histories and 992 releases. **The final total is 272
independent data histories, 408 algorithm histories and 2,976 logical releases.**
Each initial model and each replacement is
exported as weights with fixed public metadata. Paired incremental and
recomputation fits count as one logical release because their weights agree.

The grid varies initial sample size {2,000, 10,000, 50,000}, feature dimension
{4, 16, 64}, deletion events {1, 5, 20}, per-event deletion fraction
{0.001, 0.01, 0.04}, total epsilon {1, 3, 8}, feature correlation {0, 0.7},
and sparse versus dense predictive signal. It is a controlled grid, not the full
Cartesian product. Every history has an independent 5,000-record test cohort.
The additional fixed-final-size controls use 5%, 1% and 0.25% deletion per event.
Their distributions and final counts match; their exact datasets are independent.

The model is ridge prediction with a binary label. All feature values and the
label are protected by record-replacement adjacency on a fixed public roster.
The study does not protect participation, several records belonging to one
person, or private/adaptive deletion decisions. No education, income or other
named sensitive field is part of the general design.
The synthetic generating rule is public. This is a controlled study of training
and perturbation, not evidence that protected records are necessary to predict
these labels or that a constant is the strongest possible public-only predictor.

The [initial plan](plan.json) was frozen before its full run. The
[public-diagonal plan](plan-public-diagonal.json) is an explicitly subsequent
control; it was specified before its own run. The [protocol](protocol.md)
records both. The follow-up changes the whole training pipeline, including the
initial model, so it is not a continuation of identical original model bytes.
The [confirmation plan](plan-confirmation.json) fixed the prediction-distance
endpoint and five descriptive orderings before running new, disjoint seeds.

## Results that change the research plan

**Correct removal did not require a new method for this trainer.** All 2,976
stages matched exact retained-data integer statistics, identical-noise model
weights, and predictions replayed from the exported package. The written
[analysis](theory.md) supplies the algebraic equality and ideal Gaussian privacy
argument. Numerical agreement alone is not a privacy proof. Eleven focused tests
cover the implementation and controls.

**Sample size and release count give useful controlled trends.** The table
reports the public-diagonal control, retaining the original variant in the
[complete tables](analysis-v2/tables.md). Prediction distance is the mean squared
difference between private and unperturbed predictions on the same test inputs;
it is not error against the true labels. Values are mean ± sample SD across eight
histories. This diagnostic was added after inspecting endpoint test error and
must be identified as secondary analysis.

| Factor varied | Settings | Squared prediction distance, mean ± SD |
|---|---|---|
| Initial sample size | 2,000 / 10,000 / 50,000 | 0.019906 ± 0.005812 / 0.000746 ± 0.000191 / 0.000023 ± 0.000010 |
| Deletion events, same final 9,500 rows | 1 / 5 / 20 | 0.000170 ± 0.000065 / 0.000746 ± 0.000191 / 0.002860 ± 0.001428 |
| Dimension, sparse signal | 4 / 16 / 64 | 0.000021 ± 0.000008 / 0.000746 ± 0.000191 / 0.012948 ± 0.003311 |
| Dimension, dense signal | 4 / 16 / 64 | 0.000020 ± 0.000012 / 0.000621 ± 0.000141 / 0.009643 ± 0.002086 |
| Lifetime epsilon | 1 / 3 / 8 | 0.005867 ± 0.002503 / 0.000746 ± 0.000191 / 0.000123 ± 0.000052 |

Larger samples reduced perturbation, while more releases sharing a fixed allowance
increased it. Increasing dimension increased perturbation in both tested signal
families. These observations fit the mechanism analysis: later-stage noise
variance grows linearly with the number of update events when their total privacy
allowance is fixed. The prediction-deviation bound contains a factor proportional
to noise variance divided by retained sample size squared, with additional
dimension, ridge and model-norm terms. It does not prove these empirical trends
for all datasets, trainers or allocation policies. Feature normalization also
changes the regularization geometry as dimension grows.

**Fresh-seed confirmation repeated all five specified mean orderings.** It uses
eight new histories per cell, with the same public-diagonal method. The
[confirmation tables](analysis-confirmation-v2/tables.md) preserve every cell,
sample SD, test-label error and timing; the following means summarize the fixed
prediction-distance endpoint:

| Factor | Setting order as above | Fresh-seed mean squared prediction distances |
|---|---|---|
| Sample size | 2,000 / 10,000 / 50,000 | 0.024523 / 0.000624 / 0.000027 |
| Deletion events, same final size | 1 / 5 / 20 | 0.000139 / 0.000624 / 0.002677 |
| Sparse-signal dimension | 4 / 16 / 64 | 0.000017 / 0.000624 / 0.012184 |
| Dense-signal dimension | 4 / 16 / 64 | 0.000033 / 0.000595 / 0.012851 |
| Lifetime epsilon | 1 / 3 / 8 | 0.005588 / 0.000624 / 0.000086 |

This is an internal fresh-seed replication of descriptive trends, not an external
preregistration, simultaneous significance result, estimate of a universal
scaling exponent or demonstration that test-label error is monotonic. The
discovery analysis remains labeled post hoc. The confirmation run took 20.57
seconds; timing remains a bounded microbenchmark.

**Perturbation is not the same as worsening accuracy.** With the public-diagonal
control, mean test MSE minus the same-cell raw reference is +0.010155 at n=2,000,
+0.001485 at n=10,000 and +0.000007 at n=50,000. But the sparse d=64 mean difference
is −0.001891, whereas dense d=64 is +0.003586. Random perturbation, shrinkage,
clipping and finite evaluation samples can change label error in either
direction. Neither a monotonically worsening accuracy claim nor a universal
“more attributes are worse” conclusion is supported. Raw-reference MSE also
changes across dimensions and signal types.

**The stronger control helped output stability, but did not uniformly improve
test-label error.** Removing noise from the public diagonal reduced mean squared
prediction distance in all 17 tested settings. It reduced mean test MSE in 12 of
17 settings; the other five are preserved. For n=2,000, its paired MSE difference
relative to full-Gram perturbation is −0.004523 ± 0.003991. At the base setting
the difference is +0.000160 ± 0.000787. This is a control for avoidable randomness,
not evidence of optimal private regression or statistically certified dominance.

**Incremental deletion reduced aggregation work.** In the original variant,
mean aggregation time per deletion was 0.0781 ms for updating versus 2.3517 ms
for recomputation at n=10,000,d=16. At n=50,000 it was 0.2736 versus 33.0660 ms.
Both methods still pay for projection and solving; the corresponding ratios of
measured update-stage component sums were 4.89 and 35.83. These are small in-memory
workloads with fixed aggregation order, not whole-system speedups. Source IO,
authentication, physical erasure and serving are excluded. Solve order was
alternated; timings across the two separate full runs are not a randomized
mechanism-speed comparison. The complete runs took 19.33 and 21.27 seconds.

**Reusing noise can expose a deleted value through weights alone.** Across
5,000 public synthetic intercept-model trials, the reused-noise attack recovered
the deleted binary label in 100% of trials; maximum numerical reconstruction
error was about 7.1e-15. Fresh independent noise gave 54.92% sign-attack accuracy,
close to its analytic expectation of about 55.40%. Fresh noise limits this attack;
it does not make inference impossible. This is an established cancellation
counterexample, not a novel attack or an attack on the projected ridge models.
The repeated diagnostic in the second run uses the same fixture and does not
provide 5,000 additional independent trials.

## What is proved, tested, and still missing

The [theory note](theory.md) derives sensitivity, complete-history composition,
current-state retraining equality, a simulator for that restricted state/output,
and a conservative prediction-deviation bound. It applies established Gaussian
zCDP results and private regression methods; see
[Bun and Steinke (2016)](https://arxiv.org/abs/1605.02065) and
[Wang (2018)](https://arxiv.org/abs/1803.02596). Those ingredients are not claimed
as this project's novelty. The simulation is not a UC security theorem.

Privacy parameters describe each ideal-real logical history. The public
synthetic operator records disclose reproduction seeds and diagnostics, and raw
controls are separate; they are not a private-data export package. NumPy's
numerical sampler is not a finite-machine privacy certificate. Current-state
removal assumes truthful supplied deletion contributions and does not erase the
evaluator's oracle copies or the recipient's old models. No privacy budget is
refunded after deletion.

The results close the simple feasibility question for this trainer. The remaining
publication question is whether a proposed method improves on strong existing
methods under the same requirements. In particular, the current experiments do
not compare AdaSSP, certified iterative removal, SISA or private neural training;
do not measure adaptive deletion; and do not validate pretrained SLM unlearning.
Those comparisons need matched training references and guarantees before their
timings or accuracies would be interpretable. Merely adding more named attributes
or a bigger public archive would not resolve those gaps.

The next empirical progression is (1) compare iterative logistic removal and a
strong private learner at matched history/removal bounds; (2) evaluate the
resulting procedure with stronger public-information controls and complete
initial/update/storage cost; (3) test adaptive and multi-record requests only
after defining and proving the corresponding guarantees. The current report
supports no all-model conclusion.

## Reproduction and evidence

- [Full tables](analysis-v2/tables.md), [portable numerical summary](analysis-v2/summary.json),
  [independent audit](audit.md), [initial analysis retained](analysis-v1/tables.md).
- [Fresh-seed confirmation](analysis-confirmation-v2/tables.md) and
  [confirmation numerical records](analysis-confirmation-v2/summary.json).
- [Runner](../../scripts/experiment_unlearning_general_trends.py),
  [report generator](../../scripts/report_unlearning_general_trends.py),
  [tests](../../tests/test_unlearning_general_trends.py).
- Frozen full-Gram run: `<LOCAL_DRIVE_D>/model_audit_data/experiments/unlearning-general-trends-20260925/run-v1`.
- Frozen public-diagonal run: `<LOCAL_DRIVE_D>/model_audit_data/experiments/unlearning-general-trends-20260925/run-public-diagonal-v1`.
- Frozen confirmation: `<LOCAL_DRIVE_D>/model_audit_data/experiments/unlearning-general-trends-20260925/run-confirmation-v1`.

Each D: directory holds its own source snapshot, plan, environment, operator
records, model packages and SHA-256 manifest. Reproduction must use that run's
`frozen-runner.py`, not assume the current workspace script has identical bytes.
No historical evidence was overwritten. The receipt's plan hash uses canonical
JSON with LF newlines, while the manifest hashes actual file bytes; Windows CRLF
serialization makes those two hashes different without indicating corruption.

From the repository root, with an existing Python/NumPy environment:

```powershell
python '<LOCAL_DRIVE_D>/model_audit_data/experiments/unlearning-general-trends-20260925/run-v1/frozen-runner.py' --output '<LOCAL_DRIVE_D>/model_audit_data/experiments/unlearning-general-trends-20260925/NEW-original-run'
python '<LOCAL_DRIVE_D>/model_audit_data/experiments/unlearning-general-trends-20260925/run-public-diagonal-v1/frozen-runner.py' --output '<LOCAL_DRIVE_D>/model_audit_data/experiments/unlearning-general-trends-20260925/NEW-diagonal-run'
python -m unittest discover -s tests -p test_unlearning_general_trends.py -v
```

Use a genuinely new output path. Reruns generate more public synthetic evidence;
they do not supply free repetitions for private-data studies.
