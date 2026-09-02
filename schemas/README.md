# Schema map

The repository contains several independently versioned machine contracts. A schema suffix does not identify the overall framework release.

## Current contracts

- `current-schema-manifest-v1.json` is the machine-readable inventory of all 26 current contracts below. It records the package version, CLI kind, Python model import and title, versioned filename, declared `schema_version`, and SHA-256 of the exact schema bytes.
- Assessment: `assessment-request-v5.json`, `assessment-report-v5.json`, and `policy-bundle-v3.json`.
- Assessment integrity: `signed-manifest-v3.json`.
- Attack execution: `attack-catalog-v1.json`, `attack-battery-configuration-v1.json`, `attack-positive-control-result-v1.json`, `attack-battery-worker-output-v1.json`, and `attack-battery-submission-v1.json`.
- Optimization: `optimization-request-v4.json`, `optimization-report-v4.json`, and `signed-optimization-manifest-v4.json`.
- Incomplete portfolio: `incomplete-portfolio-problem-v1.json`, `incomplete-portfolio-certificate-v1.1.json`, and `incomplete-portfolio-specification-v1.json`.
- Portfolio statistics: the five `portfolio-*-v1.json` count, plan, error-budget, request, and evidence contracts.
- Protocol feasibility: `protocol-feasibility-problem-v1.json` and `protocol-feasibility-certificate-v1.json`.
- Release protocol: `release-protocol-run-v1.1.json` and `release-protocol-verification-v2.json`. Verification results name the profile, run hash, verification time, checks executed or skipped, and degradations.
- Local audit: `audit-verification-v3.json` and `audit-checkpoint-v1.json` for structured chain replay and externally retained ledger identity/count/head anchors. These contracts do not make SQLite immutable.

## Retained historical contracts

Older assessment, policy, manifest, optimization, incomplete-portfolio, and structural release-protocol schemas are retained so historical bytes and contract shapes remain inspectable. They do not override the current models under `src/model_release_assurance/`.

The current CLI intentionally rejects superseded top-level versions. Retaining a JSON Schema is structural provenance, not an executable historical verifier. Long-retention adopters must preserve the matching released wheel, dependency lock, trust metadata, and verification fixtures until version-dispatched historical replay is implemented. Evidence missing a required observation or producer binding must be recollected or migrated by an approved authority; the core must not invent it.

Assessment v5 and policy v3 add a policy-bound complete attack battery, centrally replayed positive controls, orchestrator identity/image allowlists, catalog-bound service/version/implementation identity for every run and control, catalog-validity and evidence-time checks over freeze/execution, supported Bonferroni replay, observable timeout/trial/output-byte checks, declared isolation evidence, and an explicit per-threat ceiling-clearance mode. CPU/memory budgets are declared but not mechanically attested. Individual attacks still cannot clear. Optimization v4 carries the updated assessment and policy bindings. Reports include runtime/source attribution, and the signed assessment manifest directly binds the interface hash. These artifacts remain non-authorizing; worker authentication, externally attested isolation/resource enforcement, snapshot authenticity, trusted builds, and protected release attestation are external controls.

Versioned nested current contracts validate their own exact `schema_version`; changing or omitting a nested version fails validation. `InterfaceContract 3.0` adds a complete structured rate-limit declaration and embeds `LlmProtocolContract 1.0` where applicable. Required-explicit nullable interface/channel/LLM fields are retained as JSON `null` and participate in canonical contract digests.

Generate a current schema with the CLI and name the output after the model's `schema_version`; do not overwrite an older versioned file with a newer contract.

The first governed distribution must bind this exact manifest and all 26 schema bytes. If any adopter has already governed an earlier draft outside this repository, that draft becomes a historical baseline: preserve its exact bytes, assign new versions to incompatible replacements, and document the migration instead of treating this checkout as a fresh baseline.

Run `make schemas` to regenerate and compare every current contract against its committed file and verify the manifest. After intentionally regenerating a versioned current schema, run `PYTHONPATH=src python scripts/generate_schema_manifest.py --write` to update the inventory. Compatibility-only schemas remain retained but are not regenerated from the current models.

The committed manifest is deliberately unsigned and says so explicitly. It cannot recursively include the digest of its own final bytes; its `coverage` object records that self-exclusion. Deterministic exact-byte regeneration checks the manifest in-repository. A protected release process must separately sign or attest the exact manifest bytes and publish that signature, signer identity, certificate or public-key reference, and verification policy with the release artifacts.
