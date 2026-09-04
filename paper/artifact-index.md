# Paper artifact index

This index distinguishes retained evidence from executable machinery and study
plans. A configuration, runner, test fixture, queue entry, or partial journal is
not a completed result.

## Maturity labels

| Label | Use in the paper |
|---|---|
| Retained completed result | May support an empirical statement, within the artifact's declared scope and limitations. |
| Reproducible source/proof | May support a design or theorem statement; run it at the paper commit before reporting a fresh outcome. |
| Executable example | Demonstrates a code path only; not external or release-valid evidence. |
| Registered/configured study | May describe methodology and planned evaluation, not results. |
| Local ignored output | Useful for development; absent from a clean clone and unsuitable as the sole source for a paper claim. |

## Retained completed empirical evidence

| Artifact | Contents | Paper-safe use | Boundary |
|---|---|---|---|
| [Ceiling experiment results](ceiling-experiment-results.md) and [machine-readable summary](../reproduction/ceiling-experiment-summary.json) | Generated cross-experiment tables, metric semantics, chronology, scope, and links to canonical reports | Primary source for paper-ready ceiling numbers; controlled and model-backed v3 experiments accepted | The summary is derived, not a universal proof or authorization. It preserves v2 as a failed predecessor and keeps the near-threshold v3 proxy arm outside the margin-resolution claim. |
| [Controlled finite-channel report](../reproduction/finite-channel-ceiling/results/ground-truth-report.json) and [manifest](../reproduction/finite-channel-ceiling/results/manifest.json) | Exact-risk channels, 1,800 count records, repeated analyzer results, three Engine replays, tamper checks, runtime, and digests | Supports controlled coverage, width, false-clear, and `CLEAR`/`HOLD`/`BLOCK` observations | Synthetic channels; family names are labels. The Engine replays use an experimental attack-battery waiver and issue no authorization. |
| [Model-backed v3 report](../reproduction/model-backed-finite-channel/results/v3/model-backed-finite-channel-report.json) and [manifest](../reproduction/model-backed-finite-channel/results/v3/manifest.json) | Fresh CNN/MNIST, XGBoost/Adult, and compact-Transformer/20-Newsgroups artifacts; raw-bin/erasure channels; per-observation wrapper execution; 18-endpoint role-aware evaluation | Supports conditional soundness, wrong-direction, safe-side margin-resolution, conservative holds, erasure-identity, wrapper-equivalence, replay, and negative-control observations | One artifact/family and small resampled finite pools. All oracle risks are below tolerance, so no model-backed `BLOCK` claim follows. Python wrapper execution and Engine source binding do not prove endpoint/OS semantics. The Transformer is an LLM proxy. |
| [Model-backed v2 report](../reproduction/model-backed-finite-channel/results/v2/model-backed-finite-channel-report.json) and [manifest](../reproduction/model-backed-finite-channel/results/v2/manifest.json) | Historical predecessor using aggregate sampling separate from wrapper conformance | Supports the preserved negative 109/200 raw proxy result and explains v3's prospectively frozen corrective design | V2 remains failed under its own 8/9 acceptance result; it is not rewritten or pooled as v3 evidence. |
| [Real-data training-hook execution audit](../docs/real-data-training-hook-audit-2026-09-02.md) | Curated aggregate LLM and vision workload, hook, performance, context-screen, perturbation-screen, provenance, and digest record | Completed publication-safe model-execution and instrumentation observations | Raw data, raw reports, trained state, rosters, and telemetry are excluded; all results are non-authorizing screens. |
| [LLM registered input](../reproduction/llm-training-hook/README.md) | WildChat source/revision, cohort rules, three-model workload, evidence boundary, and rerun procedure | Explain the exact design behind the completed LLM audit | The configuration alone is not completion; dataset content and caches are not committed. |
| [Vision registered input](../reproduction/vision-training-hook/README.md) | EuroSAT digest/split, two-architecture workload, hooks, perturbations, and rerun procedure | Explain the exact design behind the completed vision audit | The configuration alone is not completion; images, weights, caches, and raw outputs are not committed. |

