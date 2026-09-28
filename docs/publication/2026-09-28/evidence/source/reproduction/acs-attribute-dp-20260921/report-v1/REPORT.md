# ACS model release: attribute-only differential privacy

This experiment tests whether sanitizing the sensitive attribute before training reduces tested recovery attacks while preserving ordinary prediction utility. It retains the unprotected results as a matched historical comparator. Improvement is measured, not assumed. The protection studied is a narrowly defined randomized-response mechanism on disability, not a claim that all citizen data or exported models become private.

## Completed experiment

Completed 160 protected model fits and 120 paired-release comparisons in 15.3 minutes. The study uses 10 model families, epsilon values 1.0, 3.0, 2 fit/cache realizations per epsilon, and datasets D1, D2_0, D2_50, D2_100. The public cohort contains 150,000 selected adult householders; each fit uses 50,000 records. D1 is paired with D2 at 0%, 50% and 100% overlap in the selected public record and household keys.

The historical baseline had 80 unprotected fits on the same records and model-fit seeds. The ordinary task predicts adjusted personal income above $50,000. The recipient is assumed to know ten transformed nonsensitive inputs and the income label, and has separate reference and calibration data with true disability labels. Its no-model imputation baseline receives the same information. The sensitive attribute is DIS=1 versus DIS=2 in the public ACS disability recode. No record identifiers are supplied as model features.

## SLM example: two model releases with 50% training overlap

This prespecified overlap is shown for both SLM architectures to make the paired-score result easy to inspect. Values average both fitted realizations and measure prediction of true disability, not recovery of the randomized bit. The attacker additionally receives both full-precision per-person scores. All other overlaps, families and interfaces are retained below and in the CSV files.

| SLM family | Path | Epsilon per RR draw | True-disability member BA |
| --- | --- | --- | --- |
| Miniature causal LM (small) | Historical no DP | — | 100.00% |
| Miniature causal LM (small) | Cached RR | 1.0 | 75.79% |
| Miniature causal LM (small) | Fresh RR scoring | 1.0 | 80.22% |
| Miniature causal LM (small) | Raw-input bypass | 1.0 | 99.06% |
| Miniature causal LM (small) | Cached RR | 3.0 | 94.85% |
| Miniature causal LM (small) | Fresh RR scoring | 3.0 | 97.12% |
| Miniature causal LM (small) | Raw-input bypass | 3.0 | 100.00% |
| Miniature causal LM (medium) | Historical no DP | — | 100.00% |
| Miniature causal LM (medium) | Cached RR | 1.0 | 75.53% |
| Miniature causal LM (medium) | Fresh RR scoring | 1.0 | 79.40% |
| Miniature causal LM (medium) | Raw-input bypass | 1.0 | 98.82% |
| Miniature causal LM (medium) | Cached RR | 3.0 | 94.85% |
| Miniature causal LM (medium) | Fresh RR scoring | 3.0 | 97.11% |
| Miniature causal LM (medium) | Raw-input bypass | 3.0 | 100.00% |

## The protected object and the claim

The intervention protects one binary disability value (DIS) per fixed public record. The other ten transformed inputs, the ordinary income label, the record selection and the overlap pattern are held fixed. Neighbouring inputs differ only in one record's DIS bit. This is attribute-only differential privacy under that adjacency; it is not full-record, membership, person-level longitudinal or household differential privacy, and it is not DP-SGD. Randomized response and post-processing are established methods, not a novel DP mechanism proposed by this experiment.

Ideal binary randomized response keeps a bit with probability exp(epsilon)/(1+exp(epsilon)) and flips it otherwise. The implemented channel uses a conservative 64-bit integer threshold and records its effective epsilon in the arm contract. For either possible output, the likelihood ratio between the two possible input bits is bounded by the recorded effective exp(epsilon). Once one sanitized bit has been sampled for every record, any number of models trained only from that cached sanitized table and the fixed public information are post-processing of the same mechanism. Reusing this same cache across overlapping datasets does not itself spend another epsilon for that bit. Training randomness and a fresh model identifier do not create a fresh privacy budget.

This is a mathematical argument for the ideal randomized-response channel and its specified information flow. The empirical attacks do not prove DP; reduced attack accuracy does not establish DP, and unchanged attack accuracy does not refute DP. The guarantee bounds the effect of changing the protected bit while holding other fields fixed. It does not erase facts already inferable from correlated public information or guarantee that every sensitive value becomes difficult to guess.

## Reuse, new randomization and the bypass control

