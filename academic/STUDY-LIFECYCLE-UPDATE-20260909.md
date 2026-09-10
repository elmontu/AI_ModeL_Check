# Independent-model and lifecycle update — September 9, 2026

The [canonical manuscript](paper/mra-paper.tex) now includes a completed
independent synthetic model study and a tested local lifecycle reference.
The government/ethics review package was cancelled before any package files
were created. Its proposed government-evaluation workstream was removed from
the revision appendix. Ordinary research ethics disclosures and limits on
government-effectiveness claims remain in the paper.

This record updates the prospective work in the earlier
[review revision](REVIEW-REVISION-20260909.md); that earlier report and its
numerical receipts remain historical snapshots.

| Completed improvement | Evidence and result | Claim boundary |
|---|---|---|
| Independent model replications | [Locally frozen registration](../reproduction/independent-models-synthetic-v1/registration.json), 84 independently trained logistic models and 84 depth-2 trees; all 168 planned fits completed. | Small synthetic classifiers, not independent CNN/LLM studies or real-population validation. Four contexts and three controls are paired within models. |
| Statistical and selection replay | [Separate verifier receipt](../output/independent-models-synthetic-v1-20260909/VERIFIED.json) recounts 2,016 candidate rows and 16 primary confidence intervals from retained artifacts/draws. The [companion](paper/independent-model-study-data.json) and generated table replay exactly. | Local reproducibility, without external timestamping, external scientific validation or public availability of raw artifacts. Model-level intervals have halfwidth 0.20 before clipping. |
| Adverse decision evidence retained | The bound rule makes no observed invalid selections, but misses all 50 oracle-feasible logistic cases and 67 of 68 feasible tree cases in the boundary-stress context. Point estimates make three privacy-invalid logistic selections and utility-invalid selections for six tree models. | The same six trees fail utility in three paired contexts; they are not 18 independent failures. No observed error is not proof of zero risk, and refusal is not a useful release. |
| Concrete lifecycle mechanics | [Local SQLite reference](../src/model_release_assurance/lifecycle_reference.py) and [37-test receipt](../output/lifecycle-reference-20260909T123208.900993Z-1242217a/results.json) cover atomic updates, races, crash rollback, cumulative disclosure, current authority, expiry, leases, grants and revocation. | Separate trusted-input demonstrator; no optimizer/serving integration, authenticated external checkpoint infrastructure, distributed guarantee or Lean refinement. Integer budgets are resource counters, not statistical/DP accounting. |
| Independent counterexample correction | Review found delayed-disclosure composition and expiry-during-preparation defects after an initial 30-test pass. The corrected implementation reserves every disclosure at commit, suspends older candidates on history extension and rechecks expiry before commit. | The [initial receipt](../output/lifecycle-reference-20260909T122206.507738Z-028d9d8f/results.json) remains unchanged. Physical commit/output may still follow the final clock check. See the [verification boundary](../docs/lifecycle-reference-verification.md). |

The paper's abstract, methods, results, claim-to-evidence matrix, limitations
and research disclosures distinguish this new work from retained historical
experiments. The stronger defensible thesis remains evidence-bound assurance
under explicit premises, now with independently trained synthetic models and
concrete component checks. These additions do not establish general decision
usefulness, real-world model privacy or production lifecycle enforcement.

The [consolidated verification receipt](../output/review-revision-20260909/checks-20260909T124416.048641Z/results.json)
records **255 tests considered: 251 passed, four skipped, zero failures or
errors**. The four skipped portfolio/CLI tests require unavailable SciPy.
This is a targeted suite, not every repository test. All **109 historical
source digests match**; TeX inputs, citations, references and environments pass
source consistency checks. No dependencies were installed, historical training
was not rerun, and historical evidence was not overwritten. A prior consolidated
attempt is retained with one exact-wording manuscript assertion failure,
resolved by preserving the original accurate wording.

The manuscript was not compiled or visually verified in this update: no TeX
compiler was available on PATH. Lean was not rerun. The new claims are ordinary
Python checks and finite-world statistical evidence, not new machine-checked
theorems. Pre-integration paper copies are retained under
`output/study-lifecycle-paper-20260909/before/`.

[Reproduction instructions](../reproduction/independent-models-synthetic-v1/README.md)
provide checks that replay stored evidence without refitting. The registration,
frozen programs, completed run, failed historical studies and both lifecycle
receipts remain separately identified.

The three highest-impact next steps are:

1. Design a better-powered study with independently trained larger models and
   realistic populations/interfaces. Prespecify boundary usefulness and compare
   equivalent data/error budgets; investigate the observed abstention cost
   before changing thresholds or intervals.
2. Integrate lifecycle checks with actual assessment and output admission, then
   test current authenticated authority/checkpoints, crash recovery and deadline
   enforcement at the serving boundary. Keep broader formal claims conditional
   until a refinement argument exists.
3. Obtain independent mathematical review and prepare a shorter, typeset
   manuscript with an accessible artifact inventory. Preserve the adverse
   results and distinguish all historical, new empirical and formal evidence.