Use each canonical retained report or its generated summary, never a
transcribed spreadsheet or ignored local output. The chronology retains the
[v1 pre-outcome failure](../reproduction/model-backed-finite-channel/failed-v1-execution.json),
[v2 registration](../reproduction/model-backed-finite-channel/v2-preregistration.json)
and negative result, then the [prospectively frozen corrective v3
registration](../reproduction/model-backed-finite-channel/v3-preregistration.json)
and fresh result. V3 was designed after v2 outcomes were known but reused no v2
outcome as v3 evidence.

## Derived reports and interpretations

| Artifact | Derivation | Proper use | Boundary |
|---|---|---|---|
| [Government health-agency XGBoost release playbook for restricted healthcare data](xgboost-end-to-end-test-report.md) | Extracts the v3 XGBoost data, training, finite population, wrapper, primary Engine replays, 400 analyzer repeats, and integrity chain; adds a contract → execution-pipeline → durable-workflow application profile | Detailed technical appendix, plain-language public-sector case study, and audit-ready release/no-release guide; every number must trace to a canonical retained artifact above | Narrative, not independent evidence. No worker-to-assessment admission adapter or production orchestrator/registry/gateway/monitor exists. Adult is public census-income data; raw XGBoost is not margin-eligible; no unsafe XGBoost case, live government endpoint, clinical/domain validation, or authorization was tested. |

## Reference implementation and formal artifacts

| Artifact | Type | Paper use | Reproduction action |
|---|---|---|---|
| [`src/model_release_assurance`](../src/model_release_assurance/) | Python reference core | System implementation and enforcement-path description | Run the complete Python/schema checks at the frozen commit. |
| [Current schema index](../schemas/README.md) | Public contract inventory | Contract surface and versioning | Run schema-manifest replay; cite a commit rather than a mutable schema count in prose. |
| [MRAP/1.0](../docs/model-release-assurance-protocol.md) | Normative protocol | Roles, lifecycle, gates, messages, and conformance boundary | Audit the draft against current normative wording. |
| [Formal Lean package](../formal/lean/) | Machine-checkable abstract model | Scoped theorem claims | Run the repository verification wrapper with the pinned Lean toolchain and retain the transcript. |
| [Formal claim boundary](../docs/formal-verification.md) | Theorem inventory and non-claims | Exact theorem IDs, assumptions, trusted base, and refinement gap | Copy theorem scope, not a broader safety paraphrase. |
| [Protocol correspondence](../formal/protocol-correspondence-v1.json) | Machine-readable Python/Lean vocabulary and test mapping | Explain executable drift checks | Do not describe it as a refinement proof. |
| [Game-theory claim ledger](../formal/game-theory-claim-ledger-v1.json) | Citation provenance ledger | Separate source results, MRA inferences, and proposals | Recheck source metadata before final bibliography export. |
| [Ceiling experiment preregistration](../reproduction/ceiling-experiment-preregistration.json) | Commit-anchored source/configuration record for the controlled and original model-backed designs | Establishes the locally frozen design chronology | The commit was not externally timestamped or signed. Use the version-specific registration for each completed model-backed run. |
| [Model-backed v2 preregistration](../reproduction/model-backed-finite-channel/v2-preregistration.json) | Compatibility-only successor registration, source archive digest, environment, and pre-outcome checks | Documents that v2 was frozen before its model outcomes | Local Git/archive anchor only; no external timestamp or signature. |
| [Model-backed v3 preregistration](../reproduction/model-backed-finite-channel/v3-preregistration.json) | Corrective role-aware design, fresh seed domains, per-use wrapper path, source bindings, and pre-outcome checks | Documents that the v3 correction was frozen after v2 but before fresh v3 outcomes | Local Git/archive anchor only; no external timestamp or signature. It is a corrective replication, not an independent first study. |

## Registered or configured studies without retained completion

