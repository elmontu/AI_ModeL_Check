# Test suite

The test suite covers the offline assurance core, protocol replay, formal
artifact correspondence, optional experiments, and repository maintenance
checks. It does not test an authoritative identity service, production
registry, serving gateway, live remote MCP deployment, or operational model
monitoring.

Run tests from the repository root. Several tests import utilities directly
from the top-level `scripts/` directory, so an arbitrary working directory is
not a supported invocation context.

Paper consistency and finite-construction checks live in
[academic/tests/](../academic/tests/). They use retained artifacts and exact
constructions without rerunning historical model studies or building the PDF.
Both test directories are included by `make test` and the CI `make check` target.

## Test categories

`test_pipeline_workflow.py` exercises local case preflight, immediate-parent
lineage, file substitution, route mismatch, Engine execution, retained failures
and setup dry runs. It does not authenticate the inventoried agency documents.
The pipeline bootstrap CI job installs a new environment and runs the offline
training demo on Windows and Linux.

`test_console.py` covers the separate-worker queue and the optional HTTP API.
API tests need `requirements-console.txt` and otherwise explicitly skip. The
bootstrap CI job installs the console profile so those tests run there.

| Category | Files | Coverage |
|---|---|---|
| Training-to-assessment demo | `test_training_release_demo.py` | Offline real XGBoost target/reference fitting on the packaged scikit-learn profile; aggregate training-hook completion; preregistration-before-outcome ordering; deterministic release-bundle identity; post-plan same-artifact membership evidence; typed request admission; `AssuranceEngine` invocation; MRAP prefix stopping at `ASSESSED`; and hold/block plus non-authorization invariants. The test does not download OpenML or establish a decision-bearing ceiling. |
| Secondary guided fixture | `test_government_health_demo.py` | Core-only, no-network execution of four disclosed synthetic functional proxies; closed digest-pinned fixture copying and path-confinement controls; fresh assessment-to-optimization binding; signatures; audit checkpoint; plain-language report; live hold/block/artifact-tamper branches; structural workflow activation, stale-registry, deployment-mismatch, and suspension rehearsals; explicit discussion-overlay and non-authorization invariants. It does not train a model. |
| Assessment core and CLI | `test_framework.py`<br>`test_cli.py`<br>`test_contract_v5.py`<br>`test_attack_battery.py`<br>`test_audit_v2.py`<br>`test_critique_regressions.py`<br>`test_model_coverage.py`<br>`test_runtime_identity.py`<br>`test_schema_registry.py` | Request/report/producer/policy/scope validation, complete attack-battery identity/time/resource/multiplicity and positive-control semantics, contradictory-evidence fail-closed decisions, registry-bound optimization, two-phase audit integrity/privacy-degradation reporting, deterministic runtime attribution, exact current-schema inventory, signatures, command behavior, and governed model-family routing. |
| Decision and portfolio mathematics | `test_decision_theory.py`<br>`test_incomplete_portfolio.py`<br>`test_portfolio_statistics.py`<br>`test_protocol_feasibility.py`<br>`test_statistical_floor_family.py`<br>`test_strategic_assurance.py` | Finite decision problems, exact incomplete-portfolio certificates, simultaneous statistical evidence, preregistered and complete statistical-floor family enforcement, finite protocol feasibility, and exact-rational strategic stress tests. |
| MRAP lifecycle and formal correspondence | `test_release_protocol.py`<br>`test_release_protocol_verification_metadata.py`<br>`test_protocol_mutation_evaluation.py`<br>`test_formal_correspondence.py`<br>`test_formal_verification_artifact.py`<br>`test_system_audit_specification.py` | Structural/authenticated transcript replay, explicit degraded-verification metadata, unsafe mutation rejection, Python/Lean vocabulary and theorem/runtime-obligation correspondence, theorem inventory, integrated audit-document drift checks, and proof-artifact boundaries. The Python tests inspect formal artifacts; full Lean compilation is a separate tier. |
| Literature and claim-ledger integrity | `test_game_theory_review_artifact.py` | Primary-source ledger structure, citation bindings, and documented strategic-transfer limits. |
| Knowledge, services, and in-process workflow experiments | `test_knowledge_mcp.py`<br>`test_services.py`<br>`test_model_workflow.py`<br>`test_empirical_workflow.py`<br>`test_red_team.py` | Deterministic knowledge retrieval, MCP-facing tool logic, analyzer/model service descriptors and adapters, sample workflow integrity, empirical XGBoost/MLP execution, and focused red-team reports. Live remote MCP transport and durable orchestration are not exercised. |
| Training-hook and implementation-level checks | `test_llm_analyzers.py`<br>`test_llm_audit_profile.py`<br>`test_llm_training_hooks.py`<br>`test_llm_training_worker.py`<br>`test_vision_training_worker.py`<br>`test_llm_composition_scaling.py`<br>`test_vision_composition_scaling.py`<br>`test_composition_scaling_suite.py`<br>`test_effectiveness.py` | Watermark/canary evidence semantics, fail-closed profile validation, aggregate-hook integrity, LLM before/after context-knowledge partitions, exact EuroSAT/AlexNet/DenseNet-121 configuration and archive boundaries, vision hook coverage, five-model composition scale/seed/authority/export closure, release-gate behavior, and implementation decision-oracle probes. Unit fixtures do not download WildChat, EuroSAT, or model artifacts; live pinned matrices are separate GPU integration experiments. |
| Finite-channel ceiling experiments | `test_finite_channel_ceiling.py`<br>`test_finite_channel_ceiling_experiment.py`<br>`test_model_backed_finite_channel.py`<br>`test_model_backed_wrapper_conformance.py`<br>`test_public_privacy_audit_artifact_hash.py`<br>`test_ceiling_experiment_summary.py` | Exact/outward interval replay, frozen controlled design, model-backed configuration and source bindings, direct one-use wrapper sampling, exact aggregate-schedule cross-replay, XGBoost artifact serialization, five negative controls (including missing/tampered wrapper evidence), role-aware decision criteria, and generated publication-summary integrity. Tests use fixtures and retained artifacts; they do not retrain the public-data models or prove process/OS side-channel isolation or real serving-endpoint enforcement. |
| Reproduction and benchmark utilities | `test_openml_reproduction.py`<br>`test_xgboost_runner.py`<br>`test_portfolio_stochastic_benchmark.py`<br>`test_protocol_feasibility_benchmark.py`<br>`test_strategic_assurance_experiment.py` | Deterministic splits, statistics, artifact/hash replay, XGBoost cache and bundle behavior, stochastic benchmark checks, and protocol and strategic experiment replay. These tests use small fixtures or synthetic runs; they do not rerun the full OpenML study. |

