# Real-data training-hook execution audit — 2026-09-02

Status: **completed experimental execution**
Decision: **no release authorization**

This is the curated, publication-safe record of two end-to-end GPU integration
runs: a three-model language-model matrix and a two-model computer-vision
matrix. Both used immutable public-source data rather than synthetic training
fixtures, installed hooks during training, replayed aggregate telemetry, and
evaluated how recipient-visible metadata or model context changes the release
route.

The runs show that the experimental software executes at the registered scale.
They do not establish privacy, safety, robustness, fairness, quality,
generalization, production capacity, or legal clearance. They emit no MRAP
assessment input and cannot clear, block, authorize, deploy, or activate a
model. Any decision-bearing empirical result requires approved recollection by
the isolated, typed attack-battery path described in the
[integrated audit specification](system-audit-specification.md).

## 1. Audit boundary

| Included here | Deliberately excluded |
|---|---|
| Aggregate losses, accuracy, attack screens, throughput, memory, hook coverage, frozen revisions, and SHA-256 digests | Dialogue text, images, token IDs, logits, activations, gradients, per-example predictions, exact sample rosters, absolute host paths, credentials, and raw telemetry |
| Public-source identifiers and reproducible configuration/code hashes | The source Parquet object, extracted image corpus, trained weights, caches, and internal run directories |
| Release-process interpretation and explicit non-claims | Any assertion that an experimental report is a release contract, assessment report, attack-battery submission, or authorization |

Raw source and telemetry artifacts were generated in governed experiment
storage and digest-bound by the workers. They are not committed because the LLM
source object contains real dialogue and excluded sensitive columns, while both
raw reports contain replay identifiers unnecessary for public review.

## 2. Common execution controls

- Every remote dataset or model artifact was revision- or byte-pinned and
  digest-verified before use. The accepted end-to-end replays then loaded only
  the verified local cache.
- Each model used a fresh no-clobber run directory and its own append-only
  telemetry chain. The report was accepted only after replaying that chain and
  writing the registered completion signal last.
- Hooks observed bounded scalar aggregates. They did not retain raw examples,
  token IDs, logits, model activations, or gradients.
- LLM hook/non-hook non-interference used an exact same-state comparison.
  Vision used an exact deterministic CPU comparison; that comparison does not
  prove CUDA non-interference.
- CUDA workload order was seeded. The vision runtime used registered warn-only
  deterministic-algorithm handling because canonical adaptive-average-pooling
  backward has no deterministic CUDA implementation in the tested runtime.
  Unexpected nondeterminism warnings failed the run; bitwise CUDA
  reproducibility is not claimed.
- All screens were configured with `can_clear=false`, `can_block=false`,
  `assessment_input_emitted=false`, and `attack_battery_eligible=false`.
  Protected exact-roster disclosure is a separate logical redesign condition,
  not a favorable or unfavorable attack measurement.

## 3. LLM matrix: WildChat and three model families

### 3.1 Frozen workload

