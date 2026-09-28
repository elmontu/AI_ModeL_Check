# Research plan: person-level assurance for model exports

Updated 28 September 2026. This is the current plan. It supersedes the September 25 plan
for future work while retaining that plan and its experimental records as history.
The manuscript remains `academic/paper/mra-paper.tex`.

## Start here

A public agency may reuse the same people's records to train several models, and
may give those models to different recipients. Those recipients can retain and
combine their copies. Replacing a model, changing the dataset name or removing
records from current training does not remove earlier disclosures.

The agency therefore needs a common account of what it has already released,
which people each new computation affects, and whether the proposed models remain
useful under the remaining privacy allowance. A dependency graph can organize the
evidence. It cannot make an unsafe training procedure private or establish that
an incomplete account includes every export.

The concrete research question is: **can the agency maintain correct person-level
assurance across changing model releases at practical cost, and which private
computations retain enough information for the required workloads?**

The central technical question is now narrower: **after a model has already been
exported, can we construct a useful new model with an exactly checked bound for
the combined history, at a computational cost the release pipeline can support?**
A bookkeeping representation and a new learning mechanism answer different
questions. Ledger/graph equivalence remains a control, not the main contribution.

## Completed follow-up and current priorities

The [28 September follow-up](review-followup-20260928/README.md) replaces the
previous list of missing next steps with executable results:

1. **Count-based extension:** permutation invariance gives a lossless reduction
   to category counts. For four record values, n20 has 7,084 variables instead of
   4.4 trillion ordered-dataset variables. Exactly checked curves extend through
   n40 and compare against optimized independent composition. This is a finite
   exchangeable model family, not arbitrary-model scalability.
2. **Corrected utility study:** a frozen design with 96 independent hidden-teacher
   worlds repairs the public-information boundary. Known workloads, strong
   caching and nonprivate controls limit the conclusion. Weak-signal gains remain
   small; no gain is claimed over competent caching of identical tasks.
3. **Executed release enforcement:** the same central account runs the optimizer,
   checks its exact certificate, samples one conditional extension and commits
   both models. Three timing repeats per roster size give a 2.30-second median
   complete path at n20, with final independent audit measured separately.

The next research gates are (a) a nontrivial richer model or record alphabet whose
old joint law remains analyzable; (b) an equally informed central competitor
after the same old disclosure, including private or uncertain task selection;
and (c) an identified execution boundary for end-to-end operational evaluation.
Do not assume an agency RR-extension use case has already been observed. Official
synthetic-data publication provides broader motivation, not that specific evidence.
The remaining sections retain the original accounting study and its boundaries.

## 1. Contract before performance

The bounded instantiation protects replacement of all declared values belonging
to one registered person, across that person's fixed rows and dataset versions.
Membership, counts, task definitions and the control schedule are fixed independently
of protected values. This is value-replacement privacy, not participation privacy.
An institution choosing participation protection needs a corresponding different
mechanism, sensitivity analysis and metadata treatment.

All covered recipients may pool models and visible decisions. Fresh independent
computations are charged; descendants of the same certified private output reuse
its charge. Distinct executions with equal realized bytes are not one execution.
General shared-randomness constructions require a joint certificate and remain
outside the initial whitelist; the implemented count-based two-model certificate
is now a narrow, exactly verified exception. Pure epsilon and Gaussian/zCDP accounts
are separate families. A person's charge uses a person-calibrated certificate, or
a justified conversion from a row-level certificate; it is never a renamed row bound.

Person identities and linkage are trusted registered inputs. Unknown aliases,
incompatible scopes or unsupported dependencies block the bounded gate. Pairwise
overlap counts alone cannot justify exact person accounting. All covered output
must pass the gate, and producer evidence must be truthful. These assumptions are
explicit deployment obligations, not results of the synthetic experiment.

## 2. What existing research already supplies

