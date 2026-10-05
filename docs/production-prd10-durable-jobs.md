# PRD-10: durable public-fixture jobs and controlled workers

Status: **in progress**. The local implementation adds durable scheduling state,
per-attempt input reservations and a fixed public worker. Production isolation,
durable agency authority and deployed acceptance remain pending. Work stays in
the D: government repository; provider and region
remain open. This milestone admits no private data and authorizes no model release.

## Job and authorization contract

`production_jobs` is a separate fixture workflow. The existing local console and
its workers are not changed into production services. The only registered recipe
is `public-count-summary/v1`: it reads the exact PRD-07 fictional count fixture
and returns two categories totaling 19. There is no caller-supplied executable,
script, path, environment, model, URL or arbitrary input. A canonical descriptor
binds the agency/project/case, complete immutable object reference, worker source
hash and trusted bounds: three attempts, a 30-second lease and a five-second
worker deadline in the service.

The broker accepts raw signed access tokens and uses PRD-06 current case
permissions plus PRD-08 current key trust. Operators submit/cancel, data stewards
authorize exact input and enrolled workloads execute with a signed `job:<id>`
permission. Holders bind the entire verified credential projection, canonical
person and authority revision; reusing a token identifier with changed claims
cannot borrow a grant. Submission records the operator for independent-review
separation. A caller-supplied descriptor digest must match before work starts.

A completed result retains its original submitter, steward and worker contexts.
Read access rechecks those contexts and the current case reader. Revocation,
expiry, changed authority or unavailable trust prevents result disclosure.
Replacing input authorization cannot substitute a different worker for the
original result. The bounded input read and final result commit run under the
identity authority lock; child execution releases that lock so revocation and
cancellation can proceed while work runs. These are single-broker process-local
authority semantics, not distributed identity synchronization.

## Durable custody and restart behavior

`JobStore` uses SQLite STRICT tables for jobs, attempts, grant reservations,
bounded event codes and broker history. It opens an existing store only with its
expected identifier and exact schema. Missing, replaced, corrupt or incompatible
stores fail; there is no silent reset. Ordinary local paths, stable file identity,
size limits and refusal of links, reparse points and unexpected journal modes
reduce accidental custody substitution. This assumes a trusted host and local
filesystem; it does not defend against a malicious administrator or whole-store
rollback. SQLite operations require a runtime supporting STRICT tables.

