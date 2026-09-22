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
replaceable analyzer boundaries and the typed red-team catalog. `validate_attack_battery` performs
non-authorizing structural and digest-binding validation of an inert submission. The server also exposes
`list_export_constructions`, `inspect_export_bundle`, `read_export_history`, `plan_model_export`,
`search_assurance_docs`, `get_schema`, `validate_assessment_request`, `review_model_coverage`,
`verify_audit_chain`, `run_experimental_model_audit`, `run_empirical_model_workflow`,
`read_privacy_audit_report`, `plan_privacy_audit`, and `run_rag_guided_privacy_audit`. It has no tools for
signing, authorizing, activating, revoking, committing portfolio state, or appending audit events.

### Synthetic model-export diagnostics

The export POC has a small shared tool service at
`model_release_assurance.export_poc.tools.ExportToolService`. Its public catalog function,
`export_construction_catalog()`, is shared by CLI, HTTP discovery and MCP so each interface states the
same capabilities. These are diagnostic operations; no MCP operation prepares an export, commits a
disclosure, downloads a model, or revokes download access.

| Tool | Input | Result and boundary |
| --- | --- | --- |
| `list_export_constructions` | None | Versioned `mra-export-poc-constructions-v1` catalog, mechanism-source SHA-256, fixed fixture and protected unit, two-stage limit, and three alternative second-stage constructions. Does not sample a mechanism or train a model. |
| `inspect_export_bundle` | `model_json`: exact UTF-8 JSON text | Strict export-field allowlist, declared metadata and SHA-256 of the supplied text's exact UTF-8 bytes. Duplicate keys, private fields, false metadata and oversized bundles are rejected. A valid schema does not authenticate the producer or attest privacy. |
| `read_export_history` | `data_directory`: existing directory within the configured repository root; relative paths resolve there | Consistent read-only snapshot verification of an existing `export.sqlite3`, source binding, history ratios and public consistency summary. Missing stores are not initialized. Retained private state and uncommitted artifact bytes/hashes are not returned. |
| `plan_model_export` | `data_directory`: same confined existing history; `route`: `first`, `reuse`, `retained-state`, `independent`, or `central-count` | Versioned `mra-export-poc-plan-v1` plan from a validated public-status snapshot: stage compatibility, current/proposed privacy bounds, accounting method and required private access. Never runs training, draws noise, stages a candidate, or grants export authority. |

The four export tools use the same construction description and, for history operations, a shared
confinement check covering the database, optional WAL and history marker. `plan_model_export` is
implemented by `ExportToolService.plan_export(data_directory, route)` and the pure
`export_poc.protocol.plan_export(status, route)` planner. `ready: true` only means the snapshot's
stage permits that route. It does not establish current authority, retained-state availability, model
utility or permission to release. A live producer must still check the current revision and construct
and commit the actual artifact. Missing history is an error, not permission to reset privacy cost.
An incompatible stage or unknown route yields a blocked plan with no proposed privacy bound.
Planning does not return private state or staged model bytes.

The retained-state plan uses a certificate for the complete joint history; its apparent increase
from ratio 2 to ratio 4 must not be interpreted as an independent per-stage log(2) guarantee. The
independent and central-count routes do use sequential composition. `reuse` proposes retrieving the
identical latest committed artifact without new noise, new training or a privacy-budget refund;
a revoked latest artifact blocks this route. Reusing protected data for new training is a broader
post-processing principle, not an implemented general trainer.

For a receipt comparison, pass the original decoded UTF-8 file text to `inspect_export_bundle`,
preserving whitespace and its trailing newline. Passing a reserialized object changes the digest.
The digest is neither a normalized-JSON hash nor evidence that those bytes came from the trusted
constructor. The history reader copies existing database/WAL bytes into a private temporary snapshot
for SQLite verification; it does not create or change database sidecars in the source directory. A
changing history can be rejected as busy, and a verified snapshot may immediately become stale. It
is never a substitute for the operator's atomic commitment check.

