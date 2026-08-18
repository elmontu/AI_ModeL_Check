# OpenML benchmark package

This package defines a provenance-complete OpenML benchmark run. It does not claim to reconstruct unavailable historical model artifacts.

The benchmark corpus is OpenML-CC18, suite 99. Suite membership, dataset IDs and versions, OpenML checksums, downloaded snapshot hashes, targets, dimensions, class counts, missingness, and software versions are frozen in `manifests/`.

Raw snapshots, OpenML caches, trained models, and run outputs are intentionally ignored by Git because of their size. Their cryptographic hashes remain in retained manifests.

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

Run the frozen tree attack/capacity subset and verify every retained model,
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

## Evidence tiers

- Broad structural tier: every eligible dataset in the frozen 72-dataset suite.
- Repeated capacity tier: a deterministic, size/class/feature-stratified subset selected before outcomes are observed; complete target and reference leaf-signature histograms are retained for every capacity.
- Attack tier: pre-declared datasets and capacities with raw member/nonmember scores and TP/FP/TN/FN counts.
- Neural tier: a pre-declared subset with independently fitted non-private MLP pipelines, repeated seeds, utility, and empirical attacks.
- DP tier: shallow MLPs trained with independent Poisson sampling, per-example clipping, and Gaussian noise at two budgets, with sealed ledgers and a separate exact integer-order RDP replay. Public benchmark preprocessing is explicitly outside the private mechanism; production data-dependent preprocessing must be privatized or composed.
- Multi-shadow tier: 15 shadow models per target with exact regular in/out assignment and a per-record Gaussian likelihood-ratio score. This is LiRA-style, not the complete augmented online LiRA protocol.
- Controlled-inference tier: same-side-information no-model and model-enhanced attacks for attribute inference and one-feature reconstruction, with direct ground-truth scoring and multiplicity adjustment.
- Finite-population tier: complete benchmark-population histograms, probability samples without replacement, exact simultaneous hypergeometric lower bounds, and a deliberately biased invalid-design control.
- Decision-theory witness tier: an all-dataset search over retained composition rosters for decision-metric reversals, population-anchor reversals, and assessed/released-interface separation witnesses, followed by independent raw-row replay.
- Composition tier: all 72 datasets, with three releases evaluated on the exact intersection of their sealed target-training rosters.
- Metadata-adversary sensitivity tier: all 96 tree release configurations, with a metadata-only no-model baseline and combined model-plus-metadata attack. The adversary receives exact full-source and target-training summaries, including minima, maxima, range, mean, median, standard deviation, variance, quartiles/IQR, MAD, missingness, cardinalities, and categorical/class frequencies.

Any exclusion must be recorded with a machine-readable reason; a failed dataset is never silently dropped.

## Completed benchmark corpus

- 72/72 OpenML-CC18 datasets frozen and processed; 874,726 source rows.
- 216/216 broad tree runs, each with a complete cell histogram and three pre-declared seeds.
- 96/96 tree capacity/attack configurations, representing 192 independently trained target/reference models.
- 24/24 MLP target/reference pairs over eight datasets and three seeds, representing 48 neural models.
- 72/72 three-release composition analyses, reusing the 216 broad tree artifacts.
- 96/96 exact-metadata sensitivity runs and 192 attack evaluations; these are explicitly post-hoc.
- 48/48 DP-SGD dataset-seed-budget runs, including target/reference mechanisms and matched non-private controls; every accountant ledger replayed.
- 8/8 multi-shadow targets and 120 shadow models.
- 16/16 controlled attribute and 16/16 partial-reconstruction runs.
- 72/72 finite benchmark populations with complete truth and exact simultaneous bounds.
- 72/72 composition populations searched for non-degenerate decision-theory witnesses; 84 metric reversals, 206 anchor reversals, and 105 substitution separations found, with the selected witnesses independently replayed.

The baseline tiers trained 456 release-model artifacts. The additional tiers trained 144 DP models, 48 matched non-private controls, 120 shadow models, and 64 controlled-inference attack models. These runs are independently generated and do not reconstruct unavailable historical artifacts.

Build and replay the decision-theory witnesses from the retained models and raw rosters:

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
