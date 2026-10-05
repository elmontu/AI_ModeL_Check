# PRD-15 — registry transactions and recovery rehearsal

**Date:** 2 October 2026. **State:** in progress; bounded local implementation.
**Owner role:** Backend/database SRE; named agency owners remain pending.
**Dependencies:** PRD-02, PRD-06 and PRD-07, with current PRD-08 key trust.

The sector-neutral government framework now has a separate SQLite registry that
atomically records a case head, shared accounting head, fixed engineering charge,
immutable receipt, event and outgoing event intent. It uses the existing signed
identity and governed-storage fixtures. This does not authorize a model release.
The production target remains the agency private cloud; provider and region are
open. The [production roadmap](production-private-cloud-plan.md) still requires
PostgreSQL qualification, a real accountant, independent custody and release gates.

## Implemented boundary

Only PRD-07's exact 357-byte `public-counts-v1` fictional object is accepted.
The service independently checks its registered object/version/scope, content
hash and current retention before admission. No arbitrary JSON, private records,
model package, SACRO result, privacy mechanism or approved release is imported.
PRD-13 and PRD-14 evidence is preserved and is not reinterpreted as spending or
production approval. No prior implementation package was changed.

A trusted bootstrap configures immutable agency/project accounts. Every case in
one account shares eight **fictional engineering units**, with a charge of one
per new committed request. Case names, new object versions and request IDs cannot
reset that total. Unknown accounts cannot create capacity. There is no reset,
refund, account-creation endpoint or caller-selected cost/policy. Separate
agency/project accounts are an administrative fixture boundary; they do not
establish independent privacy populations or resolve cross-project composition.

All receipts and events explicitly set `privacy_accounting_supported`,
`authorization_eligible`, `production_authorized`, `assessment_eligible`,
`can_clear` and `model_delivery` to false. Hashes bind metadata; they are not
signatures or proof of independent authority.

## Transaction and current-authority rules

1. A human test operator supplies a raw signed JWT with current `job:run`
   permission for the exact case. PRD-06/08 check issuer/audience, current key,
   token lifetime, MFA, canonical person and current case grants. This fixture
   action records an engineering test transaction, not a policy or release vote.
2. `prepare` derives agency/project/account and person from trusted authority,
   verifies the exact fixed object bytes, and captures account and case heads.
   Its returned immutable request must be retained for retry. Snapshot reads may
   become stale; successful admission still requires both heads to match in one
   database transaction.
3. `commit` acquires `BEGIN IMMEDIATE`, validates the exact schema and bounded
   complete event history, verifies the active broker and current authorization,
   and compares both expected heads. It applies the fixed charge, receipt,
   event, heads and outbox atomically. After replaying the resulting state it
   rechecks current authority, trust and retention immediately before commit.
4. An exact request retry returns the original receipt after current eligibility
   checks. A changed request under the same permanent agency/project request ID
   conflicts. Token renewal or broker handover does not alter request identity;
   the receipt retains the original credential digest, authority/trust revisions
   and broker epoch. Raw tokens and private keys are never stored.
5. A revoked identity, expired object or missing current storage catalog cannot
   retry a commit. A current authorized case reader can separately inspect
   historical receipt metadata; this does not recreate release permission.

The lock order is current trust/identity, storage service/backend, then SQLite.
The final guard samples authorization after potentially expensive history and
byte validation. Trusted in-process role/key updates serialize on the shared
lock. This is not distributed revocation consistency across independent hosts.
A timeout or expired response after database commit is an **unknown outcome**:
read/retry the exact intent with current authorization; never restore capacity.

## Schema evolution and broker handover

`RegistryStore.create` requires a new directory, explicit account configuration
and schema version. `open` requires the expected registry ID/version and never
creates, repairs, upgrades or resets an existing database. Version 1 already
contains atomic charges, receipts, events and immutable outgoing intents.
The explicit version 1-to-2 migration adds durable delivery leases and
acknowledgements. It validates and preserves all prior accounting/receipt/outbox
records, backfills delivery state in one transaction, records the migration and
fences the old broker. A new broker requires explicit activation after migration.
Old-version handles fail closed. No automatic downgrade or rollback is supported.

