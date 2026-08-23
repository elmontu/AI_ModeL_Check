# Architecture

## Scope

MRA is an offline assurance core. It validates a release contract, evaluates bound evidence, selects among submitted release configurations, emits a typed report, and optionally appends that report to a hash-chained audit database.

The core occupies the assessment and selection stages of the normative [MRAP/1.0 lifecycle](model-release-assurance-protocol.md). Reports produced here are inputs to that protocol, not authorizations.

It does not load untrusted model binaries, operate a release gateway, own an authoritative portfolio registry, or provide production identity, key management, storage, and monitoring.

## Decision flow

```text
release request + policy + source-observed evidence context
                 |
                 v
  schema, model-family and hash validation
                 |
                 v
        evidence classification
       /          |           \
 exact/ceiling  attack floor  missing/screen
       |            |              |
       v            v              v
    may clear     may block     inconclusive
                 |
                 v
     privacy and utility feasibility
                 |
                 v
       portfolio-state validation
                 |
                 v
 least-informative feasible selection
                 |
                 v
typed report + optional signature + audit event
```

The enclosing lifecycle is:

```text
register -> freeze plan -> freeze evidence -> assess -> optimize
        -> submit authorization -> atomic portfolio commit
        -> gateway activation -> monitor -> suspend / expire / revoke
```

`release_protocol.py` can structurally replay this lifecycle as a hash-chained transcript. The authoritative registry, authenticated actors, gateway and monitor remain external production components.

## Package map

| Module | Responsibility |
|---|---|
| `models.py` | Versioned request, policy, evidence, and report contracts |
| `model_coverage.py` | Governed all-model catalog, alias routing, and non-clearing coverage review |
| `engine.py` | Assessment orchestration and fail-closed verdicts |
| `optimizer.py` | Feasible release-configuration selection |
| `decision.py` | Evidence classification and decision rules |
| `decision_theory.py` | Finite information-experiment comparison helpers |
| `portfolio.py` | Portfolio-state contracts and validation |
| `incomplete_portfolio.py` | Finite incomplete-portfolio solver and replay verifier |
| `portfolio_statistics.py` | Simultaneous marginal evidence generation and verification |
| `protocol_feasibility.py` | Finite protocol solver and exact certificate replay |
| `release_protocol.py` | Typed MRAP/1.0 transcript, state machine, artifact-role checks, and structural replay |
| `integrity.py` | Hashing and Ed25519 manifests |
| `audit.py` | Hash-chained SQLite audit records |
| `cli.py` | Command-line interface |

## Trust boundaries

The core accepts inert JSON and referenced evidence files. Assessment v3 requires workers to place release-contract, policy, artifact, interface, population and decision-game hashes in the source payload before analysis. The engine verifies that context and analyzers copy it into evidence records without restamping. Potentially hostile model parsing and empirical attacks belong in separate sandboxed workers. Production must also attest the worker identity/version and bind the current portfolio-registry head.

Final authorization must be committed atomically with the portfolio-state update. A read-evaluate-write sequence without transactional locking can approve individually valid releases against the same stale state.

## Extending the engine

1. Add or version the Pydantic contract.
2. Export and commit the matching JSON Schema.
3. Implement deterministic validation and explicit evidence semantics.
4. Add positive, negative, malformed-input, and replay tests.
5. Update examples and operational documentation.
6. Preserve backward compatibility or document a deliberate contract break.

New empirical analyzers must state whether their output is an upper bound, a lower bound, or a screen. A lower-bound attack result must never be routed into a clearance path.