| Path | What the observer receives | Interpretation |
| --- | --- | --- |
| Cached randomized response | Models and linked scores computed using the same stored sanitized bit | Post-processing of one sampled bit; no new per-record draw merely because another model is released |
| Fresh randomized response | Linked scores computed from separately redrawn sanitized bits | Additional raw-bit access; compose the new mechanisms with prior releases and retain all observations |
| Raw-sensitive-input bypass | Linked scores computed using the original disability bit | Unprotected information path; the attribute-DP claim does not cover the complete release |

A linked score is an additional record-specific disclosure. The query-only experiment does not supply such a score. The linked-score attack compares candidate input outputs with the observed score; it may recover a sanitized bit exactly while recovering the true disability value only imperfectly. Report these two correctness targets separately. Precision reduction is not itself a DP mechanism, and output rounding cannot repair a raw-input bypass in general.

Each epsilon/cache realization is an alternative experiment arm. If four independent caches at epsilon 1, 1, 3 and 3 are jointly released for the same protected bit, basic composition gives epsilon 8, not epsilon 1 or 3. Retraining from one cache is different from collecting another independently randomized copy of the original bit. Repeated attack draws or alternative caches are not additional independent model or dataset replications.

The original unprotected model export and linked true-input scores already disclosed information in the baseline. A later protected model cannot retract those artifacts, restore secrecy or retroactively replace their exposure by a finite DP budget. The baseline and protected arms are experimental counterfactuals, not a sequence of publicly released artifacts claiming an end-to-end privacy guarantee.

## Income utility through the actual protected input path

AUC values below are means across all four training sets and both fitted realizations at each epsilon. Delta AUC is protected minus matched unprotected AUC; a negative value is retained utility loss. Full accuracy, log loss, individual fits, and cached/fresh/raw-bypass serving results remain in model_metrics.csv. Raw-bypass serving is a diagnostic and is not the protected path.

| Family | Epsilon | Fits | Unprotected AUC | Cached-RR AUC | Delta AUC |
| --- | --- | --- | --- | --- | --- |
| K-nearest neighbours | 1.0 | 8 | 0.8027 | 0.7994 | -0.0033 |
| K-nearest neighbours | 3.0 | 8 | 0.8027 | 0.8027 | -0.0000 |
| Decision tree | 1.0 | 8 | 0.7280 | 0.7239 | -0.0041 |
| Decision tree | 3.0 | 8 | 0.7280 | 0.7255 | -0.0025 |
| Random forest | 1.0 | 8 | 0.8583 | 0.8571 | -0.0012 |
| Random forest | 3.0 | 8 | 0.8583 | 0.8579 | -0.0005 |
| Extra trees | 1.0 | 8 | 0.8597 | 0.8576 | -0.0022 |
| Extra trees | 3.0 | 8 | 0.8597 | 0.8587 | -0.0011 |
| Histogram gradient boosting | 1.0 | 8 | 0.8726 | 0.8714 | -0.0012 |
| Histogram gradient boosting | 3.0 | 8 | 0.8726 | 0.8723 | -0.0004 |
| XGBoost | 1.0 | 8 | 0.8729 | 0.8722 | -0.0007 |
| XGBoost | 3.0 | 8 | 0.8729 | 0.8726 | -0.0003 |
| Logistic regression | 1.0 | 8 | 0.8676 | 0.8669 | -0.0008 |
| Logistic regression | 3.0 | 8 | 0.8676 | 0.8674 | -0.0003 |
| MLP | 1.0 | 8 | 0.8001 | 0.7982 | -0.0019 |
| MLP | 3.0 | 8 | 0.8001 | 0.8002 | +0.0001 |
| Miniature causal LM (small) | 1.0 | 8 | 0.8716 | 0.8708 | -0.0008 |
| Miniature causal LM (small) | 3.0 | 8 | 0.8716 | 0.8713 | -0.0003 |
| Miniature causal LM (medium) | 1.0 | 8 | 0.8723 | 0.8714 | -0.0009 |
| Miniature causal LM (medium) | 3.0 | 8 | 0.8723 | 0.8720 | -0.0003 |

## Query-only attribute attack: no linked true-input score

Each attack may query both candidate disability values on one or two exported models. Attack selection and its balanced-accuracy threshold use reference/calibration data only. BA is balanced accuracy. The rows below average the two fitted realizations. Changes relative to historical attacks are descriptive matched differences; no independent-population uncertainty is implied. A lower tested attack score does not itself prove a privacy guarantee.

