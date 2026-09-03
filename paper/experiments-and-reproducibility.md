# Experiments and reproducibility checklist

This is both an experiment ledger and the acceptance checklist for paper
results. Checked items in the E7 sections are facts reconciled to retained
manifests; unchecked items remain paper-snapshot or deployment work.

## Current evaluation ledger

| ID | Evaluation | Current status | Result usable now? | Closure condition |
|---|---|---|---|---|
| E1 | WildChat training hooks on DistilGPT2, OPT-125M, and Pythia-160M | Completed experimental execution; curated audit retained | Yes, as aggregate integration observations and screens only | Reconcile every quoted value/digest with the [retained audit](../docs/real-data-training-hook-audit-2026-09-02.md). |
| E2 | EuroSAT training hooks and bounded perturbations on AlexNet and DenseNet-121 | Completed experimental execution; curated audit retained | Yes, as aggregate integration observations and screens only | Preserve one-run, one-epoch, one-GPU, no-CI, and non-authorizing qualifications. |
| E3 | Five-model composition scaling | Registered/configured secondary study | No outcomes | Complete all registered child cells and final suite aggregation; retain and hash both child completions and suite completion. Do not use it as primary evidence meanwhile. |
| E4 | Python core/schema regression suite | Implemented and runnable | No current paper-snapshot outcome | Run `make check` at the frozen commit; record all pass/fail/skip counts and environment. |
| E5 | Protocol adversarial mutation evaluation | Program defines two controls and 21 unsafe mutants | No score | Generate, retain, and hash the report; describe the score only as registered-mutant coverage. |
| E6 | Lean proof replay and axiom audit | Source and pinned toolchain retained | The theorem statements are citable; no fresh paper-snapshot execution claim | Run `make formal`; retain complete output, toolchain identity, and commit. |
| E7a | Controlled finite-channel ceiling validation | Completed; all registered claims passed | Yes, for the exact controlled channel family | Use the [generated result report](ceiling-experiment-results.md) and retain its synthetic-channel, three-Engine-replay, experimental-waiver, and non-authorizing boundaries. |
| E7b | Model-backed public-data ceiling validation v2 | Completed historical predecessor; 8/9 criteria passed | Yes, as a preserved negative result | Preserve zero undercoverage and the failed raw Transformer-proxy clear-power criterion together; do not pool it into v3. |
| E7c | Prospectively frozen corrective model-backed v3 | Completed; all 10 criteria passed | Yes, within its finite-pool, safe-side scope | Report 18-endpoint soundness/wrong-direction bounds, margin-eligible resolution, near-boundary holds, wrapper cross-replay, and the absence of a model-backed above-tolerance case. |
| E8 | OpenML, stochastic portfolio, strategic, and public-privacy studies | Registered or configured | No completed outcomes | Follow each study's sealing contract and retain complete raw/derived artifacts before use. |
| E9 | Production authority/registry/gateway evaluation | Not implemented | No | Requires an external system and an independently reviewed operational/refinement study. |

## Result admission gate

A result may enter the paper only when every applicable item is checked:

- [ ] A row in the [claims matrix](claims-to-evidence.md) authorizes the exact
  wording and evidence type.
- [ ] The experiment has a frozen question, hypothesis or systems property,
  metric, analysis rule, stopping rule, and exclusion rule.
- [ ] The exact release/interface/population/threat scope is registered before
  looking at the outcome.
- [ ] Dataset, model, configuration, runner, dependency, and hardware identities
  are recorded and hash-bound where applicable.
- [ ] Random seeds, independent repetitions, sample/unit counts, and split or
  partition construction are recorded.
- [ ] The statistical family and selection process are declared, with
  simultaneous uncertainty or an explicit explanation of descriptive-only
  status.
- [ ] Positive controls, negative controls, failure injection, and baseline
  comparisons required by the claim have passed—or their failures are reported.
- [ ] Raw results, sanitized aggregates, analysis code, and completion manifest
  exist and their digests reconcile.
- [ ] A completion signal was written only after all registered cells and
  resource checks completed.
