# Ordered model releases: cumulative privacy accounting and inference

This replay exercised 10 ordered recipient histories with 100 attempted releases: 96 were admitted within their registered attribute-DP budgets and 4 were blocked. It reused 40 distinct trained artifacts from the earlier 160-fit DP bank. It performed 0 new training runs and 0 new randomized-response draws. The results concern a local implemented release boundary and finite attacks on existing artifacts, with simulated release dates.

## What changed in this experiment

The previous comparison tested pairs within one model family. Here the first two accepted releases are a small SLM trained on D1 and a medium SLM trained on D2_50: their training records overlap by 50%, and the recipient combines their outputs. Subsequent releases add heterogeneous tree, KNN, linear and neural models. We combine evidence from separately released models; their weights are not merged. The SLMs remain miniature structured-record causal models trained from scratch, not pretrained conversational language models.

| Step | Model family | Training set |
| --- | --- | --- |
| 1 | slm_small | D1 |
| 2 | slm_medium | D2_50 |
| 3 | decision_tree | D2_0 |
| 4 | random_forest | D2_100 |
| 5 | extra_trees | D1 |
| 6 | hist_gradient_boosting | D2_50 |
| 7 | xgboost | D2_0 |
| 8 | knn | D2_100 |
| 9 | logistic_regression | D1 |
| 10 | mlp | D2_50 |

Each timeline has a separate counterfactual recipient and ledger. Source models recur across timelines and are not independent new fits. All timelines use the same public ACS cohort, reference/calibration partitions and evaluation records. Only one prespecified model/dataset order was evaluated: model family, dataset and step vary together, so gains cannot be causally attributed to overlap or architecture or generalized across release orders. Simulated one-day steps do not supply evidence about changing citizen attributes, new datasets arriving in real time, longitudinal identity resolution or an operating agency deployment.

## Cumulative budget and admission decisions

The protected unit is a stable public ACS record key. Neighbouring inputs replace that record's binary disability value while the public roster, ten other transformed inputs, income label and partitions stay fixed. This is conditional attribute DP, not membership, full-record, household or longitudinal citizen DP. Epsilon spent is accumulated per unit and per distinct underlying randomization; time, data-version names, model identifiers and revocation do not reset it. Reusing one cached randomized bit can reveal that bit more clearly through another model without creating a new randomized-response draw.

The fixed-arm cached histories reuse the training cache for scores. Fresh-score histories use the already-created dataset-specific scoring caches: 'fresh' describes independent original draws in the source bank, not newly generated randomness during replay. The two renewal histories switch between independent epsilon 1, 1, 3 and 3 training caches with a cumulative cap of 8 or 3. The cap is applied to each affected unit before commitment. Model training affects its training roster; linked scoring additionally affects its served roster, so nonmembers may still incur score-release spending.

| Timeline | Score policy | Cap | Admitted | Blocked | Final maximum spent | Charged units |
| --- | --- | --- | --- | --- | --- | --- |
| epsilon-1-seed-20260921-cached | cached | 1.0 | 10 | 0 | 1.0 | 150,000 |
| epsilon-1-seed-20260921-fresh | fresh | 5.0 | 10 | 0 | 5.0 | 150,000 |
| epsilon-1-seed-20260922-cached | cached | 1.0 | 10 | 0 | 1.0 | 150,000 |
| epsilon-1-seed-20260922-fresh | fresh | 5.0 | 10 | 0 | 5.0 | 150,000 |
| epsilon-3-seed-20260921-cached | cached | 3.0 | 10 | 0 | 3.0 | 150,000 |
| epsilon-3-seed-20260921-fresh | fresh | 15.0 | 10 | 0 | 15.0 | 150,000 |
| epsilon-3-seed-20260922-cached | cached | 3.0 | 10 | 0 | 3.0 | 150,000 |
| epsilon-3-seed-20260922-fresh | fresh | 15.0 | 10 | 0 | 15.0 | 150,000 |
| renewed-history-cap-8 | cached | 8.0 | 10 | 0 | 8.0 | 150,000 |
| renewed-history-cap-3 | cached | 3.0 | 6 | 4 | 2.0 | 150,000 |

![Maximum cumulative epsilon over protected units. These are ledger trajectories, not attack-success bounds.](privacy-budget-trajectories.svg)

| Denied timeline | Step | Requested model | Reason | Spending retained |
| --- | --- | --- | --- | --- |
| renewed-history-cap-3 | 7 | xgboost | budget_exceeded | 2.0 |
| renewed-history-cap-3 | 8 | knn | budget_exceeded | 2.0 |
| renewed-history-cap-3 | 9 | logistic_regression | budget_exceeded | 2.0 |
| renewed-history-cap-3 | 10 | mlp | budget_exceeded | 2.0 |

A blocked release contributes no package or new attack observation. Prior packages remain with the recipient, and its existing inference ability persists. budget_histograms.csv retains the complete per-step distribution of epsilon spent among charged units; the maximum alone does not describe every person's exposure. The cached/fresh comparison holds epsilon per draw fixed, not total privacy budget, and is not an equal-budget superiority test. Neither a timeline cap nor its guarantee applies to publishing the entire research archive or pooling all counterfactual recipients.

