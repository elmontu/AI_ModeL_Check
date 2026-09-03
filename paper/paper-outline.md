# Paper outline: contract-centered model-release assurance

Working title: **From Model Checks to Release Contracts: A Fail-Closed
Reference Architecture for Model Release Assurance**

Status: drafting skeleton. Bracketed labels follow the convention in the
[workspace README](README.md).

## Abstract scaffold

Do not turn this scaffold into a final abstract until every result placeholder
has a retained artifact.

> Releasing a model is not a single test: it couples the exact artifact and
> recipient interface to threat definitions, evidence, configuration
> selection, and an authorization lifecycle. `[SUPPORTED]` We present Model
> Release Assurance (MRA), an offline reference implementation of a
> contract-centered, fail-closed release protocol. The system distinguishes
> empirical lower-bound attacks from decision-bearing ceilings, binds evidence
> to release context, and keeps assessment separate from external
> authorization and serving. `[SUPPORTED]` A Lean model checks scoped
> authorization-integrity and statistical-accounting properties under explicit
> premises. `[SUPPORTED]` Across 1,200 controlled primary replays, the
> finite-channel ceiling had zero observed undercoverage and resolved every
> registered safe, boundary, and unsafe case as `CLEAR`, `HOLD`, or `BLOCK`.
> A first public-data follow-up preserved a failed all-family-clear criterion.
> A prospectively frozen corrective replication with fresh model and sampling
> seeds passed all 10 role-aware criteria: 1,200 repeats had no undercoverage or
> wrong-direction events, and all four margin-eligible safe-side families
> resolved correctly in 200/200 repeats. The near-threshold raw Transformer
> proxy instead produced 31 `CLEAR` and 169 conservative `HOLD` outcomes.
> `[SUPPORTED]` In a completed integration study, aggregate training
> hooks executed on three language models over a pinned WildChat cohort and two
> vision architectures over all 27,000 EuroSAT images; the retained report
> treats all measured attacks as non-authorizing screens. `[AUTHOR TODO]` Add
> fresh protocol-test, mutation, proof-replay, and overhead
> results only after their artifacts are frozen. `[NON-CLAIM]` MRA does not
> implement a production authorization registry or serving gateway and does not
> establish that the evaluated models are safe.

## 1. Introduction

### 1.1 Problem

- Model evaluation tools usually produce metrics, while a release decision also
  needs a frozen artifact/interface, a threat game, evidence direction,
  portfolio scope, policy, and an accountable authorization transition.
- A successful empirical attack and a failed empirical attack are asymmetric:
  the former can establish a lower bound under its game, while the latter does
  not establish a safety ceiling.
- Composition is meaningful only when the mathematical objects share a valid
  scope; unrelated LLM records and vision images cannot be averaged into one
  empirical risk scalar.

Ground these points in the [privacy-assurance literature review](../docs/literature-review.md)
and distinguish cited source results from this paper's proposed system design.

### 1.2 Thesis

> Explicit, versioned contracts and direction-aware evidence composition make
> finite-channel release assessment replayable and fail closed: exact-risk
> experiments can audit ceiling coverage separately from its ability to resolve
> `CLEAR`, `HOLD`, or `BLOCK`, while the protocol exposes rather than conceals
> the remaining production trust boundary.

Do not use “proves safe,” “automates governance,” or “production-ready.”

### 1.3 Contributions

Use the candidate contribution set in the [workspace README](README.md), after
checking each sentence against the [claims matrix](claims-to-evidence.md).
Lead with the contract/protocol design and two-tier ceiling evaluation. Present
the five-model hook audit as integration evidence. Keep composition scaling as
a secondary registered design whose full experiment is not completed.

## 2. Problem statement and assurance boundary

### 2.1 Release object

Define the release as the exact model/artifact, preprocessing and wrappers,
recipient-visible interface, protected unit and population snapshot, threat and
decision game, candidate controls, policy, and validity interval. Cite the
[normative protocol](../docs/model-release-assurance-protocol.md).

### 2.2 Evidence directions

Introduce four evidence roles:

- floor: can support `BLOCK`, never `CLEAR`;
- ceiling: can support `CLEAR`, never create a blocking lower bound;
- exact: decision-bearing only with complete eligible coverage;
- screen: diagnostic and non-decisional.

Explain that missing, stale, mismatched, underpowered, or incomplete evidence
produces a hold/inconclusive outcome. Use the exact current rules from the
[mathematical foundations](../docs/mathematical-foundations.md), rather than
reconstructing them from memory.

