# Documentation

This index separates the normative protocol, reference implementation, operating guides, experimental work, and research background for Model Release Assurance (MRA).

## Status labels

- **Normative** defines MRAP protocol requirements and conformance semantics.
- **Reference** explains the current design, guarantees, assumptions, or operational boundary.
- **Guide** gives procedures for using, extending, testing, or releasing the software.
- **Experimental** describes optional or research-stage capabilities that cannot authorize a release.

## Start here

- **Reference** — [Integrated system architecture and MRAP audit specification](system-audit-specification.md): one standalone document covering the complete architecture, normative roles/messages/states/gates, current contracts and pipelines, evidence semantics, security/formal boundaries, production obligations, and audit checklist.
- **Reference** — [Project scope](project-scope.md): canonical purpose, repository layers, supported responsibilities, and explicit non-goals.
- **Reference** — [Architecture](architecture.md): complete runtime/container view, commands, analyzers, data and storage, training-to-serving integration, release contracts, deployment, CI/release automation, observability, trust, and failure behavior.
- **Normative** — [Model Release Assurance Protocol (MRAP/1.0)](model-release-assurance-protocol.md): roles, messages, states, gates, atomic authorization, enforcement, monitoring, and conformance levels.
- **Reference** — [Model-family coverage](model-family-coverage.md): executable family catalog, threat routing, portfolio rule, and the distinction between coverage and clearance.

## Protocol, contracts, and verification

- **Reference** — [Model-governance core](governance-core.md): institutional authority, accountable ownership, independent challenge, affected parties, contestation, lifecycle controls, and the boundary around strategic analysis.
- **Reference** — [Mathematical foundations](mathematical-foundations.md): decision problems, transfer conditions, statistical guarantees, portfolio composition, proofs, and open obligations.
- **Reference** — [Formally verified protocol core](formal-verification.md): Lean semantics, theorem inventory, trusted base, reproduction procedure, correspondence gap, and non-claims.
- **Reference** — [Protocol adversarial evaluation](protocol-evaluation.md): positive controls, unsafe transcript mutations, reproduction, and limits of the mutation score.
- **Reference** — [Post-critique design-control validation](../reproduction/design-control-validation/README.md): retained raw outcomes for twelve targeted implementation regressions and the open binary64 boundary diagnostic.
- **Guide** — [Protocol instantiation case studies](protocol-case-studies.md): bounded XGBoost, LLM, and authenticated-lifecycle examples with explicit claim boundaries.

Versioned machine contracts are indexed in [`schemas/README.md`](../schemas/README.md), and the Lean package has its own [`formal/lean/README.md`](../formal/lean/README.md).

## Using analyzers and integrations

- **Guide** — [Local XGBoost worker](xgboost.md): configure and run the local audit worker on trusted CSV/Parquet input and interpret its non-clearing evidence outside the trusted decision core.
- **Experimental** — [LLM watermark and canary testing](llm-watermark-canary.md): preregister output-watermark detection and synthetic training-data exposure audits.
- **Experimental** — [Advisory retrieval and MCP integration](rag-mcp.md): local hashed retrieval, MCP tools, service adapters, and experimental workflow boundaries.
- **Experimental** — [SACRO-ML-inspired red-team tools](sacro-ml-red-team.md): structural-disclosure and worst-case-membership tools; the enclosing empirical workflow separately adds corruption and occlusion screens. None has clearance authority.

Executable contract demonstrations are indexed in [`examples/README.md`](../examples/README.md). Optional benchmark and evidence-generation entry points are indexed in [`scripts/README.md`](../scripts/README.md).

## Governance, security, and deployment

- **Reference** — [Threat model](reference/threat-model.md): protected assets, actors, adversary knowledge, threats, controls, and non-claims.
- **Reference** — [Adaptation profiles](reference/adaptation-profiles.md): common baseline, domain and adopter profiles, release-specific configuration, and a public-sector health example.
- **Reference** — [Production roadmap](reference/production-roadmap.md): work required to turn the offline core into an accredited service.
- **Guide** — [Release process](releasing.md): versioning, validation, packaging, and GitHub release controls.
- **Reference** — [Operational-reference index](reference/README.md): index for the deployment-oriented reference documents.

## Research and experimental assurance

- **Reference** — [Privacy-assurance literature review](literature-review.md): primary research behind the membership, extraction, differential-privacy, tree, canary, and watermark evidence semantics.
- **Reference** — [Game-theory literature review](game-theory-literature-review.md): primary-source audit, security, and strategic-ML review with claim labels and transfer limits.
- **Experimental** — [Executable strategic assurance](strategic-assurance.md): optional exact-rational incentive stress tests that cannot make a governance decision or override a mandatory gate.

## Documentation maintenance

- **Reference** — [Documentation index](README.md): this page and its status taxonomy.

The repository does not retain copies of papers, publication drafts, generated academic study reports, office documents, or presentation decks. Targeted reviews may document the primary evidence and limitations behind framework requirements. Generated benchmark output belongs under `output/`, which is excluded from version control.

New documentation must identify its status, avoid overstating assessment as authorization, and be linked from this index. Release history and migration notes belong in the root changelog rather than in duplicate version-specific documents.
