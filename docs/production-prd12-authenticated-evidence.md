# PRD-12: authenticated local execution evidence

Status: **in progress**. This milestone adds a signed, one-use evidence path for
fresh replay operations over PRD-11's public numeric candidates. It binds the
exact job, attempt, plan, source labels, policy, adapter, observed local runtime
and artifact bytes. Production image attestation, cloud isolation and agency
admission remain unimplemented. The provider and region remain open.

The framework remains sector-neutral: census, aviation, lending, mobility and
bundled classification/regression examples use the same evidence contract.
Public health is one example agency pilot. No private agency data is admitted.

## What the signature establishes

The signed operation is explicitly `retained_native_replay`. The verifier issues
and durably records a challenge before a new replay operation. A purpose-specific
RSA key signs the result under the PRD-08 current trust registry. The envelope
binds issuer, audience, agency, environment, worker owner, key ID and public-key
fingerprint along with the statement. Its domain is distinct from access tokens
and local build provenance. JSON fields, scalar types, bounds and canonical byte
encoding are exact; ambiguous or unknown fields are refused.

A signature establishes integrity under the configured ephemeral fixture key.
It does not establish honest historical training, independently authenticated
source acquisition, an approved agency identity or a trusted execution platform.
The replay operation does not change or retrospectively authenticate PRD-11's
retained results. Historical timing and training-to-reload error values are
bounded declarations; predictions, utility, membership scores and controls are
recomputed from the actual captured numeric candidate and sample.

The memory-only signing implementation handles only `worker_evidence` keys. The
existing access-token signer and its semantics are unchanged. A narrow registry
`signing_key_at` method checks exact sampled time while the caller owns the shared
operation lock. Both signing and verification recheck key eligibility after
cryptographic work. Revoked, expired, unavailable or stale trust fails closed.
Worker evidence requires an **active** key: access-token rotation's verify-only
overlap does not permit new evidence admission under a retired worker key.

## Independent bindings and exact replay

The caller freezes the context and a replay-job descriptor before issuing the
challenge. Its trusted current-context observer must resample current job and
attempt permission, source, policy, plan, code and runtime bindings. The observer
is an in-process control-plane capability; an uploaded report cannot supply it.
The command's job digest includes the complete input-artifact roster and current
package/script source hashes. The context also binds job and attempt IDs, fence,
agency, project, case, owner, source label, policy, plan and adapter hashes.

The verifier independently observes its current Python launcher bytes, Python
and numerical-library versions and platform, and compares that observation with
the pinned runtime digest. This is a limited local runtime observation. It does
not measure every loaded library, prove an OCI image digest or attest measured
boot. The broader source snapshot covers the enumerated repository code;
malicious interpreter, administrator and import-environment attacks require
separate production controls.

Exactly eight PRD-11 native artifacts are captured into an owned byte snapshot.
Unexpected entries, unsafe paths, links, hardlinks, read-time substitutions and
oversized files are refused. Each artifact is limited to 32 MiB, the candidate to
2 MiB and the complete bundle to 64 MiB. Replay uses these captured bytes for
candidate predictions, frozen-plan checks, scores, controls and receipt bindings.
It never reopens artifact paths while computing those results. Existing native
numerical helpers still inspect their own trusted local implementation/runtime.

Before committing, the verifier checks the original artifact roster again and
resamples current context, key trust and deadlines. Receipts bind content hashes;
they do not promise that mutable files will retain those bytes indefinitely.
Any later consumer must recheck the hashes. No model delivery is implemented.

## Durable replay prevention

`ReplayLedger` is a separate local SQLite fixture. Its challenge contains a
cryptographic nonce, ledger ID, frozen context digest, execution identity digest
and expiry. A unique execution identity permits only one challenge for a given
agency/project/case/job/attempt/fence, including after expiry or consumption.
Changing only the nonce or re-signing a result cannot renew that reservation.
A legitimate retry needs a newly authorized attempt in the controlling workflow.

Acceptance consumes the exact issued challenge and records the envelope hash in
one `BEGIN IMMEDIATE` transaction. Current guards run after acquiring the write
lock and again before commit. The transaction commits before a success is
returned. Concurrent callers cannot both consume a challenge. A crash after
commit burns the challenge even if the caller never received its receipt.
Invalid submissions return no admission and do not consume an otherwise valid
challenge; outstanding reservations still expire and cannot be reissued.

Explicit creation and opening with the expected ledger ID prevent silent reset.
Every operation validates the exact schema, bounded rows and persistent state,
ordinary directory/file identities, journal mode and database integrity. A
committed clock high-water mark rejects time rollback relative to prior commits.
The ledger retains all reservations and consumed tombstones, with a limit of
1,024 challenges and 16 MiB; capacity exhaustion fails closed. It is not protected
against rollback of the entire database by a privileged administrator.

