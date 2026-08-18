# Utility scripts

The package CLI under `src/model_release_assurance/` is the supported interface for assessment, optimization, certificate replay, schema generation, signing, and audit verification.

The scripts in this directory are optional benchmark and evidence-generation utilities. They are not required to install or operate the assurance core.

## Benchmark groups

- `run_v05_prospective_study.py` and `analyze_v05_prospective_study.py`: fixed-frame release-allocation benchmark.
- `run_protocol_feasibility_benchmark.py` and `analyze_protocol_feasibility_benchmark.py`: finite protocol solver stress tests.
- `run_portfolio_stochastic_benchmark.py` and `analyze_portfolio_stochastic_benchmark.py`: incomplete-portfolio statistical stress tests.
- `run_openml_*` and `analyze_openml_*`: optional OpenML evidence tiers.
- `seal_openml_reproduction.py`: hashes retained machine-readable configurations, code, summaries, and manifests.
- `evaluate_framework_effectiveness.py`: regenerates implementation-level decision-oracle output under `output/`.

Generated output belongs under `output/` and is excluded from version control.
