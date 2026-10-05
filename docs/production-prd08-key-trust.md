# PRD-08: access-token key custody and current trust

**Record:** PRD-08 / revision 0.1 / 1 October 2026.
**State:** `in_progress`; provider-interface contracts and local public-fixture
validation, pending agency key-service selection and deployment acceptance.
**Inputs:** [production roadmap](production-private-cloud-plan.md),
[threat model](production-prd02-threat-model.md),
[identity](production-prd06-identity-and-approvals.md) and
[governed storage](production-prd07-governed-storage.md).
Work stays in the D: government repository.
Provider and region remain open.

## Implemented boundary

The [trust package](../src/model_release_assurance/production_trust/) extends
the existing strict RS256 access-token profile. A memory-only fixture provider
exercises a public-key-description/signing interface; a current trust registry
controls enrollment, rotation overlap, revocation and freshness. The dynamic
verifier reuses the existing JWT verifier and integrates current trust into
saved identity reviews and outstanding storage grants.

The only implemented signing purpose is access tokens for fictional tests.
Registry purpose labels also reserve worker evidence, policy, registry and
gateway domains, but do not implement those signature protocols. Existing
file-based Ed25519 evidence/assurance functions remain unchanged. A token
signature is not scientific evidence, worker attestation or release authority.

There is no HTTP token minting, login, key export, key-file import, discovery,
administrator or key-management endpoint. The trusted Python bootstrap and
provider capability are not an authenticated agency administration workflow.
The profile accepts only the `public_fixture` environment. No private agency
data, production key or cloud resource is created.

## Registry and lifecycle contract

A key registration pins the key ID, normalized RSA public key and SHA256 SPKI
fingerprint, owner, agency, environment, exact issuer/audience/purpose, and key
validity interval. Only public RSA keys of 2048Ã¢â‚¬â€œ8192 bits are accepted; this is
the existing fixture algorithm profile, not an approved agency algorithm policy.
Private-key material and unsupported key types are refused.

The registry retains at most 32 registrations, including retired and revoked
keys. Neither a key ID nor its public-key fingerprint may be enrolled again,
including under another purpose, owner or agency. Returned registrations and
public-key maps are immutable. Multiple active keys allow staged enrollment;
callers must select the exact key to sign.

| Operation | Local behavior |
| --- | --- |
| Enroll | Validate a currently valid new registration and exact expected revision |
| Rotate | Atomically enroll a same-profile/same-owner replacement and make the old key verification-only |
| Revoke | Permanently deny the retained key; no reactivation or deletion |
| Refresh | Set a new bounded freshness deadline with an exact current revision |
| Availability | Explicitly stop/resume normal trust decisions without clearing history |

Lifecycle mutations require the current revision and increment it. A stale
revision, reused key, invalid replacement or capacity violation fails without
partial rotation. Recovery refresh, availability changes and emergency
revocation remain possible while trust is stale or unavailable; each still
requires the valid clock and current revision. These are trusted fixture hooks,
not authority to recover an actual agency key service.

Rotation allows an explicit 1Ã¢â‚¬â€œ300-second verification overlap. The fixture token issuer
immediately refuses new signing with the old key. Only tokens whose signed issuance claim precedes the rotation timestamp
can use the overlap; same-second old-key tokens are conservatively denied.
That claim is not an independently witnessed issuance time. Suspected key
compromise requires revocation; rotation overlap does not establish when a
holder of the old private key actually created a signature.
Verification ends at the overlap deadline or the key's expiry, whichever comes
first. Token expiry must fit within the key validity interval. Retired keys
cannot become active again, and revoked keys cannot be restored through refresh.

Normal trust decisions require availability and a freshness deadline no more
than 300 seconds ahead when configured. Expired or missing trust has no cached
fallback. Boolean/noninteger time, clock rollback and observations from the
registry clock's future fail closed. Revocation records and freshness are
process-local; restarting with a new registry is not approved recovery.

## Signer/provider interface

`SigningProvider` supplies a public `describe(handle)` operation and
`sign(handle, signing_input)`. `MemoryFixtureSigningProvider` generates
RSA2048 keys only in memory and caps creation at 32 keys. A bound fixture
capability pins owner and profile. The fixture's unique key ID is its immutable
handle; the SPKI fingerprint identifies the version. A real adapter must bind
the provider's actual immutable key version, permissions and algorithm policy.

`FixtureTokenIssuer` checks exact issuer/audience, required and optional claim
fields, primitive types, bounded scopes/cases, clock, key interval and a maximum
300-second token lifetime before invoking the private signing operation.
It compares provider metadata against the registered public key, owner,
purpose and version. It verifies the returned JWT through
`AccessTokenVerifier`, then rechecks current key/trust/token eligibility
before returning. Malformed claims, wrong signatures, changed provider
descriptions, disabled keys, stale trust and outages fail without a fallback.