## Two different SLMs: evidence after the second release

The table reports true-disability balanced accuracy (BA), not merely decoding a randomized bit. Full precision is the score interface actually delivered. Query-only attacks get candidate model outputs without the linked scores. The raw control substitutes raw-disability scores only inside the evaluator and is excluded from every authorized recipient package.

| Timeline | Maximum epsilon | Full-score member BA | Full-score nonmember BA | Query-only member BA | Raw-control member BA |
| --- | --- | --- | --- | --- | --- |
| epsilon-1-seed-20260921-cached | 1.0 | 75.89% | 76.40% | 70.01% | 99.52% |
| epsilon-1-seed-20260921-fresh | 3.0 | 80.31% | 79.62% | 70.01% | 99.52% |
| epsilon-1-seed-20260922-cached | 1.0 | 75.64% | 76.50% | 70.11% | 98.90% |
| epsilon-1-seed-20260922-fresh | 3.0 | 79.18% | 78.94% | 70.11% | 98.90% |
| epsilon-3-seed-20260921-cached | 3.0 | 95.00% | 95.10% | 70.25% | 100.00% |
| epsilon-3-seed-20260921-fresh | 9.0 | 97.08% | 97.00% | 70.25% | 100.00% |
| epsilon-3-seed-20260922-cached | 3.0 | 94.70% | 95.24% | 70.15% | 100.00% |
| epsilon-3-seed-20260922-fresh | 9.0 | 97.15% | 96.75% | 70.15% | 100.00% |
| renewed-history-cap-8 | 1.0 | 75.89% | 76.40% | 70.01% | 99.52% |
| renewed-history-cap-3 | 1.0 | 75.89% | 76.40% | 70.01% | 99.52% |

## All accepted disclosures retained over time

The score attacker begins with the equally informed no-model prior. It decodes a sensitive-input bit where the candidate scores distinguish it, merges observations from the same real cache once, and combines independent caches through randomized-response likelihoods. A later heterogeneous model can reveal a previously ambiguous cached bit. This plug-in attack does not model every signal in the weights or informative distinguishability patterns, and is not a certified posterior. The query attacker separately fits the registered reference-data learners to all accepted candidate-output vectors.

The attacker retains the no-model baseline and every earlier prefix attack. Thresholds and the choice of an earlier prefix use only disjoint calibration labels. Best calibration BA is therefore nondecreasing, but held-out BA can still decrease because selection generalizes imperfectly. These empirical changes do not imply that an optimal recipient loses information. Exact duplicate outputs add no information; changes in fitted BA after duplicating features reflect learner selection or regularization, not new disclosure. Score and query attacks are evaluated separately, not as an optimal joint attack on all weights and scores.

![Every timeline and attempted prefix. Shading denotes blocked releases. Raw bypass is an evaluator-only control.](attribute-inference-trajectories.svg)

| Timeline | Full member BA | Rounded member BA | Label member BA | Query-only member BA | Full nonmember BA | Raw-control member BA |
| --- | --- | --- | --- | --- | --- | --- |
| epsilon-1-seed-20260921-cached | 76.00% | 75.97% | 73.23% | 70.35% | 76.43% | 99.97% |
| epsilon-1-seed-20260921-fresh | 86.82% | 85.48% | 74.45% | 70.35% | 86.95% | 99.97% |
| epsilon-1-seed-20260922-cached | 75.87% | 75.80% | 73.64% | 70.59% | 76.87% | 100.00% |
| epsilon-1-seed-20260922-fresh | 86.94% | 85.52% | 74.68% | 70.59% | 86.31% | 100.00% |
| epsilon-3-seed-20260921-cached | 95.00% | 94.96% | 83.48% | 69.96% | 95.10% | 100.00% |
| epsilon-3-seed-20260921-fresh | 99.61% | 99.49% | 84.05% | 69.96% | 99.58% | 100.00% |
| epsilon-3-seed-20260922-cached | 94.70% | 94.61% | 83.08% | 69.99% | 95.24% | 100.00% |
| epsilon-3-seed-20260922-fresh | 99.58% | 99.43% | 83.74% | 69.99% | 99.47% | 100.00% |
| renewed-history-cap-8 | 98.22% | 97.89% | 81.21% | 70.15% | 97.75% | 100.00% |
| renewed-history-cap-3 | 81.14% | 80.59% | 72.43% | 70.15% | 81.37% | 100.00% |

Rounded-to-two-decimal and label-only interfaces are counterfactual restricted views. A recipient actually given the full-precision package can use that stronger view. Per-prefix CSVs preserve member/nonmember accuracy, BA, AUC, selection metadata and pointwise paired comparisons against the no-model prediction baseline. Intervals condition on the fitted artifacts and fixed cohort. They are descriptive, not independent-population uncertainty or multiplicity-adjusted evidence; retained one-sided accuracy p-values do not test reduced attack success.

## Prediction utility of the delivered models

