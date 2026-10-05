# PRD-18: controlled public-fixture delivery

Status: **in progress for production qualification**. The local implementation
has one scoped gateway route from a freshly reviewed public numeric candidate
to a bounded trusted writer. Production delivery is refused by default. No
private-data or agency model release is authorized. The framework remains
sector-neutral, targeting agency private cloud with provider and region open.

## Current admission and exact bytes

The additive execution bridge captures the original signed operator context
before the existing PRD-17 fresh registered fit and matches it to the retained
start record. There is no attach/import API for an old candidate, arbitrary
artifact path or caller-authored review. Activation requires exact current
policy, assessment and independent release-review acknowledgments, original
execution authority, retained evidence and candidate bytes.

The activation fixes case, agency/project, intended recipient, candidate hash
and size, policy/result/review bindings, review-store head and a short lifetime.
Its inert numeric JSON bytes are retained in a bounded ordinary-file SQLite
store. Generic public store methods expose metadata only. Only the gateway's
trusted sealed capability can activate artifacts or obtain an admitted chunk.
This is an API boundary within trusted Python, not protection against a
privileged process or filesystem administrator.

A human recipient must match a preconfigured recipient directory entry, current
case-scoped auditor assignment, dedicated signed `delivery:receive` scope and
current MFA. An auditor role or recipient name alone grants no bytes. Workload
recipients are unsupported in this profile. A current independent release actor
issues a grant to the recipient's verified raw token, exact credential digest,
activation and permanent transfer ID. A refreshed recipient token needs a fresh
grant. Grants retain their canonical recipient and current issuing authority.

Each chunk requires a fresh request and chunk ID. It may cover the next offset
or retry the exact range of a previously admitted chunk. A retry creates a new
admission and consumes additional attempted-byte capacity. IDs, grants,
activations and attempted-byte history are never reset or refunded. Transfers
are bounded by artifact size, chunk limits, admission count, attempted bytes and
exclusive grant/activation/evidence/token/delegation deadlines.

The store locks, replays history and bytes, checks the exact expected head and
retained checkpoint floor, rechecks current authority, then durably commits an
admission before returning its byte buffer to the gateway. The gateway retains
the new checkpoint before any writer call and performs current checks again
after checkpoint work. Final checks include the original operator, all reviewers
and grantors, issuer and recipient at one current timestamp. No earlier actor's
eligibility is silently carried through later work.

## Suspension, revocation and honest observations

Scoped current release or data-steward authority may suspend or revoke an
activation. Resume requires current original review/evidence authority and an
unexpired activation. Revocation is permanent. A grant can also be revoked.
Every later chunk admission checks the current durable state; an admission
ordered after suspension or revocation fails. An already admitted chunk may
escape before a later revocation. Previously disclosed bytes cannot be recalled.

Write observations distinguish returned, interrupted and failed writes. A
trusted writer can report a bounded known extent; an exception or invalid extent
records an unknown extent, because partial disclosure may already have occurred.
An admission is an attempted disclosure record, not evidence that the recipient
received bytes. No success/timeout/exception erases that record. Observations
may be retained after expiry/revocation as non-authorizing audit metadata.
Checkpoint or observation failure preserves uncertainty and consumes the
admission; it never silently authorizes a retry or claims delivery completion.

`public_fixture_bytes_delivered` means a trusted writer confirmed a positive
public-fixture extent. False is not proof of no disclosure when the extent is
unknown; inspect `disclosure_may_have_occurred` and `write_extent_known`.
`recipient_receipt_verified`, `model_delivery`, `authorization_eligible` and
`production_authorized` remain false. The HTTP test boundary buffers a chunk
and attaches admission/observation metadata. That buffer is not a real-network
recipient acknowledgment, TLS qualification or production streaming service.

## Checkpoint and startup boundary

Following the PRD-16 checkpoint principle, this new gateway retains explicit
own-log floors covering activations, grants, admissions, observations,
suspensions and revocations. Opening requires a separately known store identity
and event/head pin; it never invents a new floor or replacement ledger. A
restored prefix below that floor, fork, missing event, replacement store or
changed retained artifact is refused. The newest known pin stays in memory even
if its sink fails. Startup promotes and retains a newer validated store pin.

The local checkpoint sink uses exclusive canonical files, ordinary path checks,
file/directory identity checks, bounded reads and durable file flushes. It is
same-host trusted custody. Simultaneously rolling back the store and all trusted
external floors remains outside the guarantee. The new history is not enrolled
in an independently administered signed witness. PRD-15 fictional charges and
PRD-16's fixed-count witness remain preserved; they do not confer a privacy
accountant or atomic real-model release authority on this candidate.

After restart, retained records are historical. Live gateway contexts and the
original fresh-execution source bridge are not reconstructed from unsigned
metadata. There is no cached-approval or evidence-rehydration bypass. A new
usable public fixture requires fresh original execution and review authority.

## HTTP and CLI boundary

The explicit public-fixture FastAPI test app provides scoped activation, grant,
chunk and lifecycle routes. It rejects production startup, query-token
transport, cookies/browser sessions, duplicate bearer headers, unsupported
payload fields, caller paths and direct-file routes. It never exposes static
candidate directories or a raw-object download endpoint. Each chunk passes
through the same gateway admission. Generic store metadata cannot request bytes.

This is the sole byte route in the new controlled fixture. Earlier trusted-local
advisory consoles and public-data tools remain separate examples, not a protected
private-data deployment or a promise of machine-wide egress enforcement. Agency
network/IAM/object-store policies must remove alternate production routes before
go-live; privileged filesystem readers are outside this local API threat model.

From this government repository on D:, run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
& .venv-pipeline/Scripts/python.exe -B scripts/rehearse_controlled_delivery.py --profile local_public_fixture --output .local/controlled-delivery-v1
& .venv-pipeline/Scripts/python.exe -B scripts/run_required_tests.py --output .local/required-controlled-delivery-v1
```

Omitting `--profile local_public_fixture` refuses delivery before training or
output creation. The command accepts no private data, arbitrary model, artifact
path, recipient or caller admission. The rehearsal performs one real public
Wine fit, signed replay, independent reviews and exact candidate transfer,
then retains lifecycle, bypass and restore denials. Focused contract/store/
authorization/gateway/checkpoint/HTTP/CLI tests are in the required profile.
Final counts and source/evidence hashes are retained at
`.local/verification/prd18-delivery-20261002/validation.json`.

## Remaining production acceptance

Agency IdP/KMS and workload-recipient enrollment; independently administered
signed approval/delivery witnesses; accepted scientific criteria and privacy
accounting; atomic qualified model authorization; PostgreSQL/cloud recovery;
protected object/CLI/alternate-route IAM; TLS and actual network streaming,
stream cancellation, throughput and load qualification remain pending. No Linux
or private-cloud execution is claimed by local Windows verification.

Next is **PRD-19**, one approved profile end to end. GitHub publication remains
pending authentication; no staging, commit, tag, push or publication is performed.
