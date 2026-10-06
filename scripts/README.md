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

The paper builders, finite-construction checks and current manuscript are in
the [separate academic repository](https://github.com/elmontu/AI_Model_Academic).
They are research tools, not part of the government console installation or
its supported release process. Historical versions remain in Git history.
The [dated advisory archive was retired](../docs/government-academic-separation-plan-2026-10-01.md#retired-28-september-archive)
from this checkout. Its reporting snapshots and verifier remain in Git history;
they are not required by the current government checks.

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

Run [PRD-11 cross-sector benchmarks](../docs/production-prd11-adapter-benchmarks.md)
with `python scripts/benchmark_research_adapters.py --data-root D:/model_audit_data
--output .local/research-adapters-v1`. The command reads fixed public prepared
research samples, runs bundled classification/regression fixtures and reports
missing profiles. It never downloads data or writes into the research root.
Replay a saved case with `python scripts/replay_native_adapter.py --run
.local/research-adapters-v1/cases/acs`. Neither command authorizes a release.

The [PRD-10 job rehearsal](../docs/production-prd10-durable-jobs.md) runs with
`python scripts/rehearse_fixture_jobs.py --output .local/fixture-jobs-v1`. It uses
only the exact public counts fixture, real ephemeral credentials and a fixed
child worker. Fresh output is required; failed evidence is retained. Its durable
job history does not restore identity/storage authority or establish cloud isolation.

| Script | Purpose | Status |
|---|---|---|
| `verify_build_baseline.py` | Capture current nonignored government source plus tracked deletions and verify two offline wheel builds with pinned local tools, source/member hashes and RECORD checks. See [PRD-03](../docs/production-prd03-source-build-baseline.md). Outputs use a fresh ignored `.local/` directory. | Maintenance check; unsigned local evidence, not production attestation or publication. |
| `run_required_tests.py` | Execute the required government CI profile, including red-team/discovery, all temporal suites and PRD-05 through PRD-18 infrastructure, identity, storage, key-trust, build-control, durable-job, native/external-adapter, authenticated-evidence and registration tests; fail on missing/empty suites, import errors, skips, tolerated failures or blueprint/runtime-lock drift. Write a log and JSON result to a new ignored `.local/` path. See [PRD-04](../docs/production-prd04-required-ci.md). | Maintenance/CI gate; public/synthetic tests, not agency authorization. |
| `validate_infrastructure_plan.py` | Validate strict provider-neutral design JSON and print its hash and blockers. See [PRD-05](../docs/production-prd05-infrastructure-scaffold.md). | Read-only preparation; always non-deployable, no agency authorization. |
| `rehearse_local_deployment.py` | Exercise isolated local dev/staging stores, loopback API/worker readiness, queued fictional preflight, restart persistence and owned-process shutdown in a new ignored `.local/` path. | Public fixture only; no cloud provisioning or private-data/model-delivery authority. |
| `check_markdown_links.py` | Verify that every repository Markdown link to a local file or directory resolves. | Maintenance check run by `make check`; external URLs and fragment identifiers are outside its scope. |
| `validate_framework_e2e.py` | Execute every console model/dataset combination through API, queue, trainer, attacks, evidence downloads, case checks and reassessment; test intake variants, mode switches, tampering, cancellation and retry. | Offline public-data integration matrix with retained Markdown/JSON results. Add repeated `--language-model` arguments for installed local Ollama models. Unsupported attacks remain explicit; execution success is not model safety or release authorization. |
| `verify_build_supply_chain.py` | Verify exact wheel locks and dependency closure, generate SBOM/license evidence, and require complete current PyPI advisory observations. See [PRD-09](../docs/production-prd09-build-controls.md). | Public-package metadata requests only; fresh ignored local output; no installation or production approval. |
| `verify_build_provenance.py` | Bind actual repeat-build/test/artifact evidence in an ephemeral-key signed fixture and evaluate fail-closed local admission. | No private-key file or production trust; pending licensing remains an explicit blocker. |
| `generate_schema_manifest.py` | Replay every registered current JSON Schema and generate or verify the exact-byte schema inventory. | Maintenance check run by `make schemas`; release signing/attestation is an external protected-key operation. |
| `validate_llm_audit_profile.py` | Validate the LLM watermark/canary preregistration template and optionally enforce collection readiness. | Maintenance check and protocol linter; it does not execute an audit or emit scientific evidence. |
| `evaluate_knowledge_retrieval.py` | Measure deterministic retrieval hit rate and reciprocal rank over the repository knowledge index. | Maintenance evaluation for the RAG corpus. |
| `evaluate_protocol_mutations.py` | Run accepted controls and unsafe MRAP transcript mutations, then report the mutation score and non-claim. | Maintenance evaluation built from the protocol test suite; not a scientific adequacy result. |
| `refresh_example_contracts.py` | Deterministically regenerate the current policy, attack catalog/battery, hash-bound evidence, assessment report, and optimization request fixtures. | Maintenance generator only; it does not execute an attack or authorize a release. |
| `summarize_ceiling_experiments.py` | Validate the accepted controlled and model-backed result families and regenerate the allowlisted publication summary, paper table, and figure without exposing per-example material. | Replay/summary utility; derived output remains limited by the validated source reports and cannot create a new empirical claim. |
| `verify_formal_protocol.py` | Verify the Lean toolchain boundary, theorem inventory, proof build, and axiom audit. | Maintenance check; requires Lake/Lean for the complete proof replay. |

## Authenticated local replay evidence

`python scripts/rehearse_execution_evidence.py --output .local/evidence-v1`
authenticates fresh public numeric replay operations with exact job, policy,
runtime and artifact bindings, current signer trust and durable one-use challenges.
Use `--benchmark .local/verification/prd11-adapters-20261001/research-benchmark`
to replay all eight retained public profiles without changing their files.
[PRD-12](../docs/production-prd12-authenticated-evidence.md) explains the local
scope: production image/isolation admission is refused, and original training
is not attested. New output must remain under this D: government checkout.

## Prospective public model registration

`python scripts/rehearse_model_registration.py --output .local/model-registration-v1`
registers the pinned Wine fixture before fitting its fixed native recipe. Add
`--all-profiles --data-root D:/model_audit_data` to exercise all eight pinned
public profiles, with up to 4,096 selected rows per profile. The research root is
read-only; each run requires a fresh ignored output directory in this government
checkout. The command offers no arbitrary model import or private-data intake.

[PRD-13](../docs/production-prd13-model-registration.md) binds source/sample
lineage, the frozen plan and descriptive utility rule, signed replay evidence,
and local registration/disclosure history. External disclosure history stays
unknown, and population, protected-unit and non-DP limitations remain explicit.
A recorded review cannot clear or authorize a candidate. Production qualification
remains in progress.

## Scoped SACRO-ML comparison

`python scripts/rehearse_sacro_adapter.py --python <isolated-env-python> --output
.local/sacro-v1` runs the pinned SACRO-ML 2.0.1 probability-membership comparison
in its separately prepared dependency environment. It reads the retained PRD-13
case roster by default; `--benchmark` selects another eligible roster location.
The parent re-observes pinned public source bytes through `--data-root` (default
`D:/model_audit_data`) and reconstructs the native data/plan binding. The recorded
SACRO interpreter is `.local/verification/prd14-sacro-20261001/sacro-env/Scripts/python.exe`.
New output stays in a fresh ignored government `.local/` directory. It does not
install dependencies, fetch datasets or load a SACRO pickle/`Target.load` model.

[PRD-14](../docs/production-prd14-sacro-adapter.md) freezes three attack repetitions,
positive/null probability controls and exact native comparison groups. Independent
calculations replay retained scores and counts. All eight profiles receive a
disposition: seven classifier profiles are applicable and Diabetes regression is
unsupported. A subprocess deadline is not a hostile-code sandbox or platform
attestation. No result provides clearance or agency authorization.
[PRD-15](../docs/production-prd15-registry-transactions.md) now adds the local
registry/migration/outbox rehearsal; [PRD-16](../docs/production-prd16-witness-recovery.md) adds witness recovery; [PRD-17](../docs/production-prd17-policy-review.md) adds bound policy review; PRD-18 is next.

## Dependency guide

- Core validation and maintenance utilities generally use the package runtime
  from `requirements.lock`.
- The PRD-14 SACRO comparison uses its separate fully pinned external runtime;
  provide that environment's interpreter with `--python`. Its preparation and
  license/advisory evidence are separate from the core runtime and an agency
  deployment approval.
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

## Registry transactions

`python scripts/rehearse_registry_transactions.py --output .local/registry-v1`
rehearses signed fictional count commits, shared engineering charges, explicit
SQLite schema migration, broker fencing and lost-ack outbox recovery. It accepts
no data/model/policy input and preserves existing outputs. The local receiver
deduplicates events; it is not an independent witness. See
[PRD-15](../docs/production-prd15-registry-transactions.md) for limits and production
gates. [PRD-16](../docs/production-prd16-witness-recovery.md) adds witness recovery; [PRD-17](../docs/production-prd17-policy-review.md) adds bound policy review; PRD-18 is next.

## Witness and intent recovery

`python scripts/rehearse_witness_recovery.py --output .local/witness-v1` runs a
signed fictional registry/witness workflow, retains exact checkpoint files,
recovers a committed outcome after witness outage and rejects old registry/witness
copies and a replacement ledger. It accepts no external dataset/model/policy input.
See [PRD-16](../docs/production-prd16-witness-recovery.md) for custody assumptions,
full-history limits and production acceptance. Next is PRD-18, the sole controlled-delivery route.

## Bound policy review rehearsal

`python scripts/rehearse_policy_review.py --output .local/policy-review-v1`
requires current signed policy approval before a fresh public Wine fit and
authenticated replay, then records distinct independent acknowledgments with
exact policy/candidate/recipient bindings. Scoped delegation, current revocation,
retained outcome history and weakening/reuse denials remain non-authorizing.
See [PRD-17](../docs/production-prd17-policy-review.md) for limits and production
acceptance. PRD-18 controlled delivery is next.

## Controlled delivery rehearsal

`python scripts/rehearse_controlled_delivery.py --profile local_public_fixture --output .local/controlled-delivery-v1`
runs fresh reviewed public Wine training and signed replay, then exact bounded
candidate chunks through current human-recipient grants and durable admissions.
The default production profile is refused before output creation. Lifecycle,
interrupted-write, bypass and checkpoint-restore checks remain non-authorizing.
See [PRD-18](../docs/production-prd18-controlled-delivery.md) for scope and pending
agency acceptance.

## One public profile end to end

Run scripts/rehearse_public_profile.py with explicit --profile local_public_fixture,
--python pointing to the pinned SACRO interpreter and --output a new .local child.
It requires fresh native and external results before bound independent review and
exact fixture delivery. A signed historical receipt replays under external pins
without restoring permissions. Default production refuses before output.
See [PRD-19](../docs/production-prd19-end-to-end-profile.md) for commands and limits.

### Redacted monitoring and incident rehearsal

rehearse_monitoring.py requires explicit local_public_fixture profile and a new
ignored .local output. It injects original-worker, key, public-object and witness
faults, persists redacted alerts and exercises local receiver/incident recovery.
Production execution is refused; it sends no external alerts.
See [PRD-20](../docs/production-prd20-monitoring-incidents.md) for commands and runbooks.

### Capacity and recovery rehearsal

rehearse_capacity_recovery.py requires explicit local_public_fixture profile
and a new ignored .local output. It measures fixed tiled public Wine I/O and
real public-count jobs at concurrency1/2/4, verifies witnessed historical
backup/restore and tests delivery-context restart denials. Measurements do not
qualify agency scale or cloud failover.
See [PRD-21](../docs/production-prd21-capacity-recovery.md) for commands and limits.
Next is PRD-22, independent security and evidence assessment.

## Independent assessment handoff

rehearse_independent_assessment.py requires explicit local_public_fixture profile
and a new ignored.local destination. Eleven fresh public-native probe families,
externally pinned local packet integrity and signed current finding-review checks
remain non-authorizing. Production blockers cannot be closed by fixture review.
See [PRD-22](../docs/production-prd22-independent-assessment.md) for scope and commands.
Next is PRD-23, the restricted pilot plan; agency assessment remains pending.

## Restricted pilot planning

rehearse_restricted_pilot.py requires explicit local_public_fixture and a new
ignored.local destination. It binds fresh public assessment evidence to one
immutable named plan, seven signed people and scoped local suspension/withdrawal.
All agency admission, query and pilot-delivery gates remain closed. See
[PRD-23](../docs/production-prd23-restricted-pilot.md). Next is PRD-24 handover.

## Pilot exit review and operational handover preparation

rehearse_pilot_handover.py requires explicit local_public_fixture and a new
ignored.local destination. It creates fresh pinned public assessment evidence,
requires a current seven-person acknowledged plan and exercises independent
handover preparation, original roster expiry and terminal local retirement.
Capacity/cost and agency exit remain pending. Production defaults refuse before
output. See [PRD-24](../docs/production-prd24-operational-handover.md) for commands,
operational declarations and the acceptance boundary. PRD-25 ART adapters are next.
