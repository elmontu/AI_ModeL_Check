# MRAP protocol library

This standalone Lake package is the reusable, machine-checked protocol core of
MRAP/1.0. It uses Lean 4.32.1 and only Lean's standard library;
`lean-toolchain` pins the exact compiler release. The package name is
`mrap-protocol`, and the public Lean library is `MRAP`.

## Public import surface

Consumers may import the complete public library:

```lean
import MRAP
```

or depend only on the relevant layer:

```lean
import MRAP.Protocol
import MRAP.Deployment
import MRAP.Security
import MRAP.Statistics
```

`MRAP.lean` is the stable umbrella. `MRAP/Mutants.lean` and `Main.lean` are
audit artifacts and are intentionally not re-exported by the public library.

## Reproduce

From this directory:

```bash
lake build
lake env lean Main.lean
```

From the repository root, the wrapper additionally checks the toolchain,
forbids proof placeholders, and enforces the accepted axiom list:

```bash
python scripts/verify_formal_protocol.py
```

## Modules

- `MRAP/Protocol.lean` defines roles, authorized actions, protocol state,
  transition rules, reachability, authorization integrity, compare-and-swap,
  and a non-vacuous valid trace to `ACTIVE`.
- `MRAP/Deployment.lean` defines an ideal atomic authorization registry,
  measured gateway activation, bounded serving leases, revocation/suspension,
  and proves commit, binding, freshness, stop-service, realization, and
  executable deployment properties.
- `MRAP/Security.lean` defines bound authenticated envelopes, nonce replay and
  compromise checks, and the composed authenticated-lifecycle reachability
  relation.
- `MRAP/Statistics.lean` proves a finite weighted union bound and the resulting
  per-component registered false-authorization error-budget theorem without an
  independence assumption.
- `MRAP/Mutants.lean` contains negative witnesses for direct unsafe activation,
  stale commits, and unauthorized registry commits.
- `MRAP.lean` is the public library umbrella.
- `Main.lean` is the audit entry point and prints the axioms on which the
  reviewed theorem set depends, including audit-only mutation witnesses.

The precise interpretation, trusted base, theorem-to-protocol correspondence,
and non-claims are in [`../../docs/formal-verification.md`](../../docs/formal-verification.md).
