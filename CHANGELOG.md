# Changelog

All user-visible changes to Model Release Assurance are recorded here. The project follows semantic versioning while it remains in the `0.x` alpha series; minor releases may change public contracts when the migration is documented.

## [Unreleased]

### Added

- No unreleased changes yet.

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
