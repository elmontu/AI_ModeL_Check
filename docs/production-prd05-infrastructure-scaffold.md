# PRD-05: infrastructure intent and local lifecycle rehearsal

**Record:** PRD-05 / revision 0.1 / 1 October 2026.
**State:** `in_progress` — provider-neutral preparation; real cloud infrastructure,
agency acceptance and cloud deployment/teardown remain pending.
**Parent:** [production roadmap](production-private-cloud-plan.md).
**Dependency:** [PRD-02 threat model and decisions](production-prd02-threat-model.md).
The selected scope is a major public-health agency with large private datasets.
Provider and hosting region remain open at the user's request; no jurisdiction,
cloud runtime, agency approval or private dataset is inferred.

## Implemented preparation

The [blueprint](../deploy/agency-private-cloud/blueprint.json) is a versioned
design-input contract. The [validator](../scripts/validate_infrastructure_plan.py)
checks its structure and restrictive preparatory settings without creating cloud
resources. This is not provider infrastructure-as-code. Its logical references
will need a reviewed mapping to real resources and administrative boundaries.

| Environment | Current cloud state | Permitted local exercise |
| --- | --- | --- |
| Development | Planned, disabled | Fictional case and queued preflight |
| Staging | Planned, disabled | Separate case inventory and service readiness |
| Production | Planned, disabled | None |

Each environment has separate logical references for account, network, identity,
artifacts, evidence, governed data, keys, registry, witness, audit and backup.
Application and witness administrator references must also differ. These names
express intended separation; they cannot establish independent operators, IAM
permissions, encryption, tenancy isolation or custody.

The validator rejects duplicate/unknown fields, malformed or excessive JSON,
type substitutions, shared references, resolved endpoints, fabricated approvals
and production-enabling changes. Provider, runtime and primary/recovery locations
remain null. Supplying a provider name does not turn this preparatory schema into
a deployer: a later reviewed implementation must define actual provider inputs,
state management, lifecycle behavior and acceptance evidence.

Required intent includes private ingress/DNS/TLS; default-deny egress, lateral and
metadata access; no public object URLs; no API bulk-data grant; no worker
release-key or registry-write grant; and no direct recipient storage grant.
Scoped worker grants, immutable artifact/evidence versions, independent witness
administration, a sole delivery gateway and quarantine after backup restoration
are required design constraints. None is claimed to be enforced by this JSON.

The [local rehearsal](../scripts/rehearse_local_deployment.py) exercises the
existing console using fresh development and staging stores. It accepts no
model or dataset input. It starts API/worker processes on loopback, checks
readiness, creates a fictional case, queues its preflight, verifies separate
inventories, restarts the development services to check persistence, and stops
its owned processes. The preflight must honestly return `inputs_incomplete` and
`authorization_eligible: false`; this fixture cannot qualify a model.

## Endpoint and resource handoff

Every endpoint role in the blueprint is unresolved. Select endpoint addresses,
certificates, trust roots, name resolution and policy bindings only inside the
approved agency environment; do not commit credentials or private addresses as
substitutes for a reviewed deployment configuration.

| Intended service flow | Implementation and acceptance still required |
| --- | --- |
| Agency user to private ingress and identity service | Private DNS, validated TLS, approved SSO/MFA and case permissions; PRD-05/06 |
| API to queue and scoped metadata services | Explicit service identities and least-privilege grants; API cannot read bulk source data; PRD-05/06/07/10 |
| Worker to approved immutable inputs and restricted evidence | Per-job grants, bounded formats, denied metadata/secrets/egress, hostile-code isolation and complete timeout termination; PRD-07/09/10 |
| Registry to keys and independent witness | Atomic state transitions, separate key/witness custody, retained negative transitions, rollback detection and fencing; PRD-08/15/16 |
| Recipient to sole release gateway | Exact approved output roster, durable admission and witness before delivery, no alternate object/ZIP/log path; PRD-17/18 |
| Operations to audit and quarantined restoration | Restricted logging, approved retention, independently retained recovery expectation and tested reconciliation; PRD-16/20/21 |

For the eventual provider implementation, Platform/SRE must supply reviewed
modules, versioned inputs, an encrypted/locked state backend and separate
deployment identities for each environment. Define plan/apply review, drift
detection, inventory, ownership labels, quota/cost bounds, secret injection and
idempotent cleanup of that deployment's resources. State and backup access must
respect witness/key separation; application administrators must not be able to
silently replace every copy of authoritative history.