| Family | Epsilon | Overlap | Raw member joint BA | Cached-RR member joint BA | RR gain vs no model (pp) | RR nonmember joint BA |
| --- | --- | --- | --- | --- | --- | --- |
| K-nearest neighbours | 1.0 | 0% | 69.71% | 69.96% | -0.399 | 69.36% |
| K-nearest neighbours | 1.0 | 50% | 69.78% | 69.60% | -0.753 | 69.29% |
| K-nearest neighbours | 1.0 | 100% | 70.32% | 69.83% | -0.524 | 69.43% |
| K-nearest neighbours | 3.0 | 0% | 69.71% | 69.68% | -0.670 | 69.32% |
| K-nearest neighbours | 3.0 | 50% | 69.78% | 70.14% | -0.210 | 69.75% |
| K-nearest neighbours | 3.0 | 100% | 70.32% | 70.18% | -0.176 | 69.48% |
| Decision tree | 1.0 | 0% | 70.06% | 70.24% | -0.116 | 69.52% |
| Decision tree | 1.0 | 50% | 70.13% | 70.33% | -0.022 | 69.93% |
| Decision tree | 1.0 | 100% | 70.27% | 70.27% | -0.084 | 69.65% |
| Decision tree | 3.0 | 0% | 70.06% | 69.90% | -0.451 | 69.32% |
| Decision tree | 3.0 | 50% | 70.13% | 70.33% | -0.026 | 69.50% |
| Decision tree | 3.0 | 100% | 70.27% | 70.43% | +0.076 | 69.65% |
| Random forest | 1.0 | 0% | 70.01% | 70.37% | +0.013 | 69.66% |
| Random forest | 1.0 | 50% | 70.21% | 69.96% | -0.391 | 69.52% |
| Random forest | 1.0 | 100% | 69.67% | 69.71% | -0.648 | 69.27% |
| Random forest | 3.0 | 0% | 70.01% | 69.99% | -0.360 | 69.30% |
| Random forest | 3.0 | 50% | 70.21% | 70.06% | -0.294 | 69.50% |
| Random forest | 3.0 | 100% | 69.67% | 70.69% | +0.339 | 69.71% |
| Extra trees | 1.0 | 0% | 70.46% | 69.88% | -0.477 | 69.55% |
| Extra trees | 1.0 | 50% | 70.26% | 70.43% | +0.074 | 69.45% |
| Extra trees | 1.0 | 100% | 70.46% | 70.06% | -0.292 | 69.50% |
| Extra trees | 3.0 | 0% | 70.46% | 70.37% | +0.014 | 69.53% |
| Extra trees | 3.0 | 50% | 70.26% | 70.70% | +0.342 | 69.74% |
| Extra trees | 3.0 | 100% | 70.46% | 70.66% | +0.306 | 69.72% |
| Histogram gradient boosting | 1.0 | 0% | 69.91% | 70.08% | -0.274 | 69.41% |
| Histogram gradient boosting | 1.0 | 50% | 69.75% | 70.18% | -0.176 | 69.51% |
| Histogram gradient boosting | 1.0 | 100% | 69.72% | 69.87% | -0.483 | 69.56% |
| Histogram gradient boosting | 3.0 | 0% | 69.91% | 70.15% | -0.206 | 69.36% |
| Histogram gradient boosting | 3.0 | 50% | 69.75% | 69.65% | -0.700 | 69.48% |
| Histogram gradient boosting | 3.0 | 100% | 69.72% | 70.39% | +0.039 | 69.65% |
| XGBoost | 1.0 | 0% | 69.83% | 70.07% | -0.289 | 69.42% |
| XGBoost | 1.0 | 50% | 70.05% | 70.34% | -0.011 | 69.69% |
| XGBoost | 1.0 | 100% | 70.23% | 70.20% | -0.159 | 69.61% |
| XGBoost | 3.0 | 0% | 69.83% | 70.13% | -0.220 | 69.76% |
| XGBoost | 3.0 | 50% | 70.05% | 69.94% | -0.412 | 69.50% |
| XGBoost | 3.0 | 100% | 70.23% | 69.91% | -0.444 | 69.60% |
| Logistic regression | 1.0 | 0% | 69.98% | 69.89% | -0.465 | 69.36% |
| Logistic regression | 1.0 | 50% | 69.86% | 69.85% | -0.508 | 69.51% |
| Logistic regression | 1.0 | 100% | 70.15% | 70.24% | -0.118 | 69.60% |
| Logistic regression | 3.0 | 0% | 69.98% | 69.99% | -0.365 | 69.60% |
| Logistic regression | 3.0 | 50% | 69.86% | 70.11% | -0.244 | 69.41% |
| Logistic regression | 3.0 | 100% | 70.15% | 69.85% | -0.503 | 70.08% |
| MLP | 1.0 | 0% | 69.70% | 70.46% | +0.108 | 69.61% |
| MLP | 1.0 | 50% | 70.16% | 70.06% | -0.291 | 69.50% |
| MLP | 1.0 | 100% | 70.27% | 69.99% | -0.366 | 69.37% |
| MLP | 3.0 | 0% | 69.70% | 70.20% | -0.155 | 69.63% |
| MLP | 3.0 | 50% | 70.16% | 70.43% | +0.079 | 69.65% |
| MLP | 3.0 | 100% | 70.27% | 70.27% | -0.082 | 69.53% |
| Miniature causal LM (small) | 1.0 | 0% | 70.15% | 70.18% | -0.170 | 69.65% |
| Miniature causal LM (small) | 1.0 | 50% | 70.11% | 70.11% | -0.245 | 69.59% |
| Miniature causal LM (small) | 1.0 | 100% | 70.10% | 69.95% | -0.403 | 69.44% |
| Miniature causal LM (small) | 3.0 | 0% | 70.15% | 70.30% | -0.058 | 69.36% |
| Miniature causal LM (small) | 3.0 | 50% | 70.11% | 70.03% | -0.321 | 69.57% |
| Miniature causal LM (small) | 3.0 | 100% | 70.10% | 70.26% | -0.095 | 69.50% |
| Miniature causal LM (medium) | 1.0 | 0% | 70.05% | 69.99% | -0.359 | 69.46% |
| Miniature causal LM (medium) | 1.0 | 50% | 69.89% | 69.94% | -0.410 | 69.58% |
| Miniature causal LM (medium) | 1.0 | 100% | 70.30% | 70.26% | -0.090 | 69.44% |
| Miniature causal LM (medium) | 3.0 | 0% | 70.05% | 70.13% | -0.229 | 69.55% |
| Miniature causal LM (medium) | 3.0 | 50% | 69.89% | 69.80% | -0.555 | 69.45% |
| Miniature causal LM (medium) | 3.0 | 100% | 70.30% | 70.02% | -0.331 | 69.58% |