## Dependency tiers

| Tier | Install or tool | Tests and behavior |
|---|---|---|
| Core Python | `requirements.lock`, then an editable package install | Covers contract validation, assessment, integrity, replay, knowledge, services, and LLM paths that use only the package runtime. It is not sufficient for the complete test suite. |
| Solver Python | `.[portfolio]` | Adds SciPy for portfolio/protocol linear programs and exact statistical interval helpers. |
| Experiment Python | `requirements-experiments.txt` or `.[experiments]` | Required for the complete suite, including the actual training-to-assessment demo, OpenML, XGBoost, NumPy/Pandas/SciPy/scikit-learn, stochastic, and native empirical-workflow coverage. CI exercises the demo with `sklearn-breast-cancer` so the integration test remains offline; `make demo` uses the pinned OpenML profile by default. `test_empirical_workflow.py` and `test_red_team.py` skip when their empirical dependencies are unavailable; direct OpenML/XGBoost imports require the tier to be installed. |
| MCP runtime | `.[mcp]` | Required to launch the live MCP server. Current unit tests cover MCP-facing logic and adapters without establishing a remote server session. |
| Privacy experiment | `.[experiments,privacy-experiments]` | Required by the public-data CNN/LSTM/XGBoost/compact-Transformer worker. The standard unit suite does not download datasets or run the full PyTorch experiment. |
| Ceiling reproduction | `requirements-experiments.txt` plus `.[privacy-experiments]` for the model-backed collector | The controlled runner uses exact statistical helpers; full model-backed reproduction retrains the three registered models and executes 1,200 analyzer replays. Focused tests validate code, contracts, one-use wrapper sampling, aggregate equivalence, role-aware criteria, and retained-summary consistency; they do not prove endpoint/OS semantics or supply an above-tolerance model-backed case. |
| LLM training-hook experiment | `.[llm-experiments]` in an isolated runtime | Required for the commit-pinned WildChat-4.8M shard and sequential DistilGPT2/OPT-125M/Pythia-160M matrix. Standard tests use local fixtures and do not download remote artifacts; the live worker records exact versions, checks model-specific loader/license/use-policy fields, and remains non-authorizing. |
| Vision training-hook experiment | `.[vision-experiments]` in the registered CUDA runtime | Required for the full 27,000-image EuroSAT RGB and from-scratch AlexNet/DenseNet-121 matrix. Focused CI instantiates both architectures with `weights=None` on CPU to test hook semantics but does not download the dataset, train the full workload, or turn test success into release evidence. |
| Composition-scaling experiment | `.[llm-experiments,vision-experiments]` in the registered CUDA runtime | Required for the complete five-model matrix. Focused tests validate frozen scales/seeds, child/suite contracts, resume and closure behavior, same-population scalar composition, and mixed-modality vector boundaries without running the 165 registered training executions. |
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
python -m unittest discover -s academic/tests -v
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
- Focused training-hook CI checks contracts, bounded fixture adapters, and model
  instrumentation. It does not reproduce either real-data experiment or
  authorize any model or release interface.
- Skips caused by unavailable optional dependencies are expected only where a
  test explicitly declares that condition. CI installs the experiment tier so
  those paths are exercised there.
- A mutation score measures rejection of the registered mutants, not the
  adequacy of every possible adversarial protocol behavior.
- Formal tests distinguish inspection of retained Lean artifacts from an
  actual proof build; only the Lean tier performs the latter.
