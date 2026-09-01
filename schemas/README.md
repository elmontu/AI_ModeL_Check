# Schema map

The repository contains several independently versioned machine contracts. A schema suffix does not identify the overall framework release.

## Current contracts

- `current-schema-manifest-v1.json` is the machine-readable inventory of every current contract below. It records the package version, CLI kind, Python model import and title, versioned filename, declared `schema_version`, and SHA-256 of the exact schema bytes.
- Assessment: `assessment-request-v4.json`, `assessment-report-v4.json`, and `policy-bundle-v2.json`.
- Assessment integrity: `signed-manifest-v2.json`.
- Optimization: `optimization-request-v3.json`, `optimization-report-v3.json`, and `signed-optimization-manifest-v3.json`.
- Incomplete portfolio: `incomplete-portfolio-problem-v1.json`, `incomplete-portfolio-certificate-v1.1.json`, and `incomplete-portfolio-specification-v1.json`.
- Portfolio statistics: the five `portfolio-*-v1.json` count, plan, error-budget, request, and evidence contracts.
- Protocol feasibility: `protocol-feasibility-problem-v1.json` and `protocol-feasibility-certificate-v1.json`.
- Release protocol: `release-protocol-run-v1.1.json` and `release-protocol-verification-v1.json`. Verification results name the profile, run hash, verification time, checks executed or skipped, and degradations.
- Local audit: `audit-verification-v2.json` and `audit-checkpoint-v1.json` for structured chain replay and externally retained ledger identity/count/head anchors. These contracts do not make SQLite immutable.

## Retained historical contracts

Older assessment, policy, manifest, optimization, incomplete-portfolio, and structural release-protocol schemas are retained so historical bytes and contract shapes remain inspectable. They do not override the current models under `src/model_release_assurance/`.

The current CLI intentionally rejects superseded top-level versions. Retaining a JSON Schema is structural provenance, not an executable historical verifier. Long-retention adopters must preserve the matching released wheel, dependency lock, trust metadata, and verification fixtures until version-dispatched historical replay is implemented. Evidence missing a required observation or producer binding must be recollected or migrated by an approved authority; the core must not invent it.

Assessment v4 makes single-release composition and declared-interface limits explicit, requires all structured observable-channel sections, dispositions every evidence identifier, and binds typed analyzer producer/configuration identities. Policy v2 pins minimum producer versions, accepted implementation/configuration digests, and accepted selection-policy digests. Optimization v3 binds the active policy, declared portfolio-registry snapshot, exact covered release set, and an allowlisted versioned selection policy. Reports include runtime/source attribution, and the signed assessment manifest directly binds the interface hash. These artifacts remain non-authorizing; snapshot authenticity, trusted builds, and protected release attestation are external controls.

Generate a current schema with the CLI and name the output after the model's `schema_version`; do not overwrite an older versioned file with a newer contract.

Run `make schemas` to regenerate and compare every current contract against its committed file and verify the manifest. After intentionally regenerating a versioned current schema, run `PYTHONPATH=src python scripts/generate_schema_manifest.py --write` to update the inventory. Compatibility-only schemas remain retained but are not regenerated from the current models.

The committed manifest is deliberately unsigned and says so explicitly. A repository-held private key or self-signature would not establish an independent trust anchor. A protected release process must sign or externally attest the exact manifest bytes and publish that signature, signer identity, certificate or public-key reference, and verification policy with the release artifacts.
