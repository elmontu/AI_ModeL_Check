# Full-EuroSAT-RGB vision training-hook experiment

This experiment runs aggregate training hooks on the canonical torchvision
0.28.0 AlexNet and DenseNet-121 implementations, both trained from scratch,
while using all 27,000 real EuroSAT RGB satellite image patches: 21,600 for
training and 5,400 for untouched test evaluation. It measures software
execution and scale; it is not statistical proof of safety, a privacy result,
robustness guarantee, model assessment, or release authorization.

## Frozen source and split

[`config.json`](config.json) uses experiment schema `1.1` and binds the canonical
[EuroSAT v2 Zenodo record](https://zenodo.org/records/7711810) (DOI
`10.5281/zenodo.7711810`) and its `EuroSAT_RGB.zip` object:

- 94,658,721 bytes, with an identical hard download cap;
- SHA-256
  `b4f5b234ecb7d7ff9c6cddb046543b4717c53fd6e9815be6c0e80cc614f51b90`;
- Zenodo MD5 `f46e308c4d50d4bf32fedad2d3d62f3b`; and
- exactly 27,000 JPEGs in the ten registered class directories.

The worker streams the one object through the byte cap, disables automatic
redirects, and validates every redirect target before requesting that hop.
It then verifies both digests and safely extracts the archive. Extraction
rejects traversal, links, encryption, extra payloads, malformed paths, images
over 1 MB, wrong class counts, and more than 200 MB of expanded content. A
manifest hashes every extracted image. Its exact 4,053,063 serialized bytes are
preregistered as SHA-256
`f09028023218981546f9c4896a4f1b7201e4b73b3bdeb2c0b0fbe0003582a4d3`; its
canonical JSON digest is
`ffe4a9c460a2b20b3f2c86898733efaceac581b4d9dfc900fc73e8b553067c61`.
Cached replay caps the manifest before parsing and reapplies every path, type,
per-file, class-count, total-size, and content-digest bound. Offline replay
requires the same cached archive and re-verifies the archive and extraction.
All 27,000 files must also decode as JPEG, RGB, and 64x64; decoded pixels are
never persisted by validation.

EuroSAT consists of Sentinel-2 RGB land-use and land-cover patches, not
generated fixtures. The complete, naturally imbalanced class distribution is
used (2,000–3,000 images per class). Within each class, relative paths are
ordered by `sha256("3407:" + relative_path)`: the first 80% form the 21,600-row
training set and the remaining 20% form the 5,400-row untouched test set. The
split is deterministic, class-stratified, disjoint, and hash-reported. It is not
spatially separated, so spatial autocorrelation and new-region generalization
remain untested. This is a path-hash split: image-content digests validate
uniqueness and cross-roster non-overlap, but do not choose the roster.

The preregistered relative-path roster SHA-256 values are
`3e26b9ee7014071cd257715e8c0895f478d9256464f3afb40a26bfed3c148b75`
for training and
`c0e582d0dd8b88b41ffb08998eb0fcef5d31742815098b18c7c6e8ef2e1f0387`
for test. Independent verification of the pinned archive found 27,000 unique
JPEG SHA-256 values and zero content-digest overlap between the rosters. The
worker fails if either fact changes.

No synthetic training samples or random training augmentation are used. Native
64x64 images are deterministically resized to 96x96 and normalized. The
red-team stage derives ephemeral perturbations from a bounded real test subset;
they are not added to the corpus or training split. Source images and labels
necessarily remain in the governed dataset cache; their values, paths, and
per-example results never enter reports or telemetry.

The canonical Zenodo record declares `mit-license`. EuroSAT also contains
modified Copernicus Sentinel data, whose terms still require review. The
executable release gate is therefore `MANUAL_REVIEW_REQUIRED`, not an automatic
legal clearance.

## Models, workload, and hooks

