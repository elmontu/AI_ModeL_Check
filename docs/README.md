# Documentation

This index separates the normative protocol, reference implementation, operating guides, experimental work, and research background for Model Release Assurance (MRA).

## Status labels

- **Normative** defines MRAP protocol requirements and conformance semantics.
- **Reference** explains the current design, guarantees, assumptions, or operational boundary.
- **Guide** gives procedures for using, extending, testing, or releasing the software.
- **Experimental** describes optional or research-stage capabilities that cannot authorize a release.

## Start here

- **Guide** — [Government-health training-to-assessment demo](guided-government-health-demo.md): one-command actual XGBoost target/reference training with aggregate hooks, deterministic bundle identity, post-plan same-artifact membership evidence, a typed `AssessmentRequest`, `AssuranceEngine` assessment, and an MRAP prefix ending `ASSESSED`. Its public medical benchmark is not clinical evidence; the outcome is hold or block, never local clearance or authorization. The older core-only fixture is retained as a secondary workflow rehearsal.
- **Reference** — [Integrated system architecture and MRAP audit specification](system-audit-specification.md): one standalone document covering the complete architecture, normative roles/messages/states/gates, current contracts and pipelines, evidence semantics, security/formal boundaries, production obligations, and audit checklist.
- **Reference** — [Project scope](project-scope.md): canonical purpose, repository layers, supported responsibilities, and explicit non-goals.
- **Reference** — [Architecture](architecture.md): complete runtime/container view, commands, analyzers, data and storage, training-to-serving integration, release contracts, deployment, CI/release automation, observability, trust, and failure behavior.
- **Normative** — [Model Release Assurance Protocol (MRAP/1.0)](model-release-assurance-protocol.md): roles, messages, states, gates, atomic authorization, enforcement, monitoring, and conformance levels.
- **Reference** — [Model-family coverage](model-family-coverage.md): executable family catalog, threat routing, portfolio rule, and the distinction between coverage and clearance.
- **Experimental** — [Finite-channel ceiling results](../paper/ceiling-experiment-results.md): generated paper-ready tables and figure for the accepted controlled experiment, preserved v2 negative predecessor, and accepted prospective corrective v3, with soundness, wrong-direction, margin, wrapper, resampling, and authority boundaries.
- **Experimental** — [Real-data training-hook execution audit (2026-09-02)](real-data-training-hook-audit-2026-09-02.md): curated aggregate results for the completed WildChat three-LLM and full-EuroSAT AlexNet/DenseNet-121 GPU runs, including metadata/context release consequences, bounded red-team screens, hashes, and non-claims.
- **Experimental** — [Five-model composition-scaling protocol](../reproduction/composition-scaling/README.md): registered three-scale, five-seed WildChat/EuroSAT matrix, matched hook/batch controls, same-population output composition, cross-modal portfolio boundaries, bounded execution, and completion rules.

## Protocol, contracts, and verification

- **Reference** — [Model-governance core](governance-core.md): institutional authority, accountable ownership, independent challenge, affected parties, contestation, lifecycle controls, and the boundary around strategic analysis.
- **Reference** — [Mathematical foundations](mathematical-foundations.md): decision problems, transfer conditions, statistical guarantees, portfolio composition, proofs, and open obligations.
- **Reference** — [Formally verified protocol core](formal-verification.md): Lean semantics, theorem inventory, trusted base, reproduction procedure, correspondence gap, and non-claims.
- **Reference** — [Protocol adversarial evaluation](protocol-evaluation.md): positive controls, unsafe transcript mutations, reproduction, and limits of the mutation score.
- **Guide** — [Protocol instantiation case studies](protocol-case-studies.md): bounded XGBoost, LLM, and authenticated-lifecycle examples with explicit claim boundaries.

Versioned machine contracts are indexed in [`schemas/README.md`](../schemas/README.md), and the Lean package has its own [`formal/lean/README.md`](../formal/lean/README.md).

## Using analyzers and integrations

- **Guide** — [Local XGBoost worker](xgboost.md): configure and run the local audit worker on trusted CSV/Parquet input and interpret its non-clearing evidence outside the trusted decision core.
- **Experimental** — [LLM watermark and canary testing](llm-watermark-canary.md): preregister output-watermark detection and synthetic training-data exposure audits.
- **Experimental** — [Advisory retrieval and MCP integration](rag-mcp.md): local hashed retrieval, MCP tools, service adapters, and experimental workflow boundaries.
- **Experimental/Reference boundary** — [SACRO-ML-inspired red-team tools](sacro-ml-red-team.md): exploratory structural-disclosure and membership tools, plus the reference attack-catalog/battery/positive-control contracts that let an approved isolated worker submit floor-or-screen results. No red-team component can clear or authorize.

Executable contract demonstrations are indexed in [`examples/README.md`](../examples/README.md). Optional benchmark and evidence-generation entry points are indexed in [`scripts/README.md`](../scripts/README.md).

## Governance, security, and deployment

- **Reference** — [Threat model](reference/threat-model.md): protected assets, actors, adversary knowledge, threats, controls, and non-claims.
- **Reference** — [Adaptation profiles](reference/adaptation-profiles.md): common baseline, domain and adopter profiles, release-specific configuration, and a public-sector health example.
- **Reference** — [Production roadmap](reference/production-roadmap.md): work required to turn the offline core into an accredited service.
- **Guide** — [Release process](releasing.md): versioning, validation, packaging, and GitHub release controls.

## Research and experimental assurance

- **Guide** — [MLSys paper workspace](../paper/README.md): manuscript draft, claims-to-evidence gate, artifact index, and experiment/reproducibility checklist; it is navigation for authors, not a new evidence source.
- **Experimental** — [Ceiling experiment reproduction index](../reproduction/README.md): retained controlled and versioned model-backed reports, preregistrations, manifests, aggregate replay rows, v2 acceptance failure, and v3 corrective pass.
- **Reference** — [Systems and privacy-assurance literature review](literature-review.md): primary research and critical positioning for ML release gates, assurance cases, provenance, formal kernels, membership, extraction, differential privacy, tree models, canaries, and watermarks.
- **Reference** — [Game-theory literature review](game-theory-literature-review.md): primary-source audit, security, and strategic-ML review with claim labels and transfer limits.
- **Experimental** — [Executable strategic assurance](strategic-assurance.md): optional exact-rational incentive stress tests that cannot make a governance decision or override a mandatory gate.

## Documentation maintenance

- **Reference** — [Documentation index](README.md): this page and its status taxonomy.

Draft manuscripts and paper-navigation aids belong only under [`paper/`](../paper/)
and remain narrative or derived artifacts, never independent evidence. The
repository does not retain third-party paper copies, office documents, or
presentation decks. Generated benchmark output belongs under `output/`, which
is excluded from version control, unless a deliberately selected,
publication-safe result is promoted with provenance and a hash manifest under
`reproduction/`.

New documentation must identify its status, avoid overstating assessment as authorization, and be linked from this index. Release history and migration notes belong in the root changelog rather than in duplicate version-specific documents.
