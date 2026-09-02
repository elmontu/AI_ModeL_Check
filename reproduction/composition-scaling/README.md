# Five-model composition-scaling experiment

This directory registers a real-data, one-GPU composition experiment spanning
three language models and two vision models. It measures scaling and
same-population model composition without treating unrelated protected units as
if they belonged to one statistical population.

The shared entry point is
[`run_composition_scaling_suite.py`](../../scripts/run_composition_scaling_suite.py).
It binds the modality workers, validates their final manifests, and publishes an
aggregate-only JSON report, a Markdown audit view, and `RUN_COMPLETE.json` as the
last write. The suite is experimental: it emits no assessment input and grants
no release authorization.

## Frozen matrix

| Dimension | Registration |
| --- | --- |
| LLMs | DistilGPT2, Meta OPT-125M, Pythia-160M |
| Vision models | canonical torchvision AlexNet and DenseNet121 |
| Seeds | `3407`, `499625614`, `4288481424`, `2669540432`, `2937338177` |
| LLM real-data scales | 2,048; 4,096; 8,192 WildChat training records |
| Vision real-data scales | 5,400; 10,800; 21,600 EuroSAT training images |
| Model subsets | 31 nonempty five-model subsets |
| Scalar subsets | 7 LLM subsets and 3 vision subsets |
| Mixed-modal subsets | 21 resource/gate-vector-only subsets |
| Scalar result cells | 105 LLM and 45 vision aggregate cells |

The five seeds are repeated across both modalities. Each registered scale is a
real, deterministic subset of the bound web dataset, not a synthetic sample.
The LLM child uses
[`llm-config.json`](llm-config.json); the vision child uses
[`vision-config.json`](vision-config.json). The shared policy and exact source
digests are frozen in [`suite-config.json`](suite-config.json).

## Composition boundary

An empirical scalar can be composed only when every participating model was
evaluated over the same registered protected-unit population:

- the three LLMs share the registered WildChat candidate-record population;
- AlexNet and DenseNet121 share the registered EuroSAT held-out-image
  population; and
- an LLM record and a vision image are not interchangeable sampling units.

Consequently, the suite never calculates an all-five-model accuracy, privacy
score, risk score, or averaged attack metric. Every mixed-modal subset—especially
the all-five subset—contains a per-model resource vector and a per-axis policy
gate vector only. The report preserves modality-level empirical components
without converting them into a cross-population scalar.

## Recipient interfaces R0-R5

R0-R5 are explicit, non-ordinal masks. They are not cumulative, and a result at
R2 does not imply a monotone change at R3.

| Mask | Recipient-visible interface | Registered mapping |
| --- | --- | --- |
| R0 | Basic prediction payload only | LLM K0; vision M0 |
| R1 | Generated-token log probabilities or class scores, but no arbitrary-candidate scorer | LLM remains K0; vision M1 |
| R2 | Exact candidate source and preprocessing metadata, but no arbitrary scorer | LLM K0/K1; no vision empirical mapping |
| R3 | Arbitrary-candidate scoring and per-example loss | LLM K0/K2; vision M2 |
| R4 | White-box weights/internal features plus exact candidate metadata | LLM K0-K3; vision M2 |
| R5 | Exact protected roster and source provenance | LLM K0/K4; vision M3 |

Every mask has the same closed authority object:
`assessment_input_emitted=false`, `attack_battery_eligible=false`,
`authorization_eligible=false`, `authorization_granted=false`,
`can_clear=false`, `can_block=false`,
`requires_approved_recollection=true`, and
`decision=no_release_authorization`.

## Gate semantics

Policy gates are categorical. For each axis the suite propagates the worst
registered gate and treats block gates as absorbing; gates are never averaged.
The axes remain a vector: model license, data rights, interface disclosure,
evidence authority, robustness, and fairness.

- Any commercial subset containing Meta OPT-125M has an absorbing
  `BLOCKED_NONCOMMERCIAL_RESEARCH_ONLY` model-license gate.
- Pythia's human-facing deployment boundary is
  `MANUAL_REVIEW_REQUIRED`.
- WildChat content rights and EuroSAT/Sentinel data terms remain manual gates.
- R5 logically reveals protected membership. It is
  `BLOCKED_AND_REDESIGN_REQUIRED` regardless of an empirical screen result.
