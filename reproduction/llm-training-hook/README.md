# LLM training-hook experiment

This retained configuration exercises aggregate-only telemetry hooks while
sequentially fine-tuning three real causal language models on the same pinned
real-conversation cohort. It is an integration and research experiment, not an
assessment, privacy guarantee, release contract, content-rights determination,
or model authorization. Every generated report must remain experimental and end with
`decision: no_release_authorization` and `authorization_eligible: false`.

## Frozen inputs

[`config.json`](config.json) binds all remote inputs needed by the runner:

- the `mlabonne/llm-datasets` catalog at commit
  `67c52949f3153e311f0183db0700cca6d611524b`, whose README SHA-256 is
  `64047256aa9e8a888707cce2611b9d6ab58b50c3a6498ed5abd853de2c9546a1`,
  with the named dataset entry verified in those exact bytes;
- the catalog-listed `allenai/WildChat-4.8M` dataset at revision
  `c827c6df8fcf008219ffaffa4d1dd77491099367`;
- the single direct Parquet object `data/train-00000-of-00086.parquet`, whose
  required SHA-256 is
  `6df660dca78dd92b865bef09b928992ceb6c913b4f06082315876a5997ad2eaa`
  and whose required size is 125,527,585 bytes / 37,208 rows;
- the dataset card's declared `ODC-By-1.0` database license, bound to the exact
  14,962-byte card (SHA-256
  `946c2526ed254c35380b9366b3ca1c1bded65695c21c388194e1b643acac70c6`)
  and 19,947-byte `LICENSE.md` (SHA-256
  `a7c7f6bdb20d261b8726c7594afb5832b36926e0cabfa116c41f58625bbc776c`),
  without treating either source as clearance for individual conversation
  content or provider outputs; and
- three exact model revisions and their model-specific hook targets.