query_metrics.csv preserves both single models, the joint attack, historical unprotected joint attacks, and no-model comparisons. Receiving another artifact cannot lower an optimal attacker's best attainable success because it can ignore the artifact. Lower fitted joint-attack scores may reflect estimator or calibration limitations and do not show that information has been removed by combining artifacts.

## Linked scores: cached inputs, fresh randomization and raw-input bypass

The score attack additionally receives one or two actual per-person income scores. It first decodes the supplied bit wherever candidate outputs distinguish it, then updates the same no-model prior with the registered randomized-response channel. Cached observations of the same bit are counted once; fresh draws are separate evidence. Its decision threshold is selected using calibration records. This is a particular informed attack, not an optimal attack over all exported weights and auxiliary information.

The historical unprotected linked-score comparator is re-evaluated with the same decoding and calibration procedure. Thus it need not equal every summary in the original baseline report, which used a different tie/fallback rule. Values below are mean true-disability BA for joint full-precision scores, with all overlaps retained. Sanitized-bit distinguishability must not be confused with true-bit correctness.

| Family | Epsilon | Overlap | Historical raw BA | Cached-RR BA | Fresh-RR BA | Raw-input bypass BA |
| --- | --- | --- | --- | --- | --- | --- |
| K-nearest neighbours | 1.0 | 0% | 96.37% | 74.92% | 78.07% | 95.95% |
| K-nearest neighbours | 1.0 | 50% | 93.91% | 75.16% | 78.27% | 94.02% |
| K-nearest neighbours | 1.0 | 100% | 90.35% | 74.45% | 78.14% | 90.71% |
| K-nearest neighbours | 3.0 | 0% | 96.37% | 91.96% | 93.00% | 96.20% |
| K-nearest neighbours | 3.0 | 50% | 93.91% | 89.98% | 90.89% | 93.66% |
| K-nearest neighbours | 3.0 | 100% | 90.35% | 87.06% | 88.15% | 90.09% |
| Decision tree | 1.0 | 0% | 84.98% | 73.07% | 74.23% | 84.00% |
| Decision tree | 1.0 | 50% | 84.83% | 72.51% | 73.93% | 83.61% |
| Decision tree | 1.0 | 100% | 82.29% | 72.61% | 73.98% | 81.21% |
| Decision tree | 3.0 | 0% | 84.98% | 82.02% | 82.63% | 84.33% |
| Decision tree | 3.0 | 50% | 84.83% | 81.86% | 82.47% | 84.12% |
| Decision tree | 3.0 | 100% | 82.29% | 79.83% | 80.56% | 81.66% |
| Random forest | 1.0 | 0% | 99.90% | 75.86% | 81.29% | 99.83% |
| Random forest | 1.0 | 50% | 99.93% | 75.85% | 81.19% | 99.90% |
| Random forest | 1.0 | 100% | 99.84% | 75.88% | 80.82% | 99.85% |
| Random forest | 3.0 | 0% | 99.90% | 94.81% | 96.95% | 99.92% |
| Random forest | 3.0 | 50% | 99.93% | 94.75% | 96.95% | 99.87% |
| Random forest | 3.0 | 100% | 99.84% | 94.81% | 96.74% | 99.86% |
| Extra trees | 1.0 | 0% | 99.98% | 75.93% | 81.36% | 99.98% |
| Extra trees | 1.0 | 50% | 100.00% | 75.94% | 81.31% | 100.00% |
| Extra trees | 1.0 | 100% | 99.98% | 75.92% | 80.85% | 99.97% |
| Extra trees | 3.0 | 0% | 99.98% | 94.84% | 97.00% | 99.97% |
| Extra trees | 3.0 | 50% | 100.00% | 94.85% | 97.13% | 100.00% |
| Extra trees | 3.0 | 100% | 99.98% | 94.82% | 96.86% | 99.97% |
| Histogram gradient boosting | 1.0 | 0% | 100.00% | 75.94% | 81.38% | 100.00% |
| Histogram gradient boosting | 1.0 | 50% | 100.00% | 75.94% | 81.31% | 100.00% |
| Histogram gradient boosting | 1.0 | 100% | 100.00% | 75.94% | 80.88% | 100.00% |
| Histogram gradient boosting | 3.0 | 0% | 100.00% | 94.85% | 97.09% | 100.00% |
| Histogram gradient boosting | 3.0 | 50% | 100.00% | 94.85% | 97.13% | 100.00% |
| Histogram gradient boosting | 3.0 | 100% | 100.00% | 94.85% | 96.90% | 100.00% |
| XGBoost | 1.0 | 0% | 100.00% | 75.94% | 81.27% | 100.00% |
| XGBoost | 1.0 | 50% | 100.00% | 75.94% | 81.31% | 100.00% |
| XGBoost | 1.0 | 100% | 100.00% | 75.94% | 80.88% | 100.00% |
| XGBoost | 3.0 | 0% | 100.00% | 94.85% | 97.09% | 100.00% |
| XGBoost | 3.0 | 50% | 100.00% | 94.85% | 97.13% | 100.00% |
| XGBoost | 3.0 | 100% | 100.00% | 94.85% | 96.90% | 100.00% |
| Logistic regression | 1.0 | 0% | 100.00% | 75.94% | 81.38% | 100.00% |
| Logistic regression | 1.0 | 50% | 100.00% | 75.94% | 81.31% | 100.00% |
| Logistic regression | 1.0 | 100% | 100.00% | 75.94% | 80.88% | 100.00% |
| Logistic regression | 3.0 | 0% | 100.00% | 94.85% | 97.09% | 100.00% |
| Logistic regression | 3.0 | 50% | 100.00% | 94.85% | 97.13% | 100.00% |
| Logistic regression | 3.0 | 100% | 100.00% | 94.85% | 96.90% | 100.00% |
| MLP | 1.0 | 0% | 99.96% | 75.92% | 81.43% | 99.98% |
| MLP | 1.0 | 50% | 99.96% | 75.87% | 81.25% | 99.98% |
| MLP | 1.0 | 100% | 99.95% | 75.88% | 80.85% | 99.97% |
| MLP | 3.0 | 0% | 99.96% | 94.85% | 97.09% | 99.97% |
| MLP | 3.0 | 50% | 99.96% | 94.83% | 97.03% | 99.96% |
| MLP | 3.0 | 100% | 99.95% | 94.79% | 96.97% | 99.97% |
| Miniature causal LM (small) | 1.0 | 0% | 100.00% | 75.64% | 79.73% | 99.08% |
| Miniature causal LM (small) | 1.0 | 50% | 100.00% | 75.79% | 80.22% | 99.06% |
| Miniature causal LM (small) | 1.0 | 100% | 100.00% | 75.71% | 79.56% | 98.69% |
| Miniature causal LM (small) | 3.0 | 0% | 100.00% | 94.85% | 97.02% | 100.00% |
| Miniature causal LM (small) | 3.0 | 50% | 100.00% | 94.85% | 97.12% | 100.00% |
| Miniature causal LM (small) | 3.0 | 100% | 100.00% | 94.84% | 96.88% | 99.98% |
| Miniature causal LM (medium) | 1.0 | 0% | 100.00% | 75.63% | 79.00% | 98.83% |
| Miniature causal LM (medium) | 1.0 | 50% | 100.00% | 75.53% | 79.40% | 98.82% |
| Miniature causal LM (medium) | 1.0 | 100% | 100.00% | 75.19% | 78.98% | 98.23% |
| Miniature causal LM (medium) | 3.0 | 0% | 100.00% | 94.85% | 96.95% | 100.00% |
| Miniature causal LM (medium) | 3.0 | 50% | 100.00% | 94.85% | 97.11% | 100.00% |
| Miniature causal LM (medium) | 3.0 | 100% | 100.00% | 94.85% | 96.88% | 99.96% |

