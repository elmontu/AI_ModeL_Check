# Protocol instantiation case studies

## Purpose and claim discipline

These cases demonstrate that MRAP can be instantiated for materially different
model-release surfaces and that unsupported evidence fails closed. They are
reproducible software-artifact evaluations, not evidence that XGBoost or LLM
releases are generally safe. No result below is a production authorization.

| Case | Evaluated object | What the repository establishes | What it does not establish |
|---|---|---|---|
| Ideal mathematical deployment | Lean registry/gateway functionality | A valid commit–activate–serve path exists; replay, stale commits, substitution, stale observations, expiry, suspension and revocation fail closed for all states admitted by the definitions | PostgreSQL, networking, cryptography, clock, availability, or implementation refinement |
| Authenticated lifecycle | Synthetic complete MRAP transcript | Valid signed transcript is accepted; tampering, replay, stale sequence, privilege confusion, unknown trust and known compromise are rejected | Correctness of a production identity service, registry, gateway or scientific evidence |
| XGBoost | Synthetic tabular classification pipeline | Reproducible training/audit artifacts, disjoint splits, simultaneous membership bounds, cache replay and `can_clear=false` | A privacy ceiling, full white-box coverage, external validity or safety of a real dataset/model |
| Interactive LLM | Watermark/canary preregistration | Complete binding, multiplicity, tail support, budget, custody, contamination and fail-closed decision semantics are validated | Watermark detection, canary attack execution, transcript assurance or LLM clearance |
| Other families | Structured model profile and governed 20-family catalogue | Required threat routing and explicit unsupported/custom-review outcomes | Scientific adequacy merely from catalogue coverage |

## Case 0: ideal mathematical deployment

`formal/lean/MRAP/Deployment.lean` treats infrastructure as an ideal
functionality so the protocol logic can be proved before a database is built.
The registry commit checks the exact predecessor head and sequence, strict
head advancement, a fresh nonce, cleared gates, and a live deadline in one
atomic transition. Activation then checks the current authorization, measured
artifact and interface, and a lease no longer than the authorization. Serving
rechecks the current active record, the gateway's observed head and sequence,
the requested bindings, and both time bounds.

Lean proves universal safety theorems for every state satisfying these
definitions and checks a concrete successful execution. It also relates every
reachable, unexpired lifecycle `ACTIVE` state to a serving ideal realization.
This establishes that the framework is mathematically deployable and not
vacuous. It is a specification for later refinement, not a statement that
PostgreSQL, Python, Ed25519, a real clock, or a distributed gateway already
implements the specification.

```bash
python scripts/verify_formal_protocol.py
```

## Case 1: authenticated lifecycle and adversarial mutations

`tests/test_release_protocol.py` constructs a complete lifecycle with a distinct
Ed25519 key for every role. Each artifact producer signs its declaration; each
event actor signs the event and signed artifact set; and the next event hashes
the complete signed predecessor. Verification uses public keys from a separate
trust-store file.

The positive structural and authenticated controls are paired with nineteen
unsafe mutations: failed atomic commit, broken chain, incomplete evidence,
wrong producer, path escape, expired authorization, cross-message payload,
unsupported rejection, non-increasing registry sequence, monitoring privilege
escalation, event/artifact tampering, cross-release replay, known compromise,
untrusted signer, profile downgrade, cross-event/duplicate artifacts and early
expiry. The evaluation reports a mutation score only over this
enumerated set.

```bash
PYTHONPATH=src python scripts/evaluate_protocol_mutations.py \
  --output output/protocol-mutation-evaluation.json
```

Expected invariant: both valid controls pass and all nineteen unsafe variants
are rejected. See [Protocol adversarial evaluation](protocol-evaluation.md) for
the interpretation and non-claim.

## Case 2: XGBoost classification audit

The end-to-end regression creates synthetic multiclass tabular data, runs the
trusted local worker, and verifies:

- independent target/reference training and disjoint utility/calibration/audit
  partitions;
- controlled XGBoost objectives and parameters;
- a recipient-realizable probability-and-true-label membership score;
- Bonferroni simultaneous TPR/FPR bounds across all registered replicates and
  prior-aware PPV summaries;
- deterministic UBJ/preprocessing release bundles with content hashes;
- raw-score replay, cache-key binding and recomputation after conclusion,
  parameter, protected-unit or model-byte tampering; and
- evidence direction restricted to `floor` or `screen`, with
  `can_clear=false` in every result.

```bash
PYTHONPATH=src python -m unittest tests.test_xgboost_runner -v
```

For a real study, copy
[`../reproduction/xgboost/config.example.json`](../reproduction/xgboost/config.example.json),
replace every placeholder, bind the exact trusted dataset, preregister the
recipient and operating point, then follow [the XGBoost worker guide](xgboost.md).
The synthetic regression is an implementation case, not an empirical privacy
claim. A successful attack may establish a leakage floor; an unsuccessful
attack never establishes a privacy ceiling.

## Case 3: interactive LLM watermark and canary preregistration

The LLM case deliberately ends before evidence generation. The template linter
checks two separate decision games—output watermark provenance and randomized
training-canary exposure—and prevents either a detector miss or null extraction
result from becoming clearance evidence. It checks exact release/interface and
LLM-component binding, fixed analysis families, simultaneous procedures, tail
sample support, key status/custody, query and concurrency reconciliation,
canary randomization/dose allocation, contamination controls, adaptive attack
budgets, immutable analyzer provenance and the complete retained-artifact
contract.

```bash
PYTHONPATH=src python scripts/validate_llm_audit_profile.py \
  reproduction/llm/audit-profile.example.json
PYTHONPATH=src python -m unittest tests.test_llm_audit_profile -v
```

The unit suite also constructs a fully populated collection-ready fixture and
shows that unsafe alternatives fail: `can_clear=true`, privacy blocking from a
watermark hit, reversed null-calibration logic, insufficient tail samples,
unregistered adaptive choices, budget overflow, future preregistration,
compromised keys and inconsistent concurrency or canary assignment.

This is intentionally not presented as a completed LLM audit. A publishable
empirical evaluation still requires an isolated collection/analyzer worker,
real bound endpoints, untouched prompts and canaries, raw transcript evidence,
registered baselines and attacks, power analysis, and external replication.
Until transcript-level assurance covers the complete interactive channel, an
LLM case remains non-clearing.

## Reproduce the formal and executable evidence together

```bash
python scripts/verify_formal_protocol.py
PYTHONPATH=src python scripts/evaluate_protocol_mutations.py
PYTHONPATH=src python -m unittest \
  tests.test_release_protocol \
  tests.test_formal_correspondence \
  tests.test_protocol_mutation_evaluation \
  tests.test_xgboost_runner \
  tests.test_llm_audit_profile -v
```

For a paper artifact, record the repository commit, Lean toolchain, Python lock
file, platform, command output and generated hashes. Report the formal theorem
scope, implementation mutation results and empirical model results as separate
evidence layers; combining them into one “verified safe” label would exceed
what any of the cases establishes.
