# PRD-04: required CI profile and release gates

**Record:** PRD-04 / revision 0.1 / 1 October 2026.
**State:** `in_progress` — local implementation and validation; remote workflow
runs and required-check configuration remain pending authentication.
**Parent:** [production roadmap](production-private-cloud-plan.md).
**Input:** [PRD-03 source/build baseline](production-prd03-source-build-baseline.md).
Work stays in the D: government repository.
The prior baseline snapshot and receipts remain historical evidence of their
captured source; these CI changes form a later working-tree revision.

## Problem and resulting behavior

The previous API-enabled CI selection omitted `test_temporal_red_team.py`.
General discovery could find its tests but skip them when HTTP dependencies
were absent. Packaging also did not depend on the API-enabled bootstrap job.
A passing general suite therefore did not establish that the required temporal
screening endpoints had executed.

The [required-test runner](../scripts/run_required_tests.py) gives CI and the
release workflow one explicit government profile. It must discover actual tests
and pass every selected test. A missing module, empty suite, import error,
assertion failure, skip, expected failure or unexpected success makes this
profile fail; an expected failure is not a passing required control.

| Included test selection | Required coverage |
| --- | --- |
| `test_pipeline_workflow.py` | Source setup, case binding and workflow failure boundaries |
| `test_console.py` | Console jobs, queue and API behavior |
| `test_export_poc*.py` | Synthetic export protocol, mechanism, store, CLI, HTTP and tool surfaces |
| `test_government*.py` | Government review records, launch boundary and reference journey |
| `test_export_red_team.py` | Exact policy/report bindings, controls, evaluation and public pilot |
| `test_red_team_catalog.py` | Discovery and API contract |
| `test_temporal*.py` | Every temporal suite, including the required red-team HTTP checks |
| `test_infrastructure_plan.py` | Disabled provider-neutral intent and malformed/weakened-plan rejection (added in PRD-05) |
| `test_local_deployment_rehearsal.py` | Local rehearsal input, readiness and owned-process cleanup failure boundaries (added in PRD-05) |
| `test_production_identity_tokens.py` | Pinned JWT access-token signature, type, claims, scope and time failures (added in PRD-06) |
| `test_production_identity_policy.py` | Current authority, canonical people, case grants, revocation and atomic local review decisions (added in PRD-06) |
| `test_production_identity_api.py` | Signed HTTP requests, cross-case/self-approval denial and separate fixture boundary (added in PRD-06) |
| `test_production_storage_backend.py` | Immutable references, bounded safe fixture formats and filesystem substitution/tamper denial (added in PRD-07) |
| `test_production_storage_service.py` | Current workload permissions, exact single-use grants, expiry/revocation and retention decisions (added in PRD-07) |
| `test_production_storage_api.py` | Signed fixture storage HTTP, no arbitrary intake and no human raw reads (added in PRD-07) |
| `test_production_trust_registry.py` | Immutable key bindings, rotation/revocation, freshness, revision and clock failure controls (added in PRD-08) |
| `test_production_trust_signer.py` | Bounded provider signing, preflight validation and post-signing outage/expiry denial (added in PRD-08) |
| `test_production_trust_integration.py` | Real-signed token lifecycle, current saved reviews/grants and shared-clock/lock checks (added in PRD-08) |
| `test_production_build_artifacts.py` | Exact wheel bytes, bounded metadata, target dependency closure and SBOM/license inventory (PRD-09) |
| `test_production_build_evidence.py` | Complete advisory observations, signed context and source-bound test/build admission (PRD-09) |
| `test_production_build_cli.py` | Bounded public downloads, requirements drift and failure receipts (PRD-09) |
| `test_production_build_provenance_cli.py` | Actual source/wheel/evidence binding and explicit pending-license fixture result (PRD-09) |
| `test_production_jobs_store.py` | Durable lease/grant fences, process races, crash recovery, clock and custody refusal (PRD-10) |
| `test_production_jobs_service.py` | Current signed identity, exact job input/output, revocation and restart redaction (PRD-10) |
| `test_production_jobs_executor.py` | Fixed worker, bounded capture, owned-process timeout/cancellation and cleanup (PRD-10) |
| `test_production_jobs_rehearsal.py` | Real fixture workflow, retained failures, overwrite refusal and source stability (PRD-10) |
| `test_production_adapters_catalog.py` | Versioned research coverage inventory without inflated availability or training claims (PRD-11) |
| `test_production_adapters_datasets.py` | Bounded read-only prepared data, hashes, unsafe archive/type refusal and source drift (PRD-11) |
| `test_production_adapters_native.py` | Typed candidate, feature-group splits, controls, uncertainty and exact saved-candidate replay (PRD-11) |
| `test_production_adapters_cli.py` | Broader batch orchestration, explicit missing/failed profiles and retained evidence (PRD-11) |

