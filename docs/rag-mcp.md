# Advisory retrieval and MCP integration

> **Status: Experimental.** In version 0.7 this integration runs from a source checkout because its knowledge index reads the repository's `docs/` and `schemas/` trees; the standalone wheel does not bundle that corpus.

MRA includes a deterministic local knowledge index and an experimental MCP server. Most operations
are advisory or read-only. Execution tools may train local models, launch a subprocess, write generated
artifacts under `output/`, and populate the ignored public-dataset cache under
`reproduction/public-privacy/raw/`. This layer helps reviewers locate protocol clauses, schemas, and
operational guidance. Retrieved passages and MCP responses are **not** evidence, assessment decisions,
authorizations, or activation instructions.

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

The server exposes `list_analyzer_services` and `list_red_team_tools` for read-only discovery of the
replaceable analyzer boundaries and prospective MCP tool names. It also exposes
`search_assurance_docs`, `get_schema`, `validate_assessment_request`, `review_model_coverage`,
`verify_audit_chain`, `run_experimental_model_audit`, `run_empirical_model_workflow`,
`read_privacy_audit_report`, `plan_privacy_audit`, and `run_rag_guided_privacy_audit`. It has no tools for
signing, authorizing, activating, revoking, committing portfolio state, or appending audit events.

The current server registers tools only and runs over stdio. It does not register MCP resources or
prompts, expose SSE or Streamable HTTP, or provide `trigger_failover` or
`run_perturbation_check`. Those are not aliases for any current capability, and no MCP client has a
direct path to signing, registry mutation, activation, suspension, revocation, or failover.

That tool list is an API statement, not a security boundary. The server also launches subprocesses
and trusted local model code; its operating-system principal can reach any PEM, SQLite, repository,
or credential path granted to that principal whether or not an MCP tool names it. A production
reviewer server must run non-root under a separate principal with no signing-key, writable
audit/registry, or deployment-credential access; mount only an approved read-only corpus/audit
snapshot, constrain egress, and route execution to a separately authenticated isolated worker.

### Training-control boundary

The server does not expose `model://training/...` or `model://export/...` resources, training-specific
prompts, or tools such as `halt_training_run`, `inspect_layer_gradients`, `trigger_model_export`, or
`verify_ai_verify_compliance`. It has no integration with a training scheduler, exporter, telemetry
store, IDE, desktop host, or pipeline auditor bot. Raw activations and gradients should not become
general-purpose MCP resources because they may expose training data, model intellectual property, or
credentials embedded in inputs.

A future privileged operation belongs in a separate authenticated operator service. An MCP reviewer
could at most submit a typed action request; the controller must enforce identity, role and tenant
scope, separation of duties, expected lifecycle state, human approval where required, idempotency,
audit receipts, deadlines, and cancellation. An MCP prompt may help draft a model card or summarize a
diagnostic report, but generated text is not a release contract, compliance decision, or control-plane
authorization.

The optional `run_empirical_model_workflow` tool accepts an experimental configuration, trains native
XGBoost and scikit-learn MLP classifiers on independently seeded synthetic datasets, and returns
disjoint-holdout metrics with familywise Bonferroni-corrected exact accuracy intervals. The contract
limits replicate, sample, and feature counts. Functional metrics remain screens, membership attack
measurements are unbound empirical floors, and the overall result always returns
`no_release_authorization`. A floor cannot block until it is converted or recollected through an
approved worker into a complete source-bound assessment request.

Those input-shape limits are not a complete resource sandbox: estimator hyperparameter dictionaries
and total tool runtime are not comprehensively bounded by the current MCP adapter. Keep this tool local
and trusted until a separately authenticated worker adds strict allowlists, CPU/memory quotas,
deadlines, cancellation, and output limits.

Each empirical replicate also runs a bounded red-team stage. A reference model trained on an
independent synthetic dataset freezes a loss-threshold membership attack before application to the
target model's members and holdout nonmembers. The stage also measures Gaussian feature corruption
and every single-feature occlusion. Membership results are simultaneous empirical floors but cannot
block until routed through a complete source-bound assessment request; robustness results are screens.
Neither can clear.