- [ ] Failures, retries, exclusions, timeouts, resource breaches, warnings, and
  skipped tests are retained rather than silently omitted.
- [ ] Data/model rights, human-data handling, disclosure risk, access, retention,
  and deletion have been reviewed separately from technical success.
- [ ] The result says whether it is a screen, floor, ceiling, exact result,
  software check, or abstract theorem, and does not exceed that authority.

## Core and formal snapshot

Run from the repository root in a clean, immutable checkout.

### Environment

- [ ] Record repository commit, tag/version, dirty-tree status, operating system,
  architecture, Python version, and UTC timestamps.
- [ ] Install the dependency sets documented in
  [CONTRIBUTING](../CONTRIBUTING.md); archive the resolved environment in
  addition to the source lock files.
- [ ] Record whether optional experiment dependencies and the pinned Lean
  toolchain were available.

### Commands

```bash
make check
make formal
python scripts/evaluate_protocol_mutations.py \
  --output output/protocol-mutation-evaluation.json
```

- [ ] Store stdout/stderr and exit status for each command separately.
- [ ] Report pass, fail, error, and skip counts; do not count a skipped optional
  test as a pass.
- [ ] Verify the generated mutation report digest and retain its two control
  results plus all 21 mutant outcomes.
- [ ] For Lean, record `lean-toolchain`, the verifier's accepted axiom audit, and
  whether the complete build—not only Python artifact inspection—ran.
- [ ] State that passing fixtures and mutations do not prove scientific evidence
  adequacy or complete vulnerability coverage.

## Completed five-model audit

The [curated execution audit](../docs/real-data-training-hook-audit-2026-09-02.md)
is the public record. Before copying any number:

- [ ] Confirm it appears in the audit and preserve its displayed precision.
- [ ] Cite the pinned dataset/model revision and relevant configuration/worker
  digest from the same modality section.
- [ ] Distinguish the 125.5-MB single WildChat shard and selected 9,216-row
  cohort from the full upstream dataset.
- [ ] Distinguish complete EuroSAT benchmark use from production satellite-data
  coverage.
- [ ] Report the exact model, epoch, batch/sequence or image preprocessing,
  train/test sizes, steps, runtime, and hardware with performance numbers.
- [ ] Keep LLM membership values and vision perturbation values labeled as
  descriptive screens with `can_clear=false` and `can_block=false`.
- [ ] State that LLM assignment was not randomized and no cross-model causal
  comparison follows.
- [ ] State that the exact CPU vision no-hook check does not establish CUDA
  non-interference, and bitwise CUDA reproducibility is not claimed.
- [ ] Carry the data-rights and model-license caveats into the evaluation or
  ethics section.
- [ ] Preserve the final `no_release_authorization`,
  `authorization_eligible=false`, and `assessment_input_emitted=false`
  disposition.

## Secondary planned composition-scaling study

Use the [registered protocol](../reproduction/composition-scaling/README.md) and
do not edit the matrix after inspecting results without creating a new version.
This study is secondary to the completed ceiling evaluation until all of its
registered cells and completion manifests exist.

### Registration checks

- [ ] Three LLM and two vision model identities and source revisions match the
  frozen configs.
- [ ] Seeds are exactly `3407`, `499625614`, `4288481424`, `2669540432`, and
  `2937338177`.
- [ ] LLM scales are 2,048/4,096/8,192 WildChat training records; vision scales
  are 5,400/10,800/21,600 EuroSAT training images.
- [ ] The run covers 75 independent model/scale/seed reference cells and the 90
  registered matched vision batch/hook cells.
- [ ] All 31 nonempty model subsets are present: seven LLM scalar subsets,
  three vision scalar subsets, and 21 mixed-modal vector-only subsets.
- [ ] R0–R5 are treated as explicit non-ordinal interface masks.
- [ ] Commercial portfolios containing OPT retain the absorbing license block;
  data-rights/manual and unassessed axes remain unresolved where registered.

### Execution and completion checks

- [ ] Children run serially on one GPU; no overlap is inferred from shared
  seeds or timestamps.
