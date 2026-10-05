# PRD-22 — local assessment evidence and independent review handoff

Status: **in progress**. The bounded local implementation is ready for review;
an appointed assessor has not tested an agency deployment or accepted its
scientific evidence. Provider and region remain open. The government repository,
new outputs and offline runtimes remain on D:. GitHub authentication is pending.

## Implemented local scope

The fixed plan is written before fitting one fresh public Wine128 model through
the PRD-18 native registration, authenticated evidence, independent policy
review and controlled fixture gateway. It accepts no arbitrary model, attack
selector, dataset, JWT claims or caller assertion of successful execution.
This run does not repeat the PRD-19 SACRO comparison or private research corpus.

Eleven probe families exercise policy before fitting; canonical reviewer
independence; forged, expired and wrong-case recipients; changed retained
evidence and candidate bytes; missing direct object routes; revoked grants;
partial and unknown writer extent; externally pinned rollback; lost proof
contexts after component restart; and valid current positive controls.

Expected rejections use enumerated exception classes or the observed HTTP404.
Unrelated exceptions fail the exercise. Refusals before admission must leave
the delivery head and admissions unchanged with zero writer calls. Four
positive controls observe exact current128-byte writes. Two uncertain writer
admissions retain256 attempted bytes, including one known byte and one unknown
extent; the framework neither refunds those attempts nor claims recipient
receipt. The synthetic clock moves monotonically1000→1001 for expiry testing.
Original evidence, activation and grant deadlines are retained.

These are narrow local engineering probes. They do not establish deployed
network isolation, absence of every alternate route, hostile-worker containment
or complete mandatory telemetry on earlier entry points.

## Historical assessment packet

New production_assessment/packet.py seals the fixed plan, observations, finding
catalog and bounded raw fixture inventory with a generated Ed25519 key. The
packet includes the public candidate model and supporting public artifacts.
Its model_delivery:false flag denotes absence of new release authority from
assessment verification; it does not mean the handoff contains no model bytes.

Limits are256files,16MiB per file and32MiB total, with512KiB metadata. Files
must be ordinary, singly linked and beneath ordinary directories. Verification
requires exact externally retained manifest and public-key hashes. Embedded
keys and hashes cannot establish their own trust. Exact inventory, byte hashes,
signature, canonical schemas, fixed plan/catalog, all package Python bytes and
the observed selected runtime versions are checked. Same-byte replacement
during a replay is refused through retained physical identities.

Verification establishes historical local integrity. It does not reconstruct
probe execution, independently replay every nested SQLite history, authenticate
an agency-appointed signer or recover current authorization. The key is
generated locally and its private half is never persisted. Same-host pins do
not establish independent physical custody. Future source/runtime changes need
the matching historical implementation; old packets are never restamped.

## Current local finding review

LocalFindingReview authenticates raw signed human credentials through the
existing current-authority bridge. Both records bind one exact packet digest,
catalog digest and agency/project/case. The bootstrap records its local producer
through legitimate signed start authorization. Owner aliases and operators
cannot assess; assessor and approver must be distinct canonical people.
Exact current roles, scopes, MFA, key and authority revisions are checked again
at one final timestamp before saving a decision.

The service keeps two immutable records and trusted contexts in memory.
Serialized records are historical; a new instance cannot restore approvals.
After retained participant expiry or revocation, readable history is unusable.
Local review does not itself authenticate the packet or reconstruct attacks;
the handoff rehearsal verifies the packet before using its exact digest.

The fixed catalog has **11 permanently open production blockers**:

| Finding | Required independent agency evidence |
| --- | --- |
| deployment_pentest | Appointed assessor's deployed penetration test, scoped targets and retests |
| network_isolation | Verified workload/image, metadata, filesystem, secrets and network boundaries |
| real_idp_kms | Agency SSO/MFA, workload enrollment, key custody, rotation and revocation acceptance |
| independent_custody | Separately administered evidence, witnesses and restore floors |
| private_cohort | Approved private intake, lineage, protected population and representative audit cohorts |
| scientific_acceptance | Prospective agency criteria, suitable attacks/controls and independent scientific review |
| dp_accountant | Justified mechanism, protected unit, cumulative composition and actual privacy accountant |
| agency_scale | Approved peak load, service objectives, failover, cost and recovery evidence |
| appointed_owners | Named sponsor, service owner, data steward and independent assessment owners |
| agency_acceptance | Explicit evidenced scope, permitted residual risks and acceptance authority |
| publication | Authenticated source publication and external review evidence |

Local automation cannot close or accept these blockers. Two local residuals,
small-sample measurements and trusted in-process fixture components, permit only
their fixed local justifications. Accepting either cannot permit deployment.
The current rehearsal acknowledges both while leaving every blocker open.

## Scientific review still needed

The eight pinned public research profiles broaden engineering coverage. They
do not qualify an agency's large confidential population, dependent records,
temporal changes, protected units or recipient behavior. The existing SACRO
recipe's9900 symmetric-AUC fixture criterion and dependent repetitions are
descriptive controls; passing or replaying them supplies no DP/privacy ceiling
or attack-completeness guarantee. Wider modalities and garak/PyRIT/ART adapters
remain separately scoped expansion tasks.

The appointed scientific reviewer must approve prospective population and
cohort definitions, utility and leakage criteria, attack interfaces and query
budgets, positive/null controls, dependence handling, uncertainty reporting and
mechanism/composition assumptions. Failed or missing coverage remains an open
finding. Model fitness or a favorable attack score cannot supply acceptance.

## Run and assess

From this D-drive government repository with the recorded core runtime:

~~~powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONPATH=Join-Path (Get-Location).Path 'src'
$env:TEMP=Join-Path (Get-Location).Path '.local/verification/rehearsal-temp'
$env:TMP=$env:TEMP
& .\.venv-pipeline\Scripts\python.exe -B scripts/rehearse_independent_assessment.py --profile local_public_fixture --output .local/verification/prd22-assessment-new
~~~

Choose a new ignored.local output each time; existing outputs are never
overwritten. The default agency_private_cloud profile refuses before output
creation. The CLI captures source before and after execution and requires every
fixed check. Failure reports retain generic stage codes, completed earlier stages and
generated fixture files. An interrupted probe stage does not emit a partial
structured probe roster. Raw tokens, exception messages and private paths are
not logged.

For a separately pinned handoff:

~~~python
from model_release_assurance.production_assessment.packet import verify_packet
verified = verify_packet(
    packet_directory,
    expected_manifest_sha256=separately_retained_manifest_sha256,
    expected_key_sha256=separately_retained_key_sha256,
)
~~~

The local validation receipt is
D:/ChatGPT/model_audit/AI_ModeL_Check_Government/.local/verification/prd22-assessment-20261005/validation.json.
It records relevant focused tests, the no-skip required profile, source CLI,
fresh offline runtime, repeat wheels, installed-wheel exercise and exact
preservation checks. It supplies engineering evidence, not agency acceptance.

## Completion and next dependency

PRD-22 completes only when appointed independent assessors test the actual
protected deployment, review scientific evidence and close findings through
verified retests, with permitted residual risks explicitly accepted by the
proper agency authority. This local catalog intentionally has no such
production acceptance path.

Next is **PRD-23**, the restricted pilot plan: named users, models and interfaces,
go/no-go evidence, support and suspension authority. Actual pilot admission
depends on independent PRD-22 acceptance and unresolved production controls.
No real private data or agency release is authorized by this continuation.
