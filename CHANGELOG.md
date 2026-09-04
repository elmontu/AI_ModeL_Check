# Changelog

All user-visible changes to Model Release Assurance are recorded here. The project follows semantic versioning while it remains in the `0.x` alpha series; minor releases may change public contracts when the migration is documented.

## [Unreleased]

### Added

- A one-command, core-only government-health guided demo for nontechnical
  reviewers. It joins a fresh assessment to optimization, verifies signatures
  and the audit chain, exercises live hold/block/artifact-tamper cases, and
  replays mock activation, stale-registry, deployment-mismatch, and incident
  workflows. Its live path is a closed, digest-pinned generic synthetic fixture;
  the government-health case is explicitly a non-executed discussion overlay.
  Proxy model labels and all external simulations are disclosed, and every
  summary records that no production authorization or activation occurred.
- A preregistered exact-ground-truth finite-channel experiment with retained
  aggregate results: 1,800 completed records, zero undercoverage across 1,200
  primary analyzer replays, simultaneous undercoverage upper bound `0.015606`,
  correct `CLEAR`/`HOLD`/`BLOCK` resolution in all 400 repetitions per role,
  three source-backed Engine integrations, and fail-closed tamper controls.
- A completed public-data model-backed v2 experiment covering CNN/MNIST,
  XGBoost/Adult, and a compact-Transformer/20-Newsgroups LLM proxy under raw-bin
  and 90%-erasure variants. The retained mixed result passed eight of nine
  criteria: undercoverage was 0/1,200, but raw proxy `CLEAR` power was 109/200
  with a simultaneous lower bound of `0.449431`, below the registered `0.95`.
- A prospectively frozen corrective model-backed v3 replication, designed
  after disclosing v2 and executed with fresh model and sampling seeds. All 10
  registered criteria passed: six Engine primary replays and 1,200 analyzer
  repeats had zero undercoverage and wrong-direction events; the simultaneous
  upper bound was `0.02900166` across 18 Bonferroni endpoints; and all four
  margin-eligible safe-side families resolved correctly in 200/200 repeats
  with lower bound `0.97099834`. The near-threshold raw proxy retained 31
  `CLEAR`/169 `HOLD` outcomes. No v3 risk exceeded tolerance, so it does not
  establish model-backed `BLOCK` power.
- Generated paper-ready ceiling tables, a figure, a machine-readable summary,
  result manifests, and drafting indexes that keep coverage, tightness,
  decision usefulness, and authority scope distinct. The v1 pre-outcome
  serialization failure and compatibility-only v2 registration remain in the
  audit trail. All ceiling studies record experimental attack-battery waivers
  and no release authorization. V3 adds one-use wrapper execution, exact
  aggregate-sampler cross-replay, Engine source binding, five negative
  controls, and exact erasure identity without claiming endpoint/OS semantics.
- Publication copies of ceiling execution/resource logs now replace ephemeral
  machine paths with labeled placeholders while their manifests retain both
  the original raw-output digest and sanitized artifact digest.
- An MLSys paper workspace with a start-here guide, manuscript draft, claims-to-evidence matrix,
  artifact index, and experiment/reproducibility gates that distinguish retained results from
  configured studies and prohibited claims.
- A standalone integrated system audit specification consolidating the complete architecture, normative MRAP roles/messages/states/gates, current release contracts and pipelines, evidence semantics, threat and formal boundaries, production obligations, pass/fail rules, and an auditor checklist.
- Assessment request/report 5.0, policy 3.0, signed assessment manifest 3.0, optimization request/report 4.0, signed optimization manifest 4.0, release-protocol verification 2.0, and audit-verification 3.0 contracts. Superseded schema bytes remain retained as historical structure.
- Versioned attack catalog, frozen battery configuration, positive-control result, worker-output, and assessment-submission contracts, plus a non-clearing trusted-core `attack_battery` analyzer.
- Per-threat policy modes that require, explicitly waive, or prohibit an attack-battery precondition for ceiling-based clearance; exact-value clearance remains distinct.
- Policy allowlists for the complete catalog/configuration, required attack identifiers, worker service/version/implementation/image, isolation assurance, attester identities, and minimum positive-control power.
- Centrally replayed positive controls, complete-battery multiplicity, attack applicability checks, required floor/operating-point attainment, and fail-closed missing, failed, timed-out, uncontrolled, or unsafe-isolation dispositions.
- Machine-readable assessment scope (`single_release_no_portfolio`, `declared_interface_only`, live-interface false, authorization-ineligible) and optimization bindings for the active policy, declared hash-bound portfolio-registry snapshot, exact covered releases, and versioned ordered selection policy.
- Typed evidence-producer service/version and implementation/configuration digests, with policy minimum versions, digest allowlists, required-analyzer rules, and fail-closed stale-producer rejection.
- Two-phase assessment/optimization audit events (intent plus completed/failed), orphan detection, ledger identity, contiguous sequence/tail checks, structured verification, and externally anchorable ledger checkpoints.
- Machine-readable release-protocol verification results recording the profile, run hash,
  verification time, artifact/signature verification booleans, skipped checks, and degradations.
