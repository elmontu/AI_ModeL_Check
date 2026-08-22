# Model-family coverage

Model Release Assurance is architecture-neutral at the decision layer, but evidence is never architecture-neutral. Version 0.6 therefore separates three questions:

1. Can the release contract describe the model, task, modalities, interface, population, and portfolio?
2. Are the relevant privacy threats declared for that family and release surface?
3. Does a versioned analyzer or mechanism provide evidence with the direction and coverage needed by policy?

Only the third question can contribute to a release decision. Catalog membership is not evidence and the coverage command always emits `can_clear: false`.

## Governed catalog

The executable catalog contains 20 categories:

| Category | Examples | Primary privacy surfaces | Current route |
|---|---|---|---|
| Linear/generalized linear | logistic regression, GLM, elastic net | coefficients, scores, membership | generic floors, exact channel, or complete DP mechanism |
| Trees and ensembles | decision tree, random forest, XGBoost, LightGBM, CatBoost | leaves/paths, scores, membership, extraction | tree linkage, generic floors, exact channel, or complete DP mechanism |
| Kernel methods | SVM, kernel ridge, Gaussian process | support vectors, scores, extraction | generic floors plus a bound channel/mechanism |
| Nearest neighbour | k-NN and exemplar systems | direct exemplars, membership, linkage | dedicated worker required |
| Probabilistic/Bayesian | naïve Bayes, Bayesian networks | parameters, posterior outputs, membership | generic floors plus exact/DP evidence |
| Tabular neural networks | MLP, TabNet, tabular transformer | weights, membership, attribute and reconstruction | dedicated multi-reference/white-box worker or complete DP-SGD |
| Vision | CNN, ViT, detection, segmentation | memorized images, biometrics, inversion | modality-specific worker required |
| Speech/audio | ASR, speaker and audio models | identity, memorization, reconstruction | modality-specific worker required |
| Time series | forecasting, ARIMA, state-space models | trajectory linkage, temporal reconstruction, repeated releases | sequence-aware worker required |
| Recommender/ranking | collaborative filtering, learning to rank | preferences, user membership, adaptive queries | user-level worker required |
| Clustering/unsupervised | k-means, mixtures, topic models | cluster membership and sensitive attributes | task-specific worker required |
| Anomaly detection | isolation forest, one-class SVM | rare-person disclosure and tail behavior | tail-aware worker required |
| Embeddings/representations | encoders and feature extractors | retrieval linkage, sensitive attributes, inversion | retrieval/inversion worker required |
| Graph models | GNNs and graph embeddings | node/edge membership, link inference, neighbourhood reconstruction | graph-specific worker required |
| Generative text/LLMs | language and text-generation models | extraction, membership, RAG/tools/memory, adaptive transcripts | interactive clearance deliberately unsupported |
| Generative media | diffusion, GAN, image/audio/video generation | training-example extraction, identity/style leakage | modality-specific generation worker required |
| Multimodal foundation | VLM and multimodal foundation systems | cross-modal extraction and adaptive transcripts | interactive clearance deliberately unsupported |
| RL systems/agents | policies and agentic systems | histories, state, tools, side effects, adaptive interaction | trajectory/transcript mechanism required |
| Ensemble/composite | stacking, pipelines, mixture-of-experts | component/routing leakage and cross-component composition | complete component and joint-interface assessment |
| Custom | an unclassified future family | unidentified family and composition risks | independent review and a new versioned analyzer |

The catalog is intentionally broad enough to route classical, deep, generative, multimodal, and agentic systems. It does not pretend that the same empirical attack is valid for all of them.

## Structured model profile

Assessment v3 requires `ReleaseContract.model_profile`, which records:

- task: classification, regression, ranking, recommendation, forecasting, clustering, anomaly detection, representation, generation, retrieval, control, decision support, or a defined custom task;
- input and output modalities;
- training paradigm;
- component families for pipelines and ensembles;
- whether the system is generative; and
- whether it is stateful.

Interactive LLM contracts must have a generative text profile. Stateful profiles require an adaptive-query interface. Historical v2 contracts remain separate compatibility artifacts; the v3 core does not infer a missing profile.

## Command-line review

List the catalog:

```bash
mra model-coverage --json
```

Review a request:

```bash
mra model-coverage examples/request.json --json
```

The result reports the resolved family, declared and recommended threat kinds, structured profile, number of related releases, required dedicated workers, and `coverage_ready`. Missing recommended threats are explicit policy-review advisories rather than automatically invented mandatory harms; policy owners must justify why an omitted secret is out of scope. Unknown family names route to `custom_review_required`; they are not silently treated as ordinary predictors.

## Universal assessment sequence

For every model family:

1. bind exact model, preprocessing, wrappers, dependencies, task and modalities;
2. enumerate the complete recipient-visible interface, including local artifact access, precision, queries, state, tools and retrieval;
3. define protected units, population snapshots, secrets, priors and side information;
4. identify family- and modality-specific threats;
5. assess the complete cumulative population–secret–interface portfolio;
6. collect attack floors, screens, exact values, or mechanism ceilings without reversing their meaning;
7. reject missing source context, stale evidence, incomplete interface coverage and unsupported protocols;
8. apply utility before information minimization; and
9. authorize only the exact hash-bound release and controls that passed the final gate.

## Cumulative-release finding supplied with the update

The supplied synthetic Singapore health experiment is a useful portfolio red-team case. Under one fixed synthetic cohort, deliberately overfitting tree models, and a strong probability/counterfactual interface, equal-prior Gaussian LiRA success rose from 60.35% with one model to 70.82% with eight. Counterfactual diabetes balanced accuracy rose from 79.56% to 98.73%. The result is constructive, not representative: it uses synthetic data, one seed/order, a strong interface, and deliberately high-capacity models.

Those values are transcribed from the supplied report. Its referenced data, runner, raw predictions and manifest are not present in this repository, so this update does not claim to have independently replayed them.

The framework-level consequence is nevertheless general. A later model about the same protected population and secret cannot be assessed as an isolated file. The joint observation contains earlier prefixes as projections, and combined releases can disclose more even when each marginal release appears weak. This portfolio rule applies to every catalog family, including embeddings, forecasts, recommenders, APIs, fine-tunes and model updates.

## Honest support boundary

- The core contracts, evidence directions, decision rules, integrity checks and portfolio mathematics apply across families.
- The tree, DP, generic attack, controlled-inference and population analyzers remain the only core analyzers.
- The XGBoost worker is a strong screening workflow, not a universal tree-privacy certificate.
- The LLM profile is a preregistration linter and emits no scientific evidence.
- Most vision, audio, graph, recommender, generative-media, RL and composite releases still require dedicated workers.
- “All models” therefore means every family is classified, scoped and failed closed—not that every family can currently be cleared.