| Item | Registered value |
|---|---|
| Dataset | [`allenai/WildChat-4.8M`](https://huggingface.co/datasets/allenai/WildChat-4.8M), revision `c827c6df8fcf008219ffaffa4d1dd77491099367` |
| Verified Parquet object | 125,527,585 bytes; 37,208 rows; SHA-256 `6df660dca78dd92b865bef09b928992ceb6c913b4f06082315876a5997ad2eaa` |
| Upstream scale recorded by the dataset card | 3,199,860 conversations across 86 shards; the run used one pinned shard, not the full corpus |
| Eligible projection | First English user/assistant pair; source-marked non-toxic and unredacted; 15,730 unique eligible rows after deduplication |
| Shared selected cohort | 9,216 rows: 8,192 training and 1,024 untouched holdout; zero cross-split identifier overlap |
| Training | One FP32 epoch per model; batch 16; sequence length 256; 512 optimizer steps per model |
| Audit cells | Separate 256-member/256-nonmember calibration and audit cells for each measured knowledge profile |
| Hardware/runtime | NVIDIA L4; Python 3.13.15; PyTorch 2.13.0+cu130; Transformers 5.16.1; PyArrow 25.0.1 |

The projection excluded IP hashes, geography, request headers, timestamps,
provider request identifiers, and moderation payloads before selection. The
verified cached Parquet object necessarily retains its original columns and
therefore remains governed sensitive experiment data.

### 3.2 Training and hook results

| Model and frozen revision | Parameters | Holdout NLL / PPL before | Holdout NLL / PPL after | Steps | Rows/s | Peak GPU GiB | Aggregate hook coverage | Release route |
|---|---:|---:|---:|---:|---:|---:|---|---|
| DistilGPT2 `2290a62682d06624634c1f46a6ad5be0f47f38aa` | 81,912,576 | 2.9170 / 18.49 | 2.4882 / 12.04 | 512 | 42.49 | 6.11 | complete | assessment incomplete |
| Meta OPT-125M `27dcfa74d334bc871f3234de431e71c6eeba5dd6` | 125,239,296 | 2.5223 / 12.46 | 2.1913 / 8.95 | 512 | 31.16 | 6.37 | complete | **blocked for production/commercial use by model license** |
| Pythia-160M `50f5173d932e8e61f858120bcb800b97af589f46` | 162,322,944 | 2.4589 / 11.69 | 2.3998 / 11.02 | 512 | 28.96 | 7.43 | complete | assessment incomplete; policy/manual review required |

Across the three models, the worker recorded and replayed 3,072 forward and
3,072 backward aggregate-hook observations with zero non-finite events and
complete registered-module and trainable-parameter coverage. Throughput and
memory are single-run observations on this exact stack, not hardware-neutral
scaling laws. Cross-model differences are descriptive because model assignment
was not randomized.

### 3.3 Context and metadata risk

Balanced accuracy (BA) and area under the ROC curve (AUC) below are descriptive
before/after membership screens. The samples are too small to be release
criteria, null results cannot clear privacy, and differences across profiles do
not establish a monotone or causal effect of “more context.”

| Model | Knowledge profile | Before BA / AUC | After BA / AUC | Release-process interpretation |
|---|---|---:|---:|---|
| DistilGPT2 | K0 prior only | 0.500 / 0.500 | 0.500 / 0.500 | Inconclusive; no clearance |
| DistilGPT2 | K1 exact candidate metadata | 0.486 / 0.460 | 0.486 / 0.460 | Screen only; requires recipient access to the six registered metadata fields |
| DistilGPT2 | K2 arbitrary-candidate loss | 0.496 / 0.495 | 0.553 / 0.566 | Not applicable to a text-only interface; screen only for a scoring or white-box recipient |
| DistilGPT2 | K3 metadata plus loss | 0.488 / 0.456 | 0.518 / 0.510 | Same access qualification; no clearing or blocking authority |
| Meta OPT-125M | K0 prior only | 0.500 / 0.500 | 0.500 / 0.500 | Inconclusive; no clearance |
| Meta OPT-125M | K1 exact candidate metadata | 0.486 / 0.460 | 0.486 / 0.460 | Screen only |
| Meta OPT-125M | K2 arbitrary-candidate loss | 0.500 / 0.497 | 0.666 / 0.672 | Not applicable to a text-only interface; elevated descriptive screen |
| Meta OPT-125M | K3 metadata plus loss | 0.496 / 0.459 | 0.604 / 0.634 | Same access qualification; elevated descriptive screen |
| Pythia-160M | K0 prior only | 0.500 / 0.500 | 0.500 / 0.500 | Inconclusive; no clearance |
| Pythia-160M | K1 exact candidate metadata | 0.488 / 0.452 | 0.488 / 0.452 | Screen only |
| Pythia-160M | K2 arbitrary-candidate loss | 0.500 / 0.490 | 0.641 / 0.676 | Not applicable to a text-only interface; elevated descriptive screen |
| Pythia-160M | K3 metadata plus loss | 0.486 / 0.457 | 0.586 / 0.630 | Same access qualification; elevated descriptive screen |
| All | K4 authenticated exact protected-training roster | N/A | N/A | Direct disclosure: block the membership gate and redesign the interface |

The release process therefore keys on the actual recipient interface, not on an
abstract context label. Text generation does not imply arbitrary-candidate
loss access, and generated-token log probabilities do not by themselves imply
the ability to score an arbitrary proposed record. Any interface change that
adds those capabilities requires reassessment.

### 3.4 LLM artifact bindings

| Artifact | SHA-256 |
|---|---|
| Frozen configuration bytes | `39e5b5fe8eed4ebb1d512063d6e13a0e8f24656f9043063e879bd0d5d5141480` |
| Worker source | `8b0bca73293e20232ac45e35b2762e254977fbdbe09f70967be257ee05719ffd` |
| Shared hook source | `595de99355974866524ca1e11c0cd4d2d14c80a0846657daea36d66ee26ff33c` |
| Completion manifest | `629ff183a068059b41b15cc3d2001e98d8a72e67c71a4ad6b3b3badb554937f8` |
| Full internal JSON report | `c538a7430e4172c99b4be72a9dba8913d0a78639bc095141aa3ca7445db2851e` |
| Sanitized generated Markdown report | `d844455b1ab0459b0b23aa37f4955f00d4c0419e04c761490d65b94d2eaab2ba` |
| DistilGPT2 / OPT-125M / Pythia telemetry chains | `20f887d668780103b9b566211b13515f647f07c58f4fcde37c5794ec7a26de04` / `5a247ece5d7bf287f7813567be7e41fc447f8f168ec4359efcec8b256fbeb92b` / `3cd4164aedd5d7209991a8093fe870bd6cf2719cf353228a9ffecba88dbb00b6` |

## 4. Vision matrix: full EuroSAT, AlexNet, and DenseNet-121

### 4.1 Frozen workload

| Item | Registered value |
|---|---|
| Dataset | [EuroSAT RGB, Zenodo record 7711810](https://zenodo.org/records/7711810), DOI `10.5281/zenodo.7711810` |
| Verified archive | 94,658,721 bytes; SHA-256 `b4f5b234ecb7d7ff9c6cddb046543b4717c53fd6e9815be6c0e80cc614f51b90` |
| Corpus | All 27,000 real Sentinel-2 RGB JPEG patches, 64×64 pixels, ten classes; 27,000 unique image digests |
| Split | Deterministic class-stratified path-hash split: 21,600 training and 5,400 test; zero cross-split content overlap |
| Training | Canonical torchvision AlexNet and DenseNet-121 constructors, `weights=None`, ten-class heads, all parameters, one FP32 epoch, batch 128, 169 steps per model |
| Evaluation | Complete test split before and after training; deterministic 512-image real-data subset for perturbation screens |
| Preprocessing | Native 64×64 RGB deterministically resized to 96×96; no synthetic samples and no training augmentation |
| Hardware/runtime | NVIDIA L4; PyTorch 2.13.0+cu130; torchvision 0.28.0+cu130; exact installed implementation and image-decoder provenance matched |

### 4.2 Training and hook results

| Model | Parameters | Test CE before | Accuracy before | Test CE after | Accuracy after | Train images/s | Peak GPU GiB | Steps | Hook coverage | Exact CPU no-hook control |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| AlexNet | 57,044,810 | 2.302356 | 0.0980 | 1.937292 | 0.2394 | 937.02 | 1.59 | 169 | complete | pass |
| DenseNet-121 | 6,964,106 | 2.374993 | 0.1094 | 0.893837 | 0.6898 | 369.04 | 3.02 | 169 | complete | pass |

The matrix processed 43,200 training-example evaluations and 21,600 complete
held-out-example evaluations across the two architectures. Each telemetry chain
contained 507 forward and 507 backward aggregate-hook observations with
complete registered coverage. The one-epoch, one-seed run from random
initialization is an integration and scale test, not a competitive model study.

### 4.3 Bounded real-image red-team screens

| Model | Condition | Cross-entropy | Accuracy | Accuracy drop from clean | Attack success on clean-correct | Measured pixel L∞ |
|---|---|---:|---:|---:|---:|---:|
| AlexNet | clean | 1.961986 | 0.2344 | 0.0000 | 0.0000 | 0.00000000 |
| AlexNet | brightness ×1.25 | 2.024098 | 0.2148 | 0.0195 | 0.1583 | 0.19999999 |
| AlexNet | Gaussian noise σ=0.05 | 1.961695 | 0.2266 | 0.0078 | 0.0500 | 0.27677843 |
| AlexNet | untargeted true-label FGSM 2/255 | 2.015042 | 0.2305 | 0.0039 | 0.0750 | 0.00784317 |
| DenseNet-121 | clean | 1.044175 | 0.6523 | 0.0000 | 0.0000 | 0.00000000 |
| DenseNet-121 | brightness ×1.25 | 1.822046 | 0.4766 | 0.1758 | 0.3982 | 0.19999999 |
| DenseNet-121 | Gaussian noise σ=0.05 | 3.183635 | 0.2715 | 0.3809 | 0.6497 | 0.27677843 |
| DenseNet-121 | untargeted true-label FGSM 2/255 | 2.951896 | 0.2422 | 0.4102 | 0.6287 | 0.00784317 |

Attack success is conditioned on examples classified correctly in the clean
condition. These are smoke screens over one deterministic subset, not a
complete threat-model battery or robustness guarantee. In particular, the
observed DenseNet sensitivity is a reason to commission an approved,
preregistered robustness assessment—not evidence that this experimental worker
may itself block a release.

### 4.4 Vision metadata and release routes

| Profile | Recipient-visible surface | Illustrative route |
|---|---|---|
| M0 label only | Predicted class | manual review required |
| M1 scores | Class probabilities and confidence | privacy and extraction review required |
| M2 internal features | Embeddings, activations, or per-example loss | restricted auditor only |
| M3 source provenance | Source-relative path, exact training roster, or geolocation if available | **blocked; redesign required** |

This is an illustrative non-MRAP gate summary. Dataset rights, model
implementation licensing, quality, privacy, security, and intended-use review
remain incomplete. Operational hook success cannot satisfy any of them.

### 4.5 Vision artifact bindings

| Artifact | SHA-256 |
|---|---|
| Frozen configuration bytes | `3f2ef402e9e2a6fb3a2fb47a930de30384056682d85dae6c2134694dd6aa1412` |
| Frozen configuration canonical form | `4cc042982cadbe6d713edf695ab2373c7ef9f07fffaef9094b7963d83f273f2b` |
| Worker source | `85261cd39de3036211fff174b7b9bce5aaf87a69baac17cd42b03aff9eb03e81` |
| Shared hook source | `595de99355974866524ca1e11c0cd4d2d14c80a0846657daea36d66ee26ff33c` |
| Full internal JSON report | `5013a4b7af452cce95a3c7950a8ee46e5691446fd8040422c4782be801e64bd1` |
| Sanitized generated Markdown report | `868d495aab1f634ae23921f0d9a59e796f026a2c833ad4dddf86868730d56fd4` |
| AlexNet / DenseNet-121 telemetry chains | `1421beac6cbd71f54602f97a39d9210e128bdfb4ccc820b518088f6d06834d6f` / `9627547706a7e29c7abd764afeabd9971f12bcc885275edadb479bd838582f62` |

## 5. Scalability interpretation

The experiments cover five real/canonical architecture implementations and
two materially different data modalities. The vision run uses the complete
27,000-image benchmark; the LLM run verifies ingestion from a 125.5 MB shard
and performs 1,536 optimizer steps across 369.5 million model parameters. The
workers also exercised immutable acquisition, deterministic cohorting, full
training-time hooks, telemetry replay, bounded red teaming, and completion
publication.

That is sufficient to reject a toy-only or synthetic-only integration claim.
It is not sufficient to claim horizontal scalability, multi-node behavior,
steady-state throughput, cost efficiency, full-corpus LLM training, or
production reliability. Those claims would require repeated trials, warm-up
separation, confidence intervals, larger and more representative workloads,
failure injection, and distributed back-pressure and recovery tests.

## 6. Legal, scientific, and release limitations

- WildChat contains real human/provider interaction data. Its database-license
  declaration does not by itself clear rights in individual contents or
  provider outputs. An explicit retention/deletion policy and legal review are
  required.
- Meta OPT-125M's registered license is non-commercial research-only, so the
  production/commercial release route is blocked independently of model
  metrics. Pythia and all intended human-facing uses still need applicable
  policy and legal review.
- EuroSAT is a bounded European Sentinel-2 benchmark. The split is not spatially
  separated, so spatial autocorrelation, temporal shift, new-region behavior,
  higher-resolution production data, and rare conditions remain untested.
  Dataset and underlying imagery terms require independent review.
- No confidence intervals or repeated-seed variance estimates were produced.
  The measured screens cannot be promoted into MRAP evidence after the fact.
- A complete release still requires a current `AssessmentRequest 5.0`, policy,
  approved analyzers and any mandatory typed attack battery, a valid assessment
  and optimization result, an external atomic authorization, and live gateway
  enforcement of the exact artifact and interface.

Final machine-level disposition for both accepted runs:
`no_release_authorization`; `authorization_eligible=false`;
`assessment_input_emitted=false`.
