# Real-model membership clearance demonstration

This prospective local recipe trains a real categorical Naive Bayes model on
scikit-learn's public Wine records. It assesses an exported model-only package
using mechanism evidence, rather than interpreting a weak attack as a privacy
proof. It creates a new candidate; earlier conventional models keep their
original assessments.

## Run and inspect

1. Start the checkout with `python scripts/start_demo.py` (or `python3` on
   Linux/macOS). Existing research sources can remain configured on D.
2. Under **More guided workflows**, select **Open private-training wizard** in
   **Train with clearance evidence**. Wine and the private categorical preset
   are preselected. The final **Start training** action submits one job.
3. Inspect the completed run's scientific bound, held-out utility, real attack
   findings, controls and limitations. Utility is reported honestly even if
   noise makes it worse than the public comparator; there is no retry-until-pass.
4. Open its Education case, select **Check inputs**, then **Run assessment** to
   independently recheck the bound files and retain a new assessment attempt.
5. Use **Download verified recipient model** for the exact assessed package.
   Missing or changed mechanism, model, policy or request evidence is refused.
   The operator evidence ZIP is a separate audit bundle and is outside this
   recipient interface. A saved result describes its recorded attempt; it is
   not proof that subsequently edited evidence remains valid.

The assessment retains FPR target **0.10** and membership TPR tolerance **0.20**.
Its prospective policy accepts a mechanism ceiling and records an explicit
waiver of institutional attack-battery qualification for this mathematical local
example. This waiver does not supply independent agency acceptance. Existing
`ceiling_prohibited` policies are not changed.

## What is actually trained

The recipe fixes classes 0, 1, 2 and two public features before fitting:

| Feature | Wine column | Fixed bin edges |
| --- | --- | --- |
| Alcohol | 0 | 11, 12, 13, 14 |
| Proline | 12 | 250, 500, 750, 1000, 1250, 1500 |

Bins include the outer intervals. No scaling, private range selection,
hyperparameter search or discovered class vocabulary is fitted. The public
teaching split is fixed before the private trainer; the guarantee starts at
that trainer's valid input records. The held-out evaluation and its exact
public-data comparator remain operator diagnostics, outside the recipient
package. No claim protects private dataset selection or an agency ingestion
pipeline.

Each valid training record increments one class count and one bin count for
each of the two features. Therefore add/remove-record adjacency has L1
sensitivity **3**. Counts use arbitrary-precision integers. Independent
geometric noise is added to every count before negative-count clamping,
smoothing and probability normalization. The exported classifier learns from
these noisy counts; it is not a constant or hand-written prediction fixture.

## Mechanism and accountant

For fixed `B=9`, each noise draw is the difference of two independent
Geometric0 draws, with exact continuation probability `q=9/10`. The sampler
uses `secrets.randbelow(10)` without a published seed, draw cap, truncation or
resampling of inconvenient outputs. The difference has the two-sided geometric
law proportional to `q^abs(k)`. Noise and raw training counts are not retained.

Neighbouring count vectors differ by at most 3 in L1. Their output likelihood
ratio is bounded by `(10/9)^3`, and
`3 * log(10/9) <= 3/9 = 1/3`. The accountant therefore conservatively records
pure record-level DP with **epsilon at most 1/3 and delta 0**. Derived model
parameters and all local predictions are postprocessing of the same released
noisy counts. The existing native DP analyzer then bounds membership TPR at
FPR 0.10 by approximately **0.13957**, below tolerance 0.20.

The geometric count mechanism follows
[Ghosh, Roughgarden and Sundararajan, Example 2.1](https://timroughgarden.org/papers/priv.pdf).
Sensitivity, postprocessing and composition are treated in
[Dwork and Roth's privacy text](https://www.cis.upenn.edu/~aaroth/Papers/privacybook.pdf).
The local randomness implementation uses
[Python's OS-backed secrets API](https://docs.python.org/3/library/secrets.html).
The bound assumes hidden independent uniform randomness and the declared valid
record domain. Local source replay does not establish host integrity, entropy
quality or agency infrastructure qualification.

## Evidence verification and recipient boundary

The worker freezes the recipe, evaluation policy, adjacency, mechanism and
source identities before fitting. A separate verifier recomputes the rational
accountant, model postprocessing, public fixture joins, artifact hashes and
assessment inputs. It derives the accountant and complete-pipeline flags from
those checks; a browser assertion or an uploaded boolean cannot establish them.
The native assurance engine produces the assessment report.

The recipient gets only `recipient-package.json`: the fixed public schema,
noisy counts and model probabilities derived from them. The allowlisted inert
JSON loader accepts no executable pickle, private rows, raw counts, random
seed, noise realization or training-membership roster. Operator timestamps,
source manifests, utility evaluation and red-team/audit diagnostics are not part
of that assessed package. The exact recipient-only endpoint verifies the
retained run before returning its bytes.

Real membership, extraction, attribute and perturbation screens run on the
reloaded model where compatible. Unsupported structure, tree and retraining
checks remain visible. Independent known-leak and null prediction controls
exercise the observation pipeline; they are separate from the mathematical
privacy calculation and institutional attack-battery qualification.

## Use the exported model

From the same installed checkout, predict from the downloaded inert package:

```powershell
# Windows: use the installed demo Python, and your downloaded package path.
& .\.local\demo-venv\Scripts\python.exe -m model_release_assurance.private_model_clearance --predict-package D:/YOUR_FOLDER/recipient-package.json --alcohol 13.2 --proline 1050
```

```bash
# Linux/macOS
.local/demo-venv/bin/python -m model_release_assurance.private_model_clearance --predict-package /YOUR_FOLDER/recipient-package.json --alcohol 13.2 --proline 1050
```

This runs model inference only. It does not train a second model or reassess the
package. The expected input is these two numeric features; labels are Wine
classes, not healthcare decisions.

## Limits of a clear result

The result covers **one execution, one model-only package, add/remove-record
membership and the recorded policy metric**. It does not clear another model,
the whole Wine dataset, an operator audit ZIP, shared private preprocessing,
person-level groups, a modified package, cumulative prior disclosure, utility,
fairness or agency release authorization.

Each new noisy model release consumes additional privacy budget. Repeated
training is not free privacy refresh, and selecting favourable utility results
needs composition/selection analysis. Independent local reassessment of the
same already released bytes does not itself retrain the mechanism. Production
still requires agency-approved policy, trusted execution/key custody, private
input controls, authoritative release history and independent acceptance.