The runtime is frozen to PyTorch 2.13.0 and torchvision 0.28.0. Both models use
the canonical torchvision implementation at tag `v0.28.0` (BSD-3-Clause),
`weights=None`, and `num_classes=10`. No pretrained weights or remote model code
are loaded; all parameters begin from seeded random initialization. The seed
and deterministic data order do not imply bitwise-reproducible CUDA training.
The report hashes the installed torchvision package file manifest, both actual
constructor source files, and the `ImageFolder` and default-loader sources. It
also records exact package versions, Pillow and its image-source digest,
libjpeg, CUDA/cuDNN, NVIDIA driver, GPU, and compute capability. The declared
BSD-3-Clause license remains
`DECLARED_REQUIRES_INDEPENDENT_REVIEW`; declaration is not legal clearance.
Before any dataset access or training, those observations must match the exact
EC2 baseline registered in `config.json`: the installed Torch distribution,
torchvision distribution and package, unwrapped AlexNet and DenseNet source
files, loader source, Pillow distribution and package, `Image.py`, `_imaging`,
Pillow 12.3.0, and libjpeg 6.2. A same-version modified package therefore fails
closed. The complete runtime and implementation observations are rehashed after
the workload and must be unchanged before publication. Hardware and driver
details remain recorded observations rather than portable model claims.

| Model | Exact hook allowlist |
|---|---|
| `torchvision.models.alexnet` | `features.2`, `features.12`, `classifier.6` |
| `torchvision.models.densenet121` | `features.conv0`, `features.denseblock4`, `classifier` |

AlexNet's two MaxPool targets intentionally avoid the known conflict between
full backward hooks and outputs immediately mutated by its in-place ReLUs. Each
target still lies on the real early/late feature path. Every one of the 169
optimizer steps must emit exactly one forward and one full-backward event from
all three registered modules. The shared collector also scans all parameter
gradients before each optimizer update. Non-finite values, incomplete coverage,
more than 1,500 events, or incomplete hook cleanup fail closed.

Before the measured epoch, each architecture runs a paired noninterference
control on CPU using the same two real examples. The run with hooks must match
the no-hook run exactly on initial state, loss bits, complete named-gradient
digest, and post-step state digest, while also meeting complete hook coverage.
The report records `control_device: cpu` and
`cuda_noninterference_proven: false`. This exact bounded CPU control does not
prove noninterference for CUDA training or for untested inputs and operators.

The full workload uses CUDA with registered seeds and deterministic split and
batch order. It calls `torch.use_deterministic_algorithms(True,
warn_only=True)`, disables cuDNN benchmarking, and enables cuDNN deterministic
mode. Canonical AlexNet and DenseNet-121 backward invokes the registered
`adaptive_avg_pool2d_backward_cuda` nondeterministic kernel. The worker requires
that allowlisted warning, rejects unexpected nondeterminism warnings, and
records other warning counts and digests. It explicitly reports
`bitwise_reproducible: false` and `single_run_variance_estimated: false`; full
CUDA execution must independently meet complete hook and optimizer coverage.

Each architecture consumes the full 21,600-image training split for one FP32
SGD epoch. The full 5,400-image test split is evaluated before and after
training without tuning, selection, early stopping, or checkpoint choice. The
report includes test loss/accuracy, state hashes, parameter counts, duration,
examples/second, peak GPU memory, optimizer/event coverage, and telemetry-file
hashes. One epoch is a systems workload, not a competitive quality recipe.

The reused LLM collector's legacy `tokens` field is explicitly interpreted as
normalized image scalar elements; `target_tokens` counts class targets. Neither
field stores source values.

The collector ledger genesis is the SHA-256 of the immutable registered run
context: source/config hashes, run and dataset identity, extraction and roster
digests, runtime and installed implementation provenance, model registration,
initial state, pre-training evaluation, non-interference result, protocol
registry, and non-authorizing release decision. The worker independently
replays both the collector chain and the exact published JSONL payload. Context
or event tampering fails verification.

## Bounded red-team screens

After training, a deterministic near-class-balanced 512-real-image test subset is
evaluated under four conditions: clean input, brightness factor 1.25, Gaussian
pixel noise with standard deviation 0.05, and white-box FGSM at `2/255`. The
FGSM threat model is untargeted and true-label. The worker reports aggregate
cross-entropy, accuracy, accuracy drop, measured pixel-space L-infinity, and
attack success rate conditioned on clean-correct examples. FGSM fails closed if
its measured distance exceeds `2/255 + 1e-7`; Gaussian noise uses a registered
deterministic CPU generator. These small, known perturbations are descriptive smoke screens: they cannot clear a
robustness or security gate and do not cover adaptive attacks, physical effects,
spectral changes, spatial shift, or unseen regions.

