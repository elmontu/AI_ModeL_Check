# Reproduction assets

This directory contains committed inputs for examples, experiments, and
benchmark replays. A configuration or manifest is not evidence that the
corresponding run completed. Generated datasets, caches, trained models,
reports, audit databases, and study output belong under ignored runtime paths
such as `output/` unless a publication or release process explicitly retains
and hash-binds them.

## Maturity vocabulary

| Maturity | Meaning |
|---|---|
| Template | A starting point containing placeholders or requiring adopter-supplied data and bindings. |
| Executable example | A bounded local example with committed inert inputs; its result is illustrative and non-authorizing. |
| Configured experiment | Parameters are committed, but generated results are not retained as completed evidence. |
| Registered design | The study frame and provenance manifests are committed; publication-grade claims require complete regeneration, replay, and sealing. |

## Asset matrix

| Area | Retained assets | Maturity and current status | Entry point |
|---|---|---|---|
| [`openml/`](openml/) | OpenML-CC18 suite/source/dataset manifests; subset, MLP, metadata-adversary, DP-SGD, multi-shadow, inference, and population configurations; a historical/provisional runtime tuple | **Registered design.** The runtime tuple is neither the current CI compatibility band nor a dependency lock. The checkout records 72 manifest entries but omits raw snapshots, caches, trained models, run outputs, witness rows, and the top-level study seal. Quantitative prior-run records are provisional until regenerated and independently replayed. | Read [`openml/README.md`](openml/README.md), then use the `fetch_openml_*`, `run_openml_*`, `analyze_openml_*`, witness, and seal utilities cataloged in [`scripts/README.md`](../scripts/README.md). |
| [`portfolio-stochastic/`](portfolio-stochastic/) | Stochastic incomplete-portfolio benchmark configuration | **Configured experiment.** The benchmark and independent analysis are executable, but generated raw rows, summaries, and reports are not committed. | `scripts/run_portfolio_stochastic_benchmark.py`, then `scripts/analyze_portfolio_stochastic_benchmark.py` |
| [`strategic-assurance/`](strategic-assurance/) | Exact-rational strategic assurance problem configuration | **Configured experiment.** The seeded stress test checks registered mathematical claims and monitoring/incentive edge cases; it deliberately produces no governance decision or release authorization. | `scripts/run_strategic_assurance_experiment.py` |
| [`xgboost/`](xgboost/) | Versioned example configuration for a trusted local tabular-classification audit | **Template.** Supply and hash a local CSV/Parquet dataset and create an active configuration before running. No dataset or result is retained here. | `scripts/run_xgboost_audit.py`; see [`docs/xgboost.md`](../docs/xgboost.md) |
| [`llm/`](llm/) | Watermark and synthetic-canary audit profile example | **Template.** It intentionally contains replacement markers, zero digests, and unset collection fields. Replace and independently approve every required binding before using `--collection-ready`. | `scripts/validate_llm_audit_profile.py`; see [`docs/llm-watermark-canary.md`](../docs/llm-watermark-canary.md) |
| [`model-audit-workflow/`](model-audit-workflow/) | Hash-bound sample CNN, LSTM, XGBoost, MLP, and LLM artifacts; four-family and two-worker manifests; empirical XGBoost/MLP configuration | **Executable examples plus configured empirical experiment.** Sample artifacts exercise integrity, service replacement, and fail-closed routing. The empirical configuration trains native XGBoost/MLP models and runs focused red-team checks. All paths are experimental, non-clearing, and non-authorizing; generated reports are not retained here. | `scripts/run_sample_model_audit_workflow.py` and `scripts/run_empirical_xgboost_mlp_workflow.py` |
| [`public-privacy/`](public-privacy/) | Experiment description only | **Configured external-data workflow.** The plan, public dataset cache, trained CNN/LSTM/XGBoost/compact-Transformer models, raw losses, and report are generated locally and are not committed. Network access and PyTorch are required. | Read [`public-privacy/README.md`](public-privacy/README.md), then run `scripts/run_public_privacy_audit.py` or invoke the RAG/MCP orchestration. |

## Evidence boundary

- Sample and synthetic artifacts demonstrate code paths; they are not evidence
  that a production release is safe.
- Attack floors may support blocking decisions. Weak or unsuccessful attacks
  do not establish confidentiality and never clear a threat.
- A replayable study result must bind the exact configuration, code, runtime,
  data, model artifacts, raw measurements, summaries, and analyses it used.
- MRAP authorization remains outside these experiments. Assessment output,
  workflow completion, and a reproduction seal are not serving permissions.

Run commands from the repository root. The complete script catalog is in
[`scripts/README.md`](../scripts/README.md), and the automated coverage map is
in [`tests/README.md`](../tests/README.md).
