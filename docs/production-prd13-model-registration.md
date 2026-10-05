# PRD-13: prospective model registration and training evidence

Status: **in progress**. The local implementation records a frozen registration
before fitting a new model, links its lineage and reviewed numeric artifacts to
fresh authenticated replay, and retains failed attempts and known disclosure
observations. This is a public-data engineering fixture. It never authorizes
production import, private-data use or model delivery. Agency private-cloud
provider and region remain open.

The framework is sector-neutral. The eight available profiles cover census,
aviation, lending, mobility and bundled classification/regression examples.
Public health remains an example agency use case, not a restriction on the
framework. The separate academic repository and original workspace are unchanged.

## Registration before fitting

`LocalRegistrationWorkflow` accepts one of eight fixed public profile IDs. It
has no custom estimator, external model, parent model, private-data or privacy
budget input. Unknown profiles fail before data access. The four prepared
research files and manifests are pinned to the PRD-11 hashes; the four bundled
profiles require the pinned scikit-learn version and source hashes. Nothing is
downloaded or written into the research-data root.

Before the first native scaler or model fit, the workflow freezes and durably
commits the registration and a separate training-start event. The registration
binds agency, project, case, source and sample metadata, exact normalized data and
plan bytes, seed, fixed recipe, split counts, feature-group metric unit, utility
criterion, local source/runtime observations and the current history head.
Registration and start records are also written beside the future artifacts.

A new fit uses PRD-11's unchanged train-partition `StandardScaler` and fixed
GaussianNB classification or Ridge regression recipe. Identical feature vectors
remain indivisible groups. Exact frozen data and plan bytes must match the new
native artifacts. Code, runtime, source snapshot, frozen registration, current
signing trust and history are rechecked at custody boundaries. Changing any of
these bindings prevents a completed review. A failed or interrupted attempt
retains its registration; starting a new case does not refund or erase history.

This establishes ordering inside the trusted local process and ledger. It does
not prove remote training custody, measured boot, an approved worker image or
agency authorization. Other callable native utilities remain public fixtures;
they cannot use this registration path to obtain production authorization.

## What is reviewed and what stays blocked

The registration records fresh native lineage with no parents or external import.
Its mechanism is explicitly non-private: epsilon, delta, adjacency and accountant
are null, and privacy accounting is unsupported. It is not inserted into the
older temporal store that assumes an already justified privacy mechanism.

The protected unit and contribution bound are unresolved. Feature groups are
measurement units, not proven persons; person-level disjointness and population
representativeness are not established. The data and audit samples have been
used in earlier research. This is a new registered fit, not fresh independent
audit evidence or prospective confirmation of a scientific hypothesis.

The bundled Diabetes loader uses `scaled=True`: its upstream feature scaling
uses the full cohort before the native split. That existing profile is preserved
and the limitation is recorded in population and source metadata. The later
train-only scaler cannot undo it. Other upstream preprocessing is also not
qualified for agency use. Changing this recipe requires a separately registered
profile and comparison rather than silently relabeling the old result.

The utility rule is frozen before fitting: descriptive accuracy improvement over
the training-majority baseline for classification, or RMSE improvement over the
training-mean baseline for regression. The criterion is strict improvement above
zero on the frozen calibration plus audit rows. `met` is an engineering result,
not an approved agency threshold, subgroup qualification or significance claim.
Utility failure is retained alongside a successfully recorded review.

Every review remains `production_blocked`, with permanent reasons covering the
non-DP mechanism, unjustified protected unit, unqualified population and upstream
preprocessing, historical audit reuse, unreconciled external history, pending
agency approval and unverified production isolation. No metric can clear these
reasons. Recipient and intended production use are unassigned; the local fixture
operator is the only observed recipient of the local output files.

## Evidence links

The new candidate's eight numeric artifacts are independently replayed through
[PRD-12](production-prd12-authenticated-evidence.md). The current registration,
started history, artifacts and execution identity are bound into the replay job
and policy. The signed operation remains `retained_native_replay`: the signature
attests the fresh replay under an ephemeral fixture key, while the separate
registration ledger establishes trusted local pre-fit ordering. It is not an
original-training signature or platform attestation.

A current live verifier issues and consumes a one-use challenge. The workflow
does not accept caller-supplied admission JSON. Final completion rechecks artifact
hashes, code/data bindings, current key and expiry, then commits only if its
registration ticket still matches the agency/project history head. The completed
record includes the review payload and registration, candidate, report,
artifact-roster, signed-envelope and admission hashes. The event hash binds the
whole record, including the review. Later consumers must recheck mutable artifact bytes
against those retained hashes.

The replay ledger and registration ledger are separate transactions. A failure
between them can leave a consumed challenge and an incomplete registration; it
cannot turn that registration into a completed review. Recovery reconciles the
retained events and starts a new authorized attempt. No distributed transaction,
PRD-10 worker integration or automated recovery is claimed.

