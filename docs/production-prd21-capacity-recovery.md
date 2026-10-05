# PRD-21: capacity measurements and historical recovery

Status: **in progress for production**. This milestone adds bounded local
workload measurements and recovery drills. Agency private cloud remains the
target; provider, region, approved peak load and private-data workload are still
open. The local outcome is correctness evidence on public fixtures, not an
agency capacity, availability, recovery or go-live commitment.

## Frozen local workloads

The implementation is sector-neutral. It uses public data and engineering
fixtures, with no arbitrary dataset root, model, private object or caller-supplied
worker code. A fixed workload plan is source-bound and hashed before execution.

| Workload | Local matrix | What the measurement means |
| --- | --- | --- |
| Streaming public I/O | Tiled bundled Wine numeric bytes at targets 1/8/32 MiB, read in 64 KiB chunks | Exact public-byte integrity, actual bytes processed and elapsed write/fsync/scan time. Repetition does not create new people or a representative agency cohort. |
| Fixture jobs | Four fixed public-count jobs at each concurrency 1/2/4 | Actual authenticated admission, one-use input, real fixed child workers and durable completion. Maximum concurrent runner calls is distinct from live OS child count. |
| Delivery restart | One fresh Wine128 native training/review fixture; exact and partial writes | Historical admission/grant/counter retention and denial when old live execution/review/activation/grant contexts are absent. |
| Witnessed backup/restore | Three fictional registry commits, including recovered postcommit uncertainty; retained outbox acknowledgments | Exact receipt/head/history and engineering-charge conservation in a complete historical cut. No real privacy accountant or production failover is qualified. |

Timing uses monotonic perf_counter_ns and explicit integer units. Latency summaries
use declared nearest-rank percentiles and show sample count; a four-job sample is
not a population p95 estimate. Cache state is uncontrolled, so results do not
establish cold-cache storage performance. Parent-process high-water memory is
identified by method and scope; it excludes aggregate child-worker memory and
cannot stand in for cloud process/container resource monitoring.

Functional gates require every requested outcome to be accounted for, exact
data/digests, original worker/source bindings, confirmed child cleanup and
preserved durable history. Performance target status stays not_agency_qualified,
even when a local measurement happens to be faster than an initial roadmap
target. Missing measurements or failed jobs remain failures/unavailable outcomes;
they are not reported as zero duration, successful jobs or qualified throughput.

The fixed job service keeps its existing 5-second timeout, 30-second lease and
bounded grants. Tokens and current trust use the existing approved fixture
lifetimes; no deadline is lengthened to make the benchmark pass. Native delivery
restart probes use explicitly labeled synthetic authority time, with original
30/20-second activation/grant and 120-second evidence windows unchanged.

## Complete historical backup

The capture API requires explicit local_public_fixture selection, exact trusted
registry/witness components, an externally retained registry anchor, witness pin
and current guard. Default production selection fails before creating output.
It takes a quiesced cut under both stores' write reservations, using SQLite's
supported serialization and pure replay validation. It does not copy unlocked
live database files and assume they form a consistent snapshot.

A registry anchor binds store/namespace identity, schema, full event sequence/head
and broker epoch/identity. The witness must agree with the **entire** registry
history, including outbox claims/acknowledgments and broker events. A valid prefix
is insufficient. Pending unresolved intents refuse a reconciled capture; the
original intent and any committed charge remain retained for exact recovery.

The manifest binds the exact registry and witness bytes, external anchor/pin,
fixed schema and implementation digest. Verification requires caller-supplied
expected manifest SHA256, registry anchor and witness pin. Expectations included
inside a bundle do not become trusted simply because the bundle is self-consistent.
The three-file inventory, strict schemas, ordinary-file identities and bounded
aggregate input are checked before accepting a backup.

Historical restore writes exclusively into a fresh ordinary directory, flushes,
reads back and replays the exact bytes. Existing output, partial/mixed/stale/forked
cuts, unexpected artifacts, links, substitutions and changed validation code deny. Failures retain diagnostic new output; they never replace a prior live
store, refund a charge or invent an aborted outcome.

Restore verification does not construct a live registry service: that constructor
would activate a broker and change history. It does not recover identity, key
custody, storage catalogs, current policy/review evidence or release authority.
Its returned current_authorization_recovered and authorization_eligible flags
stay false. Local hashes/pins and directories remain trusted same-host evidence;
independently administered encrypted backups, authenticated remote custody and
privileged full-copy rollback resistance need deployment acceptance.

## Delivery-context recovery drills

The rehearsal first proves current original review/evidence, readable metadata
and still-valid original activation/grant deadlines, then runs two distinct probes:

1. A fresh gateway over copied exact durable delivery history and the original
   live review bridge lacks old gateway activation/grant proof contexts. Old
   grants, admission/resume and transfer attempts deny without calling the writer.
   Fresh activation based on genuinely current original review is a separate
   operation; gateway restart alone is not a blanket prohibition on it.
