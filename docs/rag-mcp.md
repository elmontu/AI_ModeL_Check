# Advisory retrieval and MCP integration

MRA includes a deterministic local knowledge index and a read-only MCP adapter. This layer helps
reviewers locate protocol clauses, schemas, and operational guidance. Retrieved passages and MCP
responses are **not** evidence, assessment decisions, authorizations, or activation instructions.

## Local retrieval

`KnowledgeIndex.build(repository_root)` indexes Markdown below `docs/` and versioned JSON contracts
below `schemas/`. Each result carries its source path, section, source SHA-256 digest, chunk digest,
and score. The BM25-style ranking is local, deterministic, and requires no external embedding API.

Run the labeled retrieval evaluation with:

```bash
python scripts/evaluate_knowledge_retrieval.py --output output/rag/retrieval-evaluation.json
```

## MCP server

Install the optional current MCP Python SDK, then run the local stdio server from the repository root:

```bash
python -m pip install "mcp>=2,<3"
python -m model_release_assurance.mcp_server --repository-root .
```

The server exposes only `search_assurance_docs`, `get_schema`,
`validate_assessment_request`, `review_model_coverage`, `verify_audit_chain`, and
`run_experimental_model_audit`, `read_privacy_audit_report`, `plan_privacy_audit`, and
`run_rag_guided_privacy_audit`. It has no tools for
signing, authorizing, activating, revoking, committing portfolio state, or appending audit events.

## Four-model experimental workflow

The sample manifest under `reproduction/model-audit-workflow/` binds executable toy CNN, LSTM,
additive-tree/XGBoost, and next-token/LLM artifacts. These models are deliberately tiny and synthetic;
they test orchestration and family routing, not production model quality or privacy.

```bash
python scripts/run_sample_model_audit_workflow.py
```

The workflow runs deterministic holdout inference, verifies every artifact hash, attaches RAG guidance,
and routes each model through the governed family catalog. Functional accuracy is reported as a screen
only. CNN and LSTM require dedicated workers, the XGBoost sample routes to the existing tree workflow,
and interactive LLM clearance remains unsupported. Every result has `can_clear: false`.

## Public-data privacy experiment

The `plan_privacy_audit` MCP tool retrieves family-specific requirements and limitations from the
hash-bound knowledge corpus and returns a versioned plan. `run_rag_guided_privacy_audit` freezes that
plan, launches the controlled worker, and rejects any report whose plan hash differs. The worker
downloads public MNIST, Adult Census,
and 20 Newsgroups data. It trains independent target/reference CNN, LSTM, XGBoost, and compact
Transformer models. A loss-based membership threshold is frozen using only the reference model's
disjoint calibration members/nonmembers, then evaluated against the target model's disjoint audit
population. The report retains raw losses and a one-sided exact 95% lower confidence bound.

```bash
python -m pip install -e ".[experiments,privacy-experiments]"
python scripts/run_public_privacy_audit.py
```

This remains a bounded attack study. Positive lower bounds may block; results at or near chance are
inconclusive and never establish privacy.

For remote deployment, add authenticated Streamable HTTP, per-tenant document filtering, request
size limits, rate limits, and an operational audit log before exposing the server. Do not reuse the
normative assurance-event chain as an untyped conversation log.
