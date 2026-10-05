# PRD-06: identity, case permissions and independent approvals

**Record:** PRD-06 / revision 0.1 / 1 October 2026.
**State:** `in_progress` — provider-neutral code and public-fixture verification;
agency SSO/MFA, live authority custody and deployed enforcement remain pending.
**Parent:** [production roadmap](production-private-cloud-plan.md).
**Dependencies:** [PRD-02](production-prd02-threat-model.md) and
[PRD-05](production-prd05-infrastructure-scaffold.md).

The target remains a major public-health agency holding large private datasets.
Provider, region, identity provider, agency roles and appointments are unselected.
No real agency identity, private data, model release or cloud deployment is used
by this implementation.

## Implemented boundary

The new [production_identity package](../src/model_release_assurance/production_identity/__init__.py)
contains a resource-server token verifier, a current-authority policy fixture and
an explicitly separate HTTP fixture. It does not add login or change existing
console, synthetic-lab, temporal-service or core administrative paths. Those
trusted-local interfaces retain their documented deployment boundaries.

| Component | Implemented behavior | Present limit |
| --- | --- | --- |
| [Token verifier](../src/model_release_assurance/production_identity/tokens.py) | Pinned issuer, single audience, public RSA keys, access-token type, exact claims, signature and bounded validity | One deliberately narrow JWT profile; no provider discovery, login, refresh or key enrollment |
| [Policy service](../src/model_release_assurance/production_identity/policy.py) | Current canonical identity, exact case grants, human/workload distinction, revocation, fresh MFA assertion and independent review | Trusted in-memory authority snapshot; no durable registry or distributed revocation source |
| [HTTP fixture](../src/model_release_assurance/production_identity/api.py) | Bearer-only endpoints with bounded input, no session/query-token transport and redacted failures | Explicit `public_fixture` factory; no production mode or existing-service protection |
| [Signed HTTP tests](../tests/test_production_identity_api.py) | Real signatures through the request boundary and full submit/assess/acknowledge sequence | Fictional identities and metadata; no real SSO/MFA ceremony or model assessment |

All successful fixture responses include `fixture_only: true`,
`authorization_eligible: false` and `model_delivery: false`. A usable pair of
review records shows that this identity/independence fixture accepted the bound
request. It does not establish scientific adequacy, privacy, authoritative release
eligibility, cumulative accounting or permission to deliver bytes.

## Access-token profile