| Model key | Frozen model | Owner | Declared license | Hook targets |
|---|---|---|---|---|
| `distilgpt2` | `distilbert/distilgpt2@2290a62682d06624634c1f46a6ad5be0f47f38aa` | Hugging Face | Apache-2.0 | `transformer.h.0`, `transformer.h.5` |
| `meta-opt-125m` | `facebook/opt-125m@27dcfa74d334bc871f3234de431e71c6eeba5dd6` | Meta | [OPT-175B license, non-commercial research only](https://huggingface.co/facebook/opt-125m/blob/27dcfa74d334bc871f3234de431e71c6eeba5dd6/LICENSE.md) | `model.decoder.layers.0`, `model.decoder.layers.11` |
| `pythia-160m` | `EleutherAI/pythia-160m@50f5173d932e8e61f858120bcb800b97af589f46` | EleutherAI | Apache-2.0 | `gpt_neox.layers.0`, `gpt_neox.layers.11` |

The worker downloads the named Parquet object, dataset card, and license file
directly and verifies each registered byte size and digest before use. It does
not load a dataset script or enable remote code. It projects only the first
user/assistant pair from rows marked English,
`toxic=false`, and `redacted=false`, requires non-empty content and turn IDs,
and removes exact duplicate pairs before deterministic selection. Source IP
hashes, geography, request headers, timestamps, OpenAI request IDs, and
moderation payloads are excluded from the loaded projection. These filters are
a bounded eligibility rule, not a guarantee that dialogue content is harmless,
accurate, deidentified, or legally cleared.

Model and tokenizer loading must also remain revision-pinned with remote code
disabled. The report records the resolved runtime and local artifact hashes;
the upstream identifiers alone are not a retained dataset or model snapshot.
DistilGPT2 and Pythia require safetensors. The pinned OPT revision instead uses
legacy PyTorch weight serialization: the worker must keep remote code disabled,
request weights-only loading, verify the pinned artifacts, and run in the
isolated experiment environment without credentials. This exception must not
silently become a general permission to deserialize arbitrary model files.
The worker first fetches and hashes the exact registered artifact set, then
loads only from that verified local snapshot with `local_files_only=true`,
`trust_remote_code=false`, and no credential token. `local_files_only` prevents
the Transformers loader from fetching missing files; it is not operating-system
network isolation. A deployment that requires hard egress isolation must add a
network namespace, firewall, or equivalently enforced worker boundary.

## Bounded design

The selected shard contains 37,208 rows; 16,135 meet the registered first-pair
eligibility checks before exact-pair deduplication. The worker derives opaque
record IDs from the upstream conversation hash and first-pair content digest,
ranks eligible deduplicated records by the lexical order of
`sha256("3407:" + row_id)`, takes the first 9,216, assigns the first 8,192 to
training and the remaining 1,024 to the holdout, and verifies identifier and
content disjointness. Every model receives these same raw row IDs. Each model's
tokenizer produces model-specific token and truncation metadata. The holdout is
evaluated before and after training for completion loss, perplexity, and
knowledge-profile screens, but is never used for checkpoint selection,
hyperparameter tuning, hook thresholds, early stopping, or model choice.

The frozen training limits are one deterministic FP32 epoch, batch size 16,
maximum sequence length 256, maximum prompt length 128, AdamW learning rate
`5e-5`, weight decay `0.01`, and seed `3407`. With 8,192 training rows this is
512 expected optimizer steps per model. Models run sequentially from their own
fresh revision-pinned initialization. This is a material real-data integration
workload, but one epoch over one shard still does not establish training
adequacy, external generalization, safety, fairness, privacy, or production
capacity.

Before tokenization, each user or assistant field is limited to 131,072 UTF-8
bytes and their combined record to 262,144 UTF-8 bytes. The worker tokenizes
the registered `User`/`Assistant` completion format, probes each frozen
tokenizer's actual special-token API, and accepts only a verified prefix-only
policy. Any model-specific prefix token is prepended and masked with the prompt;
completion loss begins only at assistant-response tokens. The report records
the tokenizer API used, prefix count, observed UTF-8 maxima, and truncation
indicators. These are bounded preprocessing facts, not evidence about text
safety or semantic fidelity.

Forward, backward-output-gradient, and parameter-gradient observations are
restricted to the two modules listed for the active model. The hook reduces
observations immediately to finite fractions, L2 norms, absolute maxima, and
loss summaries. It may emit at most 10,000 events, must fail on a non-finite
observation, and must remove every registered handle when each model exits.
Raw prompts, responses, token IDs, labels, activations, gradients, parameters,
or other tensors must never be written to telemetry or reports. Aggregate
telemetry is hash-bound to the configuration, code, dataset, model revision,
model key, run, step, and module; this self-reported provenance is not workload
attestation.

The Meta OPT entry has an independent legal boundary. Its pinned license is
restricted to non-commercial research, so its production/commercial release
gate is `BLOCKED` regardless of model quality, telemetry health, or privacy
screen results. The experiment does not grant or interpret licensing rights;
production users must complete independent legal review for every artifact and
dependency.

Pythia's Apache-2.0 license is not the same as a deployment endorsement. Its
[pinned model card](https://huggingface.co/EleutherAI/pythia-160m/blob/50f5173d932e8e61f858120bcb800b97af589f46/README.md)
discourages deployment and human-facing use and calls for risk and bias review.
The configuration therefore requires a policy/manual-review gate for any such
use. This is a use-policy restriction, distinct from OPT's non-commercial
license prohibition, and it cannot be waived by a favorable technical result.

## Context-knowledge risk ladder

For each model, before and after training, the same deterministic split also
demonstrates how an attacker's knowledge and the released interface change the
membership question. Training rows act as members and holdout rows as
nonmembers. Each side contributes 256 rows to calibration and a disjoint 256
rows to audit, giving equal member/nonmember priors in both partitions. These
comparisons remain descriptive screens with no statistical-power claim rather
than release criteria: they cannot block or clear, and a null or chance-level
result is inconclusive.

| Knowledge level | Added knowledge | Realizable release surface | Interpretation |
|---|---|---|---|
| `K0_prior_only` | Equal member/nonmember prior only | Every registered fragment | Dummy baseline; no model-specific evidence |
| `K1_candidate_metadata` | Exact `sequence_tokens`, `target_tokens`, `source_turn_count`, `source_model_is_gpt4`, `prompt_truncated`, and `response_truncated` | Only a fragment that explicitly exposes all six exact candidate metadata fields, with the registered tokenizer and preprocessing known | Metadata-confounding screen, not model leakage by itself |
| `K2_candidate_model_loss` | Complete candidate dialogue plus `target_nll` | White-box access or an interface that scores every supplied candidate continuation token; generated-token-only log probabilities are insufficient | Loss-based membership screen; unavailable to the registered text-only fragment |
| `K3_metadata_plus_model_loss` | All K1 metadata plus complete candidate dialogue and K2 loss | Only when every K1 metadata and K2 arbitrary-candidate-scoring precondition holds | Describes the combination of side information; it is still only a screen |
| `K4_exact_training_roster` | Authenticated `exact_training_roster_membership` | A separate local, administrative, download, log, metadata, or package path that discloses the exact protected roster | Direct lookup reveals membership; this is disclosure, not statistical inference |

The worker emits six precise illustrative interface fragments. Text-only
generation without a roster realizes K0 only. Text generation with all six
exact candidate metadata fields realizes K0 and K1. Generated-token log
probabilities alone still realize only K0 because they cannot score an
arbitrary supplied continuation. An arbitrary-candidate scoring interface
without source metadata realizes K0 and K2. White-box release with all six
metadata fields realizes K0 through K3. A protected-data package with an exact
training roster realizes K0 and K4 and is blocked. These fragments are partial
contract illustrations: none is a complete MRAP release contract, and none
claims that an ordinary text-only interface exposes K1. White-box assessor
access likewise does not widen a text-only recipient interface.

If any declared or undeclared path exposes an exact roster manifest,
membership is directly disclosed regardless of attack accuracy or sample
size. This public experiment's roster is reconstructible from its pinned
input, seed, and selection rule, but the roster view is an internal governance
scenario and is not part of the declared text-only recipient interface.

Comparisons between knowledge levels, before versus after training, or across
models are descriptive. The models have different architectures, tokenizers,
pretraining histories, parameter counts, and licenses; the fitted screens also
use bounded registered samples. Results therefore need not be monotone as knowledge grows and
must not be interpreted as causal effects of training, architecture, model
size, or side information.

The public-data experiment still reports `no_release_authorization` at every
level. For a real protected roster, exact roster exposure sets the membership
gate to `BLOCKED` and routes the release process to `REDESIGN_REQUIRED`: remove
the disclosure path, update the interface and artifact bindings, and reassess.
It must never be averaged with weaker screens or treated as evidence that a
different interface is safe.

## Run and inspect

Run from the repository root in the isolated LLM experiment environment:

```bash
python -m pip install -e '.[llm-experiments]'
python scripts/run_llm_training_hook_audit.py \
  --config reproduction/llm-training-hook/config.json
```

Each invocation creates a fresh run directory beneath
`output/llm-training-hook/` and refuses to overwrite a non-empty run. Immutable
downloads are held separately in `output/llm-training-hook/cache/`; after they
have been verified once, add `--offline` to require cache-only execution.
The dataset cache is not metadata-only: it retains the complete source Parquet,
including dialogue text and sensitive upstream columns omitted by the Arrow
training projection. The worker restricts its directory/file modes to
`0700`/`0600`; operators must define retention, access, legal-hold, and deletion
rules and must never copy this cache into a recipient release package.
Generated files are ignored. The default layout is:

```text
output/llm-training-hook/
├── cache/
└── run-YYYYMMDDTHHMMSS-ffffffZ/
    ├── RUN_COMPLETE.json
    ├── llm-training-hook-report.json
    ├── llm-training-hook-report.md
    ├── training-telemetry-distilgpt2.jsonl
    ├── training-telemetry-meta-opt-125m.jsonl
    └── training-telemetry-pythia-160m.jsonl
```

Within each fresh run:

- `RUN_COMPLETE.json` is written last and binds the exact required artifact
  names, byte sizes, and SHA-256 digests; its absence means the run is
  incomplete even if other files exist;
- `llm-training-hook-report.json` is the machine-readable result;
- `llm-training-hook-report.md` is the human audit summary; and
- `training-telemetry-distilgpt2.jsonl`,
  `training-telemetry-meta-opt-125m.jsonl`, and
  `training-telemetry-pythia-160m.jsonl` contain the separate bounded aggregate
  event streams.

An operational pass requires exact input hashes, the shared 8,192/1,024
disjoint row split, 512 completed optimizer steps for each of three models, every
model-specific hook module, finite before/after holdout measurements, complete
handle removal, and internally consistent per-model telemetry counts and
digests. The report must also reproduce each model's before/after cells with
256 members and 256 nonmembers for calibration plus disjoint cells with 256
members and 256 nonmembers for audit, for every empirical knowledge profile,
and state which profiles the declared interface makes realizable. An
operational failure, a detected anomaly, or a successful run all remain
non-authorizing. A low loss, improved perplexity, favorable risk-screen score,
or absence of a hook alarm is not evidence that the model or training data is
safe.

The selected rows contain real human-user prompts and ChatGPT-generated
assistant responses. Dataset text is untrusted input: the worker must treat
code, URLs, tool syntax, and instructions in it as inert text, use no
model-generated tool calls, and run without deployment credentials or signing
keys. The dataset card's ODC-By declaration describes database rights; it does
not license, clear, or establish lawful reuse of each conversation or provider
output. Production use additionally requires independent content-rights,
license, data-governance, security, privacy, and provenance review.