| Foundation | Consequence for our positioning |
|---|---|
| [Sage, SOSP 2019](https://arxiv.org/abs/1909.01502) | Cumulative model accounting, privacy blocks and private quality validation are established. |
| [PrivateKube, OSDI 2021](https://www.usenix.org/conference/osdi21/presentation/luo) | Privacy is a managed, nonrenewable resource; reservation and scheduling predate our gate. |
| [Cohere, IEEE S&P 2024](https://arxiv.org/abs/2301.08517) | Central privacy management across overlapping applications and global users is a close architectural baseline. |
| [ProPer, POPL 2015](https://ebadi.github.io/paper-popl2015/) | Provenance and record multiplicity already support individual accounting. Only the author abstract and institutional record were accessible in the preceding review. |
| [DProvDB, PACMMOD/SIGMOD 2024](https://arxiv.org/abs/2309.10240) | Privacy provenance and jointly private reuse of a common Gaussian answer are established; the workload is database queries, not arbitrary trained-model histories. |
| [Bun and Steinke](https://arxiv.org/abs/1605.02065) | Gaussian calibration, zCDP composition and conversion are foundations, not new theorems in this paper. |

The [primary-source comparison](central-graph-implications-20260926/closest-work.md)
records scope and access limitations. These citations motivate strong controls;
they do not establish that our combination is novel. No literature-wide absence
claim is made.

## 3. Completed evidence in this revision

The [frozen implementation/evaluation scope](central-audit-validation-20260926/PLAN.md)
separates three pieces of evidence:

1. A written conditional accounting invariant, plus equivalence of a correct exact
   ledger and graph under identical certificates. Standard privacy composition is
   cited. The proof assumes truthful approved computations and complete mediation.
2. A bounded authoritative local gate and matched cost experiment. The comparison
   includes a sound coarse account and a strong exact ledger with reuse and cached
   source sets; the ledger is not deliberately forced to rescan every history.
   Durable reservations, artifact bindings, repeated delivery, revocation and
   concurrent requests are checked independently of prediction quality.
3. Generic person-level utility experiments. Clipping each person's aggregate
   bounds sensitivity; fresh, shared-source and workload-aware central mechanisms
   are compared with public/omission and nonprivate controls. Repeated observations,
   changing task directions, signal and number of releases replace named attributes
   as the experimental factors. Population draws and noise draws remain distinct.

The experiment must state which labels and task-relevant observations exist before
the first private computation. A reusable source cannot answer genuinely new labels
merely because later tasks are called post-processing. A workload-aware baseline
may know a fixed future task set; this is stronger prior knowledge than an unknown
future workload and must be reported as such.

The [completed evidence report](central-audit-validation-20260926/README.md)
records the results. Thirty gate tests and independent mutation probes pass.
The 108-trial comparison checks 2,808 proposals with no reference mismatch;
all 36 exact-ledger/graph histories agree. Verified disjointness raises admissions
from 10/24 to 24/24, but no consistent graph speed advantage appears. A separate
18-trial follow-up reduces 2,048-alias registration from 13.093 s to 0.0198 s by
batching transactions, without changing the accounting or delivered bytes.

Five fitted models for 600 people and 1,800 rows pass the actual-package gate
integration and independent recipient replay. The sixth computation is refused
before its noise draw. This uses fresh OS-backed noise but does not certify a
finite-machine Gaussian implementation or an untrusted producer.

The utility run contains 64 independent worlds and two noise draws per world.
It supports person aggregation and avoiding redundant private computations. It
does not establish generic reuse as superior to an equally informed joint-workload
mechanism. A post-hoc public-range analysis improves failed unbounded predictions;
the original failures remain. The known-generating-law public control is better
in displayed cases, so necessity of protected training data is not established.

## 4. Interpretation rules

- Exact ledger/graph disagreement blocks the correctness claim.
- More admissions than a coarse account demonstrate use of verified overlap, not
  a novel composition theorem or a benefit unique to graphs.
- Retained old models stay in the history. Revocation does not refund exposure.
- A matched privacy allowance is necessary but not sufficient for a fair utility
  comparison: inputs, prediction tasks, public knowledge and release interfaces
  must also be stated.
- Existing row-level deletion evidence remains row-level. New person-level
  experiments do not retrospectively change its adjacency.
- Mechanism improvements, representation changes and reservation policy effects
  are reported separately. Failed comparisons remain evidence.
- Synthetic bounded controls do not establish private SLM training, cross-agency
  enforcement, real-person linkage quality or production Gaussian sampling.

## 5. Decisions and next research tests

Use the exact ledger as the initial implementation default and retain the graph
as an explanatory/audit view: the completed comparison does not establish a general
indexing advantage. Keep atomic batch registration. Prefer the workload-aware
central mechanism when its input and advance-knowledge requirements are allowed.
If person-level protection makes a task infeasible, revise contribution bounds,
task design or mechanism; do not present an unchanged row-level allowance as
person-level protection.

The next scientific tests should isolate genuinely unavailable future responses,
private workload/utility selection, and conditions under which protected data beat
an appropriate public-data control. Any claimed advantage must be measured against
the strongest equally informed central method. A larger deployment-cost study
should vary source/person incidence and concurrent updates independently of model
size; the present 1,024-person maximum does not establish national-scale performance.

The next deployment study needs an identified participating boundary, trusted
identity mapping, actual export mediation, authenticated operators, recovery and
external protection against account forks. Central authority need not centralize
all raw data. The privacy budget allocation policy also needs an explicit public
purpose: a valid accountant alone cannot choose which future projects deserve
remaining allowance.

The MLSys ambition remains a substantive systems contribution under a meaningful
privacy contract. Large corpora, more model names or additional wrapper tests are
not substitutes for a proved capability or measured advantage over strong controls.
