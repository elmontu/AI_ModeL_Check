# Utility scripts

The package CLI under `src/model_release_assurance/` is the supported interface for all-model coverage review, assessment, optimization, certificate replay, schema generation, signing, and audit verification.

The scripts in this directory are optional benchmark and evidence-generation utilities. They are not required to install or operate the assurance core.

## Benchmark groups

- `run_v05_prospective_study.py` and `analyze_v05_prospective_study.py`: fixed-frame release-allocation benchmark.
- `run_protocol_feasibility_benchmark.py` and `analyze_protocol_feasibility_benchmark.py`: finite protocol solver stress tests.
- `run_strategic_assurance_experiment.py`: optional governance stress test with exact-rational certificate replay, interval sampling, strict-tie negative control, deterrence frontier, zero-enforcement monitoring test, and explicit no-governance-decision/no-authorization scope.
- `run_portfolio_stochastic_benchmark.py` and `analyze_portfolio_stochastic_benchmark.py`: incomplete-portfolio statistical stress tests.
- `run_openml_*` and `analyze_openml_*`: optional OpenML evidence tiers.
- `run_xgboost_audit.py`: local CSV/Parquet XGBoost classification, utility, structural, and membership audit worker.
- `validate_llm_audit_profile.py`: fail-closed structural and collection-readiness linter for the LLM watermark/canary preregistration profile; it is not an evidence analyzer.
- `seal_openml_reproduction.py`: hashes retained machine-readable configurations, code, summaries, and manifests.
- `evaluate_framework_effectiveness.py`: regenerates implementation-level decision-oracle output under `output/`.

Generated output belongs under `output/` and is excluded from version control.

The local XGBoost worker is documented in [`docs/xgboost.md`](../docs/xgboost.md). It is separate from the sealed OpenML study and never emits clearance evidence.