- Required structured interface declarations for output/download/summary, serialization, timing,
  error/status, execution-state/concurrency, and side/local/administrator access channels.
- `InterfaceContract 3.0` and nested `LlmProtocolContract 1.0` use required-explicit nullable fields and add a coherent rate-limit value/window/burst/scope/retry/enforcement contract whose compatibility flag must agree.
- Deterministic runtime identities on assessment, optimization, lifecycle, and audit verification
  outputs, including package-source and transparent algorithm-profile digests.
- A centralized 30-contract schema registry and deterministic exact-byte current-schema manifest with explicit self-exclusion metadata;
  trusted release signing/attestation remains an external protected-identity operation.
- A first-class, model-family-neutral `finite_channel_ceiling` analyzer and public finite-channel
  submission, policy-bound finite-decision-game, and typed finite-state-prior contracts. The analyzer
  emits a fixed-decoder confidence floor and an exact-rational/outward confidence ceiling only for a
  complete enforced finite recipient channel; it mechanically validates serialized reference
  Clopper--Pearson endpoints under canonical-JSON decimal semantics and returns actionable hold
  resolutions when obligations fail.
- A public `EvidenceBindingContext` carried identically by finite-channel plan, counts, committed error-budget allocation,
  and compiled marginal evidence, with engine-enforced release/policy/artifact/interface/scope/game
  equality and sampling-before-observation order; endpoint eligibility is compiler- and replay-derived,
  never submitter-attested.
- Exact rational typed finite-state priors, canonical JSON-decimal decisions at policy boundaries,
  and an aggregate directed-tail work cap remove prior/threshold liveness defects and bound endpoint
  verification cost.
- Required machine-readable decision resolutions turn every inconclusive result into a fail-closed
  hold with an evidence-repair, recollection, interface-redesign, policy-registration, conflict, or
  attack-battery action; indicative sample targets are explicitly non-decision planning guidance.
