# SACRO-ML-inspired red-team tools

MRA's bounded empirical workflow includes an independent implementation inspired by
[AI-SDC/SACRO-ML](https://github.com/AI-SDC/SACRO-ML), reviewed at commit
`a94060ce85df52ac4b32d0b134f7afaa81af670d`. SACRO-ML is MIT licensed. Its useful
architectural patterns include a target abstraction, an extensible attack registry, repeated
post-training attacks, dummy baselines, structural disclosure indicators and standardized reports.

MRA does not import SACRO-ML or treat its risk summaries as authorization criteria. The local
implementation preserves MRA's source-binding, evidence-direction and fail-closed rules, emits no
record-level membership probabilities, and cannot clear or directly block a release.

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

## Deliberate differences from SACRO-ML

- no direct dependency or copied serialization format;
- no record-level report output;
- exact simultaneous bounds supplement average attack metrics;
- attack floors require the complete MRA assessment context before they may block;
- structural flags and unsuccessful attacks never clear;
- decision aggregation always remains outside the red-team worker.

This is a focused adaptation, not feature parity with SACRO-ML. SACRO-ML also contains LiRA, QMIA,
attribute-inference, instance-based and meta-attack implementations. MRA's independent shadow-loss
attack covers a different likelihood-style membership check; the other attack families remain
explicit extension points and are not claimed as implemented here.