score_disclosure_metrics.csv contains every epsilon, fit realization, family, overlap, full/rounded/label interface, single/joint access, cached/fresh/bypass policy, member/nonmember group, correctness count and comparator. Its paired bootstrap intervals are pointwise and conditional on fitted artifacts. The retained one-sided McNemar p-values test an increase in attack accuracy, not a reduction; they are unadjusted in this extension and are not evidence of DP improvement or multiplicity-adjusted balanced-accuracy effects.

The fresh path draws once for each dataset and reuses that draw across model families within the arm. For a training member, the cached training release plus two fresh scoring releases costs at most 3 epsilon under basic composition; for a nonmember the two fresh scores cost at most 2 epsilon. Releasing more dataset-specific fresh scores requires accounting for those additional draws. These comparisons hold epsilon per draw fixed, not the total privacy budget: a higher fresh-path attack score illustrates renewal and composition, not an equal-total-budget comparison of algorithms. No equal-total-budget fresh-training arm was run. The diagnostic is not a fresh unlimited-query service.

## What an exported KNN retains

KNN retains training feature vectors. The attack matches the ten known inputs and reports a sensitive value only when all exact matches agree. In the protected models that retained value is the sanitized bit. The table separately scores inferred bits against true disability and the evaluation record's cached bit. A nonmember's matched training bit need not equal that nonmember's independently sanitized bit; a matching feature pattern is not a membership or identity proof. Different arms can have different match coverage, so accuracy on matched subsets is not a fixed-subset causal comparison.