- An executable theorem-to-runtime obligation map naming concrete Python violation behavior, regression tests, coverage status, and external refinement gaps.
- Dedicated, transcript-bound interactive-LLM analyzers for output-watermark screens and randomized synthetic-canary attack floors.
- Canary evidence supports low-FPR and equal-prior membership games plus exact reconstruction, while contamination, protocol-binding, preregistration, or recipient-realizability failures downgrade the result to a non-decision-bearing screen.
- Watermark evidence is always provenance-triage screen evidence and can neither block nor clear a privacy threat; null watermark and canary results never clear a release.
- A transport-neutral analyzer-service registry, in-process compatibility adapter, versioned MCP adapter contract, capability discovery tool, and engine-side validation of remote evidence identity, bindings and decision authority.
- An explicit manifest-validation, artifact-integrity, model-execution, assurance-routing and decision-aggregation workflow with replaceable MCP-ready model workers, including deterministic XGBoost and MLP test models.
- A bounded empirical workflow that trains native XGBoost and scikit-learn MLP classifiers on independently seeded synthetic datasets, evaluates disjoint stratified holdouts, and reports Bonferroni-corrected exact one-sided confidence intervals without creating clearance evidence.
- Corrected the deterministic additive-stump fixture to identify it as a workflow proxy rather than a trained native XGBoost model.
- Integrated a red-team stage with independently trained shadow-model membership attacks, Gaussian feature corruption and exhaustive single-feature occlusion probes; outputs remain non-clearing and require complete assessment bindings before any attack floor may block.
- Added an independently implemented, MIT-attributed SACRO-ML-inspired target/tool registry with aggregate structural disclosure indicators, repeated worst-case probability membership attacks, dummy baselines, low-FPR simultaneous bounds, standardized reports and MCP-ready discovery metadata.
- MCP red-team discovery now returns a typed catalog and digest, and a non-authorizing validator checks complete attack-battery submission structure and bindings without executing models or granting decision authority.
- A digest-pinned real-data LLM training-hook worker sequentially fine-tunes revision-pinned DistilGPT2, Meta OPT-125M, and Pythia-160M on the same deterministic 8,192-row WildChat cohort, evaluates a disjoint 1,024-row holdout, and retains aggregate-only hook telemetry and final completion manifests.
- The LLM experiment includes precise before/after K0–K4 context/interface profiles: ordinary text-only generation does not imply candidate-metadata access, generated-token log probabilities do not imply arbitrary-candidate scoring, empirical K0–K3 results are non-blocking/non-clearing screens, and protected exact-roster exposure is a separate logical redesign condition.
- A full-real-data vision training-hook worker processes all 27,000 pinned EuroSAT RGB images through a deterministic 21,600/5,400 path-hash split and trains canonical torchvision AlexNet and DenseNet-121 from scratch for one epoch each, with aggregate-only hook telemetry and bounded real-image brightness, Gaussian-noise, and FGSM screens.
- Real-data worker hardening binds source/governance/model/runtime artifacts by exact bytes and digests, constrains downloads and archive extraction, separates sensitive caches from fresh no-clobber run directories, and checks hook cleanup and telemetry replay. The vision worker separates an exact CPU hook/no-hook control from seeded warn-only CUDA execution, rejects unexpected nondeterminism warnings, and makes no bitwise-CUDA or CUDA-noninterference claim. Every empirical screen is assessment-ineligible, non-clearing, and non-blocking pending approved typed recollection; every report remains non-authorizing, while direct protected-roster disclosure is handled separately as a logical redesign gate.
- A dedicated CPU-only `training-hook-runtime` CI job installs the LLM and vision experiment tiers on Python 3.13, runs all three focused hook/worker contract suites without dataset or model downloads, and gates distribution packaging without presenting CI as a full empirical run.
- A curated, publication-safe execution audit for the completed NVIDIA L4 runs records five-model real-data scale, aggregate training/hook measurements, WildChat K0–K4 context-risk screens, EuroSAT perturbation screens, artifact digests, release consequences, and limitations without publishing raw dialogue, images, rosters, per-example data, telemetry, or machine paths.
- A comprehensive five-model composition-scaling protocol registers three nested real-data scales and five seeds for DistilGPT2, OPT-125M, Pythia-160M, AlexNet, and DenseNet-121: 75 independent reference cells plus 90 matched vision batch/hook controls, seven LLM and three vision same-population output subsets, FGSM transfer, all 31 non-empty resource/gate portfolios, resumable hash-bound child journals, and fail-closed 12-hour/20-GiB suite limits. Mixed LLM/vision results remain vectors, generated output is ignored, and neither a queued nor completed experimental run can clear, block, or authorize a release.

### Changed

- The protocol-feasibility benchmark is now a self-contained synthetic study.
  It no longer discovers an obsolete ignored OpenML seal or framework report,
  and it records external evidence, deployment behavior, release yield, safety,
  and authorization as not evaluated.
- Default analyzer-service capabilities are derived from implemented behavior and cannot be widened by adapter configuration. Shipped candidate clearing paths now include DP ceilings, recipient-realizable tree exact evidence, and `finite_channel_ceiling` for a canonical exact-guess game over an enforced complete finite recipient channel; all remain subject to their other policy, portfolio, gateway, and evidence obligations.
- `model-coverage` names per-threat candidate clearing paths and unmet clearing-path threats without emitting a percentage or safety score.
- CLI assessment/optimization now requires an audit database; after request parsing/validation,
  intent is appended before analyzer/optimizer execution and completion before report output. Missing,
  malformed, or schema-invalid requests fail before the current audit-ingress boundary.