Each emitted red-team result is explicitly an `evidence_direction: screen`
with `can_clear: false`, `can_block: false`,
`attack_battery_eligible: false`, `assessment_input_emitted: false`, and
`requires_approved_recollection: true`. Decision-bearing use requires fresh
collection by an approved isolated worker under the typed attack-battery
contracts and complete assessment bindings; this experimental report cannot be
restamped into that evidence after execution.

## Metadata/context release profiles

The experiment makes interface risk explicit instead of averaging different
disclosures into one score:

| Profile | Added disclosure | Release route |
|---|---|---|
| `M0_label_only` | Predicted class | Manual review still required |
| `M1_scores` | Class probabilities and confidence | Privacy and extraction review required |
| `M2_internal_features` | Embeddings, activations, per-example loss | Restricted to governed auditors |
| `M3_source_provenance` | Relative source paths, exact training roster, or geolocation | Block and redesign the release surface |

These are release-interface scenarios, not a claim that risk is numerically
monotone. In particular, M3 can disclose provenance or membership directly and
must not be diluted by favorable accuracy or perturbation results.

The machine-readable object is named `release_gate_summary`, with
`contract_semantics: illustrative_non_mrap_gate_summary` and
`mrap_release_contract_required: true`. It is an experimental gate summary,
not the normative nested MRAP `ReleaseContract`. The top-level report also
records `assessment_input_emitted: false`.

EuroSAT is a public benchmark and this deterministic split is publicly
reconstructible; the exact roster digests are internal experiment provenance,
not a proposed recipient interface. That does not generalize to protected data.
Exposing a protected exact roster remains blocked. Removing the field changes
the interface and requires a fresh assessment; it does not clear the original
M3 design.

## Run and replay

From the repository root in the exact CUDA runtime:

```bash
python scripts/run_vision_training_hook_audit.py \
  --config reproduction/vision-training-hook/config.json
```

To capture a candidate registry on a newly provisioned target without accessing
the dataset or training, run:

```bash
python scripts/run_vision_training_hook_audit.py \
  --config reproduction/vision-training-hook/config.json \
  --capture-runtime-provenance
```

Capture is non-authorizing. The candidate must be reviewed and committed before
the full worker will accept that runtime.

After the cache has been created, prove the dataset path is network-independent:

```bash
python scripts/run_vision_training_hook_audit.py \
  --config reproduction/vision-training-hook/config.json \
  --offline
```

Every invocation reserves a fresh timestamped directory under
`output/vision-training-hook/`; a supplied `--output-dir` must not exist. Each
artifact is published atomically without overwrite:

- `vision-training-hook-report.json` — experimental execution observations and
  the illustrative, non-MRAP gate summary;
- `vision-training-hook-report.md` — human-readable experimental summary; and
- one bounded `training-telemetry-{model}.jsonl` ledger per architecture.

The JSON report is written last and is the run-completion signal. If it is
absent, the run is incomplete; individually valid telemetry or Markdown files
may remain after a failure and must not be mistaken for a completed result.

The exact configuration bytes are hashed before JSON parsing. The configuration,
runner, and hook implementation are rechecked before publication. Resolved
artifact basenames must be unique, every run directory must be fresh, and every
artifact is published without replacement. Public report provenance uses
logical repository-relative paths and artifact basenames rather than absolute
machine paths. No model weights are exported. Operational
success still leaves quality, privacy, security, robustness, fairness, and
production-distribution gates unassessed. Every report ends with
`decision: no_release_authorization`, `authorization_eligible: false`,
`assessment_input_emitted: false`, and `can_clear: false`.

Scale fields distinguish 27,000 unique corpus inputs from repeated
model/condition evaluations. The experiment runs one preregistered seed and has
no multi-seed confidence interval. Throughput covers the complete single epoch,
with no warm-up exclusion or separate steady-state estimate, and must not be
generalized beyond the reported software and hardware. The complete-corpus
workload is a systems scalability stress test, not a statistical safety,
privacy, robustness, fairness, generalization, or production-capacity proof.
