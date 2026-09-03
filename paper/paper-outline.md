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
> premises. `[SUPPORTED]` In a completed integration study, aggregate training
> hooks executed on three language models over a pinned WildChat cohort and two
> vision architectures over all 27,000 EuroSAT images; the retained report
> treats all measured attacks as non-authorizing screens. `[AUTHOR TODO]` Add
> fresh protocol-test, mutation, proof-replay, composition-scaling, and overhead
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

`[AUTHOR TODO]` Choose one primary thesis. Recommended narrow version:

> Explicit, versioned contracts and direction-aware evidence composition make
> model-release decisions replayable and fail closed across heterogeneous model
> checks, while exposing rather than concealing the remaining production trust
> boundary.

Do not use “proves safe,” “automates governance,” or “production-ready.”

### 1.3 Contributions

Use the candidate contribution set in the [workspace README](README.md), after
checking each sentence against the [claims matrix](claims-to-evidence.md).
Separate implemented contributions from the composition-scaling methodology,
whose full registered experiment is not yet retained as completed.

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
capability, not as an empirical result. Its decision-bearing statistical path
requires a policy-frozen exact-guess game and rational prior, a complete
enforced finite recipient interface, recipient-realizable observations,
selection-valid simultaneous evidence, exact context/source bindings, and
engine-replayed outward endpoints. Incomplete, continuous, or unbounded
adaptive interfaces are redesigned rather than assigned a false ceiling.

`[AUTHOR TODO]` Add a completed, independently recollected case study before
claiming this path clears or blocks a real release. Existing training-hook runs
remain screens.

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

### 5.3 Composition-scaling coordinator

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
| RQ3 | How do model, data scale, seed, and same-population composition affect measurements and resource use? | Five-model experiment is registered, not complete. | Both child completion manifests, suite completion manifest, reports, journals, environment, and analysis snapshot. |
| RQ4 | Are the scoped protocol invariants mechanically reproducible? | Lean source, pinned toolchain, and verification wrapper exist. | Fresh proof-build transcript and environment identity. |
| RQ5 | What is the runtime/storage overhead of contracts, hashing, replay, and hooks? | Isolated throughput/memory observations exist for the five-model audit. | Repeated baseline-versus-instrumented trials and end-to-end core microbenchmarks; do not infer from one run. |
| RQ6 | Can a complete finite release channel produce a decision-bearing floor/ceiling and resolution? | Core path and contracts exist; old model runs are ineligible screens. | Approved state-conditioned recollection with frozen game/prior/interface and full binding context. |

### 6.1 Completed real-data integration case study

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

### 6.2 Protocol rejection and proof replay

`[REPRODUCE]` Report the complete Python suite, schema replay, Markdown checks,
mutation evaluation, and Lean build separately. Include skips and failures;
never collapse these distinct checks into one “verified” percentage.

### 6.3 Composition and scaling

`[PLANNED]` The frozen design contains three LLMs, two vision models, three
real-data scales per modality, five seeds, 31 nonempty model subsets, seven LLM
scalar subsets, three vision scalar subsets, and 21 mixed-modal vector-only
subsets. The coordinator runs children serially on one GPU with 12-hour and
20-GiB ceilings. These are protocol facts, not measured outcomes.

### 6.4 Ablations and negative controls

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
enforcement model that makes release assumptions and evidence direction
explicit. Do not close by asserting production safety or completed
composition-scaling results.