All implemented constructions use one fixed synthetic public roster and public group membership.
The first stage has a sufficient pure-DP history ratio of 2; one alternative second stage extends
the bound to 4 (epsilon is the natural logarithm of the ratio, delta is zero). Retained-state and
independent randomized-response channels have exact finite checks. The central-count baseline uses
the standard sensitivity-one two-sided geometric mechanism and composition. These are three
alternative extensions of one first release, not three additional exports under the same ratio-4
bound. Opening another directory cannot reset actual citizen exposure.

The fitted model is a group Bernoulli forecast. No arbitrary model upload, agency-data adapter,
general DP-SGD trainer, or production privacy certificate is supplied. The catalog separates these
implemented mechanisms from the manuscript's broader protected-data reuse, joint-extension and
direct-private-training routes. Unchanged-model reuse retrieves existing bytes rather than adding
another broker stage. The finite channel's 11/15 answer accuracy is not model accuracy, and
synthetic results do not establish a retained-state utility advantage.

The mechanism-source digest pins the producer used by a store. An implementation mismatch is an
explicit migration/review condition; these tools do not rewrite an old binding or reset its history.
Local hashes detect corruption and inconsistency but do not prevent a privileged owner from
rewriting the database and hashes together. Source-path confinement likewise does not replace
process isolation or private-state custody. The MCP SDK is optional: service and registration tests
using an inert adapter do not establish SDK transport interoperability or an agency deployment.

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

The separate `scripts/run_llm_training_hook_audit.py` evidence-lab worker does
not widen this MCP surface. It downloads the WildChat-4.8M object
`data/train-00000-of-00086.parquet` at pinned revision
`c827c6df8fcf008219ffaffa4d1dd77491099367`, without remote code, and verifies
its SHA-256
`6df660dca78dd92b865bef09b928992ceb6c913b4f06082315876a5997ad2eaa`,
125,527,585-byte size, and 37,208-row count. It projects non-empty first
user/assistant pairs only from English, `toxic=false`, `redacted=false` rows,
excludes the registered sensitive source columns, and removes exact duplicate
pairs. These filters minimize the input; they do not guarantee that dialogue
is harmless, deidentified, or legally cleared.

The exact 14,962-byte dataset card and 19,947-byte license file are also
digest-bound governance inputs. Each model loads only from its already verified
local artifact set with `local_files_only=true`, remote code disabled, and no
credential token. That loader flag is not OS-level network isolation; an
enforced egress boundary remains an external worker control. Pre-tokenization
UTF-8 limits and a verified prefix-only tokenizer special-token policy bound
the completion-only formatting and masking behavior.

The worker selects the same deterministic 8,192 training rows and untouched
1,024-row holdout for revision-pinned DistilGPT2, OPT-125M, and Pythia-160M.
Each fresh model runs sequentially for 512 optimizer steps, and its holdout is
evaluated before and after without controlling tuning, stopping, or selection.
Removable model-specific first/last-block hooks emit only bounded aggregate
finite fractions, norms, and maxima; raw prompts, token IDs, activations,
gradients, parameters, outputs, and tensors are forbidden from telemetry and
reports. Run it directly with:

```bash
python scripts/run_llm_training_hook_audit.py \
  --config reproduction/llm-training-hook/config.json
```

Every invocation uses a fresh ignored `run-YYYYMMDDTHHMMSS-ffffffZ` directory
and separate `training-telemetry-{model_key}.jsonl` streams, with verified
downloads held in the sibling `cache/` directory. `RUN_COMPLETE.json` is
published last and binds the complete registered report and telemetry set; a
directory without it is incomplete. Its JSON, Markdown, and JSONL artifacts
always declare
`no_release_authorization` and are not MCP resources, assessment evidence,
production telemetry, or workload attestation. A production controller must
independently authenticate and isolate any training worker and exchange inert,
policy-approved aggregate artifacts rather than tensors.

