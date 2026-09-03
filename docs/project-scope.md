# Project scope

> **Status: Reference.** This document defines the repository's purpose and support boundary. It does not create a model-release authorization.

## Purpose

Model Release Assurance (MRA) has an offline, fail-closed Python reference core for validating model-release contracts, assessing evidence bound to a proposed release, selecting policy-compliant candidate configurations, and replaying Model Release Assurance Protocol (MRAP/1.0) transcripts and certificates. Optional evidence-lab workers may execute trusted local model code, launch subprocesses, or use the network; they remain experimental and non-authorizing.

MRA produces assessment recommendations, optimization reports, and replay results. These artifacts can inform a release process, but they are not permissions to deploy or serve a model.

## Repository areas

The repository contains one reference product and two supporting areas:

| Layer | Responsibility | Principal locations |
|---|---|---|
| Protocol and contracts | Define valid lifecycle behavior, messages, evidence shapes, and compatibility boundaries | `docs/model-release-assurance-protocol.md`, `schemas/`, `formal/` |
| Reference implementation | Validate, assess, select, sign, and replay offline artifacts | `src/model_release_assurance/`, `examples/`, `tests/` |
| Evidence lab | Exercise analyzers, generate experimental measurements and candidate evidence, and reproduce bounded studies | `scripts/`, `reproduction/`, experimental package modules |

This directory view maps to the operational model in the root README: protocol and contracts provide definition, the reference implementation and evidence lab run pipelines, and MRAP describes workflow semantics whose durable production orchestration remains external. The supported core verifies parts of that lifecycle offline; optional evidence-lab execution is a separate trust and dependency boundary. The repository is not a durable workflow orchestrator.

## In scope

- Versioned request, policy, evidence, report, manifest, and certificate contracts.
- Fail-closed evidence classification and assessment recommendations.
- Selection among submitted release configurations subject to utility, privacy, and portfolio constraints.
- Structural and authenticated replay of supplied MRAP lifecycle transcripts.
- Integrity helpers, signed non-authorizing manifests, and hash-chained local intent/terminal audit records with externally anchorable checkpoints.
- An abstract Lean model and machine-checked theorems under their stated assumptions.
- Model-family and threat routing that identifies required review without claiming clearance.
- Bounded, explicitly scoped analyzers—including the proof-obligation-heavy, model-family-neutral
  finite-channel floor/ceiling path—plus non-authorizing benchmark utilities and reproducibility
  materials.
- Optional advisory retrieval, MCP adapters, and experimental model-worker interfaces.

## Out of scope

- Issuing a production authorization or deciding that a model is safe in every deployment context.
- Operating authoritative identity, separation-of-duties, key-management, registry, budget, gateway, lease, monitoring, or revocation services.
- Loading arbitrary untrusted model binaries in the assessment core.
- Operating production training jobs, distributed-training controllers, checkpoint promotion,
  model-export or conversion pipelines, training telemetry, or serving telemetry stores.
- Providing durable scheduling, retries, checkpoints, human approvals, or distributed workflow recovery.
- Verifying that a submitter-declared interface is complete for the live deployment, inspecting all contents of a packaged model bundle, or issuing a gateway activation receipt.
- Providing a version-dispatched verifier for every retained historical schema; long-retention replay currently requires the matching released software/dependency/trust bundle.
- Treating model-family catalog coverage, a weak or unsuccessful attack, a watermark result, or a synthetic experiment as clearance evidence.
- Proving that Python code, infrastructure, cryptography, evidence collection, or a deployed service refines the Lean model.
- Replacing institutional governance, independent review, affected-party consideration, accreditation, or legal authority.

## Decision and authority boundary

The offline assessment engine returns per-threat and overall `clear`, `block`, or `inconclusive`
verdicts. The separate selection/optimization layer can recommend:

- `release_as_proposed`;
- `release_with_controls`;
- `redesign_required`; or
- `reject`.

Neither set of results is an MRAP lifecycle state. Only an external implementation of the authenticated authority, atomic portfolio registry, and enforcing gateway can create and activate a production authorization. Missing, stale, mismatched, underpowered, or unassessed evidence must remain non-clearing.

## Source-of-truth boundaries

- The [MRAP/1.0 protocol](model-release-assurance-protocol.md) is normative for the protocol roles, states, messages, gates, and conformance boundary.
- The Python models define the contracts accepted by the current reference implementation; committed current files in `schemas/` are their generated machine-readable exports. Superseded schemas preserve historical structure but are not executable compatibility promises by the current CLI.
- The Lean development proves properties of its explicitly scoped abstract model. It does not certify the Python implementation or a production deployment.
- Examples are executable demonstrations, not normative evidence.
- Scripts and reproduction materials are study tooling. Their presence does not establish that a study completed or that its outputs support a production claim.
- Release history and migration notes live in `CHANGELOG.md`; they do not override current contracts or documentation.

## Directory responsibilities

| Path | Repository contract |
|---|---|
| `src/model_release_assurance/` | Installable Python reference implementation and CLI |
| `schemas/` | Versioned current and compatibility JSON contracts |
| `formal/` | Abstract protocol semantics, proofs, and correspondence artifacts |
| `examples/` | Small inputs for supported commands and contract demonstrations |
| `tests/` | Unit, replay, integration, and bounded experiment tests |
| `docs/` | Normative, reference, guide, and experimental documentation |
| `scripts/` | Optional developer, benchmark, analyzer, and evidence-generation entry points |
| `reproduction/` | Retained study configurations and manifests; not generated results |
| `output/` | Generated local artifacts excluded from version control |

The supported operating interfaces are the `mra` CLI and the versioned contracts. Python imports are supported only when explicitly documented; a module or script is not automatically a stable API because it is importable. Experimental features must retain explicit non-authorization and evidence-direction boundaries when they are moved behind another transport or service.

## Python package boundaries

The package remains physically flat for compatibility, but its modules have four distinct owners:

| Logical group | Modules | Responsibility |
|---|---|---|
| Assessment core | `models`, `engine`, `decision`, `model_coverage`, `analyzers`, `services` | Contracts, evidence classification, analyzer dispatch, and fail-closed recommendations |
| Selection and certificates | `optimizer`, `decision_theory`, `portfolio*`, `incomplete_portfolio`, `protocol_feasibility`, `strategic_assurance` | Configuration selection and replayable mathematical artifacts |
| Protocol integrity | `release_protocol`, `integrity`, `audit` | Transcript replay, signatures, hashes, and local audit-chain integrity |
| Evidence lab | `knowledge`, `mcp_*`, `experimental_workflow`, `empirical_workflow`, `privacy_orchestration`, `red_team` | Source-checkout integrations, empirical workers, and research-stage orchestration |

Moving these modules into new subpackages would change imports, tests, script dependencies, and hash-bound reproduction records. Do that only in a planned API migration with compatibility shims and updated integrity manifests; use these logical groups for navigation until then.

## Naming

Use **MRA** for the offline supported core and its explicitly labelled evidence-lab extensions, and **MRAP/1.0** for the larger model-release lifecycle protocol. Avoid describing the repository as a production authorization service, deployment gateway, or complete workflow platform.
