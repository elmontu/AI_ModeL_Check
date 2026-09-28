# ACS model export: sensitive-attribute recovery experiment

This is an unprotected model-export baseline on public survey records. It demonstrates what these particular exported estimators or additional disclosures reveal; it does not identify citizens, establish a privacy guarantee, or validate an agency deployment.

## Direct recovery from an exported model

KNN fit seed 20260921: matching only the ten attacker-known inputs against retained training feature vectors recovered an unambiguous sensitive value for 7,882 of 10,000 member records (78.82%). 7,882 recovered values were correct, including 916 disability-positive values. There were 2,118 conflicting matches and 0 unmatched records. True DIS was used by the evaluator to score recovery, not by the attack to select a value.

On exactly those same 7,882 matched records, the no-model imputation baseline correctly predicted 6,009 values (76.24%), including 554 true disability-positive values. The displayed lead case is the first prespecified D1 seed, not a case selected for maximum recovery. Both seeds and all training sets appear below.

DIS=1 is the ACS disability recode; DIS=2 is its negative category. The ordinary KNN income classifier legitimately retains its training feature matrix, which contains this hidden input. An exported artifact therefore provides more access than a prediction API. Agreement among all exact matches is required; ambiguous matches are withheld. Nonmember matches can arise from repeated feature patterns and are not proof that the nonmember was in training. This is direct feature retention in KNN, not evidence that every model memorizes or reveals every record.

| Fit seed | Training set | Evaluation group | Unambiguous / n | Correct / recovered | Verified DIS=1 | Same-subset baseline accuracy | Conflicts |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 20260921 | D1 | eval_member | 7,882 / 10,000 | 7,882 / 7,882 | 916 | 76.24% | 2118 |
| 20260921 | D1 | eval_nonmember | 1,493 / 10,000 | 1,243 / 1,493 | 64 | 79.24% | 1804 |
| 20260921 | D2_0 | eval_member | 1,554 / 10,000 | 1,305 / 1,554 | 66 | 80.50% | 1814 |
| 20260921 | D2_0 | eval_nonmember | 1,473 / 10,000 | 1,248 / 1,473 | 56 | 79.29% | 1798 |
| 20260921 | D2_50 | eval_member | 4,753 / 10,000 | 4,613 / 4,753 | 492 | 76.50% | 1950 |
| 20260921 | D2_50 | eval_nonmember | 1,492 / 10,000 | 1,246 / 1,492 | 60 | 78.82% | 1802 |
| 20260921 | D2_100 | eval_member | 7,882 / 10,000 | 7,882 / 7,882 | 916 | 76.24% | 2118 |
| 20260921 | D2_100 | eval_nonmember | 1,493 / 10,000 | 1,243 / 1,493 | 64 | 79.24% | 1804 |
| 20260922 | D1 | eval_member | 7,882 / 10,000 | 7,882 / 7,882 | 916 | 76.24% | 2118 |
| 20260922 | D1 | eval_nonmember | 1,493 / 10,000 | 1,243 / 1,493 | 64 | 79.24% | 1804 |
| 20260922 | D2_0 | eval_member | 1,554 / 10,000 | 1,305 / 1,554 | 66 | 80.50% | 1814 |
| 20260922 | D2_0 | eval_nonmember | 1,473 / 10,000 | 1,248 / 1,473 | 56 | 79.29% | 1798 |
| 20260922 | D2_50 | eval_member | 4,753 / 10,000 | 4,613 / 4,753 | 492 | 76.50% | 1950 |
| 20260922 | D2_50 | eval_nonmember | 1,492 / 10,000 | 1,246 / 1,492 | 60 | 78.82% | 1802 |
| 20260922 | D2_100 | eval_member | 7,882 / 10,000 | 7,882 / 7,882 | 916 | 76.24% | 2118 |
| 20260922 | D2_100 | eval_nonmember | 1,493 / 10,000 | 1,243 / 1,493 | 64 | 79.24% | 1804 |

