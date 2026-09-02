# Utility scripts

The supported product interface is the `mra` CLI implemented under
`src/model_release_assurance/`. The files in this directory are optional
reproduction, benchmark, worker, and maintenance utilities. They do not issue
an MRAP authorization, and a successful script run must not be interpreted as
permission to release or serve a model.

Run scripts from the repository root so that their repository-relative inputs
and outputs resolve consistently. Generated output belongs under `output/` and
is excluded from version control.

## Status vocabulary

| Status | Meaning |
|---|---|
| Retained design | Configuration or manifests are committed, but the checkout does not contain all generated run artifacts needed to claim a completed study. |
| Replay utility | Validates or summarizes generated artifacts; it is not evidence by itself. |
| Experimental | Exercises a bounded research or integration path and cannot authorize a release. |
| Maintenance check | Verifies repository artifacts, schemas, proofs, profiles, or test behavior. |

## OpenML reproduction study

These utilities implement the registered OpenML-CC18 study described in
[`reproduction/openml/README.md`](../reproduction/openml/README.md). The current
checkout retains the design and dataset manifests, not the raw snapshots,
trained models, complete run outputs, or final study seal.

| Stage | Scripts | Purpose | Status |
|---|---|---|---|
| Acquire | `fetch_openml_suite.py` | Download immutable OpenML snapshots and record dataset and runtime provenance. | Retained design; network access and a full experiment environment are required. |
| Select | `select_openml_subsets.py` | Select expensive-study subsets deterministically from sealed metadata. | Retained design; selection precedes outcome observation. |
| Structural | `run_openml_structural.py`<br>`analyze_openml_structural.py` | Train the broad tree tier, retain split and linkage artifacts, then replay hashes, counts, and structural metrics. | Runner plus replay utility; generated artifacts are absent from the checkout. |
| Membership | `run_openml_membership.py`<br>`analyze_openml_membership.py` | Run the frozen capacity and membership-attack tier, then verify scores, counts, and bounds. | Runner plus replay utility; attack output is a floor or screen, never clearance evidence. |
| Non-private neural | `run_openml_mlp.py`<br>`analyze_openml_mlp.py` | Train independently preprocessed MLP target/reference models and replay utility and attack results. | Runner plus replay utility; generated artifacts are absent. |
| Composition | `run_openml_composition.py`<br>`analyze_openml_composition.py` | Evaluate three releases on common sealed training rosters and replay composition bounds. | Runner plus replay utility; depends on structural-tier artifacts. |
| Metadata adversary | `run_openml_metadata_adversary.py`<br>`analyze_openml_metadata_adversary.py` | Compare metadata-only and model-plus-metadata attacks under registered summaries. | Runner plus replay utility; sensitivity study only. |
| DP-SGD | `run_openml_dp_sgd.py`<br>`analyze_openml_dp_sgd.py` | Run DP-SGD and a matched non-private control, then independently replay accountant ledgers and empirical attacks. | Runner plus replay utility; preprocessing remains outside the claimed private mechanism. |
| Multi-shadow | `run_openml_multi_shadow.py`<br>`analyze_openml_multi_shadow.py` | Run and replay the registered LiRA-style multi-shadow membership tier. | Runner plus replay utility; not a complete augmented online LiRA protocol. |
| Controlled inference | `run_openml_inference.py`<br>`analyze_openml_inference.py` | Run and replay controlled attribute-inference and one-feature reconstruction comparisons. | Runner plus replay utility; not full-record reconstruction. |
| Population validation | `run_openml_population_validation.py`<br>`analyze_openml_population_validation.py` | Validate probability-sampling bounds against complete finite benchmark populations. | Runner plus replay utility; does not establish a deployment-population frame. |
| Decision witnesses | `build_openml_decision_witnesses.py`<br>`analyze_openml_decision_witnesses.py` | Build candidate decision reversals from generated rosters and independently replay the retained rows. | Downstream replay utility; requires regenerated composition and source artifacts. |
| Seal | `seal_openml_reproduction.py` | Read the expected study artifacts and hash retained configurations, code, summaries, analyses, and manifests into the top-level study manifest. | Finalization utility; its output is meaningful only after the full registered run has been independently confirmed, regenerated, and validated. |

## Synthetic and protocol benchmarks