## History and concurrency

`RegistrationStore` is a bounded append-only SQLite event fixture with strict
schemas, global and agency/project hash chains, explicit creation and reopening
by expected store ID, file identity checks and a persistent clock high-water mark.
Each operation validates history and uses `BEGIN IMMEDIATE`; success is returned
after commit. Case or profile renaming cannot reset an agency/project history.
Registration, start and completion require the current scope head. A concurrent
registration or disclosure invalidates a stale ticket. Failure events can still
be appended after that conflict to retain the failed attempt.

The limits are 128 registrations, 1,024 total events, 256 known disclosures and a
16 MiB database. Capacity, corruption, missing events, schema changes, unsafe
paths and backwards committed time fail closed. Hash chaining is not protection
against a privileged administrator replacing the entire database and its anchor.
Agency-managed immutable history and independent rollback detection remain open.

The command records two known local file observations per completed profile:
model parameters and the review metrics. These are visible public fixture files,
not external model delivery, and they do not inventory every possible output or
historical disclosure. External history stays `unknown` even in an empty ledger.
Counts are not privacy cost and never reset or certify a cumulative privacy
budget. Agency-wide, cross-project/recipient historical reconciliation remains a
production requirement. Changing the project name does not justify a new budget.

## Run and retained evidence

From the D: government checkout:

```powershell
& .\.venv-pipeline\Scripts\python.exe -B scripts/rehearse_model_registration.py --output .local/registered-wine-v1
& .\.venv-pipeline\Scripts\python.exe -B scripts/rehearse_model_registration.py --all-profiles --data-root D:/model_audit_data --output .local/registered-eight-profiles-v1
& .\.venv-pipeline\Scripts\python.exe -B scripts/run_required_tests.py --profile government --output .local/required-prd13
```

Output must be a new ignored directory under this government's `.local/`. The
batch intent is written before any fit and commits all selected profiles and the
fixed recipe. The command retains registrations, start/completion events, numeric
artifacts, replay evidence, reviews, known file observations and safe failure
receipts. Keys remain memory-only and are retired after each completed profile;
public keys/signatures do not establish independent agency trust or recover a
live authority after exit. A missing profile or failed binding produces a nonzero
exit, not a silently smaller successful batch.

The milestone's validation receipt and logs are under
`.local/verification/prd13-registration-20261001/`. Tests exercise pre-fit durable
ordering, restart, corruption, concurrency, source changes, key revocation,
failure retention and refusal of arbitrary imports. The complete required
profile, fresh offline locked environment, repeated wheel build and isolated
installed-package runs are checked before reporting the milestone.

## Observed local results

On 1 October 2026, all eight public profiles completed newly registered fits and
authenticated replay, spanning **19,370 selected rows**. The ledger retained eight
registrations and sixteen known local file observations across forty events;
reopening it reproduced the same history. The source snapshot stayed unchanged.
Six models met the frozen descriptive utility rule. **BTS and TLC did not**:
their accuracy equaled the training-majority baseline. All eight reviews remain
production-blocked regardless of utility.

This covers the same eight runnable profiles identified in PRD-11, not every
academic dataset. Its broader 87-profile source inventory still has 79 unavailable
profiles; those entries are source profiles, not a count of distinct datasets.
Full research corpora and private agency data were not trained, and no new
dataset family or untouched audit sample is claimed.

The full required government profile passed **962 tests with zero skips,
failures or errors**. Another 35 runner/documentation checks passed; the Markdown
checker verified 61 inventories. These counts overlap where stated.

The **92 new registration tests** also passed with zero failures, errors or skips
in a fresh environment installed offline from the existing 31 hash-locked Windows
wheels. Review identified two boundary issues before final validation: live
authority now runs after final history replay, and local disclosure observations
use bounded regular-file reads with content-hash comparisons. Regression tests
cover both fixes.

## Production closure and next task

PRD-13 remains open for an approved agency model/use/recipient, justified
mechanism and protected population, agency utility and subgroup criteria, bounded
contributions, complete cumulative history with an appropriate accountant,
protected training custody, durable independent trust, rollback protection and
integration with authoritative jobs, approvals and release transactions. Private
data and arbitrary imported models remain unsupported. Local validation does
not establish production readiness, Linux execution or cloud isolation.

[PRD-14](production-prd14-sacro-adapter.md) now compares these exact retained
public candidates with a pinned external SACRO-ML probability-membership method.
Its separate frozen attack plan, positive/null controls and independent metrics
cover seven classifier profiles; Diabetes regression receives an explicit
unsupported result. It does not change this milestone's training registrations,
claim fresh scientific audit data or remove any production blocker.

The next planned task is **PRD-15**: authoritative registry/migrations and atomic
head/charge/outbox operations. GitHub publication remains pending authentication.
