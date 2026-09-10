# Model-family coverage

Model Release Assurance is architecture-neutral at the decision layer. Its finite-channel theorem is
also model-family neutral, but evidence is never assumption-free: it must match the released channel,
decision game, population, and proof contract. The current framework separates three questions:

1. Can the release contract describe the model, task, modalities, interface, population, and portfolio?
2. Are the relevant privacy threats declared for that family and release surface?
3. Does a versioned analyzer or mechanism provide evidence with the direction and coverage needed by policy?

Only the third question can contribute to a release decision. Catalog membership is not evidence and the coverage command always emits `can_clear: false`.

The [completed ceiling experiments](../academic/paper/ceiling-experiment-results.md)
test the shared finite-channel path without establishing family-wide coverage.
Controlled XGBoost, CNN, and LLM names are labels only. The model-backed tier
uses one CNN/MNIST artifact, one XGBoost/Adult artifact, and one compact
Transformer/20-Newsgroups artifact under a categorical hidden-record game; the
Transformer is an LLM proxy. V2 preserved a failed all-family-clear criterion;
prospectively frozen corrective v3 used fresh model/sampling seeds and passed
all role-aware criteria. V3 observed no undercoverage or wrong-direction event,
resolved all four margin-eligible safe-side families, and held conservatively
near tolerance. No v3 oracle risk exceeded tolerance, so model-backed
unsafe-side/`BLOCK` power remains untested. These observations do not transfer
to another artifact, seed, population, or interface.

## Governed catalog

The executable catalog contains 20 categories:

| Category | Examples | Primary privacy surfaces | Current route |
|---|---|---|---|
| Linear/generalized linear | logistic regression, GLM, elastic net | coefficients, scores, membership | generic floors, `finite_channel_ceiling`, exact channel, or complete DP mechanism |
| Trees and ensembles | decision tree, random forest, XGBoost, LightGBM, CatBoost | leaves/paths, scores, membership, extraction | tree linkage, generic floors, `finite_channel_ceiling`, exact channel, or complete DP mechanism |
| Kernel methods | SVM, kernel ridge, Gaussian process | support vectors, scores, extraction | generic floors plus a bound channel/mechanism |
| Nearest neighbour | k-NN and exemplar systems | direct exemplars, membership, linkage | dedicated worker required |
| Probabilistic/Bayesian | naïve Bayes, Bayesian networks | parameters, posterior outputs, membership | generic floors plus exact/DP evidence |
| Tabular neural networks | MLP, TabNet, tabular transformer | weights, membership, attribute and reconstruction | `finite_channel_ceiling` for a complete enforced finite interface; otherwise dedicated multi-reference/white-box worker or complete DP-SGD |
| Vision | CNN, ViT, detection, segmentation | memorized images, biometrics, inversion | `finite_channel_ceiling` for a complete enforced finite interface; otherwise a modality-specific worker |
| Speech/audio | ASR, speaker and audio models | identity, memorization, reconstruction | modality-specific worker required |
| Time series | forecasting, ARIMA, state-space models | trajectory linkage, temporal reconstruction, repeated releases | sequence-aware worker required |
| Recommender/ranking | collaborative filtering, learning to rank | preferences, user membership, adaptive queries | user-level worker required |
| Clustering/unsupervised | k-means, mixtures, topic models | cluster membership and sensitive attributes | task-specific worker required |
| Anomaly detection | isolation forest, one-class SVM | rare-person disclosure and tail behavior | tail-aware worker required |
| Embeddings/representations | encoders and feature extractors | retrieval linkage, sensitive attributes, inversion | retrieval/inversion worker required |
| Graph models | GNNs and graph embeddings | node/edge membership, link inference, neighbourhood reconstruction | graph-specific worker required |
| Generative text/LLMs | language and text-generation models | extraction, membership, RAG/tools/memory, adaptive transcripts | `finite_channel_ceiling` only for a complete, bounded, enforced finite transcript; ordinary open-ended interaction remains unsupported |
| Generative media | diffusion, GAN, image/audio/video generation | training-example extraction, identity/style leakage | modality-specific generation worker required |
| Multimodal foundation | VLM and multimodal foundation systems | cross-modal extraction and adaptive transcripts | `finite_channel_ceiling` only for a complete, bounded, enforced finite transcript; ordinary open-ended interaction remains unsupported |
| RL systems/agents | policies and agentic systems | histories, state, tools, side effects, adaptive interaction | trajectory/transcript mechanism required |
| Ensemble/composite | stacking, pipelines, mixture-of-experts | component/routing leakage and cross-component composition | complete component and joint-interface assessment |
| Custom | an unclassified future family | unidentified family and composition risks | independent review and a new versioned analyzer |

The catalog is intentionally broad enough to route classical, deep, generative, multimodal, and agentic systems. It does not pretend that the same empirical attack is valid for all of them.