The verifier uses [PyJWT](https://pyjwt.readthedocs.io/en/latest/api.html) with an
explicit fixed algorithm and pinned public keys. The runtime lock adds
[PyJWT 2.15.1](https://pypi.org/project/PyJWT/2.15.1/); existing dependencies remain
at their prior versions. Tokens never supply a key URL, trust configuration or
algorithm choice.

The access-token type and issuer/audience/signature boundaries follow the
[JWT access-token profile](https://www.rfc-editor.org/info/rfc9068/).
This implementation accepts a narrower local contract; it does not claim to
accept arbitrary tokens from an agency identity provider.

- Three bounded, canonical base64url segments; duplicate JSON keys, unknown
  headers/claims, noninteger numbers and malformed encodings are rejected.
- Fixed RS256 with pinned RSA public keys of 2048–8192 bits and an explicit key ID.
  Unsigned, symmetric-algorithm and caller-selected-key alternatives are refused.
- Header type `at+jwt` or `application/at+jwt`; an OIDC ID token is not API
  authorization. Issuer and single-string audience must match exactly.
- Required claims: `iss`, `sub`, `aud`, `iat`, `nbf`, `exp`, `jti`,
  `client_id`, `scope` and the profile-specific `case_ids`.
  Only `acr` and `auth_time` are optional.
- Integer time checks enforce a positive lifetime of at most 300 seconds, no
  future issuance/not-before use and expiry at the boundary, with zero leeway.
  Explicit checks use the same trusted supplied clock as policy evaluation.
- Signed action/case scopes are upper bounds. Roles, agency/project assignment,
  canonical person identity and human/workload kind come from current authority.

The 300-second token/MFA limits are restrictive fixture settings, not a signed
agency policy. The actual provider must issue this profile or use a separately
reviewed adapter/token exchange. Do not relax verification to accommodate an
unreviewed token layout. Unsupported algorithms, claim formats and providers
remain unsupported.

## Current authority and independence

Trusted Python bootstrap supplies immutable snapshots of registered principals,
case metadata and exact grants. The snapshot is copied defensively and includes
a strictly increasing revision, explicit availability and freshness deadline.
No HTTP route grants roles, registers cases, mints tokens, rotates keys or
replaces the authority snapshot.

A principal is located by issuer and subject, then mapped to a canonical person.
Aliases of one person share independence restrictions. Grants match person,
agency, project and case together; similarly named cases/projects are not
interchangeable. Unknown roles and duplicate grants are rejected.

| Fixture action | Required current role | Additional restriction |
| --- | --- | --- |
| `case:read` | Model owner, operator, assessor, policy authority, release authority, steward, auditor or platform | Human identity with current exact case grant |
| `proposal:submit` | Model owner | Registered canonical submitter only |
| `review:assess` | Assessor | Different person from submitter and every recorded test operator |
| `review:approve` | Release authority | Different person from submitter, operators and current assessor |
| `job:run` | Test operator or worker | Permission check only; records the operator for independence, executes no job |

Within this identity HTTP surface, workload identities can only pass the job
permission check. The separate [PRD-07 storage fixture](production-prd07-governed-storage.md)
adds a workload-only `object:read` action with an exact per-job read grant;
its additional human steward actions do not grant workloads review authority.
A workload cannot
become a human reviewer by presenting extra scopes or receiving an approval-role
label. Auditor/platform labels confer no routine review or delivery authority.
Every human action requires the configured signed MFA context and recent
`auth_time`; fixture issuer assertions demonstrate checking, not actual MFA.

A proposal binds case/agency/project, canonical submitter, artifact/evidence/policy
SHA256 values, recipient ID and monotonically increasing revision. Only the
authenticated actor is recorded. Request-supplied actor/role overrides are refused.
Assessment and acknowledgement bind the exact proposal digest and authority
revision. Duplicate reviews are rejected. Supplied policy/evidence digests are
bound metadata only: the fixture does not inspect their contents or establish
prior policy-authority approval. The policy-authority role currently grants
case reading only; protected policy changes and scientific review remain PRD-17
work.

A changed proposal clears its former reviews. Any authority revision invalidates
stored review usability, and reads recheck reviewer identity, current roles,
key/token status, expiry, MFA and independence. Revoked token IDs, retired keys
and subject issuance floors persist for the lifetime of the fixture instance;
revoke/re-enable cannot revive a prior credential or review. Current permissions
are recomputed for every request; an unrelated authority update alone does not
revoke all otherwise-valid access tokens.

Expired or invalidated reviews require the owner to submit the next proposal
revision and obtain fresh reviews. The fixture does not silently renew records
or overwrite a stale review as though it had remained valid. PRD-17 still needs
durable review history, delegation, policy-authority decisions and scientific
eligibility integration.

Verification, current-state lookups and mutations share one process lock. Time
is checked again after signature verification and at mutation, and backward
clock observations fail closed. The lock provides local serialization only;
it does not establish a distributed transaction, revocation service or
independently witnessed release admission. The optional
[PRD-08 dynamic trust verifier](production-prd08-key-trust.md) shares its registry
lock and clock with this service and rechecks key trust for stored reviews and
storage grants. Static pinned-verifier fixtures retain their existing behavior.

## HTTP surface and tests

The factory requires `create_fixture_app(service, environment="public_fixture")`.
Other environments are refused. It exports no ready-to-serve global app,
credential-minting endpoint, login UI, model/data upload or download endpoint.

| Method and path | Function |
| --- | --- |
| `GET /healthz` | Public, non-authorizing fixture health |
| `GET /v1/cases/{case_id}` | Authorized case/proposal/review snapshot |
| `POST /v1/cases/{case_id}/proposals` | Exact five-field proposal |
| `POST /v1/cases/{case_id}/assessment` | Independent assessment bound to `expected_digest` |
| `POST /v1/cases/{case_id}/approval` | Separate acknowledgement bound to `expected_digest` |
| `POST /v1/cases/{case_id}/job-check` | Current permission decision with an empty JSON body; no execution |

Exactly one Authorization bearer header is required for protected operations.
Cookie/browser-origin and query-parameter requests are refused. Bodies are
limited to 8 KiB and parsed with duplicate/nonfinite-field rejection. Responses
disable caching; token, key and claim details are not reflected in errors.
Invalid credentials return 401, denied permissions 403, stale/conflicting
mutations 409 and stale/unavailable authority 503. There is no default identity
or outage fallback.

From the government repository on D:, the signed public fixture is reproducible:

```powershell
& .\.venv-pipeline\Scripts\python.exe -B -m unittest discover -s tests -p "test_production_identity*.py" -v
& .\.venv-pipeline\Scripts\python.exe -B scripts/run_required_tests.py --profile government --output .local/ci-required-prd06
```

Use a new required-profile output directory. Tests generate private signing keys
in memory and never commit, persist or print them. The three new suites are
mandatory in the government profile; unavailable HTTP dependencies fail that
profile through its no-skip rule. General core-only discovery may still report
the existing supported optional-HTTP skip. The required runner also binds
`requirements.lock`; absence or mutation fails its evidence checks.

## Local validation result

Observed on 1 October 2026: **416 required tests passed with zero skips**,
including **58 new identity tests** (17 token, 28 policy and 13 signed HTTP
tests). **31 required-runner/documentation tests** passed. Two offline builds
produced identical wheels containing all 88 package files, including the four
new identity modules and the declared JWT dependency.

The final wheel was installed into a fresh verification target. With editable
source hooks disabled, its token verifier accepted a real signed fixture,
its HTTP factory returned non-authorizing health, and an unregistered principal
was denied. This smoke test reused the recorded dependency environment; it is
not a clean production-image qualification.

The initial 415-test result and earlier wheel snapshot remain retained. Final
review added a removed-account restoration regression and issuance-floor fix;
the final 416-test run and corrected wheel are separate artifacts. No earlier
receipt was relabelled. All 84 pre-existing package files and prior PRD-04/05
evidence remained unchanged; the cleared dated archive remains absent.

## Remaining production work and closure

The agency identity owner must approve issuer, clients, audience, canonical-person
mapping, role appointments/delegations, MFA context, session policy, credential
lifetimes, revocation latency and privileged-access controls. None is selected by
the fictional test identities or role labels.

Implement the selected agency login through a maintained OIDC integration.
Qualify authorization-code/PKCE, redirect binding, login/session protections,
logout/revocation and approved step-up MFA against
[OAuth security best current practice](https://www.rfc-editor.org/rfc/rfc9700.html).
The API must continue to distinguish access tokens from login ID tokens.
Workload enrollment needs approved service identities and job-specific grants;
a signed subject string does not attest a worker environment.

Replace fixture snapshots with protected, fresh authority state and durable
revocation history. Test concurrent multi-process changes, outages, restore,
clock uncertainty, stale readers and identity/key rotation. Managed key custody
belongs to PRD-08; leases/worker isolation to PRD-10; durable registry/witness and
atomic admission to PRD-15/16; full policy/review controls to PRD-17.

Apply authenticated authorization to every actual case, search, artifact, log,
ZIP, job and delivery path, including direct storage/service alternatives.
The existing local console and temporal APIs are not protected by this separate
fixture. PRD-18 must establish the sole recipient delivery route; deployers cannot
safely expose the old interfaces merely by placing an identity proxy in front.

PRD-06 remains `in_progress` until its dependencies, actual agency SSO/MFA and
workload integration, protected authority custody and deployed bypass/revocation
tests receive accountable acceptance. Local evidence is retained under
`.local/verification/prd06-identity-20261001/`; prior PRD-03/04/05 receipts remain
historical evidence of their exact revisions.

[PRD-07](production-prd07-governed-storage.md) now develops governed immutable
object references and scoped data access against these identity contracts.
Private-data admission remains closed until the agency and deployment gates
are satisfied.
