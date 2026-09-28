# Bounded central release gate

The central authority uses one durable account for the union of certified source
executions behind all covered releases. Recipient names do not partition the
privacy budget. Releasing the same source again, or constructing several bundles
from it, does not create a fresh privacy charge; a separately randomized source
does. Public source identifiers name immutable executions, not model families.

This is an executable trusted-local prototype. It is not evidence that all
agency egress is controlled, that a general trainer is private, or that a local
database resists an administrator who forks or coherently replaces it.

## Protection contract and trusted inputs

`src/model_release_assurance/central_audit.py` supports fixed-person,
fixed-public-membership value replacement. The authority registers a global
person universe, project-local aliases, immutable dataset versions and their
row-to-person mapping before requesting covered computations. An unresolved
alias is rejected. Repeated rows or dataset versions associated with the same
person count together; overlap is never inferred absent from missing identity
data. Dataset contribution limits are checked against the public mapping.

Registration, model schedule, certificate choice, alias linkage and protection
scope must be public/fixed independently of protected values. The software does
not certify this premise. The namespace `person` contains canonical IDs; project
namespaces may bind several local aliases to the same person. The gate cannot
detect that two supplied global person IDs secretly represent the same human.
Identity resolution and completeness are central-agency obligations.

The certificate catalog is frozen at database creation. Each entry has exactly:

```python
{
    "id": "reviewed-source-mechanism",
    "family": "gaussian-person-v1",
    "cost": "1/25",
    "scope_id": "fixed-person-values",
    "randomness": "fresh-independent",
    "mechanism": "approved-person-clipped-learner-v1",
    "reviewer": "central-agency"
}
```

The catalog is an authority-reviewed trust input, not a machine-checked proof.
`cost` and `cap` are exact nonnegative rational strings; floating point is
rejected. One database uses either pure epsilon or Gaussian zCDP rho, never
their untyped sum. A Gaussian certificate assumes an approved Gaussian
mechanism with the stated sensitivity and numerical implementation. A rho cap
does not by itself specify an epsilon/delta guarantee.

| Certificate family | Per-person charge for a source with r rows belonging to that person |
|---|---|
| `pure-row-v1` | r times the certified row epsilon |
| `pure-person-v1` | the certified person epsilon once |
| `gaussian-row-v1` | r squared times the certified row Gaussian rho |
| `gaussian-person-v1` | the certified person Gaussian rho once |

The Gaussian row rule requires the Gaussian query sensitivity contract, not an
arbitrary assertion that any row-level private algorithm has this parameter.
Person-calibrated certificates already bound the entire person's contribution;
they must not be multiplied again by row count. Ordinary source certificates
require fresh independent execution. One additional built-in certificate covers
the complete count-based old/new model history described below. Shared coins
between distinct source groups, retrospective
joint-certificate merges, private cost selection and arbitrary scope changes are
unsupported. If two artifacts share one approved randomized output, register
that output once and use its source ID in both dependency closures.

## Lifecycle and actual exported bytes

1. `CentralAuditGate.create(...)` fixes authority, scope, roster, catalog,
   accounting family, cap and representation. It refuses to overwrite a file.
2. `register_alias(...)` and `register_dataset(...)` register public identities
   and bounded memberships. Existing bindings cannot be changed.
   `register_aliases([...])` validates a whole alias batch before one atomic
   commit. A bad item rejects the entire batch; repeated identical bindings are
   idempotent. Single-alias registration uses the same validation path.
3. `register_source(...)` binds dataset versions, certificate, globally unique
   execution ID and output kind (`model` or `intermediate`). Registering a new
   source name for the same execution ID is rejected.
4. `register_postprocess(...)` registers an immutable node with existing parent
   nodes. Unknown dependencies, self-dependence and cycles are rejected. The
   only supported operation is a canonical bundle of approved source bytes.
5. `prepare_release(...)` validates the full dependency closure and reserves
   every fresh source atomically under `BEGIN IMMEDIATE` before computation.
   Exact modes check every affected person's rational cumulative account. The
   coarse mode stores one scalar: the sum of each source's largest person charge.
6. The trusted approved producer computes only after this reservation. It calls
   `commit_source(...)` with the bound output bytes; a source cannot be replaced
   or rerandomized. A caller cannot attach arbitrary uncharged weights to a
   postprocessing node. Generic producer correctness is a trusted boundary.
7. `commit_release(...)` writes the immutable source bundle and hash.
   `deliver(...)` revalidates current dependencies and byte bindings, records
   delivery durably, then returns actual bytes. Recipient labels are audit
   metadata. They do not create separate accounts.

The canonical bundle contains every certified source in its closure. This is
not a minimum-disclosure system that trains an arbitrary derived model from
hidden intermediates. An intermediate source is delivered as an intermediate;
it is not relabeled a fitted model. If all registered sources are approved
private model coefficients, the bundle contains those model coefficients.

Cap refusals for valid registered proposals are recorded with public proposal
ID, node, accounting revision and `cap-exceeded`. Retrying the same refusal is
idempotent; rebinding its ID is rejected. Malformed/unregistered-input errors
are operator exceptions and are not comprehensively logged. Status and full
audit methods are trusted-operator interfaces, not arbitrary public queries.

Reservations are conservative and never refunded, including failed computation
or an abandoned request. Source commitment failure rolls back bytes while
leaving the earlier durable reservation. Retries reuse an already committed
source instead of drawing again. Revoking a source, ancestor, dataset or
certificate stops future dependent commitments and deliveries. Already delivered
bytes remain available to their recipient and remain charged. This gate does
not implement machine unlearning or assess deletion utility.

## A concrete built-in private producer