whitebox_examples.csv contains only the first eight already-recorded masked examples per KNN fit, with inferred and evaluator DIS. It exports no original SERIALNO, names, or other raw record attributes. Repeated seeds or training sets can repeat the same evidence; do not sum these rows as distinct people.

## What was trained and compared

Completed 80 fits and 60 paired-release comparisons in 0.13 hours. The source preparation scanned 16,095,728 national 2020–2024 public-use person records and selected 150,000 eligible adult householders. Each model used 50,000 records. Training did not consume all 44.57 GB of the four-cohort archive.

D1 is paired with D2 at 0%, 50%, and 100% overlap in the selected public record and household keys. All fits within an overlap condition use the same prespecified data. The two fit seeds do not generate independent populations or necessarily distinct models. In particular, deterministic KNN fits repeat. Disjoint public keys in this cohort do not prove distinct real citizens across years.

The ordinary task predicts adjusted annual personal income above $50,000. Training inputs contain ten transformed covariates and DIS; the recipient knows the ten covariates and income label but not DIS. The primary query attack evaluates both candidate DIS inputs and trains an attribute predictor on disjoint labelled reference data. The no-model baseline receives the same known features, income label and reference labels. Calibration selects the attack algorithm, threshold and best single-model comparator; evaluation labels do not select these choices.

| Model family | Fits | Parameters (LM) | Mean income AUC | Distinct query-output signatures |
| --- | --- | --- | --- | --- |
| K-nearest neighbours | 8 | — | 0.8027 | 3 / 8 |
| Decision tree | 8 | — | 0.7280 | 8 / 8 |
| Random forest | 8 | — | 0.8583 | 8 / 8 |
| Extra trees | 8 | — | 0.8597 | 8 / 8 |
| Histogram gradient boosting | 8 | — | 0.8726 | 3 / 8 |
| XGBoost | 8 | — | 0.8729 | 3 / 8 |
| Logistic regression | 8 | — | 0.8676 | 3 / 8 |
| MLP | 8 | — | 0.8001 | 8 / 8 |
| Miniature causal LM (small) | 8 | 1381248 | 0.8716 | 8 / 8 |
| Miniature causal LM (medium) | 8 | 3221248 | 0.8723 | 8 / 8 |

The five tree families are decision tree, random forest, extra trees, histogram gradient boosting and XGBoost. The two language models are miniature causal models trained from scratch on structured record tokens, not pretrained natural-language SLMs. Their next-token objective includes sensitive tokens; the classical models optimize only the income target. Architecture and objective effects are therefore not isolated. Query-output signatures compare exact predictions only on this fixed finite pool, not functional equivalence over all inputs.

### Training warnings and limits

| Family | Fits with warnings | Retained warning |
| --- | --- | --- |
| Logistic regression | 8 / 8 | Unknown solver options: iprint |
| MLP | 8 / 8 | Stochastic Optimizer: Maximum iterations (100) reached and the optimization hasn't converged yet. |

A completed fit does not establish optimizer convergence or a well-tuned family baseline. The MLP iteration-limit warnings bound the interpretation of its utility and leakage comparisons. Warnings were retained without post-result hyperparameter changes or replacement runs.

## Primary experiment: exported-model queries, without a linked true-input score

Every model family and overlap condition is shown below. BA means balanced accuracy, the mean of sensitivity and specificity. Values are descriptive means of the two fits; gains are percentage points (pp). Positive, zero and negative outcomes are all retained. Nonmembers are household-disjoint held-out records. Gain over the imputation baseline need not be individual memorization: it may reflect population inference or limitations of the tested baseline.

