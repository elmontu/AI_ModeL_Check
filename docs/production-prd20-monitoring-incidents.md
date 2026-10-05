# PRD-20: redacted monitoring and incident operations

Status: **in progress for production**. This milestone implements and verifies
an additive trusted local public-fixture monitor. Provider and hosting region
remain open for the agency private cloud. It is sector-neutral; a major
public-health agency is one possible deployment, not the only data profile.

## Implemented local boundary

The monitor accepts four exact codes: worker_unavailable, key_unavailable,
data_unavailable and ledger_inconsistent. Every observation contains only its
fixed schema, generated opaque resource/event IDs, integer observation time,
fault/healthy condition and non-authorizing flags. It accepts no text messages,
tokens, identity claims, names, paths, URLs, dataset/model bytes, subprocess
output, exception strings or hashes of those sensitive values. Invalid inputs
produce generic errors. Opaque references are generated for this fixture; they
must not be repurposed as encodings of citizen identifiers.

Collection is a trusted internal API, with no arbitrary public ingestion
endpoint. It remains usable during an identity/key outage. Human reads, local
routing and incident actions require a current signed human auditor credential,
fresh MFA and exact case-a authorization in the fixed agency/project fixture.
Stored actor records contain only human kind and current authority revision.
The trusted bootstrap binds the entire fixture monitor to this one case.

Events, incident state and pending alerts commit together in a bounded SQLite
hash-chain log. Exact event retries retain their original result; changed
payloads under the same ID conflict. Each distinct fault produces one retained
alert, even while an incident is already active. A healthy observation does not
auto-close an incident. Current authorized acknowledgment is followed by
resolution only after the latest matching resource/code observation is healthy.
A recurrent fault after resolution creates a new incident.

The store requires exact current compare-and-swap pins for writes. Reopening
requires a separately retained explicit pin and full replay. Local checkpoint
files are monotonic floors in a separate directory. The service promotes the
committed pin before calling the checkpoint sink; failed checkpoint persistence
leaves the committed history and held pin intact and returns uncertainty.
Flush/reconciliation cannot reset the event log.

A separate local receiver durably deduplicates the full redacted alert envelope.
A receiver custody acknowledgment is different from incident acknowledgment.
It proves a checked local retained copy, not a network send, a human response,
or recipient receipt. Delivery uncertainty cannot be interpreted as no effect.
No email, Slack, agency SIEM, webhook or other external notification is sent.

These are trusted local Python/filesystem controls. A privileged administrator
who replaces all copies and all separately held pins is outside their guarantee.
Existing APIs are unchanged: monitoring covers this facade and its injected
exercises, not every direct historical service call or a mandatory machine-wide
release/audit gateway. Incident resolution never resumes model delivery,
unrevokes credentials, refunds charges, rehydrates live permissions or clears
a model.

## Run the offline public fixture

Use the government checkout on D:, not the original OneDrive or academic
repositories. The existing runtime is sufficient; no package/network downloads
are part of the rehearsal. Select a fresh ignored output directory.

~~~powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONPATH = Join-Path (Get-Location).Path 'src'
$env:TEMP = Join-Path (Get-Location).Path '.local/verification/rehearsal-temp'
$env:TMP = $env:TEMP
& .\.venv-pipeline\Scripts\python.exe -B scripts/rehearse_monitoring.py --profile local_public_fixture --output .local/verification/prd20-monitoring-example
~~~

The default agency_private_cloud profile refuses execution before creating
output. Existing output is never overwritten. The result records the fixed
checks, generic failure codes, runtime and exact source bindings. Fixture files
are newly generated public data and retained locally; they must not be uploaded
as agency evidence. Tests use the same scope and assert redaction and current
authority denial.

## Alert policy and incident runbooks

Routing policy is fixed in code and hash-bound to the source/build receipts.
It cannot be supplied by event callers.