The `finite_channel_ceiling` exception applies to every governed non-custom row in the table, even
where the route cell lists only the family's usual specialized worker. It concerns the observation
channel, not a shared attack or model internals. The submission must bind the declarations, claim
labels, and evidence for a canonical exact-guess game whose ordered state semantics and exact
rational prior are frozen identically in the active policy and submitted threat, complete recipient-visible
transcript/interface, enforced finite alphabet, recipient-realizable channel, selection-valid
simultaneous multinomial coverage, approved
engine-replayed confidence-endpoint validation, exact statistical-source binding contexts, typed
game-bound prior evidence, verified nested sources, and
exact-rational outward replay.
The policy/threat game's lowest-terms rational vector is authoritative and must be repeated exactly
in the analytic `rational_prior` and typed prior evidence. The legacy float `prior` is only a
solver/display projection whose canonical-decimal entries must be within \(10^{-12}\) of their
rational counterparts; it cannot redefine the game or drive exact replay. Statistical collection is
also implementation-bounded: no more than 10,000 simultaneous cells, 10,000,000 trials per raw state
row, 2,000,000 directed terms per endpoint, and 2,000,000 directed terms across the submitted family.
Cross-entry rational and count-sum rules are runtime validations beyond what standalone JSON Schema
can express.
The reference core validates those bindings conditionally; a family name alone never activates the
path and does not prove that a live interface satisfies the claims. Deterministic point tables remain
screens with `collect_simultaneous_channel_evidence` because their channel derivation is not replayed.

## Structured model profile

Assessment v5 requires `ReleaseContract.model_profile`, which records:

- task: classification, regression, ranking, recommendation, forecasting, clustering, anomaly detection, representation, generation, retrieval, control, decision support, or a defined custom task;
- input and output modalities;
- training paradigm;
- component families for pipelines and ensembles;
- whether the system is generative; and
- whether it is stateful.

Interactive LLM contracts must have a generative text profile. Stateful profiles require an adaptive-query interface. Superseded schemas remain separate historical artifacts; the current v5 assessment core does not infer a missing profile.

## Command-line review

List the catalog:

```bash
mra model-coverage --json
```

Review a request:

```bash
mra model-coverage examples/request.json --json
```

The result reports the resolved family, declared and recommended threat kinds, structured profile,
submitter-declared lineage count, the unconditional need for an authoritative portfolio registry,
`default_clearing_paths` per declared threat,
`threats_without_default_clearing_path`, required dedicated workers, and `coverage_ready`. It emits no
coverage percentage or safety score and always emits `can_clear: false`. A listed path means only that
the shipped analyzer could produce decision-bearing upper evidence if all preconditions and the policy
tolerance are satisfied; it is not a verdict. Missing recommended threats are explicit policy-review
advisories rather than automatically invented mandatory harms; policy owners must justify why an
omitted secret is out of scope. Unknown family names route to `custom_review_required`; they are not
silently treated as ordinary predictors.

## Universal assessment sequence

For every model family:

1. bind exact model, preprocessing, wrappers, dependencies, task and modalities;
2. enumerate the complete recipient-visible interface, including local artifact access, precision, queries, state, tools and retrieval;
3. define protected units, population snapshots, secrets, priors and side information;
4. identify family- and modality-specific threats;
5. assess the complete cumulative population–secret–interface portfolio;
6. collect attack floors, screens, exact values, or mechanism ceilings without reversing their
   meaning; generic statistical floors require every accepted policy family plus a typed,
   outcome-free design registration for every planned member;
7. reject missing source context, stale evidence, incomplete interface coverage and unsupported protocols;
8. apply utility before information minimization; and
9. authorize only the exact hash-bound release and controls that passed the final gate.

## Honest support boundary

- The core contracts, evidence directions, decision rules, integrity checks and portfolio mathematics apply across families.
- In the shipped roster, an end-to-end DP ceiling, recipient-realizable tree-linkage exact evidence, or a fully replayed `finite_channel_ceiling` may clear under complete declared-interface coverage. Attack and controlled-inference/canary evidence are floors, and watermark/population evidence are screens.
- A non-DP neural release has a clearing route only when its complete released channel satisfies the finite-channel proof contract. An ordinary continuous, incomplete, or open-ended adaptive interface instead requires `redesign_interface`; more samples of a projection cannot establish a ceiling. This is an explicit adoption limitation, not evidence that the model is unsafe.
- Every shipped clearing path establishes only a single-release result against the declared interface. Portfolio optimization and live gateway conformance remain mandatory external stages.
- The XGBoost worker is a strong screening workflow, not a universal tree-privacy certificate.
- The LLM profile is a preregistration linter and emits no scientific evidence.
- Generic attack, controlled-inference, and canary floor registration binds declared dataset,
  procedure, seed, stopping, trial, low-FPR, and sealed-assignment facts by hash, but the offline core
  neither authenticates their source nor proves those declarations true or faithfully executed.
- Existing LLM, vision, training-hook, composition-scaling, and red-team runs remain screens. They require approved state-conditioned recollection under the finite-channel contract; completion of an old run cannot be restamped into evidence. The separately registered model-backed studies are evidence only for their finite-pool categorical abstractions. V2's aggregate sampler and wrapper checks were separate; v3 executed each observation through a one-use Python wrapper, checked exact sampler equivalence, and source-bound that evidence. Neither version proves deployed endpoint/OS semantics, replaces the experimentally waived attack battery, or issues an authorization.
- Most vision, audio, graph, recommender, generative-media, RL and composite releases still require dedicated workers unless their complete recipient channel meets the finite-channel proof contract.
- “All models” therefore means every family is classified, scoped and failed closed—not that every family can currently be cleared.
