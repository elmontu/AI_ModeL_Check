# PRD-24 — pilot exit review and operational handover preparation

Status: **in progress**. Local exit-review and operational handover preparation
are implemented. No agency pilot has started, passed an exit review or entered
operations. All eleven frozen PRD-22 production blockers remain open. The
architecture remains agency private cloud, with provider and region unselected.

## Implemented scope

The new production_handover service prepares one exact public Wine128 pilot
plan for a local exit review. It binds the original case, candidate bytes,
assessment manifest/key, finding catalog, plan digest and planning window.
A live acknowledged PRD-23 service is required; copied status dictionaries,
serialized records and unreviewed or suspended plans cannot establish readiness.

The contract records pilot-not-started status and a production **no_go**.
An owner proposal, current named operator, distinct assessor review and release
authority acknowledgment establish local preparation readiness only. No pilot
admission, model query, delivery, deployment or production exit pass is exposed.
The supporting fresh PRD-22 assessment performs its original bounded public
fixture probes; handover planning performs no second model fit or delivery.

Every enabling mutation uses original signed in-process participants. Exact
packet verification occurs before a final shared current-authority timestamp.
Roles, scope, MFA, trust/authority revisions, all original named people and the
original plan window remain applicable. New tokens supplied by the caller cannot
replace expired retained participants. No gateway or evidence lifetime is extended.

## Operational preparation

| Area | Local record | Agency acceptance still needed |
| --- | --- | --- |
| Exit decision | Pilot has not run; all frozen blockers remain open | Actual pilot observations, predeclared success/failure criteria and independent signed exit decision |
| Support | Named fixture operator and release authority responsibilities | Appointed service owner, support rota, contacts, escalation and every-route suspension exercise |
| Capacity | PRD-21 public fixture reference with pending objectives | Approved workload, peak/latency/recovery objectives and measured agency-scale evidence |
| Cost | Itemized cost requirements with unknown provider, region, prices and totals | Approved resource inventory, measured use, procurement prices, budget and stop limits |
| Maintenance | Access/trust/key/policy/dependency/source change review requirements | Agency cadence, named owners, tested updates and fresh independent evidence before re-enable |
| Retention/recovery | Historical records remain evidence; no authority restoration or accounting refund | Agency retention/legal holds, independently controlled backup and verified restore |
| Retirement | Terminal retirement of this local preparation | Every-route shutdown, credential/grant revocation, recipient-copy obligations, retention/deletion and closure acceptance |

Unknown cost is not zero cost. Public benchmark measurements do not qualify an
agency workload. This service does not rerun or authenticate a new capacity test,
query cloud pricing or decide procurement. Agency costing must include backups,
logs/SIEM, KMS operations, licences and independent assessment alongside compute,
storage, transfer, retention and support. Local maintenance declarations do not
appoint an agency operator or claim an operational service commitment.

## Restrictive transitions and historical records

Suspension, withdrawal or expiry of the linked pilot removes local handover
readiness. Terminal local retirement requires the current named release authority
and remains available when other people or packet evidence have become stale.
It restricts this preparation; it does not shut down an independent gateway or
erase previous disclosure, model copies or protected historical evidence.

Events are bounded and installed atomically under the shared identity lock.
Returned records are owned JSON values and never contain raw credentials.
Saved records are historical. A fresh service cannot import them to restore
operator, owner or independent-review authority.

The existing production implementation and dated research/advisory records are
preserved. New package source requires a new matching PRD-22 packet. Earlier
packets remain historical evidence replayable with their original implementation;
they are neither rewritten nor restamped to match new code.

## Rehearsal

Run from the D-drive government repository with the existing console runtime:

~~~powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONPATH=Join-Path (Get-Location).Path 'src'
$env:TEMP=Join-Path (Get-Location).Path '.local/verification/rehearsal-temp'
$env:TMP=$env:TEMP
& .\.venv-pipeline\Scripts\python.exe -B scripts/rehearse_pilot_handover.py --profile local_public_fixture --output .local/verification/prd24-handover-new
~~~

Choose a new ignored.local destination. The default production profile refuses
before output, source reads or assessment work. The explicit public rehearsal
freezes intent, generates one fresh signed assessment, completes the seven-person
pilot plan and independently acknowledges operational preparation. It exercises
scope substitution, unsigned proposals, owner/operator review denial, suspension,
original credential expiry, terminal retirement and copied-history refusal.

The CLI rejects incomplete checks, changed hashes, widened declarations,
false production claims and malformed reports. Failed stages retain completed
bounded observations and fixed generic error codes; credentials and raw exception
text are excluded. Source hashes are retained and checked for change during the run.

Local verification receipts are under
D:/ChatGPT/model_audit/AI_ModeL_Check_Government/.local/verification/prd24-handover-20261006/.
The required local government profile passed **1,909 tests with zero failures,
errors or skips**. All 37 schemas and local links in 72 Markdown files passed.
Source and isolated installed-wheel rehearsals passed, and the existing
implementation/advisory bytes remain unchanged. These are software observations
for this source tree, not agency acceptance.
The repository was published via SSH and merged into main. The frozen finding
catalog remains unchanged; publication alone does not satisfy external review
or production acceptance. Hosted CI failures are outside this phase at the
user's request.

PRD-24 completes only after a real admitted agency pilot has an evidenced exit
review, accepted capacity/cost and operational ownership, supported maintenance
and a tested retirement plan. Local preparation leaves those gates pending.

Next is **PRD-25**, selected ART adapters and further tabular/regression profiles,
with explicit dependency availability, declared attacks, validated controls and
separate scientific acceptance for each supported interface.