| Code / runbook | Local route / severity | Immediate containment | Recovery and closure evidence |
| --- | --- | --- | --- |
| worker_unavailable / RB-WORKER | sre / high | Stop admitting new work to the affected worker; establish owned-process termination; retain job/attempt and consumed-grant records. | Restore approved worker/image health, create a fresh attempt/grant where required, and verify a successful bounded run. Never reuse a spent grant or guess that timeout had no effects. |
| key_unavailable / RB-KEY | security / critical | Deny new signed/current-authority operations while trust is unavailable; retain existing audit records. | Key custodian restores current approved trust/custody, verifies new current credentials and requires fresh contexts where trust revision changed. Never undo revocation or extend token/evidence lifetimes. |
| data_unavailable / RB-DATA | security / critical | Deny integrity-mismatched reads/training/delivery; quarantine the object/reference and retain the incident. | Data steward proves exact approved bytes/version and immutable reference or performs a new approved intake. A local in-place public-byte repair is only a drill; it does not restore already consumed input rights. |
| ledger_inconsistent / RB-LEDGER | security / critical | Stop affected commits/releases; preserve registry, witness, irreversible intents and separately held floors. Treat a postcommit interruption as uncertain. | Reconcile exact request/receipt/full history against retained floors and recover the original committed result. Prove no duplicate/lost charge or outbox effect. Never create a new ledger to reset history. |

For each incident the responder verifies scope and severity, acknowledges the
retained incident, performs the relevant runbook, checks a current matching
healthy observation and resolves the local record. The monitor's healthy flag
is a trusted collector observation, not an authenticated agency attestation.
Actual owner appointments, escalation deadlines and review evidence must be
provided by the agency. SRE handles worker recovery; security, the key
custodian, data steward and ledger owner handle their respective controls.

A monitor/store/checkpoint/receiver outage is itself a custody gap. Callers must
treat generic monitor exceptions as unconfirmed capture, retain the last known
pin and stop any future integration that requires complete audit capture.
The CLI reports failure. This fixture does not invent successful events or send
an alert through the same unavailable store. A separate approved external
watchdog is required for production detection of collector silence.

## Production acceptance still required

| Control | Required agency evidence | Current limit |
| --- | --- | --- |
| Complete capture | Mandatory transaction boundary or durable intent/outbox for each job, trust, data, review and release path; injected crashes/lost acknowledgments reconcile all acknowledged effects. | Additive fixture facade; existing direct paths remain callable. |
| Telemetry privacy | Approved field/cardinality policy, measured negative leakage tests including traces/logs/labels, and private-data classification/retention decisions. | Fixed metadata-only public fixture; no private-data intake. |
| Independent custody | Separate administrative account/domain, authenticated remote append-only receipt, retained external floors, dual-control restore and tamper tests. | Separate directories on one trusted Windows host; unsigned local pins. |
| Alert delivery | Agency-selected SIEM/receiver, authenticated encrypted transport, durable retries/deduplication, dead-letter handling and separately observed delivery status. | Durable local receiver; no external sends. |
| Human response | Named on-call roster, tested escalation deadlines, incident/ticket integrations, recovery and closure approval, recurring drill records. | Role-guarded local acknowledgment and resolution; no staffing or SLA qualification. |
| Operational hardening | Provider-specific dashboards, collector-silence watchdog, bounded cardinality/retention, backup/restore, capacity targets and clock/time-source acceptance. | Bounded local SQLite and synthetic fixture clock; no distributed/cloud qualification. |
| Release safety | Agency-approved mandatory gateway checks; monitor/custody faults cannot bypass the current release guards or reinterpret unknown disclosure. | Earlier delivery/registration/accounting guards preserved; monitor cannot grant release permission. |

Deploy only after scope, classification, provider/region, owner/custodian,
network and scientific/security acceptance decisions in the
[private-cloud plan](production-private-cloud-plan.md) are supplied. Monitoring
does not establish differential privacy, attack completeness or scientific
adequacy. GitHub publication and protected remote CI remain pending authentication.

## Verification and preservation

The PRD-20 local verification receipt is stored under the fresh ignored
.local/verification/prd20-monitoring-20261005 directory. It records actual counts,
no-skip required tests, fault rehearsal, offline runtime tests, repeat-wheel
hashes, installed-wheel ownership and exact preservation of prior source/evidence.
Results apply only to the recorded local runtime; they are not Linux, cloud,
SIEM or production qualification.

All earlier implementation and advisory/evidence files are preserved. The
user-retired 28 September archive stays deleted; its Git history is untouched.
No other repository is edited and no Git commit, stage, push or publication is
performed. The next planned step is PRD-21, approved-scale and recovery exercises.
