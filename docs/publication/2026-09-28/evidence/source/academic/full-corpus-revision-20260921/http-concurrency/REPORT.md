# Bounded concurrent request evidence

All 30 prespecified concurrent request pairs matched the independent finite-state oracle. The unchanged application invocations overlapped in every pair (recorded overlap 11.1944–33.3203 ms). This is evidence for the six tested races within the local ASGI/SQLite boundary, not exhaustive concurrency verification or a distributed-service result. No production code was changed.

The accepted run is `run-v2/results.json`, SHA-256 `e69d55a2c0c853c1998a7ea5c567e43d8846cc04d23c761911a713aa2e28abce`. The source and protocol were frozen beforehand in `prespec-v1.json`, SHA-256 `36efcd280b94dcbe3bf1f5a86b55543be2507c24c20fc5467ceabeb7c62ce613`. Five independent-oracle unit tests passed before execution. The retained record verifier subsequently checked all 150 run files, 17 frozen source files, final SQLite tables, the exact 30-case grid and all recorded oracle orders (`verification-v2.json`). The verifier reuses the prespecified independent oracle, not the production accounting implementation.

Each race used two distinct TestClient instances, two HTTP caller threads, two ASGI portal threads, a shared toy SQLite ledger, two records and two separately registered channels. Each channel consumed the entire per-record cap. An outer rendezvous barrier introduced no production transaction hooks or accounting changes; overlap was measured inside the barrier, between calls to the unchanged app. The fixed five seeds identified fixtures and submission order. Operating-system scheduling was uncontrolled. These are in-process HTTP/ASGI requests, not a real HTTP server or network test.

| Concurrent operations | Races | Observed outcomes | Durable-state check |
|---|---:|---|---|
| Commit A / commit B, both reviewed at revision 0 | 5 | A won once; B won four times; other request returned stale 409 | One revision, one core/pipeline receipt, winner's two charged record/channel pairs only |
| Two commits of the same request | 5 | Both calls returned 200 in every pair | One receipt, one commitment audit event, one revision and no duplicate charge |
| Prepare B / commit A | 5 | B prepared before commit twice; three later prepares returned revision-conflict 409 | B exists only on the successful prepare branch; A committed once |
| Check B / commit A | 5 | Check succeeded first once; four later checks returned stale 409 | Failed checks left no B check/review and recorded the failed refresh |
| Review B / commit A | 5 | Review succeeded first once; four later reviews returned stale 409 | The old check remained; a stale review wrote no review record |
| Revoke A / download A | 5 | Three downloads authorized before revocation returned exact package bytes; two returned revoked 409 | Charges and receipt retained; authorization audit precedes revocation for successful download; all five subsequent downloads denied |

All tested outcomes for both distinguishable transaction orders occurred at least once in each case where order changes the outcome. Same-request retries have identical semantics in either order. These observed counts describe the realized schedules; they are not estimated branch probabilities, detector rates or coverage of all interleavings.

The completed run contains 190 HTTP requests: 125 setup calls, 60 racing calls and five post-revocation downloads. Responses were 167 HTTP 200 and 23 expected HTTP 409. There were no HTTP 500 responses, unexpected statuses, missing overlaps, byte-binding failures or oracle state mismatches in that run. Every final ledger retained exactly one core/pipeline commitment and two charged pairs at revision 1. Full raw responses, SQL snapshots, candidate orders, measured intervals and final databases remain under the corresponding numbered race directory.

## Every attempt, including failed harness attempts

1. The first prespecification startup used the existing ML runtime, which lacked FastAPI. Import failed before any fixture or HTTP request. `startup-attempt-1.json` retains this fact. The existing `.local/pipeline-runtime` environment was then selected without installing packages. Its TestClient import emits an upstream httpx-adapter deprecation warning; the warning did not prevent execution.
2. The first formal launch (`run-v1`) stopped in its first setup after one successful HTTP prepare. The harness attempted a read-only SQLite URI from a relative path and raised `ValueError: relative path can't be expressed as a file URI`. No concurrent pair ran. Its failed trace/database and result receipt remain; 1 fixture was attempted and 29 were not run. Results SHA-256: `84ac2aedfd13a954d1033452991d17f606d9b9c255886dc8c9974c744e2254bc`.
3. `invocation-amendment-v2.json` records the sole correction: pass an absolute output path. The same frozen runner, oracle, protocol, seeds and application sources were rerun in a new directory. All 30 pairs completed as reported above. No failed attempt or artifact was overwritten. Across both formal launches there were 191 HTTP requests, including the one successful setup request in the failed launch; only `run-v2` contains concurrent pairs.

## Claim suitable for the manuscript

“We additionally exercised 30 prespecified concurrent request pairs through separate in-process HTTP clients and ASGI portals, using an independent finite-state oracle over tiny retained ledgers. The tested competing commits, idempotent retries, stale preparation/check/review races, and revocation/download authorization races all matched a permitted transaction order, with no unexpected HTTP response or durable-state mismatch. Two initial harness/runtime failures were retained separately; neither was an application state violation. These tests concern the trusted local ASGI/SQLite boundary and do not establish distributed correctness or atomic network delivery.”

A successful download here means the exact registered bytes passed the authorization transaction and were returned by TestClient. It does not imply recipient acknowledgement. In a revocation race, authorization can validly precede revocation even if response completion follows revocation. Prior disclosure and privacy spending remain after revocation. The cap result is for the declared fixed-record/channel accounting model; this test supplies no independent differential-privacy proof and does not establish citizen linkage, authentication, authorization against privileged direct database access, crash recovery across hosts or correctness under every schedule.

To verify retained records without rerunning races:

```powershell
.local/pipeline-runtime/Scripts/python.exe academic/full-corpus-revision-20260921/http-concurrency/verify_records.py --run academic/full-corpus-revision-20260921/http-concurrency/run-v2 --output <new-verification-json>
```

To reproduce the fixed race grid, use the frozen prespecification and a new **absolute** output path. The runner rejects changed source hashes and existing output directories.
