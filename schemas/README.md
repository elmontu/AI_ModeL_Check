# Schema map

The repository contains several independently versioned machine contracts. A schema suffix does not identify the overall framework release.

## Current contracts

- `assessment-request-v2.json` and `assessment-report-v2.json`
- `optimization-request-v2.json` and `optimization-report-v2.json`
- `signed-optimization-manifest-v2.json`
- `incomplete-portfolio-certificate-v1.1.json`
- the `v1` protocol-feasibility and portfolio-multinomial schema families, whose current contract version is 1.x

## Compatibility contracts

The assessment, optimization, policy-bundle, and signed-manifest `v1` files are retained for provenance and compatibility. They do not override the current v2 assessment and optimization models in `src/model_release_assurance/`.

Generate a current schema with the CLI and name the output after the model's `schema_version`; do not overwrite an older versioned file with a newer contract.