### 2.3 Threat and trust model

State which submitters, recipients, workers, registries, and network messages
may be adversarial. Separate checks performed by the offline core from
declarations whose truth still requires independent collection, attestation,
or governance. The canonical boundary is in the
[reference threat model](../docs/reference/threat-model.md).

## 3. System design

### 3.1 Contracts, pipelines, and workflow

Present the three operational layers:

1. contracts define valid release and evidence objects;
2. pipelines validate, assess, optimize, sign, and replay offline artifacts;
3. MRAP coordinates lifecycle gates, but durable production orchestration is
   external.

Use the [architecture](../docs/architecture.md) for component boundaries and
the [schema index](../schemas/README.md) for current public contracts.

### 3.2 Fail-closed assessment

Describe source/context verification, analyzer dispatch, evidence brackets,
per-threat `CLEAR`/`BLOCK`/`INCONCLUSIVE` outcomes, and machine-readable
resolution actions. `[REPRODUCE]` Select a small set of positive and negative
fixtures for a paper table; archive the command, commit, environment, and raw
output rather than quoting the test suite generically.

### 3.3 Selection and portfolio constraints

Explain that utility feasibility precedes information minimization and that
component-wise checks do not automatically establish a cumulative portfolio
claim. Identify the exact assumptions behind analytic, statistical, transfer,
and DP paths. Do not imply that an optimizer result is an authorization.

### 3.4 Finite-channel bounds

Describe the architecture-neutral finite-channel path as an implementation
capability with separately scoped empirical validation. Its decision-bearing
statistical path requires a policy-frozen exact-guess game and rational prior, a complete
enforced finite recipient interface, recipient-realizable observations,
selection-valid simultaneous evidence, exact context/source bindings, and
engine-replayed outward endpoints. Incomplete, continuous, or unbounded
adaptive interfaces are redesigned rather than assigned a false ceiling.

The [completed ceiling evaluation](ceiling-experiment-results.md) supports
coverage and decision-resolution claims for exact controlled channels. It also
preserves model-backed v2's failed all-family-clear result and reports v3 as a
prospectively frozen corrective replication with fresh model and sampling
seeds. V3 adds per-observation one-use wrapper execution, exact aggregate
cross-replay, source binding, role-aware wrong-direction error, and a
predeclared resolution margin. It passed all 10 criteria, while retaining the
near-threshold raw proxy's 31 `CLEAR`/169 `HOLD` split.

The result remains conditional on finite pools and resampling. Python wrapper
execution is not proof of deployed endpoint or OS semantics, all ceiling
experiments waive the attack-battery precondition experimentally, and none
authorizes a release. V3 contains no oracle risk above tolerance, so its
model-backed evidence covers safe-side resolution and conservative holds—not
unsafe-side `BLOCK` power. Existing training-hook and red-team runs remain
screens.

### 3.5 Lifecycle integrity and external authority

Show the path from draft through assessment and selection to commit, external
authorization, activation, suspension, expiry, and revocation. Make the offline
replay/production-service distinction visually and textually explicit.

## 4. Formal model

### 4.1 Transition system

Summarize roles, indexed actions, immutable release identity, terminal states,
strict registry-head progression, authenticated messages, and ideal
commit/activation/serving semantics.

### 4.2 Machine-checked claims

Reference theorem identifiers rather than paraphrasing broader guarantees. The
[formal verification document](../docs/formal-verification.md) lists the
authorization, identity, RBAC, registry, deployment, message, composition, and
finite statistical-accounting theorem set.

### 4.3 Trusted base and non-correspondence

State explicitly that the Lean transition system is not a proof that the
Python implementation or a real registry/gateway refines the model. Record the
pinned Lean version, proof command, accepted axiom set, repository commit, and
toolchain digest for the submitted artifact.

## 5. Implementation

### 5.1 Reference core

Describe the Python package and CLI boundaries using the
[project scope](../docs/project-scope.md). Include contract validation,
assessment, configuration selection, certificate/manifest handling, audit
intent/terminal records, and protocol replay. Avoid presenting internal Python
modules as stable APIs unless documented as such.

### 5.2 Evidence lab and hooks

Explain that model execution occurs in experimental workers outside the inert
assessment core. Training hooks retain bounded aggregate telemetry rather than
examples, tokens, logits, activations, or gradients. The completed case-study
details and exact artifact digests are in the
[real-data execution audit](../docs/real-data-training-hook-audit-2026-09-02.md).

