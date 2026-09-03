# Reproduction assets

This directory contains committed inputs for examples, experiments, and
benchmark replays. A configuration or manifest is not evidence that the
corresponding run completed. Generated datasets, caches, trained models,
reports, audit databases, and study output belong under ignored runtime paths
such as `output/` unless a publication or release process explicitly retains
and hash-binds them.

The [2026-09-02 real-data training-hook execution audit](../docs/real-data-training-hook-audit-2026-09-02.md)
and the [ceiling experiment publication summary](ceiling-experiment-summary.json)
are explicit publication exceptions. The ceiling directories retain
hash-manifested aggregate reports and replay records; the hook audit retains
curated aggregate measurements and digests. Raw model scores, datasets, caches,
sample rosters, and trained state remain excluded.

## Maturity vocabulary

| Maturity | Meaning |
|---|---|
| Template | A starting point containing placeholders or requiring adopter-supplied data and bindings. |
| Executable example | A bounded local example with committed inert inputs; its result is illustrative and non-authorizing. |
| Configured experiment | Parameters are committed, but generated results are not retained as completed evidence. |
| Registered design | The study frame and provenance manifests are committed; publication-grade claims require complete regeneration, replay, and sealing. |
| Retained completed result | The registered run completed and publication-safe outputs plus an integrity manifest are committed; failed acceptance criteria remain part of the result. |

## Asset matrix

| Area | Retained assets | Maturity and current status | Entry point |
|---|---|---|---|
| [`finite-channel-ceiling/`](finite-channel-ceiling/) | Frozen exact rational channels, preregistration, runner, 1,800 aggregate count records, report, log, resource record, and manifest | **Retained completed result; accepted within controlled scope.** Across 1,200 primary analyzer replays, observed undercoverage was 0 and all 400 safe/boundary/unsafe repetitions produced the registered decision. Model-family names are labels; three integrations traversed the Engine under an experimental attack-battery waiver. | Read [`finite-channel-ceiling/README.md`](finite-channel-ceiling/README.md), then use the [paper result tables](../paper/ceiling-experiment-results.md) or replay the runner. |
| [`model-backed-finite-channel/`](model-backed-finite-channel/) | V1 failure record, frozen v2/v3 registrations and configurations, versioned retained reports, finite-pool oracles, wrapper execution evidence, repeated analyzer rows, logs, resource records, and manifests | **Retained completed v3 result; all 10 criteria passed.** V3 completed six Engine primary replays and 1,200 analyzer repeats with 0 undercoverage and wrong-direction events; four margin-eligible safe-side families resolved 200/200 correctly. V2's 8/9 negative result remains preserved. | Read [`model-backed-finite-channel/README.md`](model-backed-finite-channel/README.md), the [v3 report](model-backed-finite-channel/results/v3/model-backed-finite-channel-report.json), [v3 manifest](model-backed-finite-channel/results/v3/manifest.json), historical [v2 report](model-backed-finite-channel/results/v2/model-backed-finite-channel-report.json), and generated [paper tables](../paper/ceiling-experiment-results.md). |
| [`openml/`](openml/) | OpenML-CC18 suite/source/dataset manifests; subset, MLP, metadata-adversary, DP-SGD, multi-shadow, inference, and population configurations; a historical/provisional runtime tuple | **Registered design.** The runtime tuple is neither the current CI compatibility band nor a dependency lock. The checkout records 72 manifest entries but omits raw snapshots, caches, trained models, run outputs, witness rows, and the top-level study seal. Quantitative prior-run records are provisional until regenerated and independently replayed. | Read [`openml/README.md`](openml/README.md), then use the `fetch_openml_*`, `run_openml_*`, `analyze_openml_*`, witness, and seal utilities cataloged in [`scripts/README.md`](../scripts/README.md). |
| [`portfolio-stochastic/`](portfolio-stochastic/) | Stochastic incomplete-portfolio benchmark configuration | **Configured experiment.** The benchmark and independent analysis are executable, but generated raw rows, summaries, and reports are not committed. | `scripts/run_portfolio_stochastic_benchmark.py`, then `scripts/analyze_portfolio_stochastic_benchmark.py` |
| [`strategic-assurance/`](strategic-assurance/) | Exact-rational strategic assurance problem configuration | **Configured experiment.** The seeded stress test checks registered mathematical claims and monitoring/incentive edge cases; it deliberately produces no governance decision or release authorization. | `scripts/run_strategic_assurance_experiment.py` |
| [`xgboost/`](xgboost/) | Versioned example configuration for a trusted local tabular-classification audit | **Template.** Supply and hash a local CSV/Parquet dataset and create an active configuration before running. No dataset or result is retained here. | `scripts/run_xgboost_audit.py`; see [`docs/xgboost.md`](../docs/xgboost.md) |
| [`llm/`](llm/) | Watermark and synthetic-canary audit profile example | **Template.** It intentionally contains replacement markers, zero digests, and unset collection fields. Replace and independently approve every required binding before using `--collection-ready`. | `scripts/validate_llm_audit_profile.py`; see [`docs/llm-watermark-canary.md`](../docs/llm-watermark-canary.md) |
| [`llm-training-hook/`](llm-training-hook/) | Commit-pinned WildChat-4.8M shard (`c827c6df…`, SHA-256 `6df660dc…`; 125,527,585 bytes / 37,208 rows), safe English/non-toxic/unredacted first-pair projection, shared deterministic 8,192/1,024 train/holdout split, and sequential DistilGPT2/OPT-125M/Pythia-160M aggregate-hook matrix | **Configured experiment.** Each model runs 512 optimizer steps and a before/after knowledge-profile lattice with separate 256-member/256-nonmember calibration and audit cells. Results are underpowered, descriptive, noncausal, nonmonotone, and never authorizing; the internally reconstructible roster is modeled separately as direct disclosure. The rows contain real human-user/ChatGPT dialogue, and the dataset card's ODC-By database declaration does not clear rights in individual content or provider outputs. OPT's non-commercial license blocks production/commercial use; Pythia requires separate policy/manual review for deployment or human-facing use. | Read [`llm-training-hook/README.md`](llm-training-hook/README.md), then run `scripts/run_llm_training_hook_audit.py --config reproduction/llm-training-hook/config.json` in a fresh run directory. |
| [`vision-training-hook/`](vision-training-hook/) | Digest-pinned full EuroSAT RGB archive (94,658,721 bytes), all 27,000 real Sentinel-2 image patches, deterministic class-stratified 21,600/5,400 train/test split, and from-scratch torchvision AlexNet/DenseNet-121 aggregate-hook matrix | **Configured experiment.** Each architecture processes the complete training split for one epoch, evaluates the untouched complete test split before and after, and runs bounded brightness, Gaussian-noise, and FGSM screens on real test images. The workload demonstrates execution and scale; it is not a privacy, robustness, fairness, or quality result and never authorizes release. Dataset and modified Copernicus Sentinel terms require independent review. | Read [`vision-training-hook/README.md`](vision-training-hook/README.md), then run `scripts/run_vision_training_hook_audit.py --config reproduction/vision-training-hook/config.json` in the exact CUDA runtime. |
| [`composition-scaling/`](composition-scaling/) | Shared five-model protocol for DistilGPT2, OPT-125M, Pythia-160M, AlexNet, and DenseNet-121 across three nested real-data scales and five registered seeds | **Configured experiment.** It registers 75 independent model/scale/seed reference cells and 90 additional matched vision batch/hook cells, same-population scalar composition for seven LLM and three vision subsets, and vector-only accounting for all 31 non-empty five-model portfolios. Cross-modal AUC, accuracy, or risk is never pooled. Generated journals, reports, model state, data, and caches remain ignored; a configuration, queue record, or partial journal is not completion. | Read [`composition-scaling/README.md`](composition-scaling/README.md), then use the suite coordinator or a child worker in a bounded, offline-capable runtime. |
| [`model-audit-workflow/`](model-audit-workflow/) | Hash-bound sample CNN, LSTM, XGBoost, MLP, and LLM artifacts; four-family and two-worker manifests; empirical XGBoost/MLP configuration | **Executable examples plus configured empirical experiment.** Sample artifacts exercise integrity, service replacement, and fail-closed routing. The empirical configuration trains native XGBoost/MLP models and runs focused red-team checks. All paths are experimental, non-clearing, and non-authorizing; generated reports are not retained here. | `scripts/run_sample_model_audit_workflow.py` and `scripts/run_empirical_xgboost_mlp_workflow.py` |
| [`public-privacy/`](public-privacy/) | Experiment description only | **Configured external-data workflow.** The plan, public dataset cache, trained CNN/LSTM/XGBoost/compact-Transformer models, raw losses, and report are generated locally and are not committed. Network access and PyTorch are required. | Read [`public-privacy/README.md`](public-privacy/README.md), then run `scripts/run_public_privacy_audit.py` or invoke the RAG/MCP orchestration. |