- [ ] Separate verified LLM and vision caches are used without copying or
  symlinking them into suite output.
- [ ] The 43,200-second wall-clock and 21,474,836,480-byte GPU, host-RSS, and
  aggregate-artifact ceilings are enforced.
- [ ] Every child final manifest matches its frozen schema, report hash/size,
  authority object, model roster, scales, seeds, and complete result matrix.
- [ ] The suite remeasures artifacts, rejects unfamiliar fields/shapes, and
  writes `RUN_COMPLETE.json` last.
- [ ] Aggregate output contains no prompts, dialogue, images, tokens,
  per-example predictions, gradients, activations, identifiers, rosters, or
  host paths.
- [ ] Same-population scalars are not pooled across WildChat and EuroSAT; all
  mixed-modal and all-five outputs remain resource/gate vectors.
- [ ] Missing, partial, timed-out, over-budget, or digest-mismatched runs are
  reported as incomplete, not imputed or omitted.

### Analysis checks

- [ ] Report per-seed values and dispersion; do not present five seeds as broad
  production-distribution coverage.
- [ ] Treat nested data scales according to their dependence structure; do not
  count them as independent datasets.
- [ ] Separate training throughput, hook cost, resource use, attack screens,
  model quality, and gate decisions instead of collapsing them into one score.
- [ ] Avoid fitting or naming a “scaling law” unless the registered design and
  diagnostics justify the functional form and uncertainty.
- [ ] Do not interpret a serial resource vector as concurrent-serving capacity.
- [ ] Keep unmeasured fairness/robustness axes as `NOT_ASSESSED` and preserve
  worst/absorbing categorical gate propagation without averaging.

## Completed finite-channel ceiling evaluation

The [generated paper result](ceiling-experiment-results.md) and
[machine-readable summary](../reproduction/ceiling-experiment-summary.json)
are the drafting entry points. They derive from the retained controlled and
model-backed reports rather than manual transcription.

### E7a: controlled exact-ground-truth result

- [x] The exact rational game, prior, channel family, error allocation,
  stopping rule, and acceptance thresholds were frozen before collection.
- [x] All 1,800 predeclared records completed, including 1,200 primary analyzer
  replays at 2,000 observations per state.
- [x] Primary undercoverage was 0/1,200; the maximum Bonferroni-simultaneous
  Clopper--Pearson upper bound was `0.015606`.
- [x] Safe, boundary, and unsafe roles produced 400/400 `CLEAR`, 400/400
  `HOLD`, and 400/400 `BLOCK`, respectively; each simultaneous role-correct
  lower bound was `0.984394`.
- [x] Mean interval width decreased from 100 to 500 observations per state for
  every registered scenario.
- [x] Analyzer replay, family-label invariance, three source-backed Engine
  integrations, and registered tamper controls passed.
- [x] The report states that model-family names are labels and that the
  experimental attack-battery waiver is not deployment-valid.

### E7b: completed model-backed v2 mixed result

- [x] V1's pre-outcome XGBoost serialization failure and the compatibility-only
  v2 registration are retained rather than silently overwritten.
- [x] CNN/MNIST, XGBoost/Adult, and compact-Transformer/20-Newsgroups outputs
  were reduced to two registered categorical variants per model; the
  Transformer is labelled as an LLM proxy.
- [x] Six one-shot Engine replays and 1,200 repeated analyzer replays completed;
  observed undercoverage was 0/1,200 and each simultaneous undercoverage upper
  bound was `0.027031`, below the `0.05` target.
- [x] Five families cleared 200/200 times and met the registered simultaneous
  clear-rate lower target.
- [x] The raw Transformer-proxy family cleared only 109/200 times; its
  simultaneous lower bound was `0.449431`, below the registered `0.95` target.
- [x] The report therefore records eight of nine criteria passed and an overall
  `registered_acceptance_not_met` result.
- [x] All retained model results are conditional on one artifact per family,
  400 `IN`/400 `OUT` records for CNN and XGBoost and 350/350 for the proxy, and
  repeated sampling from those same pools.