| Epsilon | Fit seed | Dataset | Group | Matches / n | Correct true DIS | No model: correct on same matches | Correct cached bit | Matched training members | True accuracy on matches |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1.0 | 20260921 | D1 | eval_member | 7,328 / 10,000 | 5423 | 5503 | 7328 | 7328 | 74.00% |
| 1.0 | 20260921 | D1 | eval_nonmember | 1,164 / 10,000 | 784 | 895 | 696 | 0 | 67.35% |
| 1.0 | 20260921 | D2_0 | eval_member | 1,213 / 10,000 | 812 | 940 | 705 | 0 | 66.94% |
| 1.0 | 20260921 | D2_0 | eval_nonmember | 1,144 / 10,000 | 768 | 870 | 668 | 0 | 67.13% |
| 1.0 | 20260921 | D2_50 | eval_member | 4,286 / 10,000 | 3122 | 3208 | 4035 | 3697 | 72.84% |
| 1.0 | 20260921 | D2_50 | eval_nonmember | 1,138 / 10,000 | 770 | 872 | 672 | 0 | 67.66% |
| 1.0 | 20260921 | D2_100 | eval_member | 7,328 / 10,000 | 5423 | 5503 | 7328 | 7328 | 74.00% |
| 1.0 | 20260921 | D2_100 | eval_nonmember | 1,164 / 10,000 | 784 | 895 | 696 | 0 | 67.35% |
| 1.0 | 20260922 | D1 | eval_member | 7,339 / 10,000 | 5398 | 5497 | 7339 | 7339 | 73.55% |
| 1.0 | 20260922 | D1 | eval_nonmember | 1,158 / 10,000 | 775 | 889 | 670 | 0 | 66.93% |
| 1.0 | 20260922 | D2_0 | eval_member | 1,221 / 10,000 | 826 | 947 | 702 | 0 | 67.65% |
| 1.0 | 20260922 | D2_0 | eval_nonmember | 1,161 / 10,000 | 812 | 900 | 694 | 0 | 69.94% |
| 1.0 | 20260922 | D2_50 | eval_member | 4,296 / 10,000 | 3113 | 3208 | 4038 | 3692 | 72.46% |
| 1.0 | 20260922 | D2_50 | eval_nonmember | 1,180 / 10,000 | 807 | 905 | 696 | 0 | 68.39% |
| 1.0 | 20260922 | D2_100 | eval_member | 7,339 / 10,000 | 5398 | 5497 | 7339 | 7339 | 73.55% |
| 1.0 | 20260922 | D2_100 | eval_nonmember | 1,158 / 10,000 | 775 | 889 | 670 | 0 | 66.93% |
| 3.0 | 20260921 | D1 | eval_member | 7,749 / 10,000 | 7416 | 5882 | 7749 | 7749 | 95.70% |
| 3.0 | 20260921 | D1 | eval_nonmember | 1,404 / 10,000 | 1150 | 1105 | 1112 | 0 | 81.91% |
| 3.0 | 20260921 | D2_0 | eval_member | 1,459 / 10,000 | 1191 | 1167 | 1140 | 0 | 81.63% |
| 3.0 | 20260921 | D2_0 | eval_nonmember | 1,391 / 10,000 | 1151 | 1097 | 1116 | 0 | 82.75% |
| 3.0 | 20260921 | D2_50 | eval_member | 4,620 / 10,000 | 4291 | 3522 | 4446 | 3913 | 92.88% |
| 3.0 | 20260921 | D2_50 | eval_nonmember | 1,394 / 10,000 | 1134 | 1092 | 1092 | 0 | 81.35% |
| 3.0 | 20260921 | D2_100 | eval_member | 7,749 / 10,000 | 7416 | 5882 | 7749 | 7749 | 95.70% |
| 3.0 | 20260921 | D2_100 | eval_nonmember | 1,404 / 10,000 | 1150 | 1105 | 1112 | 0 | 81.91% |
| 3.0 | 20260922 | D1 | eval_member | 7,753 / 10,000 | 7422 | 5888 | 7753 | 7753 | 95.73% |
| 3.0 | 20260922 | D1 | eval_nonmember | 1,386 / 10,000 | 1108 | 1087 | 1063 | 0 | 79.94% |
| 3.0 | 20260922 | D2_0 | eval_member | 1,468 / 10,000 | 1201 | 1172 | 1152 | 0 | 81.81% |
| 3.0 | 20260922 | D2_0 | eval_nonmember | 1,402 / 10,000 | 1161 | 1105 | 1121 | 0 | 82.81% |
| 3.0 | 20260922 | D2_50 | eval_member | 4,635 / 10,000 | 4311 | 3524 | 4470 | 3915 | 93.01% |
| 3.0 | 20260922 | D2_50 | eval_nonmember | 1,397 / 10,000 | 1134 | 1095 | 1095 | 0 | 81.17% |
| 3.0 | 20260922 | D2_100 | eval_member | 7,753 / 10,000 | 7422 | 5888 | 7753 | 7753 | 95.73% |
| 3.0 | 20260922 | D2_100 | eval_nonmember | 1,386 / 10,000 | 1108 | 1087 | 1063 | 0 | 79.94% |

