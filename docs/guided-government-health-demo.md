# Government-health training-to-assessment demo

**Status:** Guide. The default run trains a real XGBoost model on a pinned
public medical benchmark and carries that candidate through the implemented
MRA evidence and assessment path. It is a teaching and integration run, not a
clinical validation, government approval, or deployment.

> **TRAINING DEMO — PUBLIC BENCHMARK — NOT PATIENT-CARE EVIDENCE — NOT
> AUTHORIZED — NOT ACTIVE.**

This is the primary end-to-end demo for users who need to see the pipeline,
not only prebuilt contracts. It connects:

1. a governed dataset snapshot;
2. an outcome-independent evidence plan frozen before the privacy result;
3. real target and reference XGBoost training with aggregate callbacks;
4. export and hashing of the candidate release bundle;
5. a post-plan membership test against that same candidate;
6. admission into a typed `AssessmentRequest`;
7. `AssuranceEngine` assessment; and
8. an MRAP transcript that stops at `ASSESSED`.

The expected disposition is **HOLD** (`inconclusive`) or **BLOCK**. The attack
is a statistical floor or screen: it may demonstrate enough risk to block, but
a weak attack cannot prove a ceiling. The demo deliberately does not invent a
`CLEAR`, local authorization, registry commit, activation, or deployment.

## The pipeline and the workflow

There are two nested lifecycles. The outer application pipeline includes data
preparation and model training. Normative MRAP starts at release registration;
it does not claim that every upstream training operation is an MRAP state.

```text
OUTER APPLICATION PIPELINE

purpose + data authority
        |
        v
snapshot + digest
        |
        v
freeze statistical design before outcomes
        |
        v
train target + reference XGBoost
        |
        +--> aggregate per-iteration hook telemetry (diagnostic only)
        |
        v
export deterministic bundle packaging + SHA-256
        |
        v

NORMATIVE MRAP PREFIX (wrapped by the outer application workflow)

REGISTERED (exact bundle)
        |
        v
approve the preregistered plan -> PLAN_FROZEN
        |
        v
execute that plan on the same target artifact
        |
        v
typed evidence adapter -------------> EVIDENCE_FROZEN
        |
        v
AssessmentRequest -> AssuranceEngine -> ASSESSED
                                      disposition: HOLD or BLOCK

STOP: no OPTIMIZED, COMMIT_PENDING, AUTHORIZED, or ACTIVE transition
```

The **pipeline** executes and binds the data, plan, training, export, attack,
and assessment stages. The **workflow** controls who may advance lifecycle
state. This repository can construct and replay the assessed prefix; a real
government deployment still needs external identities, separation of duties,
an atomic authorization registry, an enforcing serving gateway, and durable
monitoring and revocation.

## Run it

MRA requires Python 3.11 or newer. The actual-training demo uses the experiment
dependency tier because it imports XGBoost, scikit-learn, pandas, NumPy, SciPy,
PyArrow, and joblib.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock
python -m pip install -r requirements-experiments.txt
python -m pip install --no-deps --no-build-isolation -e .
make demo
```

`make demo` selects `openml-sick`. On its first run it may access OpenML to
obtain the pinned `sick`/thyroid dataset (OpenML dataset 38, version 1): 3,772
rows, 29 input features, and target `Class`. The expected retained snapshot
SHA-256 is
`be1206080af1fcccb5851ce31b9aab27c8e38631be6458a4e302301a6384158d`.
Acquisition must fail closed if the downloaded snapshot does not match its
registered identity.

For a fast, no-download integration run, use the public dataset packaged with
scikit-learn:

```bash
make demo DEMO_DATASET_PROFILE=sklearn-breast-cancer
```

Or invoke the runner directly:

```bash
PYTHONPATH=src python scripts/run_training_release_demo.py \
  --dataset-profile sklearn-breast-cancer \
  --run-dir output/training-release-demo/offline-example
```

The command prints its run directory. Read `START-HERE.md` first, then inspect
the machine-readable pipeline report and the plan, training, evidence,
assessment, and protocol artifacts beside it.

### Approved private input

The runner also accepts a local approved snapshot:

```bash
PYTHONPATH=src python scripts/run_training_release_demo.py \
  --dataset-path /approved/read-only/snapshot.parquet \
  --target-column approved_outcome \
  --run-dir /approved/write-once-results/mra-example