- [x] Counts came from the aggregate sampler; the wrapper surface was tested
  separately, so v2 supplies no end-to-end wrapper-enforcement evidence.
- [x] The controlled and v2 experiments used experimental attack-battery
  waivers and emitted no release authorization.

### E7c: accepted prospective corrective v3

- [x] V3 was designed after v2 outcomes were known, then frozen with a fresh
  collector seed, fresh primary/repeat seed domains, role-aware criteria, and
  no reuse of v2 outcomes.
- [x] All 10 registered criteria passed. Six full Engine primary replays and
  1,200 analyzer repeats completed.
- [x] Undercoverage and wrong-direction events were both 0/1,200. Across 18
  Bonferroni one-sided endpoints, every per-family simultaneous upper bound was
  `0.02900166`, below `0.05`.
- [x] All four families with exact risk at least `0.10` from the `0.65`
  tolerance produced 200/200 correct safe-side `CLEAR` decisions, with
  simultaneous lower bound `0.97099834`.
- [x] The raw Transformer proxy had exact risk `0.612857`, only `0.037143`
  below tolerance, so it was not margin eligible. Its 31 `CLEAR` and 169
  `HOLD` outcomes were retained and no outcome was wrong-direction.
- [x] No v3 oracle risk exceeded `0.65`; v3 therefore supplies no model-backed
  unsafe-side or `BLOCK`-power result. The controlled exact-risk `0.80`
  channel is the only current repeated `BLOCK` demonstration.
- [x] Every observation executed through a fresh one-use Python wrapper and
  exactly matched the aggregate reference sampler; wrapper execution evidence
  was bound into Engine source replay.
- [x] Five negative controls passed, including missing/tampered wrapper
  evidence, and all three erasure variants satisfied the exact contraction
  identity `R_e = 0.5 + 0.1(R_raw - 0.5)`.
- [x] V3 remains conditional on one fresh artifact per model, 400 `IN`/400
  `OUT` records for CNN and XGBoost and 350/350 for the proxy, and resampling
  from those pools. The Transformer is an LLM proxy.
- [x] Python wrapper execution does not prove deployed endpoint, authentication,
  timing, process-isolation, or operating-system semantics. V3 also uses an
  experimental attack-battery waiver and grants no authorization.

### Remaining deployment evidence

- [ ] Independently enforce and observe the complete recipient wrapper,
  including error, timing, process-isolation, and operating-system channels.
- [ ] Replace the experimental battery waiver with the policy-required complete
  red-team battery and independently authenticated collection.
- [ ] Validate new artifacts, seeds, populations, and deployment interfaces;
  no completed experiment transfers automatically to them.
- [ ] Implement and evaluate the external authority, registry, gateway,
  monitoring, and revocation workflow before making an authorization claim.

## Paper tables and figures

For every table or figure:

- [ ] Give it an evidence/experiment ID from this ledger.
- [ ] Generate it from a retained aggregate artifact, not by manual copy/paste.
- [ ] Record the generating script/command and input/output digests.
- [ ] Include sample/unit counts, repetitions, uncertainty, and relevant
  denominators in the caption.
- [ ] Mark descriptive screens and planned cells visually and in text.
- [ ] Use separate panels or vectors for incompatible protected-unit
  populations.
- [ ] Verify that the caption alone does not imply authorization, causality,
  completeness, or production scale.

## Final artifact audit

- [ ] Every empirical sentence maps to the [artifact index](artifact-index.md).
- [ ] Every theorem sentence maps to an exact theorem ID and its premises.
- [ ] Every external scientific statement cites a primary source, not only the
  repository's narrative reviews.
- [ ] All local links pass the repository Markdown-link checker.
- [ ] The public artifact contains no secrets, sensitive raw examples, exact
  protected rosters, credentials, or private paths.
- [ ] The paper and artifact state exactly which generated materials are public,
  restricted, reproducible from public sources, or unavailable.
- [ ] A clean reviewer workflow has been tested independently from the author's
  caches and ignored `output/` tree.
