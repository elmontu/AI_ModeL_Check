# Executable examples

The root JSON files are executable fixtures for MRA 0.8. `examples/evidence/`
contains the evidence objects referenced by those requests. These fixtures are
not results from newly executed attacks or training runs.

Several JSON fixtures use a synthetic cross-government adopter profile. That is one demonstration context and does not define the sector-neutral product scope.

There are two different demonstrations:

- `make demo` trains real target/reference XGBoost models and follows the same
  candidate through evidence collection and assessment. It requires experiment
  dependencies and uses the public OpenML `sick` profile by default. Use
  `make demo DEMO_DATASET_PROFILE=sklearn-breast-cancer` for the offline profile.
  The transcript ends at `ASSESSED`, not authorization or deployment.
- `make demo-reference` runs the core-only fixture rehearsal without training.
  It copies a digest-pinned 17-file synthetic allowlist, joins a fresh
  assessment to optimization, exercises hold/block/tamper cases, and replays
  explicitly mock external workflow records. Open its generated `START-HERE.md`.

The [demo guide](../docs/guided-government-health-demo.md) explains both paths.
Neither changes the tracked fixtures or establishes clinical validity. The
healthcare narrative is illustrative; never put real patient data here.

- `request.json` uses assessment contract v5 and policy contract v3; it includes both a standalone single-attack floor and a complete typed membership attack battery. The policy-bound battery freezes the catalog, configuration, required attack, orchestrator/runtime/image identity, per-run and per-control executor identities, positive control, raw-result digests, catalog validity window, and declared isolation posture. Only the trusted-core analyzer converts passing results to floors, and the battery is a precondition for ceiling-based membership clearance.
- `evidence/assessment-clear-report.json` uses `AssessmentReport 6.0`. Report signing uses `SignedManifest 4.0`; request/policy consistency and evidence reduction must be verified, not inferred from a signature alone.
- `optimization-request.json` uses `OptimizationRequest 5.0`, whose assessment references bind both the report and its original request by path and SHA-256. It also binds the active policy, caller-supplied portfolio-registry snapshot, and policy-allowlisted selection rule. Optimization reports and signed optimization manifests use v5. Snapshot authenticity and active-inventory completeness remain external controls.
- `config/attack-catalog.json`, `config/attack-battery.json`, `config/attack-battery-analyzer.json`, and `evidence/attack-battery.json` are the replayable attack-battery demonstration. `scripts/refresh_example_contracts.py` deterministically regenerates their dependent hashes and the retained clear report; it does not execute an attack or authorize a release.
- Other example families are separately versioned; use the current [schema inventory](../schemas/current-schema-manifest-v1.json), not the package version, to select a contract.

Files under `output/assessments/` are generated demonstrations, not authoritative empirical results or retained governance records. Reproduction tools write generated records under ignored `output/reproduction/` paths; committed study inputs and maturity labels live under `reproduction/`.