Cloud acceptance must exercise approved/denied network paths, DNS and TLS
failures, metadata and public-storage denial, cross-environment/cross-role reads,
credential leakage, witness unavailability and restore quarantine. Record actual
resource identifiers in approved custody, exact build/configuration hashes,
expected/observed results, independent review and residual risks. PRD-05's
resource teardown must account for retained audit evidence, approved retention
and holds; deleting the evidence is not successful cleanup.

## Local operation and evidence

From the government repository on D:, using its existing console environment:

```powershell
& .\.venv-pipeline\Scripts\python.exe -B scripts/validate_infrastructure_plan.py --plan deploy/agency-private-cloud/blueprint.json
& .\.venv-pipeline\Scripts\python.exe -B scripts/rehearse_local_deployment.py --plan deploy/agency-private-cloud/blueprint.json --output .local/deploy-rehearsal/prd05-run
```

Use a new ignored child of this repository's `.local/` directory for every run.
Existing destinations, traversal and symlink/reparse output paths are refused.
The rehearsal uses dedicated temporary stores and never reuses an operator's
working console store. Logs, stores and its result receipt remain after shutdown
for review. Local teardown means stopping owned processes and checking closed
listeners; it does not delete files or exercise cloud-resource deletion.

The validator prints `valid_design`, an exact-file SHA256 and
`cloud_deployable: false` with outstanding blockers; invalid inputs fail.
The rehearsal also remains non-authorizing regardless of its test result.
Its receipt records lifecycle observations and configuration/source identities.
A failed startup or fixture check must fail the run while still attempting
cleanup and retaining diagnostics. Re-run with a fresh destination after fixing
the cause; never overwrite an earlier failure receipt.

Only public/synthetic fixture metadata belongs in these diagnostics or CI.
The local rehearsal uses plain HTTP on `127.0.0.1` and the current trusted-local
console model. It does not test TLS, protect against hostile users on the host,
or establish multi-tenant isolation. Distinct local directories demonstrate
inventory separation and persistence only.

The existing [Compose setup](../compose.yaml) and
[optional restrictions](../compose.hardened.yaml) remain development tools.
Their shared volume, inherited subprocess environment and current images are
not the production worker/custody boundary. The console can still be invoked
directly using its existing interfaces, including network binding and local
filesystem intake. This wrapper does not install a global production gate or
change those application paths.

The required government test profile includes both new preparation test suites
and hashes the mandatory blueprint before and after execution. The
[CI bootstrap matrix](../.github/workflows/ci.yml) also runs the real local
rehearsal on Ubuntu and Windows, retaining its single `result.json` artifact
even on failure. A missing receipt fails upload. The package job already
depends on that matrix, so a failed rehearsal blocks that path. Remote execution
remains pending GitHub authentication; local Windows evidence does not establish
a hosted Linux result.

On Windows, child launch uses the underlying CPython interpreter with the
existing virtual-environment context, following CPython's
[Windows multiprocessing launch implementation](https://github.com/python/cpython/blob/3.12/Lib/multiprocessing/popen_spawn_win32.py).
This avoids an intermediate launcher PID while retaining the strict readiness
PID/nonce check. It is a runtime compatibility detail, not process isolation.
The local run verifies this behavior; other interpreter implementations require
separate qualification.

## Validation and closure

Local validation evidence is retained under
`.local/verification/prd05-infrastructure-20261001/`. The final receipt binds
tested sources, validator/failure-path tests, the actual lifecycle rehearsal,
documentation checks and preservation checks. Historical PRD-03/04 receipts are
left intact as records of earlier revisions.

Observed locally on 1 October 2026: **358 required tests passed with zero
skips**, including 14 blueprint and 26 rehearsal regressions. **30 runner and
documentation tests** passed, and workflow validation passed **96 assertions**.
The real Windows lifecycle passed **21 checks**; all six owned process launches
stopped and all three API listeners were closed. Local links in 53 Markdown
files and whitespace checks passed; all 84 existing package files matched the
saved baseline.

The first real attempt rejected a virtual-environment launcher/interpreter PID
mismatch. Its failure receipt remains in `rehearsal/`; the closed listener was
checked separately. The corrected run and its source identities are retained
in `rehearsal-final/`. No failed receipt was replaced with a passing one.

PRD-05 remains `in_progress` until PRD-01/02 approvals and provider/location
decisions are resolved, provider infrastructure is implemented and reviewed,
isolated environments and endpoints are deployed, and public-fixture deployment
and cloud teardown pass with accountable acceptance. A local passing receipt
does not satisfy those completion conditions.

PRD-06 can next refine identity, workload permissions and independent-approval
contracts against this design. Actual agency SSO integration and private-data
admission retain the roadmap's dependencies and acceptance gates.