Each selection must match modules, and each selected module must discover a
nonempty test set. The seven existing temporal modules are also named explicitly
so deleting one cannot silently reduce wildcard coverage. New temporal modules
join the profile automatically. Selection is checked again at the end so a
matching module added during execution cannot silently escape the run. Duplicate
test IDs and discovery problems are recorded rather than accepted as evidence
of coverage.

The broader Python/experiment suite still records legitimate optional-runtime
and platform skips. This strict profile has no skip allowlist: dependencies
required for these supported government paths must actually be present.
Future scope changes require review of the profile and its failure tests.

## Workflow enforcement

[CI](../.github/workflows/ci.yml) boots the console environment and runs the
profile on Windows and Ubuntu using Python 3.12. The distribution job depends on
that matrix as well as its existing proof, Python and demonstration jobs.

The [draft-release workflow](../.github/workflows/release.yml) runs the same
profile on both operating systems at the tag's source revision. Its release job
depends on that matrix and the formal job before building or drafting a release.
Release verification also installs the console/API dependencies for its broad
checks. It does not rely on an unrelated earlier branch run having passed.

A failed or skipped dependency prevents a dependent job from running under
GitHub's normal [job-dependency semantics](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idneeds).
Only evidence-upload steps use `always()`; packaging/release jobs do not receive
an exception that bypasses their failed prerequisites.