`execute_rr_mean(source_id, values)` supports the fixed mechanism
`rr-bit-mean-ln2-upper1-v1`, with `pure-row-v1` and cost `1` only. After checking a
durable reservation, it independently keeps each binary row with probability
2/3 and flips it otherwise using `secrets.randbelow(3)`. The exact odds are 2,
so row epsilon ln(2) is conservatively bounded by 1. It exports a clipped
debiased mean probability as a small binary mean model. This is a deliberately
simple executable example, not a competitive general predictive model. Public
input order is sorted dataset IDs followed by sorted row IDs. The correctness
of source value/version binding and OS entropy remain trusted assumptions.

Generic `commit_source` cannot claim this built-in certificate. Approved external
Gaussian trainers may use their distinct reviewed certificate, with their own
sensitivity/noise/numerical validation. The prototype does not retrofit a
certificate onto arbitrary existing models.

## Exactly checked two-model extension

The `COUNT_HISTORY` mechanism reserves the full two-model history before its old
model is sampled. Its catalog entry must use `family="pure-row-v1"`, `cost="11/10"`
and `randomness="independent-history"`. The exact joint odds are three; the
rational charge conservatively bounds `log(3)`. Different histories remain
separately charged, even when they affect the same records or recipients.

After registering its source and preparing the old release:

```python
gate.execute_count_old("history", values)  # values are internal categories 0..3
gate.commit_release("old")
old_package = gate.deliver("old", "recipient-one")
gate.optimize_count_extension("history", "new-model", gamma="3/5")
gate.prepare_release("new", "new-model")
gate.execute_count_extension("new-model")
gate.commit_release("new")
new_package = gate.deliver("new", "recipient-two")
gate.audit()
```

The earlier setup must call `prepare_release("old", "history")`. The four record
categories encode `first_bit + 2*second_bit`. The saved old model is the majority
of first-bit RR with retention 3/4; fair ties apply at even roster sizes. The
optimizer only sees public roster size and the declared public signal parameter.
It does not receive actual counts or the old model output. Its proposed rational
channel must preserve the old law and satisfy every joint DP inequality exactly.
An exact primal/dual interval also bounds utility. Ordinary `commit_source`
cannot bypass this built-in producer with caller-supplied bytes.

The new model is sampled from the verified conditional law using integer
rejection sampling. Its confidential counts stay inside the account database.
Packages retain original source outputs and add the committed new model under
`derived_models`; descendant bundles preserve both. Exactly one extension is
allowed per history. Retries reuse its bytes; an additional model, changed data
or cache disclosure needs a new joint argument or a separately charged source.
The experiment measures a fixed four-category learner, not arbitrary models.
Public parameter selection, truthful input linkage, OS entropy and a trusted
authoritative store remain assumptions. It does not enforce egress outside this
process or prevent a privileged operator from forking the database.

See [integrated measurements](../academic/extension-enforcement-20260928/README.md)
and [finite optimization evidence](../academic/scalable-extension-20260928/README.md).

## Representation comparison and verification

The saved comparison does not establish a consistent graph speed advantage.
For a new pilot, explicitly select `mode="flat"` unless indexed graph queries
have a measured benefit. The API retains its `graph` default for compatibility
with the original prototype. Use `register_aliases` for an atomic bulk import.

The fitted-model integration can be reproduced into a new, nonexistent output
directory with the existing Python environment:

```powershell
.privacy-venv/Scripts/python.exe scripts/demo_central_model_export.py --output <new-output-directory>
.privacy-venv/Scripts/python.exe scripts/replay_central_model_history.py --directory <new-output-directory> --receipt <new-output-directory>/recipient-replay.json
```

It aggregates/clips each person's three rows, reserves before computation,
commits five fitted Gaussian coefficient models, and delivers each to two
recipients. The common account is rho=1/5 per person; a sixth source is denied
before a draw. The standalone replayer uses delivered weights and public test
features only. `integration-v3` under the validation-study directory binds the
final gate revision. Its OS-backed floating Gaussian sampler is not a certified
finite-machine DP mechanism, and the generic producer remains trusted.

The `flat` comparator caches immutable canonical source/ancestor sets as
serialized records. The `graph` route additionally stores indexed source and
ancestor relations. Both maintain correct source/person indexes, reuse identical
sources, and update only fresh-source costs; neither rescans full release history.
Both should make identical decisions under identical registration and proposal
order. A graph is useful for dependency inspection, but is not mathematically
necessary to perform this accounting.

The `coarse` comparator performs a true scalar account update. Its per-person
status view is expanded only when read. It may refuse safe proposals admitted
by exact accounting; those refusals are conservatism, not evidence of greater
privacy than the same cap and contract.

`audit()` independently traverses direct edges, compares cached and indexed
closures, recomputes contribution charges, reconciles retained reservations,
and checks source/release byte hashes and refused-proposal bindings. These
checks catch bounded inconsistency and accidental mutation; unauthenticated
hashes are not an external integrity anchor. A coherent fork can independently
pass the same local checks. A production deployment needs a single authoritative
egress inventory, producer isolation, access controls, identity governance and
an external rollback/replication policy. Central authority does not require
centralizing every raw dataset, but this prototype stores public membership
manifests and delivers only locally committed bytes.

Tests are in `tests/test_central_audit.py`. They include a 216-history exhaustive
independent accounting oracle, all four calibration families, concurrency,
durable refusal and reservation behavior, revocation, mutation checks, actual RR
execution, restart recovery and an explicit coherent-fork limitation. The
benchmark runner is `scripts/benchmark_central_audit.py`; saved evidence is in
`academic/central-audit-validation-20260926/gate/`. Those trials use public fixture
artifacts to isolate accounting/control cost. They are not private-training or
utility experiments and do not support production throughput claims.
