# PRD-07: governed object references and scoped storage

**Record:** PRD-07 / revision 0.1 / 1 October 2026.
**State:** `in_progress`; local public-fixture implementation, pending cloud
qualification and agency acceptance.
**Inputs:** [production roadmap](production-private-cloud-plan.md),
[threat model](production-prd02-threat-model.md),
[infrastructure boundary](production-prd05-infrastructure-scaffold.md) and
[identity contract](production-prd06-identity-and-approvals.md).
Work stays in the government repository on D:. Provider and region remain open.

## Result and boundary

The separate [storage package](../src/model_release_assurance/production_storage/)
registers a fixed fictional JSON fixture, returns immutable exact references,
freezes reference manifests and grants a current workload one bounded read of
one exact version. Human case access alone never permits a byte response.
The fixture also evaluates retention and holds without deleting anything.

Only the built-in `public-counts-v1` catalog entry is accepted. No request can
supply a dataset, file path, URL, executable model, archive, query or linked
population. The JSON values are invented aggregate counts, not agency records
or evidence that anonymization succeeded. This fixture cannot establish a
privacy guarantee, mechanism, disclosure budget or release authorization.

The implementation is deliberately separate from the existing local console
and temporal APIs. Those paths are not protected by this storage factory.
Do not connect them to private objects or describe this fixture as the sole
production gateway. PRD-18 must enforce the eventual recipient delivery route.

## Exact references and bounded local custody

An object reference binds generated object and version IDs, agency, project,
case, exact SHA256 and byte length, JSON format, catalog ID, creation time,
retention commitment and fixed source/query/transform/linkage identifiers.
Its reference digest covers the complete canonical descriptor. The descriptor
must match the server's registered record exactly. A matching content hash
alone grants no cross-case entitlement.

Snapshots bind one to eight unique exact object versions in the same scope.
They preserve fixed fictional provenance, reject caller queries and cannot
extend beyond any constituent object's retention commitment. Snapshot
manifests are metadata contracts; this implementation grants reads per object,
not arbitrary queries or bulk snapshot downloads.

The trusted bootstrap creates a fresh local store. Server-generated names,
exclusive file creation, directory/file identity checks, link/reparse rejection
and bounded same-handle reads detect tested traversal, substitution and
tampering attempts. A read verifies size, digest and the fixed JSON content
against the exact registered reference before returning that same buffer.
The hard ceiling is 64 KiB per object; it is a defensive fixture bound, not an
agency-scale performance claim. Archives, compressed input, executable formats,
duplicate/nonfinite JSON fields and unsupported content are refused; no archive
is extracted and no model is deserialized. At most 256 object files can be
created per fixture store, including retained files from failed registrations.

Metadata access validates registered references without reading object bodies.
It does not attest that stored bytes remain intact; the byte-read boundary
performs that integrity check. No mutable `latest` alias or caller storage
locator is supported.

Local files are not encrypted cloud objects or WORM storage. Registry,
snapshots, grants and hold state are process-local; the store intentionally
requires a fresh root and does not reopen an existing directory as trusted
state. Host administrators, malicious in-process code, distributed races and
whole-store rollback are outside this fixture's protection. Production needs
protected durable records and independently administered custody.

## Current authorization and one-use reads

The existing pinned access-token verifier and current authority service remain
the only source of identity. Storage adds these explicit actions:

| Action | Current authority required |
| --- | --- |
| `object:register`, `snapshot:freeze` | Human data steward, exact case grant and fresh configured MFA |
| `object:grant`, `object:hold` | Human data steward with the same current checks |
| `object:metadata` | Human with an authorized case-reader role and matching token scope |
| `object:read` | Workload identity with current worker role and exact case grant |

The grant request includes a signed target workload token and a bounded job ID.
The workload token must include `object:read` and the exact signed
`job:<job_id>` scope. The service verifies it using current authority before
issuing a grant; a caller-made identity or job string is insufficient. Passing
a target token is a local test mechanism, not a proposed production credential
handoff workflow. No token is echoed or written to fixture object files.

Each grant binds the full verified workload identity, canonical principal,
exact object reference, job, grantor and authority revision. Its lifetime is
1Ã¢â‚¬â€œ60 seconds and cannot exceed either credential's expiry. A new token,
different job/object/case, changed authority revision, stale authority, expired
credential, revoked grant or consumed grant denies the read. Human operators,
auditors, platform roles and even a human labelled `worker` cannot use it.