Each matrix run uploads only the profile's `tests.log` and `result.json`,
with a unique operating-system/run-attempt artifact name. An always-run guard
requires both files to be nonempty and the JSON receipt to parse with the
expected profile/status. Missing or malformed evidence fails the job. Upload is
still attempted after failures, including partial diagnostics, and enables only
these explicitly selected files beneath hidden `.local/`. The mechanism uses GitHub's
[workflow artifact support](https://docs.github.com/en/actions/tutorials/store-and-share-data);
it is not immutable agency evidence custody or a protected release attestation.

Existing public offline training and broader end-to-end, Python, proof and
package checks remain. No deployment, credentials, workflow dispatch, release
tag or remote repository setting is created by this change.

## Local invocation and evidence

From the government repository root, use the configured console environment:

```powershell
& .\.venv-pipeline\Scripts\python.exe -B scripts/run_required_tests.py --profile government --output .local/ci-required
```

Use a fresh output path for each attempt. The runner accepts only a new ignored
child of this repository's `.local/` directory, rejects escaping paths and
refuses to overwrite existing results. It never edits source or the Git index.

- Exit `0`: nonempty required profile passed without skips or tolerated failures.
- Exit `1`: discovery/test failure, with diagnostic evidence retained.
- Exit `2`: invalid invocation/output location; an existing destination stays intact.

The machine receipt records module/test identities and counts, skip/failure
details, interpreter and installed versions, source hashes and source ownership.
PRD-05 also binds the mandatory infrastructure blueprint before and after the
run: a missing, changed or deleted blueprint fails the profile. PRD-06 additionally
binds the mandatory runtime lock, including its new JWT-verifier dependency;
a missing or changed lock cannot yield passing evidence.
Those details distinguish execution of the current checkout from accidentally
importing an installed older package. They do not authenticate installed
dependency artifacts or replace PRD-09's production build controls. Keep actual
agency data and secrets out of these public/synthetic tests and CI artifacts.

The local PRD-04 validation receipt is retained under
`.local/verification/prd04-ci-20261001/`. It binds the exercised runner/workflow
sources, profile result, runner failure-regression tests, documentation checks
and parsed workflow dependency/artifact checks. Local YAML parsing and a Windows
test run cannot prove GitHub accepted the workflows or that hosted Ubuntu and
Windows jobs executed.

Observed locally on 1 October 2026: **318 required tests passed, zero skips**,
including all 17 temporal red-team tests. **28 runner/documentation tests**
passed, including injected dependency skips, import/empty-suite failures,
changed selection and overwrite rejection. Parsed workflow validation passed
86 structural and executable assertions, including 24 cases for the two
evidence guards. Documentation links and whitespace checks passed. These results
apply to the source hashes in the local receipt; they are not hosted CI results.

PRD-12 adds mandatory contracts/signing, durable replay-ledger, captured-byte
replay, admission and command suites. Production isolation refusal, changed
context, current revocation and one-use consumption are required checks.

[PRD-13](production-prd13-model-registration.md) adds required coverage for the
eight-profile source/manifest pins, exact registration and utility contracts,
durable history, registration before fitting, and the public rehearsal command.
Checks must reject arbitrary imports, changed source/sample or frozen-plan
bindings, stale history and reused reservations. Unknown external disclosure
history and unmet population/non-DP qualifications cannot become clearance.
These local checks do not close PRD-13's agency/scientific requirements.

[PRD-14](production-prd14-sacro-adapter.md) adds checks for the pinned external
SACRO-ML method, frozen settings, group/split lineage, positive and null controls,
independent metric replay and explicit unsupported scope. Missing dependencies,
changed runtime/input bytes, malformed reports and failed/timeout outcomes cannot
be hidden by native fallback or a silently reduced profile roster. Validation
must distinguish the seven applicable classifiers from unsupported Diabetes
regression and retain all three repetitions. The external runtime has its own
pinned dependency preparation; no local test result establishes cloud isolation,
scientific privacy clearance or complete dependency-license approval. The
[PRD-15 continuation](production-prd15-registry-transactions.md) adds registry and
atomic state tests; PRD-16 is the next planned implementation.

## Completion and handoff

Local implementation can be reviewed now. PRD-04 becomes `done` after authenticated
remote runs at the intended source commit show the required profile passing on
both supported operating systems, retained evidence is accessible, and the
relevant PRD-03 publication/review prerequisites are satisfied. No passing badge,
remote run URL or branch protection is inferred from local results.

After authentication, verify CI's `Pipeline setup (ubuntu-latest)` and
`Pipeline setup (windows-latest)` jobs and the package dependency chain at the
actual commit. Verify the release profile jobs at a separately approved tag when
the existing [release gates](releasing.md) permit one. Configure the agreed
required-check contexts in repository settings and test that a failing profile
blocks the intended merge/release path. The release workflow itself does not
configure branch protection.

Continue PRD-05 design within the provider-neutral decisions in
[PRD-02](production-prd02-threat-model.md). Provider/region selection and agency
approvals remain open; CI success authorizes neither private-data intake nor
cloud deployment.

## PRD-15 required registry coverage

The required profile now includes `test_production_registry_*.py`: strict fixed
contracts, explicit schema migration, atomic head/charge/receipt/outbox changes,
independent-process races/crashes, current signed authority during lock waits,
local receiver deduplication and preserved historical metadata. No skipped test
satisfies this gate. [PRD-15](production-prd15-registry-transactions.md) records the
local scope; PostgreSQL/cloud failover and real privacy accounting are unverified.
The next planned implementation is PRD-16, independent witness and recovery.

## PRD-16 required witness coverage

The required profile now includes `test_production_witness_*.py`: full registry
history, external own-log floors, irreversible intents, rollback/fork/new-ledger
refusal, CAS-only abort, process crashes/races, uncertain-commit reconciliation and
checkpoint-sink/current-token boundaries. [PRD-16](production-prd16-witness-recovery.md)
records local custody limits. Independent cloud custody, authenticated remote
observations and PostgreSQL recovery remain unqualified. Next is PRD-17.

PRD-17 adds `test_production_review_*.py` to the required profile for exact
policy/result binding, signed current authority, independent reviewers, scoped
delegation, retained history and post-result weakening/evidence-reuse denials.
See [the local review boundary](production-prd17-policy-review.md).

PRD-18 adds `test_production_delivery_*.py` for controlled public-fixture
activation/grants, current scoped recipients, exact-byte admission, interrupted
write observations, lifecycle revocation, checkpoint restore and HTTP/CLI
bypass denials. See [the controlled delivery boundary](production-prd18-controlled-delivery.md).

## PRD-19 end-to-end checks

The required profile includes test_production_profile_*.py: combined plans,
durable stage history, current evidence/time boundaries, runtime selection,
receipt crypto/archival replay and default-denied CLI. Portable integration tests
use explicit fictional external child probabilities with real native fits and
stores. Separate retained Windows rehearsals run the pinned SACRO worker; portable
checks alone cannot claim that execution. See [PRD-19](production-prd19-end-to-end-profile.md).

## PRD-20 operations checks

The required profile includes test_production_monitoring_*.py. Closed telemetry
schemas reject sensitive/free-form inputs; fault exercises cover worker, current
key trust, object integrity and uncertain ledger outcomes. Custody, outbox
restart/deduplication and guarded incident transitions remain local fixture
checks. See [PRD-20](production-prd20-monitoring-incidents.md); external SIEM and
independent agency response/custody acceptance remain pending.

## PRD-21 capacity and recovery checks

The required profile includes test_production_capacity_*.py. Fixed public
workload bounds and measured outcomes remain separate from performance targets.
Historical backup validation requires complete registry/witness equality and
externally retained pins; partial/stale restores and missing live delivery
contexts deny. See [PRD-21](production-prd21-capacity-recovery.md). Approved
agency-scale load, provider HA and independent restore acceptance are pending.

## PRD-22 assessment checks

The required government profile includes test_production_assessment_*.py.
Current signed local review, exact immutable blocker dispositions, fresh native
misuse probes and signed packet tamper/external-pin tests must pass without skips.
See [PRD-22](production-prd22-independent-assessment.md). These engineering checks
cannot substitute for appointed agency penetration testing or scientific acceptance.

## PRD-23 pilot-plan checks

The government required profile includes test_production_pilot_*.py. Strict
named scope, exact extracted evidence buffers, seven original current signed
participants, independent plan review and restricted lifecycle must pass without
skips. [PRD-23](production-prd23-restricted-pilot.md) remains planning-only;
agency pilot admission and acceptance require the outstanding production evidence.