## Evidence boundary

- Sample and synthetic artifacts demonstrate code paths; they are not evidence
  that a production release is safe.
- The controlled ceiling result supports empirical calibration only for its
  exact predeclared finite channels. Model-backed v2 remains a failed
  predecessor; corrective v3 was prospectively frozen after v2 with fresh
  model and sampling seeds and passed under its role-aware criteria.
- V3 is conditional on one artifact per family, 400 `IN`/400 `OUT` records for
  CNN and XGBoost and 350/350 for the proxy, and resampling from those pools.
  Its compact Transformer is only an LLM proxy. It establishes neither
  population transfer, scalability, nor training-hook behavior.
- V3 executed every observation through a one-use Python wrapper and exactly
  cross-replayed its counts against the aggregate sampler. This does not prove
  deployed endpoint, process-isolation, timing, authentication, or OS semantic
  completeness.
- Every v3 oracle risk was below tolerance. V3 supports safe-side resolution
  and conservative near-boundary holds, not model-backed unsafe-side or
  `BLOCK` power; only the controlled `0.80` channel supplies that evidence.
- All ceiling experiments use experimental attack-battery waivers and grant no
  authorization.
- Attack floors may support blocking decisions. Weak or unsuccessful attacks
  do not establish confidentiality and never clear a threat.
- A replayable study result must bind the exact configuration, code, runtime,
  data, model artifacts, raw measurements, summaries, and analyses it used.
- MRAP authorization remains outside these experiments. Assessment output,
  workflow completion, and a reproduction seal are not serving permissions.

Run commands from the repository root. The complete script catalog is in
[`scripts/README.md`](../scripts/README.md), and the automated coverage map is
in [`tests/README.md`](../tests/README.md).
