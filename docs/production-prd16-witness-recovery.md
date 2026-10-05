# PRD-16 — witness checkpoints and intent recovery

**Date:** 2 October 2026. **State:** in progress; bounded local implementation.
**Owner role:** Security/database SRE; agency appointments remain pending.
**Dependencies:** PRD-08 current trust and PRD-15 registry transactions.

A separate witness fixture now retains the complete accepted registry event
history, irreversible pre-commit intents and its own ordered checkpoint log.
It detects an old or divergent registry against that retained history, and an
old witness against an explicitly supplied external checkpoint floor. Recovery
can reconcile an uncertain commit to its original receipt and charge. This is
sector-neutral government engineering work using fixed fictional counts.

The [private-cloud plan](production-private-cloud-plan.md) remains the production
target. Provider and region remain open. Separate local directories, unsigned
checkpoint hashes and a trusted in-process callback do not establish physical
independent agency custody, authenticated remote witness responses, KMS signing,
PostgreSQL failover or model-release authority. Those acceptance gates remain open.

## Fixed namespace and independent expectations

Trusted bootstrap enrolls one explicitly configured agency/project accounting
namespace and its exact existing PRD-15 registry UUID. Enrollment accepts a fresh
registry with no committed requests. It never adopts historical spending as if
it had witnessed earlier intent, selects a new registry UUID, resets spending or
creates capacity. Multiple projects require separately reviewed composition and
custody arrangements; the fixture does not establish independent populations.

The witness stores full canonical registry event bodies, including creation,
broker, migration, commit, outbox claim and acknowledgement transitions. Retaining
only commit/outbox hashes would omit security-relevant history. Every operation
replays PRD-15 semantics and verifies the accepted history is an exact prefix of
the new observation. A shorter history, changed prefix/head, missing or reordered
event, invalid charge/receipt, substituted UUID or unauthorized new commit is
rejected. A commit must match an exact intent already retained by the witness,
including its original broker epoch. An intention added after the commit cannot
retroactively qualify it.

The separately retained pin binds witness UUID, namespace, registry UUID and the
witness's own log revision/head. Its own log covers intent creation and resolution
as well as registry observations. Pinning only the registry head could lose an
intent while that registry head remains unchanged. Reopen requires an explicit
known pin and verifies it is an exact retained ancestor. Missing pins never
default to genesis. A service that observes a newer pin during startup must retain
that pin before continuing.

The fixture checkpoint sink writes exact pin files exclusively into a dedicated
directory and flushes them before acknowledging. Directory identity, ordinary
paths and bounded same-handle file reads detect replacement/corruption. These
checks test local storage behavior; production must provide separately protected,
durable checkpoint custody and an authenticated monotonic service. Restoring the
registry, witness **and** every trusted external checkpoint together remains
outside the demonstrated protection.

## Admission and final synchronization

1. A human test operator supplies a current raw signed JWT for the exact case.
   The service checks canonical actor, agency/project namespace, current key,
   roles, token/MFA lifetime and current trust. It receives an immutable PRD-15
   request with exact object and account/case predecessors.
2. While holding the registry write transaction, the internal history reader
   copies and validates all bounded events. The witness checks continuity and
   retains the exact irreversible intent. The required checkpoint sink must
   confirm its new pin before the separate registry commit is attempted.
3. PRD-15 performs its atomic fixed charge/head/receipt/event/outbox transaction,
   including registered object bytes, current authority and retention checks.
   The witness does not change that implementation or confer privacy semantics.
4. The service takes another locked complete registry observation, reconciles the
   exact commit into the witness, persists the resulting pin and rechecks current
   authorization after sink latency. The registry's final guard runs after that
   callback, before a witnessed metadata receipt is returned.

Lock order is current trust/identity, registry database, then witness database.
The reader never calls registry commit while its write transaction is held.
Intent, commit and final synchronization are distinct durable stages; failures
between them are expected recovery cases. A witness or checkpoint-sink outage
before retained intent prevents charge. An outage after registry commit retains
the charge and pending intent and produces no witnessed-success response.
A callback receives an owned pin, so mutation cannot downgrade the service floor.
The newest observed floor is retained in memory even when its sink fails.