Identity then storage locks serialize local decisions. The read buffers and
validates bounded bytes, rechecks current worker and grantor authorization plus
the grant deadline, and consumes its single use before returning. A failed
read returns no object body. Successful consumption is not refunded if the
client loses the response. Revoked/consumed/expired grant IDs remain tombstones;
the fixture caps lifetime grant records at 256 and snapshots at 64.

These controls do not run or attest a worker job. A signed job scope is not a
scheduler lease, approved image, sandbox attestation or bounded source query.
PRD-10 must supply those controls. Read-use counts and byte ceilings are I/O
limits, not differential-privacy accounting or a release admission transaction.

## Retention and holds

A steward selects a fixture retention commitment of 1Ã¢â‚¬â€œ86,400 seconds when
registering an object. It is immutable within that reference. These test values
are not an agency retention schedule. Retention is a minimum preservation
commitment, not an automatic deadline for authorized access. A separate
steward-controlled hold
blocks deletion eligibility; it does not silently revoke authorized reads.
Outstanding unconsumed, unrevoked, unexpired grants conservatively block
deletion eligibility even if another authorization change makes them unusable.

The deletion check reports blockers and always sets `deletion_performed` to
false. There is no delete, purge, retention-shortening or cleanup endpoint.
An eligible observation is not permission to delete production data. Legal
holds, classification, retention ownership, backup deletion and durable
concurrent enforcement require agency decisions and provider qualification.

## Explicit fixture HTTP surface

The factory requires `create_fixture_app(service, environment="public_fixture")`.
It refuses other environments and exports no ready-to-serve global app.
Protected routes below share `/v1/cases/{case_id}/`:

| POST suffix | Exact JSON fields |
| --- | --- |
| `fixture-objects` | `fixture_id`, `retention_seconds` |
| `object-metadata` | `reference` |
| `fixture-snapshots` | `references` |
| `object-read-grants` | `reference`, `worker_token`, `job_id`, `ttl_seconds` |
| `object-reads` | `reference`, `grant_id` |
| `object-read-grants/revoke` | `grant_id` |
| `object-hold` | `reference`, `held` |
| `object-deletion-check` | `reference` |

The public `GET /healthz` response is non-authorizing. Protected requests
require exactly one Authorization bearer header. Cookies, browser origins and
query parameters are refused. Bodies are limited to 32 KiB with strict JSON
fields and no compressed encoding. Errors do not expose tokens or paths.
Responses disable caching and declare fixture-only, non-authorizing,
non-delivery status; the byte response uses equivalent headers.

There is no generic upload, listing, URL fetch, presigned object URL,
model export, administrative identity change or deletion route.

## Local verification result

Observed on 1 October 2026: **472 required tests passed with zero failures
and zero skips**. This includes 53 new storage tests (18 backend, 21 service,
14 signed HTTP) and three additional identity-policy regressions.
**31 required-runner/documentation tests** also passed. The mandatory profile
binds the current source files and dependency locks before and after execution.

Review corrected metadata body reads before grant authorization and a
grant-deadline race between sequential identity checks. Regression tests cover
both fixes, concurrent single-use redemption, post-I/O expiry, cross-case and
token substitution, file tampering, compressed/archive content, holds and
retention decisions. All 84 package files preceding PRD-06 and the prior
PRD-04/05/06 evidence were verified unchanged. The 123 retired archive
deletions remain preserved.

## Reproduction and remaining acceptance

From the D: government checkout, using its configured environment:

```powershell
& .\.venv-pipeline\Scripts\python.exe -B -m unittest discover -s tests -p "test_production_storage*.py" -v
& .\.venv-pipeline\Scripts\python.exe -B scripts/run_required_tests.py --profile government --output .local/ci-required-prd07
```

Choose a fresh required-profile output directory. Its three storage suites are
explicit mandatory selections; missing suites, failures and skips fail the
profile. Tests create fictional bytes and ephemeral signing keys only.
Local verification evidence is retained under
`.local/verification/prd07-storage-20261001/`; earlier receipts remain
historical records of their captured revisions.

Production closure requires approved private intake and quarantine, selected
provider IAM/private endpoints/encryption, immutable version and retention
custody, durable current grants/revocation/holds, protected recovery, and
independently tested direct-storage bypass denial. Keep private bulk data in
the agency data plane. Qualify approved immutable cohort/query/transform/linkage
manifests and scoped in-cloud access against the real source systems, with
bounded scans, resource quotas and measured agency-scale throughput.

PRD-02/05 approvals and accountable data-steward decisions remain open.
[PRD-08](production-prd08-key-trust.md) now adds local key-trust contracts and
rotation/revocation/outage tests across these storage grants; agency key-service
selection and deployed custody remain pending.
GitHub publication and remote CI execution remain pending authentication.
