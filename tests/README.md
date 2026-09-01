# Test suite

The test suite covers the offline assurance core, protocol replay, formal
artifact correspondence, optional experiments, and repository maintenance
checks. It does not test an authoritative identity service, production
registry, serving gateway, live remote MCP deployment, or operational model
monitoring.

Run tests from the repository root. Several tests import utilities directly
from the top-level `scripts/` directory, so an arbitrary working directory is
not a supported invocation context.

## Test categories

| Category | Files | Coverage |
|---|---|---|
| Assessment core and CLI | `test_framework.py`<br>`test_cli.py`<br>`test_contract_v4.py`<br>`test_audit_v2.py`<br>`test_critique_regressions.py`<br>`test_model_coverage.py` | Request/report/producer/policy/scope validation, analyzer semantics, contradictory-evidence fail-closed decisions, registry-bound optimization, two-phase audit integrity, signatures, command behavior, and governed model-family routing. |
| Decision and portfolio mathematics | `test_decision_theory.py`<br>`test_incomplete_portfolio.py`<br>`test_portfolio_statistics.py`<br>`test_protocol_feasibility.py`<br>`test_strategic_assurance.py` | Finite decision problems, exact incomplete-portfolio certificates, simultaneous statistical evidence, finite protocol feasibility, and exact-rational strategic stress tests. |
| MRAP lifecycle and formal correspondence | `test_release_protocol.py`<br>`test_release_protocol_verification_metadata.py`<br>`test_protocol_mutation_evaluation.py`<br>`test_formal_correspondence.py`<br>`test_formal_verification_artifact.py`<br>`test_system_audit_specification.py` | Structural/authenticated transcript replay, explicit degraded-verification metadata, unsafe mutation rejection, Python/Lean vocabulary and theorem/runtime-obligation correspondence, theorem inventory, integrated audit-document drift checks, and proof-artifact boundaries. The Python tests inspect formal artifacts; full Lean compilation is a separate tier. |
| Literature and claim-ledger integrity | `test_game_theory_review_artifact.py` | Primary-source ledger structure, citation bindings, and documented strategic-transfer limits. |
| Knowledge, services, and in-process workflow experiments | `test_knowledge_mcp.py`<br>`test_services.py`<br>`test_model_workflow.py`<br>`test_empirical_workflow.py`<br>`test_red_team.py` | Deterministic knowledge retrieval, MCP-facing tool logic, analyzer/model service descriptors and adapters, sample workflow integrity, empirical XGBoost/MLP execution, and focused red-team reports. Live remote MCP transport and durable orchestration are not exercised. |
| LLM and implementation-level checks | `test_llm_analyzers.py`<br>`test_llm_audit_profile.py`<br>`test_effectiveness.py` | Watermark/canary evidence semantics, fail-closed profile validation and collection readiness, and implementation decision-oracle probes. |
| Reproduction and benchmark utilities | `test_openml_reproduction.py`<br>`test_xgboost_runner.py`<br>`test_portfolio_stochastic_benchmark.py`<br>`test_protocol_feasibility_benchmark.py`<br>`test_strategic_assurance_experiment.py` | Deterministic splits, statistics, artifact/hash replay, XGBoost cache and bundle behavior, stochastic benchmark checks, and protocol and strategic experiment replay. These tests use small fixtures or synthetic runs; they do not rerun the full OpenML study. |

## Dependency tiers

| Tier | Install or tool | Tests and behavior |
|---|---|---|
| Core Python | `requirements.lock`, then an editable package install | Covers contract validation, assessment, integrity, replay, knowledge, services, and LLM paths that use only the package runtime. It is not sufficient for the complete test suite. |
| Solver Python | `.[portfolio]` | Adds SciPy for portfolio/protocol linear programs and exact statistical interval helpers. |
| Experiment Python | `requirements-experiments.txt` or `.[experiments]` | Required for the complete suite, including OpenML, XGBoost, NumPy/Pandas/SciPy/scikit-learn, stochastic, and native empirical-workflow coverage. `test_empirical_workflow.py` and `test_red_team.py` skip when their empirical dependencies are unavailable; direct OpenML/XGBoost imports require the tier to be installed. |
| MCP runtime | `.[mcp]` | Required to launch the live MCP server. Current unit tests cover MCP-facing logic and adapters without establishing a remote server session. |
| Privacy experiment | `.[experiments,privacy-experiments]` | Required by the public-data CNN/LSTM/XGBoost/compact-Transformer worker. The standard unit suite does not download datasets or run the full PyTorch experiment. |
| Lean proof | Toolchain pinned by `formal/lean/lean-toolchain` | Required for `make formal` and the complete Lake build and axiom audit. Python formal tests alone do not compile the proof. |

## Standard commands

Install the same Python dependency families used by CI:

```bash
python -m pip install --disable-pip-version-check -r requirements.lock
python -m pip install --disable-pip-version-check -r requirements-experiments.txt
python -m pip install --no-deps -e .
```

Run the Python suite:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

Run compile checks, Python tests, current-schema replay, and local Markdown-link checks:

```bash
make check
```

Run the separate formal verification boundary:

```bash
make formal
```

To focus on one top-level test file while preserving discovery behavior:

```bash
PYTHONPATH=src python -m unittest discover -s tests -p 'test_release_protocol.py' -v
```

## Interpretation

- Passing tests establish the checked software invariants for their fixtures;
  they do not prove model safety or scientific completeness.
- Experiment tests use bounded synthetic or local data and cannot substitute
  for a complete, hash-bound reproduction run.
- Skips caused by unavailable optional dependencies are expected only where a
  test explicitly declares that condition. CI installs the experiment tier so
  those paths are exercised there.
- A mutation score measures rejection of the registered mutants, not the
  adequacy of every possible adversarial protocol behavior.
- Formal tests distinguish inspection of retained Lean artifacts from an
  actual proof build; only the Lean tier performs the latter.
