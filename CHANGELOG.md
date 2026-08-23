# Changelog

All user-visible changes to Model Release Assurance are recorded here. The project follows semantic versioning while it remains in the `0.x` alpha series; minor releases may change public contracts when the migration is documented.

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
