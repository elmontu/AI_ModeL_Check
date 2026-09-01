# Documentation

This directory contains operational and engineering documentation for the MRA reference implementation.

## Start here

- [Normative MRAP/1.0 protocol](model-release-assurance-protocol.md): roles, messages, states, gates, atomic authorization, enforcement, monitoring, proofs, and conformance boundary.
- [Formally verified protocol core](formal-verification.md): Lean semantics, theorem inventory, finite statistical bound, trusted base, reproduction, correspondence gap, and non-claims.
- [Protocol adversarial evaluation](protocol-evaluation.md): positive controls, unsafe transcript mutations, reproduction, and limits of the mutation score.
- [Protocol instantiation case studies](protocol-case-studies.md): reproducible XGBoost, LLM, and authenticated-lifecycle examples with claim boundaries.
- [Architecture](architecture.md): components, data flow, trust boundaries, and package map.
- [Model-governance core](governance-core.md): institutional authority, accountability, independent challenge, affected parties, contestation, lifecycle, and the boundary around strategic stress tests.
- [Mathematical foundations](mathematical-foundations.md): Bayesian release decisions, optional strategic stress tests, theorems, proofs, statistical guarantees, implementation correspondence, and non-claims.
- [Game-theory literature review](game-theory-literature-review.md): primary-source audit/security/strategic-ML review, claim ledger, transfer limits, hallucination controls, and the deliberately limited role of strategic stress testing in governance.
- [Executable strategic assurance](strategic-assurance.md): optional exact-rational incentive stress tests, provenance validation, pessimistic ties, adversarial tests, and the seeded synthetic experiment.
- [Threat model](reference/threat-model.md): protected assets, actors, adversary knowledge, threats, and controls.
- [Adaptation profiles](reference/adaptation-profiles.md): whole-of-government baseline and adopter-specific configuration.
- [Production roadmap](reference/production-roadmap.md): work required to deploy the offline core as an accredited service.
- [Release process](releasing.md): versioning, validation, packaging, and GitHub release controls.
- [All-model coverage](model-family-coverage.md): executable family catalog, threat routing, portfolio rule, and honest support boundary.
- [MRA 0.6 update](model-release-assurance-0.6-update.md): corrigendum to the supplied 0.5 framework specification.
- [Local XGBoost worker](xgboost.md): train and audit trusted CSV/Parquet classification data.
- [LLM watermark and canary testing](llm-watermark-canary.md): preregister output-watermark detection and synthetic training-data exposure audits.
- [Privacy-assurance literature review](literature-review.md): primary research on membership inference, extraction, differential privacy, tree ensembles, LLM canaries, and text watermarking.
- [Literature-driven check critique](check-critique-2026-08-22.md): refreshed check-by-check assessment, implemented improvements, limitations, and remaining priorities.
- [Framework audit (2026-08-22)](audit-2026-08-22.md): prioritized correctness, provenance, security, testing, and reproducibility findings.

## Documentation policy

The repository does not contain copies of papers, publication drafts, generated academic study reports, office documents, or presentation decks. A targeted literature review may document the primary evidence and limitations behind framework requirements. Generated benchmark output belongs under `output/`, which is excluded from version control. Documentation should explain how to install, operate, integrate, secure, evaluate, or contribute to the software.

Versioned machine contracts live in [`schemas/`](../schemas/), and executable examples live in [`examples/`](../examples/).