Utility is the new model's held-out income prediction using its actual cached/fresh input path. It is not the utility of an ensemble or cumulative service. Blocked models' source utility remains recorded but was not delivered. The temporal replay retrains no models, tunes no thresholds to evaluation labels, and does not establish privacy-utility superiority over dropping DIS or using full-record DP training.

| Timeline | Delivered models | Lowest model AUC | Highest model AUC | Mean model AUC (descriptive) |
| --- | --- | --- | --- | --- |
| epsilon-1-seed-20260921-cached | 10 | 0.7268 | 0.8724 | 0.8389 |
| epsilon-1-seed-20260921-fresh | 10 | 0.7300 | 0.8730 | 0.8392 |
| epsilon-1-seed-20260922-cached | 10 | 0.7220 | 0.8717 | 0.8393 |
| epsilon-1-seed-20260922-fresh | 10 | 0.7242 | 0.8717 | 0.8405 |
| epsilon-3-seed-20260921-cached | 10 | 0.7252 | 0.8730 | 0.8394 |
| epsilon-3-seed-20260921-fresh | 10 | 0.7227 | 0.8730 | 0.8390 |
| epsilon-3-seed-20260922-cached | 10 | 0.7248 | 0.8722 | 0.8410 |
| epsilon-3-seed-20260922-fresh | 10 | 0.7259 | 0.8725 | 0.8411 |
| renewed-history-cap-8 | 10 | 0.7268 | 0.8724 | 0.8406 |
| renewed-history-cap-3 | 6 | 0.7268 | 0.8724 | 0.8426 |

## Implemented lifecycle boundary and its limits

The local broker binds registered dataset membership, cache commitments, evidence, current local authority, artifact bytes and expiry to a release request. Prepare does not expose bytes; commit charges the relevant units atomically; delivery verifies the committed package. Strict packaging includes one estimator or language model, preprocessing and model metadata, protected linked scores and public mechanism text. Raw-input scores, raw-truth evaluations, mixed-cache archives and internal evidence receipts are excluded. This is a trusted local producer/operator prototype, not remote proof that an arbitrary submitter trained privately.

| Lifecycle exercise | Observed outcomes across timelines |
| --- | --- |
| authority_revocation | authority_inactive: 10/10 |
| evidence_invalidation | evidence_invalidated: 10/10 |
| future_expiry | authority_inactive: 10/10 |
| idempotent_commit_and_download | passed: 10/10 |
| revocation | release_revoked: 10/10 |
| revocation_preserves_spending_and_prior_attacker_observations | passed: 10/10 |

Idempotent retries retain the original receipt and spending. Expiry, revocation and evidence invalidation block future broker downloads; they cannot erase already downloaded models, refund committed privacy loss or remove prior attack observations. The expiry exercise records the first failing check (authority_inactive), not separate evidence that every possible expiry condition was independently triggered. Local authority identifiers are not authenticated agency roles. No operating-system isolation, hostile-administrator rollback protection, remote attestation or governmental deployment is established.

## Claim boundaries and evidence checks

Simulated release order, fixed ACS cohort and attribute; no observed longitudinal citizen changes.

Public record keys are stable benchmark units, not certified unique people across years.

One conditional sensitive-attribute adjacency, not full-record DP or absolute inference-risk authorization.

Local trusted producer and operator; no remote attestation, OS isolation, hostile-admin anti-rollback, or agency authentication.

Data versions and caches do not reset spending; downloaded models remain available after revocation.

Theories and unit tests are not machine-checked proofs or production guarantees.

Score and query attacks are evaluated separately; neither is an optimal joint attack on all exported weights and scores.

DP budget checks do not certify utility, legality or absence of sensitive inference.

Randomized response, its post-processing property and composition are established mechanisms. The new empirical evidence concerns implementing and exercising their declared data-to-model release boundary. Low finite-attack success does not prove DP; high success from correlated public inputs does not alone contradict it. Budget authorization does not certify legality, institutional effectiveness, acceptable utility or an absolute inference-risk threshold.

Run: <LOCAL_DRIVE_D>/model_audit_data\experiments\acs-temporal-assurance-20260921\run-v1. The report checked completion and registration hashes, source-study bindings and frozen code; all scenario summaries and ledger hashes; every prefix evidence record and attack archive; and all admitted package digests. It also checked counts, cap compliance and unchanged ledgers on denied steps. This report does not independently recompute predictions, inspect private truth, replay database transactions or establish a machine-checked proof.

An additional verification receipt was supplied and its run, result and registration bindings matched. The receipt remains a separate local artifact; its presence does not turn local consistency checks into external attestation or production certification.

Outputs: REPORT.md and index.html; static SVG/PDF plots; prefix_metrics.csv; attack_metrics.csv; utility_metrics.csv; budget_histograms.csv; scenario_summaries.csv; verification.json. Plots use the installed ReportLab LinePlot library because Matplotlib was unavailable; no dependencies were installed. All files are newly generated; historical studies and original source artifacts are not overwritten. This research report and its raw-truth metrics are outside the protected recipient package.