```

Use `--help` to review the local-data contract before running it. Do not put
private hospital data in the Git checkout, a shared shell history, CI, or the
public demo output directory. A government agency must run private input in an
approved protected environment with its own access, retention, legal-hold,
logging, and destruction controls. The public benchmark run is not evidence
about a private healthcare population.

## What each participant does

| Stage | Human owner | What the person checks | Executed output |
|---|---|---|---|
| 0. Purpose and authority | Programme owner, clinical authority, data steward | Intended use, prohibited use, legal authority, protected population, decision owner, and human override | Application use-case record; external to the model metric |
| 1. Dataset intake | Data steward | Source/version, target, row and feature counts, missing values, permissions, and snapshot digest | Dataset manifest and exact digest |
| 2. Plan freeze | Independent assessor and policy authority | Attack population, member/nonmember splits, threshold rule, confidence family, target false-positive rate, seeds, stopping rule, and tolerance | Outcome-independent preregistration before attack results |
| 3. Training | Model developer | Fixed configuration, disjoint splits, runtime identity, completion, and non-finite callback values | Actual target and reference XGBoost models plus aggregate training telemetry |
| 4. Export | Model owner | Exact model, preprocessor, manifest, and bundle contents | Candidate bundle and SHA-256 release identity |
| 5. Red-team evidence | Independent evidence worker | The registered attack ran after plan freeze and addresses the exported target, with calibration and audit partitions kept disjoint | Raw counts and confidence bounds, admitted only as a floor or screen |
| 6. Assessment | Independent assessor | Every release, policy, population, interface, game, source, plan, and artifact binding matches | Typed `AssessmentRequest` and `AssessmentReport` |
| 7. Workflow decision | Accountable authority | Whether the result is hold or block and what must be redesigned or recollected | MRAP transcript ending at `ASSESSED`; no authorization |

### Plain-language reading for clinicians and administrators

- **Training completed** means software fitted a model. It does not mean the
  model is clinically useful, fair, private, approved, or ready for care.
- **The hook ran** means the trainer recorded bounded aggregate learning
  telemetry. It helps diagnose execution and bind the run; it is not a privacy
  proof and does not retain patient rows or tensors.
- **The bundle hash matched** means later stages referred to the same exported
  bytes. It does not make those bytes safe.
- **The membership lower bound** estimates risk that the registered attack can
  already demonstrate. If its valid lower bound exceeds policy tolerance, the
  candidate is blocked.
- **An inconclusive attack** means “we cannot clear this release,” not “the
  attack found no problem.” Without an eligible ceiling over the complete
  release interface, the result remains on hold.

## Expected decision branches

| Engine result | Operator label | Meaning | Next action |
|---|---|---|---|
| `inconclusive` | **HOLD** | The admitted floor does not establish an above-tolerance leak, but no eligible ceiling proves risk is within tolerance. | Do not release. Redesign the release/interface or preregister and collect the missing decision-bearing ceiling evidence. |
| `block` | **BLOCK** | A valid lower bound is above the frozen tolerance for the exact candidate and game. | Do not release. Redesign, retrain, export a new candidate identity, and begin a new registered assessment. |

A successful command means the pipeline preserved these fail-closed semantics.
It does not mean the model passed.

## Binding checks that make this end to end

The report should let an auditor trace one candidate identity through every
stage:

- the dataset bytes match the dataset manifest;
- the outcome-independent plan predates the attack outcome;
- target and reference fitting use the registered, disjoint split identities;
- the training callback reports its expected boosting iterations and rejects
  non-finite diagnostics;
- the release bundle contains the exported target model and preprocessing
  artifacts, with deterministic archive construction and a recorded digest;
- the membership worker output names that candidate, plan, population,
  decision game, analyzer implementation, and configuration;
- the admitted typed analyzer input preserves raw successes, trials, false
  positives, nonmember trials, confidence family, and target FPR;
- the `AssessmentRequest` release contract names the same bundle SHA-256; and
- the MRAP transcript binds the resulting assessment report and stops at
  `ASSESSED`.

Changing a dataset, split, model parameter, preprocessor, model byte, evidence
plan, attack count, policy, or interface creates a different assessment object.
The operator must not carry forward an old result.

## Generated audit trail

The run directory includes these stable entry points:

```text
START-HERE.md
pipeline-report.json
contracts/release-contract.json
assessment/assessment-request.json
assessment/assessment-report.json
workflow/release-protocol-run.json
```

The machine report inventories the other dataset, plan, training, bundle,
telemetry, attack, and provenance artifacts with their relative paths and
SHA-256 digests. The release contract, every analyzer binding, the assessment
report, and the workflow transcript must all carry the same release-bundle
digest. A verifier or auditor should recompute those hashes rather than trust
the summary prose.

## What the experiment does and does not establish

The OpenML profile is useful because it is a real, non-synthetic medical
benchmark large enough to exercise preprocessing, missing values, categorical
features, training callbacks, export, and post-training evidence joins. It does
not establish representativeness for any hospital, clinical utility,
prospective performance, fairness, lawful processing, security, privacy of a
deployment, or fitness for patient care.

The scikit-learn profile exists for quick offline software testing. Its smaller
size changes statistical power and it is not a substitute for the pinned
OpenML run or an approved private-data study.

Neither profile supplies a decision-bearing complete-interface ceiling.
Therefore neither profile can produce a valid `CLEAR` through this demo.

## Secondary reference-only rehearsal

The older fixture suite is retained as a separate, secondary protocol
rehearsal:

```bash
make demo-reference
```

It uses checked-in generic synthetic evidence, includes hold/block/tamper and
mock registry/gateway/monitoring branches, and requires only core dependencies.
It does **not** train XGBoost and its fictional `ACTIVE` transcript is not a
production action. Use it to teach workflow failures after assessment; do not
use it as the training-to-release demo.

## Production controls still required

Before a real government-health release, evidence and controls outside this
repository must establish:

- lawful authority, purpose limitation, data minimization, retention, access,
  provider obligations, and affected-person rights;
- representative clinical validation, subgroup performance, calibration,
  prospective workflow evaluation, human factors, and safe fallback;
- independent security and privacy testing under approved preregistration;
- authenticated people and services with separation of duties;
- immutable evidence storage and a linearizable authorization/budget registry;
- a serving gateway that enforces the exact artifact, interface, controls,
  expiry, rate limits, budget, and revocation state;
- monitoring thresholds, incident ownership, suspension and revocation drills,
  contestability, communication, and retirement; and
- independent accreditation of the complete operating environment.

## Related material

- [Normative MRAP/1.0](model-release-assurance-protocol.md)
- [Integrated system audit specification](system-audit-specification.md)
- [Full software architecture](system-audit-specification.md#2-operational-model-contracts-pipelines-and-workflows)
- [Local XGBoost worker](xgboost.md)
- [Government-health XGBoost case study](../reproduction/README.md#evidence-boundary)
- [Production roadmap](system-audit-specification.md#production-readiness-exit-gates)