### 5.3 Secondary composition-scaling coordinator

Describe serial one-GPU orchestration, child manifest validation, resource
ceilings, safe aggregate publication, same-population scalar subsets, and
vector-valued mixed-modal summaries from the
[registered composition design](../reproduction/composition-scaling/README.md).
Use future tense for experiment outcomes until complete outputs are retained.

## 6. Evaluation

Organize the evaluation around answerable systems questions rather than model
leaderboards.

| RQ | Question | Present evidence | Required paper artifact |
|---|---|---|---|
| RQ1 | Does the reference core reject registered malformed, incomplete, rebound, or role-confused release records? | Test fixtures and a 21-mutant evaluation program exist. | Fresh complete test log and retained mutation report at the paper commit. |
| RQ2 | Can aggregate hooks run end to end on materially different real-data model workloads without retaining per-example telemetry? | Completed five-model WildChat/EuroSAT audit. | Already curated; independently verify cited hashes and disclose unavailable raw-public artifacts. |
| RQ3 | How do model, data scale, seed, and same-population composition affect measurements and resource use? | Secondary five-model experiment is registered, not complete. | Both child completion manifests, suite completion manifest, reports, journals, environment, and analysis snapshot. |
| RQ4 | Are the scoped protocol invariants mechanically reproducible? | Lean source, pinned toolchain, and verification wrapper exist. | Fresh proof-build transcript and environment identity. |
| RQ5 | What is the runtime/storage overhead of contracts, hashing, replay, and hooks? | Isolated throughput/memory observations exist for the five-model audit. | Repeated baseline-versus-instrumented trials and end-to-end core microbenchmarks; do not infer from one run. |
| RQ6 | Does the finite-channel ceiling cover exact risk, avoid wrong-direction decisions, and resolve cases with adequate policy margin? | Controlled experiment and prospectively frozen corrective model-backed v3 accepted; v2 negative retained. | [Generated tables and figure](ceiling-experiment-results.md), [summary](../reproduction/ceiling-experiment-summary.json), registrations, and versioned retained manifests/reports. |

### 6.1 Completed finite-channel ceiling evaluation

Use the [generated result tables and figure](ceiling-experiment-results.md), not
manual transcription. Structure the section around four metrics:

1. soundness: observed undercoverage and its simultaneous upper confidence
   bound;
2. tightness: interval width and ceiling excess over exact risk;
3. decision usefulness: `CLEAR`, `HOLD`, and `BLOCK` rates around tolerance;
4. fail-closed integration: arithmetic/source replay and negative controls.

The controlled tier completed 1,200 primary analyzer replays with 0/1,200
undercoverage, a maximum simultaneous undercoverage upper bound of `0.015606`,
and 400/400 correct decisions for each safe, boundary, and unsafe role. Only
three runs traversed the full source-backed Engine path.

Model-backed v2 completed with 8/9 criteria and its raw Transformer proxy
cleared 109/200 times under the original all-family-clear rule. Preserve that
negative outcome as the disclosed predecessor.

Corrective v3 was then prospectively frozen with fresh model and sampling seeds
and passed 10/10 criteria. Six full Engine primary replays and 1,200 analyzer
repeats had 0/1,200 undercoverage and wrong-direction events; across 18
Bonferroni endpoints, each zero-event simultaneous upper bound was `0.02900166`.
All four families at least `0.10` from tolerance made 200/200 correct safe-side
decisions, with simultaneous lower bound `0.97099834`. The raw Transformer proxy
had exact risk `0.612857`, was not margin eligible, and produced 31 `CLEAR` and
169 `HOLD` outcomes. No v3 oracle exceeded `0.65`; model-backed `BLOCK` power
is therefore untested and must not be implied. The controlled `0.80` channel
supplies the current unsafe-side evidence.

Each v3 observation traversed a one-use Python wrapper and exactly matched the
aggregate reference sampler; wrapper evidence was bound into Engine source
replay. Preserve the finite-pool/resampling, one-artifact, proxy-only,
experimental-waiver, no-authorization, and no endpoint/OS-semantic-proof
boundaries.

### 6.2 Completed real-data integration case study

Safe present-tense facts from the retained audit include:

