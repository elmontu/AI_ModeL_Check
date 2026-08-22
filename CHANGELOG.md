# Changelog

All user-visible changes to Model Release Assurance are recorded here. The project follows semantic versioning while it remains in the `0.x` alpha series; minor releases may change public contracts when the migration is documented.

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
