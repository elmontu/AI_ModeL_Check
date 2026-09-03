# Claims-to-evidence matrix

This matrix is the drafting gate for the paper. A statement belongs in a result
section only when its evidence row names a retained artifact and the stated
limitations travel with the claim.

## Status vocabulary

| Status | Meaning |
|---|---|
| Implemented | The behavior is represented in current source/contracts; a fresh paper-snapshot run is still needed for an outcome claim. |
| Machine-checkable | Lean source and a pinned verifier exist; the theorem applies only to the abstract model and stated premises. |
| Completed observation | A publication-safe retained audit records the run and aggregate result. |
| Registered/pending | A configuration or design exists, but no retained completion artifact supports an outcome. |
| Unsupported | The repository contains neither an eligible result nor a complete implementation of the claimed operational system. |

## Candidate claims

| ID | Safe paper wording | Status | Primary evidence | Required qualification or remaining work |
|---|---|---|---|---|
| C1 | MRA implements an offline reference core for versioned release-contract validation, evidence assessment, configuration selection, and transcript/certificate replay. | Implemented | [Root README](../README.md), [project scope](../docs/project-scope.md), and [`src/model_release_assurance`](../src/model_release_assurance/) | It does not authorize, deploy, or serve models. Re-run the complete test/schema suite at the paper commit before claiming observed conformance. |
| C2 | The decision model assigns direction to evidence: attack floors cannot clear, ceiling clearance has stricter completeness gates, and unresolved evidence holds the release. | Implemented | [Mathematical foundations](../docs/mathematical-foundations.md), [MRAP/1.0](../docs/model-release-assurance-protocol.md), and [test map](../tests/README.md) | This is an implementation/specification claim, not proof that submitted evidence is scientifically true or complete. Include fresh negative-fixture results. |
| C3 | The reference core contains a model-family-neutral finite-channel analyzer for a complete, enforced finite recipient channel and a policy-frozen exact-guess game. | Implemented | [Finite-channel schema](../schemas/finite-channel-ceiling-submission-v1.json), [model coverage](../docs/model-family-coverage.md), and [finite-channel analyzer](../src/model_release_assurance/analyzers/finite_channel.py) | Decision-bearing use requires engine-replayed simultaneous evidence and exact bindings. Existing model experiments do not meet this contract and remain screens. |
| C4 | Within the Lean transition semantics, reachable active states satisfy the documented authorization-integrity and binding predicates; separate theorems cover ideal deployment, authenticated-step projection, and finite statistical accounting. | Machine-checkable | [Formal claim boundary](../docs/formal-verification.md), [Lean package](../formal/lean/), and [protocol correspondence](../formal/protocol-correspondence-v1.json) | Never generalize to Python or production infrastructure; no refinement proof exists. Re-run the pinned wrapper and retain its transcript for the submission. |
| C5 | Aggregate training hooks completed end-to-end real-data runs for DistilGPT2, OPT-125M, Pythia-160M, AlexNet, and DenseNet-121. | Completed observation | [2026-09-02 execution audit](../docs/real-data-training-hook-audit-2026-09-02.md) | Five architectures across two modalities, one registered GPU stack, one epoch/model, and one seed. “Completed” means experimental execution, not assessment or authorization. |
| C6 | The completed LLM worker recorded and replayed 3,072 forward and 3,072 backward aggregate-hook observations; each vision chain recorded 507 of each, with the audit reporting complete registered coverage. | Completed observation | [Execution audit](../docs/real-data-training-hook-audit-2026-09-02.md) | Coverage is relative to the registered modules/parameters. Hooks retained bounded aggregates, not per-example tensors. It does not establish production reliability or CUDA-wide non-interference. |
| C7 | The completed case study used a 9,216-row pinned WildChat cohort and all 27,000 EuroSAT images, so the demonstrated integration is not limited to synthetic or tiny fixture execution. | Completed observation | [Execution audit](../docs/real-data-training-hook-audit-2026-09-02.md) | It does not establish full-corpus LLM training, horizontal scaling, multi-node behavior, steady-state throughput, or external validity. |
| C8 | Recipient-visible context changes the applicable release route: arbitrary-candidate loss, internal features, or exact rosters are different interfaces from label/text-only output. | Design supported; observations descriptive | [Execution audit](../docs/real-data-training-hook-audit-2026-09-02.md) and [composition interface masks](../reproduction/composition-scaling/README.md) | Do not claim a monotone or causal effect of “more metadata.” The observed membership metrics are underpowered screens and cannot clear or block. Exact-roster disclosure is a logical redesign condition. |
| C9 | The composition-scaling design permits scalar empirical composition only within a shared protected-unit population and uses vectors for mixed-modal portfolios. | Registered/pending | [Composition-scaling protocol](../reproduction/composition-scaling/README.md) and [suite configuration](../reproduction/composition-scaling/suite-config.json) | This is currently a methodology/configuration claim. No all-five scalar or completed scaling outcome may be reported. |
| C10 | The registered composition study spans five models, three scales per modality, five seeds, and all 31 nonempty model subsets under serial one-GPU resource ceilings. | Registered/pending | [Composition-scaling protocol](../reproduction/composition-scaling/README.md) | These are registered matrix dimensions, not executed cell counts or measured scaling results. Completion requires validated child and suite manifests. |
| C11 | The protocol mutation program defines two positive controls and 21 unsafe mutants covering selected lifecycle and integrity failures. | Implemented; outcome pending | [Mutation evaluation design](../docs/protocol-evaluation.md) and [evaluation script](../scripts/evaluate_protocol_mutations.py) | Do not report a mutation score until a fresh report is retained. Even a score of one covers only the registered mutants. |
| C12 | MRA routes a broad set of model families through shared contract and decision semantics while failing closed when a dedicated evidence path is absent. | Implemented routing claim | [Model-family coverage](../docs/model-family-coverage.md) | Architecture-neutral routing is not universal empirical validation and does not mean every family can be cleared. |
| C13 | The completed workers published throughput, memory, loss/accuracy, perturbation, and membership-screen aggregates with artifact digests. | Completed observation | [Execution audit](../docs/real-data-training-hook-audit-2026-09-02.md) | Values are single-run observations. Cross-model differences are descriptive; no confidence intervals, cost study, or hardware-neutral performance law is supported. |
| C14 | Legal and rights gates can dominate model metrics: the audited OPT route is blocked for production/commercial use by its registered non-commercial license, while other data/model uses require review. | Completed release-route observation | [Execution audit](../docs/real-data-training-hook-audit-2026-09-02.md) | This records the audit's registered route, not general legal advice or clearance for any dataset/model. Reconfirm terms at submission and deployment time. |
| C15 | Production authorization, activation, and serving enforcement require external authority, registry, and gateway services that this repository does not implement. | Supported non-claim | [Project scope](../docs/project-scope.md), [architecture](../docs/architecture.md), and [production roadmap](../docs/reference/production-roadmap.md) | Keep this boundary in the abstract, design, evaluation, and conclusion. |

