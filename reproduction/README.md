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
and the paper's aggregate companion are explicit aggregate-only publication exceptions. Retained failures are
evidence, not obsolete files to erase after a corrective run or code fix.

<a id="paper-draft"></a>

## Research paper draft and evidence companion

The canonical manuscript is [academic/paper/mra-paper.tex](../academic/paper/mra-paper.tex), with
[verified primary references](../academic/paper/references.bib),
[generated tables](../academic/paper/experimental-tables.tex), a
[vector scaling figure](../academic/paper/figures/academic-scaling.pdf), and the
[complete bounded aggregate inventory](../academic/paper/experimental-data.json).
There is no second Markdown manuscript. The title is *Model Governance for
Government Bodies: An Evidence-Bound Release Assurance Protocol*. The paper
studies an accountable public body's authorization of model use, update and
renewal. Privacy is its worked technical assurance case, not a mathematical
replacement for all model-governance duties. The three questions concern
institutional authorization conditions, privacy floor/ceiling uncertainty, and
which components the available model evidence supports while institutional
validation remains unperformed.

The normative, jurisdiction-neutral government profile records accountable authority,
purpose and impact review, procurement/vendor limits, human oversight and
redress, transparency with justified exemptions, monitoring and retirement.
Mandatory obligations must be evidenced by their due lifecycle stage. Privacy
RELEASE does not confer institutional authorization, and accepted residual
privacy risk cannot waive mandatory legal or rights obligations. Governmental
and research sources inform the design; citing them does not establish legal
compliance, agency approval or the effectiveness of an institution's practice.
It does not add an implemented government-policy checker to the current core.