## Renewing noise: exact channel calculation, separate from model evidence

This calculation assumes a balanced prior on one binary secret and directly observed randomized-response bits. Repeating the same cached bit supplies no new channel information. Independent draws accumulate privacy loss and increasingly identify the original bit. Two draws can leave majority-vote success unchanged because of ties while still altering posterior confidence and the privacy bound. These analytic rows are not extra trained models or empirical extraction trials.

| Epsilon per draw | Releases | Cached epsilon bound | Fresh epsilon bound | Cached balanced-prior success | Fresh balanced-prior success |
| --- | --- | --- | --- | --- | --- |
| 1.0 | 1 | 1.0000 | 1.0000 | 73.11% | 73.11% |
| 1.0 | 2 | 1.0000 | 2.0000 | 73.11% | 73.11% |
| 1.0 | 5 | 1.0000 | 5.0000 | 73.11% | 87.55% |
| 1.0 | 10 | 1.0000 | 10.0000 | 73.11% | 93.48% |
| 3.0 | 1 | 3.0000 | 3.0000 | 95.26% | 95.26% |
| 3.0 | 2 | 3.0000 | 6.0000 | 95.26% | 95.26% |
| 3.0 | 5 | 3.0000 | 15.0000 | 95.26% | 99.90% |
| 3.0 | 10 | 3.0000 | 30.0000 | 95.26% | 100.00% |

## Training warnings retained