Its before/after, model-specific context-risk lattices are similarly advisory.
Equal-prior, candidate-metadata, candidate-loss, and combined metadata/loss
results use disjoint 256-member/256-nonmember calibration and audit cells and
are intentionally descriptive screens with no statistical-power claim. Plain
text-only generation realizes only the prior view. K1 becomes realizable only
when all six exact source/preprocessing metadata fields are exposed. K2
requires arbitrary-candidate continuation scoring or white-box access;
generated-token-only log probabilities are insufficient. K3 requires both K1
and K2 preconditions, and white-box assessor access does not imply recipient
access. Differences across profiles,
checkpoints, or models are noncausal and need not be monotone. Exact
training-roster access is different: a manifest lookup reveals membership
directly. The public experiment can reconstruct this roster internally, but
the roster itself must never become an MCP resource or implied recipient
surface. If a real protected roster is exposed through any release, local,
administrative, log, or metadata path, the membership gate is `BLOCKED` and the
release is `REDESIGN_REQUIRED`; a favorable empirical screen cannot override
it.

Model-use gates also stay outside MCP and outside the statistical lattice. OPT
uses a pinned non-commercial research license, so its production/commercial
gate is `BLOCKED`; its pinned legacy PyTorch serialization is accepted only
with remote code disabled and weights-only loading. DistilGPT2 and Pythia use
safetensors with remote code disabled. Pythia's model-card warning requires
separate policy/manual risk and bias review before deployment or human-facing
use; it is a use-policy gate, not an Apache-2.0 license prohibition.

WildChat rows contain real human-user prompts and ChatGPT-generated responses.
The dataset card's ODC-By database declaration must not be presented as a
license or clearance for individual dialogue or provider outputs. Content
rights, data governance, privacy, and provider terms therefore remain separate
release gates regardless of an operationally successful experiment.

The separate EuroSAT vision training-hook worker likewise does not add MCP
resources or tools. It processes all 27,000 real RGB satellite patches through
a deterministic path-hash 21,600/5,400 train/test split, trains canonical
torchvision AlexNet and DenseNet-121 from scratch for one epoch each, and runs
bounded real-image perturbation screens. This scale is a systems stress test,
not statistical evidence that the resulting models are safe, private, robust,
fair, accurate enough, or ready for release.

The optional `run_empirical_model_workflow` tool accepts an experimental configuration, trains native
XGBoost and scikit-learn MLP classifiers on independently seeded synthetic datasets, and returns
disjoint-holdout metrics with familywise Bonferroni-corrected exact accuracy intervals. The contract
limits replicate, sample, and feature counts. Functional metrics remain screens, membership attack
measurements are unbound empirical floors, and the overall result always returns
`no_release_authorization`. A floor cannot block until a separately isolated, policy-approved worker
recollects it into `AttackBatteryWorkerOutput/1.0` and the complete content-addressed submission passes
trusted-core validation and positive-control replay.

Those input-shape limits are not a complete resource sandbox: estimator hyperparameter dictionaries
and total tool runtime are not comprehensively bounded by the current MCP adapter. Keep this tool local
and trusted until a separately authenticated worker adds strict allowlists, CPU/memory quotas,
deadlines, cancellation, and output limits.

Each empirical replicate also runs a bounded red-team stage. A reference model trained on an
independent synthetic dataset freezes a loss-threshold membership attack before application to the
target model's members and holdout nonmembers. The stage also measures Gaussian feature corruption
and every single-feature occlusion. Membership results are exploratory simultaneous floors but cannot
block until routed through the policy-bound attack-battery contract; robustness results are screens.
Neither can clear.

The empirical workflow additionally invokes the focused
[SACRO-ML-inspired red-team registry](sacro-ml-red-team.md): aggregate structural disclosure screens
and a repeated worst-case probability membership classifier with a dummy baseline and simultaneous
low-FPR bounds. Their `ExploratoryRedTeamReport/2.0` is explicitly assessment-ineligible. Discovery
returns the typed catalog and digest, but live estimator calls remain inside the bounded local workflow.
A remote deployment must exchange inert artifact references and a signed worker output from an
isolated principal; `validate_attack_battery` itself does not execute, authenticate, attest, or decide.

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