| Scripts | Purpose | Status |
|---|---|---|
| `run_portfolio_stochastic_benchmark.py`<br>`analyze_portfolio_stochastic_benchmark.py` | Generate and replay stochastic incomplete-portfolio coverage, certificate, and false-clear stress tests. | Experimental benchmark with a retained configuration; outputs are generated under `output/`. |
| `run_protocol_feasibility_benchmark.py` | Generate the finite protocol solver's raw trials, summary, and analysis in one command. | Experimental benchmark; there is no separate `analyze_protocol_feasibility_benchmark.py`. A default run also requires generated OpenML seal and framework-effectiveness output. |
| `run_strategic_assurance_experiment.py` | Replay exact-rational strategic certificates and run seeded incentive, tie, deterrence, and monitoring stress tests. | Experimental governance stress test; explicitly emits no governance decision or authorization. |
| `evaluate_framework_effectiveness.py` | Regenerate implementation-level decision-oracle probes and the documented capability-gap report. | Experimental evaluation of the declared offline oracle suite, not end-to-end assurance validation. |

## Model workers and workflows

| Script | Purpose | Status |
|---|---|---|
| `run_xgboost_audit.py` | Train trusted local CSV/Parquet XGBoost target/reference pipelines; measure utility, structure, and calibrated membership attacks; emit hash-bound artifacts and a release bundle. | Experimental local worker; floor/screen evidence only. See [`docs/xgboost.md`](../docs/xgboost.md). |
| `run_sample_model_audit_workflow.py` | Exercise the hash-bound sample CNN, LSTM, XGBoost, and LLM artifact workflow and family-specific assurance routing. | Experimental synthetic functional workflow; every model result has `can_clear: false`. |
| `run_empirical_xgboost_mlp_workflow.py` | Train native XGBoost and MLP models over repeated synthetic datasets, measure utility and attacks, and invoke the focused red-team registry. | Experimental empirical workflow; emits screens or attack floors and always returns `no_release_authorization`. |
| `run_public_privacy_audit.py` | Run the RAG-planned public-data CNN, LSTM, XGBoost, and compact Transformer privacy experiment. | Experimental worker requiring network access, experiment dependencies, and PyTorch; weak or null attacks never clear. See [`reproduction/public-privacy/README.md`](../reproduction/public-privacy/README.md). |

## Validation and maintenance

| Script | Purpose | Status |
|---|---|---|
| `check_markdown_links.py` | Verify that every repository Markdown link to a local file or directory resolves. | Maintenance check run by `make check`; external URLs and fragment identifiers are outside its scope. |
| `generate_schema_manifest.py` | Replay every registered current JSON Schema and generate or verify the exact-byte schema inventory. | Maintenance check run by `make schemas`; release signing/attestation is an external protected-key operation. |
| `validate_llm_audit_profile.py` | Validate the LLM watermark/canary preregistration template and optionally enforce collection readiness. | Maintenance check and protocol linter; it does not execute an audit or emit scientific evidence. |
| `evaluate_knowledge_retrieval.py` | Measure deterministic retrieval hit rate and reciprocal rank over the repository knowledge index. | Maintenance evaluation for the RAG corpus. |
| `evaluate_protocol_mutations.py` | Run accepted controls and unsafe MRAP transcript mutations, then report the mutation score and non-claim. | Maintenance evaluation built from the protocol test suite; not a scientific adequacy result. |
| `refresh_example_contracts.py` | Deterministically regenerate the current policy, attack catalog/battery, hash-bound evidence, assessment report, and optimization request fixtures. | Maintenance generator only; it does not execute an attack or authorize a release. |
| `verify_formal_protocol.py` | Verify the Lean toolchain boundary, theorem inventory, proof build, and axiom audit. | Maintenance check; requires Lake/Lean for the complete proof replay. |

## Dependency guide

- Core validation and maintenance utilities generally use the package runtime
  from `requirements.lock`.
- OpenML, XGBoost, stochastic, and empirical workflows require
  `requirements-experiments.txt` or the `experiments` extra.
- `run_public_privacy_audit.py` additionally requires the
  `privacy-experiments` extra and its PyTorch runtime.
- The live MCP server requires the `mcp` extra; the worker scripts themselves
  remain separate processes.
- Formal proof replay requires the Lean toolchain pinned under `formal/lean/`.

See [`reproduction/README.md`](../reproduction/README.md) for the retained-input
maturity matrix and [`tests/README.md`](../tests/README.md) for test coverage and
dependency tiers.