| Family | Overlap | Member joint BA | Gain vs baseline (pp) | Gain vs best single (pp) | Nonmember joint BA | Nonmember gain vs baseline (pp) |
| --- | --- | --- | --- | --- | --- | --- |
| K-nearest neighbours | 0% | 69.71% | -0.640 | -0.452 | 69.27% | -0.479 |
| K-nearest neighbours | 50% | 69.78% | -0.577 | -1.128 | 69.31% | -0.438 |
| K-nearest neighbours | 100% | 70.32% | -0.033 | +0.747 | 69.65% | -0.101 |
| Decision tree | 0% | 70.06% | -0.294 | -0.404 | 69.59% | -0.155 |
| Decision tree | 50% | 70.13% | -0.225 | -0.009 | 69.56% | -0.187 |
| Decision tree | 100% | 70.27% | -0.088 | -0.024 | 69.66% | -0.084 |
| Random forest | 0% | 70.01% | -0.348 | -0.028 | 69.44% | -0.310 |
| Random forest | 50% | 70.21% | -0.144 | +0.033 | 69.33% | -0.416 |
| Random forest | 100% | 69.67% | -0.685 | -0.482 | 69.34% | -0.411 |
| Extra trees | 0% | 70.46% | +0.104 | +0.522 | 69.80% | +0.054 |
| Extra trees | 50% | 70.26% | -0.096 | +0.104 | 69.60% | -0.145 |
| Extra trees | 100% | 70.46% | +0.109 | +0.370 | 69.37% | -0.375 |
| Histogram gradient boosting | 0% | 69.91% | -0.440 | -0.064 | 69.52% | -0.231 |
| Histogram gradient boosting | 50% | 69.75% | -0.603 | -0.016 | 69.57% | -0.174 |
| Histogram gradient boosting | 100% | 69.72% | -0.630 | -0.044 | 69.44% | -0.312 |
| XGBoost | 0% | 69.83% | -0.524 | -0.403 | 69.46% | -0.291 |
| XGBoost | 50% | 70.05% | -0.301 | -0.180 | 69.22% | -0.527 |
| XGBoost | 100% | 70.23% | -0.121 | +0.000 | 69.58% | -0.169 |
| Logistic regression | 0% | 69.98% | -0.373 | -0.169 | 69.85% | +0.102 |
| Logistic regression | 50% | 69.86% | -0.492 | -0.288 | 69.42% | -0.327 |
| Logistic regression | 100% | 70.15% | -0.204 | +0.000 | 69.68% | -0.063 |
| MLP | 0% | 69.70% | -0.651 | -0.669 | 69.27% | -0.478 |
| MLP | 50% | 70.16% | -0.190 | -0.115 | 69.50% | -0.247 |
| MLP | 100% | 70.27% | -0.083 | +0.440 | 69.52% | -0.223 |
| Miniature causal LM (small) | 0% | 70.15% | -0.202 | +0.173 | 69.52% | -0.227 |
| Miniature causal LM (small) | 50% | 70.11% | -0.248 | -0.153 | 69.61% | -0.133 |
| Miniature causal LM (small) | 100% | 70.10% | -0.258 | -0.093 | 69.42% | -0.328 |
| Miniature causal LM (medium) | 0% | 70.05% | -0.300 | -0.056 | 69.61% | -0.136 |
| Miniature causal LM (medium) | 50% | 69.89% | -0.462 | -0.142 | 69.50% | -0.250 |
| Miniature causal LM (medium) | 100% | 70.30% | -0.053 | +0.203 | 69.53% | -0.218 |

The full attack_metrics.csv retains both seeds, all overlap conditions, D1-only/shared-member subgroups, both single models, the joint model, the no-model baseline, the shuffled-output control, AUC, average precision and precision/coverage at the calibration-selected threshold. Empty subgroups are retained with n=0. These gains measure the tested finite attack learners. An optimal recipient can ignore an additional model, so its best attainable inference performance cannot decrease merely from receiving more information. Failure of a fitted joint attack to improve does not establish equality of the underlying information or privacy risk.

Some fully overlapping fits have identical candidate-output vectors, notably deterministic KNN, histogram boosting, XGBoost and logistic regression. Duplicating those vectors adds no information on this query pool. Any different fitted-attack score after duplicating them is a representation, regularization or estimator-selection effect, not evidence that the duplicate disclosure added sensitive information.

