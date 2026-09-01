# OpenML benchmark package

This package specifies a provenance-complete OpenML benchmark run design. It does not by itself prove that a run completed or reconstruct unavailable historical model artifacts.

The benchmark corpus is OpenML-CC18, suite 99. The retained manifest records suite membership, dataset IDs and versions, source checksums, targets, dimensions, class counts, missingness, and software-version fields.

Raw snapshots, OpenML caches, trained models, and run outputs are ignored by Git because of their size and are absent from the current checkout. A publishable replay must regenerate or restore them and bind their cryptographic hashes in the final study seal.

## Reproduction stages

```bash
python3 \
  scripts/fetch_openml_suite.py --config reproduction/openml/config.json
```

Later stages consume only the sealed dataset manifest; they never resolve datasets by a mutable name.

Run and analyse the broad structural tier:

```bash
python3 \
  scripts/run_openml_structural.py \
  --config reproduction/openml/config.json \
  --suite-manifest reproduction/openml/manifests/suite-99-datasets.json

python3 \
  scripts/analyze_openml_structural.py \
  --summary-csv output/reproduction/openml-structural-summary.csv \
  --summary-json output/reproduction/openml-structural-summary.json \
  --suite-manifest reproduction/openml/manifests/suite-99-datasets.json \
  --output-json output/reproduction/openml-structural-analysis.json \
  --output-md output/reproduction/reports/openml-structural-results.md
```

Run the frozen tree attack/capacity subset and verify every generated model,
score table, complete target/reference cell histogram, and raw count:

```bash
python3 \
  scripts/run_openml_membership.py \
  --config reproduction/openml/config.json \
  --subset-manifest reproduction/openml/manifests/expensive-subsets.json

python3 \
  scripts/analyze_openml_membership.py \
  --summary output/reproduction/openml-membership-summary.json \
  --workspace "$PWD" \
  --output-json output/reproduction/openml-membership-analysis.json \
  --output-md output/reproduction/reports/openml-membership-results.md
```

Run the non-private MLP tier and the three-release composition tier:

```bash
python3 \
  scripts/run_openml_mlp.py \
  --config reproduction/openml/config.json \
  --mlp-config reproduction/openml/mlp-config.json \
  --subset-manifest reproduction/openml/manifests/expensive-subsets.json

python3 \
  scripts/run_openml_composition.py \
  --config reproduction/openml/config.json \
  --suite-manifest reproduction/openml/manifests/suite-99-datasets.json
```

Run the post-hoc exact-metadata adversary sensitivity tier:

```bash
python3 \
  scripts/run_openml_metadata_adversary.py \
  --config reproduction/openml/config.json \
  --metadata-config reproduction/openml/metadata-adversary-config.json \
  --subset-manifest reproduction/openml/manifests/expensive-subsets.json

python3 \
  scripts/analyze_openml_metadata_adversary.py \
  --summary output/reproduction/openml-metadata-adversary-summary.json \
  --workspace "$PWD" \
  --output-json output/reproduction/openml-metadata-adversary-analysis.json \
  --output-md output/reproduction/reports/openml-metadata-adversary-results.md
```

Run DP-SGD with a matched non-private control and independently replay the
sealed accountant ledgers:

```bash
python3 \
  scripts/run_openml_dp_sgd.py \
  --config reproduction/openml/config.json \
  --dp-config reproduction/openml/dp-sgd-config.json \
  --subset-manifest reproduction/openml/manifests/expensive-subsets.json

python3 \
  scripts/analyze_openml_dp_sgd.py \
  --summary output/reproduction/openml-dp-sgd-summary.json \
  --non-private-summary output/reproduction/openml-mlp-summary.json \
  --workspace "$PWD" \
  --output-json output/reproduction/openml-dp-sgd-analysis.json \
  --output-md output/reproduction/reports/openml-dp-sgd-results.md
```

Run multi-shadow membership, controlled attribute/reconstruction, and
finite-population validation:

