# Contributing

## Development setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[portfolio]'
```

Install `.[experiments]` only when working on optional benchmark tooling.

## Before opening a pull request

Run:

```bash
make check
```

If a Pydantic contract changes, regenerate the affected schema with `mra schema`, review the diff, and update the matching example and tests.

## Change requirements

- Preserve fail-closed behavior for missing or invalid evidence.
- Keep lower-bound attacks out of clearance paths.
- Bind new evidence to artifact, interface, population, policy, and portfolio scope.
- Add replay tests for any new certificate or accountant.
- Add malformed-input and negative tests for security-sensitive changes.
- Keep generated data, reports, model artifacts, audit databases, and local secrets out of Git.

## Pull requests

Describe the affected contract version, security invariants, test coverage, and compatibility impact. Keep unrelated refactors separate from behavior changes.

Changes affecting a public contract or decision outcome must include a `CHANGELOG.md` entry. Releases follow [`docs/releasing.md`](docs/releasing.md).

Security vulnerabilities should be reported through the process in [SECURITY.md](SECURITY.md), not a public issue.