Transactions use `BEGIN IMMEDIATE`, a one-second busy timeout, DELETE journaling
and `synchronous=FULL`. SQLite serializes writers and may reject a busy writer;
callers receive failure rather than presumed success. See the primary
[transaction documentation](https://www.sqlite.org/lang_transaction.html) and
[synchronization documentation](https://www.sqlite.org/pragma.html#pragma_synchronous).
Local crash tests are not power-loss, shared-filesystem or cloud failover
qualification. There is no WAL/shared-storage cluster or durable external queue.

Each successful claim creates a random attempt ID and increments a fence. The
full lease binds the job, attempt, fence, current broker, exact holder, authority
revision, input grant and deadline. Renewal preserves a bounded attempt lifetime;
old lease tuples and late results are rejected. Current authorization and time
are checked after acquiring the database write lock and again before commit.
The committed clock high-water mark rejects backward time. Clock trust, database
anti-rollback and durable external authorization remain separate production work.

Input has three permanent transitions before success:

1. `consumed` commits the one-use grant reservation.
2. `read_started` commits permission to invoke the physical read once.
3. `delivered` records the exact size and digest check after the bounded read.

A crash or failed read never refunds those markers. Reading again requires a new
attempt and a fresh steward grant; neither a restart nor retry reuses a consumed
reservation. Success requires delivered input, a current lease, exact typed
output, current authorization and confirmed process cleanup. Cancellation and
completion serialize through the store, so a cancelled job cannot accept a late
result. Failed attempts retain bounded reasons; raw child logs, bearer tokens,
private keys and input payloads are not stored in this database.

A new trusted broker instance retires the old broker, abandons its running
attempts and revokes unused grants. Spent markers and histories remain. Reusing
a retired broker ID is refused. PRD-07 object/grant authority and PRD-06/08
identity/trust remain process-local: reopening SQLite cannot restore them.
Historical outputs are redacted without their original current authorization;
queued historical work cannot resume automatically. Production recovery needs
durable authenticated authority and a reviewed reconciliation procedure.

Fixture caps are 256 jobs, 1,024 grant records, 4,096 events and a 16 MiB database.
Capacity exhaustion fails without deleting history. These are small-fixture
bounds, not capacity planning for agency-scale health data.

## Worker process controls

The runner starts a fixed stdlib worker using an absolute trusted Python
interpreter with isolated mode, site imports disabled and bytecode writes off.
It uses fresh per-attempt working and temporary directories and a small explicit
environment; parent credentials, proxy settings and Python search paths are not
forwarded. Exact public bytes arrive through bounded stdin. Captured stdout is
limited to 64 KiB and stderr to 8 KiB; overflow, malformed output, unexpected
stderr, nonzero exit, cancellation, timeout or unconfirmed cleanup cannot yield
accepted output. Total observed byte counts can exceed capture limits without
retaining those extra bytes. At most 128 attempt directories are allowed per
runner; attempted directories are retained and cannot be reused.

On Windows, the parent assigns the owned process to a noninheritable Job Object
before releasing a one-byte bootstrap gate. Assignment failure aborts before
fixture execution. Kill-on-close and owned-handle termination cover descendants;
cleanup checks for zero active processes. See Microsoft's
[Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)
and [assignment requirements](https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-assignprocesstojobobject).
The POSIX path uses an owned process group and retains leader identity until
cleanup. It fails closed when cleanup cannot be established, including lingering
group members; it is not a hostile-code or supervisor-crash containment claim.
Linux runtime execution remains unverified locally.

These controls do **not** isolate network, filesystem, cloud metadata or host
secrets from arbitrary code. No container, VM, AppContainer, seccomp policy,
CPU/memory/disk quota or egress firewall is provisioned. Receipts explicitly keep
`hostile_code_isolated=false` and `network_isolated=false`. Worker source hashing
is local recipe binding, not PRD-09 image admission or authenticated runtime
attestation. Only the fixed public fixture is eligible for this path.

## Rehearsal and required checks

From the D: checkout, use the prepared environment and fresh ignored outputs:

```powershell
& .\.venv-pipeline\Scripts\python.exe -B scripts/rehearse_fixture_jobs.py --output .local/fixture-jobs-v1
& .\.venv-pipeline\Scripts\python.exe -B scripts/run_required_tests.py --profile government --output .local/required-prd10
& .\.venv-pipeline\Scripts\python.exe -B scripts/verify_build_baseline.py --output .local/build-baseline/prd10
```

The rehearsal uses real ephemeral signed credentials, the exact public input and
an actual child process. It verifies durable reservation ordering, job completion,
old-broker denial after reopening and historical result redaction with fresh
empty storage authority. Source hashes are checked before and after; incomplete
milestones or source drift produce a failed receipt. Existing output directories
are refused and failure evidence remains. Private signing keys and raw tokens
are never written to evidence.

Four mandatory suites cover the store, service, executor and rehearsal. They
exercise independent-process races, crash-after-read reservation, clock/lease
expiry, cancellation, identity and key changes, exact output binding, bounded
capture and descendant cleanup. Existing identity/storage/trust and government
checks remain required. Passing a local fixture is not agency approval or
production qualification.

## Observed local results

On 1 October 2026, **678 required government tests passed with zero skips,
failures or errors**. The 77 new checks comprise 31 store, 25 service, 14 executor
and seven rehearsal tests. Another 35 runner/documentation checks passed. The
standalone Windows rehearsal passed all 12 required milestones, including an
actual child-process result and restart denial. Required-test receipts bind the
exact package, script, helper and selected policy source hashes.

Evidence is retained under `.local/verification/prd10-jobs-20261001/`; the final
validation receipt records build, installed-wheel and preservation results.
The 99 other package files from PRD-09 remain byte-identical; the existing
identity policy gained only the narrow job authorization bridge. Earlier
milestone evidence and the 123 deliberate archive deletions remain preserved.
Linux execution, remote CI and cloud isolation are still unverified.

## Production closure

Before private-data use, qualify durable identity/trust and storage-grant
recovery, a production queue/database with migrations and backup/failover,
authenticated broker leadership, reviewed clock/lease policy, immutable audit
custody, resource quotas and cleanup under supervisor/host failure. Enforce
network, metadata, filesystem and secret isolation in the selected private cloud;
prove denial with hostile fixtures. Admit only approved images and exact recipes
through PRD-09 controls, complete licensing decisions and validate both target
runtimes. Agency owners must approve retention, capacity, operational response
and large-data access. The provider and region decisions remain pending.

The next local milestone is [PRD-11](production-prd11-adapter-benchmarks.md):
typed versioned adapter contracts, native controls and independent replay,
expanded to cross-sector public research benchmarks at the user's request. Earlier production acceptance gates
remain open.