This evidence ledger is **separate from PRD-10 job completion**. There is no claim
of an atomic transaction spanning the two stores, a native adapter worker lease,
or durable agency identity recovery. Production integration must supply one
coherent authority/attempt transaction and a current-permission observer.

## Required isolation stays fail closed

The API defaults to the `agency_private_cloud` requirement. It rejects that
profile because no qualified image/isolation verifier is implemented. Only an
explicit `local_public_replay` profile can return `accepted_local_replay`, and
all release, model-delivery and production-authorization flags remain false.

Local admission requires `image_sha256=null`. Image verification, hostile-code,
network and filesystem isolation, and resource-limit verification are all false.
A valid signature cannot upgrade those declarations. Unknown profiles, asserted
image digests and self-asserted true isolation fields are rejected. This exercises
the refusal path; it does not demonstrate deployed private-cloud isolation.

## Run and retained evidence

From the D: government checkout:

```powershell
& .\.venv-pipeline\Scripts\python.exe -B scripts/rehearse_execution_evidence.py --output .local/evidence-public-fixture-v1
& .\.venv-pipeline\Scripts\python.exe -B scripts/rehearse_execution_evidence.py --benchmark .local/verification/prd11-adapters-20261001/research-benchmark --output .local/evidence-eight-profiles-v1
& .\.venv-pipeline\Scripts\python.exe -B scripts/run_required_tests.py --profile government --output .local/required-prd12
```

Each output directory must be new and ignored under the government repository's
`.local/`. The default prepares a bundled Wine candidate then authenticates a
fresh replay. The existing-benchmark option reads the eight explicitly named
public profiles, preserving their original bytes. No datasets are downloaded or
written back. A source change, missing bundle or failed required check produces
a retained failure receipt and a nonzero exit. Private keys remain only in memory;
public signatures, public registration, fingerprints and consumed challenges
are retained. The public registration permits mathematical signature checks but
is not an independent trust anchor. Current ephemeral trust and identity are not
recovered after process exit; historical receipts cannot recreate admission.

Validation evidence is retained under `.local/verification/prd12-evidence-20261001/`.
The final `validation.json` records required tests, actual eight-profile replay,
locked-environment checks, repeat wheel builds, installed-wheel verification and
preservation of earlier evidence. Local results do not establish remote CI or
Linux execution. GitHub publication remains pending authentication.

## Observed local results

On 1 October 2026, **870 required government tests passed with zero skips,
failures or errors**. The 108 new tests comprise 29 contracts/signing, 36 durable
ledger, 20 captured-byte replay, 16 admission and seven command checks. Those
same 108 checks also passed in a fresh 31-wheel hash-locked Windows environment.
Another 35 runner/documentation checks passed; all 60 Markdown inventories had
valid checked local links. These test counts overlap where stated.

Fresh replay evidence passed for all eight retained PRD-11 profiles: ACS, BTS,
HMDA, TLC, breast cancer, Wine, Digits and Diabetes. Every profile completed all
13 mandatory live-admission, tamper, changed-binding, isolation-refusal, replay,
restart and independent revocation checks. Input bundles and repository source
remained unchanged. This reuses the already selected public samples; it adds no
new dataset families, full-corpus runs or privacy clearance.

Earlier milestone evidence is preserved: 246 recorded files are unchanged.
Of 110 prior package files, 109 are byte-identical; the trust registry only gains
the reviewed shared-time key check, with all its previous bytes preserved.
The 123 retired archive deletions and the Git index remain unchanged. An initial
validation run exposed a Windows test-cleanup connection leak; it was fixed and
the complete mandatory and locked suites were rerun successfully. Earlier failed
verification logs are retained alongside the final results.

## Production closure and next task

PRD-12 remains open for agency-managed signing custody, durable independent
current trust and identity, protected source/image admission, qualified platform
attestation, verified network/filesystem/resource isolation, and integration of
evidence consumption with the authoritative job and release transaction. Passing
this local fixture does not close earlier agency or scientific approval gates.

[PRD-13 model registration](production-prd13-model-registration.md) now adds
registration before new fitting for eight pinned public profiles. It binds
source/sample lineage, the native recipe, population and non-DP limitations,
a frozen utility comparison and local registration/disclosure history, then
uses this milestone's signed replay path. Arbitrary model import is refused;
external disclosure history remains unknown and no review clears a candidate.
PRD-13 remains in progress for agency and scientific qualification. This does
not retrospectively authenticate or restamp earlier PRD-11/12 evidence.

The next planned milestone is **PRD-14**: a scoped SACRO-ML adapter compared
with native controls and independent results, with unsupported cases and
licensing/maintenance acceptance explicit.