```bash
python3 \
  scripts/run_openml_multi_shadow.py \
  --config reproduction/openml/config.json \
  --shadow-config reproduction/openml/multi-shadow-config.json \
  --subset-manifest reproduction/openml/manifests/expensive-subsets.json

python3 \
  scripts/run_openml_inference.py \
  --config reproduction/openml/config.json \
  --inference-config reproduction/openml/inference-config.json \
  --subset-manifest reproduction/openml/manifests/expensive-subsets.json

python3 \
  scripts/run_openml_population_validation.py \
  --population-config reproduction/openml/population-validation-config.json \
  --suite-manifest reproduction/openml/manifests/suite-99-datasets.json
```

## Registered evidence tiers

- Broad structural tier: the registered design covers every eligible dataset in the 72-dataset suite manifest.
- Repeated capacity tier: the design selects a deterministic, size/class/feature-stratified subset before outcomes are observed and requires complete target and reference leaf-signature histograms for every capacity.
- Attack tier: the design pre-declares datasets and capacities and requires raw member/nonmember scores and TP/FP/TN/FN counts.
- Neural tier: the design pre-declares a subset with independently fitted non-private MLP pipelines, repeated seeds, utility, and empirical attacks.
- DP tier: the design specifies shallow MLPs trained with independent Poisson sampling, per-example clipping, and Gaussian noise at two budgets, with sealed ledgers and a separate exact integer-order RDP replay. Public benchmark preprocessing is explicitly outside the private mechanism; production data-dependent preprocessing must be privatized or composed.
- Multi-shadow tier: 15 shadow models per target with exact regular in/out assignment and a per-record Gaussian likelihood-ratio score. This is LiRA-style, not the complete augmented online LiRA protocol.
- Controlled-inference tier: same-side-information no-model and model-enhanced attacks for attribute inference and one-feature reconstruction, with direct ground-truth scoring and multiplicity adjustment.
- Finite-population tier: the design requires complete benchmark-population histograms, probability samples without replacement, exact simultaneous hypergeometric lower bounds, and a deliberately biased invalid-design control.
- Decision-theory witness tier: the planned all-dataset search uses composition rosters to find decision-metric reversals, population-anchor reversals, and assessed/released-interface separation witnesses, followed by independent raw-row replay.
- Composition tier: the design registers all 72 datasets and evaluates three releases on the exact intersection of their sealed target-training rosters.
- Metadata-adversary sensitivity tier: the design registers 96 tree release configurations, a metadata-only no-model baseline, and a combined model-plus-metadata attack. The registered adversary receives exact full-source and target-training summaries, including minima, maxima, range, mean, median, standard deviation, variance, quartiles/IQR, MAD, missingness, cardinalities, and categorical/class frequencies.

Any exclusion must be recorded with a machine-readable reason; a failed dataset is never silently dropped.

## Current retained status and provisional run ledger

The current checkout verifies only that the suite manifest records 72 OpenML-CC18 dataset entries and 874,726 source rows. It does not retain the raw dataset snapshots, generated model/run artifacts, witness summaries, raw witness rows, or top-level study seal needed to verify completed-run claims.

Earlier working records listed 216 broad tree runs, 96 tree capacity/attack configurations, 24 MLP target/reference pairs, 72 composition analyses, 96 metadata-sensitivity runs, 48 DP-SGD configurations, eight multi-shadow targets with 120 shadow models, 16 controlled-attribute runs, 16 partial-reconstruction runs, and 72 finite benchmark populations. They also listed 84 decision-metric reversals, 206 population-anchor reversals, and 105 interface-substitution separations. These are provisional prior-run configuration counts, not independent cases or unique-dataset counts. They have not been independently verified from the current artifact and must not be cited as results.

Before reporting any quantitative finding, reconstruct the registered inputs, rerun every tier, archive the generated outputs and environment records, replay selected witnesses from hash-checked raw rows, and create a binding study seal.

After the registered models and raw rosters have been regenerated, build and replay the decision-theory witnesses:

```bash
python3 \
  scripts/build_openml_decision_witnesses.py
python3 \
  scripts/analyze_openml_decision_witnesses.py
```

After all validation scripts pass, create the top-level evidence seal:

```bash
python3 \
  scripts/seal_openml_reproduction.py
```

The seal is `output/reproduction/openml-study-manifest.json`. It hashes retained configurations, code, schemas, examples, summaries, and analyses. Generated reports remain under the ignored `output/` tree.
