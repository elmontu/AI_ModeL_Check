# Executable examples

The root JSON files are current executable inputs for MRA 0.7. `examples/evidence/` contains evidence objects referenced by those requests.

Several JSON fixtures use a synthetic cross-government adopter profile. That is one demonstration context and does not define the sector-neutral product scope.

- `request.json` uses assessment contract v4 and policy contract v2; `optimization-request.json` uses optimization contract v3 with a hash-bound active-policy reference, caller-supplied portfolio-registry snapshot, and versioned selection policy whose canonical digest is allowlisted by the active policy. Snapshot authenticity and active-inventory completeness remain external controls.
- incomplete-portfolio, multinomial, and protocol examples use their separately versioned v1 or v1.1 contract families.

Files under `output/assessments/` are generated demonstrations, not authoritative empirical results or retained governance records. Reproduction tools write generated records under ignored `output/reproduction/` paths; committed study inputs and maturity labels live under `reproduction/`.
