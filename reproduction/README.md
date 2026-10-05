# Reproduction assets

This is the study index for committed configurations, provenance records, and
retained aggregate results. A configuration, plan, queue entry, or partial
journal is not evidence that an experiment completed. Historical results apply
to their recorded source and runtime; they do not validate the current MRA 0.8
implementation, establish a complete privacy taxonomy, or authorize release.

Generated datasets, caches, trained models, raw measurements, and audit stores
remain outside the published evidence set, normally under ignored `output/`
paths. The [ceiling publication summary](ceiling-experiment-summary.json) and
[2026-09-02 training-hook execution audit](../docs/real-data-training-hook-audit-2026-09-02.md)
are explicit aggregate-only publication exceptions in this repository.
Retained failures are evidence, not obsolete files to erase after a corrective
run or code fix.

<a id="paper-draft"></a>

## Academic paper and companion

The manuscript, paper-building scripts, and research tests belong to the
[separate academic repository](https://github.com/elmontu/AI_Model_Academic).
This government repository retains the later
[technical interpretation](../docs/advisory/technical-report-2026-10-01.md).
The [28 September advisory archive was retired](../docs/government-academic-separation-plan-2026-10-01.md#retired-28-september-archive)
from this checkout at the user's request. Its tables, source references and
verifier remain in Git history; that reporting snapshot did not include all
original model weights, data or later study results.
Older paper drafts and assembly instructions remain in Git history. Their
historical hashes and measurements were not restamped by this separation.

<a id="academic-plan"></a>

## Academic evaluation plans

Current study protocols, manuscript sources and research-only execution tools
are maintained in the [academic repository](https://github.com/elmontu/AI_Model_Academic).
A plan or configuration is not a completed experiment. The government
implementation uses its own [case and release workflow](../docs/government-audit-guide.md),
and the [advisory report](../docs/advisory/technical-report-2026-10-01.md)
records the limits of completed research evidence. Prior plan text remains in
Git history for provenance.

## Asset matrix

| Area | Retained status | Inputs, results, and entry point |
|---|---|---|
| Controlled finite-channel ceiling | Completed historical result: 1,800 aggregate records; 1,200 primary analyzer replays; three full Engine integrations. The safe, boundary, and unsafe families each produced the registered decision in 400/400 repetitions. | [Configuration](finite-channel-ceiling/config.json), [registration](ceiling-experiment-preregistration.json), [report](finite-channel-ceiling/results/ground-truth-report.json), [manifest](finite-channel-ceiling/results/manifest.json); `scripts/run_finite_channel_ceiling_experiment.py`. |
| Model-backed finite-channel ceiling | Completed historical v3: all 10 criteria passed; six primary Engine integrations and 1,200 repeated analyzer replays. V2's 8/9 negative result remains preserved. | [V3 configuration](model-backed-finite-channel/config.json), [registration](model-backed-finite-channel/v3-preregistration.json), [report](model-backed-finite-channel/results/v3/model-backed-finite-channel-report.json), [manifest](model-backed-finite-channel/results/v3/manifest.json), [v2 report](model-backed-finite-channel/results/v2/model-backed-finite-channel-report.json); `scripts/run_model_backed_finite_channel.py`. |
| OpenML-CC18 | Registered design, not a sealed completed study. The 72 dataset-manifest entries are not completed training runs. | [Configuration](openml/config.json), [suite manifest](openml/manifests/suite-99-datasets.json), [subset manifest](openml/manifests/expensive-subsets.json), [provisional runtime](openml/runtime.json); [OpenML script stages](../scripts/README.md#openml-reproduction-study). |
| LLM training hooks | Configured historical three-model experiment; curated execution observations are separately identified above. | [Pinned WildChat/model configuration](llm-training-hook/config.json); `scripts/run_llm_training_hook_audit.py`. |
| Vision training hooks | Configured historical full-EuroSAT experiment; curated execution observations are separately identified above. | [Pinned archive, split, model, and runtime configuration](vision-training-hook/config.json); `scripts/run_vision_training_hook_audit.py`. |
| Composition scaling | Configured historical five-model, three-scale, five-seed design; no completed suite is established by these inputs. | [Suite configuration](composition-scaling/suite-config.json), [LLM configuration](composition-scaling/llm-config.json), [vision configuration](composition-scaling/vision-config.json); `scripts/run_composition_scaling_suite.py` or the two child workers. |
| Stochastic portfolios | Configured benchmark; generated rows and analyses are not retained here. | [Configuration](portfolio-stochastic/config.json); `scripts/run_portfolio_stochastic_benchmark.py`, then `scripts/analyze_portfolio_stochastic_benchmark.py`. |
| Strategic assurance | Configured exact-rational incentive and monitoring stress test; no governance decision or authorization. | [Configuration](strategic-assurance/config.json); `scripts/run_strategic_assurance_experiment.py`. |
| XGBoost | Template requiring an approved local CSV/Parquet snapshot and fresh bindings; no dataset or result retained here. | [Configuration template](xgboost/config.example.json); `scripts/run_xgboost_audit.py`; [XGBoost guide](../docs/xgboost.md). |
| LLM watermark/canary | Template with replacement markers, zero digests, and unset collection fields; not collection-ready evidence. | [Profile directory](llm/); `scripts/validate_llm_audit_profile.py --collection-ready` only after completing and independently approving the required bindings; [protocol guide](../docs/llm-watermark-canary.md). |
| Model-audit workflow | Inert executable examples plus a configured empirical experiment. Generated results are not retained here. | [Sample manifest](model-audit-workflow/manifest.json), [empirical configuration](model-audit-workflow/empirical-xgboost-mlp-config.json); `scripts/run_sample_model_audit_workflow.py`, `scripts/run_empirical_xgboost_mlp_workflow.py`. |
| Public-data privacy | External-data workflow only; its plan, datasets, models, scores, and report are generated locally. | `scripts/run_public_privacy_audit.py`; see [workflow limits](#public-data-privacy-workflow). |

## Frozen replay and new runs

Run commands from the repository root in an isolated experiment environment.
The [script catalog](../scripts/README.md) lists entry points and dependency
tiers. A current compatibility range is not a historical environment lock.

- To reproduce a retained study, recover the source snapshot and exact
  configuration, data/model digests, runtime, and sampling plan named by its
  registration and completion manifest. An unavailable binding makes that
  replay incomplete; installing current dependencies does not repair it.
- Several hook/composition registrations still pin workers and runtime bytes
  from before the MRA 0.8 fixes. Their hash checks must reject changed workers.
  For new measurements, approve a separate prospective registration before
  observing outcomes, capture the new source/runtime, and use fresh output
  paths. Never repin an old registration or rewrite its results retroactively.
- Keep full source and run provenance, the required completion marker, and
  independently replayed artifact digests. LLM and composition runs publish
  `RUN_COMPLETE.json` last; the original vision worker uses its final JSON
  report as the completion signal. A partial run is not a completed result.
- `--offline`, where supported, requires a previously verified cache. It is
  not operating-system network isolation. Never provide experiment workers
  with deployment credentials or signing keys.
- Cache confidentiality, retention, and deletion need operator controls.
  Aggregate-only reports do not imply aggregate-only caches. On Windows the
  portability path does not verify POSIX permission modes or ACL protection,
  and does not promise directory-fsync durability; successful file publication
  does not establish either property.

## Ceiling result interpretation

The [retained ceiling summary](ceiling-experiment-summary.json) are
derived from the retained source reports by
`scripts/summarize_ceiling_experiments.py`. Keep those publication artifacts and
their source reports byte-identical; do not edit a measured value in prose to
make a result pass.

- Controlled model-family names are labels for exact predeclared channels,
  not evidence that real CNNs, XGBoost models, or LLMs were tested there.
  Zero observed undercoverage is not proof of zero failure probability.
- Model-backed v3 was prospectively frozen after the v2 failure, with fresh
  model and sampling seeds. It uses one artifact per family and finite pools
  of 400 `IN`/400 `OUT` records for CNN/XGBoost and 350/350 for a compact
  Transformer proxy. Repeated analyzer trials resample these same pools;
  they are not independently trained replications or a population-transfer test.
- V3 observed exact count agreement between its one-use Python wrapper and
  aggregate sampler. That is not a proof of deployed endpoint, process,
  authentication, timing, query-budget, or OS equivalence.
- All six v3 oracle risks were below tolerance. Four families at absolute
  margin at least `0.10` resolved in the correct direction 200/200 times;
  near-boundary holds are retained. V3 does not establish model-backed
  unsafe-side `BLOCK` power; only the controlled `0.80` channel supplies that
  evidence. All ceiling studies used experimental attack-battery waivers and
  grant no authorization.

## Training-hook and composition designs

The retained LLM design fine-tunes pinned DistilGPT2, OPT-125M, and Pythia-160M
on the same deterministic 8,192-row WildChat projection, with 1,024 holdout
rows and 512 optimizer steps per model. Its 256-member/256-nonmember calibration
and disjoint audit cells support descriptive knowledge-profile screens, not
clearance, causal comparisons, or a monotone empirical risk ladder. Exact
roster exposure is a separate direct-disclosure scenario, not an attack score
to average with weaker screens. Recipient interfaces and assessor access are
different: text generation alone does not imply arbitrary-candidate scoring.

The source contains real user/assistant text. Eligibility and deduplication
filters do not establish safety, deidentification, or rights in the content.
The cache retains the complete Parquet shard, including fields excluded from
the training projection. The pinned OPT license is restricted to non-commercial
research; Pythia's model card requires separate deployment-policy review.
Dataset/model license declarations are not a grant of production clearance.

The vision design uses all 27,000 EuroSAT RGB images with a deterministic
class-stratified 21,600/5,400 train/test split, resized to 96x96, and canonical
from-scratch AlexNet/DenseNet-121 for one epoch each. Exact duplicate images
are checked, but the split is not spatially separated. The registered runtime
is an exact EC2 baseline, not a portable version-number claim. Its paired
noninterference check is CPU-only; allowed CUDA nondeterminism explicitly
precludes a bitwise-reproducibility claim. Brightness, Gaussian-noise, and FGSM
screens on 512 test images cannot establish robustness or privacy. EuroSAT and
modified Sentinel terms still require independent review.

The composition design contains 45 LLM training cells and 120 vision cells
(30 reference cells plus 90 matched batch/hook controls), across five seeds
and three nested scales. It evaluates seven LLM and three vision output subsets
within their respective common populations. All 31 nonempty five-model
portfolios use resource/gate vectors; mixed-modality AUC, accuracy, or privacy
risk must not be pooled. Nested subsets, repeated scoring, and matched controls
are not additional independent population replications. No completed suite is
claimed here, and training throughput alone does not validate full MRAP
lifecycle scalability.

All hook reports retain bounded aggregate telemetry, verify coverage and
cleanup, and remain non-authorizing. Those checks are software observations,
not trusted workload attestation or proof that unobserved channels cannot leak.

## OpenML design

The suite/source manifests record dataset identifiers, versions, checksums,
targets, and dimensions. Raw snapshots, trained artifacts, complete outputs,
witness rows, and a valid final study seal are not retained. The historical
runtime tuple is provisional, not a lock or the current CI compatibility band.
The acquisition runtime also does not describe every later training stage.

Use the cataloged acquisition, deterministic subset selection, structural,
membership, neural, composition, metadata-adversary, DP-SGD, multi-shadow,
inference, population-validation, and witness-building/replay stages. A
replacement final sealer and exact new runtime must be prospectively
registered; preserve the old records separately. DP-SGD preprocessing is
outside that design's private-mechanism claim, the LiRA-style tier is not a
complete augmented online LiRA protocol, and controlled inference is not
full-record reconstruction or validation of a deployment-population frame.

## Public-data privacy workflow

`scripts/run_public_privacy_audit.py` uses public datasets for CNN, LSTM,
XGBoost, and compact-Transformer target/reference experiments, optionally with
a hash-bound RAG-generated plan. It needs network access and the
`privacy-experiments` runtime. Use `--output-dir` and `--cache-dir` to place
fresh artifacts under governed ignored paths; the legacy default cache is
`reproduction/public-privacy/raw`, not a retained publication dataset.

Its generated report contains source/snapshot/runtime bindings, raw losses,
and calibrated attack floors or screens. No such completed report is committed
here. A floor may support a blocking decision only after the required evidence
admission and statistical checks; weak attacks cannot supply a ceiling or
clear a threat. The worker ends with `no_release_authorization`.

<a id="evidence-boundary"></a>

## Claims that these assets do not establish

No study here proves universal model coverage, external-population privacy,
full lifecycle execution, current Python-to-Lean refinement, or deployed
registry/gateway enforcement. A handwritten conditional argument is not an
implementation proof; a signature binds bytes, not the truth of experimental
premises. Assessment, optimization, workflow replay, and study completion are
not serving permissions. Current automated coverage is indexed in
[`tests/README.md`](../tests/README.md).
