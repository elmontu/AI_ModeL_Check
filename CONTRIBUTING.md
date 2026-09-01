# Contributing

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
- For every evidence producer, require the direction-specific negative class: floors cannot emit clearing records under any input; ceilings cannot emit blocking records; screens cannot decide; exact evidence cannot clear without complete coverage.
- Keep generated data, reports, model artifacts, audit databases, and local secrets out of Git.

## Pull requests

Describe the affected contract version, security invariants, test coverage, and compatibility impact. Keep unrelated refactors separate from behavior changes.

Changes affecting a public contract or decision outcome must include a `CHANGELOG.md` entry. Releases follow [`docs/releasing.md`](docs/releasing.md).

Security vulnerabilities should be reported through the process in [SECURITY.md](SECURITY.md), not a public issue.