A final witnessed receipt means the fixed local metadata history was reconciled
at that guarded observation. The fixture has no prediction/model delivery route.
Every record keeps `can_clear`, `assessment_eligible`, `authorization_eligible`,
`production_authorized`, `privacy_accounting_supported` and `model_delivery`
false, and `independent_custody_verified` false.

## Recovery, permanent intents and quarantine

A current authorized case reader can reconcile historical metadata even after
object retention expires. This does not re-read private/model bytes or recreate
old object grants. A committed but unacknowledged outcome resolves to its exact
original receipt; recovery never makes a new request ID, a second charge, a refund
or a replacement ledger to escape the original outcome.

An absent receipt, timeout or broker handover leaves an intent pending. PRD-15
requests deliberately survive broker changes, so an epoch increase alone does
not prove the request can never commit. The local witness aborts a missing intent
only when a fully validated account sequence has advanced beyond its expected
predecessor: its compare-and-swap can no longer succeed. The abort remains a
permanent tombstone. Two intents can race from the same predecessor; one valid
commit can resolve the winner and prove the losing predecessor superseded.

Any unresolved intent quarantines final witnessed success. A pending old-broker
intent cannot be silently resubmitted under a new broker. A direct PRD-15 commit
without a prior exact witness intent causes reconciliation to fail and does not
advance the witness's accepted checkpoint. Contradictory observations are not
silently repaired, and no old receipt is restamped as new approval.

## Reproduce the local check

From the government repository on D:, using the core runtime:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONPATH=Join-Path (Get-Location).Path 'src'
& .\.venv-pipeline\Scripts\python.exe -B scripts/rehearse_witness_recovery.py --output .local/witness-rehearsal-v1
```

Use a new ignored `.local` directory. The command accepts only an output option,
uses fixed fictional counts and ephemeral signed identities, and retains no raw
JWTs or private keys. It does not fetch research data or contact a cloud service.
The synthetic clock supports reproducible expiry checks.

The command tests intent checkpoints, exact retries, stale replicas, witness
outage after a real registry commit, recovery to the original receipt, restoration
of an old registry, restoration of the witness below a retained external floor,
and rejection of a replacement registry UUID. It retains separate registry,
witness and checkpoint directories plus a source-bound result. Local validation
receipts are under `.local/verification/prd16-witness-20261002/`.

The required profile includes `test_production_witness_*.py`. Tests cover complete
history replay, rehashed invalid records, permanent intent constraints, concurrent
processes, abrupt process exit before/after witness commit, retained external
floors, CAS-only abort, sink failure, current authority after sink latency,
expired-object historical recovery and checkpoint path/file replacement. The
witness bounds are a 32 MiB database, 16 MiB retained registry history, 512 own-log
events, 128 permanent intents and 32 pending intents. These deliberately bounded
full-replay fixtures do not establish production throughput or capacity.

## Remaining production acceptance

- Place registry, witness, recovery events and external floors under separately
  administered agency custody, with protected identities, deployment admission,
  durable retention, outage behavior, incident controls and reviewed residual risk.
- Authenticate registry-to-witness observations and witness responses with approved
  keys/provider adapters, rotation/revocation and current trusted time. Local
  hashes and trusted Python callers cannot attest arbitrary appended events or
  withstand colluding administrators across every custody domain.
- Qualify PostgreSQL replication/failover and restored WAL/event/object reconciliation
  against witness state. Reject stale leaders/replicas, unauthorized new ledgers,
  missing negative transitions and unexplained intents before reopening delivery.
- Persist agency identity/trust and object authority, qualify real privacy accounting,
  and integrate policy, evidence and independent review in PRD-17.
- Enforce the sole delivery gateway in PRD-18 and demonstrate the complete accepted
  profile in PRD-19. A witnessed fixture receipt itself cannot authorize delivery.

PRD-16 remains **in progress** for these deployment acceptance gates. Next is
**PRD-17**, policy-authority approval and independent review. GitHub publication
remains pending authentication.