The draft uses unmodified IEEEtran
1.8b `conference,compsoc` formatting and is oriented toward IEEE S&P. The
[S&P 2027 call](https://sp2027.ieee-security.org/cfpapers.html) permits up to
13 main-text pages and five additional reference/appendix pages. Human
authorship, source/claim validation, ethics review and venue-specific AI-use
disclosures still need to be finalized before submission. The full protocol,
pseudocode, proofs and retained aggregate tables now exceed that appendix
allowance: this is explicitly an **extended research draft**, not a
submission-length paper. No layout compression or evidence removal is used
to disguise the difference.

[Section 3](../academic/paper/protocol-section.tex) integrates seven safeguards into
admission and transition rules. The [protocol appendix](../academic/paper/protocol-appendix.tex)
contains six pseudocode procedures, proofs of the six main guarantees and
seven gap arguments, including general observation-relative and fixed-budget
threshold limits. A no-go result justifies only its scoped refusal; it does
not authorize release or claim that no stronger observation model can work.
Implementation and evaluation methods are presented together. The main results
test technical protocol obligations and distinguish privacy-ceiling validity from decision
resolution, retaining the primary finite-construction and ceiling-study tables.
Detailed model workloads, CLI timings, software provenance, proof inventory and
complete supplementary aggregate tables remain in the appendices. Moving those
details does not change their source vintages or make them evidence for a
stronger theorem. Historical positive, adverse and unsupported results are
preserved, not rerun or relabelled as current production evidence.
There is no government field study in this evidence set. A workload or finite
privacy result is not a measurement of procurement quality, public legitimacy,
fairness, redress effectiveness or compliance.

The separate [September 9 independent synthetic model study](independent-models-synthetic-v1/README.md)
completed 168 fresh model fits under a locally frozen registration. Its own
companion retains every selection and rejected candidate, including severe
loss of useful selections near the threshold. The
[local lifecycle reference](../docs/lifecycle-reference-verification.md) adds
37 passing regression checks of transactional mechanics, with no integrated
serving or production authorization claim. These are new evidence layers;
they do not replace the historical experiments or Lean receipts.

From the repository root, compile the retained TeX, bibliography and figure
with Tectonic (or an IEEEtran-capable LaTeX installation):

```bash
tectonic --untrusted --outdir output/pdf academic/paper/mra-paper.tex
```

Create `output/pdf` first if absent. Tectonic may fetch standard TeX packages;
`--only-cached` permits offline compilation after that first build. The output
is `output/pdf/mra-paper.pdf`. The retained tables and figure are sufficient
for typesetting; no model training, dataset download or MRA installation is
needed. An isolated compiler was used locally; it is not a core dependency.

The new [gap-construction artifact](../academic/paper/gap-construction-results.json)
is separate from historical empirical data. Reproduce it offline with
`python academic/scripts/check_academic_gap_constructions.py --check` using only the
standard library. It checks complete finite decoder classes, multiplicity,
scope residuals, joint XOR leakage, TV/metric boundaries, 93,312 reducer-grid
cases plus ten named boundaries, and ideal-authentication semantics. Counts
have different units; they are not a pooled model privacy success rate.
Six strict-selection controls and five grant/revocation interleavings are
reported separately from those reducer counts and semantic worlds.
These checks validate finite constructions, not Python refinement or deployed
measurement truth. The [gap table](../academic/paper/gap-tables.tex) is generated from
this separate artifact by the same manuscript table builder.

To regenerate the data-derived tables and figure, use Python with the optional
`reportlab` package and run `python academic/scripts/build_academic_paper.py`. Add
`--check` to compare generated bytes. The figure uses Windows Times when
available and a Times-Roman fallback elsewhere, so byte-identical figure
regeneration requires the same fonts and renderer. These are document tools,
not new MRA runtime dependencies.

The companion contains 109 hashed source records, 63 tables and 4,754 rows,
including all 4,200 retained aggregate finite-channel replay rows. It preserves
the failed v2 criterion, unsealed legacy outputs and rejected launcher-memory
measurements with explicit status labels. Values have source-field pointers;
curated historical hook values retain their original rounding. Configured-only
and incomplete studies are explicitly excluded from completed-result claims.
This is not a claim that every historical raw artifact is retained or public.

`python academic/scripts/build_academic_paper_data.py --check` additionally reconstructs
the companion from its allowlisted original sources. Some are local ignored
`output/` files: a clean clone can inspect the retained companion and rebuild
the tables, but cannot independently repeat every source-hash check without
those originals. Hashes are not authenticated measurement certificates. Raw
dialogue, images, per-example losses, rosters, weights and keys are excluded;
any future release of underlying materials needs its own rights, privacy and
anonymization review. No corrected end-to-end scalability experiment or new
machine-checked theorem was created by writing this draft.

The academic directory separates manuscript work, assembly tools and consistency
tests from the shared runtime. Historical source paths in the companion remain
relative to the repository root. The relocation updates generator locations and
their byte hashes; retained observations, source hashes and claim boundaries are
unchanged. Run `python -m unittest discover -s academic/tests -v` from the
repository root for the academic checks; `make test` includes both test directories.
The compiled PDF and compiler output belong in ignored `output/pdf/`, separately
from the committed paper sources and retained aggregate artifacts.

<a id="academic-plan"></a>

## Academic-first evaluation plan — proposed, not executed

This is the academic track's prospective research plan, not a registration or
completion report. It adds no measured results to the historical inventory below.
The priority is a defensible claim, its explicit assumptions, a reproducible
check, and an adversarial attempt to falsify it. Production engineering is a
separate industrial track; deferring it does not remove its proof obligations.

### Research questions and publication exit criteria

| Research question | Existing proof/evidence and its boundary | Proposed evaluation and publication exit criterion |
|---|---|---|
| RQ1: Under which conditions may a government body authorize model use, update or renewal? | The normative profile binds accountable authority, stage-due evidence and review to an ordered lifecycle. [Lean results](../docs/formal-verification.md) concern abstract semantics and [regressions](../docs/gap-remediation.md) specific software paths; neither proves the truth or legal adequacy of institutional decisions. | Freeze the applicable authority, purpose, obligations, review roles and renewal/invalidation rules. Independently examine representative governance cases and evidence gaps under an approved study design. Treat institutional validation, legal review and implementation refinement as separate requirements, not consequences of the privacy theorem. |
| RQ2: How should privacy floor/ceiling evidence represent uncertainty within that governance decision? | The technical case separates demonstrated attack capability from a valid upper bound, and coverage from decision resolution. The failed v2 criterion and near-boundary v3 holds remain evidence; all v3 oracle risks are below tolerance, so model-backed unsafe-side power is not established. | Preregister the privacy game, full joint export, selection/error allocation, margins and safe/unsafe controls. Report widths, holds and failures together. Privacy RELEASE remains a scoped recommendation; accepted residual privacy risk cannot substitute for any mandatory institutional obligation. |
| RQ3: Which components do existing tree, image and language-model results validate, and what institutional validation is missing? | Historical workloads show bounded execution and scoped attack floors; ceilings of one do not clear privacy. Finite-channel studies and signed offline fixtures have different evidence boundaries. No government field study or agency approval is established. | Evaluate faithful collection and complete reference paths on their technical merits, and separately register any study of review, oversight, procurement, redress or public-sector use. A future corrected full-chain scalability study needs complete traces and independent repetitions. Existing component results cannot be relabelled as public-sector validation. |

Before using novelty or superiority language, compare the proposed claim and
assumptions with the [primary-source literature](../docs/literature-review.md).
Select baselines by the property they actually enforce. A faster system that
omits validation is not a like-for-like competitor. Where no comparable
implementation exists, publish the conceptual comparison and state that a
performance superiority claim was not tested.

### Correctness and stated-model completeness study

The study must distinguish kernel-checked theorems, handwritten conditional
arguments, executable finite checks, and observed software behavior. Rebuilding
Lean and passing Python tests are separate tasks; vocabulary correspondence is
not a refinement proof. Preserve the [mathematical premises](../docs/mathematical-foundations.md),
including statistical coverage events and the admissibility of transferred
decision rules. Publish both non-vacuous accepting controls and refusing cases.

The first proof deliverable is the four-verdict partition and precedence rule:
missing/invalid evidence and blocking floors cannot be overridden; signed risk
acceptance is outside the ordinary below-threshold clearance theorem. Any
false-RELEASE probability claim must cover every selectable candidate–threat
and release/time claim under the actual selection and stopping procedure, not
only the candidate retained after looking at outcomes. State the inclusion of
false-release events in registered failure events as an assumption or prove it;
the finite union-bound theorem does not discharge that premise. Standard
Blackwell and union-bound results are foundations, not claimed new contributions.

The preregistered counterexample families should include missing or reordered
stages; changed upstream evidence with stale downstream signatures; wrong
policy/game/population; absent battery/control evidence; hash/signature failure;
source substitution; expired or revoked acceptance; exact threshold equality and
one-unit rational perturbations; contradictory bounds; and an optional-but-in-scope
threat whose floor exceeds tolerance. Test all four governance dispositions with
genuine engine-produced evidence, not only mocked interval objects. Use separate
test keys and synthetic institutional actors; successful authentication in that
test environment does not validate a real authority.

Mathematical negative controls must also challenge the scientific premises:
weak attacks cannot supply ceilings; maxima across attacks and repeated looks need
valid family/lifetime allocation; average risk does not bound a worst allowed
subgroup; and marginal channel bounds do not bound a joint export (for example,
the two-share XOR construction). Reproduce exact finite constructions where
possible. A finite mutation score measures only the registered case family.
Add a prospectively frozen generative transition/input campaign with disclosed
search budget and seed schedule; zero found violations is not exhaustiveness.

For completeness, define the approved universe before collecting outcomes.
Threat names such as membership and attribute inference may overlap. If using
membership-profile atoms to form a partition, retain the all-false residual atom
and explain the predicates' semantic adequacy separately. Every in-scope scenario
must have decision evidence in the same game; every exclusion needs a reason.
An unknown/unmapped residual cannot silently become clearance. Include the joint
and adaptive observations allowed by the interface, not merely a list of
individually checked weights, outputs, metadata and logs. Independent review can
challenge the scope but cannot prove that no real-world channel was omitted.
For a threat-class ceiling, bound the supremum over the registered allowed
adversaries and joint observations; an average over sampled attacks or a finite-pool
membership score is not automatically that class-wide upper bound.

### Fresh tree/image/LLM protocol-scaling study

The following is a proposed design floor to be finalized in a new registration,
not permission to repin any retained study. Use real fitted tree ensembles, real
image architectures and pretrained generative LLMs with a declared fine-tuning
target; do not present controlled channel names or text-classifier proxies as
real-model scalability. Pretraining membership must remain unknown unless an
independently justified membership frame exists.

1. **Freeze two complementary cohorts.** A model-backed cohort starts with
   registered training inputs, runs actual training and fresh evidence collection,
   and proceeds through every admissible downstream stage to its genuine final
   outcome. A refusal is a valid outcome, not a reason to invent a ceiling or
   waive a required obligation. Separate controlled accepting traces exercise
   the complete reference signing, audit and lifecycle paths. Label these
   synthetic controls; they cannot fill missing real-model completion cells.
   Map the actual MRAP states, CLI artifacts and stop conditions before claiming
   that a chain is end-to-end. An `ASSESSED` prefix is not an `ACTIVE` trace.
2. **Vary scale explicitly.** Propose at least two capacity settings per model
   family, three workload sizes and three independent training/run seeds per
   setting. Freeze exact models/revisions, tree counts/depths, parameter counts,
   rows, image resolution, sequence length, tokens, optimizer steps and effective
   batch size. Use nested workloads only as a disclosed paired design, not
   independent population replications. If the resource envelope cannot support
   this design, register a smaller study and narrow the resulting claim before
   observing outcomes. Do not extrapolate a toy-only run to industrial scale.
3. **Measure both model and protocol workload.** Separate training volume/model
   capacity from evidence-record count, audit-log length, declared scenario count,
   candidate count, joint observation alphabet and portfolio size. Register
   which dimensions vary and which remain fixed.
   Fixed-size privacy scoring cannot demonstrate scaling in audit sample size;
   duplicating fixture records cannot demonstrate additional threat coverage.
   Maintain admissible fresh identities/context when constructing protocol-load
   controls, and identify them as synthetic load rather than independent evidence.
4. **Control runtime conditions.** Freeze source/dirty-tree inventory, exact
   dependencies, dataset/model hashes, split/deduplication rules, seeds, precision,
   CPU threads, GPU type/memory, batch/accumulation and time/memory limits. Record
   background contention, OS/storage and warm/cold cache state. Serialize competing
   GPU jobs, synchronize device timing, separate warm-up from measured work, and
   randomize or block the cell order prospectively. Predeclare OOM/time-limit
   handling; do not silently switch device, precision, model or batch after failure.
5. **Time the whole reference chain.** Record acquisition/cache preparation,
   registration, training, evidence collection, contract parsing, source hashing,
   analysis, assurance disposition, signatures, audit append, lifecycle replay and
   final gate separately, plus end-to-end wall time, throughput, peak host/device
   memory, disk bytes and completion/failure state. Distinguish core-library work
   from CLI/process startup and define every timer's inclusion boundaries. Mark
   unreachable stages as not executed; do not impute their cost as zero or pool
   refused prefixes with completed chains. No timing stands for an unimplemented
   live registry or serving gateway.
6. **Keep scientific outcomes and costs distinct.** Report within-model utility
   before/after, attack metric, finite-pool/population scope, confidence bounds,
   floor/ceiling/gap, final verdict and utility loss. Tokenizer-specific perplexities
   are not cross-model equivalents, and tree/image/LLM risk metrics must not be
   averaged together. State the prior/baseline before calling success probability
   an advantage. For empirical inference, preregister calibration/selection
   separation, sampling units, dependence treatment and allocation across attacks,
   classes, subgroups, cells and repeated looks. A worst-case ceiling of one is
   honest when no stronger bound applies; it is not a measured risk estimate.
7. **Include failure and overhead controls.** Pair each relevant positive chain
   with missing-evidence, tampered-source/signature, stale-context and scope-gap
   controls, plus scientifically valid above-threshold and boundary cases where
   constructible. Do not call an artificially altered empirical result a real
   attack. Measure instrumentation/checking overhead using matched workloads;
   disabled-validation variants are experimental ablations, never usable gates.
   Retain adverse utility outcomes, timeouts, OOMs, refusals and abandoned cells.

Publication requires a prospective plan and source/runtime bindings before the
first outcome, a complete inventory of attempted cells, independent replay of
counts/certificates/digests, and completion manifests for every claimed completed
run. Freeze separate soundness and decision-resolution criteria for controlled
safe, unsafe and near-boundary cases, with multiplicity-adjusted uncertainty and
declared margins; throughput cannot compensate for a soundness failure. Claim
model-backed blocking power only if scientifically valid above-threshold
model-backed cases were actually evaluated. Report per-cell values and paired
uncertainty over independent run seeds;
do not treat repeated queries from one trained model as independent training
replications or use a few repetitions for unsupported tail-latency claims.
Aggregate publication and privately retained replay material must have explicit
access/retention rules. Changed code needs a new run identity and registration;
old failures and registrations remain immutable. If any publication exit criterion
is unmet, report the narrower result or the incomplete study, not a completed claim.

### Industrial boundary: deferred, not discharged

The industrial track would need authenticated authority/role enrollment, protected
keys, independently trustworthy measurement and execution receipts, an authoritative
current inventory, linearizable durable registry operations, rollback-resistant
audit anchoring, actual artifact/interface measurement, complete serving mediation,
monitoring and enforceable revocation. It also needs operational availability,
incident recovery, retention/access controls and domain-specific legal, fairness
and stakeholder decisions. Those are not proved by a local transcript or benchmark.

Academic evaluation may use declared test doubles for these external services to
study conditional semantics, provided every substitution is explicit. It must not
claim production security, deployed end-to-end enforcement, verified Ed25519 or
Python refinement without the corresponding additional proof and implementation
evidence. Academic priority determines work order, not a weaker interpretation of
release safety. All proposed runs remain non-authorizing.

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

The [generated tables and figure](../academic/paper/ceiling-experiment-results.md) are
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
