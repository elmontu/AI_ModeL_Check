# PRD-17: local policy approval and independent review

Status: **in progress for agency production qualification**. The bounded local
implementation binds current signed policy authority to prospective public-data
training, then retains independent assessment and release-review acknowledgments.
All records remain fixture-only, non-authorizing and scientifically unqualified.
The system is sector-neutral; the rehearsal uses public Wine data. Agency private
cloud is the deployment target; provider and region remain open.

## Implemented ordering and bindings

A current model owner proposes one immutable campaign with exact agency/project/
case, recipient, public profile, selected data, source metadata, plan, code,
adapter and runtime digests. It freezes integer engineering utility-improvement
and symmetric membership-AUC thresholds and the three required native controls.
A distinct policy authority approves this exact policy **before execution**.
The candidate does not yet exist: approval covers its fixed derivation plan,
not an invented prefit candidate digest.

The human test operator starts the approved campaign. An additive driver checks
current approval at the existing PRD-13 workflow's custody boundaries before
registration/start and fitting. PRD-13 performs a fresh registered native fit,
then PRD-12 verifies its signed replay and consumes its one-use challenge.
PRD-17 binds the actual returned run identity to the retained registration,
terminal registration record, native artifacts, signed envelope, replay admission
and context. It independently replays the candidate and checks those bytes again
at review boundaries. There is no public caller-authored completion/admission API.

A separate assessor acknowledges or rejects the exact policy/result/recipient
binding. A separate release reviewer may acknowledge only its current accepted
assessment. Owner, every recorded operator, policy approver, assessor and release
reviewer are separate canonical people. Aliases cannot restore independence.
An acknowledgment never authorizes delivery or converts an attack result into a
privacy guarantee. Native known-leak/null controls remain label-aware engineering
oracles; original training attestation, representative privacy evaluation,
qualified agency criteria and accepted accounting remain pending.

## Current authority and delegation

Policy approval requires both a current server-side `policy_authority` role and
a dedicated signed `review:policy` scope, in addition to the exact case scope.
Other actions retain their distinct current roles/scopes. Only human identities
with current MFA may approve or operate this workflow. Revoked tokens/keys,
disabled principals, changed authority revisions, stale trust, expired tokens or
MFA and unavailable/backward clocks deny usable decisions. Final guards check
all retained participants at one current timestamp after evidence/database work.

Delegation narrows an existing role; it never grants a new role. A current actor
with `review:delegate` may create a non-recursive, at-most-300-second delegation
for one action, campaign, exact policy and delegate canonical person. The policy
also fixes case, recipient and all source/plan/runtime bindings. Both grantor and
delegate remain current. Durable revocation and expiry invalidate downstream use.
Only the original grantor may revoke its delegation in this fixture.

## Retained history and changes

A bounded ordinary-file SQLite log replays every event and transition under a
write transaction. Exact store identity and case enrollment are explicit; no
missing store is silently replaced. Service mutations compare the current event
head with the exact state whose proof was checked. Final current-time guards
execute after replay/lock waits and before commit. Failed/started campaigns are
retained; a timeout or exception does not reset an execution.

Approved policy payloads cannot change. Once any campaign starts, the enrolled
agency/project retains a monotonic utility floor and membership-risk ceiling
across cases: later campaigns cannot weaken those criteria. Required controls
cannot be dropped. Every new campaign still requires fresh registered execution.
Permanent store-wide registration/envelope/admission tombstones reject reuse of
already attached evidence under a new campaign, policy or recipient. Identical
candidate bytes from deterministic fresh fits are not proof of reused evidence;
the fresh registration and one-use authenticated replay identities decide that.

Exact fresh acknowledgments append review history and make dependent decisions
stale. They remain subject to the original execution/operator/policy contexts,
retained evidence and their lifetimes; renewal cannot revive expired original
execution authority. Reopening a service makes saved completed campaigns
historical and unusable. There is no evidence rehydration API: current usable
review then requires a new approved campaign, fresh registered fit and fresh
signed replay. This implementation does not reconstruct identity authority from
unsigned database metadata or persist bearer tokens/private keys.

## Rehearsal and verification

From the government repository on D:, run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
& .venv-pipeline/Scripts/python.exe -B scripts/rehearse_policy_review.py --output .local/policy-review-v1
& .venv-pipeline/Scripts/python.exe -B scripts/run_required_tests.py --output .local/required-policy-review-v1
```

Outputs must be fresh ignored directories under this repository. The rehearsal
uses an ephemeral signed fixture authority and one actual public Wine fit/replay;
it retains original evidence and adversarial denials, including prefit approval,
independence, material changes, stale evidence, delegation and revocation.
Focused contract/store/authorization/service/CLI tests are in the required CI
profile. Exact final counts and source/evidence hashes are retained in
`.local/verification/prd17-review-20261002/validation.json`.

## Production acceptance still required

This is trusted local Python orchestration and SQLite, not a hostile-worker
isolation boundary or durable agency IdP/KMS approval service. Privileged direct
store callers/filesystem edits are outside this trusted API's authority model.
The review store is not yet enrolled in an independent signed witness; hashes
alone do not prevent privileged coherent rollback of its whole history.
PRD-15's fictional registry charges and PRD-16's local witness are preserved but
are not claimed to atomically authorize these ordinary non-DP trained models.
No PostgreSQL/cloud failover, private-data intake, Linux execution, remote policy
signature, agency appointment/conflict exception or scientific clearance is
qualified by this milestone.

The next task is **PRD-18**, the sole controlled-delivery route, current grants,
admission receipts and suspension/revocation. GitHub publication remains pending
authentication; no staging, commit, tag, push or publication is performed.
