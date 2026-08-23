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

`release_protocol.py` can replay this lifecycle as a hash-chained transcript. Its structural profile checks state and binding rules; its authenticated profile additionally verifies release-bound Ed25519 event/artifact signatures against an external trust store and supplied compromise list. The authoritative identity system, registry, gateway and monitor remain external production components.

The independent `formal/lean` package is organized as the reusable `MRAP` protocol library. Its public umbrella exports lifecycle, symbolic authenticated-message, ideal atomic registry/gateway, and finite-statistical semantics; mutation witnesses and the axiom-audit entry point remain outside that public surface. It proves authorization integrity, message replay/binding properties, stale-head exclusion, role authorization, executable commit–activate–serve behavior, fail-closed substitution/expiry/revocation behavior, non-vacuity and a per-component finite statistical union bound. A checked correspondence manifest prevents vocabulary and permission drift, but neither the Python verifier nor a concrete registry/gateway has been proved to refine that specification; the formal theorem therefore applies directly to the Lean model, while implementation conformance remains test-based or external.

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
| `release_protocol.py` | Typed MRAP/1.0 transcript, state machine, artifact-role checks, structural replay, and trust-anchored authenticated replay |
| `integrity.py` | Hashing and Ed25519 manifests |
| `audit.py` | Hash-chained SQLite audit records |
| `cli.py` | Command-line interface |
| `formal/lean/` | Lean 4 lifecycle/message and ideal-deployment semantics, composed reachability, CAS, serving-denial, non-vacuity and finite statistical proofs |

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