Members: across 60 individual fitted-pair comparisons, joint-minus-baseline BA ranged from -0.923 to +0.320 pp. 0 pointwise BA-gain intervals lay entirely above zero. 30 adjusted accuracy tests were below 0.05; this different metric can improve through a changed class-prediction balance even when BA does not improve.

Nonmembers: across 60 individual fitted-pair comparisons, joint-minus-baseline BA ranged from -0.527 to +0.282 pp. 0 pointwise BA-gain intervals lay entirely above zero. 24 adjusted accuracy tests were below 0.05; this different metric can improve through a changed class-prediction balance even when BA does not improve.

Paired stratified-bootstrap intervals are conditional on the fitted models and fixed sampled cohort and are pointwise descriptive intervals. They are not population-level intervals over independently acquired datasets. Holm adjustment applies to the one-sided paired accuracy McNemar tests across all primary joint-vs-baseline and joint-vs-single member/nonmember comparisons. These p-values test accuracy, not balanced accuracy, and must not be presented as multiplicity-adjusted BA evidence.

## Separate diagnostic: an additional linked score computed with the true sensitive input

This diagnostic gives the recipient an extra per-record income score produced using the actual hidden DIS value. Candidate-input queries can then be compared with that observed score. This extra disclosure is not available to the primary attack. If the candidates differ, exact matching can reveal which input was used even for a nonmember. Such results demonstrate conditional input disclosure; they do not demonstrate training memorization. Rounded scores and labels reduce this distinguishability only where they collapse candidate outputs.

| Family | Overlap | Full score: identifiable fraction | 2-decimal score: fraction | Label: fraction |
| --- | --- | --- | --- | --- |
| K-nearest neighbours | 0% | 89.05% | 88.96% | 44.43% |
| K-nearest neighbours | 50% | 83.26% | 83.21% | 39.97% |
| K-nearest neighbours | 100% | 73.43% | 73.39% | 29.20% |
| Decision tree | 0% | 41.25% | 41.25% | 27.84% |
| Decision tree | 50% | 40.58% | 40.58% | 27.16% |
| Decision tree | 100% | 32.38% | 32.31% | 18.94% |
| Random forest | 0% | 99.78% | 98.77% | 17.47% |
| Random forest | 50% | 99.79% | 98.56% | 16.68% |
| Random forest | 100% | 99.69% | 97.84% | 13.70% |
| Extra trees | 0% | 99.98% | 99.59% | 20.95% |
| Extra trees | 50% | 100.00% | 99.45% | 19.96% |
| Extra trees | 100% | 99.99% | 98.88% | 17.31% |
| Histogram gradient boosting | 0% | 100.00% | 97.67% | 11.43% |
| Histogram gradient boosting | 50% | 100.00% | 97.32% | 10.91% |
| Histogram gradient boosting | 100% | 100.00% | 91.28% | 7.78% |
| XGBoost | 0% | 100.00% | 98.20% | 10.68% |
| XGBoost | 50% | 100.00% | 98.40% | 10.88% |
| XGBoost | 100% | 100.00% | 93.20% | 7.97% |
| Logistic regression | 0% | 100.00% | 98.63% | 8.97% |
| Logistic regression | 50% | 100.00% | 98.81% | 8.88% |
| Logistic regression | 100% | 100.00% | 97.95% | 7.17% |
| MLP | 0% | 99.50% | 83.56% | 27.62% |
| MLP | 50% | 99.34% | 81.80% | 27.89% |
| MLP | 100% | 99.30% | 80.24% | 26.14% |
| Miniature causal LM (small) | 0% | 100.00% | 98.72% | 10.78% |
| Miniature causal LM (small) | 50% | 100.00% | 98.81% | 10.89% |
| Miniature causal LM (small) | 100% | 100.00% | 98.32% | 10.37% |
| Miniature causal LM (medium) | 0% | 100.00% | 98.61% | 10.85% |
| Miniature causal LM (medium) | 50% | 100.00% | 98.30% | 11.42% |
| Miniature causal LM (medium) | 100% | 100.00% | 98.31% | 10.85% |

