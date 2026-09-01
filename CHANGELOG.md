# Changelog

All user-visible changes to Model Release Assurance are recorded here. The project follows semantic versioning while it remains in the `0.x` alpha series; minor releases may change public contracts when the migration is documented.

## [Unreleased]

### Added

- A standalone integrated system audit specification consolidating the complete architecture, normative MRAP roles/messages/states/gates, current release contracts and pipelines, evidence semantics, threat and formal boundaries, production obligations, pass/fail rules, and an auditor checklist.
- Assessment request/report 4.0, policy 2.0, signed assessment manifest 2.0, optimization request/report 3.0, and signed optimization manifest 3.0 contracts.
- Machine-readable assessment scope (`single_release_no_portfolio`, `declared_interface_only`, live-interface false, authorization-ineligible) and optimization bindings for the active policy, declared hash-bound portfolio-registry snapshot, exact covered releases, and versioned ordered selection policy.
- Typed evidence-producer service/version and implementation/configuration digests, with policy minimum versions, digest allowlists, required-analyzer rules, and fail-closed stale-producer rejection.
- Two-phase assessment/optimization audit events (intent plus completed/failed), orphan detection, ledger identity, contiguous sequence/tail checks, structured verification, and externally anchorable ledger checkpoints.
- Machine-readable release-protocol verification results recording the profile, run hash,
  verification time, artifact/signature verification booleans, skipped checks, and degradations.
- Required structured interface declarations for output/download/summary, serialization, timing,
  error/status, execution-state/concurrency, and side/local/administrator access channels.
- Deterministic runtime identities on assessment, optimization, lifecycle, and audit verification
  outputs, including package-source and transparent algorithm-profile digests.
- A centralized 21-contract schema registry and deterministic exact-byte current-schema manifest;
  trusted release signing/attestation remains an external protected-identity operation.
- A retained twelve-case post-critique control evaluation covering interface completeness, future
  registry times, selection-policy authorization, evidence disposition, manifest interface binding,
  audit splicing, state-head replay, runtime attribution, CLI verdict semantics, and binary64 drift.
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

### Changed

- Default analyzer-service capabilities are derived from implemented behavior and cannot be widened by adapter configuration; only DP ceilings and recipient-realizable tree exact evidence currently provide shipped clearing paths.
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

### Removed

- Removed the dated framework audit/corrigendum documents and the frozen Version 0.5 prospective-study runner, analyzer, configuration, test, and seal requirements. Superseded schemas remain historical structural records for provenance and external schema validation; the current CLI accepts only current contract versions.

### Fixed

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