- Removed the rejected `adversarial_supply_chain` enum value; supported trust profiles are cooperative and separated-assessor, and signatures continue to establish only byte/key binding.
- Clarified the offline product scope and repository organization, exposed CLI version information, replayed every current schema in checks, and aligned contributor and release verification dependencies.
- Added GitHub project links, current issue/PR routing, Markdown-link verification, wheel smoke tests, annotated-tag/main-branch/version guards, and a formal proof gate for tagged releases.
- Rebuilt the reference architecture as a full software view covering runtime units, entry points, analyzer semantics, workflows, storage, release contracts, external training/export integration, deployment tiers, CI/release automation, observability, trust boundaries, and failure recovery; it also distinguishes the reviewer MCP server from the prospective analyzer adapter and current contracts from target integration gaps.
- The active policy now allowlists the canonical selection-policy digest; other selection-stage
  inputs remain caller-supplied and require authenticated authorities in production.
- Assessment and optimization reports now expose their emitting implementation/runtime profile;
  ordinary binary64 clearance comparisons are explicitly ineligible for unresolved MRAP G7 claims.
- Required-explicit nullable interface declarations now survive CLI, MCP, audit-ledger, fixture, and canonical-hash round trips and participate in governed model digests.
- New audit failures bound caller-controlled error codes/messages before retaining stable error codes and domain-separated diagnostic fingerprints rather than raw exception text. Audit Verification 3.0 counts fingerprint-form versus plaintext-compatible failed diagnostics and explicitly degrades when plaintext rows are present. The v2 envelope remains plaintext and content-bearing and is not a vintage dispatcher for prior Assessment 4.0 or Optimization 3.0 documents.
- Complete attack batteries now bind every run and positive-control disposition to its catalogued service, attack version, and implementation digest, distinguish heterogeneous executors from the battery orchestrator, enforce catalog validity over freeze/execution, expose executor identities in evidence, and revalidate copied/constructed request models at the engine boundary.
- Attack-battery observations must fall within the worker interval; the engine checks the full interval against policy/release/current-time bounds. Frozen timeout, aggregate reported-trial, and canonical output-byte limits are replayed, while CPU/memory are explicitly declared external-enforcement budgets. Unsupported unparameterized Holm/preallocated battery modes now fail closed in favor of the implemented Bonferroni replay.
- Exposed retry-after behavior now requires matching retry metadata and HTTP `429` or gRPC `RESOURCE_EXHAUSTED` declarations; custom transports retain explicit custom-code semantics.
- Experiment resolver constraints now stay within the scikit-learn 1.5/1.6 and
  XGBoost 2.x compatibility band instead of silently selecting incompatible
  future versions in CI. CI validates the versions resolved for each job, not
  every allowed combination, and this range file is not a reproduction lock.

### Removed

- Removed the dated framework audit/corrigendum documents and the frozen Version 0.5 prospective-study runner, analyzer, configuration, test, and seal requirements. Superseded schemas remain historical structural records for provenance and external schema validation; the current CLI accepts only current contract versions.
- Removed the self-attested post-critique design-control result, evaluator, and test; executable unit/regression tests are the maintained software evidence, while external custody and scientific adequacy remain outside the repository.
- Removed the obsolete OpenML v2-era seal constructor, whose hard-coded schema
  inventory and date could not produce a current study seal. Historical bytes
  remain available in Git; a replacement must be preregistered.
- Removed the duplicate operational-reference mini-index and the superseded
  paper-outline scaffold. Canonical reference links remain in `docs/README.md`,
  while open paper experiments and ablations now live in the reproducibility
  ledger beside the current manuscript.

### Fixed

- Composite controlled-inference and equal-prior canary floors now combine canonical confidence
  endpoints as exact rationals and round the final lower bound outward, preventing a one-ULP false
  block at a policy boundary.
- Exact rational decision bounds preserve a finite-channel ceiling equal to the policy tolerance
  across the outward-rounded binary64 display boundary. Exact Bonferroni allocation and directed
  binomial-tail replay prevent inward confidence endpoints or upward alpha rounding from clearing.
