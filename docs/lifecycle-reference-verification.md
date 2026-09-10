# Experimental local lifecycle mechanics

The new `src/model_release_assurance/lifecycle_reference.py` is a separate,
single-host SQLite reference implementation. It makes several ideal-registry
premises in Algorithms A5 and A6 executable. It is **not integrated with the
assessment facade, optimizer, CLI, Lean model, model-serving process or any
government authority**. Its receipts are local audit records and confer no
deployment authorization.

Each mutation takes an explicit external `Checkpoint` containing registry
identity, sequence and head. It acquires a SQLite `BEGIN IMMEDIATE` transaction,
checks the stored event chain and current state commitment, compares the
checkpoint, then samples the clock and checks current prerequisites. It samples
time and rechecks expiry again after event preparation, immediately before the
SQLite commit call. Nonce,
release, fixed integer budget charge, disclosure reservation, event and receipt
head are committed together. Only successful SQLite commitment returns a
receipt. Independent connections serialize their writes through SQLite;
`synchronous=FULL` is requested. These properties rely on SQLite and its
filesystem/hardware assumptions, not a new transaction algorithm or proof.
See the official [isolation documentation](https://www.sqlite.org/isolation.html)
and [atomic-commit documentation](https://www.sqlite.org/atomiccommit.html),
accessed September 9, 2026.

The supported route is an externally attested CLEAR assessment, PASS obligations
and PASS joint portfolio over the exact cumulative roster, followed by
authorized, active, suspended and revoked states. Activation and
every access check the committed artifact/interface digests, current authority
status and epoch, evidence/policy/authorization expiry, bounded lease, cumulative
integer budget and per-release access limit. Authority status UNKNOWN or REVOKED,
a replacement authority epoch, and equality at an expiry boundary deny access.
Clock reversal relative to the last committed event also denies transitions.
This clock test cannot establish trustworthy physical time.

Disclosure history and current release status are different tables. Every
commitment must reserve disclosure; delayed reservation is unsupported. Every
history extension suspends all previously authorized or active candidates in
the same transaction. The new candidate's certificate does not authorize earlier
endpoints. Activation and access also require equality between the current
history and the candidate's frozen history plus itself. Resuming a suspended
service requires a newly assessed candidate with a fresh identity and complete
history. Revocation never deletes history or refunds charges. Every later commit
must name the complete stored history; omission of a revoked release is rejected.
The registry cannot establish that the supplied original history was complete,
that two registries have disjoint adversaries, or that joint privacy evidence is
valid. It does not calculate composition risk.

The regression suite exercises:

- A safe positive commit, activation, grant and revocation path.
- Two independent database connections racing for one expected head; one wins.
- Grant/revocation ordering, stale retry refusal and denial following revocation.
- Duplicate nonces, stale heads, immutable release identity and changed bindings.
- Atomic rollback after state writes and after event preparation; process
  termination before commit; grant failure without partial charges and failed
  history extension without suspension of the existing service.
- Cumulative disclosure after revocation and uncertain client acknowledgement.
- Refusal of delayed reservation; suspension of active and unactivated earlier
  candidates on history extension; no automatic certificate inheritance.
- Unknown, revoked, replaced and expired authority; exact expiry boundaries;
  lease bounds; rechecking time after lock contention and event preparation;
  clock reversal before and during a transaction.
- Budget/access exhaustion, unsupported residual-risk acceptance and non-PASS gates.
- Mutable-state tampering, append-only table guards, and backup rollback detection
  against a separately retained checkpoint.

Run with an existing compatible Python environment and the source directory on
`PYTHONPATH`:

```powershell
$env:PYTHONPATH = (Resolve-Path src).Path
python -B -m unittest discover -s tests -p test_lifecycle_reference.py -v
```

The earlier [September 9, 2026 receipt](../output/lifecycle-reference-20260909T122206.507738Z-028d9d8f/results.json)
records 30 passing tests for the first version and remains unchanged.
Independent review subsequently found two missing cases: delayed disclosure
could reuse a stale joint roster, and expiry was checked only near transaction
entry. The supported subset now refuses delayed disclosure, invalidates earlier
service on history extension, and rechecks expiry before committing. The new
regressions cover these defects; the earlier receipt is not validation of these
corrections. Each receipt's adjacent `tests.txt` retains complete output.
The [post-review receipt](../output/lifecycle-reference-20260909T123208.900993Z-1242217a/results.json)
records **37 passed, zero failures, errors or skips**, and pins the corrected
module and test-source hashes.

These are ordinary Python regression tests, including one abrupt subprocess
termination. They are not exhaustive scheduling, power-loss or storage-fault
tests, machine-checked refinement, or a proof that SQLite/Windows is correct.
The first exploratory run exposed two Windows cleanup errors caused by unclosed
test-only SQLite connections; those tests now explicitly close their connections.
No historical evidence or proof receipt was changed.

**Rollback boundary:** a fresh trusted external checkpoint rejects a restored
older database. The suite also demonstrates that reading the restored database's
own head accepts that internally consistent older history. The independent
checkpoint store, authentication, durability and reconciliation after commit
without acknowledged receipt are unimplemented. A stale expected checkpoint
blocks progress; the caller must not silently refresh it from an untrusted file.
Hash chains and SQLite triggers do not authenticate a malicious database owner.

**Integration boundary:** authority installation is a trusted administrative
fixture, with every installed valid authority treated as a registry-wide revoker.
Assessment/obligation statuses and digests are trusted inputs. No signatures,
issuer roles, departmental delegations, current legal duties, due-stage reviews,
redress, monitoring signal, complete query policy or signed artifact measurement
are verified here. Budget units are frozen integer resource counters, not
statistical alpha or differential-privacy composition. There is no external
model output, bearer-token redemption or complete-output-channel enforcement;
already admitted accesses cannot be undone by later revocation. The immutable
snapshot measurement and real serving process still need a verified integration.
Optional RWR and actionable INCONCLUSIVE remain unsupported.
The reference recomputes the full local state/event chain on every transition;
no throughput, availability or distributed scalability claim is made.
The final expiry check still precedes the physical durable commit and any later
output. Scheduling, commit or delivery latency can cross a deadline after that
check. The event timestamp is the first in-transaction observation, not an
attestation of physical commit time. A real gateway must enforce deadlines at
actual output admission; these local audit receipts are not service tokens.

This demonstrator supplies fresh implementation evidence for a bounded subset of
the lifecycle. A publication should retain the distinction between these tested
mechanics, the broader written protocol, historical Lean theorems about an ideal
registry, and unverified operational and institutional premises.
