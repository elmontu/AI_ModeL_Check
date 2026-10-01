# Contributing

## Repository scope and contributions

This repository maintains the government audit implementation, its contracts,
tests, operating guides and dated advisory archive. Start with the
[government audit guide](docs/government-audit-guide.md) and the
[implementation boundary](docs/system-audit-specification.md#industrial-track).
The current research manuscript, its study protocols and paper-building tools
are maintained in a separate academic checkout; its public repository is still
pending publication. The [reproduction index](reproduction/README.md) describes
the historical assets retained here.

Label a contribution `government-implementation`, `advisory`, or `shared-core`
in its description. Use the existing library, contracts and canonical documents.
A shared-core change must explain its effect on research source bindings and
existing proof and evidence claims. Fix known fail-open defects without treating
research results as deployment approval. Authoritative identity, worker
isolation, registry and gateway services still need the acceptance evidence in
the [industrial track](docs/system-audit-specification.md#industrial-track).

For a new or revised advisory claim, identify its premises, proof status,
counterexamples, supporting source or experiment, and remaining gap.
Distinguish kernel-checked theorems, handwritten arguments, finite regression
checks and observations. New empirical claims require a frozen prospective
plan and fresh result paths in the academic workstream; do not restamp historical
studies. Navigation tests protect documentation structure, not scientific
correctness or novelty.

## Development setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.lock
python -m pip install -r requirements-experiments.txt
python -m pip install --no-deps -e .
```

This matches the dependency set used by CI for the complete repository check, including the optional experiment tests.

## Before opening a pull request

Run:

```bash
make check
```

Run `make verify` when changing MRAP protocol semantics, Lean artifacts, or the Python-to-Lean correspondence boundary.

If a Pydantic contract changes, regenerate the affected schema with `mra schema`, review the diff, and update the matching example and tests. An incompatible public-contract change requires a new schema version and migration note; never overwrite a retained compatibility schema with a different contract.

## Change requirements

- Preserve fail-closed behavior for missing or invalid evidence.
- Keep lower-bound attacks out of clearance paths.
- Bind new evidence to artifact, interface, population, policy, and portfolio scope.
- Bind every decision-bearing producer to a service ID, semantic version, implementation digest, and configuration digest accepted by policy.
- Add replay tests for any new certificate or accountant.
- Add malformed-input, substitution, expiry, replay, and capability-escalation tests for security-sensitive changes.
- Test the direction of each emitted evidence record: floor records cannot clear, ceiling records cannot block, screens cannot decide, and exact records cannot clear without complete coverage. An interval analyzer may emit separate floor and ceiling records; this is not permission for either record to exceed its authority.
- Keep generated data, reports, model artifacts, audit databases, and local secrets out of Git.

## Pull requests

Describe the affected contract version, security invariants, test coverage, and compatibility impact. Keep unrelated refactors separate from behavior changes.

Changes affecting a public contract or decision outcome must include a `CHANGELOG.md` entry. Releases follow [`docs/releasing.md`](docs/releasing.md).

Security vulnerabilities should be reported through the process in [SECURITY.md](SECURITY.md), not a public issue.

## Extension rules

Choose the owning layer first: reference core, evidence lab, formal abstraction or
external production integration. Define coverage, realizability, evidence direction
and maximum decision authority before adding an analyzer. Preserve all release,
policy, artifact, interface, population, game, source and time bindings. Include
positive, malformed, substitution, expiry, replay, contradiction, policy-version
and capability-escalation tests. Update the current schema registry, examples,
canonical audit specification and changelog; do not create another overview page.

Remote transports may return typed evidence, but central decision authority stays
in `AssuranceEngine`. They must not authorize, mutate a production registry or
expand scope. Workload identity, attestation, replay protection, resource limits,
isolation and durable orchestration must be established separately.

The package remains physically flat; current imports and source-bound studies
must not be moved merely for visual organization. Only explicitly documented
Python APIs are supported. The logical ownership map is in the
[system specification](docs/system-audit-specification.md#202-repository-responsibility-map).

## Support

This alpha reference library has no operational service-level commitment. Use
GitHub issues for reproducible defects, documentation corrections and bounded
feature proposals using synthetic or public data. Include the package version,
command/contract, expected and actual result, and a minimal reproduction.

Do not submit confidential data, private models, credentials, signing material or
sensitive attack details. Follow [SECURITY.md](SECURITY.md) for security reports.
Deployment authority, accreditation, key management and institutional risk
acceptance remain the adopter's responsibility.