- Finite-channel evidence cannot substitute an assessor-selected state space or favorable prior:
  policy and threat contracts freeze identical semantics and rational weights, typed evidence binds
  the numerical vector, and deterministic point tables remain non-decision-bearing screens until
  recollected as selection-valid simultaneous multinomial evidence.
- Contradictory upper evidence can no longer weaken a validated over-tolerance floor from `block` to `inconclusive`; reports distinguish contradictory from insufficient evidence and identify the conflicting evidence records.
- Direct-joint portfolio evidence can no longer claim an assessed empty release set, and optimization requires exact coverage of the authoritative active registry snapshot plus the candidate.
- Release-protocol CLI machine output no longer hides structural-profile or skipped-artifact verification degradation.
- Audit-event v2 hashing now binds ledger, operation, release/instance identity, canonical payload,
  predecessor, timestamp, and hash format; legacy rows require explicit opt-in.
- Registry-commit replay now requires a one-step append and recomputes a release-bound
  `MRAP-STATE-1` commitment instead of accepting an arbitrary new head.
- Threat decisions name every excluded evidence identifier, report validation checks the complete
  included/excluded partition, and signed assessment manifests bind the interface hash directly.
- Future-dated portfolio snapshots and active-policy-unapproved selection rules fail closed.

### Known limitations

- The gateway/live-interface conformance service, immutable audit anchor, bundle-content verifier, retained-records system, and adversarial-supply-chain execution environment remain adopter-owned production components.
- Superseded JSON Schemas are retained for structural provenance, but the current CLI is not yet a version-dispatched historical verifier; preserve matching released wheels, locks, trust metadata, and replay fixtures for long retention.
- Registry semantic-delta completeness, authoritative inclusion/CAS, live gateway enforcement,
  trusted-build attestation, selection-input issuer authentication, and cross-release budget custody
  remain external. Ordinary binary64 decision boundaries remain a current MRAP G7 blocker.

## [0.7.0] - 2026-08-23

### Added

- A pinned Lean 4 formalization of the MRAP role-indexed transition system with machine-checked authorization-integrity, release-binding, role-authorization, compare-and-swap and finite false-authorization-budget theorems.
- Compiled negative witnesses, a reproducible proof/axiom audit wrapper, and a dedicated CI proof job that rejects proof placeholders and unapproved axioms.
- A formal mathematical-foundations document with explicit finite decision games, Blackwell transfer, simultaneous-coverage authorization, soundness–liveness protocols, incomplete-portfolio optimization, differential-privacy bounds, proofs, assumptions, and non-claims.
- Mathematical regression tests for arbitrary-prior finite-secret DP bounds and stable large-epsilon evaluation.
- A normative MRAP/1.0 lifecycle protocol with explicit authorities, signed message semantics, immutable instances, admissibility gates, a state machine, atomic portfolio authorization, gateway activation, monitoring, revocation, recovery, security theorems, and conformance levels.
- A typed lifecycle transcript and fail-closed structural verifier covering role-qualified artifact production, exact-decimal error spending, event hash chaining, assessment/selection gates, compare-and-swap authorization, deployment binding, expiry, monitoring, suspension, revocation, and abort behavior.
- A `release-protocol-verify` command and versioned `ReleaseProtocolRun` JSON Schema.
- A contract-1.1 authenticated transcript profile with external Ed25519 trust anchors, release-bound event/artifact signatures, known-compromise rejection, and monotonically increasing registry sequences.
- Composed Lean authenticated-message/lifecycle semantics, replay/binding/compromise/expiry theorems, a non-vacuous valid activation trace, and a proof-carrying per-component statistical budget ledger.
- An ideal Lean deployment functionality with atomic authorization commits, measured gateway activation, bounded per-request serving, lifecycle realization, and machine-checked replay, concurrency, substitution, expiry, suspension, and revocation denial theorems.
- A standalone `mrap-protocol` Lean package with a stable `MRAP` public umbrella and audit-only mutation/theorem-inventory modules kept outside the exported protocol surface.
- A checked Python-to-Lean role/state/action correspondence manifest and a reproducible adversarial mutation evaluation covering nineteen unsafe transcript classes.
- A primary-source game-theory review and machine-readable claim ledger with source/inference/proposal labels, transfer limits, pessimistic tie handling, and regression-tested hallucination controls.
- A scoped supplemental strategic stress test separating Bayesian leakage from submitter incentives, assessor effort, attacker effort, robust deterrence, and real-world parameter provenance without treating governance as a game.
- An exact-rational strategic assurance library with replayable submitter, assessor, attacker, and Blackwell-control certificates; explicit mathematical-versus-deployment statuses; and fail-closed evidence, unit, positive-control, tie, completeness, and enforceability checks.
- A seeded synthetic health-release stress experiment with adverse-endpoint sampling, exact deterrence frontiers, certificate replay, and a negative control showing that monitoring cannot deter an attacker when enforceable consequence is zero.
- An explicit institutional governance core covering purpose, authority, accountable ownership, independent challenge, affected parties, conflict controls, contestation, reasoned decisions, lifecycle enforcement, and retirement; strategic analysis is now formally marked as a supplemental stress test with no governance-decision, authorization, or gate-override effect.

