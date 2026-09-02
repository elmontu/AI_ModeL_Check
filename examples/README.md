# Executable examples

The root JSON files are current executable inputs for MRA 0.7. `examples/evidence/` contains evidence objects referenced by those requests.

Several JSON fixtures use a synthetic cross-government adopter profile. That is one demonstration context and does not define the sector-neutral product scope.

- `request.json` uses assessment contract v5 and policy contract v3; it includes both a standalone single-attack floor and a complete typed membership attack battery. The policy-bound battery freezes the catalog, configuration, required attack, orchestrator/runtime/image identity, per-run and per-control executor identities, positive control, raw-result digests, catalog validity window, and declared isolation posture. Only the trusted-core analyzer converts passing results to floors, and the battery is a precondition for ceiling-based membership clearance.
- `optimization-request.json` uses optimization contract v4 with a hash-bound active-policy reference, caller-supplied portfolio-registry snapshot, and versioned selection policy whose canonical digest is allowlisted by the active policy. Snapshot authenticity and active-inventory completeness remain external controls.
- `config/attack-catalog.json`, `config/attack-battery.json`, `config/attack-battery-analyzer.json`, and `evidence/attack-battery.json` are the replayable attack-battery demonstration. `scripts/refresh_example_contracts.py` deterministically regenerates their dependent hashes and the retained clear report; it does not execute an attack or authorize a release.
- incomplete-portfolio, multinomial, and protocol examples use their separately versioned v1 or v1.1 contract families.

Files under `output/assessments/` are generated demonstrations, not authoritative empirical results or retained governance records. Reproduction tools write generated records under ignored `output/reproduction/` paths; committed study inputs and maturity labels live under `reproduction/`.
