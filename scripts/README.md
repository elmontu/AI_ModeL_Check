# Utility scripts

The supported product interface is the `mra` CLI implemented under
`src/model_release_assurance/`. The files in this directory are optional
reproduction, benchmark, worker, and maintenance utilities. They do not issue
an MRAP authorization, and a successful script run must not be interpreted as
permission to release or serve a model.

Run scripts from the repository root so that their repository-relative inputs
and outputs resolve consistently. Generated output belongs under `output/` and
is excluded from version control.

Historical study registrations bind their original source and runtime; they
are not validation of the current MRA 0.8 implementation. Replaying them
requires the pinned source/runtime, or a separately approved prospective
registration for changed code. Do not update old study hashes to make a new
worker pass. The [reproduction index](../reproduction/README.md#frozen-replay-and-new-runs)
distinguishes retained results, configured workloads, and fresh runs.

## Status vocabulary

The cross-platform `setup_pipeline.py` installer and the packaged `mra-workflow`
commands provide [case setup, preflight and assessment](../docs/pipeline-quickstart.md).
Use `--dry-run` to inspect installation commands or `--wheelhouse` for a local
package source. Neither setup nor case preflight is a release approval.

| Status | Meaning |
|---|---|
| Retained design | Configuration or manifests are committed, but the checkout does not contain all generated run artifacts needed to claim a completed study. |
| Replay utility | Validates or summarizes generated artifacts; it is not evidence by itself. |
| Experimental | Exercises a bounded research or integration path and cannot authorize a release. |
| Maintenance check | Verifies repository artifacts, schemas, proofs, profiles, or test behavior. |

## Academic paper assembly

These tools live in [academic/scripts/](../academic/scripts/); run the commands
from the repository root using that path.

| Script | Purpose | Boundary |
|---|---|---|
| [build_academic_paper_data.py](../academic/scripts/build_academic_paper_data.py) | Extract the explicitly allowlisted aggregate evidence into `academic/paper/experimental-data.json`; `--check` revalidates retained bytes. | Requires the original local source files, including ignored outputs. It performs no experiments and does not create an MRAP contract. |
| [build_academic_paper.py](../academic/scripts/build_academic_paper.py) | Generate manuscript tables and a vector scaling figure from the retained companion; `--check` compares generated artifacts. | Optional ReportLab/font dependency for the figure only; no MRA core or schema changes. |
| [check_academic_gap_constructions.py](../academic/scripts/check_academic_gap_constructions.py) | Reproduce seven exact finite countermodels and repair controls in `academic/paper/gap-construction-results.json`; `--check` compares bytes. | Standard library only, seed-free and offline; no model training, core imports, cryptographic implementation or universal-refinement claim. |

The committed paper companion, tables and figure are deliberate aggregate-only
exceptions to the usual `output/` convention. See the
[paper build and evidence-access instructions](../reproduction/README.md#paper-draft).

## OpenML reproduction study

These utilities implement the registered OpenML-CC18 study described in the
[reproduction index](../reproduction/README.md#openml-design). The current
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

## Synthetic and protocol benchmarks

| Scripts | Purpose | Status |
|---|---|---|
| `run_finite_channel_ceiling_experiment.py` | Replay exact controlled safe, boundary, and unsafe channels through the reference analyzer, selected full Engine paths, simultaneous meta-evaluation, and tamper controls. | Historical experimental validation with [retained accepted results](../reproduction/finite-channel-ceiling/results/manifest.json). Its model names are labels, only three replays traverse the Engine, and the experimental battery waiver is not deployment-valid. |
| `run_model_backed_finite_channel.py` | Train CNN, XGBoost, and compact-Transformer-proxy collectors on public data, compile finite-pool categorical channels, execute observations through one-use wrappers with exact aggregate cross-replay, and run six primary Engine plus 1,200 repeated analyzer replays. | Prospectively frozen v3 completed with [all 10 criteria passed](../reproduction/model-backed-finite-channel/results/v3/manifest.json); v2's [8/9 negative result](../reproduction/model-backed-finite-channel/results/v2/manifest.json) remains retained. V3 demonstrates execution and exact agreement on the recorded Python paths, not deployed endpoint or OS semantics, and contains no above-tolerance model-backed case. |
| `run_portfolio_stochastic_benchmark.py`<br>`analyze_portfolio_stochastic_benchmark.py` | Generate and replay stochastic incomplete-portfolio coverage, certificate, and false-clear stress tests. | Experimental benchmark with a retained configuration; outputs are generated under `output/`. |
| `run_protocol_feasibility_benchmark.py` | Generate the finite protocol solver's exact synthetic frontiers, Monte Carlo rows, summary, and analysis in one self-contained command. | Experimental synthetic benchmark; there is no separate analyzer and it consumes no external empirical evidence. Its output explicitly records that deployment behavior, representative release yield, safety, and authorization were not evaluated. |
| `run_strategic_assurance_experiment.py` | Replay exact-rational strategic certificates and run seeded incentive, tie, deterrence, and monitoring stress tests. | Experimental governance stress test; explicitly emits no governance decision or authorization. |
| `evaluate_framework_effectiveness.py` | Regenerate implementation-level decision-oracle probes and the documented capability-gap report. | Experimental evaluation of the declared offline oracle suite, not end-to-end assurance validation. |

## Model workers and workflows

| Script | Purpose | Status |
|---|---|---|
| `run_training_release_demo.py` | Execute the primary application pipeline: acquire or validate a governed dataset snapshot, freeze an outcome-independent plan, train real target/reference XGBoost models with aggregate callbacks, export and hash the release bundle, run a post-plan membership test on that same candidate, adapt it into a typed `AssessmentRequest`, invoke `AssuranceEngine`, and emit an MRAP transcript ending at `ASSESSED`. | Guided experiment-tier integration demo. The default pinned OpenML `sick` profile may use the network; `sklearn-breast-cancer` is the fast offline profile; `--dataset-path` accepts an approved local snapshot. Attack output is a floor or screen, so the result is hold or block—never local clearance, authorization, or deployment. See [`docs/guided-government-health-demo.md`](../docs/guided-government-health-demo.md). |
| `run_government_health_demo.py` | Run the secondary core-only fixture journey: four disclosed non-clearing proxy previews, contract/artifact validation, assessment-to-optimization hand-off, signatures, audit replay, hold/block/tamper cases, and mock MRAP registry/gateway/monitoring branches. | Reference rehearsal using checked-in generic synthetic evidence. It does not train a model. Raw typed replay files may record fictional authorization/activation states, but the top-level result remains not authorized and not active. Invoke with `make demo-reference`. |
| `run_xgboost_audit.py` | Train trusted local CSV/Parquet XGBoost target/reference pipelines; measure utility, structure, and calibrated membership attacks; emit hash-bound artifacts and a release bundle. | Experimental local worker; floor/screen evidence only. See [`docs/xgboost.md`](../docs/xgboost.md). |
| `run_sample_model_audit_workflow.py` | Exercise the hash-bound sample CNN, LSTM, XGBoost, and LLM artifact workflow and family-specific assurance routing. | Experimental synthetic functional workflow; every model result has `can_clear: false`. |
| `run_empirical_xgboost_mlp_workflow.py` | Train native XGBoost and MLP models over repeated synthetic datasets, measure utility and attacks, and invoke the focused red-team registry. | Experimental empirical workflow; emits screens or attack floors and always returns `no_release_authorization`. |
| `run_public_privacy_audit.py` | Run the RAG-planned public-data CNN, LSTM, XGBoost, and compact Transformer privacy experiment. | Experimental worker requiring network access, experiment dependencies, and PyTorch; weak or null attacks never clear. See [public-data privacy workflow](../reproduction/README.md#public-data-privacy-workflow). |
| `llm_training_hooks.py` | Provide the shared bounded, aggregate-only PyTorch activation/gradient/loss hook collector used by the LLM and vision workers. It enforces an allowlist, event cap, complete per-step hook coverage, cleanup, and hash-chain replay without retaining tensors or examples. | Experimental support library imported by workers and tests; not a standalone release pipeline or public CLI. |
| `run_llm_training_hook_audit.py` | Sequentially fine-tune pinned DistilGPT2, OPT-125M, and Pythia-160M revisions for 512 steps each on the same deterministic 8,192-row projection from a digest-verified WildChat-4.8M shard; collect model-specific bounded aggregate activation/gradient telemetry; evaluate the untouched 1,024-row holdout before and after; and compare prior, metadata, loss, combined, and exact-roster knowledge profiles. | Experimental network/GPU worker using separate telemetry streams and a fresh run directory per invocation. Its disjoint 256-member/256-nonmember calibration and audit cells are underpowered, descriptive, noncausal, and nonmonotone; exact roster disclosure is separate; real human-user/ChatGPT content requires independent rights review; OPT's production/commercial legal gate is blocked; Pythia deployment requires policy/manual review; and no result clears or authorizes. See [training-hook designs and limits](../reproduction/README.md#training-hook-and-composition-designs). |
| `run_vision_training_hook_audit.py` | Train canonical torchvision AlexNet and DenseNet-121 from scratch for one epoch each on the complete deterministic 21,600-image training split from the digest-pinned 27,000-image EuroSAT RGB archive; evaluate the complete 5,400-image test split before and after; collect bounded aggregate hook telemetry; and run brightness, Gaussian-noise, and FGSM screens on 512 real test images. | Experimental network/GPU worker using a fresh run directory and separate telemetry ledger per architecture. It measures execution and scale over a real satellite-image corpus; one epoch and the bounded perturbations do not establish quality, privacy, security, robustness, fairness, or production readiness. Dataset/modified Sentinel terms remain under manual review, and every result is non-clearing and non-authorizing. See [training-hook designs and limits](../reproduction/README.md#training-hook-and-composition-designs). |
| `run_llm_composition_scaling.py` | Run fresh DistilGPT2/OPT-125M/Pythia-160M cells at 2,048, 4,096, and 8,192 WildChat training rows over five seeds, then evaluate seven same-roster output subsets and a separately labelled cumulative-exposure sensitivity path. | Experimental child worker with a bounded resumable journal and aggregate-only suite export. Subset contrasts use the mean of their constituent singleton results; protected-roster exposure and license/policy gates remain separate. |
| `run_vision_composition_scaling.py` | Run AlexNet/DenseNet-121 at 5,400, 10,800, and 21,600 EuroSAT training images over five seeds, with matched batch-size and hook/no-hook cells, probability-average output composition, real-image perturbations, and registered FGSM source-to-target transfer. | Experimental child worker. Hook effects, batch effects, ensemble screens, and attack transfer remain descriptive and cannot block, clear, or authorize. |
| `run_composition_scaling_suite.py` | Validate and optionally serialize both child workers, verify their completion manifests and aggregate exports, construct all 31 non-empty five-model resource/gate portfolios, and publish a final suite manifest last. | Experimental coordinator with a 12-hour/20-GiB fail-closed envelope. It composes scalars only within a shared protected-unit population; mixed-modality portfolios remain vectors. See [composition design and limits](../reproduction/README.md#training-hook-and-composition-designs). |

## Validation and maintenance

| Script | Purpose | Status |
|---|---|---|
| `check_markdown_links.py` | Verify that every repository Markdown link to a local file or directory resolves. | Maintenance check run by `make check`; external URLs and fragment identifiers are outside its scope. |
| `validate_framework_e2e.py` | Execute every console model/dataset combination through API, queue, trainer, attacks, evidence downloads, case checks and reassessment; test intake variants, mode switches, tampering, cancellation and retry. | Offline public-data integration matrix with retained Markdown/JSON results. Add repeated `--language-model` arguments for installed local Ollama models. Unsupported attacks remain explicit; execution success is not model safety or release authorization. |
| `generate_schema_manifest.py` | Replay every registered current JSON Schema and generate or verify the exact-byte schema inventory. | Maintenance check run by `make schemas`; release signing/attestation is an external protected-key operation. |
| `validate_llm_audit_profile.py` | Validate the LLM watermark/canary preregistration template and optionally enforce collection readiness. | Maintenance check and protocol linter; it does not execute an audit or emit scientific evidence. |
| `evaluate_knowledge_retrieval.py` | Measure deterministic retrieval hit rate and reciprocal rank over the repository knowledge index. | Maintenance evaluation for the RAG corpus. |
| `evaluate_protocol_mutations.py` | Run accepted controls and unsafe MRAP transcript mutations, then report the mutation score and non-claim. | Maintenance evaluation built from the protocol test suite; not a scientific adequacy result. |
| `refresh_example_contracts.py` | Deterministically regenerate the current policy, attack catalog/battery, hash-bound evidence, assessment report, and optimization request fixtures. | Maintenance generator only; it does not execute an attack or authorize a release. |
| `summarize_ceiling_experiments.py` | Validate the accepted controlled and model-backed result families and regenerate the allowlisted publication summary, paper table, and figure without exposing per-example material. | Replay/summary utility; derived output remains limited by the validated source reports and cannot create a new empirical claim. |
| `verify_formal_protocol.py` | Verify the Lean toolchain boundary, theorem inventory, proof build, and axiom audit. | Maintenance check; requires Lake/Lean for the complete proof replay. |

## Dependency guide

- Core validation and maintenance utilities generally use the package runtime
  from `requirements.lock`.
- OpenML, XGBoost, stochastic, and empirical workflows require
  `requirements-experiments.txt` or the `experiments` extra.
- The primary `run_training_release_demo.py` uses that experiment tier.
  `openml-sick` is its public, network-acquired default; use
  `sklearn-breast-cancer` for the offline integration profile. The secondary
  `run_government_health_demo.py` fixture rehearsal uses only core dependencies.
- The controlled ceiling runner uses the experiment dependency tier for exact
  interval calculations. Its default retained study executed 1,800 records;
  replay of the published result requires its frozen configuration, source,
  and runtime together, not merely the current package with an old JSON file.
- The model-backed ceiling runner additionally uses the public-privacy
  collector stack and PyTorch. Its compact Transformer is an LLM proxy, its
  target pools are small finite benchmark populations, and its repeated trials
  resample those same pools. The v3 role-aware resolution target applies only
  at absolute risk margin at least `0.10`; all observed v3 risks were below
  tolerance, so unsafe-side `BLOCK` power is outside that result.
- `run_public_privacy_audit.py` additionally requires the
  `privacy-experiments` extra and its PyTorch runtime.
- `run_llm_training_hook_audit.py` uses the `llm-experiments` extra (PyTorch,
  Transformers, tokenizers, safetensors, and PyArrow) in an isolated experiment
  environment; its report records the exact resolved runtime.
- `run_vision_training_hook_audit.py` uses the `vision-experiments` extra
  (PyTorch and torchvision). Its registered full-EuroSAT execution requires
  the exact CUDA runtime declared by the experiment; the focused CI tier is a
  CPU-only contract/hook test and neither downloads nor trains on EuroSAT.
- The composition-scaling coordinator uses both experiment tiers. Its focused
  tests validate configuration, closure, journaling, authority, and export
  contracts without downloading data or executing the registered GPU matrix.
- The live MCP server requires the `mcp` extra; the worker scripts themselves
  remain separate processes.
- Formal proof replay requires the Lean toolchain pinned under `formal/lean/`.

See [`reproduction/README.md`](../reproduction/README.md) for the retained-input
maturity matrix and [`tests/README.md`](../tests/README.md) for test coverage and
dependency tiers.
