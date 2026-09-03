# MLSys paper workspace

This directory is a drafting workspace, not a source of experimental evidence.
It turns the repository's current implementation, formal artifacts, and
retained results into a paper-ready structure without upgrading configured
experiments into completed results.

## Start here

1. Choose the paper's narrow thesis in the [paper outline](paper-outline.md).
2. Check every proposed statement against the
   [claims-to-evidence matrix](claims-to-evidence.md).
3. Use the [artifact index](artifact-index.md) as the only starting point for
   numbers, code, contracts, and reproduction entry points.
4. Before writing any result in past tense, complete the
   [experiment and reproducibility checklist](experiments-and-reproducibility.md).

The strongest supportable systems framing today is:

> Model Release Assurance is an offline, fail-closed reference system that
> represents a proposed release, its evidence, and its selection constraints as
> versioned contracts; keeps empirical attack floors separate from clearing
> ceilings; and makes ceiling soundness and decision usefulness separately
> auditable. Controlled exact-ground-truth evidence supports the finite-channel
> path, while a mixed public-data result exposes where a sound ceiling remains
> too loose to resolve a release. Production authorization and serving controls
> remain external.

That is a candidate framing, not a final title or an assertion that the system
is production-ready. The root [README](../README.md),
[project scope](../docs/project-scope.md), and normative
[MRAP/1.0 protocol](../docs/model-release-assurance-protocol.md) remain the
sources of truth.

## Evidence snapshot

| Paper component | Current maturity | What may be written now |
|---|---|---|
| Contracts, assessment/selection core, and offline protocol replay | Implemented reference core | Describe the design and implementation; reproduce tests at the paper commit before reporting outcomes. |
| Lean protocol model | Machine-checkable scoped formal artifact | State only the theorems and assumptions listed in the [formal verification boundary](../docs/formal-verification.md); rerun the pinned proof build for the paper artifact. |
| Controlled finite-channel ceiling validation | Completed, accepted experiment with exact ground truth | Report zero observed undercoverage across 1,200 primary analyzer replays, the simultaneous `0.015606` upper bound, perfect registered decision resolution, and interval tightening within the frozen controlled family. |
| Public-data model-backed ceiling validation v2 | Completed experiment; 8/9 registered criteria passed | Report zero observed undercoverage across 1,200 repeats and the failed raw Transformer-proxy usefulness criterion. Do not call the overall model-backed experiment accepted. |
| WildChat/EuroSAT training-hook study | Completed experimental execution with a committed, publication-safe audit | Report the audit's aggregate observations with its single-run and non-authorizing qualifications. |
| Five-model composition scaling | Configured secondary experiment | Describe the registered design only, as secondary or future evaluation. Do not report scaling results until complete child and suite manifests are retained and checked. |
| OpenML, stochastic portfolio, strategic assurance, and public-privacy studies | Registered designs or configured experiments | Use as evaluation plans or future work, not completed evidence. |
| Production registry, gateway, durable orchestration, and monitoring | Outside this repository | Present as an explicit deployment/refinement gap, never as implemented functionality. |

## Drafting convention

Use these labels in working prose and remove them only during the final claim
audit:

- `[SUPPORTED]`: backed by a named retained artifact or inspectable
  implementation.
- `[REPRODUCE]`: implemented, but a fresh result must be generated and retained
  at the paper commit.
- `[PLANNED]`: registered or configured; no completed result is retained.
- `[AUTHOR TODO]`: missing text, choice, citation, measurement, or artifact.
- `[NON-CLAIM]`: a boundary that must survive editing.

The labels deliberately separate three kinds of support: a software/design
claim, a machine-checked claim inside an abstract model, and an empirical
observation. None substitutes for the others.

## Candidate contribution set

Keep the final contribution list no broader than the evidence supports:

1. A contract-centered decomposition of model release into definition
   (contracts), offline evidence/selection pipelines, and an authorization
   workflow with an explicit external authority boundary.
2. Direction-aware, fail-closed decision semantics in which lower-bound attacks
   may block, clearing requires eligible upper evidence, and unresolved or
   mismatched evidence holds the release.
3. Hash-bound protocol replay plus a scoped Lean transition model for
   authorization integrity, ideal deployment, authenticated steps, and finite
   statistical accounting under stated premises.
4. A two-tier finite-channel evaluation: controlled exact-risk channels test
   coverage, tightness, decision resolution, replay, and tamper rejection; a
   completed model-backed study preserves the negative finding that the raw
   compact-Transformer proxy ceiling was sound but not reliably decisive.
5. A real-data integration case study covering training-time aggregate hooks on
   three language models and two vision architectures, reported only as
   execution, instrumentation, and descriptive screen evidence.

Treat the registered composition-scaling methodology as secondary design or
future evaluation until its run completes; do not use it as a headline
empirical contribution.

## Hard claim boundary

The current repository does not support claims of production authorization,
live gateway enforcement, complete model safety, general privacy clearance,
horizontal or multi-node scalability, production reliability, causal effects
of metadata, or universal coverage across model families. Legacy hook and
red-team runs remain screens and cannot be retroactively promoted. The new
model-backed study is decision-bearing only inside its frozen finite-pool game:
its counts came from an aggregate sampler and wrapper conformance was tested
separately, so it is not an end-to-end wrapper or serving result. Both ceiling
studies use experimental attack-battery waivers and grant no authorization.
See the [ceiling result report](ceiling-experiment-results.md), [production
roadmap](../docs/reference/production-roadmap.md), and completed hook audit's
[limitations](../docs/real-data-training-hook-audit-2026-09-02.md).

## Writing sources

- System and protocol: [architecture](../docs/architecture.md),
  [MRAP/1.0](../docs/model-release-assurance-protocol.md), and
  [integrated audit specification](../docs/system-audit-specification.md).
- Mathematics: [mathematical foundations](../docs/mathematical-foundations.md)
  and [formal verification](../docs/formal-verification.md).
- Empirical evidence: [ceiling experiment results](ceiling-experiment-results.md),
  [machine-readable ceiling summary](../reproduction/ceiling-experiment-summary.json),
  [real-data execution audit](../docs/real-data-training-hook-audit-2026-09-02.md),
  and the [reproduction maturity index](../reproduction/README.md).
- Related work: [privacy assurance review](../docs/literature-review.md) and
  [game-theory review](../docs/game-theory-literature-review.md). These are
  targeted narrative reviews, not systematic reviews.
- Test boundary: [test-suite guide](../tests/README.md).

No LaTeX toolchain is required for this workspace. Draft in Markdown first;
choose a venue template only after the story, claims, and retained artifacts
are frozen.