| Family | Fits with warnings | Warning |
| --- | --- | --- |
| Logistic regression | 16 / 16 | Unknown solver options: iprint |
| MLP | 16 / 16 | Stochastic Optimizer: Maximum iterations (100) reached and the optimization hasn't converged yet. |

Completion does not establish optimizer convergence. No result-dependent replacement fits or hyperparameter changes are implied by this report.

## Limits on interpreting improvement

Compare privacy and ordinary-task utility together. The main utility number must use the input the protected service would actually use: the sanitized sensitive bit. Feeding the true disability value back into protected models solely to improve utility recreates the bypass and is not the utility of the protected protocol. A drop in true-bit recovery at epsilon 1 or 3 is useful evidence about these attacks only; a lower utility score is a retained cost, not a result to discard.

All model families, overlaps, seeds, negative results and training warnings are retained. Two fit seeds on fixed training records are not independently sampled populations. Each replicate pairs a new system-random cache with another model-fit seed; differences do not isolate optimization variance. The public model-fit seed does not generate the response flips. Paired evaluation-record bootstrap intervals, when supplied, condition on the fitted artifacts and sampled cohort. They do not measure uncertainty over new agency datasets or provide a universal worst-case adversarial bound.

The two SLMs are miniature structured-record causal language models trained from scratch, not pretrained natural-language SLMs. Their next-token loss includes the sensitive token; the classical classifiers optimize the ordinary income target. The paired releases use two instances of one family. They do not constitute a test of jointly releasing every family or of merging SLM weights.

The data are public ACS microdata used as a reproducible benchmark, not confidential Singapore agency records. One selected adult householder per public household key avoids same-key household overlap in the specified partition; different public keys do not establish different real citizens across years. Utility, privacy and linkage findings cannot be generalized to all records in the 44.57 GB archive or to all citizens.

The attribute-only adjacency deliberately holds correlated fields and the income label fixed. It does not establish a semantic guarantee when changing disability would also change those fields, a guarantee against inference from those fields, or protection for membership and other attributes. Those questions require a different protected unit, adjacency and mechanism, followed by new utility and attack experiments.

This extension does not include a model trained with DIS omitted. It therefore cannot establish that randomized response is preferable to dropping that input. Utility differences are descriptive means on a fixed cohort, without a noninferiority margin or confidence interval over independently sampled datasets.

Sanitization uses operating-system cryptographic randomness; the public model-fit seeds do not determine the response flips. The private evaluation cache stores realized sanitized bits so artifacts can be checked without regenerating noise. Publicly exposing the flip randomness alongside sanitized bits could undo the protection. Production still requires private randomness, protected cache access, stable internal record linkage, enforcement of every export and score path, and accounting when new raw-bit randomizations occur. No production enforcement or governmental pilot is established by these measurements.

## Evidence verification and reproducibility

Source run: <LOCAL_DRIVE_D>/model_audit_data\experiments\acs-attribute-dp-20260921\run-v1. This report verified the completed-result and registration hashes; the historical baseline and prepared-data hashes; frozen source hashes; each arm contract and private cache hash; every model metadata/prediction hash; and every pair's metadata against the consolidated results. Baseline utility and query metrics were matched back to the historical source records. It did not reload models, recompute predictions, inspect raw sensitive records or independently re-score the saved prediction arrays.

SHA-256 receipts establish consistency with these local records, not an external timestamp, external preregistration or authenticity attestation. The new experiment was locally registered before sanitization and fitting but after the historical baseline had been inspected. The proposed protected-export allowlist is estimator.joblib or language_model.pt, preprocessing.json, metadata.json and metadata.sha256: those artifacts come from training on the cached table and fixed public income labels. A public projection of the arm privacy contract can state the mechanism, adjacency and accounting. The complete privacy-contract.json also contains cache_sha256 for an archive holding both cached and fresh randomizations; that private-state commitment is excluded from the single-cache export claim.

The model directory itself is not a protected export package. study-model.json contains raw-truth utility and recovery counts, and candidate-predictions.npz includes the raw_bypass scores. Registration also binds raw-data hashes. Copying a whole model directory, registration, private evaluation state or report archive is outside the stated DP guarantee. The verifier's allowlist manifest describes an intended boundary; it does not implement or enforce export packaging. Raw-truth evaluation and diagnostic artifacts remain separate research evidence.

Files: model_metrics.csv (all fits, utility paths and warnings), query_metrics.csv (query-only attacks), score_disclosure_metrics.csv (all score paths and comparators), whitebox_metrics.csv (KNN recovery), renewal_stress.csv (exact channel calculations), REPORT.md, index.html and verification.json. No earlier evidence was overwritten.

