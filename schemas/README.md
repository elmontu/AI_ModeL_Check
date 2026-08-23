# Schema map

The repository contains several independently versioned machine contracts. A schema suffix does not identify the overall framework release.

## Current contracts

- `assessment-request-v3.json` and `assessment-report-v3.json`
- `optimization-request-v2.json` and `optimization-report-v2.json`
- `signed-optimization-manifest-v2.json`
- `release-protocol-run-v1.json`, the structural MRAP/1.0 lifecycle transcript contract
- `incomplete-portfolio-certificate-v1.1.json`
- the `v1` protocol-feasibility and portfolio-multinomial schema families, whose current contract version is 1.x

## Compatibility contracts

The assessment v1/v2, optimization v1, policy-bundle v1, and signed-manifest v1 files are retained for provenance and compatibility. They do not override the current v3 assessment and v2 optimization models in `src/model_release_assurance/`.

Assessment v3 adds the structured model profile and requires every analyzer input/evidence record to carry the source-observed release/policy/artifact/interface/population/game context. Assessment v2 evidence must be recollected or migrated by an approved worker; the core must not invent the missing source observations.

Generate a current schema with the CLI and name the output after the model's `schema_version`; do not overwrite an older versioned file with a newer contract.
