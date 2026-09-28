# Generated release-gate validation

The actual local HTTP gate agreed with the independent oracle on all 3,896
tested HTTP actions and preserved the oracle's accounting state across 200
application-client restarts. All 384 specified fault probes blocked their
designated invalid target. No false accept, false denial, commitment-state
divergence or wrong-byte delivery was observed in this finite study.

These results support enforcement of the tested local contract. They are not
a population fault-detection rate, universal state-machine verification,
privacy information-flow proof or deployment evaluation.

## Methods

`PLAN.md` documents the design. `run-v1/registration.json` was written before
the full run and fixes source hashes, runtime versions, seeds and denominators.
The design was informed by the implementation, its previous tests and the
preserved `smoke-v1` development execution. It was not independently or
externally preregistered. The full run uses seeds 20260921--20261048 for 128
32-action traces, followed by seeds 20270921--20270932 for each of 32 fault
classes. All data, registries and package bytes are generated toy fixtures in
temporary directories. The script executes production FastAPI endpoints and
the existing store and pipeline, without editing those implementations.

The independent oracle uses stage flags, revisions and channel/unit sets. It
does not call production accounting helpers or infer expected outcomes from
server status flags. Three generated package modes cover model-only export,
same-cache scoring and separately randomized scoring dependencies. Costs,
roster overlaps and caps vary across seeds. The generated histories begin with
complete proposal paths, including permitted controls, before seeded action
ordering, retries, stale payloads and revocation. Every action compares the
decision, persisted revision, charges, receipt identities and pipeline commit
identities. Successful downloads are compared with the registered exact bytes.

Faults mutate one selected binding or prerequisite after an appropriate stage,
or inject an exception/expiry at an actual transaction hook. They cover skipped
stages, cross-request approvals, changed artifacts and lineage, current
authority/evidence, competing commitments, receipt integrity and rollback.
The 12 fixtures per class cycle through all three package modes. Relevant
classes target both commit and download. The complete class list and mutation
definitions are retained in the plan and runner.

## State-transition results

| HTTP action | Tested | Oracle permits | Oracle denies | Disagreements |
|---|---:|---:|---:|---:|
| Prepare | 850 | 607 | 243 | 0 |
| Checks | 697 | 329 | 368 | 0 |
| Review | 674 | 329 | 345 | 0 |
| Commit | 835 | 651 | 184 | 0 |
| Download | 696 | 555 | 141 | 0 |
| Revoke | 144 | 125 | 19 | 0 |
| **Total HTTP actions** | **3,896** | **2,596** | **1,300** | **0** |

The 200 client/application restarts are additional persistence checks, not
HTTP admission decisions or process-kill tests. Together they yield 4,096
trace actions. The trace includes 1,645 successful prescribed control actions.
Permitted repeated commits return the original authorization without duplicate
charges; denied actions do not become authorized merely because earlier
steps or unrelated commitments exist.

## Fault results

| Specified fault group | Classes | Probes | Target blocked and committed state preserved |
|---|---:|---:|---:|
| Stage and review | 5 | 60 | 60 |
| Bound bytes and lineage | 9 | 108 | 108 |
| Stored assurance binding | 3 | 36 | 36 |
| Current prerequisites | 5 | 60 | 60 |
| Release history | 4 | 48 | 48 |
| Recovery | 6 | 72 | 72 |
| **Total** | **32** | **384** | **384** |

Target responses were 324 HTTP 409 denials, 24 HTTP 503 configuration denials,
and 36 HTTP 500 responses caused by the deliberately injected exceptions.
Those 500s are retained outcomes, not silently discarded failures. Each
exception probe required rollback of committed state and successful retry
after removal of the fault. All 72 specified recovery cases passed, including
failed-check invalidation: restoring a corrupted cache did not resurrect an
old review; new checks and review were required before commitment.

No escaped fault or false denial was observed. This statement is limited to
the specified mutations and generated traces, which share code and fixtures.
It should not be converted into a binomial confidence bound over unknown
deployment faults.

## Evidence and limits

All eight oracle/harness unit tests passed; their exact output is retained in
`run-v1/harness-tests.txt`. A separate read-only record audit passed 223
source-binding, denominator and aggregation checks. It verifies the retained
assertions and counts; it does not repeat the API experiment or supply an
independent security proof. The four tested production source files retained
their original hashes throughout execution. Every probe is retained in
`run-v1/probes.jsonl`; each seed and class can be replayed by the script.

The oracle itself is a small executable specification and could contain
errors; its five focused logic tests reduce, but do not eliminate, that risk.
The study does not exhaust action sequences or combinations of simultaneous
faults. SQL mutations represent stale/corrupted trusted inputs, not an
administrator capable of coherently rewriting all bindings. The operation
clock is controlled. Exceptions and application restarts are not power-loss,
storage durability, anti-rollback or process-crash tests. Package contents are
opaque toy bytes, so no training provenance, private model selection, DP
certificate, MLflow integration, legal authority or statistical utility gate
is validated. No latency, throughput, scalability or contention result is
reported, and no live or historical ledger was modified.

Key SHA-256 bindings:

- Registration: `9dc004f8f3398e9113ec9eae72af3e6c8f69d725cb40ec749dc68caddfe4df8d`
- Probe records: `c74754c2d6abfd7454ded4e0970bd34f01a30cad28611db017eb11bbfa728b96`
- Results: `faa96c78916eb9be8b194269ccaa16f57d925374c79fb0765b65e4ffd37187bd`
- Record verification: `e33b5dc21328eefc39f82d9ee307069b5d05e758d0c1e7b4925ea84e1d0a46c3`

Run the integrity audit without API execution using a new output path:

```powershell
.local/pipeline-runtime/Scripts/python.exe academic/full-revision-20260921/fault-study/verify_records.py --run academic/full-revision-20260921/fault-study/run-v1 --output <new-verification-json>
```