Private keys are never written by this fixture, but remain accessible to its
Python process. A sign-only interface is not proof of non-exportability or HSM
custody. Provider bootstrap and capability binding are trusted local setup, not
IAM or proof of possession by a deployed identity provider. No real provider,
secret, certificate chain or agency login is configured.

A signing-provider outage prevents new token issuance. Verification of an
already-issued token uses fresh trusted public metadata and does not require a
private signing call. A trust-registry outage denies verification and guarded
identity/storage operations. This distinction is not a production release
outage policy; subsequent release gates still need their own current checks.

## Identity and storage integration

`RegistryAccessTokenVerifier` constructs the existing strict verifier from
current matching public keys and checks trust again after cryptography.
The identity service requires the dynamic verifier's complete lock, clock and
current-trust contract. Registered cases must belong to its exact agency.
Static pinned-verifier fixtures retain their earlier behavior.

The registry and identity service share one reentrant operation lock, which
covers identity mutations and PRD-07 storage decisions. Dynamic identity uses
the registry clock even if an old bootstrap clock argument is supplied.
A decision samples that clock once, then checks every actor's key trust,
credential, MFA, authority and grant deadline at that same timestamp. The
trusted `check_current_at` helper requires lock ownership and the exact last
sample; it neither accepts an HTTP identity proof nor independently resamples
time inside a grant decision. CPython reentrant-lock ownership introspection
is required and absence fails closed.

Both current key trust and `AuthorityState.active_key_ids` must permit a
credential. Enrolling a key does not grant a person, client, role, case or
approval. Saved assessments/approvals recheck their signer's current trust.
Outstanding read grants recheck both worker and grantor trust before content
I/O and after the bounded read. Revocation and byte-read decisions serialize:
a read already authorized under the lock may finish before a later revocation;
subsequent reads fail. Revocation does not recall bytes already returned.

The shared timestamp also preserves PRD-07's grant-expiry boundary when key
checks are added. This is one-process serialization, not a distributed lock,
revocation propagation guarantee, independent witness or durable admission
transaction. The unchanged legacy console, temporal and evidence-signing paths
are not made production-safe by constructing this separate dynamic verifier.

## Local verification result

Observed on 1 October 2026: **529 required tests passed with zero failures
and zero skips**, including 57 new trust tests (19 registry, 21 signer,
17 real-signed identity/storage integration). **31 required-runner and
documentation tests** also passed.

Review corrected shared-clock decision timing, expiry after provider signing,
agency binding at identity bootstrap and acceptance of extra PEM material.
Regression tests cover those cases together with rotation overlap, permanent
revocation, stale trust, outages, saved-review invalidation and concurrent
revocation/read ordering. The original 84 package files remain unchanged.
Among the 93 files in the preceding package, only the intended identity-policy
bridge changed. PRD-04/05/06/07 evidence and all 123 archive deletions remain
preserved.

## Verification and production closure

From the D: government checkout:

```powershell
& .\.venv-pipeline\Scripts\python.exe -B -m unittest discover -s tests -p "test_production_trust*.py" -v
& .\.venv-pipeline\Scripts\python.exe -B scripts/run_required_tests.py --profile government --output .local/ci-required-prd08
```

Choose a fresh output directory. The three new trust suites are mandatory in
the government profile; a missing module, failure or skip fails that gate.
Tests generate ephemeral keys and fictional credentials without writing or
printing private keys or tokens. Verification evidence is retained in
`.local/verification/prd08-key-trust-20261001/`; prior receipts remain
historical records of their exact source revisions.

PRD-08 remains in progress until the agency approves key custodians,
algorithms, issuer/audience, key-service provider/region, lifecycle policy,
credential lifetimes and outage/recovery behavior. Implement and qualify the
real KMS/HSM adapter, protected enrollment, authenticated and independently
controlled administration, durable revision/revocation custody, protected clock,
audit history and restart/restore behavior. Exercise key compromise and
multi-process stale-cache/rotation/revocation scenarios against deployed paths.

Worker, policy, registry, witness and gateway signing purposes need separate
keys and scoped service identities with their own protocols. Encryption-key
custody, envelope encryption and rotation of protected data also remain open;
this access-token fixture does not implement them. PRD-12/16/18 must integrate
authentic evidence, independent recovery and sole delivery enforcement.

The next local milestone is recorded in [PRD-09](production-prd09-build-controls.md):
locked dependency artifacts, SBOM, advisory/license evidence and local signed
provenance. Its production closure remains pending. GitHub publication
and hosted CI remain pending authentication.
