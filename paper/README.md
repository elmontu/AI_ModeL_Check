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
> ceilings; and replays a lifecycle whose production authorization and serving
> controls remain external.

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
| WildChat/EuroSAT training-hook study | Completed experimental execution with a committed, publication-safe audit | Report the audit's aggregate observations with its single-run and non-authorizing qualifications. |
| Five-model composition scaling | Configured experiment | Describe the registered design only. Do not report scaling results until complete child and suite manifests are retained and checked. |
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
4. A real-data integration case study covering training-time aggregate hooks on
   three language models and two vision architectures, reported only as
   execution, instrumentation, and descriptive screen evidence.
5. A registered composition-scaling methodology that permits empirical scalar
   composition only over shared protected-unit populations and otherwise keeps
   cross-modal results vector-valued. This remains a design contribution until
   the registered run is completed.

## Hard claim boundary

The current repository does not support claims of production authorization,
live gateway enforcement, complete model safety, general privacy clearance,
horizontal or multi-node scalability, production reliability, causal effects
of metadata, or universal coverage across model families. The completed model
runs are screens and cannot be retroactively promoted into decision-bearing
evidence. See the [production roadmap](../docs/reference/production-roadmap.md)
and the completed audit's [limitations](../docs/real-data-training-hook-audit-2026-09-02.md).

## Writing sources

- System and protocol: [architecture](../docs/architecture.md),
  [MRAP/1.0](../docs/model-release-assurance-protocol.md), and
  [integrated audit specification](../docs/system-audit-specification.md).
- Mathematics: [mathematical foundations](../docs/mathematical-foundations.md)
  and [formal verification](../docs/formal-verification.md).
- Empirical evidence: [real-data execution audit](../docs/real-data-training-hook-audit-2026-09-02.md)
  and the [reproduction maturity index](../reproduction/README.md).
- Related work: [privacy assurance review](../docs/literature-review.md) and
  [game-theory review](../docs/game-theory-literature-review.md). These are
  targeted narrative reviews, not systematic reviews.
- Test boundary: [test-suite guide](../tests/README.md).

No LaTeX toolchain is required for this workspace. Draft in Markdown first;
choose a venue template only after the story, claims, and retained artifacts
are frozen.