- a pinned 9,216-row WildChat cohort (8,192 train, 1,024 holdout) was used for
  one FP32 epoch each on DistilGPT2, OPT-125M, and Pythia-160M;
- the three LLM runs recorded 3,072 forward and 3,072 backward aggregate-hook
  observations with complete registered coverage and zero non-finite events;
- all 27,000 EuroSAT images were split into 21,600 training and 5,400 test
  images for one epoch each of AlexNet and DenseNet-121;
- the two vision telemetry chains each contained 507 forward and 507 backward
  aggregate-hook observations with complete registered coverage; and
- all privacy and perturbation outputs were descriptive screens with final
  disposition `no_release_authorization`.

Keep exact performance and screen values in tables sourced directly from the
audit. Preserve its qualifications: one seed, one epoch, one GPU stack, no
confidence intervals, non-randomized model assignment, and no causal metadata
effect.

### 6.3 Protocol rejection and proof replay

`[REPRODUCE]` Report the complete Python suite, schema replay, Markdown checks,
mutation evaluation, and Lean build separately. Include skips and failures;
never collapse these distinct checks into one “verified” percentage.

### 6.4 Secondary composition and scaling

`[PLANNED]` The frozen design contains three LLMs, two vision models, three
real-data scales per modality, five seeds, 31 nonempty model subsets, seven LLM
scalar subsets, three vision scalar subsets, and 21 mixed-modal vector-only
subsets. The coordinator runs children serially on one GPU with 12-hour and
20-GiB ceilings. These are protocol facts, not measured outcomes.

### 6.5 Ablations and negative controls

`[AUTHOR TODO]` Prioritize ablations that test the paper's mechanism:

- remove or alter artifact/interface/context bindings and confirm rejection;
- omit, duplicate, or substitute statistical-family members;
- compare hook/no-hook behavior with the registered non-interference controls;
- compare same-population scalar aggregation with rejected cross-population
  aggregation; and
- test stale registry state, replay, substitution, expiry, and role confusion.

## 7. Discussion and limitations

At minimum, retain these limitations:

- production identities, immutable stores, atomic registries, gateways,
  monitoring, revocation services, and institutional authority are absent;
- formal theorems apply to an abstract system and explicit premises;
- most empirical runs are screens, not upper bounds or release evidence;
- controlled ceiling coverage is not a universal proof, and the model-backed
  result is conditional on one artifact per family and resampling from finite
  target pools of 400/400 records for CNN and XGBoost and 350/350 for the
  proxy;
- v2 did not route aggregate samples through the wrapper harness per
  observation; v3 does, but still provides no endpoint/OS semantic proof;
- every v3 oracle risk is below tolerance, so model-backed unsafe-side and
  `BLOCK` power remain untested;
- all ceiling runs used experimental attack-battery waivers;
- the compact Transformer is an LLM proxy, not an interactive LLM;
- the completed GPU study is single-run and single-node;
- dataset/model licensing and human-data rights remain independent gates;
- complete interactive LLM interfaces, adaptive transcripts, tools, RAG,
  memory, and side channels are not established by the case study; and
- model-family neutrality at the contract/decision layer is not empirical
  validation of one analyzer across all architectures.

## 8. Related work

Structure this section around:

1. empirical privacy attacks and privacy games;
2. differential privacy and empirical auditing;
3. model extraction, LLM memorization, canaries, and watermarks;
4. algorithmic auditing and model governance;
5. audit games, strategic classification, and performative prediction; and
6. formal methods for authorization, provenance, and deployment controls.

Start from the two curated reviews linked in the [workspace README](README.md),
then verify every final citation against its primary source and the conference's
current citation rules.

## 9. Reproducibility, ethics, and artifact availability

Use the [artifact index](artifact-index.md) and
[reproducibility checklist](experiments-and-reproducibility.md). Explain why
raw WildChat dialogue, exact rosters, source images, trained state, and detailed
telemetry are not committed; distinguish responsible exclusion from complete
artifact availability. Report licensing, access, retention, and deletion
conditions rather than treating a public download as rights clearance.

## 10. Conclusion

Return to the narrow thesis: the contribution is a reference architecture and
enforcement model that makes release assumptions, evidence direction, ceiling
soundness, and decision usefulness explicit. Treat the preserved model-backed
v2 failure and the prospectively frozen v3 correction as an honest study
chronology, not as license to rewrite the predecessor. Do not close by
asserting production safety, model-backed `BLOCK` validation, or completed
composition-scaling results.