Every operation validates exact table definitions, metadata, row bounds,
canonical records, event hashes and replayed materialized state. Missing or
changed rows, unexpected triggers, schema versions, divergent projections and
backwards clocks are rejected. Root/database file identities, ordinary file
paths, size bounds and SQLite rollback-journal settings are checked. The fixed
limits are 32 accounts, 128 cases, 256 receipts, 2,048 history events, 64 broker
identities, eight delivery attempts per event and a 16 MiB database. Full replay
on each operation is deliberately bounded; it is not a large-agency capacity
benchmark or a recommended production database access pattern.

Local broker epochs fence older handles against the same authoritative file.
The tests cover process crashes and local broker replacement. They do **not**
qualify PostgreSQL replication, stale replicas, multi-host leader election,
cloud failover or coordinated backup restoration. An administrator who rolls
back the entire store can also roll back its local hashes/epoch. Independent
rollback detection is the next task, PRD-16.

## Outgoing metadata and the local receiver

A current signed workload can claim events only for its authorized exact case.
Each bounded lease binds account/case, event ID, worker identity, broker epoch,
lease ID, generation and expiry. A stale broker, different worker, changed lease
or expired unacknowledged lease cannot acknowledge it. The same worker can use a
fresh valid token. Acknowledging the exact completed lease is idempotent under
the current broker. Exhausted attempts fail explicitly; they are not treated
as successful delivery. An empty claim means no event is available at that
instant, not that every event has been acknowledged.

The separate local receiver atomically stores one applied effect and receipt per
`(store_id, event_id)`. An exact duplicate returns the original receipt; the same
ID with different bytes conflicts. If the receiver commits and the sender loses
its acknowledgement, the sender redelivers the stable event and the receiver
keeps one effect. Claims and acknowledgements never change charge or case heads.
This demonstrates at-least-once metadata publication with local deduplication.

The receiver uses the same trusted local filesystem, accepts internal fixture
events, and is **not** an authenticated external service or independent witness.
The sender's acknowledgement is a current worker assertion; the registry does
not verify an external receiver signature. Neither exactly-once external model
delivery nor external event authenticity is established. PRD-16/18 own those
additional custody and delivery requirements.

## Reproduce the local rehearsal

From the government repository on D:, use the existing core environment:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONPATH=Join-Path (Get-Location).Path 'src'
& .\.venv-pipeline\Scripts\python.exe -B scripts/rehearse_registry_transactions.py --output .local/registry-rehearsal-v1
```

Choose a new ignored `.local` directory. Existing evidence is never overwritten.
The command accepts only an output option; it does not fetch data, access the
research repositories, contact a cloud service, open a listener or publish to
GitHub. Ephemeral signing keys stay in memory. A synthetic clock tests deadline
boundaries. Retained files contain only fictional counts, metadata, SQLite state
and source-bound results.

The command checks two commits across two cases, current-token idempotency,
stale-head refusal, explicit migration, broker fencing, denied unconfigured
scope, lost-ack redelivery, wrong/stale lease rejection, receipt retention after
restart and the inability of an empty storage catalog to reauthorize old input.
It also verifies that all participating source files remain unchanged.

The required suite includes `test_production_registry_*.py`. Store/receiver tests
use independent processes for duplicate/racing requests and abrupt exits around
commit; service tests use actual signed credentials and a held database lock.
Saved local results are under `.local/verification/prd15-registry-20261002/`.
The final validation receipt records exact counts, build hashes, installed-wheel
checks and preservation of earlier evidence.

## Remaining production acceptance

- Implement and qualify the supported PostgreSQL adapter/migrations under actual
  transaction isolation, contention, replication, leader changes and failover;
  preserve these invariants and immutable migration checksums in agency custody.
- Bind an independently accepted accountant to registered mechanisms, protected
  entities, overlapping populations, all prior disclosures and approved limits.
  Ordinary model training and attack scores do not supply epsilon/delta.
- Persist identity/trust, revocation and governed object authority. Reopening
  this registry alone never restores the in-memory PRD-06/07/08 controls.
- Add independent witness/intent custody and reconcile rollback, lost events,
  stale replicas and unauthorized new ledgers in PRD-16.
- Bind approved policy/evidence/independent review in PRD-17, enforce the sole
  delivery gateway in PRD-18, then demonstrate the complete selected profile.

PRD-15 remains **in progress**. The next implementation step is **PRD-16**.
GitHub publication remains pending authentication; no deployment or release is
implied by a local passing test.