### Fixed

- Removed monitoring-authority privilege escalation through monitoring outcomes; revocation and expiry now require their dedicated role-authorized events.
- Replaced hash-inequality-only registry freshness with explicit append-only sequence advancement and added authenticated CLI replay coverage.
- Replaced the finite-secret DP ceiling's silent uniform-prior assumption with a proved bound using a policy-bound, source-validated upper bound on maximum secret-prior mass.
- Required pairwise DP across every finite-secret alternative and a source-bound validation flag for the numerical prior cap before the evidence may clear.
- Rewrote DP probability formulas into algebraically equivalent inverse-exponential forms that do not overflow for large finite epsilon.
- Extended the proof/axiom audit parser to recognize declarations whose kernel audit reports no axiom dependencies.

## [0.6.0] - 2026-08-22

### Added

- A local CSV/Parquet XGBoost classification worker with deterministic target/reference training, utility and leaf-signature metrics, a calibrated membership attack, verified caching, and hash-bound release artifacts.
- An end-to-end synthetic XGBoost regression test and a framework security/correctness audit.
- An interactive-LLM audit profile for output-watermark detection and synthetic training-canary exposure testing, with floor/screen-only decision semantics.
- A primary-source literature review covering membership inference, model extraction, differential-privacy auditing, XGBoost evidence limits, LLM canaries, and text-watermark calibration and attacks.
- A literature-driven refresh of audit checks: joint low-FPR confidence correction, XGBoost replicate-family correction and deployment-prior PPV, decision-game binding, cache-result replay, public-metadata minimization, stricter interactive-LLM contracts, and a collection-readiness linter for the LLM profile.
- A governed 20-category model-family catalog, structured task/modality/training profiles, and the fail-closed `mra model-coverage` command.
- A versioned 0.6 corrigendum and all-model coverage matrix incorporating the cumulative synthetic-health portfolio finding.

### Fixed

- Enforced LF checkout bytes for hash-bound text so examples remain valid on Windows.
- Bound assessment signing to the complete validated request/release and required exact report/manifest expiry agreement.
- Replaced claimant-selected provenance coverage with an exact framework-owned analyzer payload and routing check.
- Added a source-observed evidence context binding the release contract, policy, artifact, interface, population, decision game and observation time; removed post-analysis context stamping.
- Versioned the breaking assessment contract as request/report schema 3.0; v2 evidence cannot be upgraded by restamping missing source observations.
- Made the protocol benchmark unit test independent of ignored generated output and closed its SQLite tamper-test connection explicitly.
- Installed declared experiment dependencies in CI and included utility scripts in compilation checks.

## [0.5.0] - 2026-08-18

### Added

- Typed assessment and release-optimization contracts.
- Fail-safe assessment and release-selection engines.
- Replayable protocol-feasibility and incomplete-portfolio certificates.
- Versioned JSON Schemas, executable examples, CLI commands, and audit-chain support.
- OpenML benchmark configurations, retained provenance manifests, and evidence-generation utilities.
- GitHub CI, issue templates, security reporting guidance, and a controlled release workflow.

### Security

- Clearance requires applicable upper-bound evidence or a replayable certificate.
- Missing, stale, mismatched, or inconclusive evidence cannot authorize release.
- Assessment-to-release substitution and portfolio composition are checked explicitly.