These are mean candidate-distinguishable fractions for member records with both disclosures. score_disclosure_metrics.csv contains both seeds, every interface, each single disclosure, joint disclosures, nonmembers, verified correct identifications, subset accuracy, and overall accuracy/BA including the baseline fallback for tied candidates. Distinguishability alone must not be reported as verified recovery; use the accompanying correctness counts.

## Scope, limitations and next experiment

Public-use US data, not confidential citizens or a Singapore pilot.

One householder per household and fixed discretization narrow generalizability.

Disjoint public person/household identifiers do not establish distinct citizens across survey years.

Language models are scratch-trained miniature structured-record causal LMs, not pretrained natural-language SLMs.

LMs optimize all next tokens including S; classical models optimize Y. Differences do not isolate architecture alone.

Query-based gains are relative to tested imputation algorithms, not an optimal no-model adversary.

Sensitive inference can reflect population relationships; it is not automatically individual memorization.

No DP training or privacy guarantee is tested in this unprotected baseline.

Failure of these attacks is not a privacy assurance.

Disability is deliberately present in the training input and withheld from the recipient's auxiliary features. The experiment therefore asks what this release exposes about a private input, not whether a classifier trained without disability reconstructs an absent clinical record. The known-income-label and ten-known-covariate assumptions are substantial. Different auxiliary knowledge, continuous features, release interfaces and independently sampled datasets require new experiments.

No DP training is used. Public-use disclosure control is not asserted to be differential privacy. Fresh training randomness, overlapping releases and record identifiers do not confer a compositional privacy guarantee. Appropriate follow-up is to test a specified protected training/release mechanism under the same attacker information, utility task and overlap conditions, with correct person-level accounting and independent data replications.

## Evidence and reproducibility

Run: <LOCAL_DRIVE_D>/model_audit_data\experiments\acs-leakage-20260921\run-v1. Data: <LOCAL_DRIVE_D>/model_audit_data\experiments\acs-leakage-20260921\data-v1. This report reads the completed run without modifying source evidence. The completion and registration hashes, frozen source files, prepared-data hashes, model metadata and candidate-output files were checked. Whitebox arrays were checked against the completed aggregate counts and scored against the frozen labels. Model artifacts were not reloaded or attacks rerun by this reporting script.

A separate verification hashed 160 saved model/preprocessing artifacts. It reloaded the saved KNN and reran recovery on an auxiliary file containing only X and benchmark row IDs, with no disability or income labels. Its recovered values exactly matched the original attack; the evaluator checked truth only afterward.

- [Independent saved-model replay and artifact verification](../artifact-replay-verification.json)
verification.json records the exact files read and report outputs. SHA-256 establishes consistency with these local receipts, not an external timestamp, signature or proof of experimental authenticity. This was a prospective local registration, not an externally preregistered study. The whitebox-array hashes are bound when this report is built; the original completed results bound their summary counts rather than those array hashes.

Files: model_metrics.csv (every fit and full fit metadata); attack_metrics.csv (all query attack results); score_disclosure_metrics.csv (additional-disclosure diagnostic); whitebox_metrics.csv (direct recovery counts); whitebox_examples.csv (masked examples); REPORT.md and index.html (this report).

## Primary references framing the experiment

- [Jayaraman and Evans: attribute inference versus imputation (2022)](https://arxiv.org/abs/2209.01292)
- [Mehnaz et al.: Are Your Sensitive Attributes Private? (USENIX Security 2022)](https://www.usenix.org/conference/usenixsecurity22/presentation/mehnaz)
- [Fredrikson et al.: Model Inversion Attacks that Exploit Confidence Information (CCS 2015)](https://www.cs.cmu.edu/~mfredrik/papers/fjr2015ccs.pdf)
- [US Census Bureau: 2020–2024 ACS PUMS data dictionary](https://www2.census.gov/programs-surveys/acs/tech_docs/pums/data_dict/PUMS_Data_Dictionary_2020-2024.pdf)