| Study | Retained inputs | Intended paper question | Current restriction |
|---|---|---|---|
| [Five-model composition scaling](../reproduction/composition-scaling/README.md) | Shared protocol plus LLM, vision, and suite configs | Scale/seed sensitivity, hook/batch controls, same-population composition, resource vectors | Do not report outcomes until both child completions and the final suite completion are retained and verified. |
| [OpenML study](../reproduction/openml/README.md) | Dataset/source manifests and multiple registered analysis configs | Cross-dataset/tabular evidence behavior | Raw snapshots, trained models, outputs, witnesses, and study seal are absent; historical numeric records are provisional. |
| [Portfolio stochastic benchmark](../reproduction/portfolio-stochastic/config.json) | Benchmark configuration | Optimizer/bound behavior under stochastic problems | Generated rows, summaries, and reports are not committed. |
| [Strategic assurance experiment](../reproduction/strategic-assurance/config.json) | Exact-rational stress-test configuration | Sensitivity of optional strategic primitives and monitoring incentives | Configured only; deliberately non-authorizing. |
| [Public privacy workflow](../reproduction/public-privacy/README.md) | Workflow description and runner contract | Multi-family public-data privacy screening | Data, models, measurements, and report are generated locally and not retained. |
| [Model-audit workflow](../reproduction/model-audit-workflow/manifest.json) | Hash-bound sample artifacts/manifests and empirical config | Integration and red-team code paths for classical/neural examples | Examples are illustrative; empirical generated reports are not retained in the reproduction directory. |

The complete maturity table is maintained in the
[reproduction index](../reproduction/README.md).

## Executable evaluations whose paper outputs must be regenerated

| Evaluation | Source | Current retained outcome | Paper action |
|---|---|---|---|
| Python, schema, and link checks | [Makefile](../Makefile) and [test guide](../tests/README.md) | Tests and source are retained; no paper-snapshot log is committed | Run `make check`, record environment/commit/start/end/status/skips, and retain the log outside this drafting directory. |
| Lean proof build and axiom audit | [Verifier](../scripts/verify_formal_protocol.py) | Proof source and toolchain pin are retained | Run `make formal`; retain full output and toolchain identity. |
| Protocol mutation evaluation | [Design](../docs/protocol-evaluation.md) and [runner](../scripts/evaluate_protocol_mutations.py) | Two controls and 21 mutant definitions; no generated report identified as committed | Generate and hash the JSON report before quoting a mutation score. |
| Framework-effectiveness evaluation | [Runner](../scripts/evaluate_framework_effectiveness.py) | Executable evaluation source | Define the exact paper question and retain output before using a result. |

## Local ignored outputs

The current working tree contains generated files under `output/`, including
`output/model-audit-workflow/empirical-xgboost-mlp-report.json` and
`output/model-audit-workflow/xgboost-mlp-report.json`. The repository explicitly
ignores `output/`, so these files are not available in a clean clone and are not
archival paper evidence. The first report also labels its classification data
synthetic and its functional/red-team measurements non-clearing. Use these
outputs to debug the workflow or to design a properly retained study, not as an
uncaveated empirical result.

## Submission artifact manifest to create

`[AUTHOR TODO]` At the paper snapshot, create an immutable external manifest
that records, for every reported table/figure:

- repository commit and dirty-tree status;
- exact command, configuration digest, runner digest, and environment/lock
  identity;
- dataset/model source identifiers, licenses, revisions, byte counts, and
  SHA-256 digests;
- raw-result, sanitized-result, analysis, figure, and completion-manifest
  digests;
- start/end time, host/GPU identity, random seeds, repetitions, failures, and
  skips;
- statistical family, selection rule, interval method, and error allocation;
- authority status and why the output is a screen, floor, ceiling, exact value,
  or non-authorizing system check; and
- custody/access instructions for sensitive artifacts that cannot be public.

Do not place sensitive dialogue, exact rosters, credentials, private host paths,
or raw per-example model outputs in this paper directory.