2. A fresh review service and review bridge over retained review history lack the
   original execution/evidence contexts. Historical reviews remain readable but
   unusable as current authority; new activation also denies.

No private in-memory proof maps are copied into either probe. The rehearsal
retains identical historical candidate hash, admission IDs, transfer caps and
attempted-byte accounting. Exact partial writes do not erase attempted bytes.
Transfer-cap bytes are different from fictional registry engineering units;
neither is a proven privacy budget or authenticated recipient receipt.

After revocation, an earlier delivery prefix is rejected using the separately
retained later floor. Probe copies are fresh files; the original generated live
store and all previous milestone artifacts stay intact. These are component
restart and stale-copy drills using ephemeral fixture identity, not full IdP/KMS
recovery, replicated database failover or a cloud disaster-recovery exercise.

## Run and inspect the local harness

Use only the D-drive government checkout. No dependency downloads, cloud
deployment, private dataset admission or external messages are part of the run.
Choose a fresh ignored output under .local.

~~~powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONPATH = Join-Path (Get-Location).Path 'src'
$env:TEMP = Join-Path (Get-Location).Path '.local/verification/rehearsal-temp'
$env:TMP = $env:TEMP
& .\.venv-pipeline\Scripts\python.exe -B scripts/rehearse_capacity_recovery.py --profile local_public_fixture --output .local/verification/prd21-capacity-example
~~~

The result records the frozen workload plan/digest, measured outcomes, source and
runtime bindings, restore/counter conservation, exact named checks, generic failure
types and non-authorizing flags. Credentials, private key material and exception
text are omitted. The CLI refuses production before output creation and never
overwrites a run. A source change or incomplete required check set fails the run.

## Agency-scale qualification still required

The [private-cloud plan](production-private-cloud-plan.md) proposes metadata p95
under 2 seconds, sustained 2x agreed peak, zero lost acknowledged privacy charges,
validated recovery within 4 hours and 99.9% availability. These are initial
unapproved engineering targets. This fixture does not qualify any of them.

| Decision or test | Required production evidence | Local limit |
| --- | --- | --- |
| Approved workload | Named agency/model/interface, users, releases/day, full object sizes, scan/selectivity, worker hours, expected bursts and retention; accepted quotas and stop limits. | Fixed public tiles and twelve tiny count jobs; no private-data scale target. |
| Data scanning | Approved safe large-object formats, partition/cohort queries, encrypted immutable snapshots, bounded streaming/memory/I/O at full agreed scale. | Numeric public-byte projection; prior bounded research loaders are not huge-data streaming proof. |
| Scheduling/capacity | Tested queues, backpressure, fair per-project quotas, worker/container CPU/memory limits and measured 2x peak over an agreed sustained duration. | Bounded local process fixture; runner-call count is not aggregate OS/cluster resource telemetry. |
| Database HA | Provider-selected authoritative database/replication, acknowledged-commit durability, fencing, split-brain and network-partition drills, no duplicate/lost real charges. | Local SQLite write reservation and witnessed historical replay; fictional units only. |
| Backup custody | Approved encryption/KMS, separated administrators, retained external authenticated floors, backup availability and dual-control restore from independent custody. | Ordinary new local files and separately held local pins; coherent privileged replacement remains outside scope. |
| Current-authority recovery | Fresh accepted identity/trust/data/policy/evidence decisions, suspended export until uncertainty resolved, no historical approval rehydration. | Local component denial drills; no production identity/key/catalog restore. |
| Recovery targets | Measured RPO/RTO under approved load and fault model, including total site loss, stale replicas, collector outage and live transfer uncertainty. | Measured bounded historical file restore and current-context denial; no cloud/site recovery. |
| Independent acceptance | SRE/database/key/data owners and independent assessors review all results, failures, remaining gaps and operational runbooks. | Trusted local verification; accountable agency appointments still required. |

A production trial must retain failed/denied/uncertain outcomes and resource
measurements alongside successful samples. Correct security denial is not an
availability success or silent capacity drop. Unsupported interfaces stay blocked,
and no backlog, backup or failover retry may reset cumulative disclosure history.

## Verification and preservation

The fresh ignored .local/verification/prd21-capacity-20261005 receipt records actual
test counts, required no-skip government checks, offline focused tests, real
source/installed rehearsals, repeat-wheel hashes and exact prior preservation.
Results qualify only the recorded local Windows runtime and fixed workload.

All earlier package source, implementation, advisory files, evidence and runtime
environments remain preserved. The retired 28 September archive stays deleted,
and no OneDrive/original/academic repository is edited. No Git staging, commit,
push or publication is performed. GitHub authentication remains pending.

Next is PRD-22, independent security and evidence assessment. Production work
remains in progress until the actual approved deployment meets its acceptance gates.