- Unmeasured robustness and fairness axes remain `NOT_ASSESSED`; they are not
  silently converted to pass states.

These policy gates do not turn the exploratory screens into release evidence.
Approved recollection means rerunning a registered, recipient-realizable attack
battery under the eventual signed release contract.

## Resource and execution contract

The shared runner launches the LLM worker and then the vision worker with
`CUDA_VISIBLE_DEVICES=0`; no two child processes overlap. Shell execution is
disabled. A successful suite must stay within all of these limits:

- 43,200 seconds (12 hours) total wall clock;
- 21,474,836,480 bytes (20 GiB) peak GPU reserved memory;
- 21,474,836,480 bytes peak host RSS; and
- 21,474,836,480 bytes of aggregate retained artifacts.

Each child checks its own runtime budget. The suite checks registered resource
vectors and measures child output trees again before it publishes. A timeout,
memory breach, artifact breach, incomplete matrix, unfamiliar schema, digest
mismatch, missing authority flag, unsafe path, or unexpected completion shape
fails closed and produces no suite completion manifest.

The modality caches remain separate because they already contain verified,
multi-gigabyte source/model objects:

- LLM default: `output/llm-training-hook/cache`
- vision default: `output/cache/vision-training-hook`

The suite passes each cache directly to its child; it does not copy or symlink a
cache into a new tree.

## Queue or replay the complete suite

Validate every registered source/config/runner digest without importing Torch:

```bash
python3 scripts/run_composition_scaling_suite.py \
  --config reproduction/composition-scaling/suite-config.json \
  --output-dir output/composition-scaling/suite/validation-unused \
  --llm-cache-dir output/llm-training-hook/cache \
  --vision-cache-dir output/cache/vision-training-hook \
  --validate-only
```

Queue both workers serially against the existing verified caches:

```bash
python3 scripts/run_composition_scaling_suite.py \
  --config reproduction/composition-scaling/suite-config.json \
  --output-dir output/composition-scaling/suite/aggregate-v1 \
  --work-dir output/composition-scaling/suite-work-v1 \
  --llm-cache-dir output/llm-training-hook/cache \
  --vision-cache-dir output/cache/vision-training-hook \
  --execute-children \
  --offline
```

The output and work parents must exist, while the two target directories must be
fresh. Child work is retained separately for internal audit; the suite output
contains only the safe aggregate artifacts.

Aggregate two already-completed child runs without rerunning training:

```bash
python3 scripts/run_composition_scaling_suite.py \
  --config reproduction/composition-scaling/suite-config.json \
  --output-dir output/composition-scaling/suite/aggregate-replay-v1 \
  --llm-output-dir output/composition-scaling/llm/completed-run \
  --vision-output-dir output/composition-scaling/vision/completed-run
```

## Child interchange and publication safety

Each child `RUN_COMPLETE.json` binds a safe report basename, exact byte count,
SHA-256 digest, final status, experiment name, and the closed authority object.
The bound report contains a `suite_export` with exactly these categories:
modality, protected-unit population name, model keys, seeds, scales, authority,
one resource component per model, and the complete aggregate subset-scalar
matrix. Unknown or extra interchange fields are rejected.

The shared report contains no dialogue text, prompt text, tokens, images,
per-example predictions, logits, activations, gradients, source paths, machine
paths, run identifiers, record identifiers, or exact rosters. Model keys,
aggregate metrics, category gates, public matrix sizes, and cryptographic
artifact digests are retained. `RUN_COMPLETE.json` has no artifact paths because
the three suite basenames are frozen by config; it records only artifact roles,
byte counts, and hashes.

## Interpretation limits

- These are descriptive screens, not powered release tests or causal scaling
  laws.
- Same-population subset composition does not establish independence between
  model errors or attacks.
- Five seeds estimate sensitivity within this registered design; they do not
  establish production-distribution coverage.
- Cross-modal resource vectors are not throughput forecasts for concurrent
  serving—the experiment is serial.
- No empirical result overrides an absorbing legal, rights, or direct-disclosure
  gate.
- Release still requires a complete signed contract, registered recipient
  interfaces, approved recollection, and the normative release protocol.