The empirical workflow additionally invokes the focused
[SACRO-ML-inspired red-team registry](sacro-ml-red-team.md): aggregate structural disclosure screens
and a repeated worst-case probability membership classifier with a dummy baseline and simultaneous
low-FPR bounds. The in-process estimator tools are discovery-visible but are not exposed as remote
calls until an attested inert-artifact worker contract exists.

`McpAnalyzerService` is a transport adapter for separately deployed analyzer servers. It intentionally accepts an invocation function instead of importing a particular MCP client implementation, keeping the assurance core independent of SDK lifecycle and transport choices. Requests and responses use contract version `2.0`; producer service/version and implementation/configuration digests are revalidated against the routed descriptor and active policy while the assessment engine retains all decision authority. Discovery metadata does not imply that every analyzer is already remotely deployed—the default registry uses local adapters and can be migrated service by service.

## Four-model experimental workflow

The sample manifest under `reproduction/model-audit-workflow/` binds executable toy CNN, LSTM,
additive-tree/XGBoost, and next-token/LLM artifacts. These models are deliberately tiny and synthetic;
they test orchestration and family routing, not production model quality or privacy.

```bash
python scripts/run_sample_model_audit_workflow.py
```

The workflow runs deterministic holdout inference, verifies every artifact hash, attaches RAG guidance,
and routes each model through the governed family catalog. Functional accuracy is reported as a screen
only. CNN and LSTM require dedicated workers; the XGBoost sample resolves to the `tree_ensemble`
catalog entry and reports recommended evidence routes, but it does not invoke the tree-linkage analyzer
or XGBoost audit worker. Interactive LLM clearance remains unsupported. Every result has
`can_clear: false`.

A focused XGBoost/MLP service workflow is also retained at
`reproduction/model-audit-workflow/xgboost-mlp-manifest.json`. It records every workflow stage and
routes execution through `mra.model-worker.xgboost` and `mra.model-worker.mlp`. Both workers publish
prospective MCP tools and can be replaced independently without changing the manifest or aggregation
semantics:

```bash
python scripts/run_sample_model_audit_workflow.py \
  --manifest reproduction/model-audit-workflow/xgboost-mlp-manifest.json \
  --output output/model-audit-workflow/xgboost-mlp-report.json
```

Run the real empirical training workflow with:

```bash
python scripts/run_empirical_xgboost_mlp_workflow.py \
  --config reproduction/model-audit-workflow/empirical-xgboost-mlp-config.json \
  --output output/model-audit-workflow/empirical-xgboost-mlp-report.json
```

On macOS, the native XGBoost wheel additionally requires the LLVM OpenMP runtime.

## Public-data privacy experiment

The `plan_privacy_audit` MCP tool retrieves family-specific requirements and limitations from the
hash-bound knowledge corpus and returns a versioned plan. `run_rag_guided_privacy_audit` freezes that
plan, launches the controlled worker, and rejects any report whose plan hash differs. The worker
downloads public MNIST, Adult Census,
and 20 Newsgroups data. It trains target/reference models on disjoint rows. The XGBoost pair shares a
preprocessor fitted on the union of its target and reference training rows, so its preprocessing is not
independent. A loss-based membership threshold is frozen using only the reference model's
disjoint calibration members/nonmembers, then evaluated against the target model's disjoint audit
population. The report retains raw losses and a one-sided exact 95% lower confidence bound.

```bash
python -m pip install -e ".[experiments,privacy-experiments]"
python scripts/run_public_privacy_audit.py
```

The MCP execution tool specifically looks for `.privacy-venv/bin/python` on Unix or
`.privacy-venv/Scripts/python.exe` on Windows. To use that tool, create that named environment and
install the same extras into it; an unrelated active virtual environment is not discovered.

```bash
python -m venv .privacy-venv
.privacy-venv/bin/python -m pip install -e ".[experiments,privacy-experiments]"
```

This remains an experimental attack study. Positive lower bounds may support blocking only after an
approved conversion or recollection binds them into a complete assessment request. Results at or near
chance are inconclusive and never establish privacy, and the MCP tool itself never blocks a release.

For remote deployment, add authenticated Streamable HTTP, per-tenant document filtering, request
size limits, rate limits, and an operational audit log before exposing the server. Do not reuse the
normative assurance-event chain as an untyped conversation log.
