# SACRO-ML-inspired red-team tools

MRA's bounded empirical workflow includes an independent implementation inspired by
[AI-SDC/SACRO-ML](https://github.com/AI-SDC/SACRO-ML), reviewed at commit
`a94060ce85df52ac4b32d0b134f7afaa81af670d`. SACRO-ML is MIT licensed. Its useful
architectural patterns include a target abstraction, an extensible attack registry, repeated
post-training attacks, dummy baselines, structural disclosure indicators and standardized reports.

MRA does not import SACRO-ML or treat its risk summaries as authorization criteria. The exploratory
implementation emits no record-level membership probabilities and has no decision authority. A
separate reference contract path can accept results only from a policy-approved, content-addressed
attack battery; the trusted core may translate a valid adverse result into a blocking floor, but no
red-team result can clear or authorize a release.

## Tools

`StructuralDisclosureTool` reports aggregate train/test accuracy, generalization gap, a two-sample
loss-distribution test, learned parameter count, residual degrees of freedom, parameter-to-record
ratio, rounded-output equivalence-class sizes, near-zero class-probability disclosure indicators and
small predicted group-mass indicators. Observed-label homogeneity is retained under a separate metric
name. These are diagnostics, not calibrated privacy ceilings. In particular, equivalence classes are
defined by identical rounded probability vectors. Continuous model scores are commonly unique, so
the result is highly dependent on the declared rounding precision and must not be reported as a
calibrated k-anonymity guarantee or disclosure rate.

`WorstCaseMembershipTool` follows SACRO-ML's deliberately strong diagnostic scenario: it gives an
attack classifier probability outputs from target members and nonmembers, repeats disjoint
attack-train/audit splits, retains a permuted-label dummy baseline and reports AUC. It additionally
freezes a low-FPR threshold on attack-training nonmembers and uses simultaneous exact one-sided
bounds before labeling an operating point as attained. This threat model commonly overestimates a
real recipient because it assumes access to labeled member and nonmember outputs.

The permuted-label `dummy_auc` is a negative/null control. It is never accepted as the mandatory
positive control. A decision-bearing membership battery instead uses a preregistered known-leak
fixture with raw binomial counts; the trusted core recomputes its exact one-sided lower bound.

The pre-existing MRA shadow-loss attack remains separate. It trains a full reference model on an
independent synthetic dataset and freezes its threshold before target evaluation. Running both
guards against relying on one attack construction.

## Service boundary

The tools are registered as `mra.red-team.structural-disclosure` and
`mra.red-team.worst-case-membership`. They advertise prospective MCP tools
`red_team_structural_disclosure` and `red_team_worst_case_membership`. The current transport is
in-process because live estimator objects are not safe JSON payloads. A remote deployment must use
an attested isolated worker and exchange only a versioned inert target manifest, immutable artifact
references and aggregate reports; it must not deserialize an untrusted model inside the assurance
core.

`RedTeamToolRegistry.run` emits `ExploratoryRedTeamReport/2.0`, including the typed catalog and
configuration digests, timestamps, runtime identity, and `assessment_eligible: false`. It is not an
`AttackBatteryWorkerOutput` and therefore cannot be inserted into an assessment unchanged.

## Policy-bound assessment integration

Five public schemas define the in-band boundary:

- `attack-catalog-v1.json` fixes attack identity/version, implementation digest, applicability,
  metric, evidence role, positive-control kind, repetition floor, and `can_clear: false`.
- `attack-battery-configuration-v1.json` binds the catalog digest, every planned run, seeds,
  repetitions, stopping rule, resource limits, the currently supported equal-Bonferroni family,
  and positive-control plans. Unparameterized Holm/preallocated labels are rejected.
- `attack-positive-control-result-v1.json` carries raw control outcomes and the catalogued executor
  service, attack version, and implementation digest. Caller-supplied pass flags are not authoritative.
- `attack-battery-worker-output-v1.json` dispositions every run/control, binds the release, policy,
  artifact, interface, population, decision game, worker/runtime/image, isolation declaration, and
  retained raw-result digests, every run's catalogued executor identity, and hard-codes no clearance
  authority. The single worker identity is the battery orchestrator; heterogeneous executors do not
  have to impersonate it.
- `attack-battery-submission-v1.json` binds the catalog, configuration, worker output, evidence
  context, source, producer, and exact digests presented to the trusted core.

`PolicyBundle 3.0` names the exact required attack IDs and allowlists the complete catalog,
configuration, worker implementation/version/image, isolation level, and positive-control minimum.
The core also requires configuration freeze and worker execution to fall inside the catalog validity
window, and reparses the complete request at the engine boundary so validator-skipping model copies
cannot bypass these bindings.
The evidence observation must lie inside the worker execution interval. The engine checks the full
interval against policy/release/current-time bounds, while the input contract enforces elapsed
timeout, aggregate reported statistical trials, and canonical governed-output bytes. CPU and memory
remain declared budgets without independently observed telemetry; an isolated production worker must
enforce and attest them.
For each required attack, all frozen runs must succeed, controls must pass, the plan must be a
blocking-floor plan, and any low-FPR operating point must be attained under the complete-battery
multiplicity allocation. Missing artifacts are rejected; explicit failures, timeouts, weak controls,
screen-only plans, unsafe isolation, or missed operating points keep an otherwise clearing ceiling
`inconclusive`. A valid adverse lower bound above tolerance blocks.

The MCP server exposes only catalog discovery and structural `validate_attack_battery` checks.
Validation does not execute a model, authenticate a worker, verify an external isolation signature,
create evidence, or make a decision.

Catalog equality and canonical hashes provide structural integrity, not executor authenticity. The
declared-isolation profile is therefore an explicit lower-assurance mode. A production profile must
verify a protected workload signature or attestation over the exact worker output and its release,
policy, catalog, configuration, run/control identities, and raw-result hashes. The reference core
deliberately cannot satisfy a policy that requires external isolation attestation.

## Deliberate differences from SACRO-ML

- no direct dependency or copied serialization format;
- no record-level report output;
- exact simultaneous bounds supplement average attack metrics;
- attack floors require a policy-approved complete battery, passing positive controls, and the
  complete MRA assessment context before they may block;
- structural flags and unsuccessful attacks never clear;
- decision aggregation always remains outside the red-team worker.

This is a focused adaptation, not feature parity with SACRO-ML. SACRO-ML also contains LiRA, QMIA,
attribute-inference, instance-based and meta-attack implementations. MRA's independent shadow-loss
attack covers a different likelihood-style membership check; the other attack families remain
explicit extension points and are not claimed as implemented here.