## Claims not currently supportable

| Prohibited wording | Why it is unsupported | What would be needed |
|---|---|---|
| “MRA proves that a model is safe/private/fair/robust.” | Formal claims concern protocol traces; empirical model outputs are screens or narrowly scoped evidence. | A defined harm/game, eligible evidence, complete release interface, production enforcement, and a claim no broader than those premises. |
| “The system is production-ready” or “MRA authorizes releases.” | Authoritative identities, durable orchestration, atomic registry, live gateway, monitoring, and revocation are outside the repository. | An independently reviewed L3/L4 deployment and refinement/operational evidence. |
| “The system scales horizontally” or “scales to production workloads.” | The completed study is serial, single-node, and single-run; the larger matrix is only configured. | Repeated distributed experiments with back-pressure, failures, recovery, utilization, cost, and confidence intervals. |
| “More metadata monotonically increases privacy risk.” | R0–R5 are explicit non-ordinal interfaces; current metrics are descriptive and confounded. | A preregistered causal or otherwise valid comparative design with adequate power and a precise intervention. |
| “All five model risks compose to one score.” | LLM records and vision images are different protected-unit populations. | A justified joint game/population or a vector-valued decision; never an arbitrary average. |
| “The composition-scaling experiment completed.” | Only configs, runners, and validation contracts are retained. | Complete child reports/manifests and final suite report/manifest, all hash-verified. |
| “A failed red-team attack clears privacy.” | Empirical failure supplies no upper bound. | An eligible ceiling/exact mechanism with complete coverage plus all policy gates. |
| “The Lean proof verifies the Python implementation.” | The repository explicitly has no implementation-refinement proof. | A reviewed semantic correspondence/refinement proof covering the relevant executable and infrastructure. |
| “Model-family neutral means evidence-valid for every model.” | The shared decision layer is neutral; evidence assumptions remain model/interface/population specific. | Family-appropriate, recipient-realizable validation or a complete finite-channel/mechanism argument for each release. |

## Final prose audit

Before submission, search the draft for `safe`, `secure`, `private`, `verified`,
`proved`, `scalable`, `complete`, `all models`, `production`, `causal`, and
`authorizes`. For each occurrence, cite a matrix row and copy its qualification
into the surrounding paragraph. If no row supports it, weaken or remove it.
